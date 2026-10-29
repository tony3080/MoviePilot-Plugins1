"""Editable VT+ RSS task persistence tests."""

import importlib.util
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

# Other host tests install scheduler stubs; use the real triggers in isolation.
with patch.dict(sys.modules):
    for module_name in list(sys.modules):
        if module_name == "apscheduler" or module_name.startswith("apscheduler."):
            del sys.modules[module_name]
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    SCHEDULER_MODULES = {
        name: module for name, module in sys.modules.items()
        if name == "apscheduler" or name.startswith("apscheduler.")
    }


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
    def setUp(self) -> None:
        scheduler_modules = patch.dict(sys.modules, SCHEDULER_MODULES)
        scheduler_modules.start()
        self.addCleanup(scheduler_modules.stop)

    def test_numeric_schedule_preserves_minutes_in_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "state.db")
            store.initialize()
            for value in (19, " 19 "):
                with self.subTest(value=value):
                    tasks = rss_tasks.normalize_rss_tasks([{
                        "id": "interval",
                        "config": {"rss_cron": value},
                    }])
                    store.replace_rss_tasks(tasks)
                    config = store.list_all_rss_tasks()[0]["config"]
                    self.assertEqual(config["rss_cron"], "19")
                    self.assertEqual(config["start_cron"], "*/5 * * * *")
                    self.assertEqual(config["hr_cron"], "30 3 * * *")
                    trigger = rss_tasks.build_rss_trigger(config["rss_cron"])
                    self.assertIsInstance(trigger, IntervalTrigger)
                    self.assertEqual(trigger.interval, timedelta(minutes=19))

    def test_interval_continues_across_hour_boundary(self) -> None:
        before = datetime.now(timezone.utc)
        trigger = rss_tasks.build_rss_trigger("19")
        after = datetime.now(timezone.utc)
        first = trigger.get_next_fire_time(None, after)
        self.assertGreaterEqual(first, before + timedelta(minutes=19))
        self.assertLessEqual(first, after + timedelta(minutes=19))
        previous = datetime(2026, 10, 26, 8, 57, tzinfo=trigger.timezone)
        next_fire = trigger.get_next_fire_time(previous, previous)
        self.assertEqual(next_fire, previous + timedelta(minutes=19))
        self.assertEqual((next_fire.hour, next_fire.minute), (9, 16))

    def test_cron_retains_hour_boundary_behavior(self) -> None:
        value = "*/19 * * * *"
        tasks = rss_tasks.normalize_rss_tasks([{"config": {"rss_cron": value}}])
        self.assertEqual(tasks[0]["config"]["rss_cron"], value)
        trigger = rss_tasks.build_rss_trigger(value)
        self.assertIsInstance(trigger, CronTrigger)
        previous = datetime(2026, 10, 26, 8, 57, tzinfo=trigger.timezone)
        next_fire = trigger.get_next_fire_time(previous, previous)
        self.assertEqual((next_fire.hour, next_fire.minute), (9, 0))

    def test_invalid_minutes_are_rejected_and_empty_schedule_is_preserved(self) -> None:
        for value in (0, "0", "-19", "1.5", "nineteen"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "正整数"):
                rss_tasks.normalize_rss_tasks([{"config": {"rss_cron": value}}])
        tasks = rss_tasks.normalize_rss_tasks([{"config": {"rss_cron": ""}}])
        self.assertEqual(tasks[0]["config"]["rss_cron"], "")
        with self.assertRaises(ValueError):
            rss_tasks.build_rss_trigger("*/61 * * * *")

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
