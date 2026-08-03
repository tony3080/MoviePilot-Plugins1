"""Local inventory and read-only qB synchronization checks."""

import importlib.util
import json
import sqlite3
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
    @staticmethod
    def add_rss_task(
        store,
        *,
        task_id="rss-task",
        downloader="qb-main",
        category="movie",
        enabled=True,
    ):
        now = database.utc_now()
        connection = sqlite3.connect(store.path)
        try:
            connection.execute(
                """INSERT INTO rss_tasks(
                    id, name, enabled, position, config_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    task_id,
                    int(enabled),
                    0,
                    json.dumps({
                        "qb_downloader": downloader,
                        "qb_category": category,
                    }, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def update_rss_task_category(store, task_id, category):
        connection = sqlite3.connect(store.path)
        try:
            connection.execute(
                "UPDATE rss_tasks SET config_json = ?, updated_at = ? WHERE id = ?",
                (
                    json.dumps({
                        "qb_downloader": "qb-main",
                        "qb_category": category,
                    }, ensure_ascii=False),
                    database.utc_now(),
                    task_id,
                ),
            )
            connection.commit()
        finally:
            connection.close()

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
            self.add_rss_task(store)
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

    def test_sync_only_recognizes_rss_task_downloader_category_pairs(self) -> None:
        class Gateway:
            recognitions = []

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
                return [
                    {
                        "hash": "MANAGED",
                        "title": "Managed.Movie.2026",
                        "category": "movie",
                        "content_path": "/downloads/managed.mkv",
                    },
                    {
                        "hash": "OTHER",
                        "title": "Private.Movie.2026",
                        "category": "private",
                        "content_path": "/downloads/private.mkv",
                    },
                ]

            @staticmethod
            def torrent_dict(item):
                return dict(item)

            def recognize(self, title):
                self.recognitions.append(title)
                return None, None

            @staticmethod
            def meta_payload(_meta):
                return {}

        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "state.db")
            store.initialize()
            self.add_rss_task(store, category="movie", enabled=False)
            gateway = Gateway()
            store.create_background_task("filtered", qb_sync.QB_TASK_TYPE)

            result = qb_sync.QbSyncService(store=store, gateway=gateway).run(
                "filtered"
            )

            self.assertEqual(gateway.recognitions, ["Managed.Movie.2026"])
            self.assertEqual(result["scanned"], 1)
            self.assertEqual(result["filtered_out"], 1)
            self.assertIsNotNone(store.get_torrent_snapshot("qb-main", "managed"))
            self.assertIsNone(store.get_torrent_snapshot("qb-main", "other"))
            self.assertEqual(
                result["managed_scope"]["downloaders"],
                {"qb-main": ["movie"]},
            )

            self.update_rss_task_category(store, "rss-task", "new-category")

            class OfflineGateway(Gateway):
                @staticmethod
                def list_downloaders():
                    return [qb_sync.DownloaderView(
                        name="qb-main",
                        type="qbittorrent",
                        enabled=True,
                        default=True,
                        ready=False,
                    )]

            store.create_background_task("scope-changed", qb_sync.QB_TASK_TYPE)
            changed = qb_sync.QbSyncService(
                store=store,
                gateway=OfflineGateway(),
            ).run("scope-changed")
            self.assertEqual(changed["out_of_scope"], 1)
            self.assertEqual(store.list_torrents()["total"], 0)
            self.assertEqual(store.list_media()["total"], 0)

    def test_sync_never_falls_back_to_all_torrents_without_rss_scope(self) -> None:
        class Gateway:
            listed = False

            @staticmethod
            def list_downloaders():
                raise AssertionError("无 RSS 分类时不应读取下载器")

        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "state.db")
            store.initialize()
            store.create_background_task("empty-scope", qb_sync.QB_TASK_TYPE)

            result = qb_sync.QbSyncService(store=store, gateway=Gateway()).run(
                "empty-scope"
            )

            task = store.get_background_task("empty-scope")
            self.assertEqual(result["scanned"], 0)
            self.assertEqual(task["state"], "failed")
            self.assertIn("VT+", task["error_message"])


if __name__ == "__main__":
    unittest.main()
