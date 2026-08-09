"""Durable serial pending-import queue with CloudDrive2 monitoring."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.parse import unquote

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
    text = unquote(str(value or "").strip()).replace("\\", "/")
    if not text:
        return ""
    normalized = str(PurePosixPath(text))
    return normalized.casefold()


def _paths_match(left: object, right: object) -> bool:
    first = _normalized_path(left)
    second = _normalized_path(right)
    if not first or not second:
        return False
    if first == second:
        return True
    first_parts = tuple(part for part in first.split("/") if part)
    second_parts = tuple(part for part in second.split("/") if part)
    shorter, longer = sorted((first_parts, second_parts), key=len)
    return len(shorter) >= 2 and tuple(longer[-len(shorter):]) == tuple(shorter)


def _sizes_match(reported: object, expected: object) -> bool:
    reported_size = int(reported or 0)
    expected_size = int(expected or 0)
    return reported_size == expected_size or (reported_size == 0 and expected_size > 0)


def _upload_signature(upload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "dest_path": _normalized_path(upload.get("dest_path")),
        "size": int(upload.get("size") or 0),
        "transferred_bytes": int(upload.get("transferred_bytes") or 0),
        "status": str(upload.get("status") or "").strip().casefold(),
        "error_message": str(upload.get("error_message") or ""),
    }


def _cloud_file_signature(cloud_file: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(cloud_file.get("id") or ""),
        "full_path": _normalized_path(cloud_file.get("full_path")),
        "size": int(cloud_file.get("size") or 0),
        "create_time": str(cloud_file.get("create_time") or ""),
        "write_time": str(cloud_file.get("write_time") or ""),
    }


@dataclass
class PendingImportConfig:
    cd2_dest_root: str
    plugin_staging_roots: List[str] = field(default_factory=list)
    plugin_staging_root: str = ""
    discovery_timeout: int = 180
    card_timeout: int = 7200
    poll_interval: int = 10
    cloud_verify_delay: int = 20
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
        self._resolved_cd2_dest_root = ""

    def status(self) -> Dict[str, Any]:
        batch = self.store.latest_active_import_batch()
        return {
            "running": bool(batch),
            "batch": batch,
            "pending": self.store.count_media_states(["pending"]),
            "importing": self.store.count_media_states(["importing"]),
            "active_watches": len(self.store.list_import_watches(states=ACTIVE_WATCH_STATES)),
        }

    def preflight(self, *, manage_external_switches: bool = True) -> None:
        self.config.validate()
        if not self.cd2.ready:
            raise RuntimeError("CloudDrive2 gRPC 地址或令牌未配置")
        if not self.scanner.ready:
            raise RuntimeError("Emby 扫库配置不完整")
        if manage_external_switches and not self.controls.ready:
            raise RuntimeError("追更或外部扫库联动配置不完整")

    def run(self, trigger_source: str) -> Dict[str, Any]:
        batch = self.store.latest_active_import_batch()
        if batch:
            state = str(batch.get("state") or "")
            manage_external_switches = self._manages_external_switches(batch)
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
            if manage_external_switches:
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
            manage_external_switches = (
                str(trigger_source or "").strip().casefold() != "manual"
            )
            self.preflight(manage_external_switches=manage_external_switches)
            now = utc_now()
            if manage_external_switches:
                snapshot = self.controls.snapshot()
                batch = {
                    "id": uuid.uuid4().hex,
                    "state": "switch_snapshot_saved",
                    "trigger_source": str(trigger_source or "cron"),
                    "current_media_id": "",
                    "original_catchup_enabled": snapshot.catchup_enabled,
                    "original_scan_enabled": snapshot.scan_enabled,
                    "succeeded": 0,
                    "failed": 0,
                    "risk_count": 0,
                    "details": {
                        "manage_external_switches": True,
                        "switch_snapshot_saved_at": now,
                    },
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
            else:
                batch = {
                    "id": uuid.uuid4().hex,
                    "state": "running",
                    "trigger_source": "manual",
                    "current_media_id": "",
                    "original_catchup_enabled": None,
                    "original_scan_enabled": None,
                    "succeeded": 0,
                    "failed": 0,
                    "risk_count": 0,
                    "details": {
                        "manage_external_switches": False,
                        "switch_management_skipped_at": now,
                    },
                    "created_at": now,
                    "updated_at": now,
                }
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
        event_name = str(event.get("event_name") or "").strip().casefold()
        if event_name not in COMPLETED_SCAN_EVENTS:
            return {"accepted": False, "message": "不是 scheduledtasks.completed 回调"}
        requested_at = _parse_time(batch.get("refresh_requested_at"))
        event_time = _parse_time(event.get("event_time")) or datetime.now(timezone.utc)
        if requested_at and event_time < requested_at:
            return {"accepted": False, "message": "回调早于本轮媒体库刷新请求"}
        refresh_target = dict(
            (batch.get("details") or {}).get("refresh_target") or {}
        )
        expected_server_id = str(
            refresh_target.get("server_id") or self.config.callback_server_id or ""
        ).strip()
        callback_server_id = str(event.get("server_id") or "").strip()
        if (
            expected_server_id
            and callback_server_id
            and callback_server_id != expected_server_id
        ):
            return {"accepted": False, "message": "回调 server_id 与配置不匹配"}
        expected_task_id = str(
            refresh_target.get("task_id") or self.config.callback_task_id or ""
        ).strip()
        expected_task_name = str(
            refresh_target.get("task_name") or self.config.callback_task_name or ""
        ).strip()
        callback_task_id = str(event.get("task_id") or "").strip()
        callback_task_name = str(event.get("task_name") or "").strip()
        callback_has_identity = bool(callback_task_id or callback_task_name)
        if callback_task_id and expected_task_id:
            if callback_task_id != expected_task_id:
                return {"accepted": False, "message": "回调 task_id 与扫库任务不匹配"}
        elif callback_task_name and expected_task_name:
            if callback_task_name.casefold() != expected_task_name.casefold():
                return {"accepted": False, "message": "回调 task_name 与扫库任务不匹配"}

        # Emby Webhooks can emit ScheduledTasks.Completed without the nested
        # Task/Server object.  The callback secret has already been verified by
        # the API route; use the configured Emby task as a second factor before
        # accepting an identifierless event.
        api_confirmation = None
        if not callback_has_identity:
            try:
                task = self.scanner.emby_task_status(
                    expected_task_id, expected_task_name
                )
            except Exception as error:
                return {
                    "accepted": False,
                    "message": f"回调未携带扫库任务标识，Emby 状态核对失败：{error}",
                }
            if not self._scan_task_completed_after_refresh(batch, task):
                return {
                    "accepted": False,
                    "message": "回调未携带扫库任务标识，Emby 尚未确认本轮扫库完成",
                }
            api_confirmation = task
        details = dict(batch.get("details") or {})
        details["scan_callback"] = copy.deepcopy(event)
        if api_confirmation:
            details["scan_callback_api_confirmation"] = copy.deepcopy(api_confirmation)
        details["scan_completed_at"] = utc_now()
        batch["details"] = details
        batch["updated_at"] = utc_now()
        self.store.upsert_import_batch(batch)
        manages_switches = self._manages_external_switches(batch)
        self._restore_and_finish(batch, final_state="completed")
        return {
            "accepted": True,
            "message": (
                "扫库完成回调已确认，外部开关已恢复"
                if manages_switches
                else "扫库完成回调已确认"
            ),
        }

    def cancel_scan_wait(self) -> Dict[str, Any]:
        """End an Emby callback wait without changing imported media records."""

        batch = self.store.latest_active_import_batch()
        if not batch:
            return {"accepted": False, "message": "当前没有运行中的待入库批次"}
        if str(batch.get("state") or "") != "waiting_scan_callback":
            return {"accepted": False, "message": "当前批次不在等待 Emby 扫库完成"}

        details = dict(batch.get("details") or {})
        details["scan_wait_cancelled_at"] = utc_now()
        batch.update({
            "details": details,
            "error_message": "",
            "updated_at": utc_now(),
        })
        self.store.upsert_import_batch(batch)
        manages_switches = self._manages_external_switches(batch)
        self._restore_and_finish(batch, final_state="cancelled")

        finished = self.store.get_import_batch(batch["id"]) or batch
        if str(finished.get("state") or "") == "restore_failed":
            return {
                "accepted": False,
                "message": str(finished.get("error_message") or "恢复外部开关失败"),
            }
        return {
            "accepted": True,
            "message": (
                "已结束扫库等待并恢复外部开关"
                if manages_switches
                else "已结束扫库等待"
            ),
        }

    @staticmethod
    def _scan_task_completed_after_refresh(
        batch: Dict[str, Any], task: Dict[str, Any]
    ) -> bool:
        requested_at = _parse_time(batch.get("refresh_requested_at"))
        last_started_at = _parse_time(task.get("last_started_at"))
        last_finished_at = _parse_time(task.get("last_finished_at"))
        last_status = str(task.get("last_status") or "").strip().casefold()
        return bool(
            requested_at
            and last_started_at
            and last_finished_at
            and last_started_at >= requested_at
            and last_status in {"completed", "success", "succeeded"}
        )

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
        baseline_uploads = self.cd2.list_uploads()
        cloud_baselines = self._cloud_baselines(item)
        try:
            prepared = MediaActionService(self.store).prepare_monitored_import(media_id)
            created = list(prepared.get("created_mappings") or [])
            if not created:
                MediaActionService(self.store).finalize_monitored_import(media_id)
                self._increment_batch(batch, succeeded=1, current_media_id="")
                return "success"
            watches = self._create_watches(
                batch,
                media_id,
                created,
                baseline_uploads,
                cloud_baselines,
            )
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
        baseline_uploads: Iterable[Dict[str, Any]],
        cloud_baselines: Dict[str, Optional[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        result = []
        now = datetime.now(timezone.utc)
        for mapping in mappings:
            local_path = str(mapping.get("local_hardlink_path") or "")
            expected_path = self._cd2_dest_path(local_path)
            expected_size = int(mapping.get("file_size") or 0)
            matching_baseline_tasks = {
                str(row.get("key") or ""): _upload_signature(row)
                for row in baseline_uploads
                if row.get("key")
                and _paths_match(row.get("dest_path"), expected_path)
                and _sizes_match(row.get("size"), expected_size)
            }
            watch = {
                "id": uuid.uuid4().hex,
                "batch_id": batch["id"],
                "media_id": media_id,
                "file_index": int(mapping.get("file_index") or 0),
                "state": "waiting_task",
                "local_hardlink_path": local_path,
                "expected_cd2_dest_path": expected_path,
                "expected_mp_library_path": str(mapping.get("inventory_path") or ""),
                "cd2_key": "",
                "file_size": expected_size,
                "transferred_bytes": 0,
                "details": {
                    "baseline_keys": sorted(matching_baseline_tasks),
                    "baseline_tasks": matching_baseline_tasks,
                    "cloud_baseline": cloud_baselines.get(
                        _normalized_path(expected_path)
                    ),
                    "cloud_verify_after": (
                        now + timedelta(seconds=max(0, self.config.cloud_verify_delay))
                    ).isoformat(timespec="seconds"),
                    "discovery_deadline": (
                        now
                        + timedelta(seconds=self.config.discovery_timeout)
                    ).isoformat(timespec="seconds"),
                    "card_deadline": (
                        now
                        + timedelta(seconds=self.config.card_timeout)
                    ).isoformat(timespec="seconds"),
                },
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            self.store.upsert_import_watch(watch)
            result.append(watch)
        return result

    def _cloud_baselines(
        self, item: Dict[str, Any]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        expected_paths = []
        mappings = self.store.list_file_mappings(
            item.get("downloader_id"), item.get("info_hash")
        )
        for mapping in mappings:
            if bool(mapping.get("inventory_exists")):
                continue
            local_path = str(mapping.get("local_hardlink_path") or "").strip()
            if not local_path:
                continue
            expected_path = self._cd2_dest_path(local_path)
            expected_paths.append(expected_path)
        return self.cd2.find_files(expected_paths, force_refresh=True)

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
            PurePosixPath(self._destination_root())
            / PurePosixPath(*relative.parts)
        )

    def _destination_root(self) -> str:
        if self._resolved_cd2_dest_root:
            return self._resolved_cd2_dest_root
        configured = str(self.config.cd2_dest_root or "").strip()
        resolved = configured
        resolver = getattr(self.cd2, "resolve_destination_root", None)
        if callable(resolver):
            try:
                resolved = str(resolver(configured) or configured).strip()
            except Exception as error:
                self.logger.warning(f"RSS一条龙：CD2 目标根目录自动校正失败：{error}")
        self._resolved_cd2_dest_root = resolved or configured
        if _normalized_path(self._resolved_cd2_dest_root) != _normalized_path(configured):
            self.logger.warning(
                "RSS一条龙：CD2 目标根目录已从挂载路径校正为 "
                f"{self._resolved_cd2_dest_root}"
            )
        return self._resolved_cd2_dest_root

    def _refresh_watch_destination_paths(self, batch_id: str, media_id: str) -> None:
        for watch in self.store.list_import_watches(
            batch_id=batch_id, media_id=media_id
        ):
            local_path = str(watch.get("local_hardlink_path") or "").strip()
            if not local_path:
                continue
            expected_path = self._cd2_dest_path(local_path)
            previous_path = str(watch.get("expected_cd2_dest_path") or "")
            if _normalized_path(expected_path) == _normalized_path(previous_path):
                continue
            details = dict(watch.get("details") or {})
            details["destination_path_adjusted_from"] = previous_path
            watch.update({
                "expected_cd2_dest_path": expected_path,
                "details": details,
                "updated_at": utc_now(),
            })
            self.store.upsert_import_watch(watch)

    def _monitor_card(
        self,
        batch: Dict[str, Any],
        media_id: str,
        watches: List[Dict[str, Any]],
    ) -> str:
        self._refresh_watch_destination_paths(batch["id"], media_id)
        while not self.stop_event.is_set():
            uploads = self.cd2.list_uploads()
            by_key = {str(row.get("key") or ""): row for row in uploads if row.get("key")}
            current_watches = self.store.list_import_watches(
                batch_id=batch["id"], media_id=media_id
            )
            now = datetime.now(timezone.utc)
            due_paths = []
            for watch in current_watches:
                if str(watch.get("state") or "") == "done":
                    continue
                key = str(watch.get("cd2_key") or "")
                if key and key in by_key:
                    continue
                verify_after = _parse_time(
                    (watch.get("details") or {}).get("cloud_verify_after")
                )
                if verify_after and now >= verify_after:
                    due_paths.append(watch.get("expected_cd2_dest_path"))
            cloud_results: Dict[str, Optional[Dict[str, Any]]] = {}
            cloud_error = ""
            if due_paths:
                try:
                    cloud_results = self.cd2.find_files(
                        due_paths, force_refresh=True
                    )
                except Exception as error:
                    cloud_results = {
                        _normalized_path(path): None for path in due_paths
                    }
                    cloud_error = str(error)
            changed = False
            terminal = True
            failure = ""
            risk = False
            for watch in current_watches:
                if str(watch.get("state") or "") == "done":
                    continue
                terminal = False
                result = self._observe_watch(
                    watch,
                    uploads,
                    by_key,
                    cloud_results=cloud_results,
                    cloud_error=cloud_error,
                )
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
        *,
        cloud_results: Optional[Dict[str, Optional[Dict[str, Any]]]] = None,
        cloud_error: str = "",
    ) -> str:
        now = datetime.now(timezone.utc)
        details = dict(watch.get("details") or {})
        task = None
        key = str(watch.get("cd2_key") or "")
        if key:
            task = by_key.get(key)
        else:
            baseline = set(details.get("baseline_keys") or [])
            baseline_tasks = dict(details.get("baseline_tasks") or {})
            expected_path = _normalized_path(watch.get("expected_cd2_dest_path"))
            expected_size = int(watch.get("file_size") or 0)
            matching_tasks = [
                row for row in uploads
                if _paths_match(row.get("dest_path"), expected_path)
                and _sizes_match(row.get("size"), expected_size)
            ]
            candidates = [
                row for row in matching_tasks
                if (
                    str(row.get("key") or "") not in baseline
                    or baseline_tasks.get(str(row.get("key") or ""))
                    != _upload_signature(row)
                )
            ]
            if len(candidates) == 1:
                task = candidates[0]
                watch["cd2_key"] = str(task.get("key") or "")
                watch["state"] = "watching"
            elif len(candidates) > 1:
                return "failed:CD2 出现多个相同完整路径和大小的上传任务"
            elif len(matching_tasks) == 1:
                task = matching_tasks[0]
                watch["cd2_key"] = str(task.get("key") or "")
                watch["state"] = "watching"
            elif len(matching_tasks) > 1:
                return "failed:CD2 出现多个相同完整路径和大小的上传任务"
            else:
                interrupted = [
                    signature
                    for signature in baseline_tasks.values()
                    if str(signature.get("status") or "") in {"transfer", "pause"}
                    and int(signature.get("transferred_bytes") or 0) > 0
                ]
                if interrupted:
                    transferred = max(
                        int(signature.get("transferred_bytes") or 0)
                        for signature in interrupted
                    )
                    details["baseline_real_transfer"] = interrupted
                    watch.update({
                        "state": "rolling_back",
                        "transferred_bytes": transferred,
                        "details": details,
                        "updated_at": utc_now(),
                    })
                    self.store.upsert_import_watch(watch)
                    return f"failed:CD2 旧上传任务已发生真实传输（{transferred} 字节）"
        if not task:
            discovery_deadline = _parse_time(details.get("discovery_deadline"))
            card_deadline = _parse_time(details.get("card_deadline"))
            if card_deadline and now >= card_deadline:
                return "failed:CD2 单卡监控超过最终超时"
            missing_task_deadline = None
            if key:
                missing_since = _parse_time(details.get("task_missing_since"))
                if not missing_since:
                    missing_since = now
                    details["task_missing_since"] = now.isoformat(timespec="seconds")
                missing_task_deadline = missing_since + timedelta(
                    seconds=self.config.discovery_timeout
                )
            cloud_path_key = _normalized_path(
                watch.get("expected_cd2_dest_path")
            )
            if cloud_results is not None and cloud_path_key in cloud_results:
                if cloud_error:
                    details["last_cloud_check_at"] = utc_now()
                    details["last_cloud_error"] = cloud_error
                else:
                    cloud_file = cloud_results.get(cloud_path_key)
                    details["last_cloud_check_at"] = utc_now()
                    details["last_cloud_file"] = cloud_file
                    details.pop("last_cloud_error", None)
                    completion_source = self._cloud_file_completion_source(
                        watch, cloud_file
                    )
                    if key and completion_source:
                        completion_source = "cloud_file_after_task"
                    if (
                        completion_source
                        and (
                            completion_source != "cloud_existing"
                            or not discovery_deadline
                            or now >= discovery_deadline
                        )
                    ):
                        details["completion_source"] = completion_source
                        watch.update({
                            "state": "done",
                            "details": details,
                            "updated_at": utc_now(),
                        })
                        self.store.upsert_import_watch(watch)
                        return "done"
                details["cloud_verify_after"] = (
                    now + timedelta(seconds=max(10, self.config.poll_interval))
                ).isoformat(timespec="seconds")
            if not key and discovery_deadline and now >= discovery_deadline:
                suffix = ""
                if details.get("last_cloud_error"):
                    suffix = f"；云端文件校验失败：{details['last_cloud_error']}"
                return f"failed:CD2 未发现本次上传任务或新生成的目标文件{suffix}"
            if key and missing_task_deadline and now >= missing_task_deadline:
                return "failed:CD2 上传任务已消失且目标文件未出现"
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
        details.pop("task_missing_since", None)
        if self._is_risk(error_message):
            watch.update({"state": "risk_control", "details": details, "updated_at": utc_now()})
            self.store.upsert_import_watch(watch)
            return "risk"
        if status in {"finish", "skipped"}:
            watch.update({"state": "done", "details": details, "updated_at": utc_now()})
            self.store.upsert_import_watch(watch)
            return "done"
        if status in {"transfer", "pause"}:
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
            paused_transfer = status == "pause" and transferred > 0 and grace_elapsed
            if transferred >= threshold or paused_transfer or (
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
    def _cloud_file_completion_source(
        watch: Dict[str, Any], cloud_file: Optional[Dict[str, Any]]
    ) -> str:
        if not cloud_file or bool(cloud_file.get("is_directory")):
            return ""
        if not _paths_match(
            cloud_file.get("full_path"), watch.get("expected_cd2_dest_path")
        ):
            return ""
        if int(cloud_file.get("size") or 0) != int(watch.get("file_size") or 0):
            return ""
        details = dict(watch.get("details") or {})
        baseline = details.get("cloud_baseline")
        if not baseline:
            return "cloud_file"
        if _cloud_file_signature(cloud_file) != _cloud_file_signature(baseline):
            return "cloud_file"
        return "cloud_existing"

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
        now = datetime.now(timezone.utc)
        if not deadline or now < deadline:
            return self.status()

        details = dict(batch.get("details") or {})
        refresh_target = dict(details.get("refresh_target") or {})
        interval = max(300, int(self.config.scan_callback_timeout or 7200))
        try:
            task = self.scanner.emby_task_status(
                str(refresh_target.get("task_id") or self.config.callback_task_id),
                str(refresh_target.get("task_name") or self.config.callback_task_name),
            )
        except Exception as error:
            next_deadline = now + timedelta(seconds=interval)
            details["scan_status_check_error"] = str(error)
            details["scan_status_check_error_at"] = utc_now()
            details["scan_status_check_count"] = int(
                details.get("scan_status_check_count") or 0
            ) + 1
            batch.update({
                "error_message": "",
                "scan_callback_deadline": next_deadline.isoformat(timespec="seconds"),
                "details": details,
                "updated_at": utc_now(),
            })
            self.store.upsert_import_batch(batch)
            self.notify(
                "RSS一条龙扫库状态检查失败",
                f"暂时无法查询 Emby 扫库状态，已继续等待：{error}",
            )
            return self.status()

        details.pop("scan_status_check_error", None)
        details.pop("scan_status_check_error_at", None)
        details["last_scan_task_status"] = copy.deepcopy(task)
        details["last_scan_status_checked_at"] = utc_now()
        details["scan_status_check_count"] = int(
            details.get("scan_status_check_count") or 0
        ) + 1
        if task.get("is_running"):
            next_deadline = now + timedelta(seconds=interval)
            details["scan_wait_extended_at"] = utc_now()
            batch.update({
                "error_message": "",
                "scan_callback_deadline": next_deadline.isoformat(timespec="seconds"),
                "details": details,
                "updated_at": utc_now(),
            })
            self.store.upsert_import_batch(batch)
            return self.status()

        requested_at = _parse_time(batch.get("refresh_requested_at"))
        last_started_at = _parse_time(task.get("last_started_at"))
        last_finished_at = _parse_time(task.get("last_finished_at"))
        last_status = str(task.get("last_status") or "").strip().casefold()
        completed_statuses = {"completed", "success", "succeeded"}
        if (
            requested_at
            and last_started_at
            and last_finished_at
            and last_started_at >= requested_at
            and last_status in completed_statuses
        ):
            details["scan_completed_via_api"] = copy.deepcopy(task)
            details["scan_completed_at"] = utc_now()
            batch.update({
                "error_message": "",
                "details": details,
                "updated_at": utc_now(),
            })
            self.store.upsert_import_batch(batch)
            self.notify(
                "RSS一条龙扫库完成",
                "未收到 Emby 回调，但 API 已确认本轮媒体库扫描完成",
            )
            self._restore_and_finish(batch, final_state="completed")
            return self.status()

        batch["error_message"] = (
            "等待 Emby 回调超时，API 显示扫库任务未运行，"
            f"最近状态为 {task.get('last_status') or task.get('state') or '未知'}"
        )
        details["scan_callback_timeout_at"] = utc_now()
        batch["details"] = details
        self.store.upsert_import_batch(batch)
        self.notify("RSS一条龙扫库回调超时", batch["error_message"])
        self._restore_and_finish(batch, final_state="failed")
        return self.status()

    def _restore_and_finish(self, batch: Dict[str, Any], *, final_state: str) -> None:
        final_state = final_state if final_state in {"completed", "failed", "cancelled"} else "failed"
        details = dict(batch.get("details") or {})
        if self._manages_external_switches(batch):
            snapshot = self._batch_snapshot(batch)
            if snapshot is None:
                self._fail_batch_without_switch_snapshot(batch)
                return
            try:
                self.controls.restore(snapshot)
            except ExternalControlError as error:
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
            details["switches_restored_at"] = utc_now()
        else:
            details["switch_restore_skipped_at"] = utc_now()
        if final_state == "completed":
            try:
                details["post_scan_task"] = {
                    **self.scanner.start_emby_task("Extract MediaInfo"),
                    "triggered_at": utc_now(),
                }
                details.pop("post_scan_task_error", None)
            except Exception as error:
                details["post_scan_task_error"] = str(error)
                details["post_scan_task_error_at"] = utc_now()
                self.notify("RSS一条龙 MediaInfo 任务启动失败", str(error))
        details.pop("restore_final_state", None)
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
    def _manages_external_switches(batch: Dict[str, Any]) -> bool:
        details = dict(batch.get("details") or {})
        if "manage_external_switches" in details:
            return bool(details.get("manage_external_switches"))
        return True

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
