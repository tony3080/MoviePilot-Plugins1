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

    def add_item(
        self,
        media_id: str,
        mappings: list[dict],
        state: str = "identified",
        media_type: str = "tv",
        category: str = "国产剧",
    ):
        self.store.upsert_media_item({
            "id": media_id,
            "state": state,
            "media_type": media_type,
            "title": "测试剧",
            "source_name": "Test.Show.S01",
            "source_path": str(self.root / "source"),
            "downloader_id": "qb-main",
            "info_hash": media_id,
            "tmdb_id": 42,
            "season": 1,
            "category": category,
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

    def test_active_batch_only_blocks_cards_still_owned_by_queue(self) -> None:
        imported = {"id": "done", "state": "imported"}
        another_imported = {"id": "done-2", "state": "imported"}
        existing = {"id": "already-present", "state": "existing"}
        identified = {"id": "identified", "state": "identified"}
        pending = {"id": "pending", "state": "pending"}
        importing = {"id": "active", "state": "importing"}

        self.assertEqual(
            self.service.pending_batch_action_error(
                "delete_hardlinks", [imported]
            ),
            "",
        )
        self.assertEqual(
            self.service.pending_batch_action_error(
                "delete_both", [imported, another_imported]
            ),
            "",
        )
        self.assertIn(
            "正在处理",
            self.service.pending_batch_action_error(
                "delete_both",
                [imported],
                current_media_id="done",
            ),
        )

        self.assertIn(
            "CD2 监控",
            self.service.pending_batch_action_error(
                "delete_hardlinks",
                [imported],
                watched_media_ids={"done"},
            ),
        )
        self.assertEqual(
            self.service.pending_batch_action_error(
                "delete_source", [identified, pending]
            ),
            "",
        )
        self.assertEqual(
            self.service.pending_batch_action_error(
                "import", [imported]
            ),
            "",
        )
        self.assertIn(
            "正在处理",
            self.service.pending_batch_action_error(
                "import", [importing], current_media_id="active"
            ),
        )
        self.assertIn(
            "正在处理",
            self.service.pending_batch_action_error(
                "delete_source", [importing]
            ),
        )
        self.assertEqual(
            self.service.pending_batch_action_error(
                "delete_source", [imported]
            ),
            "",
        )
        self.assertEqual(
            self.service.pending_batch_action_error(
                "delete_source", [existing]
            ),
            "",
        )
        self.assertEqual(
            self.service.pending_batch_action_error(
                "queue_import", [importing]
            ),
            "",
        )

    def test_realtime_task_cannot_queue_before_link_source_is_ready(self) -> None:
        source = self.root / "CHD" / "Movie.mkv"
        target = self.root / "library" / "Movie.mkv"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"movie")
        self.add_item("realtime-failed", [{
            "source_relative_path": "Movie.mkv",
            "source": source,
            "new_rel": "Movie/Movie.mkv",
            "target": target,
        }])
        item = self.store.get_media_item("realtime-failed")
        item["details"] = {
            "import_control": {"realtime_hardlink_enabled": True},
            "realtime_hardlink": {
                "state": "failed",
                "error": "link failed",
            },
            "source_identity": {
                "kind": "qb_download",
                "source_path": str(source.parent),
            },
        }
        self.store.upsert_media_item(item)

        result = self.service.execute("queue_import", ["realtime-failed"])

        self.assertFalse(result["success"])
        self.assertIn("实时硬链接尚未成功", result["results"][0]["message"])
        self.assertEqual(
            self.store.get_media_item("realtime-failed")["state"],
            "identified",
        )

    def test_realtime_import_deletion_preserves_qb_original(self) -> None:
        qb_source = self.root / "CHD" / "Movie" / "Movie.mkv"
        realtime_source = self.root / "CHDlink" / "Movie" / "Movie.mkv"
        library_link = self.root / "library" / "Movie" / "Movie.mkv"
        qb_source.parent.mkdir(parents=True)
        realtime_source.parent.mkdir(parents=True)
        library_link.parent.mkdir(parents=True)
        qb_source.write_bytes(b"movie")
        os.link(qb_source, realtime_source)
        os.link(realtime_source, library_link)
        self.add_item(
            "realtime-imported",
            [{
                "source_relative_path": "Movie/Movie.mkv",
                "source": realtime_source,
                "new_rel": "Movie/Movie.mkv",
                "target": library_link,
                "details": {"hardlink_owned": True},
            }],
            state="imported",
            media_type="movie",
        )
        item = self.store.get_media_item("realtime-imported")
        item["source_path"] = str(realtime_source.parent)
        item["details"] = {
            "import_control": {"realtime_hardlink_enabled": True},
            "realtime_hardlink": {"state": "linked"},
            "source_identity": {
                "kind": "realtime_hardlink",
                "source_path": str(realtime_source.parent),
                "qb_source_path": str(qb_source.parent),
                "deletion_scope": "persisted_file_mappings_only",
            },
        }
        self.store.upsert_media_item(item)

        result = self.service.execute("delete_both", ["realtime-imported"])

        self.assertTrue(result["success"])
        self.assertTrue(qb_source.is_file())
        self.assertFalse(realtime_source.exists())
        self.assertFalse(library_link.exists())
        self.assertIsNone(self.store.get_media_item("realtime-imported"))

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

    def test_import_repairs_legacy_mapping_missing_dotted_source_directory(self) -> None:
        source_dir = self.root / "source" / "Show.2026.S01.Complete.1080p.WEB-DL"
        source_dir.mkdir(parents=True)
        source = source_dir / "Show.2026.S01E01.1080p.mkv"
        source.write_bytes(b"episode-one")
        target = self.root / "links" / "Show" / "E01.mkv"
        self.add_item("legacy-dotted-folder", [{
            "source_relative_path": source.name,
            "source": source,
            "target": target,
            "new_rel": "Show/Season 01/Show S01E01.mkv",
        }])
        item = self.store.get_media_item("legacy-dotted-folder")
        item["source_path"] = str(source_dir)
        self.store.upsert_media_item(item)
        mappings = self.store.list_file_mappings("qb-main", "legacy-dotted-folder")
        mappings[0]["current_source_path"] = str(source_dir.parent / source.name)
        self.store.replace_file_mappings("qb-main", "legacy-dotted-folder", mappings)

        result = self.service.execute("import", ["legacy-dotted-folder"])

        self.assertTrue(result["success"])
        self.assertTrue(target.is_file())
        self.assertTrue(os.path.samefile(source, target))
        repaired = self.store.list_file_mappings("qb-main", "legacy-dotted-folder")
        self.assertTrue(os.path.samefile(repaired[0]["current_source_path"], source))
        refreshed = self.store.get_media_item("legacy-dotted-folder")
        self.assertIn("source_paths_repaired_at", refreshed["details"])

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

    def test_delete_source_preserves_source_shared_by_another_card(self) -> None:
        source_dir = self.root / "source"
        source_dir.mkdir()
        source = source_dir / "Shared.mkv"
        source.write_bytes(b"shared")
        self.add_item("hash-owner-a", [{
            "source_relative_path": "Shared.mkv",
            "source": source,
            "target": self.root / "links" / "A.mkv",
            "new_rel": "A/Shared.mkv",
        }])
        self.add_item("hash-owner-b", [{
            "source_relative_path": "Shared.mkv",
            "source": source,
            "target": self.root / "links" / "B.mkv",
            "new_rel": "B/Shared.mkv",
        }])

        result = self.service.execute("delete_source", ["hash-owner-a"])

        self.assertTrue(result["success"])
        self.assertEqual(result["results"][0]["preserved"], 1)
        self.assertTrue(source.exists())
        self.assertIsNone(self.store.get_media_item("hash-owner-a"))
        self.assertIsNotNone(self.store.get_media_item("hash-owner-b"))

        final = self.service.execute("delete_source", ["hash-owner-b"])
        self.assertTrue(final["success"])
        self.assertFalse(source.exists())

    def test_delete_both_preserves_shared_source_but_removes_owned_hardlink(self) -> None:
        source_dir = self.root / "source"
        source_dir.mkdir()
        source = source_dir / "Shared.mkv"
        source.write_bytes(b"shared")
        hardlink = self.root / "links" / "Shared.mkv"
        hardlink.parent.mkdir()
        os.link(source, hardlink)
        self.add_item("hash-imported", [{
            "source_relative_path": "Shared.mkv",
            "source": source,
            "target": hardlink,
            "new_rel": "Shared/Shared.mkv",
            "details": {"hardlink_owned": True},
        }], state="imported")
        self.add_item("hash-other", [{
            "source_relative_path": "Shared.mkv",
            "source": source,
            "target": self.root / "links" / "Other.mkv",
            "new_rel": "Other/Shared.mkv",
        }])

        result = self.service.execute("delete_both", ["hash-imported"])

        self.assertTrue(result["success"])
        self.assertEqual(result["results"][0]["shared_sources"], 1)
        self.assertFalse(hardlink.exists())
        self.assertTrue(source.exists())
        self.assertIsNone(self.store.get_media_item("hash-imported"))
        self.assertIsNotNone(self.store.get_media_item("hash-other"))

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

    def test_delete_tv_hardlinks_cleans_empty_season_and_show_directories(self) -> None:
        source_root = self.root / "downloads"
        source_dir = source_root / "Show"
        source_dir.mkdir(parents=True)
        source = source_dir / "E01.mkv"
        source.write_bytes(b"episode")
        link_root = self.root / "links"
        category_root = link_root / "国产剧"
        target = category_root / "Show" / "Season 1" / "Show S01E01.mkv"
        target.parent.mkdir(parents=True)
        os.link(source, target)
        self.add_item("hash-tv-clean", [{
            "source_relative_path": "Show/E01.mkv",
            "source": source,
            "target": target,
            "new_rel": "Show/Season 1/Show S01E01.mkv",
            "details": {"hardlink_owned": True},
        }], state="imported")
        library_layout = layout.LibraryLayout.from_config("", [{
            "name": "test",
            "prefix": str(source_root),
            "link_roots": {"series": str(link_root)},
            "enabled": True,
        }])

        result = media_actions.MediaActionService(
            self.store, library_layout
        ).execute("delete_hardlinks", ["hash-tv-clean"])

        self.assertTrue(result["success"])
        self.assertEqual(result["results"][0]["directories_cleaned"], 2)
        self.assertFalse((category_root / "Show").exists())
        self.assertTrue(category_root.is_dir())

    def test_delete_movie_hardlink_cleans_only_media_directory(self) -> None:
        source_root = self.root / "downloads"
        source_dir = source_root / "Movie"
        source_dir.mkdir(parents=True)
        source = source_dir / "Movie.mkv"
        source.write_bytes(b"movie")
        link_root = self.root / "links"
        category_root = link_root / "外语电影"
        media_dir = category_root / "Movie (2026) {tmdbid=42}"
        target = media_dir / "Movie.mkv"
        target.parent.mkdir(parents=True)
        os.link(source, target)
        self.add_item("hash-movie-clean", [{
            "source_relative_path": "Movie/Movie.mkv",
            "source": source,
            "target": target,
            "new_rel": "Movie (2026) {tmdbid=42}/Movie.mkv",
            "details": {"hardlink_owned": True},
        }], state="imported", media_type="movie", category="外语电影")
        library_layout = layout.LibraryLayout.from_config("", [{
            "name": "test",
            "prefix": str(source_root),
            "link_roots": {"movie": str(link_root)},
            "enabled": True,
        }])

        result = media_actions.MediaActionService(
            self.store, library_layout
        ).execute("delete_hardlinks", ["hash-movie-clean"])

        self.assertTrue(result["success"])
        self.assertEqual(result["results"][0]["directories_cleaned"], 1)
        self.assertFalse(media_dir.exists())
        self.assertTrue(category_root.is_dir())

    def test_hardlink_cleanup_stops_when_directory_contains_another_file(self) -> None:
        source_root = self.root / "downloads"
        source_dir = source_root / "Show"
        source_dir.mkdir(parents=True)
        source = source_dir / "E01.mkv"
        source.write_bytes(b"episode")
        link_root = self.root / "links"
        category_root = link_root / "国产剧"
        season_dir = category_root / "Show" / "Season 1"
        target = season_dir / "Show S01E01.mkv"
        season_dir.mkdir(parents=True)
        os.link(source, target)
        (season_dir / ".keep").write_text("keep", encoding="utf-8")
        self.add_item("hash-tv-nonempty", [{
            "source_relative_path": "Show/E01.mkv",
            "source": source,
            "target": target,
            "new_rel": "Show/Season 1/Show S01E01.mkv",
            "details": {"hardlink_owned": True},
        }], state="imported")
        library_layout = layout.LibraryLayout.from_config("", [{
            "name": "test",
            "prefix": str(source_root),
            "link_roots": {"series": str(link_root)},
            "enabled": True,
        }])

        result = media_actions.MediaActionService(
            self.store, library_layout
        ).execute("delete_hardlinks", ["hash-tv-nonempty"])

        self.assertTrue(result["success"])
        self.assertEqual(result["results"][0]["directories_cleaned"], 0)
        self.assertTrue(season_dir.is_dir())
        self.assertTrue((season_dir / ".keep").is_file())

    def test_delete_source_cleans_one_empty_parent_below_source_root(self) -> None:
        source_root = self.root / "downloads"
        source_dir = source_root / "Movie"
        source_dir.mkdir(parents=True)
        source = source_dir / "Movie.mkv"
        source.write_bytes(b"movie")
        self.add_item("hash-source-clean", [{
            "source_relative_path": "Movie/Movie.mkv",
            "source": source,
            "target": self.root / "links" / "Movie.mkv",
            "new_rel": "Movie/Movie.mkv",
        }])
        library_layout = layout.LibraryLayout.from_config("", [{
            "name": "test",
            "prefix": str(source_root),
            "link_roots": {"series": str(self.root / "links")},
            "enabled": True,
        }])

        result = media_actions.MediaActionService(
            self.store, library_layout
        ).execute("delete_source", ["hash-source-clean"])

        self.assertTrue(result["success"])
        self.assertEqual(result["results"][0]["directories_cleaned"], 1)
        self.assertFalse(source_dir.exists())
        self.assertTrue(source_root.is_dir())

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
