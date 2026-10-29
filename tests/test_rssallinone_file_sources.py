"""Durable origins survive card deletion without extra hashing or filename guesses."""

import hashlib
import importlib
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "rss_file_source_tests"
namespace = types.ModuleType(PACKAGE)
namespace.__path__ = [str(ROOT / "plugins.v2" / "rssallinone")]
sys.modules[PACKAGE] = namespace
database = importlib.import_module(PACKAGE + ".database")
hashes = importlib.import_module(PACKAGE + ".file_hashes")
manager = importlib.import_module(PACKAGE + ".file_manager")


class Gateway:
    @staticmethod
    def recognize(_title):
        return types.SimpleNamespace(begin_season=None), types.SimpleNamespace(
            title="Demo", tmdb_id=42, season=None, category="Movies",
        )

    @staticmethod
    def recognize_manual(*_args):
        return Gateway.recognize("")

    @staticmethod
    def media_type(_media):
        return "movie"

    @staticmethod
    def media_payload(_media):
        return {"title": "Demo"}

    @staticmethod
    def meta_payload(_meta):
        return {}

    @staticmethod
    def plan_inventory_files(_media, files, **_kwargs):
        return {
            "expected_files": [
                {"file_index": row["index"], "source_name": row["name"],
                 "new_rel": row["name"], "file_size": row["size"]}
                for row in files
            ],
            "total_files": len(files),
        }


class FileSourceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "Movie.mkv"
        self.path.write_bytes(b"movie-source")
        self.store = database.SQLiteStore(self.root / "state.db")
        self.store.initialize()
        self.cache = hashes.FileHashCache(self.store, threading.Event(), Mock())
        self.url = "https://example.invalid/details.php?id=123"

    def card(self, paths=None, url=None, media_id="qb-card", mappings=True):
        paths = paths or [self.path]
        details = {"rss_source": {"detail_url_masked": url or self.url}}
        if mappings:
            details["file_mappings"] = [
                {"media_id": media_id, "file_index": index, "current_source_path": str(path)}
                for index, path in enumerate(paths)
            ]
        record = {
            "id": media_id, "state": "identified", "source_path": str(paths[0]),
            "downloader_id": "qb", "info_hash": "abc" if media_id == "qb-card" else media_id,
            "details": details,
        }
        self.store.upsert_media_item(record)
        return record

    def counts(self):
        with self.store.connection() as connection:
            return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                         for table in ("file_origins", "file_origin_links", "file_hashes"))

    def test_delete_rename_hardlink_restart_and_manual_identification_restore_both(self):
        self.card()
        expected = self.cache.ensure(self.path)
        self.assertTrue(self.store.delete_media_item("qb-card"))
        linked = self.root / "linked.mkv"
        os.link(self.path, linked)
        self.path.rename(self.root / "renamed.mkv")
        reopened = database.SQLiteStore(self.store.path)
        reopened.initialize()
        service = manager.LocalFileManagerService(reopened, gateway=Gateway())
        notify = Mock()
        reopened.on_media_files_changed = notify
        with patch.object(hashes.hashlib, "sha1", side_effect=AssertionError("must reuse")):
            result = service.recognize_entry(
                linked, manual_override={"media_type": "movie", "tmdb_id": 42},
            )
            self.assertEqual(result["item"]["details"]["rss_source"]["detail_url_masked"], self.url)
            cache = hashes.FileHashCache(reopened, threading.Event(), Mock())
            self.assertEqual(cache.ensure(linked), expected)
        notify.assert_not_called()
        self.assertEqual(self.counts(), (1, 1, 1))
        self.assertTrue(reopened.delete_media_item(result["media_id"]))
        second = service.recognize_entry(linked)
        self.assertEqual(second["item"]["details"]["rss_source"]["detail_url_masked"], self.url)
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_no_hash_during_restore_and_missing_hash_still_waits_for_import(self):
        self.card()
        self.store.delete_media_item("qb-card")
        notify = Mock()
        self.store.on_media_files_changed = notify
        with patch.object(hashes.hashlib, "sha1", side_effect=AssertionError("no new hash")):
            result = manager.LocalFileManagerService(self.store, gateway=Gateway()).recognize_entry(self.path)
        notify.assert_not_called()
        self.assertEqual(self.store.initial_hash_paths(result["media_id"]), [])
        self.assertEqual(self.counts(), (1, 1, 0))
        self.assertEqual(self.cache.ensure(self.path), hashlib.sha1(b"movie-source").hexdigest())

    def test_first_file_manager_identification_never_queues_hashes(self):
        service = manager.LocalFileManagerService(self.store, gateway=Gateway())
        notify = Mock()
        self.store.on_media_files_changed = notify
        for override in (None, {"media_type": "movie", "tmdb_id": 42}):
            with self.subTest(override=override):
                with patch.object(self.cache, "ensure") as ensure:
                    result = service.recognize_entry(self.path, manual_override=override)
                    self.cache.prepare_media(result["media_id"])
                self.assertEqual(result["state"], "identified")
                self.assertEqual(self.store.hash_candidate_ids(), [])
                ensure.assert_not_called()
                notify.assert_not_called()
                self.assertEqual(self.counts(), (0, 0, 0))
                self.store.delete_media_item(result["media_id"])

    def test_old_file_manager_queue_is_skipped_after_restart_without_losing_metadata(self):
        expected = self.cache.ensure(self.path)
        record = self.card(media_id="local-card")
        record["downloader_id"] = "FILE"
        record["details"]["source_identity"] = {"kind": "local_file"}
        with self.store.write_connection() as connection:
            connection.execute("DELETE FROM media_hash_preparations WHERE media_id=?", ("local-card",))
        self.store.upsert_media_item(record, prepare_hashes=True)
        self.assertEqual(self.store.hash_candidate_ids(), ["local-card"])
        reopened = database.SQLiteStore(self.store.path)
        reopened.initialize()
        cache = hashes.FileHashCache(reopened, threading.Event(), Mock())
        with patch.object(cache, "ensure") as ensure:
            for media_id in reopened.hash_candidate_ids():
                cache.prepare_media(media_id)
        ensure.assert_not_called()
        self.assertEqual(reopened.hash_candidate_ids(), [])
        self.assertEqual(reopened.get_file_sha1(database.file_identity(self.path)[2]), expected)
        self.assertEqual(reopened.find_file_sources([self.path])["source"]["detail_url"], self.url)

    def test_unidentified_card_restores_link_without_tmdb(self):
        self.card()
        self.store.delete_media_item("qb-card")
        gateway = Mock()
        gateway.recognize.return_value = (None, None)
        gateway.meta_payload.return_value = {}
        result = manager.LocalFileManagerService(self.store, gateway=gateway).recognize_entry(self.path)
        self.assertEqual(result["state"], "unidentified")
        self.assertEqual(result["item"]["details"]["rss_source"]["detail_url_masked"], self.url)
        self.store.delete_media_item(result["media_id"])
        self.assertEqual(self.counts(), (1, 1, 0))

    def test_same_name_other_file_and_changed_content_never_inherit_source(self):
        self.card()
        self.cache.ensure(self.path)
        other = self.root / "other" / self.path.name
        other.parent.mkdir()
        other.write_bytes(self.path.read_bytes())
        self.assertEqual(self.store.find_file_sources([other])["source"], {})
        self.path.write_bytes(b"changed-file-content")
        self.assertEqual(self.store.find_file_sources([self.path])["source"], {})
        self.assertFalse(self.store.find_file_sources([self.path])["known"])

    def test_series_deduplicates_origin_and_conflicting_or_mixed_folder_is_not_guessed(self):
        episodes = []
        for index in range(3):
            path = self.root / f"E{index}.mkv"
            path.write_bytes(f"episode-{index}".encode())
            episodes.append(path)
        self.card(episodes)
        self.assertEqual(self.counts(), (1, 3, 0))
        self.assertEqual(self.store.find_file_sources(episodes)["source"]["detail_url"], self.url)
        unknown = self.root / "unknown.mkv"
        unknown.write_bytes(b"unknown")
        self.assertEqual(self.store.find_file_sources([*episodes, unknown])["source"], {})
        self.card([episodes[1]], url="https://example.invalid/details.php?id=456", media_id="other")
        result = self.store.find_file_sources(episodes)
        self.assertTrue(result["ambiguous"])
        self.assertEqual(result["source"], {})

    def test_identical_updates_do_not_write_origins_or_hash_cache(self):
        record = self.card()
        self.cache.ensure(self.path)
        _, stat, identity_key = database.file_identity(self.path)
        expected = self.cache.ensure(self.path)
        before = self.counts()
        with self.store.write_connection() as connection:
            connection.executescript("""
                CREATE TRIGGER forbid_origin_update BEFORE UPDATE ON file_origins
                BEGIN SELECT RAISE(ABORT, 'unnecessary origin write'); END;
                CREATE TRIGGER forbid_hash_update BEFORE UPDATE ON file_hashes
                BEGIN SELECT RAISE(ABORT, 'unnecessary hash write'); END;
            """)
        self.store.upsert_media_item(record)
        self.store.save_file_sha1(identity_key, expected, str(self.path.resolve()), stat.st_size)
        self.assertEqual(self.counts(), before)

    def test_source_urls_exclude_credentials_and_sensitive_query_parameters(self):
        self.card(url="https://user:password@example.invalid/details.php?id=123&passkey=private&api_key=private")
        self.assertEqual(self.store.find_file_sources([self.path])["source"]["detail_url"], self.url)
        with self.store.connection() as connection:
            value = json.dumps(dict(connection.execute("SELECT * FROM file_origins").fetchone()))
        self.assertNotIn("private", value)
        self.assertNotIn("password", value)

    def test_existing_card_migration_is_resumable_and_only_runs_once_without_hashing(self):
        record = self.card(mappings=False)
        with self.store.write_connection() as connection:
            connection.execute("DELETE FROM file_origin_links")
            connection.execute("DROP TABLE file_origins")
        self.store.initialize()
        stop = threading.Event()
        stop.set()
        self.assertEqual(self.store.backfill_file_sources(stop), 0)
        stop.clear()
        with patch.object(hashes.hashlib, "sha1", side_effect=AssertionError("no hash")):
            self.assertEqual(self.store.backfill_file_sources(stop), 1)
        self.assertEqual(self.store.find_file_sources([self.path])["source"]["detail_url"], self.url)
        self.store.initialize()
        self.assertEqual(self.store.backfill_file_sources(stop), 0)
        self.assertEqual(self.store.get_media_item(record["id"])["state"], "identified")

    def test_mapping_only_paths_are_preserved_before_the_card_is_deleted(self):
        record = self.card(mappings=False)
        record["source_path"] = str(self.root / "folder")
        self.store.upsert_media_item(record)
        self.store.replace_file_mappings("qb", "abc", [{
            "media_id": "qb-card", "file_index": 0, "current_source_path": str(self.path),
        }])
        self.store.delete_media_item("qb-card")
        self.assertEqual(self.store.find_file_sources([self.path])["source"]["detail_url"], self.url)

    def test_missing_files_do_not_delete_durable_metadata(self):
        self.card()
        self.cache.ensure(self.path)
        self.store.delete_media_item("qb-card")
        self.path.unlink()
        self.store.initialize()
        self.store.backfill_file_sources(threading.Event())
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_identity_lookup_uses_primary_key_index(self):
        with self.store.connection() as connection:
            plan = connection.execute(
                "EXPLAIN QUERY PLAN SELECT origin_key FROM file_origin_links WHERE identity_key=?",
                ("file",),
            ).fetchall()
        self.assertIn("SEARCH", " ".join(str(row["detail"]) for row in plan).upper())


if __name__ == "__main__":
    unittest.main()
