"""Pending-import queue behavior with fake CloudDrive2 and external controls."""

import importlib.util
import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v2" / "rssallinone"
PACKAGE = "rssallinone_pending_test"


def load_module(module_name, filename):
    full_name = f"{PACKAGE}.{module_name}"
    spec = importlib.util.spec_from_file_location(full_name, PLUGIN_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


package = types.ModuleType(PACKAGE)
package.__path__ = [str(PLUGIN_DIR)]
sys.modules[PACKAGE] = package
database = load_module("database", "database.py")
load_module("domain", "domain.py")
media_actions = load_module("media_actions", "media_actions.py")
load_module("clouddrive_client", "clouddrive_client.py")
external_controls = load_module("external_controls", "external_controls.py")
pending_import = load_module("pending_import", "pending_import.py")


class FakeLogger:
    def error(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None


class FakeControls:
    ready = True

    def __init__(self):
        self.disabled = 0
        self.restored = 0

    def snapshot_and_disable(self):
        self.disabled += 1
        return external_controls.ExternalSwitchSnapshot(True, True)

    def restore(self, snapshot):
        self.restored += 1
        self.snapshot = snapshot


class FakeScanner:
    def __init__(self):
        self.refreshes = 0

    def request_emby_refresh(self):
        self.refreshes += 1
        return {"host": "http://emby", "node_name": "Emby01", "server_id": "srv1"}


class FakeCd2:
    ready = True

    def __init__(self, upload):
        self.upload = upload
        self.calls = 0
        self.paused = []
        self.cancelled = []

    def list_uploads(self):
        self.calls += 1
        return [] if self.calls == 1 else [dict(self.upload)]

    def pause(self, keys):
        self.paused.extend(keys)

    def cancel(self, keys):
        self.cancelled.extend(keys)


class PendingImportTest(unittest.TestCase):
    def make_store(self, directory, *, size=1024):
        root = Path(directory)
        source = root / "source" / "Movie.mkv"
        target = root / "staging" / "Movie" / "Movie.mkv"
        inventory = root / "library" / "Movie" / "Movie.strm"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"x" * size)
        store = database.SQLiteStore(root / "state.db")
        store.initialize()
        store.upsert_media_item({
            "id": "media-1",
            "state": "pending",
            "media_type": "movie",
            "title": "Movie",
            "source_name": "Movie.mkv",
            "source_path": str(source),
            "downloader_id": "qb",
            "info_hash": "abc",
            "category": "外语电影",
        })
        store.replace_file_mappings("qb", "abc", [{
            "file_index": 0,
            "media_id": "media-1",
            "current_source_path": str(source),
            "local_hardlink_path": str(target),
            "inventory_path": str(inventory),
            "file_size": size,
            "inventory_exists": False,
        }])
        return store, source, target, inventory

    def coordinator(self, store, staging_root, cd2, controls, scanner):
        return pending_import.PendingImportCoordinator(
            store=store,
            config=pending_import.PendingImportConfig(
                plugin_staging_root=str(staging_root),
                cd2_dest_root="/cloud",
                discovery_timeout=2,
                card_timeout=3,
                poll_interval=2,
                scan_callback_timeout=30,
                callback_server_id="srv1",
                callback_task_id="task1",
            ),
            cd2=cd2,
            controls=controls,
            scanner=scanner,
            stop_event=threading.Event(),
            logger=FakeLogger(),
        )

    def test_success_waits_for_scan_callback_before_restoring_switches(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, target, _inventory = self.make_store(directory)
            controls = FakeControls()
            scanner = FakeScanner()
            cd2 = FakeCd2({
                "key": "upload-1",
                "dest_path": "/cloud/Movie/Movie.mkv",
                "size": 1024,
                "transferred_bytes": 0,
                "status": "Finish",
                "error_message": "",
            })
            coordinator = self.coordinator(
                store, Path(directory) / "staging", cd2, controls, scanner
            )

            coordinator.run("manual")

            batch = store.latest_active_import_batch()
            self.assertEqual(batch["state"], "waiting_scan_callback")
            self.assertEqual(store.get_media_item("media-1")["state"], "imported")
            self.assertTrue(target.exists())
            self.assertEqual(controls.disabled, 1)
            self.assertEqual(controls.restored, 0)
            self.assertEqual(scanner.refreshes, 1)

            result = coordinator.handle_scan_callback({
                "event_name": "scheduledtasks.completed",
                "server_id": "srv1",
                "task_id": "task1",
            })
            self.assertTrue(result["accepted"])
            self.assertEqual(controls.restored, 1)
            self.assertIsNone(store.latest_active_import_batch())

    def test_real_transfer_rolls_back_only_the_new_hardlink(self):
        with tempfile.TemporaryDirectory() as directory:
            size = 10 * 1024 * 1024
            store, source, target, _inventory = self.make_store(directory, size=size)
            controls = FakeControls()
            scanner = FakeScanner()
            cd2 = FakeCd2({
                "key": "upload-2",
                "dest_path": "/cloud/Movie/Movie.mkv",
                "size": size,
                "transferred_bytes": 9 * 1024 * 1024,
                "status": "Transfer",
                "error_message": "",
            })
            coordinator = self.coordinator(
                store, Path(directory) / "staging", cd2, controls, scanner
            )

            coordinator.run("manual")

            item = store.get_media_item("media-1")
            self.assertEqual(item["state"], "identified")
            self.assertEqual(item["failure_code"], "cd2_monitor_failed")
            self.assertTrue(source.exists())
            self.assertFalse(target.exists())
            self.assertEqual(cd2.paused, ["upload-2"])
            self.assertEqual(cd2.cancelled, ["upload-2"])
            self.assertEqual(controls.restored, 1)
            self.assertEqual(scanner.refreshes, 0)

    def test_risk_control_pauses_batch_without_restoring_switches(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, target, _inventory = self.make_store(directory)
            controls = FakeControls()
            scanner = FakeScanner()
            cd2 = FakeCd2({
                "key": "upload-3",
                "dest_path": "/cloud/Movie/Movie.mkv",
                "size": 1024,
                "transferred_bytes": 0,
                "status": "FatalError",
                "error_message": "Forbidden: risk control",
            })
            coordinator = self.coordinator(
                store, Path(directory) / "staging", cd2, controls, scanner
            )

            coordinator.run("manual")

            batch = store.latest_active_import_batch()
            self.assertEqual(batch["state"], "paused_risk")
            self.assertIsNotNone(batch["resume_at"])
            self.assertEqual(store.get_media_item("media-1")["state"], "identified")
            self.assertFalse(target.exists())
            self.assertEqual(controls.restored, 0)
            self.assertEqual(scanner.refreshes, 0)


class FakeExternalHttp:
    def __init__(self):
        self.catchup = True
        self.catchup_saved_object = None
        self.scan_switch = True
        self.refreshes = 0

    def request(self, method, url, **kwargs):
        if url.endswith("/api/v1/login/access-token"):
            return 200, {"access_token": "jwt"}
        if "/emby/UI/View?" in url:
            return 200, {
                "PageId": "page1",
                "PluginId": "plugin1",
                "EditObjectContainer": {
                    "Object": {
                        "GeneralOptions": {"CatchupMode": self.catchup},
                        "Other": {"preserved": True},
                    },
                },
            }
        if "/emby/UI/Command?" in url:
            body = kwargs["json_body"]
            self.catchup_saved_object = json.loads(body["Data"])
            self.catchup = bool(
                self.catchup_saved_object["GeneralOptions"]["CatchupMode"]
            )
            return 204, None
        if "/api/v1/system/settings/" in url:
            return 200, [{
                "name": "Emby01",
                "switch": self.scan_switch,
                "host": "http://emby",
                "api_key": "key",
            }]
        if url.endswith("/api/v1/system/save_settings"):
            row = kwargs["json_body"]["settings"][0]
            self.scan_switch = bool(row["switch"])
            return 200, {"success": True}
        if "/emby/Library/Refresh?" in url:
            self.refreshes += 1
            return 204, None
        raise AssertionError(f"unexpected request: {method} {url}")


class ExternalControlTest(unittest.TestCase):
    def test_switch_clients_preserve_full_objects_and_verify_changes(self):
        http = FakeExternalHttp()
        catchup = external_controls.CatchupSwitchClient(
            "http://emby", "page1", "token", http=http
        )
        scanner = external_controls.ScanSystemClient(
            "http://scan", "user", "pass", "nodes", "Emby01", http=http
        )

        self.assertFalse(catchup.set_enabled(False))
        self.assertTrue(http.catchup_saved_object["Other"]["preserved"])
        self.assertFalse(scanner.set_enabled(False))
        target = scanner.request_emby_refresh()
        self.assertEqual(target["node_name"], "Emby01")
        self.assertEqual(http.refreshes, 1)


if __name__ == "__main__":
    unittest.main()
