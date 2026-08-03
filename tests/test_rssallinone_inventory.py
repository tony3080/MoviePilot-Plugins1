"""Local inventory and read-only qB synchronization checks."""

import importlib.util
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


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
            "movie", [{"relative_path": "A/A.mkv", "size": 4}], tmdb_id=1
        )
        self.assertEqual(state, "unconfigured")

        with tempfile.TemporaryDirectory() as directory:
            missing_root = Path(directory) / "offline"
            checker = inventory.LocalInventoryChecker.from_config(
                f"movie => {missing_root}"
            )
            state, details = checker.check(
                "movie", [{"relative_path": "A/A.mkv", "size": 4}], tmdb_id=1
            )
        self.assertEqual(state, "unavailable")
        self.assertEqual(details["folder_status"], "unavailable")

    def test_locks_tmdb_folder_and_only_counts_strm_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media_root = root / "剧名 (2026) {tmdbid=42}"
            first = media_root / "Season 00" / "剧名 S00E01 2160p.strm"
            second = media_root / "Season 00" / "剧名 S00E02 2160p.strm"
            first.parent.mkdir(parents=True)
            first.write_text("cloud://episode-1", encoding="utf-8")
            checker = inventory.LocalInventoryChecker.from_config(f"tv => {root}")
            expected = [
                {
                    "source_name": "Show.S00E01.2160p.mkv",
                    "relative_path": (
                        "剧名 (2026) {tmdbid=42}/Season 00/剧名 S00E01 2160p.mkv"
                    ),
                    "size": 40_000,
                },
                {
                    "source_name": "Show.S00E02.2160p.mkv",
                    "relative_path": (
                        "剧名 (2026) {tmdbid=42}/Season 00/剧名 S00E02 2160p.mkv"
                    ),
                    "size": 50_000,
                },
            ]

            state, details = checker.check("tv", expected, tmdb_id=42)
            self.assertEqual(state, "partial")
            self.assertEqual(details["folder"]["match_method"], "tmdb_id")
            self.assertEqual(details["folder"]["title"], "剧名")
            self.assertEqual(details["exists_count"], 1)
            self.assertEqual(details["missing_count"], 1)
            self.assertTrue(details["files"][0]["inventory_exists"])

            second.with_suffix(".mkv").write_bytes(b"not-an-inventory-file")
            state, details = checker.check("tv", expected, tmdb_id=42)
            self.assertEqual(state, "partial")
            self.assertEqual(details["exists_count"], 1)

            second.write_text("x", encoding="utf-8")
            state, details = checker.check("tv", expected, tmdb_id=42)
            self.assertEqual(state, "exists")
            self.assertEqual(details["exists_count"], 2)

    def test_matches_inventory_title_features_after_mp_naming(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media_root = root / "库存中文标题 (2026) [tmdbid=42]"
            inventory_file = (
                media_root / "Season 01" / "库存中文标题.S01E03.2160p.WEB-DL.strm"
            )
            inventory_file.parent.mkdir(parents=True)
            inventory_file.write_text("cloud://episode-3", encoding="utf-8")
            checker = inventory.LocalInventoryChecker.from_config(f"tv => {root}")

            state, details = checker.check(
                "tv",
                [{
                    "source_name": "Source.S01E03.mkv",
                    "relative_path": (
                        "库存中文标题 (2026) [tmdbid=42]/Season 01/"
                        "库存中文标题 - S01E03 - 2160p WEB-DL.mkv"
                    ),
                    "size": 999999,
                }],
                tmdb_id=42,
            )

            self.assertEqual(state, "exists")
            self.assertEqual(
                details["files"][0]["match_method"], "filename_features"
            )
            self.assertEqual(details["files"][0]["new_rel"].split("/")[-1],
                             "库存中文标题 - S01E03 - 2160p WEB-DL.mkv")

    def test_duplicate_tmdb_directories_are_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "A {tmdbid=42}").mkdir()
            (root / "B [tmdbid=42]").mkdir()
            checker = inventory.LocalInventoryChecker.from_config(f"movie => {root}")

            state, details = checker.check(
                "movie", [{"relative_path": "A/A.mkv"}], tmdb_id=42
            )

            self.assertEqual(state, "ambiguous")
            self.assertEqual(len(details["folder"]["candidates"]), 2)

    def test_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checker = inventory.LocalInventoryChecker.from_config(directory)
            state, details = checker.check(
                "movie",
                [{"relative_path": "../outside.mkv", "size": 1}],
                tmdb_id=1,
            )
        self.assertEqual(state, "unknown")
        self.assertTrue(details["plan_errors"])


class MoviePilotNamingPlanTest(unittest.TestCase):
    def test_preserves_full_mp_name_and_only_derives_strm_suffix(self) -> None:
        calls = []

        class FakeMetaInfoPath:
            def __init__(self, path):
                self.path = path
                self.begin_season = 1
                self.begin_episode = 3
                self.year = None

        class FakeMetaInfo:
            def __init__(self, title):
                self.title = title
                self.begin_season = 1
                self.begin_episode = 3
                self.year = None

        class FakeFileManagerModule:
            @staticmethod
            def recommend_name(meta, media):
                calls.append((meta.path.as_posix(), media.title))
                return (
                    f"{media.title} (2023) {{tmdbid=42}}/Season 01/"
                    f"{media.title} - S01E03 - 2160p NF WEB-DL "
                    "DDP5.1 DV HEVC-NTb.mkv"
                )

        app_module = types.ModuleType("app")
        app_module.__path__ = []
        core_module = types.ModuleType("app.core")
        core_module.__path__ = []
        config_module = types.ModuleType("app.core.config")
        config_module.settings = types.SimpleNamespace(RMT_MEDIAEXT=[".mkv"])
        metainfo_module = types.ModuleType("app.core.metainfo")
        metainfo_module.MetaInfo = FakeMetaInfo
        metainfo_module.MetaInfoPath = FakeMetaInfoPath
        core_module.metainfo = metainfo_module
        modules_module = types.ModuleType("app.modules")
        modules_module.__path__ = []
        filemanager_module = types.ModuleType("app.modules.filemanager")
        filemanager_module.FileManagerModule = FakeFileManagerModule
        fake_modules = {
            "app": app_module,
            "app.core": core_module,
            "app.core.config": config_module,
            "app.core.metainfo": metainfo_module,
            "app.modules": modules_module,
            "app.modules.filemanager": filemanager_module,
        }
        media = types.SimpleNamespace(
            type="电视剧",
            title="MoviePilot识别标题",
            year=2023,
            season=1,
        )

        with mock.patch.dict(sys.modules, fake_modules):
            result = qb_sync.MoviePilotQbGateway.plan_inventory_files(
                media,
                [{
                    "name": (
                        "发布目录/The.Last.of.Us.S01E03.2160p.NF.WEB-DL."
                        "DDP5.1.DV.H.265-NTb.mkv"
                    ),
                    "size": 1000,
                }],
                title_override="库存中文标题",
            )

        expected = result["expected_files"][0]
        self.assertEqual(
            calls,
            [(
                "发布目录/The.Last.of.Us.S01E03.2160p.NF.WEB-DL."
                "DDP5.1.DV.H.265-NTb.mkv",
                "库存中文标题",
            )],
        )
        self.assertEqual(media.title, "MoviePilot识别标题")
        self.assertTrue(expected["relative_path"].endswith("HEVC-NTb.mkv"))
        self.assertTrue(
            expected["inventory_relative_path"].endswith("HEVC-NTb.strm")
        )
        self.assertEqual(expected["new_rel"], expected["relative_path"])


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

            def plan_inventory_files(self, _media, _files, title_override=""):
                self.plans += 1
                naming_title = title_override or "MoviePilot English Title"
                media_directory = f"{naming_title} (2026) {{tmdbid=42}}"
                return {
                    "method": "moviepilot_naming",
                    "media_type": "movie",
                    "title_override": title_override,
                    "total_files": 1,
                    "expected_files": [{
                        "source_name": "Example.Movie.2026.mkv",
                        "relative_path": f"{media_directory}/{naming_title}.mkv",
                        "inventory_relative_path": (
                            f"{media_directory}/{naming_title}.strm"
                        ),
                        "size": 4,
                    }],
                    "ignored_files": [],
                    "plan_errors": [],
                    "expected_directory": media_directory,
                    "target_name": f"{media_directory}/{naming_title}.mkv",
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
                / "库存中文标题 (2026) {tmdbid=42}"
                / "库存中文标题.strm"
            )
            expected.parent.mkdir(parents=True)
            expected.write_text("cloud://movie", encoding="utf-8")
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
            self.assertEqual(gateway.plans, 4)

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
