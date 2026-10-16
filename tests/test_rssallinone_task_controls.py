"""Failure retention and non-destructive card reclassification regressions."""

import importlib.util
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from test_rssallinone_inventory import database, file_manager, qb_sync


PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins.v2" / "rssallinone"


@contextmanager
def plugin_host(store):
    log = types.ModuleType("app.log")
    log.logger = mock.Mock()
    plugins = types.ModuleType("app.plugins")
    plugins._PluginBase = type("PluginBase", (), {})
    cron = types.ModuleType("apscheduler.triggers.cron")
    cron.CronTrigger = types.SimpleNamespace(from_crontab=lambda value: value)
    with mock.patch.dict(sys.modules, {
        "app": types.ModuleType("app"),
        "app.log": log,
        "app.plugins": plugins,
        "apscheduler": types.ModuleType("apscheduler"),
        "apscheduler.triggers": types.ModuleType("apscheduler.triggers"),
        "apscheduler.triggers.cron": cron,
    }):
        name = "rssallinone_task_controls_plugin"
        spec = importlib.util.spec_from_file_location(
            name, PLUGIN_DIR / "__init__.py",
            submodule_search_locations=[str(PLUGIN_DIR)],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        plugin = module.RssAllInOne()
        plugin._store = store
        plugin._enabled = True
        yield plugin


class TaskControlsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = database.SQLiteStore(Path(self.directory.name) / "state.db")
        self.store.initialize()

    def task(self, identity, state, *, old=False, result=None, failed=0):
        self.store.create_background_task(identity, "rss_run", state=state)
        if state not in {"running", "queued"}:
            self.store.finish_background_task(identity, state, result=result)
        self.store.update_background_task(identity, failed=failed)
        if old:
            old_time = (
                datetime.now(timezone.utc) - timedelta(days=4)
            ).isoformat(timespec="seconds")
            with self.store.write_connection() as connection:
                connection.execute(
                    """UPDATE background_tasks SET updated_at = ?, finished_at = ?
                       WHERE id = ?""",
                    (old_time, old_time, identity),
                )

    def media(self, *, identity="card", state="identified"):
        self.store.upsert_media_item({
            "id": identity,
            "state": state,
            "title": "Old Title",
            "source_name": "source.mkv",
            "source_path": str(Path(self.directory.name) / "source.mkv"),
            "downloader_id": "qb-main",
            "info_hash": "hash",
            "tmdb_id": 42,
            "season": 1,
            "media_type": "tv",
            "category": "series",
            "target_name": "Old Title/S01E01.mkv",
            "rolled_back": state == "rolled_back",
            "details": {
                "rss_source": {"detail_url_masked": "https://tracker.test/details.php?id=42"},
                "manual_override": {"tmdb_id": 42, "season": 1},
                "site_labels": {"mandarin": True, "effect": True, "torrent_id": "42"},
                "inventory_plan": {"expected_directory": "Old Title", "expected_files": []},
                "media": {"title": "Old Title", "tmdb_id": 42},
                "source_identity": {"kind": "qb_download"},
            },
        })
        return self.store.get_media_item(identity)

    def snapshot(self, downloader="qb-main"):
        now = database.utc_now()
        self.store.upsert_torrent_snapshot({
            "downloader_id": downloader, "info_hash": "hash",
            "name": "source", "state": "downloading", "category": "movie",
            "content_path": "/downloads/source", "progress": 0.5, "size": 4,
            "media_id": None, "source_url_masked": "https://tracker.test/details.php?id=42",
            "present": 1, "recognition_state": "identified", "inventory_state": "missing",
            "media_title": "Old Title", "media_type": "tv", "media_year": "2026",
            "tmdb_id": 42, "season": 1, "poster": "",
            "recognition_error": "", "recognized_at": now, "last_seen_at": now,
            "missing_since": None, "updated_at": now,
            "details": {"inventory_plan": {"expected_directory": "Old Title"}},
        })
        return self.store.get_torrent_snapshot(downloader, "hash")

    def test_failure_list_and_clear_keep_partial_errors(self):
        self.task("good", "succeeded")
        self.task("failed", "failed")
        self.task("partial", "partial")
        self.task("count-error", "succeeded", failed=1)
        self.task("payload-error", "succeeded", result={"failed": 1})
        self.task("list-error", "succeeded", result={"errors": [{"message": "rename failed"}]})
        self.task("running", "running", failed=1)
        expected = {"failed", "partial", "count-error", "payload-error", "list-error"}
        with plugin_host(self.store) as plugin:
            result = plugin.api_background_tasks()
            self.assertEqual({item["id"] for item in result["items"]}, expected)
            self.assertEqual(result["total"], 5)
            self.assertEqual(plugin.api_background_tasks(offset=1, limit=2)["total"], 5)
            self.assertEqual(len(plugin.api_background_tasks(offset=1, limit=2)["items"]), 2)
            cleared = plugin.api_clear_background_tasks()
            self.assertEqual(cleared["deleted"], 5)
            self.assertEqual(plugin.api_background_tasks()["total"], 0)
        self.assertIsNotNone(self.store.get_background_task("good"))
        self.assertIsNotNone(self.store.get_background_task("running"))

    def test_retention_is_bounded_and_preserves_failures_and_active_work(self):
        for identity, state in (
            ("good", "succeeded"), ("cancelled", "cancelled"),
            ("failed", "failed"), ("partial", "partial"),
            ("running", "running"), ("queued", "queued"),
        ):
            self.task(identity, state, old=True)
        self.task("recent", "succeeded")
        self.task("count-error", "succeeded", old=True, failed=1)
        self.task("payload-error", "succeeded", old=True, result={"failed": 1})
        self.task("list-error", "succeeded", old=True, result={"errors": [{"message": "error"}]})
        self.store.upsert_rss_history({
            "task_id": "rss", "source_key": "item", "title": "source", "status": "queued",
        })
        self.assertEqual(self.store.prune_background_tasks(batch_size=1), 1)
        self.assertEqual(self.store.prune_background_tasks(batch_size=1), 1)
        self.assertEqual(self.store.prune_background_tasks(batch_size=1), 0)
        for identity in (
            "failed", "partial", "running", "queued", "recent",
            "count-error", "payload-error", "list-error",
        ):
            self.assertIsNotNone(self.store.get_background_task(identity), identity)
        self.assertEqual(self.store.list_rss_history()["total"], 1)

    def test_daily_cleanup_is_registered_and_runs_without_opening_page(self):
        self.task("expired", "succeeded", old=True)
        self.task("failed", "failed", old=True)
        with plugin_host(self.store) as plugin:
            job = next(
                item for item in plugin.get_service()
                if item["id"] == "RssAllInOne.BackgroundTaskCleanup"
            )
            self.assertEqual(job["trigger"], "20 4 * * *")
            job["func"](**job["func_kwargs"])
        self.assertIsNone(self.store.get_background_task("expired"))
        self.assertIsNotNone(self.store.get_background_task("failed"))

    def test_move_only_changes_state_and_preserves_files_plans_and_source(self):
        for state in ("identified", "existing", "rolled_back"):
            with self.subTest(state=state):
                original = self.media(state=state)
                path = Path(original["source_path"])
                path.touch()
                self.store.replace_file_mappings("qb-main", "hash", [{
                    "media_id": "card", "current_source_path": str(path),
                    "local_hardlink_path": str(path.parent / "link.mkv"),
                }])
                mappings = self.store.list_file_mappings("qb-main", "hash")
                with plugin_host(self.store) as plugin:
                    result = plugin.api_mark_unidentified({"media_id": "card"})
                self.assertTrue(result["success"])
                updated = self.store.get_media_item("card")
                self.assertEqual(updated["state"], "unidentified")
                for key, value in original.items():
                    if key not in {"state", "updated_at", "details"}:
                        self.assertEqual(updated[key], value, key)
                self.assertEqual(updated["details"], {
                    **original["details"], "manual_unidentified": True,
                })
                self.assertEqual(self.store.list_file_mappings("qb-main", "hash"), mappings)
                self.assertTrue(path.is_file())
                self.assertEqual(self.store.list_media(state="unidentified")["total"], 1)
                self.assertEqual(self.store.list_media(state=state)["total"], 0)

    def test_qb_move_is_scoped_to_downloader_and_hash(self):
        original = self.snapshot()
        self.snapshot("other-qb")
        with plugin_host(self.store) as plugin:
            result = plugin.api_mark_unidentified({
                "downloader_id": "qb-main", "info_hash": "HASH",
            })
        self.assertTrue(result["success"])
        updated = self.store.get_torrent_snapshot("qb-main", "hash")
        self.assertEqual(updated["recognition_state"], "unidentified")
        self.assertEqual(updated["tmdb_id"], original["tmdb_id"])
        self.assertEqual(updated["source_url_masked"], original["source_url_masked"])
        self.assertEqual(updated["details"]["inventory_plan"], original["details"]["inventory_plan"])
        self.assertEqual(
            self.store.get_torrent_snapshot("other-qb", "hash")["recognition_state"], "identified"
        )

    def test_reject_active_or_imported_cards_and_stale_requests(self):
        for state in ("pending", "importing", "imported"):
            with self.subTest(state=state):
                original = self.media(state=state)
                with self.assertRaises(ValueError):
                    self.store.mark_unidentified(media_id="card")
                self.assertEqual(self.store.get_media_item("card"), original)
        self.media()
        for state in ("waiting_task", "watching", "waiting_library", "rolling_back"):
            self.store.upsert_import_watch({"id": "watch", "media_id": "card", "state": state})
            with self.subTest(watch_state=state), self.assertRaises(ValueError):
                self.store.mark_unidentified(media_id="card")
        with self.assertRaises(ValueError):
            self.store.mark_unidentified(media_id="missing")

    def test_qb_request_cannot_bypass_associated_import_protection(self):
        self.media(identity="qb:qb-main:hash", state="imported")
        self.snapshot()
        with self.assertRaises(ValueError):
            self.store.mark_unidentified(downloader_id="qb-main", info_hash="hash")
        self.assertEqual(
            self.store.get_torrent_snapshot("qb-main", "hash")["recognition_state"], "identified"
        )


class HeldQbCardTest(unittest.TestCase):
    setUp = TaskControlsTest.setUp

    class Gateway:
        def __init__(self):
            self.recognitions = 0
            self.raw = {
                "hash": "hash", "name": "Example.Movie.2026",
                "content_path": "/downloads/Example.Movie.2026.mkv",
                "category": "movie", "progress": 0.5, "size": 4, "state": "downloading",
            }
            self.media = types.SimpleNamespace(
                tmdb_id=42, title="Example Movie", year="2026", season=None, category="movie",
            )

        def list_downloaders(self):
            return [qb_sync.DownloaderView(
                name="qb-main", type="qbittorrent", enabled=True, default=True, ready=True,
            )]

        def list_torrents(self, _downloader):
            return [self.raw]

        def recognize(self, _title):
            self.recognitions += 1
            return types.SimpleNamespace(begin_season=None), self.media

        def restore_media(self, _payload):
            return self.media

        def restore_meta(self, _title, _payload):
            return types.SimpleNamespace(begin_season=None)

        def recognize_manual(self, title, _media_type, tmdb_id, _season):
            self.media.tmdb_id = tmdb_id
            return self.recognize(title)

        torrent_dict = staticmethod(dict)
        media_type = staticmethod(lambda _media: "movie")
        media_payload = staticmethod(vars)
        meta_payload = staticmethod(vars)
        poster = staticmethod(lambda _media: "")
        list_torrent_files = staticmethod(lambda *_args: [])
        plan_inventory_files = staticmethod(lambda *_args, **_kwargs: {
            "expected_files": [], "expected_directory": "Example Movie",
        })

    def service(self):
        self.store.replace_rss_tasks([{
            "id": "rss", "name": "rss", "enabled": True,
            "config": {"qb_downloader": "qb-main", "qb_category": "movie", "import_enabled": True},
        }])
        gateway = self.Gateway()
        return qb_sync.QbSyncService(store=self.store, gateway=gateway), gateway

    def test_automatic_refresh_keeps_held_card_and_manual_identification_releases(self):
        service, gateway = self.service()
        service.refresh_item("qb-main", "hash")
        self.store.mark_unidentified(downloader_id="qb-main", info_hash="hash")
        service._sync_one(
            downloader=gateway.list_downloaders()[0],
            raw=gateway.raw, force_recognition=False,
        )
        refreshed = self.store.get_torrent_snapshot("qb-main", "hash")
        self.assertEqual(refreshed["recognition_state"], "unidentified")
        self.assertTrue(refreshed["details"]["manual_unidentified"])
        self.assertEqual(gateway.recognitions, 1)
        identified = service.refresh_item(
            "qb-main", "hash", manual_override={"media_type": "movie", "tmdb_id": 99},
        )
        self.assertEqual(identified["recognition_state"], "identified")
        self.assertEqual(identified["tmdb_id"], 99)
        self.assertNotIn("manual_unidentified", identified["details"])

    def test_completion_moves_held_card_to_unidentified_not_identified(self):
        service, gateway = self.service()
        service.refresh_item("qb-main", "hash")
        self.store.mark_unidentified(downloader_id="qb-main", info_hash="hash")
        gateway.raw.update({"progress": 1, "state": "uploading"})
        service.refresh_item("qb-main", "hash", completion_confirmed=True)
        item = self.store.get_media_item("qb:qb-main:hash")
        self.assertEqual(item["state"], "unidentified")
        self.assertTrue(item["details"]["manual_unidentified"])
        self.assertEqual(item["tmdb_id"], 42)

    def test_explicit_refresh_can_release_hold(self):
        service, _gateway = self.service()
        service.refresh_item("qb-main", "hash")
        self.store.mark_unidentified(downloader_id="qb-main", info_hash="hash")
        refreshed = service.refresh_item("qb-main", "hash", release_unidentified=True)
        self.assertEqual(refreshed["recognition_state"], "identified")
        self.assertNotIn("manual_unidentified", refreshed["details"])

    def test_local_card_can_be_manually_identified_without_losing_p_link(self):
        _service, gateway = self.service()
        path = Path(self.directory.name) / "Example.Movie.2026.mkv"
        path.touch()
        service = file_manager.LocalFileManagerService(self.store, gateway=gateway)
        item = service.recognize_entry(path)["item"]
        item["details"]["rss_source"] = {
            "detail_url_masked": "https://tracker.test/details.php?id=42",
        }
        self.store.upsert_media_item(item)
        self.store.mark_unidentified(media_id=item["id"])
        refreshed = service.recognize_entry(
            path, refresh_media_id=item["id"],
            manual_override={"media_type": "movie", "tmdb_id": 99},
        )["item"]
        self.assertEqual(refreshed["state"], "identified")
        self.assertEqual(refreshed["tmdb_id"], 99)
        self.assertNotIn("manual_unidentified", refreshed["details"])
        self.assertEqual(refreshed["details"]["rss_source"], item["details"]["rss_source"])


if __name__ == "__main__":
    unittest.main()
