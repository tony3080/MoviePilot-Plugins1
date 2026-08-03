"""RSS All-in-One framework plugin for MoviePilot V2."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.log import logger
from app.plugins import _PluginBase

from .capabilities import runtime_capabilities
from .database import SQLiteStore


PLUGIN_ID = "RssAllInOne"
PLUGIN_DIR = Path(__file__).resolve().parent


class RssAllInOne(_PluginBase):
    plugin_name = "RSS一条龙"
    plugin_desc = "统一管理 PT RSS、qBittorrent、硬链接 staging 与 CloudDrive2 备份流程。"
    plugin_icon = (
        "https://raw.githubusercontent.com/jxxghp/"
        "MoviePilot-Plugins/main/icons/rss.png"
    )
    plugin_version = "0.1.0"
    plugin_author = "tony3080"
    author_url = "https://github.com/tony3080"
    plugin_config_prefix = "rssallinone_"
    plugin_order = 45
    auth_level = 2

    _enabled = False
    _database_filename = "rssallinone.db"
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

    def init_plugin(self, config: dict = None) -> None:
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        self._database_filename = self._safe_database_filename(
            config.get("database_filename") or "rssallinone.db"
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
        try:
            self._store = SQLiteStore(self._database_path())
            self._store.initialize()
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

    @staticmethod
    def get_service() -> List[Dict[str, Any]]:
        return []

    def stop_service(self) -> None:
        self._store = None

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            self._api("/overview", self.api_overview, "GET", "框架总览"),
            self._api("/health", self.api_health, "GET", "依赖与数据库状态"),
            self._api("/media", self.api_media, "GET", "入库管理列表"),
            self._api("/torrents", self.api_torrents, "GET", "QB 管理列表"),
            self._api("/rss/tasks", self.api_rss_tasks, "GET", "RSS 任务列表"),
            self._api("/rss/history", self.api_rss_history, "GET", "RSS 历史列表"),
            self._api("/tasks", self.api_background_tasks, "GET", "后台任务列表"),
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
                "phase": "framework",
            },
            "counts": store.counts(),
            "capabilities": runtime_capabilities(PLUGIN_DIR),
        }

    def api_health(self) -> Dict[str, Any]:
        if self._store is None:
            return {
                "success": False,
                "database": {"ready": False},
                "capabilities": runtime_capabilities(PLUGIN_DIR),
                "startup_error": self._startup_error or "SQLite 尚未初始化",
            }
        return {
            "success": True,
            "database": self._store.health(),
            "capabilities": runtime_capabilities(PLUGIN_DIR),
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

    def api_torrents(self, offset: int = 0, limit: int = 50) -> Dict[str, Any]:
        return {
            "success": True,
            **self._require_store().list_torrents(offset=offset, limit=limit),
        }

    def api_rss_tasks(self, offset: int = 0, limit: int = 100) -> Dict[str, Any]:
        return {
            "success": True,
            **self._require_store().list_rss_tasks(offset=offset, limit=limit),
        }

    def api_rss_history(self, offset: int = 0, limit: int = 50) -> Dict[str, Any]:
        return {
            "success": True,
            **self._require_store().list_rss_history(offset=offset, limit=limit),
        }

    def api_background_tasks(self, offset: int = 0, limit: int = 50) -> Dict[str, Any]:
        return {
            "success": True,
            **self._require_store().list_background_tasks(offset=offset, limit=limit),
        }

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
        return {
            "enabled": False,
            "database_filename": "rssallinone.db",
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
