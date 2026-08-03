"""Framework checks for the RSS All-in-One MoviePilot plugin."""

import ast
import hashlib
import importlib.util
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "RssAllInOne"
PLUGIN_DIR = ROOT / "plugins.v2" / PLUGIN_ID.lower()


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PLUGIN_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


domain = load_module("rssallinone_domain", "domain.py")
database = load_module("rssallinone_database", "database.py")


class DomainContractTest(unittest.TestCase):
    def test_specials_use_season_zero(self) -> None:
        self.assertEqual(domain.validate_season(0), 0)
        self.assertEqual(domain.validate_season("0"), 0)
        self.assertIsNone(domain.validate_season(None))
        with self.assertRaises(ValueError):
            domain.validate_season(-1)

    def test_media_transition_matrix_is_explicit(self) -> None:
        self.assertTrue(domain.can_transition("identified", "pending"))
        self.assertTrue(domain.can_transition("importing", "rolled_back"))
        self.assertFalse(domain.can_transition("imported", "discovered"))
        self.assertFalse(domain.can_transition("unknown", "pending"))


class SQLiteFrameworkTest(unittest.TestCase):
    def test_schema_initializes_and_lists_empty_collections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "rssallinone.db")
            store.initialize()

            health = store.health()
            self.assertTrue(health["ready"])
            self.assertEqual(health["schema_version"], database.SCHEMA_VERSION)
            self.assertEqual(store.counts()["media"], 0)
            self.assertEqual(store.list_media()["items"], [])
            self.assertEqual(store.list_torrents()["items"], [])
            self.assertEqual(store.list_rss_history()["items"], [])

    def test_schema_accepts_specials_season_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "rssallinone.db")
            store.initialize()
            now = database.utc_now()
            with store.connection() as connection:
                connection.execute(
                    """INSERT INTO media_items(
                        id, state, media_type, title, tmdb_id, season, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("special", "identified", "tv", "特别篇", 1, 0, now, now),
                )
            item = store.list_media()["items"][0]
            self.assertEqual(item["season"], 0)

    def test_v1_torrent_snapshots_migrate_without_losing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rssallinone.db"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE torrent_snapshots (
                        downloader_id TEXT NOT NULL,
                        info_hash TEXT NOT NULL,
                        name TEXT NOT NULL DEFAULT '',
                        state TEXT NOT NULL DEFAULT '',
                        category TEXT NOT NULL DEFAULT '',
                        content_path TEXT NOT NULL DEFAULT '',
                        progress REAL NOT NULL DEFAULT 0,
                        size INTEGER NOT NULL DEFAULT 0,
                        media_id TEXT,
                        source_url_masked TEXT NOT NULL DEFAULT '',
                        details_json TEXT NOT NULL DEFAULT '{}',
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (downloader_id, info_hash)
                    );
                    INSERT INTO torrent_snapshots(
                        downloader_id, info_hash, name, updated_at
                    ) VALUES ('qb-main', 'abc123', '旧快照', '2026-08-03T00:00:00+00:00');
                    """
                )
                connection.commit()
            finally:
                connection.close()

            store = database.SQLiteStore(path)
            store.initialize()
            migrated = store.get_torrent_snapshot("qb-main", "abc123")
            self.assertEqual(migrated["name"], "旧快照")
            self.assertEqual(migrated["present"], 1)
            self.assertEqual(migrated["inventory_state"], "unknown")
            self.assertEqual(store.health()["schema_version"], 2)


class RepositoryContractTest(unittest.TestCase):
    def test_identity_and_market_metadata_match(self) -> None:
        package = json.loads((ROOT / "package.v2.json").read_text(encoding="utf-8"))
        metadata = package[PLUGIN_ID]
        tree = ast.parse((PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8"))
        plugin_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == PLUGIN_ID
        )
        attributes = {}
        for item in plugin_class.body:
            if isinstance(item, ast.Assign) and len(item.targets) == 1:
                target = item.targets[0]
                if isinstance(target, ast.Name):
                    try:
                        attributes[target.id] = ast.literal_eval(item.value)
                    except (TypeError, ValueError):
                        pass
        self.assertEqual(PLUGIN_DIR.name, PLUGIN_ID.lower())
        self.assertEqual(attributes["plugin_name"], metadata["name"])
        self.assertEqual(attributes["plugin_version"], metadata["version"])
        self.assertEqual(attributes["plugin_desc"], metadata["description"])
        self.assertEqual(attributes["auth_level"], metadata["level"])

    def test_vue_full_page_contract(self) -> None:
        vite = (PLUGIN_DIR / "vite.config.js").read_text(encoding="utf-8")
        backend = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
        app_page = (
            PLUGIN_DIR / "src" / "components" / "AppPage.vue"
        ).read_text(encoding="utf-8")
        self.assertIn("'./AppPage'", vite)
        self.assertIn("'./Page'", vite)
        self.assertIn("'./Config'", vite)
        self.assertIn("get_sidebar_nav", backend)
        self.assertIn('return "vue", "dist/assets"', backend)
        self.assertEqual(
            app_page.count(':items-per-page="-1"'),
            app_page.count("hide-default-footer"),
        )

    def test_clouddrive_contract_is_original_and_generated(self) -> None:
        digest = hashlib.sha256((PLUGIN_DIR / "clouddrive.proto").read_bytes()).hexdigest()
        self.assertEqual(
            digest.upper(),
            "3F1AB3E53EA9A5A73C9E154724C7AD0E6B824454F1B7C27BF6EF0F2FCE41C552",
        )
        generated = PLUGIN_DIR / "generated" / "clouddrive_pb2_grpc.py"
        self.assertTrue(generated.is_file())
        self.assertIn(
            "from . import clouddrive_pb2 as clouddrive__pb2",
            generated.read_text(encoding="utf-8"),
        )

    def test_prompt_no_longer_requires_remote_moviepilot(self) -> None:
        prompt = (
            PLUGIN_DIR / "MoviePilot_ReelHarbor_V1_plugin_prompt.md"
        ).read_text(encoding="utf-8")
        self.assertIn("插件只使用当前所在 MoviePilot 实例", prompt)
        self.assertNotIn("选择从哪个 MoviePilot 实例同步站点", prompt)
        self.assertIn("大于等于 0 的数字", prompt)

    def test_inventory_is_direct_local_filesystem_only(self) -> None:
        backend = (PLUGIN_DIR / "qb_sync.py").read_text(encoding="utf-8")
        prompt = (
            PLUGIN_DIR / "MoviePilot_ReelHarbor_V1_plugin_prompt.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("get_no_exists_info", backend)
        self.assertNotIn("media_exists", backend)
        self.assertIn("直接读取 `mp_library_path` 下的本地目录和文件", prompt)

    def test_current_layout_defaults_are_documented(self) -> None:
        prompt = (
            PLUGIN_DIR / "MoviePilot_ReelHarbor_V1_plugin_prompt.md"
        ).read_text(encoding="utf-8")
        config = (
            PLUGIN_DIR / "src" / "components" / "Config.vue"
        ).read_text(encoding="utf-8")
        for expected in (
            "/SSD/云盘/strm/影视库",
            "/MP/电影UP",
            "/MP/剧集UP",
            "/SSD/云盘/l",
        ):
            self.assertIn(expected, prompt)
            self.assertIn(expected, config)
        self.assertIn("默认覆盖 MoviePilot 返回的全部分类", prompt)

    def test_qb_management_is_scoped_by_saved_rss_tasks(self) -> None:
        backend = (PLUGIN_DIR / "qb_sync.py").read_text(encoding="utf-8")
        prompt = (
            PLUGIN_DIR / "MoviePilot_ReelHarbor_V1_plugin_prompt.md"
        ).read_text(encoding="utf-8")
        self.assertIn("RssTaskQbScope", backend)
        self.assertIn("VT+ RSS 任务声明的 `(QB下载器, QB分类)`", prompt)
        self.assertIn("禁止回退为全量扫描", prompt)

    def test_vt_rss_task_editor_contract(self) -> None:
        editor = (
            PLUGIN_DIR / "src" / "components" / "RssTaskEditor.vue"
        ).read_text(encoding="utf-8")
        app_page = (
            PLUGIN_DIR / "src" / "components" / "AppPage.vue"
        ).read_text(encoding="utf-8")
        config = (
            PLUGIN_DIR / "src" / "components" / "Config.vue"
        ).read_text(encoding="utf-8")
        self.assertIn("添加任务", editor)
        self.assertIn("QB下载器", editor)
        self.assertIn("QB分类", editor)
        self.assertIn("saveRssTasks", app_page)
        self.assertNotIn("电影目录组分类", config)
        self.assertNotIn("剧集目录组分类", config)


class PluginLifecycleTest(unittest.TestCase):
    def test_plugin_loads_inside_a_minimal_moviepilot_host(self) -> None:
        app = types.ModuleType("app")
        app.__path__ = []
        app_log = types.ModuleType("app.log")
        app_plugins = types.ModuleType("app.plugins")
        app_db = types.ModuleType("app.db")
        app_db.__path__ = []
        app_site_oper = types.ModuleType("app.db.site_oper")

        class Logger:
            @staticmethod
            def error(*_args, **_kwargs):
                return None

        class SiteOper:
            @staticmethod
            def list():
                return [types.SimpleNamespace(
                    id=1,
                    name="测试站点",
                    url="https://tracker.example.test/",
                    is_active=True,
                    public=False,
                    apikey=None,
                    token=None,
                    cookie="secret-cookie",
                    proxy=False,
                    render=False,
                )]

        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory)

            class PluginBase:
                def __init__(self, *_args, **_kwargs):
                    self._config = {}

                @staticmethod
                def get_data_path():
                    return data_path

            app_log.logger = Logger()
            app_plugins._PluginBase = PluginBase
            app_site_oper.SiteOper = SiteOper
            previous = {
                name: sys.modules.get(name)
                for name in (
                    "app", "app.log", "app.plugins", "app.db",
                    "app.db.site_oper", "rssallinone",
                )
            }
            sys.modules["app"] = app
            sys.modules["app.log"] = app_log
            sys.modules["app.plugins"] = app_plugins
            sys.modules["app.db"] = app_db
            sys.modules["app.db.site_oper"] = app_site_oper
            try:
                spec = importlib.util.spec_from_file_location(
                    "rssallinone",
                    PLUGIN_DIR / "__init__.py",
                    submodule_search_locations=[str(PLUGIN_DIR)],
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules["rssallinone"] = module
                spec.loader.exec_module(module)

                plugin = module.RssAllInOne()
                plugin.init_plugin({"enabled": True})
                overview = plugin.api_overview()
                health = plugin.api_health()
                saved = plugin.api_save_rss_tasks({
                    "items": [{
                        "id": "movies",
                        "name": "电影 RSS",
                        "enabled": True,
                        "config": {
                            "qb_downloader": "qb-main",
                            "qb_category": "movie",
                        },
                    }],
                })
                sites = plugin.api_sites()

                self.assertTrue(plugin.get_state())
                self.assertTrue(overview["success"])
                self.assertEqual(overview["plugin"]["id"], PLUGIN_ID)
                self.assertTrue(health["database"]["ready"])
                self.assertTrue((data_path / "rssallinone.db").is_file())
                self.assertEqual(plugin.get_sidebar_nav()[0]["nav_key"], "rssallinone")
                self.assertTrue(saved["success"])
                self.assertEqual(saved["items"][0]["config"]["qb_category"], "movie")
                self.assertEqual(
                    plugin._qb_scope().categories_for("qb-main"),
                    ["movie"],
                )
                self.assertTrue(sites["success"])
                self.assertEqual(sites["items"][0]["auth_mode"], "Cookie")
                self.assertNotIn("secret-cookie", repr(sites))

                from rssallinone.generated import clouddrive_pb2_grpc

                self.assertTrue(clouddrive_pb2_grpc.CloudDriveFileSrvStub)
            finally:
                for name, value in previous.items():
                    if value is None:
                        sys.modules.pop(name, None)
                    else:
                        sys.modules[name] = value


if __name__ == "__main__":
    unittest.main()
