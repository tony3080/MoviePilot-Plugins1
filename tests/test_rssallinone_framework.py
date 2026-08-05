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
            self.assertEqual(store.counts()["file_mappings"], 0)

    def test_file_mappings_replace_source_and_target_pairs_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "rssallinone.db")
            store.initialize()
            records = store.replace_file_mappings("qb-main", "ABC123", [{
                "file_index": 7,
                "media_id": "qb:qb-main:abc123",
                "source_relative_path": "Show/Show.S01E01.mkv",
                "current_source_path": "/downloads/Show/Show.S01E01.mkv",
                "new_rel": "剧名/Season 01/剧名 S01E01.mkv",
                "local_hardlink_path": "/staging/剧名/Season 01/剧名 S01E01.mkv",
                "inventory_path": "/library/剧名/Season 01/剧名 S01E01.strm",
                "inventory_exists": False,
                "file_size": 1024,
            }])

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["info_hash"], "abc123")
            self.assertEqual(records[0]["file_index"], 7)
            self.assertEqual(records[0]["state"], "planned")

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

    def test_archived_rss_history_is_hidden_but_still_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "rssallinone.db")
            store.initialize()
            store.upsert_rss_history({
                "task_id": "task-a",
                "source_key": "source-a",
                "content_key": "qb-main:abc123",
                "title": "Movie",
                "status": "processed",
                "detail_url_masked": "https://example.invalid/details/1",
                "payload": {"downloader": "qb-main", "info_hash": "abc123"},
            })

            archived = store.archive_rss_history_for_torrent("qb-main", "abc123")

            self.assertEqual(archived, 1)
            self.assertEqual(store.list_rss_history()["total"], 0)
            self.assertEqual(store.counts()["rss_history"], 0)
            self.assertEqual(
                store.find_rss_source_keys("task-a", ["source-a"]),
                {"source-a"},
            )
            self.assertEqual(
                store.find_rss_content_keys(["qb-main:abc123"]),
                {"qb-main:abc123"},
            )

    def test_clear_background_tasks_preserves_running_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "rssallinone.db")
            store.initialize()
            store.create_background_task("running", "rss_run")
            store.create_background_task("done", "rss_run")
            store.create_background_task("failed", "qb_refresh")
            store.finish_background_task("done", "succeeded")
            store.finish_background_task("failed", "failed", error_message="boom")

            result = store.clear_background_tasks()

            self.assertEqual(result, {"deleted": 2, "running": 1})
            self.assertEqual(store.list_background_tasks()["total"], 1)
            self.assertEqual(store.get_background_task("running")["state"], "running")

    def test_media_can_be_filtered_by_multiple_rss_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "rssallinone.db")
            store.initialize()
            for task_id in ("task-a", "task-b", "task-c"):
                store.upsert_media_item({
                    "id": f"media-{task_id}",
                    "state": "identified",
                    "title": task_id,
                    "details": {"import_control": {"task_id": task_id}},
                })

            result = store.list_media(rss_task_ids=["task-a", "task-c"])

            self.assertEqual(result["total"], 2)
            self.assertEqual(
                {item["title"] for item in result["items"]},
                {"task-a", "task-c"},
            )

    def test_clear_card_data_keeps_rss_configuration_and_resets_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "rssallinone.db")
            store.initialize()
            now = database.utc_now()
            store.replace_rss_tasks([{
                "id": "task-a",
                "name": "彩虹岛",
                "enabled": True,
                "position": 0,
                "config": {"qb_downloader": "qb-main", "qb_category": "chd"},
            }])
            store.upsert_media_item({
                "id": "media-a",
                "state": "identified",
                "title": "Movie",
                "details": {"import_control": {"task_id": "task-a"}},
            })
            with store.connection() as connection:
                connection.execute(
                    """INSERT INTO torrent_snapshots(
                        downloader_id, info_hash, name, state, category,
                        content_path, progress, size, present, details_json,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "qb-main", "abc123", "Movie", "downloading", "chd",
                        "/downloads/Movie.mkv", 0.5, 4, 1, "{}", now,
                    ),
                )
            store.upsert_rss_history({
                "task_id": "task-a",
                "source_key": "source-a",
                "content_key": "qb-main:abc123",
                "title": "Movie",
                "status": "processed",
                "payload": {
                    "info_hash": "abc123",
                    "completion_processed": True,
                    "imported_to_library": True,
                    "qb_delete": {"job_id": "qb-main:abc123"},
                },
            })
            store.schedule_qb_delete(
                task_id="task-a",
                task_name="彩虹岛",
                downloader_id="qb-main",
                info_hash="abc123",
                source_path="/SSD/QB目录/REMUX/CHD/Movie.mkv",
                delete_files=True,
                due_at="2026-08-05T00:00:00+00:00",
                details={"deletion_scope": "qb_task_and_save_path"},
            )

            counts = store.clear_card_data()

            self.assertEqual(counts["media"], 1)
            self.assertEqual(counts["torrents"], 1)
            self.assertEqual(store.list_media()["total"], 0)
            self.assertEqual(store.list_torrents()["total"], 0)
            self.assertEqual(store.list_rss_tasks()["total"], 1)
            self.assertEqual(counts["qb_delete_jobs"], 1)
            self.assertEqual(store.list_qb_delete_jobs(), [])
            history = store.latest_rss_history_for_torrent("qb-main", "abc123")
            self.assertEqual(history["status"], "queued")
            self.assertNotIn("completion_processed", history["payload"])
            self.assertNotIn("qb_delete", history["payload"])

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
            self.assertEqual(store.health()["schema_version"], 5)


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

    def test_chinese_dashboard_task_labels_and_dragon_branding(self) -> None:
        backend = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
        app_page = (
            PLUGIN_DIR / "src" / "components" / "AppPage.vue"
        ).read_text(encoding="utf-8")
        metadata = json.loads((ROOT / "package.v2.json").read_text(encoding="utf-8"))[
            PLUGIN_ID
        ]
        self.assertTrue((PLUGIN_DIR / "assets" / "dragon.svg").is_file())
        self.assertTrue((PLUGIN_DIR / "assets" / "dragon.png").is_file())
        self.assertIn('"icon": "tabler:dragon"', backend)
        self.assertIn('icon="tabler:dragon"', app_page)
        self.assertTrue(metadata["icon"].endswith("/assets/dragon.png"))
        self.assertLess(
            app_page.index("{ title: '文件管理', value: 'files'"),
            app_page.index("{ title: '入库管理', value: 'library'"),
        )
        for label in (
            "MoviePilot 本机能力",
            "CloudDrive2 上传监控",
            "下载完成回调闭环",
            "RSS 任务执行",
            "QB 刷新识别",
            "文件批量识别",
            "结果 / 错误",
        ):
            self.assertIn(label, app_page)

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
        self.assertIn("完成后创建实时硬链接", editor)
        self.assertIn("实时硬链接源根目录", editor)
        self.assertIn("mediaRssTaskIds", app_page)
        self.assertIn("label=\"RSS任务\"", app_page)
        self.assertIn("saveRssTasks", app_page)
        self.assertNotIn("电影目录组分类", config)
        self.assertNotIn("剧集目录组分类", config)
        self.assertNotIn("轮询兜底 CRON", editor)

    def test_library_filters_hide_internal_transition_states(self) -> None:
        app_page = (
            PLUGIN_DIR / "src" / "components" / "AppPage.vue"
        ).read_text(encoding="utf-8")
        self.assertNotIn("{ title: '已发现', value: 'discovered' }", app_page)
        self.assertNotIn("{ title: '入库中', value: 'importing' }", app_page)
        self.assertIn("{ title: '已回退', value: 'rolled_back' }", app_page)

    def test_file_manager_page_contract(self) -> None:
        app_page = (
            PLUGIN_DIR / "src" / "components" / "AppPage.vue"
        ).read_text(encoding="utf-8")
        browser = (
            PLUGIN_DIR / "src" / "components" / "FileManagerBrowser.vue"
        ).read_text(encoding="utf-8")
        self.assertIn("{ title: '文件管理', value: 'files'", app_page)
        self.assertIn("files/browse", browser)
        self.assertIn("files/recognize", browser)
        self.assertIn("files/recognize-batch", browser)
        self.assertIn("files/task", browser)
        self.assertIn("批量识别", browser)
        self.assertIn(">\n          识别\n", browser)
        self.assertNotIn("window.confirm", browser)
        self.assertNotIn("修改时间", browser)
        self.assertNotIn("文件大小", browser)

    def test_external_control_config_keeps_emby_and_sa_separate(self) -> None:
        config = (
            PLUGIN_DIR / "src" / "components" / "Config.vue"
        ).read_text(encoding="utf-8")
        app_page = (
            PLUGIN_DIR / "src" / "components" / "AppPage.vue"
        ).read_text(encoding="utf-8")
        self.assertIn("追更控制（Emby）", config)
        self.assertIn("外部扫库控制（SA）", config)
        self.assertIn("catchup_base_url", config)
        self.assertIn("scan_base_url", config)
        self.assertNotIn("external/catchup/control", config)
        self.assertNotIn("external/scan/control", config)
        self.assertIn("external/catchup/control", app_page)
        self.assertIn("external/scan/control", app_page)
        self.assertIn("追更", app_page)
        self.assertIn("扫库", app_page)
        self.assertIn("自动使用的本地硬链接根目录", config)
        self.assertNotIn('v-model="config.cd2_plugin_staging_root"', config)

    def test_qb_delete_button_preserves_downloaded_files(self) -> None:
        backend = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
        app_page = (
            PLUGIN_DIR / "src" / "components" / "AppPage.vue"
        ).read_text(encoding="utf-8")
        self.assertIn('self._api("/qb/delete"', backend)
        self.assertIn("deleteSelectedQbTasks", app_page)
        self.assertIn("删除任务", app_page)
        self.assertIn("保留已下载文件", app_page)

    def test_qb_refresh_preserves_rollback_marker(self) -> None:
        backend = (PLUGIN_DIR / "qb_sync.py").read_text(encoding="utf-8")
        self.assertIn(
            '"rolled_back": bool(existing_media.get("rolled_back"))',
            backend,
        )

    def test_rss_scheduler_uses_function_kwargs_for_task_id(self) -> None:
        backend = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('"func_kwargs": {"task_id": task_id}', backend)
        self.assertNotIn('"kwargs": {"task_id": task_id}', backend)

    def test_qb_callback_keeps_v1_and_moviepilot_node_names_separate(self) -> None:
        script = (
            PLUGIN_DIR / "qb_completed_notify.sh.example"
        ).read_text(encoding="utf-8")
        self.assertIn('DEFAULT_V1_NODE="QBSSD"', script)
        self.assertIn('DEFAULT_MP_DOWNLOADER="QB"', script)
        self.assertIn('--data-urlencode "node=$V1_NODE_NAME"', script)
        self.assertIn('"$HASH" "$MP_DOWNLOADER_ID"', script)


class PluginLifecycleTest(unittest.TestCase):
    def test_plugin_loads_inside_a_minimal_moviepilot_host(self) -> None:
        app = types.ModuleType("app")
        app.__path__ = []
        app_log = types.ModuleType("app.log")
        app_plugins = types.ModuleType("app.plugins")
        app_db = types.ModuleType("app.db")
        app_db.__path__ = []
        app_site_oper = types.ModuleType("app.db.site_oper")
        apscheduler = types.ModuleType("apscheduler")
        apscheduler.__path__ = []
        apscheduler_triggers = types.ModuleType("apscheduler.triggers")
        apscheduler_triggers.__path__ = []
        apscheduler_cron = types.ModuleType("apscheduler.triggers.cron")

        class Logger:
            @staticmethod
            def error(*_args, **_kwargs):
                return None

            info = error
            warning = error

        class CronTrigger:
            @staticmethod
            def from_crontab(value):
                return str(value)

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
            apscheduler_cron.CronTrigger = CronTrigger
            previous = {
                name: sys.modules.get(name)
                for name in (
                    "app", "app.log", "app.plugins", "app.db",
                    "app.db.site_oper", "apscheduler", "apscheduler.triggers",
                    "apscheduler.triggers.cron", "rssallinone",
                )
            }
            sys.modules["app"] = app
            sys.modules["app.log"] = app_log
            sys.modules["app.plugins"] = app_plugins
            sys.modules["app.db"] = app_db
            sys.modules["app.db.site_oper"] = app_site_oper
            sys.modules["apscheduler"] = apscheduler
            sys.modules["apscheduler.triggers"] = apscheduler_triggers
            sys.modules["apscheduler.triggers.cron"] = apscheduler_cron
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
                self.assertTrue(overview["plugin"]["rss_enabled"])
                self.assertTrue(overview["capabilities"]["hardlink_import"]["ready"])
                self.assertFalse(
                    overview["capabilities"]["hardlink_import"]["clouddrive_api"]
                )
                self.assertTrue(health["database"]["ready"])
                self.assertTrue((data_path / "rssallinone.db").is_file())
                self.assertEqual(plugin.get_sidebar_nav()[0]["nav_key"], "rssallinone")
                self.assertEqual(
                    plugin.get_sidebar_nav()[0]["icon"],
                    "tabler:dragon",
                )
                self.assertTrue(saved["success"])
                self.assertEqual(saved["items"][0]["config"]["qb_category"], "movie")
                self.assertEqual(
                    plugin._qb_scope().categories_for("qb-main"),
                    ["movie"],
                )
                paused = plugin.api_rss_control({"enabled": False})
                self.assertFalse(paused["enabled"])
                self.assertEqual(
                    plugin.api_rss_run({"task_id": "movies"})["message"],
                    "RSS 调度已暂停",
                )
                resumed = plugin.api_rss_control({"enabled": True})
                self.assertTrue(resumed["enabled"])
                self.assertTrue(sites["success"])
                self.assertEqual(sites["items"][0]["auth_mode"], "Cookie")
                self.assertNotIn("secret-cookie", repr(sites))
                api_paths = {item["path"] for item in plugin.get_api()}
                self.assertIn("/qb/completed", api_paths)
                self.assertIn("/qb/delete", api_paths)
                self.assertIn("/media/action", api_paths)
                self.assertIn("/media/refresh", api_paths)
                self.assertIn("/data/clear-cards", api_paths)
                self.assertIn("/tasks/clear", api_paths)
                self.assertIn("/external/catchup/control", api_paths)
                self.assertIn("/external/scan/control", api_paths)
                self.assertFalse(
                    plugin.api_external_catchup_control({"action": "invalid"})[
                        "success"
                    ]
                )
                self.assertFalse(
                    plugin.api_external_scan_control({"action": "invalid"})[
                        "success"
                    ]
                )
                self.assertEqual(
                    plugin._coerce_emby_callback_payload([
                        {"Event": "scheduledtasks.completed"}
                    ]),
                    {"Event": "scheduledtasks.completed"},
                )
                self.assertEqual(
                    plugin._coerce_emby_callback_payload(
                        '{"Event":"scheduledtasks.completed"}'
                    ),
                    {"Event": "scheduledtasks.completed"},
                )
                self.assertEqual(
                    plugin._coerce_emby_callback_payload(
                        "Event=scheduledtasks.completed&task_id=scan"
                    ),
                    {
                        "Event": "scheduledtasks.completed",
                        "task_id": "scan",
                    },
                )
                service_ids = {item["id"] for item in plugin.get_service()}
                self.assertIn("RssAllInOne.QbDeleteJobs", service_ids)
                self.assertNotIn("RssAllInOne.QbRefresh", service_ids)

                class MissingTorrentService:
                    @staticmethod
                    def find_torrent_downloader(_info_hash):
                        raise LookupError("不是 RSS 一条龙受管任务")

                original_service = plugin._qb_sync_service
                plugin._qb_sync_service = lambda: MissingTorrentService()
                ignored = plugin.api_qb_completed({"info_hash": "outside"})
                plugin._qb_sync_service = original_service
                self.assertTrue(ignored["success"])
                self.assertTrue(ignored["ignored"])

                class OutsideScopeService:
                    @staticmethod
                    def refresh_item(_downloader_id, _info_hash):
                        raise LookupError("该任务不属于任何已保存的 VT+ RSS 分类")

                plugin._qb_sync_service = lambda: OutsideScopeService()
                ignored_with_downloader = plugin.api_qb_completed({
                    "downloader_id": "qb-main",
                    "info_hash": "outside",
                })
                plugin._qb_sync_service = original_service
                self.assertTrue(ignored_with_downloader["success"])
                self.assertTrue(ignored_with_downloader["ignored"])

                plugin._store.upsert_torrent_snapshot({
                    "downloader_id": "qb-main",
                    "info_hash": "manual-delete-ok",
                    "name": "保留文件",
                    "state": "pausedDL",
                    "category": "movie",
                    "content_path": "/downloads/保留文件.mkv",
                    "progress": 0.5,
                    "size": 1024,
                    "source_url_masked": "",
                    "present": 1,
                    "recognition_state": "identified",
                    "inventory_state": "missing",
                    "media_title": "保留文件",
                    "media_type": "movie",
                    "media_year": "2026",
                    "poster": "",
                    "recognition_error": "",
                    "last_seen_at": database.utc_now(),
                    "updated_at": database.utc_now(),
                })
                plugin._store.upsert_torrent_snapshot({
                    "downloader_id": "qb-main",
                    "info_hash": "manual-delete-fail",
                    "name": "删除失败",
                    "state": "pausedDL",
                    "category": "movie",
                    "content_path": "/downloads/删除失败.mkv",
                    "progress": 0.5,
                    "size": 1024,
                    "source_url_masked": "",
                    "present": 1,
                    "recognition_state": "identified",
                    "inventory_state": "missing",
                    "media_title": "删除失败",
                    "media_type": "movie",
                    "media_year": "2026",
                    "poster": "",
                    "recognition_error": "",
                    "last_seen_at": database.utc_now(),
                    "updated_at": database.utc_now(),
                })
                manual_removed = []
                original_remove = module.MoviePilotQbGateway.remove_torrent
                try:
                    module.MoviePilotQbGateway.remove_torrent = staticmethod(
                        lambda downloader, info_hash, delete_files: (
                            manual_removed.append(
                                (downloader, info_hash, delete_files)
                            )
                            or info_hash == "manual-delete-ok"
                        )
                    )
                    manual_delete = plugin.api_qb_delete({
                        "items": [
                            {
                                "downloader_id": "qb-main",
                                "info_hash": "manual-delete-ok",
                            },
                            {
                                "downloader_id": "qb-main",
                                "info_hash": "manual-delete-fail",
                            },
                        ],
                    })
                    self.assertFalse(manual_delete["success"])
                    self.assertTrue(manual_delete["partial"])
                    self.assertEqual(manual_delete["succeeded"], 1)
                    self.assertEqual(manual_delete["failed"], 1)
                    self.assertEqual(
                        manual_removed,
                        [
                            ("qb-main", "manual-delete-ok", False),
                            ("qb-main", "manual-delete-fail", False),
                        ],
                    )
                    self.assertIsNone(plugin._store.get_torrent_snapshot(
                        "qb-main", "manual-delete-ok"
                    ))
                    self.assertIsNotNone(plugin._store.get_torrent_snapshot(
                        "qb-main", "manual-delete-fail"
                    ))
                    outside = plugin.api_qb_delete({
                        "items": [{
                            "downloader_id": "qb-main",
                            "info_hash": "not-a-card",
                        }],
                    })
                    self.assertFalse(outside["success"])
                    self.assertEqual(len(manual_removed), 2)
                finally:
                    module.MoviePilotQbGateway.remove_torrent = original_remove

                plugin._store.schedule_qb_delete(
                    task_id="movies",
                    task_name="彩虹岛",
                    downloader_id="qb-main",
                    info_hash="delete-me",
                    source_path="/SSD/QB目录/REMUX/CHD/Movie.mkv",
                    delete_files=True,
                    due_at="2020-01-01T00:00:00+00:00",
                    details={"deletion_scope": "qb_task_and_save_path"},
                )
                plugin._store.upsert_rss_history({
                    "task_id": "movies",
                    "source_key": "delete-source",
                    "content_key": "qb-main:delete-me",
                    "title": "Movie",
                    "status": "processed",
                    "payload": {"downloader": "qb-main", "info_hash": "delete-me"},
                })
                removed = []
                original_list = module.MoviePilotQbGateway.list_torrents
                original_dict = module.MoviePilotQbGateway.torrent_dict
                original_remove = module.MoviePilotQbGateway.remove_torrent
                try:
                    module.MoviePilotQbGateway.list_torrents = staticmethod(
                        lambda _downloader: [{
                            "hash": "delete-me",
                            "progress": 1.0,
                            "state": "pausedUP",
                        }]
                    )
                    module.MoviePilotQbGateway.torrent_dict = staticmethod(dict)
                    module.MoviePilotQbGateway.remove_torrent = staticmethod(
                        lambda downloader, info_hash, delete_files: removed.append(
                            (downloader, info_hash, delete_files)
                        ) or True
                    )
                    plugin._scheduled_qb_deletes()
                    self.assertEqual(
                        removed, [("qb-main", "delete-me", True)]
                    )
                    self.assertFalse(any(
                        item["info_hash"] == "delete-me"
                        for item in plugin._store.list_qb_delete_jobs()
                    ))
                    self.assertEqual(
                        plugin._store.list_rss_history()["total"], 0
                    )
                    self.assertEqual(
                        plugin._store.find_rss_source_keys(
                            "movies", ["delete-source"]
                        ),
                        {"delete-source"},
                    )

                    plugin._store.schedule_qb_delete(
                        task_id="movies",
                        task_name="彩虹岛",
                        downloader_id="qb-main",
                        info_hash="retry-me",
                        source_path="/SSD/QB目录/REMUX/CHD/Retry.mkv",
                        delete_files=True,
                        due_at="2020-01-01T00:00:00+00:00",
                    )
                    module.MoviePilotQbGateway.list_torrents = staticmethod(
                        lambda _downloader: [{
                            "hash": "retry-me",
                            "progress": 1.0,
                            "state": "pausedUP",
                        }]
                    )
                    module.MoviePilotQbGateway.remove_torrent = staticmethod(
                        lambda *_args: False
                    )
                    plugin._scheduled_qb_deletes()
                    retry_job = next(
                        item for item in plugin._store.list_qb_delete_jobs()
                        if item["info_hash"] == "retry-me"
                    )
                    self.assertEqual(retry_job["state"], "pending")
                    self.assertEqual(retry_job["attempts"], 1)
                    self.assertIn("qB 删除任务返回失败", retry_job["last_error"])
                finally:
                    module.MoviePilotQbGateway.list_torrents = original_list
                    module.MoviePilotQbGateway.torrent_dict = original_dict
                    module.MoviePilotQbGateway.remove_torrent = original_remove

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
