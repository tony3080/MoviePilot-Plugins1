"""SHA1 identity, active upload, hardlink rollback and pending recovery."""

import hashlib
import importlib
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "rss_remote_tests"
namespace = types.ModuleType(PACKAGE)
namespace.__path__ = [str(ROOT / "plugins.v2" / "rssallinone")]
sys.modules[PACKAGE] = namespace
database = importlib.import_module(PACKAGE + ".database")
hashes = importlib.import_module(PACKAGE + ".file_hashes")
actions = importlib.import_module(PACKAGE + ".media_actions")
pending = importlib.import_module(PACKAGE + ".pending_import")
upload = importlib.import_module(PACKAGE + ".media_upload")
remote = importlib.import_module(PACKAGE + ".remote_upload")
wire = importlib.import_module(PACKAGE + ".cd2_wire")


class ActiveUploadTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mkv"
        self.source.write_bytes(b"media-content")
        self.target = self.root / "stage" / "movie" / "title.mkv"
        self.store = database.SQLiteStore(self.root / "data.db")
        self.store.initialize()
        self.logger = Mock()
        self.stop = threading.Event()
        self.cache = hashes.FileHashCache(self.store, self.stop, self.logger)

    def add_card(self, state="identified", second=False, prepare_hashes=True):
        rows = [{
            "file_index": 0, "media_id": "card", "file_size": self.source.stat().st_size,
            "current_source_path": str(self.source), "local_hardlink_path": str(self.target),
        }]
        if second:
            other = self.root / "episode2.mkv"
            other.write_bytes(b"episode-two")
            rows.append({
                "file_index": 1, "media_id": "card", "file_size": other.stat().st_size,
                "current_source_path": str(other),
                "local_hardlink_path": str(self.root / "stage" / "series" / "episode2.mkv"),
            })
        self.store.upsert_media_item({
            "id": "card", "state": state, "downloader_id": "qb", "info_hash": "abc",
            "source_path": str(self.source), "details": {"file_mappings": rows},
        }, prepare_hashes=prepare_hashes)
        self.store.replace_file_mappings("qb", "abc", rows)

    def test_hardlink_rename_and_new_store_reuse_hash_but_content_change_invalidates(self):
        expected = hashlib.sha1(self.source.read_bytes()).hexdigest()
        self.assertEqual(self.cache.ensure(self.source), expected)
        linked = self.root / "hardlink.mkv"
        os.link(self.source, linked)
        renamed = self.root / "renamed.mkv"
        self.source.rename(renamed)
        cache = hashes.FileHashCache(database.SQLiteStore(self.store.path), self.stop, self.logger)
        with patch.object(hashes.hashlib, "sha1", side_effect=AssertionError("must reuse")):
            self.assertEqual(cache.ensure(linked), expected)
            self.assertEqual(cache.ensure(renamed), expected)
        linked.write_bytes(b"new-content")
        self.assertNotEqual(cache.ensure(linked), expected)

    def test_all_episodes_hashed_and_existing_card_skipped(self):
        self.add_card(second=True)
        self.cache.prepare_media("card")
        with self.store.connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM file_hashes").fetchone()[0], 2)
        item = self.store.get_media_item("card")
        item["state"] = "existing"
        self.store.upsert_media_item(item)
        with patch.object(self.cache, "ensure") as ensure:
            self.cache.prepare_media("card")
            ensure.assert_not_called()

    def test_partial_inventory_only_hashes_ten_of_fourteen_episodes(self):
        rows = []
        for index in range(14):
            path = self.root / f"episode-{index}.mkv"
            path.write_bytes(str(index).encode("ascii"))
            rows.append({
                "file_index": index, "media_id": "card",
                "current_source_path": str(path), "inventory_exists": index < 4,
            })
        self.store.upsert_media_item({
            "id": "card", "state": "identified", "downloader_id": "qb", "info_hash": "abc",
            "details": {"file_mappings": rows},
        }, prepare_hashes=True)
        self.store.replace_file_mappings("qb", "abc", rows)
        with patch.object(self.cache, "ensure", wraps=self.cache.ensure) as ensure:
            self.cache.prepare_media("card")
        self.assertEqual(ensure.call_count, 10)
        self.assertEqual(
            {Path(call.args[0]).name for call in ensure.call_args_list},
            {f"episode-{index}.mkv" for index in range(4, 14)},
        )

    def test_reidentification_keeps_cache_and_never_requeues_precalculation(self):
        self.add_card()
        self.cache.prepare_media("card")
        notify = Mock()
        self.store.on_media_files_changed = notify
        item = self.store.get_media_item("card")
        item.update({"title": "New title", "tmdb_id": 42})
        self.store.upsert_media_item(item)
        mappings = self.store.list_file_mappings("qb", "abc")
        self.store.replace_file_mappings("qb", "abc", mappings)
        notify.assert_not_called()
        self.assertEqual(self.store.hash_candidate_ids(), [])
        expected = hashlib.sha1(b"media-content").hexdigest()
        with patch.object(hashes.hashlib, "sha1", side_effect=AssertionError("must reuse")):
            self.assertEqual(self.cache.ensure(self.source), expected)

    def test_existing_to_missing_after_manual_identification_waits_until_import(self):
        self.add_card(state="existing")
        notify = Mock()
        self.store.on_media_files_changed = notify
        item = self.store.get_media_item("card")
        item.update({"state": "identified", "tmdb_id": 999})
        self.store.upsert_media_item(item)
        self.store.replace_file_mappings("qb", "abc", self.store.list_file_mappings("qb", "abc"))
        notify.assert_not_called()
        with patch.object(self.cache, "ensure") as ensure:
            self.cache.prepare_media("card")
            ensure.assert_not_called()
        self.assertEqual(self.store.hash_candidate_ids(), [])
        with patch.object(upload, "upload_once", return_value={"result": "instant"}) as send:
            result = actions.MediaActionService(self.store, upload=self.service()).execute("import", ["card"])
        self.assertTrue(result["success"])
        self.assertEqual(send.call_args.args[1]["sha1"], hashlib.sha1(b"media-content").hexdigest())

    def test_failed_precalculation_waits_until_import_instead_of_retrying_on_refresh(self):
        self.add_card()
        with patch.object(self.cache, "ensure", side_effect=OSError("disk offline")) as ensure:
            self.cache.prepare_media("card")
            self.cache.prepare_media("card")
        ensure.assert_called_once()
        self.assertEqual(self.store.hash_candidate_ids(), [])

    def test_direct_import_computes_missing_hash_without_precalculation(self):
        self.add_card(prepare_hashes=False)
        self.assertEqual(self.store.hash_candidate_ids(), [])
        with patch.object(upload, "upload_once", return_value={"result": "instant"}) as send:
            result = actions.MediaActionService(self.store, upload=self.service()).execute("import", ["card"])
        self.assertTrue(result["success"])
        expected = hashlib.sha1(b"media-content").hexdigest()
        self.assertEqual(send.call_args.args[1]["sha1"], expected)
        self.assertEqual(self.store.get_file_sha1(database.file_identity(self.source)[2]), expected)

    def service(self):
        cd2 = Mock(ready=True, address="localhost:1", token="test-token")
        cd2.resolve_destination_root.side_effect = lambda path: path
        return upload.MediaUploadService(
            self.store, cd2, [str(self.root / "stage")], "/115/library", self.stop, self.logger
        )

    def test_pacing_waits_three_seconds_within_card_five_between_cards_without_stacking(self):
        self.add_card(second=True)
        service = self.service()
        clock = [100.0]

        def wait(seconds):
            clock[0] += seconds
            return False

        with patch.object(upload.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(self.stop, "wait", side_effect=wait) as waiting, \
                patch.object(upload, "upload_once", return_value={"result": "instant"}) as send:
            actions.MediaActionService(self.store, upload=service).execute("import", ["card"])
            mappings = self.store.list_file_mappings("qb", "abc")
            self.store.upsert_media_item({
                "id": "other-card", "state": "identified",
                "downloader_id": "qb", "info_hash": "other",
            })
            self.store.replace_file_mappings("qb", "other", [
                {**mappings[0], "media_id": "other-card"},
            ])
            other_mappings = self.store.list_file_mappings("qb", "other")
            other_service = self.service()
            other_service.pacing = service.pacing
            other_service("other-card", other_mappings)
            self.assertEqual([call.args[0] for call in waiting.call_args_list], [3, 5])
            clock[0] += 10
            other_service("other-card", other_mappings)
            self.assertEqual(waiting.call_count, 2)
            self.assertEqual(send.call_count, 4)

    def test_failed_session_also_cools_down_and_stopping_wait_prevents_next_upload(self):
        self.add_card()
        self.target.parent.mkdir(parents=True)
        os.link(self.source, self.target)
        mappings = self.store.list_file_mappings("qb", "abc")
        service = self.service()
        with patch.object(upload.time, "monotonic", return_value=100), \
                patch.object(upload, "upload_once", side_effect=remote.NotInstant("not instant")):
            with self.assertRaises(remote.NotInstant):
                service("card", mappings)
        with patch.object(upload.time, "monotonic", return_value=101), \
                patch.object(self.stop, "wait", return_value=True) as waiting, \
                patch.object(upload, "upload_once") as send:
            with self.assertRaisesRegex(RuntimeError, "已停止"):
                service("another-card", mappings)
            waiting.assert_called_once_with(4)
            send.assert_not_called()

    def test_active_upload_uses_precomputed_hash_and_persists_per_file_result(self):
        self.add_card(second=True)
        self.cache.prepare_media("card")
        with patch.object(upload, "upload_once", return_value={"result": "instant"}) as send:
            result = actions.MediaActionService(self.store, upload=self.service()).execute("import", ["card"])
        self.assertTrue(result["success"])
        self.assertEqual(send.call_count, 2)
        self.assertEqual(send.call_args_list[0].args[1]["sha1"], hashlib.sha1(b"media-content").hexdigest())
        self.assertEqual(send.call_args_list[0].args[1]["destination"], "/115/library/movie/title.mkv")
        self.assertEqual(self.store.get_media_item("card")["state"], "imported")
        self.assertEqual(
            self.store.list_file_mappings("qb", "abc")[0]["details"]["remote_upload"]["result"], "instant"
        )
        self.assertTrue(os.path.samefile(self.source, self.target))

    def test_noninstant_direct_upload_rolls_back_only_created_hardlinks(self):
        self.add_card()
        with patch.object(upload, "upload_once", side_effect=remote.NotInstant(
            "CD2 已进入真实传输"
        )):
            result = actions.MediaActionService(self.store, upload=self.service()).execute("import", ["card"])
        self.assertFalse(result["success"])
        self.assertTrue(self.source.exists())
        self.assertFalse(self.target.exists())
        self.assertEqual(self.store.get_media_item("card")["state"], "rolled_back")

    def test_pending_remote_path_does_not_poll_backup_tasks(self):
        self.add_card(state="pending", prepare_hashes=False)
        cd2 = Mock(ready=True)
        coordinator = pending.PendingImportCoordinator(
            store=self.store, config=pending.PendingImportConfig(
                cd2_dest_root="/115/library", plugin_staging_roots=[str(self.root / "stage")],
                callback_server_name="emby", callback_task_name="scan",
            ), cd2=cd2, controls=Mock(), scanner=Mock(), stop_event=self.stop,
            logger=self.logger, remote_upload=self.service(),
        )
        with patch.object(upload, "upload_once", return_value={"result": "instant"}) as send:
            coordinator.run("manual")
        cd2.list_uploads.assert_not_called()
        cd2.find_files.assert_not_called()
        self.assertEqual(self.store.get_media_item("card")["state"], "imported")
        self.assertEqual(self.store.list_import_watches(media_id="card")[0]["state"], "done")
        expected = hashlib.sha1(b"media-content").hexdigest()
        self.assertEqual(send.call_args.args[1]["sha1"], expected)
        self.assertEqual(self.store.get_file_sha1(database.file_identity(self.source)[2]), expected)

    def test_restart_remote_watches_skip_completed_episodes(self):
        self.add_card(state="pending", second=True)
        prepared = actions.MediaActionService(self.store).prepare_monitored_import("card")
        self.store.upsert_import_batch({
            "id": "batch", "state": "running", "trigger_source": "manual",
            "current_media_id": "card", "details": {"manage_external_switches": False},
        })
        for row in prepared["upload_mappings"]:
            self.store.upsert_import_watch({
                "id": str(row["file_index"]), "batch_id": "batch", "media_id": "card",
                "file_index": row["file_index"], "state": "done" if row["file_index"] == 0 else "watching",
                "details": {"remote_upload": True},
            })
        send = Mock()
        coordinator = pending.PendingImportCoordinator(
            store=self.store, config=pending.PendingImportConfig(cd2_dest_root="/115/library"),
            cd2=Mock(), controls=Mock(), scanner=Mock(), stop_event=self.stop,
            logger=self.logger, remote_upload=send,
        )
        coordinator.run("manual")
        send.assert_called_once()
        self.assertEqual(send.call_args.args[1][0]["file_index"], 1)
        self.assertEqual(self.store.get_media_item("card")["state"], "imported")

    def test_direct_batch_is_durable_scoped_and_never_runs_external_controls(self):
        self.add_card()
        self.store.upsert_media_item({"id": "other", "state": "pending"})
        controls, scanner = Mock(), Mock()
        coordinator = pending.PendingImportCoordinator(
            store=self.store, config=pending.PendingImportConfig(
                cd2_dest_root="/115/library", plugin_staging_roots=[str(self.root / "stage")],
            ), cd2=Mock(ready=True), controls=controls, scanner=scanner,
            stop_event=self.stop, logger=self.logger, remote_upload=Mock(),
        )
        batch = coordinator.queue_direct(["card"])
        self.assertEqual(batch["details"]["selected_media_ids"], ["card"])
        self.assertFalse(self.target.exists())
        coordinator.run("supervisor")
        self.assertEqual(self.store.get_media_item("card")["state"], "imported")
        self.assertEqual(self.store.get_media_item("other")["state"], "pending")
        self.assertEqual(self.store.get_import_batch(batch["id"])["state"], "completed")
        self.assertEqual(controls.mock_calls, [])
        self.assertEqual(scanner.mock_calls, [])

    def test_failed_direct_card_is_not_retried_forever(self):
        self.add_card()
        send = Mock(side_effect=remote.NotInstant("CD2 已进入真实传输"))
        coordinator = pending.PendingImportCoordinator(
            store=self.store, config=pending.PendingImportConfig(
                cd2_dest_root="/115/library", plugin_staging_roots=[str(self.root / "stage")],
            ), cd2=Mock(ready=True), controls=Mock(), scanner=Mock(),
            stop_event=self.stop, logger=self.logger, remote_upload=send,
        )
        batch = coordinator.queue_direct(["card"])
        coordinator.run("direct")
        send.assert_called_once()
        self.assertEqual(self.store.get_media_item("card")["state"], "rolled_back")
        self.assertEqual(self.store.get_import_batch(batch["id"])["state"], "completed")
        self.assertFalse(self.target.exists())
        self.assertTrue(self.source.exists())

    def test_direct_batch_restart_before_preparing_card_retries_safely(self):
        self.add_card()
        coordinator = pending.PendingImportCoordinator(
            store=self.store, config=pending.PendingImportConfig(
                cd2_dest_root="/115/library", plugin_staging_roots=[str(self.root / "stage")],
            ), cd2=Mock(ready=True), controls=Mock(), scanner=Mock(),
            stop_event=self.stop, logger=self.logger, remote_upload=Mock(),
        )
        batch = coordinator.queue_direct(["card"])
        batch["current_media_id"] = "card"
        self.store.upsert_import_batch(batch)
        coordinator.run("supervisor")
        self.assertEqual(self.store.get_media_item("card")["state"], "imported")

    def test_forced_batch_restores_mode_for_each_episode_without_affecting_next_batch(self):
        self.add_card(second=True, prepare_hashes=False)
        self.store.upsert_media_item({"id": "unselected", "state": "pending"})

        def coordinator():
            return pending.PendingImportCoordinator(
                store=self.store, config=pending.PendingImportConfig(
                    cd2_dest_root="/115/library",
                    plugin_staging_roots=[str(self.root / "stage")],
                ), cd2=Mock(ready=True), controls=Mock(), scanner=Mock(),
                stop_event=self.stop, logger=self.logger, remote_upload=self.service(),
            )

        batch = coordinator().queue_direct(["card"], allow_full_upload=True)
        self.assertTrue(self.store.get_import_batch(batch["id"])["details"]["allow_full_upload"])
        with patch.object(upload, "upload_once", return_value={"result": "uploaded"}) as send:
            coordinator().run("supervisor")
        self.assertEqual(send.call_count, 2)
        self.assertTrue(all(call.kwargs["allow_full_upload"] for call in send.call_args_list))
        self.assertEqual(send.call_args_list[0].args[1]["sha1"],
                         hashlib.sha1(b"media-content").hexdigest())
        self.assertEqual(send.call_args_list[0].args[1]["destination"],
                         "/115/library/movie/title.mkv")
        self.assertEqual(self.store.get_media_item("card")["state"], "imported")
        self.assertEqual(self.store.get_media_item("unselected")["state"], "pending")
        self.assertTrue(self.target.exists())

        # A later ordinary batch must remain instant-only, including failures.
        item = self.store.get_media_item("card")
        item["state"] = "identified"
        self.store.upsert_media_item(item)
        ordinary = coordinator().queue_direct(["card"])
        self.assertFalse(ordinary["details"]["allow_full_upload"])
        with patch.object(upload, "upload_once", side_effect=remote.NotInstant(
            "CD2 已进入真实传输",
        )) as send:
            coordinator().run("direct")
        self.assertFalse(send.call_args.kwargs["allow_full_upload"])
        self.assertEqual(self.store.get_media_item("card")["state"], "rolled_back")
        self.assertTrue(self.source.exists())

    def test_forced_upload_error_still_rolls_back_and_finishes_batch(self):
        self.add_card()
        coordinator = pending.PendingImportCoordinator(
            store=self.store, config=pending.PendingImportConfig(
                cd2_dest_root="/115/library", plugin_staging_roots=[str(self.root / "stage")],
            ), cd2=Mock(ready=True), controls=Mock(), scanner=Mock(),
            stop_event=self.stop, logger=self.logger, remote_upload=self.service(),
        )
        batch = coordinator.queue_direct(["card"], allow_full_upload=True)
        with patch.object(upload, "upload_once", side_effect=remote.UploadIdleTimeout(
            "CD2 连续 60 秒无有效响应",
        )) as send:
            coordinator.run("direct")
        send.assert_called_once()
        self.assertTrue(send.call_args.kwargs["allow_full_upload"])
        self.assertTrue(self.source.exists())
        self.assertFalse(self.target.exists())
        self.assertEqual(self.store.get_media_item("card")["state"], "identified")
        self.assertIn("60 秒", self.store.get_media_item("card")["failure_message"])
        self.assertEqual(self.store.get_import_batch(batch["id"])["state"], "completed")

    def test_forced_batch_rejects_unidentified_cards(self):
        self.add_card(state="unidentified")
        coordinator = pending.PendingImportCoordinator(
            store=self.store, config=pending.PendingImportConfig(
                cd2_dest_root="/115/library", plugin_staging_roots=[str(self.root / "stage")],
            ), cd2=Mock(ready=True), controls=Mock(), scanner=Mock(),
            stop_event=self.stop, logger=self.logger, remote_upload=self.service(),
        )
        with self.assertRaisesRegex(RuntimeError, "仅可入库"):
            coordinator.queue_direct(["card"], allow_full_upload=True)
        self.assertIsNone(self.store.latest_active_import_batch())
        self.assertFalse(self.target.exists())

    def test_forced_protocol_still_probes_instant_then_can_stream_full_file(self):
        import grpc

        self.source.write_bytes(b"media" * 60000)
        for real_transfer, fails in ((False, False), (True, False), (True, True)):
            with self.subTest(real_transfer=real_transfer, fails=fails):
                item = {
                    **remote.identity(self.source),
                    "sha1": hashlib.sha1(self.source.read_bytes()).hexdigest(),
                    "destination": "/115/library/source.mkv",
                }
                client = Mock()
                client.GetSystemInfo.return_value = types.SimpleNamespace(IsLogin=True, SystemReady=True)
                client.StartRemoteUpload.return_value = types.SimpleNamespace(upload_id="forced")
                events = [self.status_event(1, "forced")]
                if real_transfer:
                    events += [
                        self.status_event(7, "forced"), self.status_event(3, "forced"),
                        wire.pb.RemoteUploadChannelReply(
                            upload_id="forced", read_data={
                                "offset": 0, "length": item["size"], "lazy_read": True,
                            },
                        ),
                    ]
                events.append(wire.pb.RemoteUploadChannelReply(
                    upload_id="forced", status_changed={
                        "status": 9 if fails else 5,
                        "error_message": "test cloud error" if fails else "",
                    },
                ))
                stream = Mock()
                stream.__iter__ = Mock(return_value=iter(events))
                client.RemoteUploadChannel.return_value = stream
                client.RemoteReadData.side_effect = lambda request, **_: types.SimpleNamespace(
                    success=True, bytes_received=len(request.data),
                )
                with (
                    patch.object(remote, "Client", return_value=client),
                    patch.object(grpc, "insecure_channel"),
                ):
                    if fails:
                        with self.assertRaisesRegex(remote.UploadError, "test cloud error"):
                            remote.upload_once(
                                {"address": "localhost:1", "token": "test-token",
                                 "max_request_bytes": 131072},
                                item, self.stop, allow_full_upload=True,
                            )
                    else:
                        result = remote.upload_once(
                            {"address": "localhost:1", "token": "test-token",
                             "max_request_bytes": 131072},
                            item, self.stop, allow_full_upload=True,
                        )
                        self.assertEqual(result["result"], "uploaded" if real_transfer else "instant")
                start = client.StartRemoteUpload.call_args.args[0]
                self.assertEqual(start.known_hashes[2], item["sha1"])
                if real_transfer:
                    requests = [call.args[0] for call in client.RemoteReadData.call_args_list]
                    self.assertEqual(b"".join(request.data for request in requests),
                                     self.source.read_bytes())
                    self.assertEqual([request.offset for request in requests], [0, 131072, 262144])
                    self.assertEqual([request.is_last_chunk for request in requests],
                                     [False, False, True])
                else:
                    client.RemoteReadData.assert_not_called()
                self.assertEqual(client.RemoteUploadControl.call_count, int(fails))
                stream.cancel.assert_called_once()

    def test_generated_remote_rpc_messages_match_client_fields(self):
        start = wire.MESSAGES["StartRequest"](
            file_path="/115/library/a.mkv", file_size=123,
            known_hashes={2: "a" * 40}, client_can_calculate_hashes=True,
        )
        self.assertEqual(start.known_hashes[2], "a" * 40)
        read = wire.MESSAGES["ReadUpload"](
            upload_id="test", offset=1, data=b"payload", is_last_chunk=True,
        )
        self.assertEqual(read.data, b"payload")

    def test_noninstant_session_cancels_using_generated_protocol(self):
        import grpc
        client = Mock()
        client.GetSystemInfo.return_value = types.SimpleNamespace(IsLogin=True, SystemReady=True)
        client.StartRemoteUpload.return_value = types.SimpleNamespace(upload_id="noninstant-session")
        events = [
            wire.pb.RemoteUploadChannelReply(
                upload_id="noninstant-session", status_changed={"status": state}
            ) for state in (1, 7, 3)
        ]
        stream = Mock()
        stream.__iter__ = Mock(return_value=iter(events))
        client.RemoteUploadChannel.return_value = stream
        item = {
            **remote.identity(self.source), "sha1": hashlib.sha1(b"media-content").hexdigest(),
            "destination": "/115/library/source.mkv",
        }
        messages = []
        with patch.object(remote, "Client", return_value=client), patch.object(grpc, "insecure_channel"):
            with self.assertRaises(remote.NotInstant):
                remote.upload_once(
                    {"address": "localhost:1", "token": "test-token"}, item,
                    self.stop, emit=messages.append,
                )
        client.RemoteUploadControl.assert_called_once()
        request = client.RemoteUploadControl.call_args.args[0]
        self.assertEqual(request.upload_id, "noninstant-session")
        self.assertEqual(request.WhichOneof("control"), "cancel")
        self.assertIsInstance(request.cancel, wire.pb.CancelRemoteUpload)
        self.assertFalse(any("取消 CD2 会话失败" in text for text in messages))
        client.RemoteReadData.assert_not_called()
        stream.cancel.assert_called_once()

    def test_source_change_between_hash_and_upload_never_submits_stale_hash(self):
        self.add_card()
        prepared = actions.MediaActionService(self.store).prepare_monitored_import("card")
        service = self.service()
        def change(_path):
            self.target.write_bytes(b"changed media")
            return "a" * 40
        with patch.object(service.cache, "ensure", side_effect=change), patch.object(upload, "upload_once") as send:
            with self.assertRaisesRegex(RuntimeError, "文件发生变化"):
                service("card", prepared["upload_mappings"])
        send.assert_not_called()

    def run_timed_session(self, scheduled, prepare=None, read=None):
        import grpc

        clock = [0.0]

        class TimedQueue:
            def get(self, timeout):
                if scheduled and scheduled[0][0] <= clock[0] + timeout:
                    at, event = scheduled.pop(0)
                    clock[0] = max(clock[0], at)
                    return "event", event
                clock[0] += timeout
                raise remote.queue.Empty

        client = Mock()
        client.GetSystemInfo.return_value = types.SimpleNamespace(IsLogin=True, SystemReady=True)
        client.StartRemoteUpload.return_value = types.SimpleNamespace(upload_id="idle-session")
        if read:
            client.RemoteReadData.side_effect = lambda *args, **kwargs: read(clock)
        item = {
            **remote.identity(self.source), "sha1": hashlib.sha1(b"media-content").hexdigest(),
            "destination": "/115/library/source.mkv",
        }
        if prepare:
            item.pop("sha1")
        messages = []
        self.timed_client, self.timed_messages, self.timed_clock = client, messages, clock
        with (
            patch.object(remote, "Client", return_value=client),
            patch.object(grpc, "insecure_channel"),
            patch.object(remote.queue, "Queue", return_value=TimedQueue()),
            patch.object(remote.threading, "Thread"),
            patch.object(remote.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(remote, "sha1_file", side_effect=lambda *args: prepare(clock)),
        ):
            return remote.upload_once(
                {"address": "localhost:1", "token": "test-token"}, item,
                self.stop, emit=messages.append,
            )

    def status_event(self, state, upload_id="idle-session"):
        return wire.pb.RemoteUploadChannelReply(
            upload_id=upload_id, status_changed={"status": state},
        )

    def test_no_first_response_times_out_after_sixty_seconds_and_cancels(self):
        with self.assertRaisesRegex(remote.UploadIdleTimeout, "60 秒.*尚未收到"):
            self.run_timed_session([])
        self.assertEqual(self.timed_clock[0], 60)
        self.timed_client.RemoteUploadControl.assert_called_once()
        self.timed_client.RemoteUploadChannel.return_value.cancel.assert_called_once()
        self.assertTrue(any("连续 60 秒无有效响应" in text for text in self.timed_messages))

    def test_current_session_responses_reset_idle_timeout_beyond_sixty_seconds(self):
        result = self.run_timed_session([
            (50, self.status_event(1)), (100, self.status_event(7)),
            (149, self.status_event(5)),
        ])
        self.assertEqual(result["result"], "instant")
        self.assertEqual(self.timed_clock[0], 149)
        self.timed_client.RemoteUploadControl.assert_not_called()

    def test_other_sessions_and_empty_envelopes_do_not_reset_timeout(self):
        with self.assertRaises(remote.UploadIdleTimeout):
            self.run_timed_session([
                (30, self.status_event(1, "another-session")),
                (55, wire.pb.RemoteUploadChannelReply(upload_id="idle-session")),
            ])
        self.assertEqual(self.timed_clock[0], 60)

    def test_silence_after_valid_response_has_its_own_sixty_second_budget(self):
        with self.assertRaisesRegex(remote.UploadIdleTimeout, "最后状态=7"):
            self.run_timed_session([(50, self.status_event(7))])
        self.assertEqual(self.timed_clock[0], 110)

    def test_sha1_preparation_is_excluded_from_response_timeout(self):
        def prepare(clock):
            clock[0] += 120
            return hashlib.sha1(b"media-content").hexdigest()

        with self.assertRaises(remote.UploadIdleTimeout):
            self.run_timed_session([], prepare=prepare)
        self.assertEqual(self.timed_clock[0], 180)

    def test_local_read_and_reply_time_is_excluded_from_idle_wait(self):
        def read(clock):
            clock[0] += 90
            return types.SimpleNamespace(success=True, bytes_received=5)

        result = self.run_timed_session([
            (50, wire.pb.RemoteUploadChannelReply(
                upload_id="idle-session", read_data={"offset": 0, "length": 5},
            )),
            (190, self.status_event(5)),
        ], read=read)
        self.assertEqual(result["sent_bytes"], 5)
        self.assertEqual(result["status"], "completed")

    def test_idle_timeout_rolls_back_current_card_and_continues_direct_queue(self):
        self.add_card()
        other_source = self.root / "other.mkv"
        other_source.write_bytes(b"other-media")
        other_target = self.root / "stage" / "movie" / "other.mkv"
        rows = [{
            "file_index": 0, "media_id": "other", "file_size": other_source.stat().st_size,
            "current_source_path": str(other_source), "local_hardlink_path": str(other_target),
        }]
        self.store.upsert_media_item({
            "id": "other", "state": "identified", "downloader_id": "qb", "info_hash": "other",
            "source_path": str(other_source), "details": {"file_mappings": rows},
        })
        self.store.replace_file_mappings("qb", "other", rows)
        coordinator = pending.PendingImportCoordinator(
            store=self.store, config=pending.PendingImportConfig(
                cd2_dest_root="/115/library", plugin_staging_roots=[str(self.root / "stage")],
            ), cd2=Mock(ready=True), controls=Mock(), scanner=Mock(),
            stop_event=self.stop, logger=self.logger, remote_upload=self.service(),
        )
        batch = coordinator.queue_direct(["card", "other"])
        with patch.object(upload, "upload_once", side_effect=[
            remote.UploadIdleTimeout("CD2 连续 60 秒无有效响应"), {"result": "instant"},
        ]) as send:
            coordinator.run("direct")
        self.assertEqual(send.call_count, 2)
        failed = self.store.get_media_item("card")
        self.assertEqual(failed["state"], "identified")
        self.assertIn("60 秒无有效响应", failed["failure_message"])
        self.assertEqual(self.store.list_import_watches(media_id="card")[0]["state"], "rolled_back")
        self.assertEqual(self.store.get_media_item("other")["state"], "imported")
        self.assertTrue(self.source.exists())
        self.assertFalse(self.target.exists())
        self.assertTrue(other_target.exists())
        finished = self.store.get_import_batch(batch["id"])
        self.assertEqual((finished["state"], finished["succeeded"], finished["failed"]),
                         ("completed", 1, 1))


if __name__ == "__main__":
    unittest.main()
