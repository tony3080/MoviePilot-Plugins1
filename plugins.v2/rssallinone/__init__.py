"""RSS All-in-One framework plugin for MoviePilot V2."""

from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.log import logger
from app.plugins import _PluginBase

from .capabilities import runtime_capabilities
from .database import SQLiteStore, utc_now
from .inventory import LocalInventoryChecker
from .layout import LibraryLayout, default_layout_config
from .qb_sync import (
    MoviePilotQbGateway,
    QB_TASK_TYPE,
    QbSyncService,
    RssTaskQbScope,
)
from .rss_feed import RssFeedError, RssPreviewService
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
    plugin_version = "0.5.0"
    plugin_author = "tony3080"
    author_url = "https://github.com/tony3080"
    plugin_config_prefix = "rssallinone_"
    plugin_order = 45
    auth_level = 2

    _enabled = False
    _database_filename = "rssallinone.db"
    _qb_refresh_cron = "*/10 * * * *"
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
        self._stop_event = threading.Event()
        self._source_routes: List[Dict[str, Any]] = []
        self._library_layout = LibraryLayout("", [])

    def init_plugin(self, config: dict = None) -> None:
        config = config or {}
        defaults = self._default_config()
        self._enabled = bool(config.get("enabled", False))
        self._database_filename = self._safe_database_filename(
            config.get("database_filename") or "rssallinone.db"
        )
        self._qb_refresh_cron = str(
            config.get("qb_refresh_cron") or "*/10 * * * *"
        ).strip()
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
        if not self._enabled or not self._store or not self._qb_refresh_cron:
            return []
        try:
            from apscheduler.triggers.cron import CronTrigger

            trigger = CronTrigger.from_crontab(self._qb_refresh_cron)
        except (ImportError, TypeError, ValueError) as error:
            logger.error(f"RSS一条龙：无效的 QB 刷新周期 {self._qb_refresh_cron}：{error}")
            return []
        return [{
            "id": "RssAllInOne.QbRefresh",
            "name": "RSS一条龙 QB 只读同步",
            "trigger": trigger,
            "func": self._scheduled_qb_refresh,
            "kwargs": {},
        }]

    def stop_service(self) -> None:
        self._stop_event.set()
        self._store = None

    def get_api(self) -> List[Dict[str, Any]]:
        return [
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
                "phase": "rss_preview",
            },
            "counts": store.counts(),
            "capabilities": self._capabilities(),
            "qb_task": store.latest_running_task(QB_TASK_TYPE),
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
        offset: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        result = self._require_store().list_media(
            state=str(state or "").strip(),
            media_type=str(media_type or "").strip(),
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

    def _scheduled_qb_refresh(self) -> None:
        if not self._qb_scope().ready:
            return
        self._start_qb_refresh(force_recognition=False, source="scheduler")

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
                f"RSS一条龙：开始 QB 只读同步，来源={source}，"
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
            "phase": "readonly_preview",
            "formats": ["rss", "atom"],
            "qb_write": False,
        }
        capabilities["local_inventory"] = self._library_layout.capability()
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
                "phase": "readonly_sync",
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
            "database_filename": "rssallinone.db",
            "qb_refresh_cron": "*/10 * * * *",
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
