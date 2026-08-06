"""Durable serial pending-import queue with CloudDrive2 monitoring."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, Iterable, List, Optional

from .clouddrive_client import CloudDriveClient
from .database import SQLiteStore, utc_now
from .external_controls import (
    ExternalControlBundle,
    ExternalControlError,
    ExternalSwitchSnapshot,
    ScanSystemClient,
)
from .media_actions import MediaActionService


ACTIVE_WATCH_STATES = {
    "waiting_task",
    "watching",
    "waiting_library",
    "rolling_back",
}
RISK_WORDS = {
    "captcha",
    "验证码",
    "rate limit",
    "ratelimit",
    "too many requests",
    "forbidden",
    "risk control",
    "风控",
    "限流",
    "禁止访问",
}
COMPLETED_SCAN_EVENTS = {
    "scheduledtask.completed",
    "scheduledtasks.completed",
}


def _parse_time(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalized_path(value: object) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    normalized = str(PurePosixPath(text))
    return normalized.casefold()


@dataclass
class PendingImportConfig:
    cd2_dest_root: str
    plugin_staging_roots: List[str] = field(default_factory=list)
    plugin_staging_root: str = ""
    discovery_timeout: int = 180
    card_timeout: int = 7200
    poll_interval: int = 10
    transfer_grace: int = 20
    risk_cooldown: int = 1800
    risk_retry_limit: int = 3
    scan_callback_timeout: int = 7200
    callback_server_id: str = ""
    callback_task_id: str = ""
    callback_task_name: str = ""

    def staging_roots(self) -> List[str]:
        values = [*list(self.plugin_staging_roots or []), self.plugin_staging_root]
        return list(dict.fromkeys(
            str(value or "").strip() for value in values if str(value or "").strip()
        ))

    def validate(self) -> None:
        if not self.staging_roots():
            raise RuntimeError("源路径路由中没有可用的硬链接根目录")
        if not str(self.cd2_dest_root or "").strip():
            raise RuntimeError("未配置 CD2 云端目标根目录")
        if not str(self.callback_server_id or "").strip():
            raise RuntimeError("未配置 Emby 扫库回调服务器 ID")
        if not (
            str(self.callback_task_id or "").strip()
            or str(self.callback_task_name or "").strip()
        ):
            raise RuntimeError("至少配置 Emby 扫库回调任务 ID 或任务名称")


class PendingImportCoordinator:
    """Run one card at a time and persist every externally visible state."""

    def __init__(
        self,
        *,
        store: SQLiteStore,
        config: PendingImportConfig,
        cd2: CloudDriveClient,
        controls: ExternalControlBundle,
        scanner: ScanSystemClient,
        stop_event: Any,
        logger: Any,
        notify: Optional[Callable[[str, str], None]] = None,
    ):
        self.store = store
        self.config = config
        self.cd2 = cd2
        self.controls = controls
        self.scanner = scanner
        self.stop_event = stop_event
        self.logger = logger
        self.notify = notify or (lambda _title, _text: None)

    def status(self) -> Dict[str, Any]:
        batch = self.store.latest_active_import_batch()
        return {
            "running": bool(batch),
            "batch": batch,
            "pending": self.store.count_media_states(["pending"]),
            "importing": self.store.count_media_states(["importing"]),
            "active_watches": len(self.store.list_import_watches(states=ACTIVE_WATCH_STATES)),
        }

    def preflight(self) -> None:
        self.config.validate()
        if not self.cd2.ready:
            raise RuntimeError("CloudDrive2 gRPC 地址或令牌未配置")
        if not self.controls.ready:
            raise RuntimeError("追更或外部扫库联动配置不完整")

    def run(self, trigger_source: str) -> Dict[str, Any]:
        batch = self.store.latest_active_import_batch()
        if batch:
            state = str(batch.get("state") or "")
            if state == "waiting_scan_callback":
                return self._supervise_scan_wait(batch)
            if state == "restore_failed":
                details = dict(batch.get("details") or {})
                final_state = str(
                    details.get("restore_final_state") or "completed"
                ).strip()
                self._restore_and_finish(batch, final_state=final_state)
                return self.status()
            if state == "paused_risk":
                resume_at = _parse_time(batch.get("resume_at"))
                if resume_at and datetime.now(timezone.utc) < resume_at:
                    return self.status()
                batch["state"] = "running"
                batch["resume_at"] = None
                batch["updated_at"] = utc_now()
                self.store.upsert_import_batch(batch)
            if self._batch_snapshot(batch) is None:
                self._fail_batch_without_switch_snapshot(batch)
                return self.status()
            if state in {"starting", "switch_snapshot_saved"}:
                snapshot = self._batch_snapshot(batch)
                if snapshot is None:
                    self._fail_batch_without_switch_snapshot(batch)
                    return self.status()
                try:
                    self.controls.disable(snapshot)
                except Exception as error:
                    self._fail_batch_start(batch, error)
                    raise
                batch.update({
                    "state": "running",
                    "details": {
                        **dict(batch.get("details") or {}),
                        "switches_disabled_at": utc_now(),
                    },
                    "updated_at": utc_now(),
                })
                self.store.upsert_import_batch(batch)
            else:
                self.controls.ensure_disabled()
        else:
            if self.store.count_media_states(["pending", "importing"]) <= 0:
                return self.status()
            self.preflight()
            snapshot = self.controls.snapshot()
            now = utc_now()
            batch = {
                "id": uuid.uuid4().hex,
                "state": "switch_snapshot_saved",
                "trigger_source": str(trigger_source or "manual"),
                "current_media_id": "",
                "original_catchup_enabled": snapshot.catchup_enabled,
                "original_scan_enabled": snapshot.scan_enabled,
                "succeeded": 0,
                "failed": 0,
                "risk_count": 0,
                "details": {"switch_snapshot_saved_at": now},
                "created_at": now,
                "updated_at": now,
            }
            self.store.upsert_import_batch(batch)
            try:
                self.controls.disable(snapshot)
            except Exception as error:
                self._fail_batch_start(batch, error)
                raise
            batch.update({
                "state": "running",
                "details": {
                    **dict(batch.get("details") or {}),
                    "switches_disabled_at": utc_now(),
                },
                "updated_at": utc_now(),
            })
            self.store.upsert_import_batch(batch)

        resumed = self._resume_current_card_if_needed(batch)
        if resumed == "risk":
            return self.status()
        while not self.stop_event.is_set():
            item = self.store.next_media_in_state("pending")
            if not item:
                break
            outcome = self._process_card(batch, item)
            if outcome == "risk":
                return self.status()
            batch = self.store.get_import_batch(batch["id"]) or batch
        if self.stop_event.is_set():
            return self.status()
        return self._finish_queue(batch)

    def handle_scan_callback(self, event: Dict[str, Any]) -> Dict[str, Any]:
        batch = self.store.latest_active_import_batch()
        if not batch or str(batch.get("state") or "") != "waiting_scan_callback":
            return {"accepted": False, "message": "当前没有等待扫库回调的批次"}
        requested_at = _parse_time(batch.get("refresh_requested_at"))
        event_time = _parse_time(event.get("event_time")) or datetime.now(timezone.utc)
        if requested_at and event_time < requested_at:
            return {"accepted": False, "message": "回调早于本轮媒体库刷新请求"}
        filters = {
            "server_id": self.config.callback_server_id,
            "task_id": self.config.callback_task_id,
            "task_name": self.config.callback_task_name,
        }
        for key, expected in filters.items():
            if expected and str(event.get(key) or "").strip() != str(expected).strip():
                return {"accepted": False, "message": f"回调 {key} 与配置不匹配"}
        event_name = str(event.get("event_name") or "").strip().casefold()
        if event_name not in COMPLETED_SCAN_EVENTS:
            return {"accepted": False, "message": "不是 scheduledtasks.completed 回调"}
        details = dict(batch.get("details") or {})
        details["scan_callback"] = copy.deepcopy(event)
        details["scan_completed_at"] = utc_now()
        batch["details"] = details
        batch["updated_at"] = utc_now()
        self.store.upsert_import_batch(batch)
        self._restore_and_finish(batch, final_state="completed")
        return {"accepted": True, "message": "扫库完成回调已确认，外部开关已恢复"}

    def _resume_current_card_if_needed(self, batch: Dict[str, Any]) -> str:
        media_id = str(batch.get("current_media_id") or "").strip()
        if not media_id:
            importing = self.store.next_media_in_state("importing")
            media_id = str((importing or {}).get("id") or "")
        if not media_id:
            return "none"
        watches = self.store.list_import_watches(batch_id=batch["id"], media_id=media_id)
        if not watches:
            MediaActionService(self.store).rollback_monitored_import(
                media_id,
                failure_code="restart_watch_missing",
                failure_message="插件重启后找不到 CD2 监控记录",
            )
            self._increment_batch(batch, failed=1, current_media_id="")
            return "failed"
        outcome = self._monitor_card(batch, media_id, watches)
        if outcome == "success":
            MediaActionService(self.store).finalize_monitored_import(media_id)
            self._increment_batch(batch, succeeded=1, current_media_id="")
        elif outcome == "risk":
            self._pause_for_risk(batch, media_id, "CD2 风控，队列暂停")
            return "risk"
        elif outcome == "stopped":
            return "stopped"
        else:
            self._rollback_card(batch, media_id, "cd2_monitor_failed", str(outcome))
            return "failed"
        return "success"

    def _process_card(self, batch: Dict[str, Any], item: Dict[str, Any]) -> str:
        media_id = str(item.get("id") or "")
        self._increment_batch(batch, current_media_id=media_id)
        baseline_keys = {row.get("key") for row in self.cd2.list_uploads() if row.get("key")}
        try:
            prepared = MediaActionService(self.store).prepare_monitored_import(media_id)
            created = list(prepared.get("created_mappings") or [])
            if not created:
                MediaActionService(self.store).finalize_monitored_import(media_id)
                self._increment_batch(batch, succeeded=1, current_media_id="")
                return "success"
            watches = self._create_watches(batch, media_id, created, baseline_keys)
            outcome = self._monitor_card(batch, media_id, watches)
            if outcome == "success":
                MediaActionService(self.store).finalize_monitored_import(media_id)
                self._increment_batch(batch, succeeded=1, current_media_id="")
                return "success"
            if outcome == "risk":
                self._pause_for_risk(batch, media_id, "CD2 命中风控或限流")
                return "risk"
            if outcome == "stopped":
                return "stopped"
            self._rollback_card(batch, media_id, "cd2_monitor_failed", str(outcome))
            return "failed"
        except Exception as error:
            current = self.store.get_media_item(media_id)
            if current and str(current.get("state") or "") == "importing":
                self._rollback_card(batch, media_id, "pending_import_failed", str(error))
            else:
                failed = copy.deepcopy(current or item)
                failed.update({
                    "state": "identified",
                    "failure_code": "pending_import_failed",
                    "failure_message": str(error),
                    "updated_at": utc_now(),
                })
                self.store.upsert_media_item(failed)
                self._increment_batch(batch, failed=1, current_media_id="")
            self.logger.error(f"RSS一条龙：待入库卡片处理失败：{error}", exc_info=True)
            return "failed"

    def _create_watches(
        self,
        batch: Dict[str, Any],
        media_id: str,
        mappings: Iterable[Dict[str, Any]],
        baseline_keys: set,
    ) -> List[Dict[str, Any]]:
        result = []
        for mapping in mappings:
            local_path = str(mapping.get("local_hardlink_path") or "")
            watch = {
                "id": uuid.uuid4().hex,
                "batch_id": batch["id"],
                "media_id": media_id,
                "file_index": int(mapping.get("file_index") or 0),
                "state": "waiting_task",
                "local_hardlink_path": local_path,
                "expected_cd2_dest_path": self._cd2_dest_path(local_path),
                "expected_mp_library_path": str(mapping.get("inventory_path") or ""),
                "cd2_key": "",
                "file_size": int(mapping.get("file_size") or 0),
                "transferred_bytes": 0,
                "details": {
                    "baseline_keys": sorted(baseline_keys),
                    "discovery_deadline": (
                        datetime.now(timezone.utc)
                        + timedelta(seconds=self.config.discovery_timeout)
                    ).isoformat(timespec="seconds"),
                    "card_deadline": (
                        datetime.now(timezone.utc)
                        + timedelta(seconds=self.config.card_timeout)
                    ).isoformat(timespec="seconds"),
                },
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            self.store.upsert_import_watch(watch)
            result.append(watch)
        return result

    def _cd2_dest_path(self, local_path: str) -> str:
        local = Path(str(local_path)).expanduser().resolve(strict=False)
        matches = []
        for value in self.config.staging_roots():
            root = Path(value).expanduser().resolve(strict=False)
            try:
                relative = local.relative_to(root)
            except ValueError:
                continue
            matches.append((len(root.parts), relative))
        if not matches:
            roots = "、".join(self.config.staging_roots())
            raise RuntimeError(f"硬链接路径未命中源路径路由根目录：{local}；候选：{roots}")
        _depth, relative = max(matches, key=lambda item: item[0])
        return str(
            PurePosixPath(self.config.cd2_dest_root)
            / PurePosixPath(*relative.parts)
        )

    def _monitor_card(
        self,
        batch: Dict[str, Any],
        media_id: str,
        watches: List[Dict[str, Any]],
    ) -> str:
        while not self.stop_event.is_set():
            uploads = self.cd2.list_uploads()
            by_key = {str(row.get("key") or ""): row for row in uploads if row.get("key")}
            changed = False
            terminal = True
            failure = ""
            risk = False
            for watch in self.store.list_import_watches(
                batch_id=batch["id"], media_id=media_id
            ):
                if str(watch.get("state") or "") == "done":
                    continue
                terminal = False
                result = self._observe_watch(watch, uploads, by_key)
                changed = changed or result in {"done", "failed", "risk"}
                if result == "risk":
                    risk = True
                    break
                if result.startswith("failed:"):
                    failure = result.removeprefix("failed:")
                    break
            if risk:
                self._stop_cd2_tasks(batch["id"], media_id)
                return "risk"
            if failure:
                self._stop_cd2_tasks(batch["id"], media_id)
                return failure
            remaining = self.store.list_import_watches(
                batch_id=batch["id"], media_id=media_id, states=ACTIVE_WATCH_STATES
            )
            if not remaining and (terminal or changed):
                return "success"
            self.stop_event.wait(max(2, self.config.poll_interval))
        return "stopped"

    def _observe_watch(
        self,
        watch: Dict[str, Any],
        uploads: List[Dict[str, Any]],
        by_key: Dict[str, Dict[str, Any]],
    ) -> str:
        now = datetime.now(timezone.utc)
        details = dict(watch.get("details") or {})
        task = None
        key = str(watch.get("cd2_key") or "")
        if key:
            task = by_key.get(key)
        else:
            baseline = set(details.get("baseline_keys") or [])
            expected_path = _normalized_path(watch.get("expected_cd2_dest_path"))
            expected_size = int(watch.get("file_size") or 0)
            candidates = [
                row for row in uploads
                if str(row.get("key") or "") not in baseline
                and _normalized_path(row.get("dest_path")) == expected_path
                and int(row.get("size") or 0) == expected_size
            ]
            if len(candidates) == 1:
                task = candidates[0]
                watch["cd2_key"] = str(task.get("key") or "")
                watch["state"] = "watching"
            elif len(candidates) > 1:
                return "failed:CD2 出现多个相同完整路径和大小的上传任务"
        if not task:
            discovery_deadline = _parse_time(details.get("discovery_deadline"))
            card_deadline = _parse_time(details.get("card_deadline"))
            if card_deadline and now >= card_deadline:
                return "failed:CD2 单卡监控超过最终超时"
            if not key and discovery_deadline and now >= discovery_deadline:
                return "failed:CD2 未在限定时间内发现上传任务"
            watch["updated_at"] = utc_now()
            self.store.upsert_import_watch(watch)
            return "waiting"
        status = str(task.get("status") or "").strip().casefold()
        error_message = str(task.get("error_message") or "")
        transferred = int(task.get("transferred_bytes") or 0)
        watch["transferred_bytes"] = transferred
        details["last_status"] = status
        details["last_error"] = error_message
        details["last_seen_at"] = utc_now()
        if self._is_risk(error_message):
            watch.update({"state": "risk_control", "details": details, "updated_at": utc_now()})
            self.store.upsert_import_watch(watch)
            return "risk"
        if status in {"finish", "skipped"}:
            watch.update({"state": "done", "details": details, "updated_at": utc_now()})
            self.store.upsert_import_watch(watch)
            return "done"
        if status == "transfer":
            first_transfer = _parse_time(details.get("first_transfer_at"))
            previous = int(details.get("last_transfer_bytes") or 0)
            if not first_transfer:
                first_transfer = now
                details["first_transfer_at"] = now.isoformat(timespec="seconds")
            if transferred > previous:
                details["growth_samples"] = int(details.get("growth_samples") or 0) + 1
            details["last_transfer_bytes"] = transferred
            threshold = max(
                8 * 1024 * 1024,
                min(64 * 1024 * 1024, max(1, int(watch.get("file_size") or 0)) // 100),
            )
            grace_elapsed = (now - first_transfer).total_seconds() >= self.config.transfer_grace
            if transferred >= threshold or (
                grace_elapsed and int(details.get("growth_samples") or 0) >= 2 and transferred > 0
            ):
                watch.update({"state": "rolling_back", "details": details, "updated_at": utc_now()})
                self.store.upsert_import_watch(watch)
                return f"failed:CD2 已进入真实传输（{transferred} 字节）"
        if status in {"error", "fatalerror", "cancelled", "ignored"}:
            watch.update({"state": "error", "details": details, "updated_at": utc_now()})
            self.store.upsert_import_watch(watch)
            return f"failed:CD2 上传任务异常：{error_message or status}"
        card_deadline = _parse_time(details.get("card_deadline"))
        if card_deadline and now >= card_deadline:
            return "failed:CD2 单卡监控超过最终超时"
        watch.update({"state": "watching", "details": details, "updated_at": utc_now()})
        self.store.upsert_import_watch(watch)
        return "watching"

    @staticmethod
    def _is_risk(message: object) -> bool:
        text = str(message or "").casefold()
        return bool(text and any(word in text for word in RISK_WORDS))

    def _stop_cd2_tasks(self, batch_id: str, media_id: str) -> None:
        keys = [
            str(watch.get("cd2_key") or "")
            for watch in self.store.list_import_watches(batch_id=batch_id, media_id=media_id)
            if watch.get("cd2_key")
        ]
        if not keys:
            return
        errors = []
        try:
            self.cd2.pause(keys)
        except Exception as error:
            errors.append(f"暂停失败：{error}")
        try:
            self.cd2.cancel(keys)
        except Exception as error:
            errors.append(f"取消失败：{error}")
        if errors:
            self.logger.warning("RSS一条龙：" + "；".join(errors))

    def _rollback_card(
        self, batch: Dict[str, Any], media_id: str, code: str, message: str
    ) -> None:
        MediaActionService(self.store).rollback_monitored_import(
            media_id, failure_code=code, failure_message=message
        )
        for watch in self.store.list_import_watches(batch_id=batch["id"], media_id=media_id):
            watch.update({"state": "rolled_back", "updated_at": utc_now()})
            self.store.upsert_import_watch(watch)
        self._increment_batch(batch, failed=1, current_media_id="")

    def _pause_for_risk(self, batch: Dict[str, Any], media_id: str, message: str) -> None:
        self._rollback_card(batch, media_id, "cd2_risk_control", message)
        batch = self.store.get_import_batch(batch["id"]) or batch
        risk_count = int(batch.get("risk_count") or 0) + 1
        batch["risk_count"] = risk_count
        batch["error_message"] = message
        if risk_count >= self.config.risk_retry_limit:
            batch.update({"state": "failed", "finished_at": utc_now(), "updated_at": utc_now()})
            self.store.upsert_import_batch(batch)
            self.notify("RSS一条龙 CD2 风控", f"连续 {risk_count} 次命中风控，队列已停止")
            self._restore_and_finish(batch, final_state="failed")
            return
        resume_at = datetime.now(timezone.utc) + timedelta(seconds=self.config.risk_cooldown)
        batch.update({
            "state": "paused_risk",
            "resume_at": resume_at.isoformat(timespec="seconds"),
            "updated_at": utc_now(),
        })
        self.store.upsert_import_batch(batch)
        self.notify("RSS一条龙 CD2 风控", f"队列暂停至 {batch['resume_at']} 后自动继续")

    def _finish_queue(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        batch = self.store.get_import_batch(batch["id"]) or batch
        if self.store.count_media_states(["pending", "importing"]) > 0:
            return self.status()
        if self.store.list_import_watches(states=ACTIVE_WATCH_STATES):
            return self.status()
        if int(batch.get("succeeded") or 0) <= 0:
            self._restore_and_finish(batch, final_state="completed")
            return self.status()
        requested_at = datetime.now(timezone.utc)
        details = dict(batch.get("details") or {})
        details["waiting_scan_callback_at"] = requested_at.isoformat(timespec="seconds")
        batch.update({
            "state": "waiting_scan_callback",
            "current_media_id": "",
            "refresh_requested_at": requested_at.isoformat(timespec="seconds"),
            "scan_callback_deadline": (
                requested_at + timedelta(seconds=self.config.scan_callback_timeout)
            ).isoformat(timespec="seconds"),
            "details": details,
            "updated_at": utc_now(),
        })
        self.store.upsert_import_batch(batch)
        try:
            refresh_target = self.scanner.request_emby_refresh()
            refresh_server_id = str(refresh_target.get("server_id") or "").strip()
            if refresh_server_id and refresh_server_id != self.config.callback_server_id:
                raise RuntimeError("扫库节点服务器 ID 与回调服务器 ID 配置不一致")
            batch = self.store.get_import_batch(batch["id"]) or batch
            details = dict(batch.get("details") or {})
            details["refresh_target"] = refresh_target
            batch["details"] = details
            batch["updated_at"] = utc_now()
            self.store.upsert_import_batch(batch)
        except Exception as error:
            batch["error_message"] = f"发起 Emby 媒体库刷新失败：{error}"
            self.store.upsert_import_batch(batch)
            self._restore_and_finish(batch, final_state="failed")
        return self.status()

    def _supervise_scan_wait(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        deadline = _parse_time(batch.get("scan_callback_deadline"))
        if deadline and datetime.now(timezone.utc) >= deadline:
            batch["error_message"] = "等待 Emby scheduledtasks.completed 回调超时"
            details = dict(batch.get("details") or {})
            details["scan_callback_timeout_at"] = utc_now()
            batch["details"] = details
            self.store.upsert_import_batch(batch)
            self.notify("RSS一条龙扫库回调超时", batch["error_message"])
            self._restore_and_finish(batch, final_state="failed")
        return self.status()

    def _restore_and_finish(self, batch: Dict[str, Any], *, final_state: str) -> None:
        snapshot = self._batch_snapshot(batch)
        if snapshot is None:
            self._fail_batch_without_switch_snapshot(batch)
            return
        final_state = final_state if final_state in {"completed", "failed", "cancelled"} else "failed"
        try:
            self.controls.restore(snapshot)
        except ExternalControlError as error:
            details = dict(batch.get("details") or {})
            details["restore_final_state"] = final_state
            batch.update({
                "state": "restore_failed",
                "error_message": str(error),
                "details": details,
                "updated_at": utc_now(),
            })
            self.store.upsert_import_batch(batch)
            self.notify("RSS一条龙恢复外部开关失败", str(error))
            return
        details = dict(batch.get("details") or {})
        details.pop("restore_final_state", None)
        details["switches_restored_at"] = utc_now()
        batch.update({
            "state": final_state,
            "current_media_id": "",
            "resume_at": None,
            "details": details,
            "finished_at": utc_now(),
            "updated_at": utc_now(),
        })
        self.store.upsert_import_batch(batch)

    @staticmethod
    def _batch_snapshot(batch: Dict[str, Any]) -> Optional[ExternalSwitchSnapshot]:
        catchup = batch.get("original_catchup_enabled")
        scan = batch.get("original_scan_enabled")
        if catchup is None or scan is None:
            return None
        return ExternalSwitchSnapshot(
            catchup_enabled=bool(catchup),
            scan_enabled=bool(scan),
        )

    def _fail_batch_start(self, batch: Dict[str, Any], error: Exception) -> None:
        details = dict(batch.get("details") or {})
        details["switch_disable_failed_at"] = utc_now()
        batch.update({
            "state": "failed",
            "error_message": f"关闭追更/扫库失败：{error}",
            "details": details,
            "finished_at": utc_now(),
            "updated_at": utc_now(),
        })
        self.store.upsert_import_batch(batch)

    def _fail_batch_without_switch_snapshot(self, batch: Dict[str, Any]) -> None:
        message = "待入库批次缺少原始开关快照，已停止队列；请人工核对追更和扫库开关"
        details = dict(batch.get("details") or {})
        details["switch_snapshot_missing_at"] = utc_now()
        batch.update({
            "state": "failed",
            "error_message": message,
            "details": details,
            "finished_at": utc_now(),
            "updated_at": utc_now(),
        })
        self.store.upsert_import_batch(batch)
        self.notify("RSS一条龙待入库保护停止", message)

    def _increment_batch(
        self,
        batch: Dict[str, Any],
        *,
        succeeded: int = 0,
        failed: int = 0,
        current_media_id: Optional[str] = None,
    ) -> None:
        current = self.store.get_import_batch(batch["id"]) or batch
        current["succeeded"] = int(current.get("succeeded") or 0) + int(succeeded)
        current["failed"] = int(current.get("failed") or 0) + int(failed)
        if current_media_id is not None:
            current["current_media_id"] = current_media_id
        current["updated_at"] = utc_now()
        self.store.upsert_import_batch(current)
        batch.update(current)
