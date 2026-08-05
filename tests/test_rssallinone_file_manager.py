"""Tests for local directory browsing and file-card deduplication."""

from __future__ import annotations

import importlib.util
import tempfile
import types
import unittest
from pathlib import Path


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


class LocalFileManagerTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
