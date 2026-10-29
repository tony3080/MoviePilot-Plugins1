"""Completed qB source paths, prehashing and durable label warnings."""

import hashlib
import importlib
import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import Mock


PACKAGE = "rss_completed_sources_tests"
namespace = types.ModuleType(PACKAGE)
namespace.__path__ = [str(Path(__file__).resolve().parents[1] / "plugins.v2" / "rssallinone")]
sys.modules[PACKAGE] = namespace
database = importlib.import_module(PACKAGE + ".database")
qb_sync = importlib.import_module(PACKAGE + ".qb_sync")
hashes = importlib.import_module(PACKAGE + ".file_hashes")
layout = importlib.import_module(PACKAGE + ".layout")
actions = importlib.import_module(PACKAGE + ".media_actions")


class CompletedSourceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "downloads" / "Movie.2024.REMUX" / "Movie.mkv"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"completed-movie")
        self.store = database.SQLiteStore(self.root / "state.db")
        self.store.initialize()
        self.downloader = qb_sync.DownloaderView(
            name="qb-main", type="qbittorrent", enabled=True, default=True, ready=True,
        )
        self.raw = {
            "hash": "abc", "title": "Movie.2024", "category": "movie",
            "progress": 1.0, "state": "uploading", "size": self.source.stat().st_size,
            "save_path": str(self.root / "downloads"), "content_path": str(self.source),
        }
        media = types.SimpleNamespace(
            title="Movie", year="2024", tmdb_id=42, season=None, category="外语电影",
        )
        gateway = Mock()
        gateway.recognize.return_value = (types.SimpleNamespace(begin_season=None), media)
        gateway.recognize_manual.return_value = gateway.recognize.return_value
        gateway.media_payload.return_value = {"title": "Movie", "tmdb_id": 42}
        gateway.meta_payload.return_value = {}
        gateway.media_type.return_value = "movie"
        gateway.poster.return_value = ""
        gateway.plan_inventory_files.side_effect = lambda _media, files, **_kwargs: {
            "expected_files": [{
                "file_index": row["index"], "source_name": row["name"],
                "relative_path": "Movie (2024) {tmdbid=42}/Movie.mkv",
                "inventory_relative_path": "Movie (2024) {tmdbid=42}/Movie.strm",
                "size": row["size"],
            } for row in files],
            "expected_directory": "Movie (2024) {tmdbid=42}",
            "total_files": len(files), "plan_errors": [],
        }
        gateway.list_torrent_files.side_effect = AssertionError("must use local files")
        self.gateway = gateway
        self.service = qb_sync.QbSyncService(
            store=self.store, gateway=gateway,
            library_layout=layout.LibraryLayout.from_config(
                str(self.root / "library"),
                [{"name": "source", "prefix": str(self.root),
                  "link_roots": {"movie": str(self.root / "links")}, "enabled": True}],
            ),
        )
        now = database.utc_now()
        with self.store.write_connection() as connection:
            connection.execute(
                """INSERT INTO rss_tasks
                   (id, name, enabled, position, config_json, created_at, updated_at)
                   VALUES (?, ?, 1, 0, ?, ?, ?)""",
                ("rss-task", "RSS", json.dumps({
                    "task_type": "rss", "qb_downloader": "qb-main",
                    "qb_category": "movie", "import_enabled": True,
                }), now, now),
            )
        self.history = {
            "task_id": "rss-task", "source_key": "source", "content_key": "qb-main:abc",
            "status": "queued", "title": "Movie",
            "payload": {"downloader": "qb-main", "info_hash": "abc"},
        }
        self.store.upsert_rss_history(self.history)

    def sync(self):
        return self.service._sync_one(
            downloader=self.downloader, raw=self.raw, force_recognition=True,
        )

    def test_nested_single_file_paths_are_persisted_before_sha1_preparation(self):
        self.sync()
        card = self.store.get_media_item("qb:qb-main:abc")
        saved = self.store.list_file_mappings("qb-main", "abc")
        self.assertEqual(Path(saved[0]["current_source_path"]), self.source.resolve())
        self.assertEqual(
            card["details"]["file_mappings"][0]["current_source_path"],
            saved[0]["current_source_path"],
        )
        self.assertEqual(
            self.store.initial_hash_paths(card["id"]), [str(self.source.resolve())],
        )
        cache = hashes.FileHashCache(self.store, threading.Event(), Mock())
        cache.prepare_media(card["id"])
        key = database.file_identity(self.source)[2]
        self.assertEqual(
            self.store.get_file_sha1(key), hashlib.sha1(b"completed-movie").hexdigest(),
        )
        self.gateway.list_torrent_files.assert_not_called()

    def test_completion_prepares_only_once_and_manual_inventory_refresh_does_not_requeue(self):
        notify = Mock()
        self.store.on_media_files_changed = notify
        self.sync()
        media_id = "qb:qb-main:abc"
        notify.assert_called_once_with(media_id)
        self.store.finish_hash_preparation(media_id)
        notify.reset_mock()
        self.sync()
        self.service.refresh_media_from_saved_files(media_id)
        self.service.refresh_media_from_saved_files(
            media_id, manual_override={"media_type": "movie", "tmdb_id": 42},
        )
        notify.assert_not_called()
        self.assertEqual(self.store.hash_candidate_ids(), [])
        self.assertEqual(self.store.get_file_sha1(database.file_identity(self.source)[2]), "")

    def test_downloading_card_waits_for_completion_before_preparing_hashes(self):
        notify = Mock()
        self.store.on_media_files_changed = notify
        self.raw.update(progress=0.5, state="downloading")
        self.gateway.list_torrent_files.side_effect = None
        self.gateway.list_torrent_files.return_value = [{
            "index": 0, "name": self.source.name, "size": self.source.stat().st_size,
        }]
        self.sync()
        notify.assert_not_called()
        self.assertEqual(self.store.hash_candidate_ids(), [])
        self.raw.update(progress=1.0, state="uploading")
        self.sync()
        notify.assert_called_once_with("qb:qb-main:abc")
        self.assertEqual(self.store.initial_hash_paths("qb:qb-main:abc"), [str(self.source.resolve())])

    def test_failed_labels_survive_qb_completion_archiving_and_refresh(self):
        labels = {"requested": True, "status": "failed", "site_kind": "hdsky",
                  "reason": "站内搜索没有找到种子详情结果"}
        self.history["payload"]["site_labels"] = labels
        self.store.upsert_rss_history(self.history)
        self.raw["progress"] = 0.5
        self.raw["state"] = "downloading"
        self.gateway.list_torrent_files.side_effect = None
        self.gateway.list_torrent_files.return_value = [{
            "index": 0, "name": self.source.name, "size": self.source.stat().st_size,
        }]
        self.sync()
        self.assertEqual(
            self.store.get_torrent_snapshot("qb-main", "abc")["details"]["site_labels"],
            labels,
        )
        self.store.archive_rss_history_for_torrent("qb-main", "abc")
        self.sync()
        self.assertEqual(
            self.store.get_torrent_snapshot("qb-main", "abc")["details"]["site_labels"],
            labels,
        )
        self.raw.update(progress=1.0, state="uploading")
        self.sync()
        self.assertEqual(
            self.store.get_media_item("qb:qb-main:abc")["details"]["site_labels"], labels,
        )
        self.store.archive_rss_history_for_torrent("qb-main", "abc")
        self.sync()
        self.assertEqual(
            self.store.get_media_item("qb:qb-main:abc")["details"]["site_labels"], labels,
        )
        self.service.refresh_media_from_saved_files("qb:qb-main:abc")
        self.assertEqual(
            self.store.get_media_item("qb:qb-main:abc")["details"]["site_labels"], labels,
        )
        for status in ("not_matched", "matched"):
            with self.subTest(status=status):
                new_labels = {"requested": True, "status": status, "reason": ""}
                self.history["payload"]["site_labels"] = new_labels
                self.store.upsert_rss_history(self.history)
                self.sync()
                self.assertEqual(
                    self.store.get_media_item("qb:qb-main:abc")["details"]["site_labels"],
                    new_labels,
                )

    def test_import_repairs_old_single_file_mapping_from_saved_content_path(self):
        self.sync()
        card = self.store.get_media_item("qb:qb-main:abc")
        mappings = self.store.list_file_mappings("qb-main", "abc")
        mappings[0]["current_source_path"] = str(self.root / "downloads" / self.source.name)
        self.store.replace_file_mappings("qb-main", "abc", mappings)
        card["details"]["file_mappings"] = mappings
        self.store.upsert_media_item(card)
        self.store.finish_hash_preparation(card["id"])
        self.assertEqual(self.store.get_file_sha1(database.file_identity(self.source)[2]), "")
        result = actions.MediaActionService(self.store).prepare_monitored_import(card["id"])
        saved = self.store.list_file_mappings("qb-main", "abc")[0]
        self.assertEqual(Path(saved["current_source_path"]), self.source.resolve())
        self.assertTrue(self.source.samefile(saved["local_hardlink_path"]))
        self.assertEqual(result["state"], "importing")
        cache = hashes.FileHashCache(self.store, threading.Event(), Mock())
        self.assertEqual(
            cache.ensure(saved["local_hardlink_path"]),
            hashlib.sha1(b"completed-movie").hexdigest(),
        )

    def test_content_file_wins_over_save_directory(self):
        self.assertEqual(
            qb_sync.resolve_current_source_path(
                {"save_path": "/downloads", "content_path": "/downloads/Movie/Movie.mkv"},
                "Movie.mkv",
            ),
            "/downloads/Movie/Movie.mkv",
        )


if __name__ == "__main__":
    unittest.main()
