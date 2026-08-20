"""Editable VT+ RSS task persistence tests."""

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v2" / "rssallinone"
PACKAGE = "rssallinone_rss_task_tests"


def load_package_module(name: str):
    package = sys.modules.get(PACKAGE)
    if package is None:
        package = types.ModuleType(PACKAGE)
        package.__path__ = [str(PLUGIN_DIR)]
        sys.modules[PACKAGE] = package
    module_name = f"{PACKAGE}.{name}"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PLUGIN_DIR / f"{name}.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


database = load_package_module("database")
rss_tasks = load_package_module("rss_tasks")


class RssTaskContractTest(unittest.TestCase):
    def test_normalization_adds_defaults_and_preserves_extensions(self) -> None:
        tasks = rss_tasks.normalize_rss_tasks([{
            "id": "task 1",
            "name": "  电影任务  ",
            "enabled": "true",
            "config": {
                "qb_downloader": " qb-main ",
                "qb_category": " movie ",
                "delete_after_minutes": -1,
                "realtime_hardlink_enabled": "true",
                "realtime_source_root": " /SSD/QB目录/REMUX/CHD ",
                "realtime_link_root": " /SSD/QB目录/REMUX/CHDlink ",
                "extension_value": {"keep": True},
            },
        }])
        task = tasks[0]
        self.assertEqual(task["id"], "task-1")
        self.assertEqual(task["name"], "电影任务")
        self.assertEqual(task["config"]["qb_downloader"], "qb-main")
        self.assertEqual(task["config"]["qb_category"], "movie")
        self.assertEqual(task["config"]["delete_after_minutes"], 0)
        self.assertFalse(task["config"]["hr_enabled"])
        self.assertEqual(task["config"]["hr_cron"], "30 3 * * *")
        self.assertTrue(task["config"]["pause_on_add"])
        self.assertTrue(task["config"]["realtime_hardlink_enabled"])
        self.assertEqual(
            task["config"]["realtime_source_root"],
            "/SSD/QB目录/REMUX/CHD",
        )
        self.assertEqual(
            task["config"]["realtime_link_root"],
            "/SSD/QB目录/REMUX/CHDlink",
        )
        self.assertNotIn("path_mappings", task["config"])
        self.assertEqual(task["config"]["extension_value"], {"keep": True})

    def test_duplicate_ids_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            rss_tasks.normalize_rss_tasks([
                {"id": "same", "name": "A"},
                {"id": "same", "name": "B"},
            ])

    def test_duplicate_qb_downloader_category_pairs_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "相同的 QB 节点和分类"):
            rss_tasks.normalize_rss_tasks([
                {
                    "id": "one",
                    "name": "电影 RSS",
                    "config": {
                        "qb_downloader": "QB01",
                        "qb_category": "电影",
                    },
                },
                {
                    "id": "two",
                    "name": "备用 RSS",
                    "config": {
                        "qb_downloader": "qb01",
                        "qb_category": "电影",
                    },
                },
            ])

    def test_replace_is_ordered_and_removes_deleted_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "state.db")
            store.initialize()
            first = rss_tasks.normalize_rss_tasks([
                {
                    "id": "one",
                    "name": "电影",
                    "config": {
                        "qb_downloader": "qb-main",
                        "qb_category": "movie",
                    },
                },
                {"id": "two", "name": "剧集"},
            ])
            saved = store.replace_rss_tasks(first)
            created_at = saved[0]["created_at"]

            second = rss_tasks.normalize_rss_tasks([{
                **saved[0],
                "name": "电影更新",
            }])
            saved = store.replace_rss_tasks(second)

            self.assertEqual([item["id"] for item in saved], ["one"])
            self.assertEqual(saved[0]["name"], "电影更新")
            self.assertEqual(saved[0]["created_at"], created_at)
            self.assertEqual(saved[0]["config"]["qb_category"], "movie")


if __name__ == "__main__":
    unittest.main()
