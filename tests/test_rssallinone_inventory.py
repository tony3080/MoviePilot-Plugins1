"""Local inventory and read-only qB synchronization checks."""

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v2" / "rssallinone"
PACKAGE = "rssallinone_phase2_tests"


def load_package_module(name: str):
    package = sys.modules.get(PACKAGE)
    if package is None:
        package = types.ModuleType(PACKAGE)
        package.__path__ = [str(PLUGIN_DIR)]
        sys.modules[PACKAGE] = package
    module_name = f"{PACKAGE}.{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(
        module_name,
        PLUGIN_DIR / f"{name}.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


database = load_package_module("database")
inventory = load_package_module("inventory")
layout = load_package_module("layout")
qb_sync = load_package_module("qb_sync")


class LocalInventoryCheckerTest(unittest.TestCase):
    def test_parses_typed_and_shared_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roots, errors = inventory.parse_inventory_roots(
                f"movie => {root / 'Movies'}\n电视剧 => {root / 'TV'}\n{root / 'Shared'}"
            )
        self.assertEqual(errors, [])
        self.assertEqual([item.media_type for item in roots], ["movie", "tv", "*"])

    def test_unconfigured_and_unavailable_are_not_reported_missing(self) -> None:
        checker = inventory.LocalInventoryChecker.from_config("")
        state, _ = checker.check(
            "movie", [{"relative_path": "A/A.mkv", "size": 4}]
        )
        self.assertEqual(state, "unconfigured")

        with tempfile.TemporaryDirectory() as directory:
            missing_root = Path(directory) / "offline"
            checker = inventory.LocalInventoryChecker.from_config(
                f"movie => {missing_root}"
            )
            state, details = checker.check(
                "movie", [{"relative_path": "A/A.mkv", "size": 4}]
            )
        self.assertEqual(state, "unavailable")
        self.assertEqual(len(details["unavailable_roots"]), 1)

    def test_checks_exact_relative_paths_and_sizes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "Show (2026)" / "Season 00" / "Show S00E01.mkv"
            second = root / "Show (2026)" / "Season 00" / "Show S00E02.mkv"
            first.parent.mkdir(parents=True)
            first.write_bytes(b"1234")
            checker = inventory.LocalInventoryChecker.from_config(f"tv => {root}")
            expected = [
                {"relative_path": "Show (2026)/Season 00/Show S00E01.mkv", "size": 4},
                {"relative_path": "Show (2026)/Season 00/Show S00E02.mkv", "size": 4},
            ]

            state, details = checker.check("tv", expected)
            self.assertEqual(state, "partial")
            self.assertEqual(details["exists"], 1)
            self.assertEqual(details["missing"], 1)

            second.write_bytes(b"bad")
            state, details = checker.check("tv", expected)
            self.assertEqual(state, "partial")
            self.assertEqual(details["size_mismatch"], 1)

            second.write_bytes(b"1234")
            state, details = checker.check("tv", expected)
            self.assertEqual(state, "exists")
            self.assertEqual(details["exists"], 2)

    def test_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checker = inventory.LocalInventoryChecker.from_config(directory)
            state, details = checker.check(
                "movie", [{"relative_path": "../outside.mkv", "size": 1}]
            )
        self.assertEqual(state, "unknown")
        self.assertTrue(details["plan_errors"])


class ReadOnlyQbSyncTest(unittest.TestCase):
    def test_sync_reuses_recognition_but_rechecks_local_inventory(self) -> None:
        class Meta:
            begin_season = None

            @staticmethod
            def to_dict():
                return {"title": "Example.Movie.2026"}

        class Media:
            title = "Example Movie"
            year = "2026"
            tmdb_id = 42
            season = None
            category = "华语电影"

        class Gateway:
            def __init__(self):
                self.media = Media()
                self.recognitions = 0
                self.plans = 0

            @staticmethod
            def list_downloaders():
                return [qb_sync.DownloaderView(
                    name="qb-main",
                    type="qbittorrent",
                    enabled=True,
                    default=True,
                    ready=True,
                )]

            @staticmethod
            def list_torrents(_downloader):
                return [{
                    "hash": "ABC123",
                    "title": "Example.Movie.2026.1080p",
                    "state": "seeding",
                    "category": "movie",
                    "content_path": "/downloads/Example.Movie.2026.mkv",
                    "progress": 100,
                    "size": 4,
                }]

            @staticmethod
            def torrent_dict(item):
                return dict(item)

            def recognize(self, _title):
                self.recognitions += 1
                return Meta(), self.media

            def restore_media(self, _payload):
                return self.media

            @staticmethod
            def restore_meta(_title, _payload):
                return Meta()

            @staticmethod
            def list_torrent_files(_downloader, _info_hash):
                return [{"name": "Example.Movie.2026.mkv", "size": 4}]

            def plan_inventory_files(self, _media, _files):
                self.plans += 1
                return {
                    "method": "moviepilot_naming",
                    "media_type": "movie",
                    "expected_files": [{
                        "source_name": "Example.Movie.2026.mkv",
                        "relative_path": "Example Movie (2026)/Example Movie (2026).mkv",
                        "size": 4,
                    }],
                    "ignored_files": [],
                    "target_name": "Example Movie (2026)/Example Movie (2026).mkv",
                }

            @staticmethod
            def media_payload(_media):
                return {"title": "Example Movie", "tmdb_id": 42}

            @staticmethod
            def meta_payload(meta):
                return meta.to_dict()

            @staticmethod
            def poster(_media):
                return ""

            @staticmethod
            def media_type(_media):
                return "movie"

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            store = database.SQLiteStore(directory / "state.db")
            store.initialize()
            library_root = directory / "library"
            expected = (
                library_root
                / "华语电影"
                / "Example Movie (2026)"
                / "Example Movie (2026).mkv"
            )
            expected.parent.mkdir(parents=True)
            expected.write_bytes(b"1234")
            gateway = Gateway()
            service = qb_sync.QbSyncService(
                store=store,
                gateway=gateway,
                inventory_checker=inventory.LocalInventoryChecker([]),
                library_layout=layout.LibraryLayout.from_config(
                    str(library_root),
                    [{
                        "name": "downloads",
                        "prefix": "/downloads",
                        "link_roots": {"movie": str(directory / "staging")},
                        "enabled": True,
                    }],
                    {"movie": ["华语电影"]},
                ),
            )

            store.create_background_task("first", qb_sync.QB_TASK_TYPE)
            service.run("first")
            first = store.get_torrent_snapshot("qb-main", "abc123")
            self.assertEqual(first["inventory_state"], "exists")
            self.assertEqual(first["recognition_state"], "identified")
            self.assertEqual(first["details"]["inventory"]["scope"], "mp_library_path")
            self.assertEqual(
                first["details"]["path_plan"]["inventory_base"],
                str(library_root / "华语电影").replace("\\", "/"),
            )

            expected.unlink()
            store.create_background_task("second", qb_sync.QB_TASK_TYPE)
            service.run("second")
            second = store.get_torrent_snapshot("qb-main", "abc123")
            self.assertEqual(second["inventory_state"], "missing")
            self.assertEqual(gateway.recognitions, 1)
            self.assertEqual(gateway.plans, 1)


if __name__ == "__main__":
    unittest.main()
