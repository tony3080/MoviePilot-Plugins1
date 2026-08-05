"""Filesystem-level tests for library card actions."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v2" / "rssallinone"
PACKAGE = "rssallinone_media_action_tests"


def load_package_module(name: str, filename: str):
    if PACKAGE not in sys.modules:
        package = types.ModuleType(PACKAGE)
        package.__path__ = [str(PLUGIN_DIR)]
        sys.modules[PACKAGE] = package
    full_name = f"{PACKAGE}.{name}"
    spec = importlib.util.spec_from_file_location(full_name, PLUGIN_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


database = load_package_module("database", "database.py")
load_package_module("domain", "domain.py")
media_actions = load_package_module("media_actions", "media_actions.py")
layout = sys.modules[f"{PACKAGE}.layout"]


class MediaActionServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = database.SQLiteStore(self.root / "rssallinone.db")
        self.store.initialize()
        self.service = media_actions.MediaActionService(self.store)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def add_item(self, media_id: str, mappings: list[dict], state: str = "identified"):
        self.store.upsert_media_item({
            "id": media_id,
            "state": state,
            "media_type": "tv",
            "title": "测试剧",
            "source_name": "Test.Show.S01",
            "source_path": str(self.root / "source"),
            "downloader_id": "qb-main",
            "info_hash": media_id,
            "tmdb_id": 42,
            "season": 1,
            "category": "国产剧",
            "target_name": "测试剧 (2026) {tmdbid=42}",
            "details": {},
        })
        prepared = []
        for index, mapping in enumerate(mappings):
            prepared.append({
                "file_index": index,
                "media_id": media_id,
                "source_relative_path": mapping["source_relative_path"],
                "current_source_path": str(mapping["source"]),
                "new_rel": mapping["new_rel"],
                "local_hardlink_path": str(mapping["target"]),
                "inventory_path": str(mapping.get("inventory_path") or ""),
                "inventory_exists": mapping.get("inventory_exists", False),
                "file_size": mapping["source"].stat().st_size,
                "details": mapping.get("details") or {},
            })
        self.store.replace_file_mappings("qb-main", media_id, prepared)

    def test_import_creates_only_missing_hardlinks_and_rolls_back_cleanly(self) -> None:
        source_dir = self.root / "source"
        source_dir.mkdir()
        first = source_dir / "E01.mkv"
        second = source_dir / "E02.mkv"
        first.write_bytes(b"episode-one")
        second.write_bytes(b"episode-two")
        first_target = self.root / "links" / "Show" / "E01.mkv"
        second_target = self.root / "links" / "Show" / "E02.mkv"
        self.add_item("hash-one", [
            {
                "source_relative_path": "Show/E01.mkv",
                "source": first,
                "target": first_target,
                "new_rel": "Show/Season 01/Show S01E01.mkv",
            },
            {
                "source_relative_path": "Show/E02.mkv",
                "source": second,
                "target": second_target,
                "new_rel": "Show/Season 01/Show S01E02.mkv",
                "inventory_exists": True,
            },
        ])

        queued = self.service.execute("queue_import", ["hash-one"])
        imported = self.service.execute("import", ["hash-one"])

        self.assertTrue(queued["success"])
        self.assertTrue(imported["success"])
        self.assertTrue(first_target.is_file())
        self.assertTrue(os.path.samefile(first, first_target))
        self.assertFalse(second_target.exists())
        self.assertEqual(self.store.get_media_item("hash-one")["state"], "imported")
        mappings = self.store.list_file_mappings("qb-main", "hash-one")
        self.assertEqual(mappings[0]["state"], "hardlinked")
        self.assertTrue(mappings[0]["details"]["hardlink_owned"])
        self.assertEqual(mappings[1]["state"], "existing")

        rolled_back = self.service.execute("delete_hardlinks", ["hash-one"])
        self.assertTrue(rolled_back["success"])
        self.assertFalse(first_target.exists())
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        item = self.store.get_media_item("hash-one")
        self.assertEqual(item["state"], "rolled_back")
        self.assertTrue(item["rolled_back"])

    def test_import_failure_removes_links_created_in_same_attempt(self) -> None:
        source_dir = self.root / "source"
        source_dir.mkdir()
        first = source_dir / "E01.mkv"
        second = source_dir / "E02.mkv"
        first.write_bytes(b"episode-one")
        second.write_bytes(b"episode-two")
        first_target = self.root / "links" / "E01.mkv"
        conflict_target = self.root / "links" / "E02.mkv"
        conflict_target.parent.mkdir()
        conflict_target.write_bytes(b"different-file")
        self.add_item("hash-two", [
            {
                "source_relative_path": "E01.mkv",
                "source": first,
                "target": first_target,
                "new_rel": "Show/E01.mkv",
            },
            {
                "source_relative_path": "E02.mkv",
                "source": second,
                "target": conflict_target,
                "new_rel": "Show/E02.mkv",
            },
        ])

        result = self.service.execute("import", ["hash-two"])

        self.assertFalse(result["success"])
        self.assertFalse(first_target.exists())
        self.assertEqual(conflict_target.read_bytes(), b"different-file")
        item = self.store.get_media_item("hash-two")
        self.assertEqual(item["state"], "identified")
        self.assertEqual(item["failure_code"], "hardlink_import_failed")

    def test_delete_source_uses_current_paths_and_preserves_hardlink_target(self) -> None:
        source_dir = self.root / "source"
        source_dir.mkdir()
        source = source_dir / "Movie.mkv"
        source.write_bytes(b"movie")
        external_link = self.root / "external" / "Movie.mkv"
        external_link.parent.mkdir()
        os.link(source, external_link)
        self.add_item("hash-three", [{
            "source_relative_path": "Movie.mkv",
            "source": source,
            "target": external_link,
            "new_rel": "Movie/Movie.mkv",
        }])

        result = self.service.execute("delete_source", ["hash-three"])

        self.assertTrue(result["success"])
        self.assertFalse(source.exists())
        self.assertTrue(external_link.exists())
        self.assertIsNone(self.store.get_media_item("hash-three"))

    def test_delete_both_removes_completed_workflow_but_keeps_rss_dedup(self) -> None:
        source_dir = self.root / "source"
        source_dir.mkdir()
        source = source_dir / "Movie.mkv"
        source.write_bytes(b"movie")
        hardlink = self.root / "links" / "Movie.mkv"
        hardlink.parent.mkdir()
        os.link(source, hardlink)
        self.add_item("hash-cleanup", [{
            "source_relative_path": "Movie.mkv",
            "source": source,
            "target": hardlink,
            "new_rel": "Movie/Movie.mkv",
            "details": {"hardlink_owned": True},
        }], state="imported")
        self.store.upsert_rss_history({
            "task_id": "task-a",
            "source_key": "source-cleanup",
            "content_key": "qb-main:hash-cleanup",
            "title": "Movie",
            "status": "processed",
            "payload": {"downloader": "qb-main", "info_hash": "hash-cleanup"},
        })
        self.store.schedule_qb_delete(
            task_id="task-a",
            task_name="Movie RSS",
            downloader_id="qb-main",
            info_hash="hash-cleanup",
            source_path=str(source),
            delete_files=False,
            due_at="2026-08-05T00:00:00+00:00",
        )
        job = self.store.list_qb_delete_jobs()[0]
        self.store.finish_qb_delete_job(job["id"], success=True)

        result = self.service.execute("delete_both", ["hash-cleanup"])

        self.assertTrue(result["success"])
        self.assertFalse(source.exists())
        self.assertFalse(hardlink.exists())
        self.assertIsNone(self.store.get_media_item("hash-cleanup"))
        self.assertEqual(self.store.list_file_mappings("qb-main", "hash-cleanup"), [])
        self.assertEqual(self.store.list_rss_history()["total"], 0)
        self.assertEqual(self.store.list_qb_delete_jobs(), [])
        self.assertEqual(
            self.store.find_rss_source_keys("task-a", ["source-cleanup"]),
            {"source-cleanup"},
        )

    def test_destructive_action_refuses_missing_persisted_mappings(self) -> None:
        self.store.upsert_media_item({
            "id": "no-mapping",
            "state": "identified",
            "title": "无映射",
        })

        result = self.service.execute("delete_source", ["no-mapping"])

        self.assertFalse(result["success"])
        self.assertIn("拒绝猜测", result["results"][0]["message"])

    def test_imported_refresh_rechecks_saved_strm_paths_without_recognition(self) -> None:
        source_dir = self.root / "source"
        source_dir.mkdir()
        first = source_dir / "E01.mkv"
        second = source_dir / "E02.mkv"
        first.write_bytes(b"episode-one")
        second.write_bytes(b"episode-two")
        inventory_root = self.root / "inventory"
        category_root = inventory_root / "国产剧"
        media_directory = "测试剧 (2026) - {tmdbid=42}"
        existing = category_root / media_directory / "Season 1" / "测试剧 - S01E01.strm"
        existing.parent.mkdir(parents=True)
        existing.write_text("cloud://episode-one", encoding="utf-8")
        first_rel = f"{media_directory}/Season 1/测试剧 - S01E01.mkv"
        second_rel = f"{media_directory}/Season 1/测试剧 - S01E02.mkv"
        self.add_item("hash-refresh", [
            {
                "source_relative_path": "E01.mkv",
                "source": first,
                "target": self.root / "links" / "E01.mkv",
                "new_rel": first_rel,
                "inventory_path": category_root / PurePosixPath(first_rel).with_suffix(".strm"),
            },
            {
                "source_relative_path": "E02.mkv",
                "source": second,
                "target": self.root / "links" / "E02.mkv",
                "new_rel": second_rel,
                "inventory_path": category_root / PurePosixPath(second_rel).with_suffix(".strm"),
            },
        ], state="imported")
        library_layout = layout.LibraryLayout(str(inventory_root), [])

        result = media_actions.MediaInventoryRefreshService(
            self.store, library_layout
        ).refresh("hash-refresh")

        self.assertEqual(result["inventory_state"], "partial")
        self.assertEqual(result["exists_count"], 1)
        self.assertEqual(result["total_files"], 2)
        item = self.store.get_media_item("hash-refresh")
        self.assertEqual(item["state"], "imported")
        self.assertEqual(item["details"]["inventory"]["exists_count"], 1)
        self.assertEqual(
            item["details"]["inventory"]["refresh_mode"],
            "saved_file_mappings",
        )
        mappings = self.store.list_file_mappings("qb-main", "hash-refresh")
        self.assertTrue(mappings[0]["inventory_exists"])
        self.assertFalse(mappings[1]["inventory_exists"])


if __name__ == "__main__":
    unittest.main()
