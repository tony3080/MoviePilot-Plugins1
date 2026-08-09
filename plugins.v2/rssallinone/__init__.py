"""RSS All-in-One framework plugin for MoviePilot V2."""

from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qs

from app.log import logger
from app.plugins import _PluginBase

from .capabilities import runtime_capabilities
from .clouddrive_client import CloudDriveClient
from .database import SQLiteStore, utc_now
from .external_controls import CatchupSwitchClient, ExternalControlBundle, ScanSystemClient
from .file_manager import FILE_BATCH_TASK_TYPE, FileManagerError, LocalFileManagerService
from .inventory import LocalInventoryChecker
from .layout import LibraryLayout, default_layout_config
from .media_actions import (
    MediaActionError,
    MediaActionService,
    MediaInventoryRefreshService,
)
from .pending_import import PendingImportConfig, PendingImportCoordinator
from .qb_sync import (
    MoviePilotQbGateway,
    QB_TASK_TYPE,
    QbSyncService,
    RssTaskQbScope,
)
from .rss_feed import RssFeedError, RssPreviewService
from .rss_execute import RSS_RUN_TASK_TYPE, RssExecutionError, RssExecutionService
from .rss_tasks import normalize_rss_tasks


PLUGIN_ID = "RssAllInOne"
PLUGIN_DIR = Path(__file__).resolve().parent
RSS_MAX_CONCURRENT_RUNS = 2


class RssAllInOne(_PluginBase):
    plugin_name = "RSS一条龙"
    plugin_desc = "统一管理 PT RSS、qBittorrent、媒体识别与硬链接入库流程。"
    plugin_icon = (
        "https://raw.githubusercontent.com/tony3080/MoviePilot-Plugins1/"
        "main/plugins.v2/rssallinone/assets/dragon.png"
    )
    plugin_version = "0.13.18"
    plugin_author = "tony3080"
    author_url = "https://github.com/tony3080"
    plugin_config_prefix = "rssallinone_"
    plugin_order = 45
    auth_level = 2

    _enabled = False
    _database_filename = "rssallinone.db"
    _rss_enabled = True
    _inventory_root = ""
    _cd2_grpc_addr = ""
    _cd2_token = ""
    _cd2_plugin_staging_root = ""
    _cd2_dest_root = ""
    _pending_import_cron = "0 1 * * *"
    _catchup_base_url = ""
    _catchup_page_id = ""
    _catchup_token = ""
    _scan_base_url = ""
    _scan_username = ""
    _scan_password = ""
    _scan_setting_name = ""
    _scan_target_name = ""
    _scan_callback_secret = ""
    _scan_callback_server_id = ""
    _scan_callback_task_id = ""
    _scan_callback_task_name = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._store: Optional[SQLiteStore] = None
        self._startup_error = ""
        self._qb_refresh_lock = threading.Lock()
        self._qb_delete_lock = threading.Lock()
        self._rss_queue_lock = threading.RLock()
        self._rss_active_run_ids: Dict[str, str] = {}
        self._rss_active_downloaders: Dict[str, str] = {}
        self._media_action_lock = threading.Lock()
        self._file_scan_lock = threading.Lock()
        self._pending_import_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._rss_stop_event = threading.Event()
        self._runtime_config: Dict[str, Any] = {}
        self._source_routes: List[Dict[str, Any]] = []
        self._library_layout = LibraryLayout("", [])

    def init_plugin(self, config: dict = None) -> None:
        config = config or {}
        self._runtime_config = deepcopy(config)
        defaults = self._default_config()
        self._enabled = bool(config.get("enabled", False))
        self._rss_enabled = bool(config.get("rss_enabled", True))
        self._database_filename = self._safe_database_filename(
            config.get("database_filename") or "rssallinone.db"
        )
        self._inventory_root = str(
            config.get("inventory_root", defaults["inventory_root"]) or ""
        ).strip()
        self._source_routes = deepcopy(
            config.get("source_routes", defaults["source_routes"])
        )
        self._library_layout = LibraryLayout.from_config(
            self._inventory_root,
            self._source_routes,
        )
        self._cd2_grpc_addr = str(config.get("cd2_grpc_addr") or "").strip()
        self._cd2_token = str(config.get("cd2_token") or "").strip()
        self._cd2_plugin_staging_root = str(
            config.get("cd2_plugin_staging_root") or ""
        ).strip()
        self._cd2_dest_root = str(config.get("cd2_dest_root") or "").strip()
        self._pending_import_cron = str(
            config.get("pending_import_cron") or defaults["pending_import_cron"]
        ).strip()
        self._catchup_base_url = str(config.get("catchup_base_url") or "").strip()
        self._catchup_page_id = str(config.get("catchup_page_id") or "").strip()
        self._catchup_token = str(config.get("catchup_token") or "").strip()
        self._scan_base_url = str(config.get("scan_base_url") or "").strip()
        self._scan_username = str(config.get("scan_username") or "").strip()
        self._scan_password = str(config.get("scan_password") or "").strip()
        self._scan_setting_name = str(config.get("scan_setting_name") or "").strip()
        self._scan_target_name = str(config.get("scan_target_name") or "").strip()
        self._scan_callback_secret = str(config.get("scan_callback_secret") or "").strip()
        self._scan_callback_server_id = str(
            config.get("scan_callback_server_id") or ""
        ).strip()
        self._scan_callback_task_id = str(
            config.get("scan_callback_task_id") or ""
        ).strip()
        self._scan_callback_task_name = str(
            config.get("scan_callback_task_name") or ""
        ).strip()

        self._startup_error = ""
        self._stop_event.clear()
        if self._rss_enabled:
            self._rss_stop_event.clear()
        else:
            self._rss_stop_event.set()
        try:
            self._store = SQLiteStore(self._database_path())
            self._store.initialize()
            recovered = self._store.recover_incomplete_tasks(
                preserve_queued_types={RSS_RUN_TASK_TYPE}
            )
            if recovered:
                logger.warning(f"RSS一条龙：已终止 {recovered} 个重启前未完成的后台任务")
            cleaned_jobs = self._store.cleanup_completed_qb_delete_jobs()
            if cleaned_jobs:
                logger.info(f"RSS一条龙：已清理 {cleaned_jobs} 个历史 qB 删除计划")
            self._dispatch_rss_queue()
        except Exception as error:
            self._store = None
            self._startup_error = str(error)
            logger.error(f"RSS一条龙：初始化 SQLite 失败：{error}", exc_info=True)

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        return "vue", "dist/assets"

    @staticmethod
    def get_sidebar_nav() -> List[Dict[str, Any]]:
        return [{
            "name": "RSS一条龙",
            "icon": "tabler:dragon",
            "path": "/rssallinone",
            "nav_key": "rssallinone",
        }]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [], self._default_config()

    @staticmethod
    def get_page() -> List[dict]:
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled or not self._store:
            return []
        services: List[Dict[str, Any]] = []
        try:
            from apscheduler.triggers.cron import CronTrigger

            for task in self._store.list_all_rss_tasks():
                if not task.get("enabled"):
                    continue
                config = task.get("config") if isinstance(task.get("config"), dict) else {}
                task_id = str(task.get("id") or "").strip()
                task_name = str(task.get("name") or task_id).strip()
                rss_url = str(config.get("rss_url") or "").strip()
                rss_cron = str(config.get("rss_cron") or "").strip()
                if rss_url and rss_cron:
                    try:
                        trigger = CronTrigger.from_crontab(rss_cron)
                    except (TypeError, ValueError) as error:
                        logger.error(
                            f"RSS一条龙：任务 {task_name} 的 RSS CRON 无效：{error}"
                        )
                    else:
                        services.append({
                            "id": f"RssAllInOne.Rss.{task_id}",
                            "name": f"RSS一条龙 RSS：{task_name}",
                            "trigger": trigger,
                            "func": self._scheduled_rss_run,
                            "func_kwargs": {"task_id": task_id},
                        })

                start_cron = str(config.get("start_cron") or "").strip()
                downloader = str(config.get("qb_downloader") or "").strip()
                category = str(config.get("qb_category") or "").strip()
                if start_cron and downloader and category:
                    try:
                        start_trigger = CronTrigger.from_crontab(start_cron)
                    except (TypeError, ValueError) as error:
                        logger.error(
                            f"RSS一条龙：任务 {task_name} 的开始任务 CRON 无效：{error}"
                        )
                    else:
                        services.append({
                            "id": f"RssAllInOne.Start.{task_id}",
                            "name": f"RSS一条龙 开始任务：{task_name}",
                            "trigger": start_trigger,
                            "func": self._scheduled_rss_start,
                            "func_kwargs": {"task_id": task_id},
                        })
        except ImportError:
            logger.error("RSS一条龙：缺少 APScheduler，无法注册 RSS CRON")
        try:
            from apscheduler.triggers.cron import CronTrigger

            services.append({
                "id": "RssAllInOne.QbDeleteJobs",
                "name": "RSS一条龙 qB 到期删除任务",
                "trigger": CronTrigger.from_crontab("* * * * *"),
                "func": self._scheduled_qb_deletes,
                "func_kwargs": {},
            })
        except ImportError:
            logger.error("RSS一条龙：缺少 APScheduler，无法执行 qB 到期删除任务")
        try:
            from apscheduler.triggers.cron import CronTrigger

            if self._pending_import_cron:
                services.append({
                    "id": "RssAllInOne.PendingImportCron",
                    "name": "RSS一条龙 待入库队列",
                    "trigger": CronTrigger.from_crontab(self._pending_import_cron),
                    "func": self._scheduled_pending_import,
                    "func_kwargs": {},
                })
            services.append({
                "id": "RssAllInOne.PendingImportSupervisor",
                "name": "RSS一条龙 待入库恢复检查",
                "trigger": CronTrigger.from_crontab("* * * * *"),
                "func": self._supervise_pending_import,
                "func_kwargs": {},
            })
        except (ImportError, TypeError, ValueError) as error:
            logger.error(f"RSS一条龙：待入库 CRON 无法注册：{error}")
        return services

    def stop_service(self) -> None:
        self._stop_event.set()
        self._rss_stop_event.set()
        self._store = None

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            self._api("/qb/item/refresh", self.api_qb_item_refresh, "POST", "刷新单个 QB 任务"),
            self._api("/qb/item/identify", self.api_qb_item_identify, "POST", "手动识别单个 QB 任务"),
            self._api("/qb/delete", self.api_qb_delete, "POST", "删除 QB 任务并保留下载文件"),
            self._api("/qb/completed", self.api_qb_completed, "POST", "接收 qB 下载完成回调"),
            self._api("/media/delete", self.api_media_delete, "POST", "删除插件媒体记录"),
            self._api("/media/action", self.api_media_action, "POST", "批量执行入库管理操作"),
            self._api("/import/run", self.api_pending_import_run, "POST", "立即处理待入库队列"),
            self._api("/import/status", self.api_pending_import_status, "GET", "读取待入库队列状态"),
            self._api(
                "/external/catchup/control",
                self.api_external_catchup_control,
                "POST",
                "读取或切换 Emby 追更开关",
            ),
            self._api(
                "/external/scan/control",
                self.api_external_scan_control,
                "POST",
                "读取或切换 SA 扫库开关",
            ),
            self._api(
                "/emby/scheduledtasks/completed",
                self.api_emby_scheduled_completed,
                "POST",
                "接收 Emby 扫库完成回调",
                auth="none",
            ),
            self._api("/media/refresh", self.api_media_refresh, "POST", "刷新入库管理媒体记录"),
            self._api(
                "/media/inventory/refresh-batch",
                self.api_media_inventory_refresh_batch,
                "POST",
                "批量复查已入库库存",
            ),
            self._api("/files/browse", self.api_files_browse, "GET", "浏览本地文件夹"),
            self._api("/files/recognize", self.api_files_recognize, "POST", "识别单个本地文件或文件夹"),
            self._api("/files/recognize-batch", self.api_files_recognize_batch, "POST", "批量识别当前目录"),
            self._api("/files/task", self.api_files_task, "GET", "查询文件批量识别任务"),
            self._api("/data/clear-cards", self.api_clear_cards, "POST", "清空 QB 与入库卡片"),
            self._api("/categories", self.api_categories, "GET", "可用媒体分类"),
            self._api("/overview", self.api_overview, "GET", "框架总览"),
            self._api("/health", self.api_health, "GET", "依赖与数据库状态"),
            self._api("/media", self.api_media, "GET", "入库管理列表"),
            self._api("/torrents", self.api_torrents, "GET", "QB 管理列表"),
            self._api("/qb/downloaders", self.api_qb_downloaders, "GET", "可用 qB 节点"),
            self._api("/qb/refresh", self.api_qb_refresh, "POST", "刷新并识别 QB 任务"),
            self._api("/layout", self.api_layout, "GET", "目录规划配置"),
            self._api("/rss/tasks", self.api_rss_tasks, "GET", "RSS 任务列表"),
            self._api("/rss/tasks", self.api_save_rss_tasks, "POST", "保存 RSS 任务"),
            self._api("/rss/test", self.api_rss_test, "POST", "只读测试 RSS 任务"),
            self._api("/rss/run", self.api_rss_run, "POST", "执行 RSS 任务"),
            self._api("/rss/control", self.api_rss_control, "POST", "暂停或恢复 RSS 执行"),
            self._api("/rss/history", self.api_rss_history, "GET", "RSS 历史列表"),
            self._api("/sites", self.api_sites, "GET", "MoviePilot 站点身份"),
            self._api("/tasks", self.api_background_tasks, "GET", "后台任务列表"),
            self._api("/tasks/clear", self.api_clear_background_tasks, "POST", "清除已结束后台任务"),
            self._api("/tasks/{task_id}", self.api_background_task, "GET", "后台任务详情"),
        ]

    def api_overview(self) -> Dict[str, Any]:
        store = self._require_store()
        rss_runs = store.list_background_tasks_by_state(
            RSS_RUN_TASK_TYPE,
            {"queued", "running"},
        )
        return {
            "success": True,
            "plugin": {
                "id": PLUGIN_ID,
                "name": self.plugin_name,
                "version": self.plugin_version,
                "enabled": self._enabled,
                "rss_enabled": self._rss_enabled,
                "phase": "dual_stage_naming",
            },
            "counts": store.counts(),
            "capabilities": self._capabilities(),
            "qb_task": store.latest_running_task(QB_TASK_TYPE),
            "rss_task": store.latest_running_task(RSS_RUN_TASK_TYPE),
            "rss_tasks": rss_runs,
            "rss_queue": {
                "max_concurrent": RSS_MAX_CONCURRENT_RUNS,
                "running": sum(item.get("state") == "running" for item in rss_runs),
                "queued": sum(item.get("state") == "queued" for item in rss_runs),
            },
            "pending_import": self._pending_coordinator().status(),
        }

    def api_health(self) -> Dict[str, Any]:
        if self._store is None:
            return {
                "success": False,
                "database": {"ready": False},
                "capabilities": self._capabilities(),
                "startup_error": self._startup_error or "SQLite 尚未初始化",
            }
        return {
            "success": True,
            "database": self._store.health(),
            "capabilities": self._capabilities(),
            "startup_error": self._startup_error,
        }

    def api_media(
        self,
        state: str = "",
        media_type: str = "",
        rss_task_ids: str = "",
        offset: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        task_ids = [
            item.strip()
            for item in str(rss_task_ids or "").split(",")
            if item.strip()
        ]
        result = self._require_store().list_media(
            state=str(state or "").strip(),
            media_type=str(media_type or "").strip(),
            rss_task_ids=task_ids,
            offset=offset,
            limit=limit,
        )
        return {"success": True, **result}

    def api_torrents(
        self,
        downloader_id: str = "",
        view: str = "",
        keyword: str = "",
        offset: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        return {
            "success": True,
            **self._require_store().list_torrents(
                downloader_id=str(downloader_id or "").strip(),
                view=str(view or "").strip(),
                keyword=str(keyword or "").strip(),
                offset=offset,
                limit=limit,
            ),
        }

    def api_qb_downloaders(self) -> Dict[str, Any]:
        try:
            scope = self._qb_scope()
            items = []
            for item in MoviePilotQbGateway.list_downloaders():
                categories = scope.categories_for(item.name)
                items.append({**item.to_dict(), "categories": categories})
            return {"success": True, "items": items, "total": len(items)}
        except Exception as error:
            logger.error(f"RSS一条龙：读取 qBittorrent 节点失败：{error}", exc_info=True)
            return {"success": False, "message": str(error), "items": [], "total": 0}

    def api_qb_refresh(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self._enabled:
            return {"success": False, "message": "插件尚未启用"}
        force = self._as_bool((payload or {}).get("force_recognition", False))
        return self._start_qb_refresh(force_recognition=force, source="manual")

    def api_qb_item_refresh(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        data = payload or {}
        try:
            item = self._qb_sync_service().refresh_item(
                data.get("downloader_id"), data.get("info_hash")
            )
            return {"success": True, "message": "任务已刷新", "item": item}
        except Exception as error:
            logger.error(f"RSS一条龙：刷新单个 QB 任务失败：{error}", exc_info=True)
            return {"success": False, "message": str(error), "item": None}

    def api_qb_item_identify(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        data = payload or {}
        media_type = str(data.get("media_type") or "").strip().casefold()
        if media_type not in {"movie", "tv"}:
            return {"success": False, "message": "请选择电影或电视剧"}
        try:
            tmdb_id = int(data.get("tmdb_id") or 0)
        except (TypeError, ValueError):
            tmdb_id = 0
        if tmdb_id <= 0:
            return {"success": False, "message": "请输入有效的 TMDB ID"}
        try:
            season = int(data.get("season") or 0) if media_type == "tv" else None
        except (TypeError, ValueError):
            return {"success": False, "message": "季号必须是大于等于 0 的整数"}
        if season is not None and season < 0:
            return {"success": False, "message": "季号必须大于等于 0"}
        category = self._library_layout.canonical_category(
            str(data.get("category") or "").strip()
        )
        try:
            media_id = str(data.get("media_id") or "").strip()
            media_item = self._require_store().get_media_item(media_id) if media_id else None
            if media_item and str(media_item.get("state") or "") == "importing":
                return {"success": False, "message": "入库中的卡片不能人工修改识别结果"}
            source_kind = str(
                ((media_item or {}).get("details") or {})
                .get("source_identity", {})
                .get("kind") or ""
            )
            if media_item and source_kind in {"local_folder", "local_file"}:
                result = self._file_manager_service().recognize_entry(
                    media_item.get("source_path"),
                    manual_override={
                        "media_type": media_type,
                        "tmdb_id": tmdb_id,
                        "season": season,
                        "category": category,
                    },
                    refresh_media_id=media_id,
                )
                return {
                    "success": True,
                    "message": "已按指定信息重新识别",
                    "item": result.get("item"),
                }
            if media_item:
                item = self._qb_sync_service().refresh_media_from_saved_files(
                    media_id,
                    manual_override={
                        "media_type": media_type,
                        "tmdb_id": tmdb_id,
                        "season": season,
                        "category": category,
                    },
                )
                return {
                    "success": True,
                    "message": "已按指定信息重新识别",
                    "item": item,
                }
            item = self._qb_sync_service().refresh_item(
                data.get("downloader_id"),
                data.get("info_hash"),
                manual_override={
                    "media_type": media_type,
                    "tmdb_id": tmdb_id,
                    "season": season,
                    "category": category,
                },
            )
            return {
                "success": True,
                "message": "已按指定信息重新识别",
                "item": item,
            }
        except Exception as error:
            logger.error(f"RSS一条龙：手动识别失败：{error}", exc_info=True)
            return {"success": False, "message": str(error), "item": None}

    def api_qb_delete(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        raw_items = (payload or {}).get("items") or []
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        if not isinstance(raw_items, list) or not raw_items:
            return {"success": False, "message": "请选择要删除的 QB 任务"}
        store = self._require_store()
        if not self._qb_delete_lock.acquire(blocking=False):
            return {"success": False, "message": "已有 QB 删除操作正在执行"}

        results = []
        seen = set()
        try:
            for raw in raw_items:
                data = raw if isinstance(raw, dict) else {}
                downloader_id = str(data.get("downloader_id") or "").strip()
                info_hash = str(data.get("info_hash") or "").strip().lower()
                identity = (downloader_id, info_hash)
                if identity in seen:
                    continue
                seen.add(identity)
                result = {
                    "downloader_id": downloader_id,
                    "info_hash": info_hash,
                    "success": False,
                    "delete_files": False,
                }
                if not downloader_id or not info_hash:
                    result["message"] = "任务缺少 QB 节点或 info-hash"
                    results.append(result)
                    continue
                snapshot = store.get_torrent_snapshot(downloader_id, info_hash)
                if not snapshot or not bool(snapshot.get("present")):
                    result["message"] = "QB 管理卡片不存在或已失效"
                    results.append(result)
                    continue
                try:
                    removed = MoviePilotQbGateway.remove_torrent(
                        downloader_id,
                        info_hash,
                        False,
                    )
                    if not removed:
                        raise RuntimeError("qB 删除任务返回失败")
                    if not store.delete_torrent_snapshot(downloader_id, info_hash):
                        raise RuntimeError("qB 任务已删除，但插件卡片清理失败，请刷新识别")
                    store.archive_rss_history_for_torrent(downloader_id, info_hash)
                    store.delete_qb_delete_jobs_for_torrent(downloader_id, info_hash)
                    result.update({
                        "success": True,
                        "message": "QB 任务已删除，下载文件已保留",
                    })
                except Exception as error:
                    result["message"] = str(error)
                    logger.error(
                        "RSS一条龙：手动删除 QB 任务失败："
                        f"{downloader_id}/{info_hash}：{error}",
                        exc_info=True,
                    )
                results.append(result)
        finally:
            self._qb_delete_lock.release()

        succeeded = sum(1 for item in results if item["success"])
        failed = len(results) - succeeded
        return {
            "success": bool(results) and failed == 0,
            "partial": succeeded > 0 and failed > 0,
            "message": (
                f"已删除 {succeeded} 个 QB 任务，下载文件均已保留"
                if failed == 0
                else f"QB 任务删除部分完成：成功 {succeeded} 项，失败 {failed} 项"
                if succeeded
                else results[0]["message"]
            ),
            "succeeded": succeeded,
            "failed": failed,
            "delete_files": False,
            "results": results,
        }

    def api_qb_completed(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        data = payload or {}
        info_hash = str(
            data.get("info_hash")
            or data.get("hash")
            or data.get("torrent_hash")
            or ""
        ).strip().lower()
        downloader_id = str(
            data.get("downloader_id") or data.get("downloader") or ""
        ).strip()
        if not info_hash:
            return {"success": False, "message": "完成回调缺少 info-hash"}
        try:
            service = self._qb_sync_service()
            if not downloader_id:
                downloader_id = service.find_torrent_downloader(info_hash)
            item = service.refresh_item(
                downloader_id,
                info_hash,
                schedule_delete=True,
            )
            completed = bool(item.get("completed"))
            moved = bool(item.get("transitioned_to_library"))
            return {
                "success": True,
                "message": (
                    "下载完成，已转入入库管理"
                    if moved
                    else "下载完成，已从 QB 管理移除"
                    if completed
                    else "完成回调已接收，但 qB 当前仍显示未完成"
                ),
                "downloader_id": downloader_id,
                "info_hash": info_hash,
                "completed": completed,
                "transitioned_to_library": moved,
                "media_id": item.get("media_id"),
            }
        except LookupError as error:
            return {
                "success": True,
                "ignored": True,
                "message": str(error),
                "info_hash": info_hash,
            }
        except Exception as error:
            logger.error(f"RSS一条龙：处理 qB 完成回调失败：{error}", exc_info=True)
            return {"success": False, "message": str(error)}

    def api_clear_cards(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if self._pending_coordinator().status().get("running"):
            return {"success": False, "message": "待入库批次运行期间不能清空卡片"}
        if str((payload or {}).get("confirm") or "").strip() != "CLEAR":
            return {"success": False, "message": "清空卡片需要 confirm=CLEAR"}
        counts = self._require_store().clear_card_data()
        return {
            "success": True,
            "message": (
                f"已清空 QB 卡片 {counts['torrents']} 条、"
                f"入库卡片 {counts['media']} 条"
            ),
            "counts": counts,
        }

    def api_media_delete(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        media_id = str((payload or {}).get("media_id") or "").strip()
        store = self._require_store()
        item = store.get_media_item(media_id)
        if item and str(item.get("state") or "") == "importing":
            return {"success": False, "message": "入库中的卡片不能删除"}
        if store.list_import_watches(media_id=media_id, states={
            "waiting_task", "watching", "waiting_library", "rolling_back"
        }):
            return {"success": False, "message": "卡片仍有 CD2 监控任务，不能删除"}
        deleted = store.delete_media_item(media_id)
        return {
            "success": deleted,
            "message": "媒体记录已删除" if deleted else "媒体记录不存在",
        }

    def api_media_action(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        data = payload or {}
        action = str(data.get("action") or "").strip().casefold()
        media_ids = data.get("media_ids") or []
        if isinstance(media_ids, str):
            media_ids = [media_ids]
        if action != "queue_import" and self._pending_coordinator().status().get("running"):
            return {"success": False, "message": "待入库批次运行期间不能执行其他入库或删除操作"}
        if action in MediaActionService.DESTRUCTIVE_ACTIONS:
            expected = f"CONFIRM_{action.upper()}"
            if str(data.get("confirm") or "").strip() != expected:
                return {"success": False, "message": "高风险操作缺少确认标记"}
        if not self._media_action_lock.acquire(blocking=False):
            return {"success": False, "message": "已有入库管理操作正在执行"}
        try:
            result = MediaActionService(
                self._require_store(), self._library_layout
            ).execute(action, media_ids)
            if result["success"]:
                result["message"] = f"操作完成：成功 {result['succeeded']} 项"
            elif result["partial"]:
                result["message"] = (
                    f"操作部分完成：成功 {result['succeeded']} 项，"
                    f"失败 {result['failed']} 项"
                )
            else:
                first_error = next(
                    (item.get("message") for item in result["results"] if not item["success"]),
                    "操作失败",
                )
                result["message"] = str(first_error)
            return result
        except MediaActionError as error:
            return {"success": False, "message": str(error)}
        except Exception as error:
            logger.error(f"RSS一条龙：入库管理操作失败：{error}", exc_info=True)
            return {"success": False, "message": str(error)}
        finally:
            self._media_action_lock.release()

    def api_pending_import_run(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return self._start_pending_import("manual")

    def api_pending_import_status(self) -> Dict[str, Any]:
        return {"success": True, **self._pending_coordinator().status()}

    def api_external_catchup_control(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        data = payload or {}
        action = str(data.get("action") or "read").strip().casefold()
        if action not in {"read", "toggle"}:
            return {"success": False, "message": "不支持的追更开关操作"}
        client = CatchupSwitchClient(
            str(data.get("catchup_base_url", self._catchup_base_url) or ""),
            str(data.get("catchup_page_id", self._catchup_page_id) or ""),
            str(data.get("catchup_token", self._catchup_token) or ""),
        )
        try:
            current = bool(client.read()["enabled"])
            enabled = client.set_enabled(not current) if action == "toggle" else current
            return {
                "success": True,
                "enabled": bool(enabled),
                "action": action,
                "message": f"追更已{'开启' if enabled else '关闭'}",
            }
        except Exception as error:
            logger.warning(f"RSS一条龙：追更开关测试失败：{error}")
            return {"success": False, "message": str(error)}

    def api_external_scan_control(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        data = payload or {}
        action = str(data.get("action") or "read").strip().casefold()
        if action not in {"read", "toggle"}:
            return {"success": False, "message": "不支持的 SA 扫库开关操作"}
        client = ScanSystemClient(
            str(data.get("scan_base_url", self._scan_base_url) or ""),
            str(data.get("scan_username", self._scan_username) or ""),
            str(data.get("scan_password", self._scan_password) or ""),
            str(data.get("scan_setting_name", self._scan_setting_name) or ""),
            str(data.get("scan_target_name", self._scan_target_name) or ""),
        )
        try:
            current = bool(client.read()["enabled"])
            enabled = client.set_enabled(not current) if action == "toggle" else current
            return {
                "success": True,
                "enabled": bool(enabled),
                "action": action,
                "message": f"SA 扫库已{'开启' if enabled else '关闭'}",
            }
        except Exception as error:
            logger.warning(f"RSS一条龙：SA 扫库开关测试失败：{error}")
            return {"success": False, "message": str(error)}

    def api_emby_scheduled_completed(
        self,
        payload: Optional[Union[Dict[str, Any], List[Any], str]] = None,
        secret: str = "",
    ) -> Dict[str, Any]:
        data = self._coerce_emby_callback_payload(payload)
        if not self._scan_callback_secret:
            return {"success": False, "message": "尚未配置扫库回调密钥"}
        supplied_secret = str(secret or data.get("secret") or "").strip()
        if self._scan_callback_secret and supplied_secret != self._scan_callback_secret:
            return {"success": False, "message": "扫库回调密钥不正确"}
        event = self._normalize_emby_callback(data)
        result = self._pending_coordinator().handle_scan_callback(event)
        return {"success": bool(result.get("accepted")), **result}

    def api_media_refresh(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        media_id = str((payload or {}).get("media_id") or "").strip()
        item = self._require_store().get_media_item(media_id)
        if not item:
            return {"success": False, "message": "媒体记录不存在"}
        if str(item.get("state") or "") == "importing":
            return {"success": False, "message": "入库中的卡片不能刷新或重新识别"}
        try:
            if str(item.get("state") or "") == "imported":
                result = MediaInventoryRefreshService(
                    self._require_store(), self._library_layout
                ).refresh(media_id)
                return {
                    "success": True,
                    "message": (
                        f"库存复查完成：已存在 {result['exists_count']}/"
                        f"{result['total_files']}"
                    ),
                    "mode": "inventory_only",
                    **result,
                }
            source_kind = str(
                (item.get("details") or {})
                .get("source_identity", {})
                .get("kind") or ""
            )
            if source_kind in {"local_folder", "local_file"}:
                result = self._file_manager_service().recognize_entry(
                    item.get("source_path"),
                    manual_override=(item.get("details") or {}).get("manual_override"),
                    refresh_media_id=media_id,
                )
                return {
                    "success": True,
                    "message": "已重新识别并复查库存",
                    "mode": "recognize_and_inventory",
                    "item": result.get("item"),
                }
            refreshed = self._qb_sync_service().refresh_media_from_saved_files(
                media_id
            )
            return {
                "success": True,
                "message": "已重新识别并复查库存",
                "mode": "recognize_and_inventory",
                "item": refreshed,
            }
        except Exception as error:
            logger.error(f"RSS一条龙：刷新入库管理记录失败：{error}", exc_info=True)
            return {"success": False, "message": str(error)}

    def api_media_inventory_refresh_batch(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        media_ids = (payload or {}).get("media_ids") or []
        if isinstance(media_ids, str):
            media_ids = [media_ids]
        identities = []
        for value in media_ids:
            identity = str(value or "").strip()
            if identity and identity not in identities:
                identities.append(identity)
        if not identities:
            return {"success": False, "message": "请至少选择一个已入库项目"}
        if not self._media_action_lock.acquire(blocking=False):
            return {"success": False, "message": "已有入库管理操作正在执行"}
        try:
            service = MediaInventoryRefreshService(
                self._require_store(), self._library_layout
            )
            results = []
            for media_id in identities:
                try:
                    result = service.refresh(media_id)
                    results.append({"media_id": media_id, "success": True, **result})
                except Exception as error:
                    results.append({
                        "media_id": media_id,
                        "success": False,
                        "message": str(error),
                    })
            succeeded = sum(1 for item in results if item["success"])
            failed = len(results) - succeeded
            return {
                "success": failed == 0,
                "partial": 0 < succeeded < len(results),
                "total": len(results),
                "succeeded": succeeded,
                "failed": failed,
                "results": results,
                "message": (
                    f"库存复查完成：成功 {succeeded} 项"
                    if not failed
                    else (
                        f"库存复查部分完成：成功 {succeeded} 项，失败 {failed} 项"
                        if succeeded
                        else f"库存复查失败：{failed} 项均未完成"
                    )
                ),
            }
        except Exception as error:
            logger.error(f"RSS一条龙：批量库存复查失败：{error}", exc_info=True)
            return {"success": False, "message": str(error)}
        finally:
            self._media_action_lock.release()

    def api_files_browse(self, path: str = "/") -> Dict[str, Any]:
        try:
            return {"success": True, **self._file_manager_service().browse_sources(path)}
        except FileManagerError as error:
            return {"success": False, "message": str(error), "items": [], "total": 0}

    def api_files_recognize(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self._file_scan_lock.acquire(blocking=False):
            return {"success": False, "message": "已有文件识别任务正在运行，请稍后再试"}
        try:
            result = self._file_manager_service().recognize_entry(
                (payload or {}).get("path")
            )
            return result
        except FileManagerError as error:
            return {"success": False, "message": str(error)}
        except Exception as error:
            logger.error(f"RSS一条龙：单个文件识别失败：{error}", exc_info=True)
            return {"success": False, "message": str(error)}
        finally:
            self._file_scan_lock.release()

    def api_files_recognize_batch(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        store = self._require_store()
        if not self._file_scan_lock.acquire(blocking=False):
            running = store.latest_running_task(FILE_BATCH_TASK_TYPE)
            return {
                "success": False,
                "message": "已有文件识别任务正在运行",
                "task_id": running.get("id") if running else None,
            }
        task_id = uuid.uuid4().hex
        source_path = str((payload or {}).get("path") or "").strip()
        try:
            store.create_background_task(task_id, FILE_BATCH_TASK_TYPE)
            thread = threading.Thread(
                target=self._run_file_batch_recognition,
                kwargs={"task_id": task_id, "source_path": source_path},
                name=f"rssallinone-files-{task_id[:8]}",
                daemon=True,
            )
            thread.start()
        except Exception as error:
            store.finish_background_task(task_id, "failed", error_message=str(error))
            self._file_scan_lock.release()
            return {"success": False, "message": str(error)}
        return {
            "success": True,
            "message": "当前目录批量识别已启动",
            "task_id": task_id,
        }

    def api_files_task(self, task_id: str = "") -> Dict[str, Any]:
        task = self._require_store().get_background_task(str(task_id or "").strip())
        if not task or task.get("task_type") != FILE_BATCH_TASK_TYPE:
            return {"success": False, "message": "文件批量识别任务不存在"}
        return {"success": True, "task": task}

    def api_categories(self) -> Dict[str, Any]:
        categories = set(self._library_layout.category_options())
        media = self._require_store().list_media(offset=0, limit=200)
        for item in media.get("items") or []:
            category = self._library_layout.canonical_category(
                item.get("category") or ""
            )
            if category:
                categories.add(category)
        items = sorted(categories, key=str.casefold)
        return {"success": True, "items": items, "total": len(items)}

    def _qb_sync_service(self) -> QbSyncService:
        return QbSyncService(
            store=self._require_store(),
            inventory_checker=LocalInventoryChecker([]),
            library_layout=self._library_layout,
            logger=logger,
        )

    def api_layout(self) -> Dict[str, Any]:
        return {
            "success": True,
            "layout": self._library_layout.to_dict(),
            "capability": self._library_layout.capability(),
        }

    def api_rss_tasks(self, offset: int = 0, limit: int = 100) -> Dict[str, Any]:
        return {
            "success": True,
            **self._require_store().list_rss_tasks(offset=offset, limit=limit),
        }

    def api_save_rss_tasks(
        self,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            tasks = normalize_rss_tasks((payload or {}).get("items"))
            store = self._require_store()
            items = store.replace_rss_tasks(tasks)
            scope = RssTaskQbScope.from_tasks(items)
            out_of_scope = store.mark_torrents_outside_scope(
                scope.downloader_categories(),
                utc_now(),
            )
            return {
                "success": True,
                "message": f"已保存 {len(items)} 条 RSS 任务",
                "items": items,
                "total": len(items),
                "out_of_scope": out_of_scope,
            }
        except (TypeError, ValueError) as error:
            return {"success": False, "message": str(error), "items": []}

    @staticmethod
    def api_sites() -> Dict[str, Any]:
        try:
            from app.db.site_oper import SiteOper

            items = []
            for site in SiteOper().list() or []:
                if bool(getattr(site, "public", False)):
                    auth_mode = "公开"
                elif str(getattr(site, "apikey", "") or "").strip():
                    auth_mode = "API Key"
                elif str(getattr(site, "token", "") or "").strip():
                    auth_mode = "Token"
                elif str(getattr(site, "cookie", "") or "").strip():
                    auth_mode = "Cookie"
                else:
                    auth_mode = "未配置"
                enabled = bool(getattr(site, "is_active", False))
                items.append({
                    "id": str(getattr(site, "id", "") or ""),
                    "name": str(getattr(site, "name", "") or ""),
                    "domain": str(getattr(site, "url", "") or ""),
                    "enabled": enabled,
                    "auth_mode": auth_mode,
                    "ready": enabled and auth_mode != "未配置",
                    "proxy": bool(getattr(site, "proxy", False)),
                    "render": bool(getattr(site, "render", False)),
                })
            return {"success": True, "items": items, "total": len(items)}
        except Exception as error:
            logger.error(f"RSS一条龙：读取 MoviePilot 站点身份失败：{error}", exc_info=True)
            return {"success": False, "message": str(error), "items": [], "total": 0}

    def api_rss_history(self, offset: int = 0, limit: int = 50) -> Dict[str, Any]:
        return {
            "success": True,
            **self._require_store().list_rss_history(offset=offset, limit=limit),
        }

    def api_rss_test(
        self,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            raw_task = (payload or {}).get("task")
            if not isinstance(raw_task, dict):
                raise ValueError("缺少需要测试的 RSS 任务配置")
            task = normalize_rss_tasks([raw_task])[0]
            result = RssPreviewService(
                existing_keys=self._require_store().find_rss_source_keys,
            ).run(task)
            counts = result.get("counts") or {}
            return {
                "success": True,
                "message": (
                    f"读取 {counts.get('total', 0)} 条，"
                    f"可处理 {counts.get('ready', 0)} 条"
                ),
                "result": result,
            }
        except (RssFeedError, TypeError, ValueError) as error:
            return {"success": False, "message": str(error), "result": None}
        except Exception as error:
            logger.error(f"RSS一条龙：RSS 只读测试失败：{error}", exc_info=True)
            return {
                "success": False,
                "message": "RSS 测试失败，请查看 MoviePilot 日志",
                "result": None,
            }

    def api_rss_run(
        self,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        task_id = str((payload or {}).get("task_id") or "").strip()
        if not task_id:
            return {"success": False, "message": "缺少 RSS 任务 ID"}
        return self._start_rss_run(task_id=task_id, source="manual")

    def api_rss_control(
        self,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        enabled = bool((payload or {}).get("enabled"))
        self._rss_enabled = enabled
        if enabled:
            self._rss_stop_event.clear()
            self._dispatch_rss_queue()
        else:
            self._rss_stop_event.set()
        self._runtime_config["rss_enabled"] = enabled
        try:
            update_config = getattr(self, "update_config", None)
            if callable(update_config):
                update_config(deepcopy(self._runtime_config))
        except Exception as error:
            logger.error(f"RSS一条龙：保存 RSS 运行开关失败：{error}", exc_info=True)
            return {"success": False, "message": "RSS 运行开关保存失败"}
        return {
            "success": True,
            "enabled": enabled,
            "message": "RSS 调度已恢复" if enabled else "RSS 调度已暂停",
        }

    def api_background_tasks(self, offset: int = 0, limit: int = 50) -> Dict[str, Any]:
        return {
            "success": True,
            **self._require_store().list_background_tasks(offset=offset, limit=limit),
        }

    def api_clear_background_tasks(self) -> Dict[str, Any]:
        result = self._require_store().clear_background_tasks()
        deleted = int(result.get("deleted") or 0)
        running = int(result.get("running") or 0)
        return {
            "success": True,
            **result,
            "message": (
                f"已清除 {deleted} 条已结束后台任务"
                + (f"，保留 {running} 条运行中任务" if running else "")
            ),
        }

    def api_background_task(self, task_id: str) -> Dict[str, Any]:
        task = self._require_store().get_background_task(str(task_id or "").strip())
        if not task:
            return {"success": False, "message": "后台任务不存在"}
        return {"success": True, "task": task}

    def _scheduled_rss_run(self, task_id: str) -> None:
        if not self._rss_enabled:
            return
        self._start_rss_run(task_id=str(task_id or "").strip(), source="scheduler")

    def _scheduled_rss_start(self, task_id: str) -> None:
        """Resume paused, incomplete qB tasks for one RSS task."""
        if not self._rss_enabled or not self._store:
            return
        task_id = str(task_id or "").strip()
        task = next(
            (
                item
                for item in self._store.list_all_rss_tasks()
                if str(item.get("id") or "").strip() == task_id
            ),
            None,
        )
        if not task or not task.get("enabled"):
            return
        config = task.get("config") if isinstance(task.get("config"), dict) else {}
        if not bool(config.get("download_enabled", True)):
            logger.info("RSS一条龙：任务 %s 未启用自动下载", task.get("name") or task_id)
            return
        downloader = str(config.get("qb_downloader") or "").strip()
        category = str(config.get("qb_category") or "").strip()
        if not downloader or not category:
            return
        try:
            candidates: List[str] = []
            for item in MoviePilotQbGateway.list_torrents(downloader):
                raw = MoviePilotQbGateway.torrent_dict(item)
                if str(raw.get("category") or "").strip() != category:
                    continue
                info_hash = str(raw.get("hash") or raw.get("info_hash") or "").strip().lower()
                if not info_hash or self._torrent_is_completed(raw):
                    continue
                snapshot = self._store.get_torrent_snapshot(downloader, info_hash)
                if str((snapshot or {}).get("inventory_state") or "").strip() == "exists":
                    continue
                state = str(raw.get("state") or "").strip().casefold()
                if state not in {"paused", "pauseddl", "pausedup", "stopped", "stoppeddl"}:
                    continue
                candidates.append(info_hash)
            if candidates:
                if not MoviePilotQbGateway.resume_torrents(downloader, candidates):
                    raise RuntimeError("qB 返回启动失败")
                logger.info(
                    "RSS一条龙：开始任务 CRON 已启动 %s 个 qB 任务，RSS任务=%s，分类=%s",
                    len(candidates),
                    task.get("name") or task_id,
                    category,
                )
        except Exception as error:
            logger.error(
                "RSS一条龙：开始任务 CRON 执行失败，RSS任务=%s：%s",
                task.get("name") or task_id,
                error,
                exc_info=True,
            )

    def _scheduled_qb_deletes(self) -> None:
        if not self._store or not self._qb_delete_lock.acquire(blocking=False):
            return
        try:
            for job in self._store.claim_due_qb_delete_jobs():
                try:
                    torrent = None
                    for item in MoviePilotQbGateway.list_torrents(
                        str(job.get("downloader_id") or "")
                    ):
                        raw = MoviePilotQbGateway.torrent_dict(item)
                        if str(raw.get("hash") or "").strip().lower() == str(
                            job.get("info_hash") or ""
                        ).strip().lower():
                            torrent = raw
                            break
                    if torrent and not self._torrent_is_completed(torrent):
                        raise RuntimeError("qB 任务当前尚未完成，延后删除")
                    if torrent and not MoviePilotQbGateway.remove_torrent(
                        str(job.get("downloader_id") or ""),
                        str(job.get("info_hash") or ""),
                        bool(job.get("delete_files")),
                    ):
                        raise RuntimeError("qB 删除任务返回失败")
                    self._store.finish_qb_delete_job(
                        job.get("id"), success=True
                    )
                    self._store.archive_rss_history_for_torrent(
                        job.get("downloader_id"), job.get("info_hash")
                    )
                    self._store.delete_torrent_snapshot(
                        job.get("downloader_id"), job.get("info_hash")
                    )
                    self._store.delete_qb_delete_job(job.get("id"))
                    logger.info(
                        "RSS一条龙：qB 到期删除完成 "
                        f"{job.get('downloader_id')}/{job.get('info_hash')}，"
                        f"删除文件={bool(job.get('delete_files'))}"
                        + ("，任务已由 qB 或用户提前移除" if not torrent else "")
                    )
                except Exception as error:
                    retry_at = (
                        datetime.now(timezone.utc) + timedelta(seconds=60)
                    ).isoformat(timespec="seconds")
                    self._store.finish_qb_delete_job(
                        job.get("id"),
                        success=False,
                        error=str(error),
                        retry_at=retry_at,
                    )
                    logger.error(
                        "RSS一条龙：qB 到期删除失败，60 秒后重试："
                        f"{job.get('downloader_id')}/{job.get('info_hash')}：{error}"
                    )
        finally:
            self._qb_delete_lock.release()

    def _scheduled_pending_import(self) -> None:
        self._start_pending_import("cron")

    def _supervise_pending_import(self) -> None:
        try:
            status = self._pending_coordinator().status()
        except Exception as error:
            logger.error(f"RSS一条龙：读取待入库恢复状态失败：{error}")
            return
        batch = status.get("batch") or {}
        if batch or status.get("importing"):
            self._start_pending_import("supervisor")

    @staticmethod
    def _torrent_is_completed(torrent: Dict[str, Any]) -> bool:
        try:
            progress = float(torrent.get("progress") or 0)
        except (TypeError, ValueError):
            progress = 0
        if progress >= 99.999 or 0.999999 <= progress <= 1.0:
            return True
        return str(torrent.get("state") or "").strip().casefold() in {
            "completed", "uploading", "stalledup", "pausedup",
            "queuedup", "checkingup", "forcedup",
        }

    def _start_rss_run(self, *, task_id: str, source: str) -> Dict[str, Any]:
        store = self._require_store()
        if not self._rss_enabled:
            return {"success": False, "message": "RSS 调度已暂停"}
        task = next(
            (item for item in store.list_all_rss_tasks() if str(item.get("id") or "") == task_id),
            None,
        )
        if not task:
            return {"success": False, "message": "RSS 任务不存在"}
        if not task.get("enabled"):
            return {"success": False, "message": "RSS 任务未启用"}
        with self._rss_queue_lock:
            existing = self._find_pending_rss_run_locked(task_id)
            if existing:
                return {
                    "success": False,
                    "message": "该 RSS 任务已在执行队列中",
                    "task_id": existing.get("id"),
                    "state": existing.get("state"),
                }
            run_id = uuid.uuid4().hex
            store.create_background_task(
                run_id,
                RSS_RUN_TASK_TYPE,
                task_name=str(task.get("name") or task_id),
                state="queued",
                result={
                    "rss_task_id": task_id,
                    "task_name": str(task.get("name") or task_id),
                    "source": source,
                },
            )
            self._dispatch_rss_queue_locked()
            queued_task = store.get_background_task(run_id) or {}
        state = str(queued_task.get("state") or "queued")
        return {
            "success": True,
            "message": (
                "RSS 执行已启动"
                if state == "running"
                else "RSS 任务已加入执行队列"
            ),
            "task_id": run_id,
            "state": state,
        }

    def _find_pending_rss_run_locked(self, rss_task_id: str) -> Optional[Dict[str, Any]]:
        store = self._store
        if not store:
            return None
        normalized = str(rss_task_id or "").strip()
        for run_id, task_id in self._rss_active_run_ids.items():
            if task_id == normalized:
                return store.get_background_task(run_id) or {
                    "id": run_id,
                    "state": "running",
                }
        for item in store.list_background_tasks_by_state(
            RSS_RUN_TASK_TYPE,
            {"queued"},
        ):
            result = item.get("result") if isinstance(item.get("result"), dict) else {}
            if str(result.get("rss_task_id") or result.get("task_id") or "").strip() == normalized:
                return item
        return None

    def _dispatch_rss_queue(self) -> None:
        with self._rss_queue_lock:
            self._dispatch_rss_queue_locked()

    def _dispatch_rss_queue_locked(self) -> None:
        store = self._store
        if not store or not self._rss_enabled or self._rss_stop_event.is_set():
            return
        while len(self._rss_active_run_ids) < RSS_MAX_CONCURRENT_RUNS:
            queued = store.list_background_tasks_by_state(
                RSS_RUN_TASK_TYPE,
                {"queued"},
            )
            if not queued:
                return
            tasks = {
                str(item.get("id") or "").strip(): item
                for item in store.list_all_rss_tasks()
            }
            selected = None
            selected_task = None
            selected_downloader = ""
            selected_source = "scheduler"
            for item in queued:
                result = item.get("result") if isinstance(item.get("result"), dict) else {}
                rss_task_id = str(
                    result.get("rss_task_id") or result.get("task_id") or ""
                ).strip()
                task = tasks.get(rss_task_id)
                if not task or not task.get("enabled"):
                    store.finish_background_task(
                        item.get("id"),
                        "failed",
                        error_message=(
                            "排队期间 RSS 任务已删除或禁用"
                            if rss_task_id
                            else "排队记录缺少 RSS 任务 ID"
                        ),
                    )
                    continue
                config = task.get("config") if isinstance(task.get("config"), dict) else {}
                downloader = str(config.get("qb_downloader") or "").strip()
                if not downloader:
                    store.finish_background_task(
                        item.get("id"),
                        "failed",
                        error_message="RSS 任务未配置 QB 下载器",
                    )
                    continue
                if downloader in self._rss_active_downloaders.values():
                    continue
                selected = item
                selected_task = task
                selected_downloader = downloader
                selected_source = str(result.get("source") or "scheduler")
                break
            if not selected or not selected_task:
                return
            run_id = str(selected.get("id") or "").strip()
            rss_task_id = str(selected_task.get("id") or "").strip()
            if not store.start_background_task(run_id):
                continue
            self._rss_active_run_ids[run_id] = rss_task_id
            self._rss_active_downloaders[run_id] = selected_downloader
            try:
                thread = threading.Thread(
                    target=self._run_rss_task,
                    kwargs={
                        "background_task_id": run_id,
                        "task": deepcopy(selected_task),
                        "source": selected_source,
                    },
                    name=f"rssallinone-rss-{run_id[:8]}",
                    daemon=True,
                )
                thread.start()
            except Exception as error:
                self._rss_active_run_ids.pop(run_id, None)
                self._rss_active_downloaders.pop(run_id, None)
                store.finish_background_task(
                    run_id,
                    "failed",
                    error_message=f"后台线程启动失败：{error}",
                )

    def _run_rss_task(
        self,
        *,
        background_task_id: str,
        task: Dict[str, Any],
        source: str,
    ) -> None:
        store = self._store
        if not store:
            with self._rss_queue_lock:
                self._rss_active_run_ids.pop(background_task_id, None)
                self._rss_active_downloaders.pop(background_task_id, None)
            return
        try:
            logger.info(
                f"RSS一条龙：开始执行 RSS 任务 {task.get('name') or task.get('id')}，来源={source}"
            )
            RssExecutionService(
                store=store,
                on_source_ready=self._recognize_rss_qb_item,
                logger=logger,
            ).run(
                background_task_id,
                task,
                stop_event=self._rss_stop_event,
            )
        except Exception as error:
            logger.error(f"RSS一条龙：RSS 执行失败：{error}", exc_info=True)
            store.finish_background_task(
                background_task_id,
                "failed",
                error_message=str(error),
            )
        finally:
            with self._rss_queue_lock:
                self._rss_active_run_ids.pop(background_task_id, None)
                self._rss_active_downloaders.pop(background_task_id, None)
                self._dispatch_rss_queue_locked()

    def _recognize_rss_qb_item(self, downloader_id: str, info_hash: str) -> None:
        self._qb_sync_service().refresh_item(downloader_id, info_hash)

    def _start_qb_refresh(
        self,
        *,
        force_recognition: bool,
        source: str,
    ) -> Dict[str, Any]:
        store = self._require_store()
        if not self._qb_refresh_lock.acquire(blocking=False):
            running = store.latest_running_task(QB_TASK_TYPE)
            return {
                "success": False,
                "message": "QB 刷新识别正在运行",
                "task_id": running.get("id") if running else None,
            }
        task_id = uuid.uuid4().hex
        try:
            store.create_background_task(task_id, QB_TASK_TYPE)
            thread = threading.Thread(
                target=self._run_qb_refresh,
                kwargs={
                    "task_id": task_id,
                    "force_recognition": force_recognition,
                    "source": source,
                },
                name=f"rssallinone-qb-{task_id[:8]}",
                daemon=True,
            )
            thread.start()
        except Exception as error:
            store.finish_background_task(
                task_id,
                "failed",
                error_message=f"后台线程启动失败：{error}",
            )
            self._qb_refresh_lock.release()
            raise
        return {
            "success": True,
            "message": "QB 刷新识别已启动",
            "task_id": task_id,
        }

    def _run_qb_refresh(
        self,
        *,
        task_id: str,
        force_recognition: bool,
        source: str,
    ) -> None:
        store = self._store
        if not store:
            self._qb_refresh_lock.release()
            return
        try:
            logger.info(
                f"RSS一条龙：开始 QB 同步与完成转移，来源={source}，"
                f"强制识别={force_recognition}"
            )
            QbSyncService(
                store=store,
                inventory_checker=LocalInventoryChecker([]),
                library_layout=self._library_layout,
                logger=logger,
            ).run(
                task_id,
                force_recognition=force_recognition,
                stop_event=self._stop_event,
            )
        except Exception as error:
            logger.error(f"RSS一条龙：QB 刷新识别失败：{error}", exc_info=True)
            store.finish_background_task(
                task_id,
                "failed",
                error_message=str(error),
            )
        finally:
            self._qb_refresh_lock.release()

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().casefold() in {"1", "true", "yes", "on", "是"}
        return bool(value)

    def _capabilities(self) -> Dict[str, Any]:
        capabilities = runtime_capabilities(PLUGIN_DIR)
        capabilities["rss_reader"] = {
            "ready": True,
            "phase": "enqueue",
            "formats": ["rss", "atom"],
            "qb_write": True,
        }
        capabilities["local_inventory"] = self._library_layout.capability()
        cd2_configured = bool(
            self._cd2_grpc_addr
            and self._cd2_token
            and self._cd2_staging_roots()
            and self._cd2_dest_root
        )
        capabilities["clouddrive"].update({
            "ready": bool(capabilities["clouddrive"].get("grpc") and cd2_configured),
            "configured": cd2_configured,
            "phase": "upload_monitoring" if cd2_configured else "connection_pending",
        })
        capabilities["catchup"] = {
            "ready": bool(
                self._catchup_base_url and self._catchup_page_id and self._catchup_token
            ),
            "phase": "batch_switch_guard",
        }
        capabilities["scanner"] = {
            "ready": bool(
                self._scan_base_url
                and self._scan_username
                and self._scan_password
                and self._scan_setting_name
                and self._scan_target_name
                and self._scan_callback_secret
            ),
            "phase": "refresh_callback_restore",
        }
        capabilities["hardlink_import"] = {
            "ready": True,
            "phase": "manual_and_cd2_monitored_queue",
            "mode": "local_os_link",
            "inventory_existing_files": "skip",
            "clouddrive_api": cd2_configured,
        }
        try:
            downloaders = MoviePilotQbGateway.list_downloaders()
            scope = self._qb_scope()
            managed = [
                item for item in downloaders
                if scope.categories_for(item.name)
            ]
            capabilities["qbittorrent"] = {
                "ready": scope.ready and any(item.ready for item in managed),
                "scope": "vt_rss_task_downloader_category",
                "configured": len(downloaders),
                "managed": len(managed),
                "available": sum(1 for item in managed if item.ready),
                "managed_scope": scope.to_dict(),
                "phase": "completion_lifecycle",
            }
        except Exception as error:
            capabilities["qbittorrent"] = {
                "ready": False,
                "scope": "moviepilot_configured_qbittorrent_only",
                "configured": 0,
                "available": 0,
                "phase": "runtime_error",
                "message": str(error),
            }
        return capabilities

    def _qb_scope(self) -> RssTaskQbScope:
        tasks = self._store.list_all_rss_tasks() if self._store else []
        return RssTaskQbScope.from_tasks(tasks)

    def _file_manager_service(self) -> LocalFileManagerService:
        return LocalFileManagerService(
            store=self._require_store(),
            inventory_checker=LocalInventoryChecker([]),
            library_layout=self._library_layout,
            logger=logger,
        )

    def _pending_coordinator(self) -> PendingImportCoordinator:
        config = PendingImportConfig(
            cd2_dest_root=self._cd2_dest_root,
            plugin_staging_roots=self._cd2_staging_roots(),
            plugin_staging_root=self._cd2_plugin_staging_root,
            discovery_timeout=self._bounded_int(
                self._runtime_config.get("cd2_discovery_timeout"), 180, 30, 1800
            ),
            card_timeout=self._bounded_int(
                self._runtime_config.get("cd2_card_timeout"), 7200, 300, 43200
            ),
            poll_interval=self._bounded_int(
                self._runtime_config.get("cd2_poll_interval"), 10, 2, 60
            ),
            transfer_grace=self._bounded_int(
                self._runtime_config.get("cd2_transfer_grace"), 20, 5, 120
            ),
            risk_cooldown=self._bounded_int(
                self._runtime_config.get("cd2_risk_cooldown"), 1800, 60, 86400
            ),
            risk_retry_limit=self._bounded_int(
                self._runtime_config.get("cd2_risk_retry_limit"), 3, 1, 10
            ),
            scan_callback_timeout=self._bounded_int(
                self._runtime_config.get("scan_callback_timeout"), 7200, 300, 43200
            ),
            callback_server_id=self._scan_callback_server_id,
            callback_task_id=self._scan_callback_task_id,
            callback_task_name=self._scan_callback_task_name,
        )
        catchup = CatchupSwitchClient(
            self._catchup_base_url, self._catchup_page_id, self._catchup_token
        )
        scanner = ScanSystemClient(
            self._scan_base_url,
            self._scan_username,
            self._scan_password,
            self._scan_setting_name,
            self._scan_target_name,
        )
        return PendingImportCoordinator(
            store=self._require_store(),
            config=config,
            cd2=CloudDriveClient(self._cd2_grpc_addr, self._cd2_token),
            controls=ExternalControlBundle(catchup, scanner),
            scanner=scanner,
            stop_event=self._stop_event,
            logger=logger,
            notify=self._notify_pending_import,
        )

    def _cd2_staging_roots(self) -> List[str]:
        roots = []
        for route in self._library_layout.routes:
            if not route.enabled:
                continue
            roots.extend(
                str(value or "").strip()
                for value in route.link_roots.values()
                if str(value or "").strip()
            )
        return list(dict.fromkeys(roots))

    def _start_pending_import(self, trigger_source: str) -> Dict[str, Any]:
        if not self._enabled:
            return {"success": False, "message": "插件尚未启用"}
        if not self._pending_import_lock.acquire(blocking=False):
            return {
                "success": True,
                "message": "待入库队列已经在运行",
                **self._pending_coordinator().status(),
            }
        status = self._pending_coordinator().status()
        if not status.get("batch") and not status.get("pending") and not status.get("importing"):
            self._pending_import_lock.release()
            return {"success": True, "message": "当前没有待入库项目", **status}
        if not status.get("batch"):
            try:
                if not self._scan_callback_secret:
                    raise RuntimeError("未配置 Emby 扫库回调密钥")
                self._pending_coordinator().preflight(
                    manage_external_switches=(
                        str(trigger_source or "").strip().casefold() != "manual"
                    )
                )
            except Exception as error:
                self._pending_import_lock.release()
                return {"success": False, "message": str(error), **status}
        worker = threading.Thread(
            target=self._run_pending_import,
            kwargs={"trigger_source": trigger_source},
            name="RssAllInOnePendingImport",
            daemon=True,
        )
        worker.start()
        return {
            "success": True,
            "message": "待入库队列已启动",
            **status,
        }

    def _run_pending_import(self, *, trigger_source: str) -> None:
        try:
            self._pending_coordinator().run(trigger_source)
        except Exception as error:
            logger.error(f"RSS一条龙：待入库队列执行失败：{error}", exc_info=True)
            self._notify_pending_import("RSS一条龙待入库失败", str(error))
        finally:
            self._pending_import_lock.release()

    def _notify_pending_import(self, title: str, text: str) -> None:
        try:
            sender = getattr(self, "post_message", None)
            if callable(sender):
                sender(title=title, text=text)
                return
        except Exception:
            logger.warning("RSS一条龙：发送待入库通知失败", exc_info=True)
        logger.warning(f"{title}：{text}")

    @staticmethod
    def _coerce_emby_callback_payload(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            for item in payload:
                parsed = RssAllInOne._coerce_emby_callback_payload(item)
                if parsed:
                    return parsed
            return {}
        if not isinstance(payload, str):
            return {}

        text = payload.strip()
        if not text:
            return {}
        try:
            decoded = json.loads(text)
        except (TypeError, ValueError):
            decoded = None
        if decoded is not None and decoded != payload:
            parsed = RssAllInOne._coerce_emby_callback_payload(decoded)
            if parsed:
                return parsed

        form = parse_qs(text, keep_blank_values=True)
        if form:
            return {key: values[-1] if values else "" for key, values in form.items()}
        return {"raw": text}

    @staticmethod
    def _normalize_emby_callback(payload: Dict[str, Any]) -> Dict[str, Any]:
        nested = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        source = {**nested, **payload}
        task = source.get("Task") or source.get("task") or source.get("Item") or {}
        server = source.get("Server") or source.get("server") or {}
        task = task if isinstance(task, dict) else {}
        server = server if isinstance(server, dict) else {}
        return {
            "event_name": str(
                source.get("Event")
                or source.get("event")
                or source.get("NotificationType")
                or source.get("event_type")
                or source.get("type")
                or ""
            ),
            "event_time": str(
                source.get("Timestamp")
                or source.get("timestamp")
                or source.get("event_time")
                or utc_now()
            ),
            "server_id": str(
                source.get("server_id")
                or server.get("Id")
                or server.get("id")
                or ""
            ),
            "task_id": str(
                source.get("task_id") or task.get("Id") or task.get("id") or ""
            ),
            "task_name": str(
                source.get("task_name")
                or task.get("Name")
                or task.get("name")
                or ""
            ),
        }

    @staticmethod
    def _bounded_int(value: Any, fallback: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = fallback
        return max(minimum, min(maximum, parsed))

    def _run_file_batch_recognition(self, *, task_id: str, source_path: str) -> None:
        store = self._store
        if not store:
            self._file_scan_lock.release()
            return
        try:
            def update_progress(
                current_item: str,
                processed: int,
                succeeded: int,
                failed: int,
                total: int,
            ) -> None:
                store.update_background_task(
                    task_id,
                    current_item=current_item,
                    processed=processed,
                    succeeded=succeeded,
                    failed=failed,
                    total=total,
                )

            result = self._file_manager_service().recognize_current_directory(
                source_path,
                progress=update_progress,
            )
            store.finish_background_task(
                task_id,
                "succeeded" if not result.get("failed") else "partial",
                result=result,
            )
        except Exception as error:
            logger.error(f"RSS一条龙：当前目录批量识别失败：{error}", exc_info=True)
            store.finish_background_task(task_id, "failed", error_message=str(error))
        finally:
            self._file_scan_lock.release()

    def _database_path(self) -> Path:
        getter = getattr(self, "get_data_path", None)
        if callable(getter):
            data_path = Path(getter())
        else:
            data_path = PLUGIN_DIR / ".runtime"
        return data_path / self._database_filename

    def _require_store(self) -> SQLiteStore:
        if self._store is None:
            raise RuntimeError(self._startup_error or "SQLite 尚未初始化")
        return self._store

    @staticmethod
    def _safe_database_filename(value: object) -> str:
        filename = Path(str(value or "rssallinone.db")).name
        return filename if filename.endswith(".db") else f"{filename}.db"

    @staticmethod
    def _api(
        path: str,
        endpoint: Any,
        method: str,
        summary: str,
        *,
        auth: str = "bear",
    ) -> Dict[str, Any]:
        return {
            "path": path,
            "endpoint": endpoint,
            "methods": [method],
            "auth": auth,
            "summary": summary,
        }

    @staticmethod
    def _default_config() -> Dict[str, Any]:
        layout = default_layout_config()
        return {
            "enabled": False,
            "rss_enabled": True,
            "database_filename": "rssallinone.db",
            **layout,
            "cd2_grpc_addr": "",
            "cd2_token": "",
            "cd2_dest_root": "",
            "pending_import_cron": "0 1 * * *",
            "cd2_discovery_timeout": 180,
            "cd2_card_timeout": 7200,
            "cd2_poll_interval": 10,
            "cd2_transfer_grace": 20,
            "cd2_risk_cooldown": 1800,
            "cd2_risk_retry_limit": 3,
            "catchup_base_url": "",
            "catchup_page_id": "",
            "catchup_token": "",
            "scan_base_url": "",
            "scan_username": "",
            "scan_password": "",
            "scan_setting_name": "",
            "scan_target_name": "",
            "scan_callback_secret": "",
            "scan_callback_server_id": "",
            "scan_callback_task_id": "",
            "scan_callback_task_name": "",
            "scan_callback_timeout": 7200,
        }
