"""Regression checks for manual labels on cards backed by saved qB files."""

import hashlib
import importlib
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "rss_manual_identify_tests"
namespace = types.ModuleType(PACKAGE)
namespace.__path__ = [str(ROOT / "plugins.v2" / "rssallinone")]
sys.modules[PACKAGE] = namespace
database = importlib.import_module(PACKAGE + ".database")
hashes = importlib.import_module(PACKAGE + ".file_hashes")
layout = importlib.import_module(PACKAGE + ".layout")
qb_sync = importlib.import_module(PACKAGE + ".qb_sync")


class SavedFileManualIdentifyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "Demo"
        self.folder.mkdir()
        self.store = database.SQLiteStore(self.root / "state.db")
        self.store.initialize()
        self.media_id = "qb:removed-node:demo"
        self.source_url = "https://example.invalid/details.php?id=42"
        self.cache = hashes.FileHashCache(self.store, threading.Event(), Mock())
        self.gateway = Mock()
        self.gateway.recognize_manual.return_value = (
            types.SimpleNamespace(begin_season=None),
            types.SimpleNamespace(
                title="Correct Movie", tmdb_id=42, season=None, category="外语电影",
            ),
        )
        self.gateway.media_type.return_value = "movie"
        self.gateway.media_payload.return_value = {"title": "Correct Movie", "tmdb_id": 42}
        self.gateway.meta_payload.return_value = {}

        def plan(_media, files, **_kwargs):
            return {
                "expected_files": [{
                    "file_index": row["index"],
                    "source_name": row["name"],
                    "relative_path": "Correct Movie/" + Path(row["name"]).name,
                    "inventory_relative_path": (
                        "Correct Movie/" + Path(row["name"]).with_suffix(".strm").name
                    ),
                    "size": row["size"],
                } for row in files],
                "expected_directory": "Correct Movie",
                "total_files": len(files),
                "plan_errors": [],
            }

        self.gateway.plan_inventory_files.side_effect = plan
        self.service = qb_sync.QbSyncService(
            store=self.store, gateway=self.gateway,
            library_layout=layout.LibraryLayout.from_config(
                str(self.root / "library"),
                [{
                    "name": "test", "prefix": str(self.root), "enabled": True,
                    "link_roots": {"movie": str(self.root / "links")},
                }],
            ),
        )

    def add_card(self, count=1):
        rows = []
        for index in range(count):
            path = self.folder / f"Demo.{index}-REMUX-U版.mkv"
            path.write_bytes(f"media-{index}".encode("ascii"))
            rows.append({
                "media_id": self.media_id, "file_index": 11 + index * 2,
                "source_relative_path": "Demo/" + path.name,
                "current_source_path": str(path), "file_size": path.stat().st_size,
            })
            self.cache.ensure(path)
        self.store.upsert_media_item({
            "id": self.media_id, "state": "identified",
            "source_path": str(self.folder if count > 1 else path),
            "source_name": "Wrong identification",
            "downloader_id": "removed-node", "info_hash": "demo",
            "details": {
                "source_identity": {"kind": "qb_download"},
                "rss_source": {"detail_url_masked": self.source_url},
            },
        })
        self.store.replace_file_mappings("removed-node", "demo", rows)
        self.store.on_media_files_changed = Mock()
        return rows

    def identify(self, labels):
        return self.service.refresh_media_from_saved_files(
            self.media_id,
            manual_override={"media_type": "movie", "tmdb_id": 42},
            manual_labels=labels,
        )

    def test_saved_manual_season_reaches_naming_on_identification_and_refresh(self):
        self.add_card()
        self.gateway.media_type.return_value = "tv"
        self.gateway.recognize_manual.return_value[1].season = 4
        override = {"media_type": "tv", "tmdb_id": 42, "season": 4}
        for supplied in (override, None):
            with self.subTest(manual_override=supplied):
                self.service.refresh_media_from_saved_files(
                    self.media_id, manual_override=supplied,
                )
                self.assertEqual(
                    self.gateway.plan_inventory_files.call_args.kwargs["season_override"], 4,
                )
                self.assertEqual(
                    self.store.get_media_item(self.media_id)["details"]["manual_override"]["season"], 4,
                )
        self.store.on_media_files_changed.assert_not_called()

    def test_single_file_keeps_source_hash_and_link_after_manual_label_rename(self):
        old = self.add_card()[0]
        item = self.identify({"mandarin": True, "effects": True})
        mapping = self.store.list_file_mappings("removed-node", "demo")[0]
        renamed = Path(mapping["current_source_path"])
        self.assertTrue(renamed.is_file())
        self.assertFalse(Path(old["current_source_path"]).exists())
        self.assertEqual(renamed.name, "Demo.0-国配-特效-REMUX-U版.mkv")
        self.assertEqual(mapping["file_index"], 11)
        self.assertEqual(mapping["source_relative_path"], "Demo/" + renamed.name)
        self.assertEqual(item["source_path"], str(renamed.resolve()))
        self.assertEqual(item["tmdb_id"], 42)
        self.assertEqual(item["details"]["rss_source"]["detail_url_masked"], self.source_url)
        self.assertTrue(item["details"]["site_labels"]["mandarin"])
        with patch.object(hashes.hashlib, "sha1", side_effect=AssertionError("must reuse")):
            self.assertEqual(
                self.cache.ensure(renamed), hashlib.new("sha1", b"media-0").hexdigest(),
            )
        self.assertEqual(self.store.find_file_sources([renamed])["source"]["detail_url"], self.source_url)
        self.store.on_media_files_changed.assert_not_called()
        self.gateway.list_torrents.assert_not_called()

    def test_multifile_labels_keep_dicts_indices_sizes_and_paths_for_naming(self):
        self.add_card(count=2)
        item = self.identify({"mandarin": False, "effects": True})
        self.assertEqual(item["source_path"], str(self.folder))
        planned = self.gateway.plan_inventory_files.call_args.args[1]
        self.assertEqual([row["index"] for row in planned], [11, 13])
        self.assertEqual([row["name"] for row in planned], [
            "Demo/Demo.0-特效-REMUX-U版.mkv", "Demo/Demo.1-特效-REMUX-U版.mkv",
        ])
        for row in planned:
            self.assertEqual(row["size"], 7)
            self.assertTrue(Path(row["current_source_path"]).is_file())
        mappings = self.store.list_file_mappings("removed-node", "demo")
        self.assertEqual([row["file_index"] for row in mappings], [11, 13])
        self.assertEqual(
            [row["current_source_path"] for row in mappings],
            [row["current_source_path"] for row in planned],
        )
        self.store.on_media_files_changed.assert_not_called()

    def test_unchecked_labels_still_allow_manual_identification(self):
        old = self.add_card()[0]
        item = self.identify({"mandarin": False, "effects": False})
        self.assertEqual(item["state"], "identified")
        self.assertEqual(item["source_path"], old["current_source_path"])
        self.assertEqual(item["source_name"], Path(old["current_source_path"]).name)

    def test_rename_collision_preserves_both_files(self):
        old = self.add_card()[0]
        collision = self.folder / "Demo.0-国配-REMUX-U版.mkv"
        collision.write_bytes(b"other-file")
        with self.assertRaisesRegex(RuntimeError, "本地重命名目标已存在"):
            self.identify({"mandarin": True, "effects": False})
        self.assertEqual(Path(old["current_source_path"]).read_bytes(), b"media-0")
        self.assertEqual(collision.read_bytes(), b"other-file")


if __name__ == "__main__":
    unittest.main()
