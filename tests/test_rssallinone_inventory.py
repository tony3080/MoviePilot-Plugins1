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

    def test_tmdb_folder_matches_changed_title_by_exact_episode_features(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media_root = root / "百花杀 (2026) - {tmdbid=286506}"
            inventory_file = (
                media_root
                / "Season 1"
                / "百花杀 - S01E01 - 第 1 集 - 1080p.strm"
            )
            inventory_file.parent.mkdir(parents=True)
            inventory_file.write_text("cloud://episode-1", encoding="utf-8")
            checker = inventory.LocalInventoryChecker.from_config(f"tv => {root}")

            state, details = checker.check(
                "tv",
                [{
                    "source_name": "Dong.Feng.Xin.S01E01.mkv",
                    "relative_path": (
                        "东风信 (2026) - {tmdbid=286506}/Season 01/"
                        "东风信 - S01E01 - 第 1 集 - 1080p.mkv"
                    ),
                }],
                tmdb_id=286506,
                expected_directory="东风信 (2026) - {tmdbid=286506}",
                media_title="百花杀",
                alternate_titles=["东风信"],
            )

            self.assertEqual(state, "exists")
            self.assertEqual(details["folder"]["match_method"], "tmdb_id")
            self.assertEqual(details["folder"]["title"], "百花杀")
            self.assertEqual(
                details["files"][0]["match_method"], "filename_features"
            )

    def test_feature_match_rejects_extra_version_and_other_season(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media_root = root / "百花杀 (2026) - {tmdbid=286506}"
            extra_version = (
                media_root
                / "Season 1"
                / "百花杀 - S01E01 - 第 1 集 - 1080p - 纯净版.strm"
            )
            other_season = (
                media_root
                / "Season 2"
                / "百花杀 - S01E01 - 第 1 集 - 1080p.strm"
            )
            extra_version.parent.mkdir(parents=True)
            other_season.parent.mkdir(parents=True)
            extra_version.write_text("cloud://extra", encoding="utf-8")
            other_season.write_text("cloud://wrong-season", encoding="utf-8")
            checker = inventory.LocalInventoryChecker.from_config(f"tv => {root}")

            state, details = checker.check(
                "tv",
                [{
                    "relative_path": (
                        "东风信 (2026) - {tmdbid=286506}/Season 01/"
                        "东风信 - S01E01 - 第 1 集 - 1080p.mkv"
                    ),
                }],
                tmdb_id=286506,
                media_title="百花杀",
                alternate_titles=["东风信"],
            )

            self.assertEqual(state, "missing")
            self.assertEqual(details["exists_count"], 0)

    def test_feature_key_only_removes_a_leading_complete_title(self) -> None:
        self.assertEqual(
            inventory._feature_key("[百花杀].S01E01.1080p", "百花杀"),
            "s01e01 1080p",
        )
        self.assertEqual(
            inventory._feature_key("版本.百花杀.S01E01.1080p", "百花杀"),
            "版本 百花杀 s01e01 1080p",
        )

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

    def test_expected_directory_disambiguates_duplicate_tmdb_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected_name = "Show (2026) - {tmdbid=42}"
            media_root = root / expected_name
            stale_root = root / "Show (2026) - (2026) - {tmdbid=42}"
            inventory_file = media_root / "Season 1" / "Show - S01E01 - 1080p.strm"
            inventory_file.parent.mkdir(parents=True)
            inventory_file.write_text("cloud://episode-1", encoding="utf-8")
            stale_root.mkdir()
            checker = inventory.LocalInventoryChecker.from_config(f"tv => {root}")

            state, details = checker.check(
                "tv",
                [
                    {
                        "relative_path": (
                            f"{expected_name}/Season 1/Show - S01E01 - 1080p.mkv"
                        )
                    },
                    {
                        "relative_path": (
                            f"{expected_name}/Season 1/Show - S01E02 - 1080p.mkv"
                        )
                    },
                ],
                tmdb_id=42,
                expected_directory=expected_name,
            )

            self.assertEqual(state, "partial")
            self.assertEqual(details["folder_status"], "exists")
            self.assertEqual(
                details["folder"]["match_method"],
                "tmdb_id_expected_directory",
            )
            self.assertEqual(details["exists_count"], 1)
            self.assertEqual(details["missing_count"], 1)
            self.assertEqual(len(details["files"]), 2)

    def test_inventory_title_removes_year_and_template_separators(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media_root = root / "聪明镇 (2026) - {tmdbid=300259}"
            media_root.mkdir()
            checker = inventory.LocalInventoryChecker.from_config(f"tv => {root}")

            folder = checker.locate_root(root, 300259)

            self.assertEqual(folder.status, "exists")
            self.assertEqual(folder.title, "聪明镇")

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

    def test_inherits_southpaw_resource_metadata_from_torrent_title(self) -> None:
        captured = []

        class FakeMetaInfoPath:
            def __init__(self, path):
                self.path = path
                self.begin_season = None
                self.begin_episode = None
                self.year = None
                self.resource_type = None
                self.resource_effect = None
                self.resource_pix = None
                self.resource_team = None
                self.customization = None
                self.video_encode = None
                self.audio_encode = None
                self.apply_words = []

        class FakeMetaInfo(FakeMetaInfoPath):
            def __init__(self, title):
                super().__init__(Path(title))
                self.title = title

        class FakeFileManagerModule:
            @staticmethod
            def recommend_name(meta, media):
                captured.append({
                    "resource_type": meta.resource_type,
                    "resource_effect": meta.resource_effect,
                    "resource_pix": meta.resource_pix,
                    "resource_team": meta.resource_team,
                    "customization": meta.customization,
                    "video_encode": meta.video_encode,
                    "audio_encode": meta.audio_encode,
                    "apply_words": list(meta.apply_words),
                })
                return (
                    f"{media.title} (2015) [tmdbid=307081]/"
                    f"{media.title} (2015) - {meta.resource_type} - "
                    f"{meta.resource_effect} - {meta.resource_pix} - "
                    f"{meta.audio_encode} - {meta.customization} - "
                    f"{meta.resource_team}.mkv"
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
            type="movie",
            title="铁拳",
            year=2015,
        )
        torrent_meta = types.SimpleNamespace(
            resource_type="BluRay REMUX",
            resource_effect="杜比视界 HDR",
            resource_pix="2160p",
            resource_team="CHD",
            customization="V2@REMUX@杜比视界@HDR",
            video_encode="HEVC",
            audio_encode="Atmos TrueHD 7.1",
            apply_words=[
                r"\b([Dd][Vv]|[Dd][Oo][Vv][Ii])\b => 杜比视界",
                r"\b([Hh][Dd][Rr]10?)\b => HDR",
                r"\b([Rr][Ee][Mm][Uu][Xx])\b => REMUX",
                r"\b([Vv]2)\b => V2",
            ],
        )

        with mock.patch.dict(sys.modules, fake_modules):
            result = qb_sync.MoviePilotQbGateway.plan_inventory_files(
                media,
                [{"name": "Southpaw.mkv", "size": 1000}],
                torrent_meta=torrent_meta,
            )

        self.assertEqual(captured, [{
            "resource_type": "BluRay REMUX",
            "resource_effect": "杜比视界 HDR",
            "resource_pix": "2160p",
            "resource_team": "CHD",
            "customization": "V2@REMUX@杜比视界@HDR",
            "video_encode": "HEVC",
            "audio_encode": "Atmos TrueHD 7.1",
            "apply_words": torrent_meta.apply_words,
        }])
        expected = result["expected_files"][0]
        self.assertIn("BluRay REMUX", expected["relative_path"])
        self.assertIn("杜比视界 HDR", expected["relative_path"])
        self.assertIn("Atmos TrueHD 7.1", expected["relative_path"])
        self.assertIn(
            "V2@REMUX@杜比视界@HDR", expected["relative_path"]
        )
        self.assertEqual(
            expected["recognition"]["resource_tokens"],
            [
                "BluRay REMUX",
                "杜比视界 HDR",
                "2160p",
                "CHD",
                "V2@REMUX@杜比视界@HDR",
                "HEVC",
                "Atmos TrueHD 7.1",
            ],
        )
        self.assertEqual(
            expected["recognition"]["customization"],
            "V2@REMUX@杜比视界@HDR",
        )
        self.assertEqual(
            expected["recognition"]["apply_words"],
            torrent_meta.apply_words,
        )
        self.assertIn(
            "resource_effect", expected["recognition"]["inherited_fields"]
        )

    def test_refresh_customization_uses_live_moviepilot_matchers(self) -> None:
        prepared_titles = []

        class FakeWordsMatcher:
            @staticmethod
            def prepare(title):
                return (
                    title.replace("DoVi", "杜比视界").replace("HDR10", "HDR"),
                    ["DoVi => 杜比视界", "HDR10 => HDR"],
                )

        class FakeCustomizationMatcher:
            @staticmethod
            def match(title):
                prepared_titles.append(title)
                return "V2@REMUX@杜比视界@HDR"

        app_module = types.ModuleType("app")
        app_module.__path__ = []
        core_module = types.ModuleType("app.core")
        core_module.__path__ = []
        meta_module = types.ModuleType("app.core.meta")
        meta_module.__path__ = []
        words_module = types.ModuleType("app.core.meta.words")
        words_module.WordsMatcher = FakeWordsMatcher
        customization_module = types.ModuleType("app.core.meta.customization")
        customization_module.CustomizationMatcher = FakeCustomizationMatcher
        fake_modules = {
            "app": app_module,
            "app.core": core_module,
            "app.core.meta": meta_module,
            "app.core.meta.words": words_module,
            "app.core.meta.customization": customization_module,
        }
        meta = types.SimpleNamespace(customization="C版@REMUX")
        title = (
            "Southpaw 2015 USA V2 BluRay REMUX UHD DoVi HDR10 "
            "2160p Atmos TrueHD7.1-CHD.mkv"
        )

        with mock.patch.dict(sys.modules, fake_modules):
            customization = qb_sync.MoviePilotQbGateway.refresh_customization(
                meta, title
            )

        self.assertEqual(
            customization,
            "V2@REMUX@杜比视界@HDR@C版",
        )
        self.assertEqual(meta.customization, customization)
        self.assertEqual(len(prepared_titles), 1)
        self.assertIn("杜比视界", prepared_titles[0])
        self.assertNotIn("DoVi", prepared_titles[0])

    def test_refresh_customization_drops_subtitle_only_tokens(self) -> None:
        customization_module = types.ModuleType("app.core.meta.customization")
        words_module = types.ModuleType("app.core.meta.words")

        class FakeCustomizationMatcher:
            @staticmethod
            def match(title):
                self.assertEqual(title, "Movie.2026")
                return "REMUX@U版@简体@字幕"

        class FakeWordsMatcher:
            @staticmethod
            def prepare(title):
                return title, []

        customization_module.CustomizationMatcher = FakeCustomizationMatcher
        words_module.WordsMatcher = FakeWordsMatcher
        modules = {
            "app.core.meta.customization": customization_module,
            "app.core.meta.words": words_module,
        }
        meta = types.SimpleNamespace(customization="繁体@REMUX")

        with mock.patch.dict(sys.modules, modules):
            customization = qb_sync.MoviePilotQbGateway.refresh_customization(
                meta, "Movie.2026"
            )

        self.assertEqual(customization, "REMUX@U版")
        self.assertEqual(meta.customization, "REMUX@U版")


class ReadOnlyQbSyncTest(unittest.TestCase):
    def test_manual_override_preserves_specials_and_category(self) -> None:
        override = qb_sync._normalize_manual_override({
            "media_type": "tv",
            "tmdb_id": "42",
            "season": 0,
            "category": "纪录片",
        })

        self.assertEqual(override, {
            "media_type": "tv",
            "tmdb_id": 42,
            "season": 0,
            "category": "纪录片",
        })

    @staticmethod
    def add_rss_task(
        store,
        *,
        task_id="rss-task",
        downloader="qb-main",
        category="movie",
        task_name="rss-task",
        enabled=True,
        import_enabled=True,
        realtime_hardlink_enabled=False,
        realtime_source_root="",
        realtime_link_root="",
        delete_after_minutes=0,
        delete_files=False,
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
                    task_name,
                    int(enabled),
                    0,
                    json.dumps({
                        "qb_downloader": downloader,
                        "qb_category": category,
                        "import_enabled": import_enabled,
                        "realtime_hardlink_enabled": realtime_hardlink_enabled,
                        "realtime_source_root": realtime_source_root,
                        "realtime_link_root": realtime_link_root,
                        "delete_after_minutes": delete_after_minutes,
                        "delete_files": delete_files,
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
                    "state": "downloading",
                    "category": "movie",
                    "content_path": "/downloads/Example.Movie.2026.mkv",
                    "progress": 0.5,
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

            def plan_inventory_files(
                self,
                _media,
                _files,
                title_override="",
                torrent_meta=None,
            ):
                del torrent_meta
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
            store.upsert_rss_history({
                "task_id": "rss-task",
                "source_key": "source-abc123",
                "content_key": "legacy-qb-name:abc123",
                "title": "Example.Movie.2026.1080p",
                "status": "queued",
                "detail_url_masked": "https://pt.example/details.php?id=42",
            })
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
            self.assertEqual(first["media_title"], "库存中文标题")
            self.assertEqual(
                first["details"]["recognized_title"], "Example Movie"
            )
            self.assertEqual(
                first["details"]["inventory_title"], "库存中文标题"
            )
            self.assertEqual(
                first["details"]["media"]["title"], "库存中文标题"
            )
            self.assertEqual(
                first["source_url_masked"],
                "https://pt.example/details.php?id=42",
            )
            self.assertEqual(first["details"]["rss_source"]["task_id"], "rss-task")
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

    def test_qb_comment_source_url_is_masked_before_card_storage(self) -> None:
        value = qb_sync._source_url_for_torrent(
            {},
            {"comment": "https://pt.example/details.php?id=42&authkey=secret"},
        )
        self.assertEqual(
            value,
            "https://pt.example/details.php?id=42&authkey=***",
        )

    def test_library_refresh_uses_saved_local_files_after_qb_deletion(self) -> None:
        class Meta:
            begin_season = None

            @staticmethod
            def to_dict():
                return {"title": "Local.Movie.2026"}

        class Media:
            title = "Local Movie"
            year = "2026"
            tmdb_id = 42
            season = None
            category = "外语电影"

        class Gateway:
            recognized_titles = []

            @staticmethod
            def recognize(title):
                Gateway.recognized_titles.append(title)
                return Meta(), Media()

            @staticmethod
            def list_torrents(_downloader):
                raise AssertionError("library refresh must not query qB")

            @staticmethod
            def plan_inventory_files(_media, files, **_kwargs):
                self.assertEqual(files[0]["name"], "Local.Movie.2026.mkv")
                return {
                    "expected_files": [{
                        "file_index": 0,
                        "source_name": "Local.Movie.2026.mkv",
                        "relative_path": (
                            "Local Movie (2026) {tmdbid=42}/Local Movie.mkv"
                        ),
                        "inventory_relative_path": (
                            "Local Movie (2026) {tmdbid=42}/Local Movie.strm"
                        ),
                        "size": files[0]["size"],
                    }],
                    "expected_directory": "Local Movie (2026) {tmdbid=42}",
                    "inventory_target_name": (
                        "Local Movie (2026) {tmdbid=42}/Local Movie.strm"
                    ),
                    "total_files": 1,
                    "plan_errors": [],
                }

            @staticmethod
            def media_payload(_media):
                return {"title": "Local Movie", "tmdb_id": 42}

            @staticmethod
            def meta_payload(meta):
                return meta.to_dict()

            @staticmethod
            def media_type(_media):
                return "movie"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Local.Movie.2026.mkv"
            source.write_bytes(b"video")
            library_root = root / "library"
            inventory_file = (
                library_root
                / "外语电影"
                / "Local Movie (2026) {tmdbid=42}"
                / "Local Movie.strm"
            )
            inventory_file.parent.mkdir(parents=True)
            inventory_file.write_text("cloud://movie", encoding="utf-8")
            store = database.SQLiteStore(root / "state.db")
            store.initialize()
            store.upsert_media_item({
                "id": "qb:qb-main:abc123",
                "state": "identified",
                "source_name": "Old.QB.Name",
                "source_path": str(source),
                "downloader_id": "qb-main",
                "info_hash": "abc123",
                "details": {
                    "manual_override": {},
                    "rss_source": {"task_id": "rss-task"},
                    "source_identity": {"kind": "qb_download"},
                },
            })
            store.replace_file_mappings("qb-main", "abc123", [{
                "media_id": "qb:qb-main:abc123",
                "file_index": 0,
                "source_relative_path": source.name,
                "current_source_path": str(source),
            }])
            service = qb_sync.QbSyncService(
                store=store,
                gateway=Gateway(),
                inventory_checker=inventory.LocalInventoryChecker([]),
                library_layout=layout.LibraryLayout.from_config(
                    str(library_root),
                    [{
                        "name": "source",
                        "prefix": str(root),
                        "link_roots": {"movie": str(root / "links")},
                        "enabled": True,
                    }],
                ),
            )

            refreshed = service.refresh_media_from_saved_files(
                "qb:qb-main:abc123"
            )

            self.assertEqual(Gateway.recognized_titles, [source.name])
            self.assertEqual(refreshed["state"], "existing")
            self.assertEqual(refreshed["source_name"], source.name)
            self.assertEqual(refreshed["details"]["inventory"]["exists_count"], 1)
            self.assertEqual(
                refreshed["details"]["rss_source"]["task_id"], "rss-task"
            )

    def test_library_refresh_repairs_source_renamed_after_qb_deletion(self) -> None:
        class Meta:
            begin_season = None

            @staticmethod
            def to_dict():
                return {"title": "Sentimental.Value.2025"}

        class Media:
            title = "情感价值"
            year = "2025"
            tmdb_id = 1124566
            season = None
            category = "外语电影"

        class Gateway:
            recognized_titles = []

            @staticmethod
            def recognize(title):
                Gateway.recognized_titles.append(title)
                return Meta(), Media()

            @staticmethod
            def plan_inventory_files(_media, files, **_kwargs):
                self.assertEqual(
                    files[0]["name"],
                    "[情感价值].Sentimental.Value.2025-REMUX-U版.mkv",
                )
                return {
                    "expected_files": [{
                        "file_index": 0,
                        "source_name": files[0]["name"],
                        "relative_path": "情感价值 (2025) {tmdbid=1124566}/情感价值.mkv",
                        "inventory_relative_path": "情感价值 (2025) {tmdbid=1124566}/情感价值.strm",
                        "size": files[0]["size"],
                    }],
                    "expected_directory": "情感价值 (2025) {tmdbid=1124566}",
                    "inventory_target_name": "情感价值 (2025) {tmdbid=1124566}/情感价值.strm",
                    "total_files": 1,
                    "plan_errors": [],
                }

            @staticmethod
            def media_payload(_media):
                return {"title": "情感价值", "tmdb_id": 1124566}

            @staticmethod
            def meta_payload(meta):
                return meta.to_dict()

            @staticmethod
            def media_type(_media):
                return "movie"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "Sentimental.Value.2025"
            source_dir.mkdir()
            stale = source_dir / "[简英双语].Sentimental.Value.2025-REMUX-U版.mkv"
            actual = source_dir / "[情感价值].Sentimental.Value.2025-REMUX-U版.mkv"
            actual.write_bytes(b"video")
            store = database.SQLiteStore(root / "state.db")
            store.initialize()
            media_id = "qb:qb-main:sentimental"
            store.upsert_media_item({
                "id": media_id,
                "state": "rolled_back",
                "source_name": stale.name,
                "source_path": str(stale),
                "downloader_id": "qb-main",
                "info_hash": "sentimental",
                "rolled_back": True,
                "details": {
                    "manual_override": {},
                    "source_identity": {
                        "kind": "qb_download",
                        "source_path": str(stale),
                    },
                    "torrent": {"content_path": str(stale)},
                },
            })
            store.replace_file_mappings("qb-main", "sentimental", [{
                "media_id": media_id,
                "file_index": 0,
                "source_relative_path": stale.name,
                "current_source_path": str(stale),
                "file_size": actual.stat().st_size,
            }])
            service = qb_sync.QbSyncService(
                store=store,
                gateway=Gateway(),
                inventory_checker=inventory.LocalInventoryChecker([]),
                library_layout=layout.LibraryLayout.from_config(
                    str(root / "library"),
                    [{
                        "name": "source",
                        "prefix": str(root),
                        "link_roots": {"movie": str(root / "links")},
                        "enabled": True,
                    }],
                ),
            )

            refreshed = service.refresh_media_from_saved_files(media_id)

            self.assertEqual(Gateway.recognized_titles, [actual.name])
            self.assertEqual(refreshed["state"], "rolled_back")
            self.assertTrue(refreshed["rolled_back"])
            self.assertEqual(refreshed["source_name"], actual.name)
            self.assertEqual(refreshed["source_path"], str(actual.resolve()))
            self.assertEqual(
                refreshed["details"]["source_identity"]["source_path"],
                str(actual.resolve()),
            )
            mappings = store.list_file_mappings("qb-main", "sentimental")
            self.assertEqual(mappings[0]["current_source_path"], str(actual.resolve()))
            self.assertEqual(mappings[0]["source_relative_path"], actual.name)

    def test_database_lists_cards_by_source_filename_and_keeps_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "state.db")
            store.initialize()
            for info_hash, source_name in (
                ("hash-b", "Zulu.Movie.mkv"),
                ("hash-a", "alpha.Movie.mkv"),
            ):
                store.upsert_media_item({
                    "id": f"qb:qb-main:{info_hash}",
                    "state": "identified",
                    "title": "Same Movie",
                    "source_name": source_name,
                    "source_path": f"/downloads/{info_hash}/{source_name}",
                    "downloader_id": "qb-main",
                    "info_hash": info_hash,
                    "tmdb_id": 42,
                    "details": {"customization": "same-label"},
                })
                store.upsert_torrent_snapshot({
                    "downloader_id": "qb-main",
                    "info_hash": info_hash,
                    "name": source_name,
                    "state": "pausedDL",
                    "category": "movie",
                    "content_path": f"/downloads/{info_hash}/{source_name}",
                    "progress": 0.5,
                    "size": 1,
                    "media_id": None,
                    "source_url_masked": "",
                    "present": 1,
                    "recognition_state": "identified",
                    "inventory_state": "missing",
                    "media_title": "Same Movie",
                    "media_type": "movie",
                    "media_year": "2026",
                    "tmdb_id": 42,
                    "season": None,
                    "poster": "",
                    "recognition_error": "",
                    "recognized_at": database.utc_now(),
                    "last_seen_at": database.utc_now(),
                    "missing_since": None,
                    "details": {},
                    "updated_at": database.utc_now(),
                })

            self.assertEqual(
                [item["source_name"] for item in store.list_media()["items"]],
                ["alpha.Movie.mkv", "Zulu.Movie.mkv"],
            )
            self.assertEqual(
                [item["name"] for item in store.list_torrents()["items"]],
                ["alpha.Movie.mkv", "Zulu.Movie.mkv"],
            )
            self.assertEqual(store.list_media()["total"], 2)
            self.assertEqual(store.list_torrents()["total"], 2)

    def test_database_lists_same_title_by_resolution_then_customization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "state.db")
            store.initialize()
            records = (
                ("hash-1080", "1080p", "REMUX@C版"),
                ("hash-2160-c", "2160p", "REMUX@C版"),
                ("hash-2160-a", "2160p", "REMUX@A版"),
            )
            for info_hash, resolution, customization in records:
                store.upsert_media_item({
                    "id": f"qb:qb-main:{info_hash}",
                    "state": "identified",
                    "title": "Same Movie",
                    "source_name": f"{info_hash}.mkv",
                    "source_path": f"/downloads/{info_hash}.mkv",
                    "downloader_id": "qb-main",
                    "info_hash": info_hash,
                    "tmdb_id": 42,
                    "details": {
                        "recognition": {
                            "meta": {
                                "resource_pix": resolution,
                                "customization": customization,
                            }
                        }
                    },
                })

            self.assertEqual(
                [item["info_hash"] for item in store.list_media()["items"]],
                ["hash-1080", "hash-2160-a", "hash-2160-c"],
            )

    def test_realtime_hardlink_preserves_qb_source_and_moves_card_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "CHD"
            link_root = root / "CHDlink"
            source = source_root / "Movie" / "Movie.2026.mkv"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"movie-data")
            mappings = [{
                "file_index": 0,
                "current_source_path": str(source),
                "source_relative_path": "Movie/Movie.2026.mkv",
                "details": {"recognition": {"customization": "REMUX@C版"}},
            }]

            updated, content_path, details = qb_sync.create_realtime_hardlinks(
                content_path=str(source.parent),
                file_mappings=mappings,
                source_root=str(source_root),
                link_root=str(link_root),
            )

            target = link_root / "Movie" / "Movie.2026.mkv"
            self.assertTrue(target.is_file())
            self.assertTrue(target.samefile(source))
            self.assertEqual(
                Path(content_path).resolve(),
                (link_root / "Movie").resolve(),
            )
            self.assertEqual(
                Path(updated[0]["current_source_path"]).resolve(),
                target.resolve(),
            )
            self.assertEqual(
                Path(updated[0]["details"]["qb_source_path"]).resolve(),
                source.resolve(),
            )
            self.assertEqual(details["created_count"], 1)
            self.assertEqual(details["reused_count"], 0)

            _updated, _content_path, repeated = qb_sync.create_realtime_hardlinks(
                content_path=str(source.parent),
                file_mappings=mappings,
                source_root=str(source_root),
                link_root=str(link_root),
            )
            self.assertEqual(repeated["created_count"], 0)
            self.assertEqual(repeated["reused_count"], 1)

    def test_completed_realtime_task_moves_library_card_to_link_tree(self) -> None:
        class Meta:
            begin_season = None

        class Media:
            title = "CHD Movie"
            year = "2026"
            tmdb_id = 42
            season = None
            category = "外语电影"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "CHD"
            link_root = root / "CHDlink"
            source = source_root / "Movie" / "Movie.2026.mkv"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"movie-data")

            class Gateway:
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
                        "hash": "CHDMOVIE",
                        "title": "Movie.2026.REMUX-CHD",
                        "state": "uploading",
                        "category": "chd",
                        "save_path": str(source_root),
                        "content_path": str(source),
                        "progress": 1.0,
                        "size": source.stat().st_size,
                    }]

                @staticmethod
                def torrent_dict(item):
                    return dict(item)

                @staticmethod
                def recognize(_title):
                    return Meta(), Media()

                @staticmethod
                def list_torrent_files(_downloader, _info_hash):
                    raise AssertionError("completed sync must prefer local files")

                @staticmethod
                def plan_inventory_files(_media, _files, **_kwargs):
                    return {
                        "expected_files": [{
                            "file_index": 0,
                            "source_name": "Movie.2026.mkv",
                            "new_rel": "CHD Movie (2026) {tmdbid=42}/CHD Movie.mkv",
                            "relative_path": "CHD Movie (2026) {tmdbid=42}/CHD Movie.mkv",
                            "inventory_relative_path": "CHD Movie (2026) {tmdbid=42}/CHD Movie.strm",
                            "size": source.stat().st_size,
                        }],
                        "expected_directory": "CHD Movie (2026) {tmdbid=42}",
                        "total_files": 1,
                        "plan_errors": [],
                    }

                @staticmethod
                def media_payload(_media):
                    return {"title": "CHD Movie", "tmdb_id": 42}

                @staticmethod
                def meta_payload(_meta):
                    return {}

                @staticmethod
                def poster(_media):
                    return "https://image.example/poster.jpg"

                @staticmethod
                def media_type(_media):
                    return "movie"

            store = database.SQLiteStore(root / "state.db")
            store.initialize()
            self.add_rss_task(
                store,
                task_id="chd-task",
                task_name="彩虹岛",
                category="chd",
                realtime_hardlink_enabled=True,
                realtime_source_root=str(source_root),
                realtime_link_root=str(link_root),
            )
            store.upsert_rss_history({
                "task_id": "chd-task",
                "source_key": "source-chd",
                "content_key": "qb-main:chdmovie",
                "title": "Movie.2026.REMUX-CHD",
                "status": "queued",
                "detail_url_masked": "https://pt.example/details.php?id=42",
                "payload": {"info_hash": "chdmovie"},
            })
            store.create_background_task("chd-complete", qb_sync.QB_TASK_TYPE)

            qb_sync.QbSyncService(store=store, gateway=Gateway()).run(
                "chd-complete"
            )

            self.assertEqual(store.list_torrents()["total"], 0)
            media = store.list_media()["items"][0]
            self.assertEqual(
                media["details"]["import_control"]["task_id"],
                "chd-task",
            )
            linked_file = link_root / "Movie" / "Movie.2026.mkv"
            self.assertTrue(linked_file.samefile(source))
            self.assertEqual(
                Path(media["source_path"]).resolve(),
                linked_file.resolve(),
            )
            self.assertEqual(
                media["details"]["source_identity"]["kind"],
                "realtime_hardlink",
            )
            self.assertEqual(
                Path(media["details"]["source_identity"]["qb_source_path"]).resolve(),
                source.resolve(),
            )
            self.assertEqual(
                media["details"]["rss_source"]["detail_url_masked"],
                "https://pt.example/details.php?id=42",
            )
            mapping = store.list_file_mappings("qb-main", "chdmovie")[0]
            self.assertEqual(
                Path(mapping["current_source_path"]).resolve(),
                linked_file.resolve(),
            )
            self.assertEqual(
                Path(mapping["details"]["qb_source_path"]).resolve(),
                source.resolve(),
            )

    def test_completed_realtime_task_backfills_without_import_card(self) -> None:
        class Meta:
            begin_season = None

        class Media:
            title = "CHD Backfill"
            year = "2026"
            tmdb_id = 43
            season = None
            category = "外语电影"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "CHD"
            link_root = root / "CHDlink"
            source = source_root / "Backfill" / "Backfill.2026.mkv"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"movie-data")

            class Gateway:
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
                        "hash": "CHDBACKFILL",
                        "title": "Backfill.2026.REMUX-CHD",
                        "state": "uploading",
                        "category": "chd",
                        "content_path": str(source.parent),
                        "progress": 1.0,
                        "size": source.stat().st_size,
                    }]

                @staticmethod
                def torrent_dict(item):
                    return dict(item)

                @staticmethod
                def recognize(_title):
                    return None, None

                @staticmethod
                def list_torrent_files(_downloader, _info_hash):
                    raise AssertionError("completed sync must prefer local files")

                @staticmethod
                def plan_inventory_files(_media, _files, **_kwargs):
                    return {
                        "expected_files": [{
                            "file_index": 0,
                            "source_name": "Backfill/Backfill.2026.mkv",
                            "new_rel": "CHD Backfill (2026) {tmdbid=43}/CHD Backfill.mkv",
                            "relative_path": "CHD Backfill (2026) {tmdbid=43}/CHD Backfill.mkv",
                            "inventory_relative_path": "CHD Backfill (2026) {tmdbid=43}/CHD Backfill.strm",
                            "size": source.stat().st_size,
                        }],
                        "expected_directory": "CHD Backfill (2026) {tmdbid=43}",
                        "total_files": 1,
                        "plan_errors": [],
                    }

                @staticmethod
                def media_payload(_media):
                    return {"title": "CHD Backfill", "tmdb_id": 43}

                @staticmethod
                def meta_payload(_meta):
                    return {}

                @staticmethod
                def poster(_media):
                    return ""

                @staticmethod
                def media_type(_media):
                    return "movie"

            store = database.SQLiteStore(root / "state.db")
            store.initialize()
            self.add_rss_task(
                store,
                task_id="chd-task",
                task_name="彩虹岛",
                category="chd",
                import_enabled=False,
                realtime_hardlink_enabled=True,
                realtime_source_root=str(source_root),
                realtime_link_root=str(link_root),
            )
            store.upsert_rss_history({
                "task_id": "chd-task",
                "source_key": "source-chd-backfill",
                "content_key": "qb-main:chdbackfill",
                "title": "Backfill.2026.REMUX-CHD",
                "status": "processed",
                "reason": "下载完成，任务未启用入库",
                "payload": {
                    "info_hash": "chdbackfill",
                    "completion_processed": True,
                    "imported_to_library": False,
                },
            })
            store.create_background_task("chd-backfill", qb_sync.QB_TASK_TYPE)

            result = qb_sync.QbSyncService(store=store, gateway=Gateway()).run(
                "chd-backfill"
            )

            linked_file = link_root / "Backfill" / "Backfill.2026.mkv"
            self.assertTrue(linked_file.samefile(source))
            self.assertEqual(store.list_media()["total"], 0)
            self.assertEqual(result["completed_skipped"], 0)
            history = store.latest_rss_history_for_torrent(
                "qb-main", "chdbackfill"
            )
            self.assertEqual(
                history["payload"]["realtime_hardlink"]["state"],
                "linked",
            )
            self.assertFalse(history["payload"]["imported_to_library"])
            self.assertIn("已创建实时硬链接", history["reason"])

    def test_completed_torrent_with_import_disabled_stays_out_of_library(self) -> None:
        class Gateway:
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
                    "hash": "NOIMPORT",
                    "title": "Download.Only.2026",
                    "state": "pausedUP",
                    "category": "movie",
                    "content_path": "/downloads/download-only.mkv",
                    "progress": 1.0,
                    "size": 4,
                }]

            @staticmethod
            def torrent_dict(item):
                return dict(item)

            @staticmethod
            def recognize(_title):
                return None, None

            @staticmethod
            def meta_payload(_meta):
                return {}

        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "state.db")
            store.initialize()
            self.add_rss_task(store, import_enabled=False)
            store.create_background_task("download-only", qb_sync.QB_TASK_TYPE)

            qb_sync.QbSyncService(store=store, gateway=Gateway()).run(
                "download-only"
            )

            snapshot = store.get_torrent_snapshot("qb-main", "noimport")
            self.assertIsNone(snapshot)
            self.assertEqual(store.list_torrents()["total"], 0)
            self.assertEqual(store.list_media()["total"], 0)

    def test_completed_torrent_schedules_qb_source_deletion_by_hash(self) -> None:
        class Gateway:
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
                    "hash": "CHDDELETE",
                    "title": "CHD.Movie.2026",
                    "state": "pausedUP",
                    "category": "chd",
                    "content_path": "/SSD/QB目录/REMUX/CHD/CHD.Movie.2026.mkv",
                    "progress": 1.0,
                    "size": 4,
                }]

            @staticmethod
            def torrent_dict(item):
                return dict(item)

            @staticmethod
            def recognize(_title):
                return None, None

            @staticmethod
            def meta_payload(_meta):
                return {}

        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "state.db")
            store.initialize()
            self.add_rss_task(
                store,
                task_name="彩虹岛",
                category="chd",
                import_enabled=False,
                delete_after_minutes=120,
                delete_files=True,
            )
            store.upsert_rss_history({
                "task_id": "rss-task",
                "source_key": "source-chddelete",
                "content_key": "qb-main:chddelete",
                "title": "CHD.Movie.2026",
                "status": "queued",
                "payload": {"info_hash": "chddelete"},
            })
            store.create_background_task("chd-delete", qb_sync.QB_TASK_TYPE)

            qb_sync.QbSyncService(store=store, gateway=Gateway()).run(
                "chd-delete",
                schedule_delete=True,
            )

            jobs = store.list_qb_delete_jobs()
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["downloader_id"], "qb-main")
            self.assertEqual(jobs[0]["info_hash"], "chddelete")
            self.assertTrue(jobs[0]["delete_files"])
            self.assertEqual(
                jobs[0]["source_path"],
                "/SSD/QB目录/REMUX/CHD/CHD.Movie.2026.mkv",
            )
            self.assertEqual(
                jobs[0]["details"]["deletion_scope"],
                "qb_task_and_save_path",
            )
            self.assertNotIn("CHDlink", repr(jobs[0]))

    def test_completed_torrent_with_import_enabled_moves_to_library_only(self) -> None:
        class Gateway:
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
                    "hash": "IMPORTME",
                    "title": "Import.Me.2026",
                    "state": "pausedUP",
                    "category": "movie",
                    "content_path": "/downloads/import-me.mkv",
                    "progress": 1.0,
                    "size": 4,
                }]

            @staticmethod
            def torrent_dict(item):
                return dict(item)

            @staticmethod
            def recognize(_title):
                return None, None

            @staticmethod
            def meta_payload(_meta):
                return {}

        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "state.db")
            store.initialize()
            self.add_rss_task(store, import_enabled=True)
            store.upsert_rss_history({
                "task_id": "rss-task",
                "source_key": "source-importme",
                "content_key": "qb-main:importme",
                "title": "Import.Me.2026",
                "status": "queued",
                "payload": {"info_hash": "importme"},
            })
            store.create_background_task("import-me", qb_sync.QB_TASK_TYPE)

            result = qb_sync.QbSyncService(store=store, gateway=Gateway()).run(
                "import-me"
            )

            self.assertEqual(result["completed"], 1)
            self.assertEqual(store.list_torrents()["total"], 0)
            media = store.list_media()["items"]
            self.assertEqual(len(media), 1)
            self.assertEqual(media[0]["details"]["import_control"]["task_id"], "rss-task")
            history = store.latest_rss_history_for_torrent("qb-main", "importme")
            self.assertEqual(history["status"], "processed")
            self.assertTrue(history["payload"]["completion_processed"])

    def test_completed_state_with_zero_progress_stays_in_qb_management(self) -> None:
        class Gateway:
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
                    "hash": "FALSECOMPLETE",
                    "title": "False.Complete.2026",
                    "state": "completed",
                    "category": "movie",
                    "content_path": "/downloads/false-complete.mkv",
                    "progress": 0.0,
                    "size": 4,
                }]

            @staticmethod
            def torrent_dict(item):
                return dict(item)

            @staticmethod
            def recognize(_title):
                return None, None

            @staticmethod
            def meta_payload(_meta):
                return {}

        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "state.db")
            store.initialize()
            self.add_rss_task(store, import_enabled=True)
            store.upsert_rss_history({
                "task_id": "rss-task",
                "source_key": "source-falsecomplete",
                "content_key": "qb-main:falsecomplete",
                "title": "False.Complete.2026",
                "status": "queued",
                "payload": {"info_hash": "falsecomplete"},
            })

            qb_sync.QbSyncService(
                store=store,
                gateway=Gateway(),
            ).refresh_item("qb-main", "falsecomplete")

            self.assertIsNotNone(store.get_torrent_snapshot(
                "qb-main", "falsecomplete"
            ))
            self.assertEqual(store.list_media()["total"], 0)
            history = store.latest_rss_history_for_torrent(
                "qb-main", "falsecomplete"
            )
            self.assertEqual(history["status"], "queued")
            self.assertFalse(bool(
                history["payload"].get("completion_processed")
            ))

    def test_manual_refresh_reopens_stale_completed_history(self) -> None:
        class Gateway:
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
                    "hash": "STALECOMPLETE",
                    "title": "Stale.Complete.2026",
                    "state": "paused",
                    "category": "movie",
                    "content_path": "/downloads/stale-complete.mkv",
                    "progress": 0.0,
                    "size": 4,
                }]

            @staticmethod
            def torrent_dict(item):
                return dict(item)

            @staticmethod
            def recognize(_title):
                return None, None

            @staticmethod
            def meta_payload(_meta):
                return {}

        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "state.db")
            store.initialize()
            self.add_rss_task(store, import_enabled=True)
            store.upsert_rss_history({
                "task_id": "rss-task",
                "source_key": "source-stalecomplete",
                "content_key": "qb-main:stalecomplete",
                "title": "Stale.Complete.2026",
                "status": "processed",
                "reason": "下载完成，已转入入库管理",
                "payload": {
                    "downloader": "qb-main",
                    "info_hash": "stalecomplete",
                    "completion_processed": True,
                    "completion_processed_at": database.utc_now(),
                    "imported_to_library": True,
                    "qb_delete": {"job_id": "qb-main:stalecomplete"},
                },
            })
            store.upsert_media_item({
                "id": "qb:qb-main:stalecomplete",
                "state": "imported",
                "media_type": "movie",
                "title": "Stale Complete",
                "source_name": "Stale.Complete.2026",
                "source_path": "/downloads/stale-complete.mkv",
                "downloader_id": "qb-main",
                "info_hash": "stalecomplete",
                "tmdb_id": 1,
                "season": None,
                "category": "movie",
                "target_name": "Stale Complete.strm",
                "failure_code": "",
                "failure_message": "",
                "details": {},
            })
            store.schedule_qb_delete(
                task_id="rss-task",
                task_name="RSS Task",
                downloader_id="qb-main",
                info_hash="stalecomplete",
                source_path="/downloads/stale-complete.mkv",
                delete_files=False,
                due_at="2030-01-01T00:00:00+00:00",
            )

            qb_sync.QbSyncService(
                store=store,
                gateway=Gateway(),
            ).refresh_item("qb-main", "stalecomplete")

            self.assertIsNone(store.get_torrent_snapshot(
                "qb-main", "stalecomplete"
            ))
            protected_media = store.get_media_item(
                "qb:qb-main:stalecomplete"
            )
            self.assertEqual(protected_media["state"], "imported")
            protected_history = store.latest_rss_history_for_torrent(
                "qb-main", "stalecomplete"
            )
            self.assertTrue(
                protected_history["payload"]["completion_processed"]
            )

            protected_media["state"] = "identified"
            store.upsert_media_item(protected_media)
            qb_sync.QbSyncService(
                store=store,
                gateway=Gateway(),
            ).refresh_item("qb-main", "stalecomplete")

            self.assertIsNotNone(store.get_torrent_snapshot(
                "qb-main", "stalecomplete"
            ))
            self.assertIsNone(store.get_media_item(
                "qb:qb-main:stalecomplete"
            ))
            self.assertFalse(any(
                item["info_hash"] == "stalecomplete"
                for item in store.list_qb_delete_jobs()
            ))
            history = store.latest_rss_history_for_torrent(
                "qb-main", "stalecomplete"
            )
            self.assertEqual(history["status"], "queued")
            self.assertIn("恢复到 QB 管理", history["reason"])
            self.assertNotIn("completion_processed", history["payload"])
            self.assertNotIn("imported_to_library", history["payload"])
            self.assertNotIn("qb_delete", history["payload"])

    def test_initial_rss_recognition_waits_for_completion_callback(self) -> None:
        class Gateway:
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
                    "hash": "CALLBACKONLY",
                    "title": "Callback.Only.2026",
                    "state": "pausedUP",
                    "category": "movie",
                    "content_path": "/downloads/callback-only.mkv",
                    "progress": 1.0,
                    "size": 4,
                }]

            @staticmethod
            def torrent_dict(item):
                return dict(item)

            @staticmethod
            def recognize(_title):
                return None, None

            @staticmethod
            def meta_payload(_meta):
                return {}

        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "state.db")
            store.initialize()
            self.add_rss_task(store, import_enabled=False)
            store.upsert_rss_history({
                "task_id": "rss-task",
                "source_key": "source-callbackonly",
                "content_key": "qb-main:callbackonly",
                "title": "Callback.Only.2026",
                "status": "queued",
                "payload": {"info_hash": "callbackonly"},
            })
            service = qb_sync.QbSyncService(store=store, gateway=Gateway())

            service.refresh_item(
                "qb-main",
                "callbackonly",
                allow_completion_transition=False,
            )
            self.assertIsNotNone(store.get_torrent_snapshot(
                "qb-main", "callbackonly"
            ))

            result = service.refresh_item(
                "qb-main",
                "callbackonly",
                completion_confirmed=True,
            )
            self.assertTrue(result["completed"])
            self.assertIsNone(store.get_torrent_snapshot(
                "qb-main", "callbackonly"
            ))
            history = store.latest_rss_history_for_torrent(
                "qb-main", "callbackonly"
            )
            self.assertEqual(history["status"], "processed")
            self.assertTrue(history["payload"]["completion_processed"])

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


class SourceTargetMappingTest(unittest.TestCase):
    def test_dotted_content_directory_keeps_its_folder_component(self) -> None:
        source_name = "Show.2026.S03E01.2160p.WEB-DL.mp4"

        path = qb_sync.resolve_current_source_path(
            {
                "content_path": (
                    "/MP/完结剧集1/"
                    "Show.2026.S03.Complete.2160p.WEB-DL-GROUP"
                )
            },
            source_name,
        )

        self.assertEqual(
            path,
            (
                "/MP/完结剧集1/"
                "Show.2026.S03.Complete.2160p.WEB-DL-GROUP/"
                f"{source_name}"
            ),
        )

    def test_single_file_content_path_is_not_duplicated(self) -> None:
        source_name = "Movie.2026.2160p.mkv"

        path = qb_sync.resolve_current_source_path(
            {"content_path": f"/MP/电影/{source_name}"},
            source_name,
        )

        self.assertEqual(path, f"/MP/电影/{source_name}")

    def test_mapping_keeps_qb_source_and_mp_target_as_independent_paths(self) -> None:
        mappings = qb_sync.build_source_target_mappings(
            downloader_id="qb-main",
            info_hash="ABC123",
            media_id="qb:qb-main:abc123",
            torrent={
                "save_path": "/MP/downloads",
                "content_path": "/MP/downloads/[沙丘].Dune",
            },
            expected_files=[{
                "file_index": 3,
                "source_name": "[沙丘].Dune/[沙丘].Dune-国配-REMUX.mkv",
                "relative_path": "沙丘2 (2024) [tmdbid=693134]/沙丘2 - 2160p.mkv",
                "new_rel": "沙丘2 (2024) [tmdbid=693134]/沙丘2 - 2160p.mkv",
                "inventory_relative_path": "沙丘2 (2024) [tmdbid=693134]/沙丘2 - 2160p.strm",
                "size": 100,
            }],
            path_plan={
                "link_files": [{
                    "file_index": 3,
                    "source_name": "[沙丘].Dune/[沙丘].Dune-国配-REMUX.mkv",
                    "path": "/MP/电影UP/华语电影/沙丘2 (2024) [tmdbid=693134]/沙丘2 - 2160p.mkv",
                }],
                "inventory_files": [{
                    "file_index": 3,
                    "source_name": "[沙丘].Dune/[沙丘].Dune-国配-REMUX.mkv",
                    "path": "/SSD/云盘/strm/影视库/华语电影/沙丘2 (2024) [tmdbid=693134]/沙丘2 - 2160p.strm",
                }],
            },
            inventory_details={
                "files": [{
                    "file_index": 3,
                    "source_name": "[沙丘].Dune/[沙丘].Dune-国配-REMUX.mkv",
                    "inventory_exists": False,
                    "status": "missing",
                }],
            },
        )

        self.assertEqual(len(mappings), 1)
        mapping = mappings[0]
        self.assertEqual(
            mapping["current_source_path"],
            "/MP/downloads/[沙丘].Dune/[沙丘].Dune-国配-REMUX.mkv",
        )
        self.assertEqual(
            mapping["new_rel"],
            "沙丘2 (2024) [tmdbid=693134]/沙丘2 - 2160p.mkv",
        )
        self.assertNotEqual(
            Path(mapping["current_source_path"]).name,
            Path(mapping["local_hardlink_path"]).name,
        )


if __name__ == "__main__":
    unittest.main()
