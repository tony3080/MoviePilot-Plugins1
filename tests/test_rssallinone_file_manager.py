"""Tests for local directory browsing and file-card deduplication."""

from __future__ import annotations

import importlib.util
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v2" / "rssallinone"
PACKAGE = "rssallinone_file_manager_tests"


def load_module(name: str):
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(PLUGIN_DIR)]
    import sys

    sys.modules.setdefault(PACKAGE, package)
    fullname = f"{PACKAGE}.{name}"
    spec = importlib.util.spec_from_file_location(fullname, PLUGIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module
    assert spec.loader
    spec.loader.exec_module(module)
    return module


database = load_module("database")
file_manager = load_module("file_manager")
rss_execute = load_module("rss_execute")
rss_site_labels = load_module("rss_site_labels")


class LocalFileManagerTest(unittest.TestCase):
    @staticmethod
    def _manual_label_gateway(category):
        class Media:
            title = "Demo"
            tmdb_id = None
            season = None

            def __init__(self):
                self.category = category

        class Gateway:
            @staticmethod
            def recognize(_title):
                return types.SimpleNamespace(begin_season=None), Media()

            @staticmethod
            def recognize_manual(_title, _media_type, _tmdb_id, _season):
                return types.SimpleNamespace(begin_season=None), Media()

            @staticmethod
            def media_type(_media):
                return "tv" if category == "国产剧" else "movie"

            @staticmethod
            def media_payload(media):
                return {"title": media.title, "category": media.category}

            @staticmethod
            def meta_payload(_meta):
                return {}

        return Gateway()

    def _recognize_with_manual_labels(self, root, category):
        class Labels:
            def __init__(self, *_args, **_kwargs):
                pass

            @staticmethod
            def detect(**_kwargs):
                return {
                    "status": "matched",
                    "mandarin": True,
                    "effects": True,
                    "request_url_masked": "https://example.invalid/details.php?id=1",
                }

        project = root / "Demo.2026"
        project.mkdir()
        (project / "Demo.2026.mkv").write_bytes(b"movie")
        store = database.SQLiteStore(root / "state.db")
        store.initialize()
        service = file_manager.LocalFileManagerService(
            store, gateway=self._manual_label_gateway(category)
        )
        with mock.patch.object(
            rss_execute.MoviePilotRssGateway,
            "site_access",
            return_value=object(),
        ), mock.patch.object(rss_site_labels, "SiteLabelService", Labels):
            return service.recognize_entry(
                project,
                site_id="site-1",
                recognize_cn=True,
                recognize_fx=True,
            )

    def test_manual_local_mandarin_is_skipped_for_disallowed_category(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            result = self._recognize_with_manual_labels(root, "国产剧")

            item = result["item"]
            source = Path(item["source_path"])
            self.assertIn("特效", source.name)
            self.assertNotIn("国配", source.name)
            self.assertNotIn("国配", next(source.glob("*.mkv")).name)
            labels = item["details"]["site_labels"]
            self.assertFalse(labels["mandarin_allowed"])
            self.assertTrue(labels["mandarin_skipped"])

    def test_manual_local_mandarin_is_applied_for_allowed_category(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            result = self._recognize_with_manual_labels(root, "外语电影")

            item = result["item"]
            source = Path(item["source_path"])
            self.assertIn("国配", source.name)
            self.assertIn("国配", next(source.glob("*.mkv")).name)
            labels = item["details"]["site_labels"]
            self.assertTrue(labels["mandarin_allowed"])
            self.assertTrue(labels["mandarin_applied"])

    def test_manual_local_unclassified_mandarin_is_kept_pending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            result = self._recognize_with_manual_labels(root, "")

            item = result["item"]
            source = Path(item["source_path"])
            self.assertNotIn("国配", source.name)
            self.assertNotIn("国配", next(source.glob("*.mkv")).name)
            labels = item["details"]["site_labels"]
            self.assertTrue(labels["mandarin_pending"])
            self.assertFalse(labels["mandarin_applied"])

    def test_manual_local_pending_mandarin_applies_after_manual_recognition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initial = self._recognize_with_manual_labels(root, "")
            item = initial["item"]
            original_id = item["id"]
            store = database.SQLiteStore(root / "state.db")
            store.initialize()
            service = file_manager.LocalFileManagerService(
                store, gateway=self._manual_label_gateway("")
            )

            refreshed = service.recognize_entry(
                item["source_path"],
                manual_override={
                    "media_type": "movie",
                    "tmdb_id": 42,
                    "category": "外语电影",
                },
                refresh_media_id=original_id,
            )

            refreshed_item = refreshed["item"]
            self.assertEqual(refreshed_item["id"], original_id)
            self.assertIn("国配", Path(refreshed_item["source_path"]).name)
            labels = refreshed_item["details"]["site_labels"]
            self.assertFalse(labels["mandarin_pending"])
            self.assertTrue(labels["mandarin_applied"])

    def test_same_filename_in_different_paths_has_distinct_source_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "Disney" / "Movie.mkv"
            second = root / "Netflix" / "Movie.mkv"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_bytes(b"disney")
            second.write_bytes(b"netflix")

            first_id, _ = file_manager._source_identity(first)
            second_id, _ = file_manager._source_identity(second)

            self.assertNotEqual(first_id, second_id)

    def test_browse_returns_directories_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Beta").mkdir()
            (root / "alpha").mkdir()
            (root / "movie.mkv").write_bytes(b"video")

            result = file_manager.LocalFileManagerService.browse(root)

            self.assertEqual(
                [item["name"] for item in result["items"]],
                ["alpha", "Beta", "movie.mkv"],
            )
            self.assertEqual(
                [item["type"] for item in result["items"]],
                ["dir", "dir", "file"],
            )
            self.assertEqual(result["total"], 3)
            self.assertEqual(Path(result["path"]), root.resolve())

    def test_virtual_root_only_lists_configured_source_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mp_root = root / "MP"
            ssd_root = root / "SSD"
            mp_root.mkdir()
            ssd_root.mkdir()

            result = file_manager.LocalFileManagerService.browse(
                "/", [ssd_root, mp_root, root / "missing"]
            )

            self.assertEqual([item["name"] for item in result["items"]], ["MP", "SSD"])
            self.assertEqual([item["type"] for item in result["items"]], ["dir", "dir"])
            self.assertEqual(result["path"], "/")

    def test_configured_root_cannot_browse_outside_source_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowed = root / "allowed"
            outside = root / "outside"
            allowed.mkdir()
            outside.mkdir()

            with self.assertRaises(file_manager.FileManagerError):
                file_manager.LocalFileManagerService.browse(outside, [allowed])

    def test_existing_source_folder_is_not_recognized_twice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media_dir = root / "Existing Movie"
            media_dir.mkdir()
            (media_dir / "Existing.Movie.2026.mkv").write_bytes(b"video")
            store = database.SQLiteStore(root / "state.db")
            store.initialize()
            store.upsert_media_item({
                "id": "existing-card",
                "state": "identified",
                "source_name": media_dir.name,
                "source_path": str(media_dir.resolve()),
                "details": {},
            })

            result = file_manager.LocalFileManagerService(store).recognize_folder(media_dir)

            self.assertTrue(result["success"])
            self.assertTrue(result["duplicate"])
            self.assertEqual(result["media_id"], "existing-card")
            self.assertEqual(store.list_media()["total"], 1)

    def test_existing_file_mapping_prevents_second_card(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media_dir = root / "Mapped Show"
            media_dir.mkdir()
            source = media_dir / "Mapped.Show.S01E01.mkv"
            source.write_bytes(b"video")
            store = database.SQLiteStore(root / "state.db")
            store.initialize()
            store.upsert_media_item({
                "id": "mapped-card",
                "state": "identified",
                "source_name": "old source",
                "source_path": str(root / "old"),
                "downloader_id": "QB",
                "info_hash": "abc",
                "details": {},
            })
            store.replace_file_mappings("QB", "abc", [{
                "media_id": "mapped-card",
                "file_index": 0,
                "current_source_path": str(source.resolve()),
            }])

            result = file_manager.LocalFileManagerService(store).recognize_folder(media_dir)

            self.assertTrue(result["duplicate"])
            self.assertEqual(result["media_id"], "mapped-card")
            self.assertEqual(store.list_media()["total"], 1)

    def test_single_file_uses_the_same_duplicate_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Single.Movie.2026.mkv"
            source.write_bytes(b"video")
            store = database.SQLiteStore(root / "state.db")
            store.initialize()
            store.upsert_media_item({
                "id": "single-card",
                "state": "identified",
                "source_name": source.name,
                "source_path": str(source.resolve()),
                "details": {},
            })

            result = file_manager.LocalFileManagerService(store).recognize_entry(source)

            self.assertTrue(result["duplicate"])
            self.assertEqual(result["media_id"], "single-card")

    def test_batch_recognition_processes_direct_children_individually(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "Series Folder"
            child.mkdir()
            (child / "Series.S01E01.mkv").write_bytes(b"episode")
            movie = root / "Movie.2026.mkv"
            movie.write_bytes(b"movie")
            (root / "poster.jpg").write_bytes(b"image")
            store = database.SQLiteStore(root / "state.db")
            store.initialize()

            class RecordingService(file_manager.LocalFileManagerService):
                def __init__(self):
                    super().__init__(store)
                    self.paths = []

                def recognize_entry(self, path, **_kwargs):
                    self.paths.append(Path(path).name)
                    return {"success": True, "duplicate": False}

            service = RecordingService()
            result = service.recognize_current_directory(root)

            self.assertEqual(service.paths, ["Series Folder", "Movie.2026.mkv"])
            self.assertEqual(result["total"], 2)
            self.assertEqual(result["succeeded"], 2)
            self.assertEqual(result["failed"], 0)

    def test_batch_recognition_prefers_folder_name_for_site_search(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "ManualRoot"
            root.mkdir()
            folder = root / "Folder.Release.2026"
            folder.mkdir()
            (folder / "movie.mkv").write_bytes(b"episode")
            file_item = root / "File.Release.2026.mkv"
            file_item.write_bytes(b"movie")
            store = database.SQLiteStore(root / "state.db")
            store.initialize()

            class RecordingService(file_manager.LocalFileManagerService):
                def __init__(self):
                    super().__init__(store)
                    self.search_titles = []

                def recognize_entry(self, path, **kwargs):
                    self.search_titles.append(kwargs.get("site_search_title"))
                    return {"success": True, "duplicate": False}

            service = RecordingService()
            service.recognize_current_directory(root)

            self.assertEqual(
                service.search_titles,
                ["Folder.Release.2026", "File.Release.2026.mkv"],
            )

    def test_local_rename_updates_media_files_and_project_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "Movie.2026.UBits"
            project.mkdir()
            media = project / "Movie.2026.UBits.mkv"
            media.write_bytes(b"movie")

            renamed_files = file_manager.LocalFileManagerService._rename_local_files(
                [media], "/ubits/i => REMUX-U版"
            )
            renamed_project = file_manager.LocalFileManagerService._rename_local_directory(
                project, "/ubits/i => REMUX-U版"
            )
            final_media = renamed_project / renamed_files[0].relative_to(project.resolve())

            self.assertEqual(renamed_project.name, "Movie.2026.REMUX-U版")
            self.assertEqual(renamed_files[0].name, "Movie.2026.REMUX-U版.mkv")
            self.assertTrue(final_media.exists())

            fx_file = renamed_project / "Movie.2026.REMUX-U版.mkv"
            fx_renamed = file_manager.LocalFileManagerService._rename_local_files(
                [fx_file], "/ubits/i => REMUX-U版", add_fx=True
            )
            self.assertEqual(fx_renamed[0].name, "Movie.2026-特效-REMUX-U版.mkv")


if __name__ == "__main__":
    unittest.main()
