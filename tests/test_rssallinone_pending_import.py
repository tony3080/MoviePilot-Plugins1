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
        self.snapshots = 0
        self.disabled = 0
        self.restored = 0

    def snapshot(self):
        self.snapshots += 1
        return external_controls.ExternalSwitchSnapshot(True, True)

    def disable(self, snapshot=None):
        self.disabled += 1

    def snapshot_and_disable(self):
        snapshot = self.snapshot()
        self.disable(snapshot)
        return snapshot

    def ensure_disabled(self):
        self.disabled += 1

    def restore(self, snapshot):
        self.restored += 1
        self.snapshot = snapshot


class FakeScanner:
    ready = True

    def __init__(self):
        self.refreshes = 0
        self.post_scan_tasks = []
        self.status_calls = 0
        self.task_status = {
            "host": "http://emby",
            "node_name": "Emby01",
            "server_id": "srv1",
            "task_id": "task1",
            "task_name": "Scan media library",
            "task_key": "RefreshLibrary",
            "state": "Idle",
            "is_running": False,
            "progress": None,
            "last_status": "",
            "last_started_at": "",
            "last_finished_at": "",
        }

    def request_emby_refresh(self):
        self.refreshes += 1
        return {
            "host": "http://emby",
            "node_name": "Emby01",
            "server_id": "srv1",
            "task_id": "task1",
            "task_name": "Scan media library",
        }

    def emby_task_status(self, _task_id="", _task_name=""):
        self.status_calls += 1
        return dict(self.task_status)

    def start_emby_task(self, task_name):
        self.post_scan_tasks.append(task_name)
        return {"task_id": "post-scan", "task_name": task_name, "status": "started"}


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

    def find_file(self, _path, *, force_refresh=False):
        return None

    def find_files(self, paths, *, force_refresh=False):
        return {
            pending_import._normalized_path(path): self.find_file(
                path, force_refresh=force_refresh
            )
            for path in paths
        }

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

    def test_multiple_staging_roots_share_one_cd2_destination_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            movie_root = base / "movie"
            series_root = base / "series"
            target = series_root / "国产剧" / "Show" / "Episode.mkv"
            target.parent.mkdir(parents=True)
            target.touch()
            coordinator = pending_import.PendingImportCoordinator(
                store=object(),
                config=pending_import.PendingImportConfig(
                    plugin_staging_roots=[str(movie_root), str(series_root)],
                    cd2_dest_root="/cloud/library",
                    callback_server_id="srv1",
                    callback_task_id="task1",
                ),
                cd2=object(),
                controls=object(),
                scanner=object(),
                stop_event=threading.Event(),
                logger=FakeLogger(),
            )

            self.assertEqual(
                coordinator._cd2_dest_path(str(target)),
                "/cloud/library/国产剧/Show/Episode.mkv",
            )

    def test_cd2_destination_root_uses_api_path_resolved_by_client(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "series"
            target = root / "Show" / "Episode.mkv"
            target.parent.mkdir(parents=True)
            target.touch()

            class ResolvingCd2:
                def resolve_destination_root(self, configured):
                    self.configured = configured
                    return "/115/library"

            cd2 = ResolvingCd2()
            coordinator = pending_import.PendingImportCoordinator(
                store=object(),
                config=pending_import.PendingImportConfig(
                    plugin_staging_root=str(root),
                    cd2_dest_root="/SSD/CloudDrive/115/library",
                    callback_server_id="srv1",
                    callback_task_id="task1",
                ),
                cd2=cd2,
                controls=object(),
                scanner=object(),
                stop_event=threading.Event(),
                logger=FakeLogger(),
            )

            self.assertEqual(
                coordinator._cd2_dest_path(str(target)),
                "/115/library/Show/Episode.mkv",
            )
            self.assertEqual(cd2.configured, "/SSD/CloudDrive/115/library")

    def test_paused_upload_with_transferred_bytes_is_real_transfer(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, _target, _inventory = self.make_store(directory)
            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                FakeCd2({}),
                FakeControls(),
                FakeScanner(),
            )
            coordinator.config.transfer_grace = 0
            watch = {
                "id": "watch-1",
                "batch_id": "batch-1",
                "media_id": "media-1",
                "state": "watching",
                "expected_cd2_dest_path": "/cloud/Movie/Movie.mkv",
                "cd2_key": "upload-1",
                "file_size": 1024 * 1024 * 1024,
                "transferred_bytes": 0,
                "details": {},
                "created_at": database.utc_now(),
                "updated_at": database.utc_now(),
            }
            task = {
                "key": "upload-1",
                "dest_path": "/cloud/Movie/Movie.mkv",
                "size": watch["file_size"],
                "transferred_bytes": 1024,
                "status": "Pause",
                "error_message": "",
            }

            result = coordinator._observe_watch(
                watch, [task], {"upload-1": task}
            )

            self.assertTrue(result.startswith("failed:CD2 已进入真实传输"))

    def test_disappeared_baseline_transfer_cannot_be_cloud_file_success(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, _target, _inventory = self.make_store(directory)
            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                FakeCd2({}),
                FakeControls(),
                FakeScanner(),
            )
            watch = {
                "id": "watch-1",
                "batch_id": "batch-1",
                "media_id": "media-1",
                "state": "waiting_task",
                "expected_cd2_dest_path": "/cloud/Movie/Movie.mkv",
                "cd2_key": "",
                "file_size": 1024 * 1024 * 1024,
                "transferred_bytes": 0,
                "details": {
                    "baseline_keys": ["old-upload"],
                    "baseline_tasks": {
                        "old-upload": {
                            "dest_path": "/cloud/Movie/Movie.mkv",
                            "size": 1024 * 1024 * 1024,
                            "transferred_bytes": 512 * 1024 * 1024,
                            "status": "pause",
                            "error_message": "",
                        }
                    },
                },
                "created_at": database.utc_now(),
                "updated_at": database.utc_now(),
            }

            result = coordinator._observe_watch(
                watch,
                [],
                {},
                cloud_results={
                    pending_import._normalized_path(
                        watch["expected_cd2_dest_path"]
                    ): {
                        "id": "preallocated-cloud-file",
                        "name": "Movie.mkv",
                        "full_path": "/cloud/Movie/Movie.mkv",
                        "size": watch["file_size"],
                        "is_directory": False,
                    }
                },
            )

            self.assertTrue(result.startswith("failed:CD2 旧上传任务已发生真实传输"))
            self.assertEqual(watch["state"], "rolling_back")

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

            coordinator.run("cron")

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
            self.assertEqual(scanner.post_scan_tasks, ["Extract MediaInfo"])
            self.assertIsNone(store.latest_active_import_batch())

    def test_manual_run_skips_external_switches_but_still_refreshes_emby(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, target, _inventory = self.make_store(directory)
            controls = FakeControls()
            controls.ready = False
            scanner = FakeScanner()
            cd2 = FakeCd2({
                "key": "upload-manual",
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
            batch_id = batch["id"]
            self.assertEqual(batch["state"], "waiting_scan_callback")
            self.assertFalse(batch["details"]["manage_external_switches"])
            self.assertIsNone(batch["original_catchup_enabled"])
            self.assertIsNone(batch["original_scan_enabled"])
            self.assertEqual(store.get_media_item("media-1")["state"], "imported")
            self.assertTrue(target.exists())
            self.assertEqual(controls.snapshots, 0)
            self.assertEqual(controls.disabled, 0)
            self.assertEqual(controls.restored, 0)
            self.assertEqual(scanner.refreshes, 1)

            result = coordinator.handle_scan_callback({
                "event_name": "scheduledtasks.completed",
                "server_id": "srv1",
                "task_id": "task1",
            })

            self.assertTrue(result["accepted"])
            self.assertEqual(result["message"], "扫库完成回调已确认")
            self.assertEqual(controls.restored, 0)
            finished = store.get_import_batch(batch_id)
            self.assertEqual(finished["state"], "completed")
            self.assertIn("switch_restore_skipped_at", finished["details"])

    def test_scan_wait_can_be_cancelled_without_rolling_back_import(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, target, _inventory = self.make_store(directory)
            controls = FakeControls()
            scanner = FakeScanner()
            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                FakeCd2({
                    "key": "upload-cancel-wait",
                    "dest_path": "/cloud/Movie/Movie.mkv",
                    "size": 1024,
                    "transferred_bytes": 0,
                    "status": "Finish",
                    "error_message": "",
                }),
                controls,
                scanner,
            )

            coordinator.run("cron")
            batch = store.latest_active_import_batch()
            self.assertEqual(batch["state"], "waiting_scan_callback")

            result = coordinator.cancel_scan_wait()

            self.assertTrue(result["accepted"])
            self.assertEqual(controls.restored, 1)
            self.assertEqual(store.get_media_item("media-1")["state"], "imported")
            self.assertTrue(target.exists())
            self.assertIsNone(store.latest_active_import_batch())
            finished = store.get_import_batch(batch["id"])
            self.assertEqual(finished["state"], "cancelled")
            self.assertIn("scan_wait_cancelled_at", finished["details"])
            self.assertEqual(scanner.post_scan_tasks, [])

    def test_identifierless_scan_callback_confirms_completed_task_via_emby_api(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, _target, _inventory = self.make_store(directory)
            controls = FakeControls()
            scanner = FakeScanner()
            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                FakeCd2({
                    "key": "upload-identifierless-callback",
                    "dest_path": "/cloud/Movie/Movie.mkv",
                    "size": 1024,
                    "transferred_bytes": 0,
                    "status": "Finish",
                    "error_message": "",
                }),
                controls,
                scanner,
            )

            coordinator.run("cron")
            batch = store.latest_active_import_batch()
            requested_at = pending_import._parse_time(batch["refresh_requested_at"])
            scanner.task_status.update({
                "state": "Idle",
                "is_running": False,
                "last_status": "Completed",
                "last_started_at": (
                    requested_at + pending_import.timedelta(seconds=1)
                ).isoformat(),
                "last_finished_at": (
                    requested_at + pending_import.timedelta(minutes=1)
                ).isoformat(),
            })

            result = coordinator.handle_scan_callback({
                "event_name": "scheduledtasks.completed",
            })

            self.assertTrue(result["accepted"])
            self.assertEqual(scanner.status_calls, 1)
            self.assertIsNone(store.latest_active_import_batch())
            finished = store.get_import_batch(batch["id"])
            self.assertIn("scan_callback_api_confirmation", finished["details"])

    def test_identifierless_callback_does_not_finish_unconfirmed_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, _target, _inventory = self.make_store(directory)
            controls = FakeControls()
            scanner = FakeScanner()
            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                FakeCd2({
                    "key": "upload-unconfirmed-callback",
                    "dest_path": "/cloud/Movie/Movie.mkv",
                    "size": 1024,
                    "transferred_bytes": 0,
                    "status": "Finish",
                    "error_message": "",
                }),
                controls,
                scanner,
            )

            coordinator.run("cron")

            result = coordinator.handle_scan_callback({
                "event_name": "scheduledtasks.completed",
            })

            self.assertFalse(result["accepted"])
            self.assertEqual(scanner.status_calls, 1)
            self.assertIsNotNone(store.latest_active_import_batch())

    def test_completed_upload_missing_from_task_list_uses_cloud_file(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, target, _inventory = self.make_store(directory)

            class InstantCloudCd2(FakeCd2):
                def __init__(self):
                    super().__init__({})
                    self.file_calls = 0

                def list_uploads(self):
                    return []

                def find_file(self, path, *, force_refresh=False):
                    self.file_calls += 1
                    if self.file_calls == 1:
                        return None
                    return {
                        "id": "cloud-file-1",
                        "name": "Movie.mkv",
                        "full_path": str(path),
                        "size": 1024,
                        "is_directory": False,
                        "create_time": "2026-08-08T00:00:00+00:00",
                        "write_time": "2026-08-08T00:00:00+00:00",
                    }

            controls = FakeControls()
            scanner = FakeScanner()
            cd2 = InstantCloudCd2()
            coordinator = self.coordinator(
                store, Path(directory) / "staging", cd2, controls, scanner
            )
            coordinator.config.cloud_verify_delay = 0

            coordinator.run("cron")

            self.assertEqual(store.get_media_item("media-1")["state"], "imported")
            self.assertTrue(target.exists())
            self.assertEqual(cd2.file_calls, 2)
            watches = store.list_import_watches(media_id="media-1")
            self.assertEqual(watches[0]["state"], "done")
            self.assertEqual(
                watches[0]["details"]["completion_source"], "cloud_file"
            )

    def test_preexisting_exact_cloud_file_is_only_accepted_at_discovery_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            store, source, target, _inventory = self.make_store(directory)
            existing = {
                "id": "old-cloud-file",
                "name": "Movie.mkv",
                "full_path": "/cloud/Movie/Movie.mkv",
                "size": 1024,
                "is_directory": False,
                "create_time": "2026-08-01T00:00:00+00:00",
                "write_time": "2026-08-01T00:00:00+00:00",
            }

            class ExistingCloudCd2(FakeCd2):
                def __init__(self):
                    super().__init__({})

                def list_uploads(self):
                    return []

                def find_file(self, _path, *, force_refresh=False):
                    return dict(existing)

            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                ExistingCloudCd2(),
                FakeControls(),
                FakeScanner(),
            )
            coordinator.config.cloud_verify_delay = 0
            coordinator.config.discovery_timeout = 0

            coordinator.run("cron")

            item = store.get_media_item("media-1")
            self.assertEqual(item["state"], "imported")
            self.assertTrue(source.exists())
            self.assertTrue(target.exists())
            watches = store.list_import_watches(media_id="media-1")
            self.assertEqual(
                watches[0]["details"]["completion_source"], "cloud_existing"
            )

    def test_preexisting_cloud_file_with_wrong_size_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, target, _inventory = self.make_store(directory)

            class WrongSizeCloudCd2(FakeCd2):
                def __init__(self):
                    super().__init__({})

                def list_uploads(self):
                    return []

                def find_file(self, path, *, force_refresh=False):
                    return {
                        "id": "wrong-size-file",
                        "name": "Movie.mkv",
                        "full_path": str(path),
                        "size": 512,
                        "is_directory": False,
                        "create_time": "2026-08-01T00:00:00+00:00",
                        "write_time": "2026-08-01T00:00:00+00:00",
                    }

            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                WrongSizeCloudCd2(),
                FakeControls(),
                FakeScanner(),
            )
            coordinator.config.cloud_verify_delay = 0
            coordinator.config.discovery_timeout = 0

            coordinator.run("cron")

            self.assertEqual(store.get_media_item("media-1")["state"], "identified")
            self.assertFalse(target.exists())

    def test_same_filename_in_different_cloud_folder_is_not_matched(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, target, _inventory = self.make_store(directory)

            class WrongFolderCd2(FakeCd2):
                def __init__(self):
                    super().__init__({})
                    self.file_calls = 0

                def list_uploads(self):
                    return []

                def find_file(self, _path, *, force_refresh=False):
                    self.file_calls += 1
                    if self.file_calls == 1:
                        return None
                    return {
                        "id": "wrong-folder-file",
                        "name": "Movie.mkv",
                        "full_path": "/cloud/Other/Movie.mkv",
                        "size": 1024,
                        "is_directory": False,
                        "create_time": "2026-08-08T00:00:00+00:00",
                        "write_time": "2026-08-08T00:00:00+00:00",
                    }

            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                WrongFolderCd2(),
                FakeControls(),
                FakeScanner(),
            )
            coordinator.config.cloud_verify_delay = 0
            coordinator.config.discovery_timeout = 0

            coordinator.run("cron")

            self.assertEqual(store.get_media_item("media-1")["state"], "identified")
            self.assertFalse(target.exists())

    def test_upload_task_accepts_mount_prefix_path_variation(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, target, _inventory = self.make_store(directory)
            cd2 = FakeCd2({
                "key": "upload-relative-path",
                "dest_path": "Movie/Movie.mkv",
                "size": 1024,
                "transferred_bytes": 0,
                "status": "Finish",
                "error_message": "",
            })
            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                cd2,
                FakeControls(),
                FakeScanner(),
            )

            coordinator.run("cron")

            self.assertEqual(store.get_media_item("media-1")["state"], "imported")
            self.assertTrue(target.exists())

    def test_captured_upload_task_can_finish_and_disappear_between_polls(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, target, _inventory = self.make_store(directory)

            class DisappearingTaskCd2(FakeCd2):
                def __init__(self):
                    super().__init__({})
                    self.upload_calls = 0
                    self.file_calls = 0

                def list_uploads(self):
                    self.upload_calls += 1
                    if self.upload_calls == 2:
                        return [{
                            "key": "brief-upload",
                            "dest_path": "/cloud/Movie/Movie.mkv",
                            "size": 1024,
                            "transferred_bytes": 0,
                            "status": "Preprocessing",
                            "error_message": "",
                        }]
                    return []

                def find_file(self, path, *, force_refresh=False):
                    self.file_calls += 1
                    if self.file_calls < 3:
                        return None
                    return {
                        "id": "completed-after-task",
                        "name": "Movie.mkv",
                        "full_path": str(path),
                        "size": 1024,
                        "is_directory": False,
                        "create_time": "2026-08-08T00:00:00+00:00",
                        "write_time": "2026-08-08T00:00:00+00:00",
                    }

            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                DisappearingTaskCd2(),
                FakeControls(),
                FakeScanner(),
            )
            coordinator.config.cloud_verify_delay = 0

            coordinator.run("cron")

            self.assertEqual(store.get_media_item("media-1")["state"], "imported")
            self.assertTrue(target.exists())
            watches = store.list_import_watches(media_id="media-1")
            self.assertEqual(
                watches[0]["details"]["completion_source"],
                "cloud_file_after_task",
            )

    def test_scan_started_callback_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, _target, _inventory = self.make_store(directory)
            controls = FakeControls()
            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                FakeCd2({
                    "key": "upload-started",
                    "dest_path": "/cloud/Movie/Movie.mkv",
                    "size": 1024,
                    "transferred_bytes": 0,
                    "status": "Finish",
                    "error_message": "",
                }),
                controls,
                FakeScanner(),
            )
            coordinator.run("cron")
            result = coordinator.handle_scan_callback({
                "event_name": "scheduledtasks.started",
                "server_id": "srv1",
                "task_id": "task1",
            })
            self.assertFalse(result["accepted"])
            missing_event = coordinator.handle_scan_callback({
                "server_id": "srv1",
                "task_id": "task1",
            })
            self.assertFalse(missing_event["accepted"])
            self.assertEqual(controls.restored, 0)
            self.assertIsNotNone(store.latest_active_import_batch())

    def test_discovered_emby_task_id_overrides_stale_config_for_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, _target, _inventory = self.make_store(directory)
            controls = FakeControls()

            class DiscoveredTaskScanner(FakeScanner):
                def request_emby_refresh(self):
                    self.refreshes += 1
                    return {
                        "host": "http://emby",
                        "node_name": "Emby01",
                        "server_id": "srv1",
                        "task_id": "actual-task-id",
                        "task_name": "Scan media library",
                    }

            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                FakeCd2({
                    "key": "upload-discovered-task",
                    "dest_path": "/cloud/Movie/Movie.mkv",
                    "size": 1024,
                    "transferred_bytes": 0,
                    "status": "Finish",
                    "error_message": "",
                }),
                controls,
                DiscoveredTaskScanner(),
            )
            self.assertEqual(coordinator.config.callback_task_id, "task1")
            coordinator.run("cron")

            result = coordinator.handle_scan_callback({
                "event_name": "scheduledtasks.completed",
                "server_id": "srv1",
                "task_id": "actual-task-id",
            })

            self.assertTrue(result["accepted"])
            self.assertEqual(controls.restored, 1)
            self.assertIsNone(store.latest_active_import_batch())

    def test_scan_timeout_finishes_as_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, _target, _inventory = self.make_store(directory)
            controls = FakeControls()
            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                FakeCd2({
                    "key": "upload-timeout",
                    "dest_path": "/cloud/Movie/Movie.mkv",
                    "size": 1024,
                    "transferred_bytes": 0,
                    "status": "Finish",
                    "error_message": "",
                }),
                controls,
                FakeScanner(),
            )
            coordinator.run("cron")
            batch = store.latest_active_import_batch()
            batch["scan_callback_deadline"] = "2000-01-01T00:00:00+00:00"
            store.upsert_import_batch(batch)
            coordinator.run("cron")
            self.assertIsNone(store.latest_active_import_batch())
            finished = store.get_import_batch(batch["id"])
            self.assertEqual(finished["state"], "failed")
            self.assertEqual(controls.restored, 1)

    def test_running_emby_scan_extends_callback_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, _target, _inventory = self.make_store(directory)
            controls = FakeControls()
            scanner = FakeScanner()
            scanner.task_status.update({
                "state": "Running",
                "is_running": True,
                "progress": 48.5,
            })
            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                FakeCd2({
                    "key": "upload-running-scan",
                    "dest_path": "/cloud/Movie/Movie.mkv",
                    "size": 1024,
                    "transferred_bytes": 0,
                    "status": "Finish",
                    "error_message": "",
                }),
                controls,
                scanner,
            )
            coordinator.run("cron")
            batch = store.latest_active_import_batch()
            batch["scan_callback_deadline"] = "2000-01-01T00:00:00+00:00"
            store.upsert_import_batch(batch)

            coordinator.run("cron")

            extended = store.latest_active_import_batch()
            self.assertIsNotNone(extended)
            self.assertEqual(extended["state"], "waiting_scan_callback")
            self.assertGreater(
                pending_import._parse_time(extended["scan_callback_deadline"]),
                pending_import.datetime.now(pending_import.timezone.utc),
            )
            self.assertEqual(
                extended["details"]["last_scan_task_status"]["progress"],
                48.5,
            )
            self.assertEqual(scanner.status_calls, 1)
            self.assertEqual(controls.restored, 0)

    def test_api_confirmed_scan_completion_replaces_missing_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, _target, _inventory = self.make_store(directory)
            controls = FakeControls()
            scanner = FakeScanner()
            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                FakeCd2({
                    "key": "upload-api-complete",
                    "dest_path": "/cloud/Movie/Movie.mkv",
                    "size": 1024,
                    "transferred_bytes": 0,
                    "status": "Finish",
                    "error_message": "",
                }),
                controls,
                scanner,
            )
            coordinator.run("cron")
            batch = store.latest_active_import_batch()
            requested_at = pending_import._parse_time(batch["refresh_requested_at"])
            scanner.task_status.update({
                "state": "Idle",
                "is_running": False,
                "last_status": "Completed",
                "last_started_at": (
                    requested_at + pending_import.timedelta(seconds=1)
                ).isoformat(),
                "last_finished_at": (
                    requested_at + pending_import.timedelta(minutes=20)
                ).isoformat(),
            })
            batch["scan_callback_deadline"] = "2000-01-01T00:00:00+00:00"
            store.upsert_import_batch(batch)

            coordinator.run("cron")

            self.assertIsNone(store.latest_active_import_batch())
            finished = store.get_import_batch(batch["id"])
            self.assertEqual(finished["state"], "completed")
            self.assertIn("scan_completed_via_api", finished["details"])
            self.assertEqual(controls.restored, 1)

    def test_switch_snapshot_is_persisted_before_disable_side_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _source, _target, _inventory = self.make_store(directory)

            class InspectingControls(FakeControls):
                def __init__(self, local_store):
                    super().__init__()
                    self.local_store = local_store
                    self.observed = None

                def disable(self, snapshot=None):
                    batch = self.local_store.latest_active_import_batch()
                    self.observed = (
                        batch["id"],
                        batch["state"],
                        batch["original_catchup_enabled"],
                        batch["original_scan_enabled"],
                    )
                    raise RuntimeError("模拟关闭开关时进程故障")

            controls = InspectingControls(store)
            coordinator = self.coordinator(
                store,
                Path(directory) / "staging",
                FakeCd2({
                    "key": "upload-snapshot",
                    "dest_path": "/cloud/Movie/Movie.mkv",
                    "size": 1024,
                    "transferred_bytes": 0,
                    "status": "Finish",
                    "error_message": "",
                }),
                controls,
                FakeScanner(),
            )
            with self.assertRaises(RuntimeError):
                coordinator.run("cron")
            batch_id, state, catchup, scan = controls.observed
            self.assertEqual((state, catchup, scan), ("switch_snapshot_saved", 1, 1))
            finished = store.get_import_batch(batch_id)
            self.assertEqual(finished["state"], "failed")

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

            coordinator.run("cron")

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

            coordinator.run("cron")

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
        self.started_task_url = ""

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
        if "/emby/ScheduledTasks/Running/" in url:
            self.started_task_url = url
            return 204, None
        if "/emby/ScheduledTasks?" in url:
            return 200, [
                {
                    "Id": "actual-task",
                    "Name": "Scan media library",
                    "Key": "RefreshLibrary",
                    "State": "Running",
                    "CurrentProgressPercentage": 25,
                    "LastExecutionResult": {
                        "Status": "Completed",
                        "StartTimeUtc": "2026-08-08T00:00:00Z",
                        "EndTimeUtc": "2026-08-08T00:30:00Z",
                    },
                },
                {
                    "Id": "extract-mediainfo",
                    "Name": "Extract MediaInfo",
                    "Key": "MediaInfoExtractTask",
                    "State": "Idle",
                    "LastExecutionResult": {},
                },
            ]
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
        status = scanner.emby_task_status("stale-configured-task-id")
        self.assertEqual(status["task_id"], "actual-task")
        self.assertTrue(status["is_running"])
        target = scanner.request_emby_refresh()
        self.assertEqual(target["node_name"], "Emby01")
        self.assertEqual(target["task_id"], "actual-task")
        self.assertEqual(http.refreshes, 1)
        started = scanner.start_emby_task("Extract MediaInfo")
        self.assertEqual(started["status"], "started")
        self.assertIn("/emby/ScheduledTasks/Running/extract-mediainfo?", http.started_task_url)


if __name__ == "__main__":
    unittest.main()
