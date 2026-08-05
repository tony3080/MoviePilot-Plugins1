"""RSS All-in-One framework plugin for MoviePilot V2."""

from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.log import logger
from app.plugins import _PluginBase

from .capabilities import runtime_capabilities
from .database import SQLiteStore, utc_now
from .file_manager import FILE_BATCH_TASK_TYPE, FileManagerError, LocalFileManagerService
from .inventory import LocalInventoryChecker
from .layout import LibraryLayout, default_layout_config
from .media_actions import (
    MediaActionError,
    MediaActionService,
    MediaInventoryRefreshService,
)
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


class RssAllInOne(_PluginBase):
    plugin_name = "RSS一条龙"
    plugin_desc = "统一管理 PT RSS、qBittorrent、媒体识别与硬链接入库流程。"
    plugin_icon = (
        "https://raw.githubusercontent.com/jxxghp/"
        "MoviePilot-Plugins/main/icons/rss.png"
    )
    plugin_version = "0.12.1"
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
    _catchup_base_url = ""
    _catchup_page_id = ""
    _catchup_token = ""
    _scan_base_url = ""
    _scan_username = ""
    _scan_password = ""
    _scan_setting_name = ""
    _scan_target_name = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._store: Optional[SQLiteStore] = None
        self._startup_error = ""
        self._qb_refresh_lock = threading.Lock()
        self._qb_delete_lock = threading.Lock()
        self._rss_run_lock = threading.Lock()
        self._media_action_lock = threading.Lock()
        self._file_scan_lock = threading.Lock()
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
        self._catchup_base_url = str(config.get("catchup_base_url") or "").strip()
        self._catchup_page_id = str(config.get("catchup_page_id") or "").strip()
        self._catchup_token = str(config.get("catchup_token") or "").strip()
        self._scan_base_url = str(config.get("scan_base_url") or "").strip()
        self._scan_username = str(config.get("scan_username") or "").strip()
        self._scan_password = str(config.get("scan_password") or "").strip()
        self._scan_setting_name = str(config.get("scan_setting_name") or "").strip()
        self._scan_target_name = str(config.get("scan_target_name") or "").strip()

        self._startup_error = ""
        self._stop_event.clear()
        if self._rss_enabled:
            self._rss_stop_event.clear()
        else:
            self._rss_stop_event.set()
        try:
            self._store = SQLiteStore(self._database_path())
            self._store.initialize()
            recovered = self._store.recover_incomplete_tasks()
            if recovered:
                logger.warning(f"RSS一条龙：已终止 {recovered} 个重启前未完成的后台任务")
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
            "icon": "rss",
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
                rss_url = str(config.get("rss_url") or "").strip()
                rss_cron = str(config.get("rss_cron") or "").strip()
                if not rss_url or not rss_cron:
                    continue
                try:
                    trigger = CronTrigger.from_crontab(rss_cron)
                except (TypeError, ValueError) as error:
                    logger.error(
                        f"RSS一条龙：任务 {task.get('name') or task.get('id')} 的 RSS CRON 无效：{error}"
                    )
                    continue
                task_id = str(task.get("id") or "").strip()
                services.append({
                    "id": f"RssAllInOne.Rss.{task_id}",
                    "name": f"RSS一条龙 RSS：{task.get('name') or task_id}",
                    "trigger": trigger,
                    "func": self._scheduled_rss_run,
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
        return services

    def stop_service(self) -> None:
        self._stop_event.set()
        self._rss_stop_event.set()
        self._store = None

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            self._api("/qb/item/refresh", self.api_qb_item_refresh, "POST", "刷新单个 QB 任务"),
            self._api("/qb/item/identify", self.api_qb_item_identify, "POST", "手动识别单个 QB 任务"),
            self._api("/qb/completed", self.api_qb_completed, "POST", "接收 qB 下载完成回调"),
            self._api("/media/delete", self.api_media_delete, "POST", "删除插件媒体记录"),
            self._api("/media/action", self.api_media_action, "POST", "批量执行入库管理操作"),
            self._api("/media/refresh", self.api_media_refresh, "POST", "刷新入库管理媒体记录"),
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
            self._api("/tasks/{task_id}", self.api_background_task, "GET", "后台任务详情"),
        ]

    def api_overview(self) -> Dict[str, Any]:
        store = self._require_store()
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
            item = service.refresh_item(downloader_id, info_hash)
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
        deleted = self._require_store().delete_media_item(media_id)
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
        if action in MediaActionService.DESTRUCTIVE_ACTIONS:
            expected = f"CONFIRM_{action.upper()}"
            if str(data.get("confirm") or "").strip() != expected:
                return {"success": False, "message": "高风险操作缺少确认标记"}
        if not self._media_action_lock.acquire(blocking=False):
            return {"success": False, "message": "已有入库管理操作正在执行"}
        try:
            result = MediaActionService(self._require_store()).execute(action, media_ids)
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

    def api_media_refresh(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        media_id = str((payload or {}).get("media_id") or "").strip()
        item = self._require_store().get_media_item(media_id)
        if not item:
            return {"success": False, "message": "媒体记录不存在"}
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
            refreshed = self._qb_sync_service().refresh_item(
                item.get("downloader_id"), item.get("info_hash")
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

    def api_background_task(self, task_id: str) -> Dict[str, Any]:
        task = self._require_store().get_background_task(str(task_id or "").strip())
        if not task:
            return {"success": False, "message": "后台任务不存在"}
        return {"success": True, "task": task}

    def _scheduled_rss_run(self, task_id: str) -> None:
        if not self._rss_enabled:
            return
        self._start_rss_run(task_id=str(task_id or "").strip(), source="scheduler")

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
                    logger.info(
                        "RSS一条龙：qB 到期删除完成 "
                        f"{job.get('downloader_id')}/{job.get('info_hash')}，"
                        f"删除文件={bool(job.get('delete_files'))}"
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
        if not self._rss_run_lock.acquire(blocking=False):
            running = store.latest_running_task(RSS_RUN_TASK_TYPE)
            return {
                "success": False,
                "message": "RSS 执行正在运行",
                "task_id": running.get("id") if running else None,
            }
        run_id = uuid.uuid4().hex
        try:
            store.create_background_task(run_id, RSS_RUN_TASK_TYPE)
            thread = threading.Thread(
                target=self._run_rss_task,
                kwargs={
                    "background_task_id": run_id,
                    "task": deepcopy(task),
                    "source": source,
                },
                name=f"rssallinone-rss-{run_id[:8]}",
                daemon=True,
            )
            thread.start()
        except Exception as error:
            store.finish_background_task(run_id, "failed", error_message=str(error))
            self._rss_run_lock.release()
            raise
        return {
            "success": True,
            "message": "RSS 执行已启动",
            "task_id": run_id,
        }

    def _run_rss_task(
        self,
        *,
        background_task_id: str,
        task: Dict[str, Any],
        source: str,
    ) -> None:
        store = self._store
        if not store:
            self._rss_run_lock.release()
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
            self._rss_run_lock.release()

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
        capabilities["hardlink_import"] = {
            "ready": True,
            "phase": "library_actions",
            "mode": "local_os_link",
            "inventory_existing_files": "skip",
            "clouddrive_api": False,
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
    def _api(path: str, endpoint: Any, method: str, summary: str) -> Dict[str, Any]:
        return {
            "path": path,
            "endpoint": endpoint,
            "methods": [method],
            "auth": "bear",
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
            "catchup_base_url": "",
            "catchup_page_id": "",
            "catchup_token": "",
            "scan_base_url": "",
            "scan_username": "",
            "scan_password": "",
            "scan_setting_name": "",
            "scan_target_name": "",
        }
