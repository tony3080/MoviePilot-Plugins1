"""MoviePilot V2 check-in plugin for SMZDM and Chiphell."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.triggers.cron import CronTrigger

from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import NotificationType

from .core import (
    SITE_NAMES,
    normalize_cookie,
    parse_chiphell_page,
    parse_smzdm_response,
    prune_history,
)


DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
SMZDM_CHECKIN_URL = "https://zhiyou.smzdm.com/user/checkin/jsonp_checkin"
CHIPHELL_URL = "https://www.chiphell.com/forum.php"
SUCCESS_STATUSES = {"success", "already"}


class Checkin(_PluginBase):
    plugin_name = "签到助手"
    plugin_desc = "通过 MoviePilot CloakBrowser 执行什么值得买签到和 Chiphell 登录保活。"
    plugin_icon = (
        "https://raw.githubusercontent.com/jxxghp/"
        "MoviePilot-Plugins/main/icons/signin.png"
    )
    plugin_version = "0.1.0"
    plugin_author = "tony3080"
    author_url = "https://github.com/tony3080"
    plugin_config_prefix = "checkin_"
    plugin_order = 55
    auth_level = 2

    _enabled = False
    _onlyonce = False
    _notify = True
    _history_days = 30
    _smzdm_enabled = False
    _smzdm_cookie = ""
    _smzdm_cron = "0 9 * * *"
    _chiphell_enabled = False
    _chiphell_cookie = ""
    _chiphell_cron = "10 9 * * *"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._history_lock = threading.RLock()
        self._run_locks = {
            "smzdm": threading.Lock(),
            "chiphell": threading.Lock(),
        }

    def init_plugin(self, config: dict = None) -> None:
        config = config or {}
        defaults = self._default_config()
        self._enabled = bool(config.get("enabled", defaults["enabled"]))
        self._onlyonce = bool(config.get("onlyonce", defaults["onlyonce"]))
        self._notify = bool(config.get("notify", defaults["notify"]))
        self._history_days = self._bounded_int(
            config.get("history_days"), defaults["history_days"], 1, 365,
        )
        self._smzdm_enabled = bool(
            config.get("smzdm_enabled", defaults["smzdm_enabled"])
        )
        self._smzdm_cookie = normalize_cookie(config.get("smzdm_cookie", ""))
        self._smzdm_cron = str(
            config.get("smzdm_cron") or defaults["smzdm_cron"]
        ).strip()
        self._chiphell_enabled = bool(
            config.get("chiphell_enabled", defaults["chiphell_enabled"])
        )
        self._chiphell_cookie = normalize_cookie(config.get("chiphell_cookie", ""))
        self._chiphell_cron = str(
            config.get("chiphell_cron") or defaults["chiphell_cron"]
        ).strip()

        if self._onlyonce:
            self._onlyonce = False
            self._save_config()
            threading.Thread(
                target=self._run_enabled_sites,
                kwargs={"manual": True},
                daemon=True,
                name="checkin-run-once",
            ).start()

    @staticmethod
    def _default_config() -> Dict[str, Any]:
        return {
            "enabled": False,
            "onlyonce": False,
            "notify": True,
            "history_days": 30,
            "smzdm_enabled": False,
            "smzdm_cookie": "",
            "smzdm_cron": "0 9 * * *",
            "chiphell_enabled": False,
            "chiphell_cookie": "",
            "chiphell_cron": "10 9 * * *",
        }

    @staticmethod
    def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(minimum, min(number, maximum))

    def _save_config(self) -> None:
        self.update_config({
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "notify": self._notify,
            "history_days": self._history_days,
            "smzdm_enabled": self._smzdm_enabled,
            "smzdm_cookie": self._smzdm_cookie,
            "smzdm_cron": self._smzdm_cron,
            "chiphell_enabled": self._chiphell_enabled,
            "chiphell_cookie": self._chiphell_cookie,
            "chiphell_cron": self._chiphell_cron,
        })

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
            "name": "签到助手",
            "icon": "tabler:calendar-check",
            "path": "/checkin",
            "nav_key": "checkin",
        }]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [], self._default_config()

    @staticmethod
    def get_page() -> List[dict]:
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        services = []
        definitions = (
            ("smzdm", self._smzdm_enabled, self._smzdm_cron),
            ("chiphell", self._chiphell_enabled, self._chiphell_cron),
        )
        for site, enabled, cron in definitions:
            if not enabled or not cron:
                continue
            try:
                trigger = CronTrigger.from_crontab(cron)
            except (TypeError, ValueError) as error:
                logger.error(f"签到助手：{SITE_NAMES[site]} Cron 无效：{error}")
                continue
            services.append({
                "id": f"Checkin.{site}",
                "name": f"签到助手 {SITE_NAMES[site]}",
                "trigger": trigger,
                "func": self._scheduled_run,
                "func_kwargs": {"site": site},
            })
        return services

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/run",
                "endpoint": self.api_run,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即执行签到",
            },
            {
                "path": "/history",
                "endpoint": self.api_history,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "查询签到历史",
            },
            {
                "path": "/history/clear",
                "endpoint": self.api_clear_history,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "清空签到历史",
            },
        ]

    def api_run(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        site = str((payload or {}).get("site") or "all").strip().lower()
        if site not in {"all", "smzdm", "chiphell"}:
            return {"success": False, "message": "不支持的签到站点"}
        records = (
            self._run_enabled_sites(manual=True)
            if site == "all"
            else [self._run_site(site, manual=True)]
        )
        success = all(record.get("status") in SUCCESS_STATUSES for record in records)
        return {
            "success": success,
            "message": "签到执行完成" if success else "签到执行完成，存在失败项目",
            "items": records,
        }

    def api_history(self) -> Dict[str, Any]:
        items = list(reversed(self.get_data("history") or []))
        return {
            "success": True,
            "items": items,
            "total": len(items),
            "running": {
                site: lock.locked() for site, lock in self._run_locks.items()
            },
        }

    def api_clear_history(self) -> Dict[str, Any]:
        with self._history_lock:
            self.save_data("history", [])
        return {"success": True, "message": "签到历史已清空"}

    def _scheduled_run(self, site: str) -> Dict[str, Any]:
        return self._run_site(site, manual=False)

    def _run_enabled_sites(self, manual: bool) -> List[Dict[str, Any]]:
        sites = []
        if self._smzdm_enabled:
            sites.append("smzdm")
        if self._chiphell_enabled:
            sites.append("chiphell")
        if manual and not sites:
            sites = ["smzdm", "chiphell"]
        return [self._run_site(site, manual=manual) for site in sites]

    def _run_site(self, site: str, manual: bool) -> Dict[str, Any]:
        lock = self._run_locks[site]
        if not lock.acquire(blocking=False):
            return self._decorate_result(site, {
                "status": "busy",
                "message": "该站点已有签到任务正在执行",
            }, manual)
        try:
            cookie = self._smzdm_cookie if site == "smzdm" else self._chiphell_cookie
            if not cookie:
                result = {
                    "status": "failed",
                    "message": f"未配置 {SITE_NAMES[site]} Cookie",
                }
            elif site == "smzdm":
                result = self._run_smzdm(cookie)
            else:
                result = self._run_chiphell(cookie)
        except Exception as error:
            logger.error(f"签到助手：{SITE_NAMES[site]} 执行异常：{error}", exc_info=True)
            result = {"status": "failed", "message": str(error)}
        finally:
            lock.release()

        record = self._decorate_result(site, result, manual)
        self._append_history(record)
        self._notify_result(record)
        level = "info" if record["status"] in SUCCESS_STATUSES else "warning"
        getattr(logger, level)(
            f"签到助手：{record['site_name']} {record['message']}"
        )
        return record

    def _run_smzdm(self, cookie: str) -> Dict[str, Any]:
        checkin_url = f"{SMZDM_CHECKIN_URL}?_={int(time.time() * 1000)}"

        def page_handler(page) -> Dict[str, Any]:
            try:
                body = page.inner_text("body")
            except Exception:
                body = page.content()
            return parse_smzdm_response(body)

        result = self._browser_action(
            url=checkin_url,
            cookie=cookie,
            callback=page_handler,
        )
        return result or {
            "status": "failed",
            "message": "CloakBrowser 未返回签到响应，请检查浏览器组件和网络",
        }

    def _run_chiphell(self, cookie: str) -> Dict[str, Any]:
        def page_handler(page) -> Dict[str, Any]:
            cookies = page.context.cookies()
            return parse_chiphell_page(page.content(), cookies=cookies)

        result = self._browser_action(
            url=CHIPHELL_URL,
            cookie=cookie,
            callback=page_handler,
        )
        return result or {
            "status": "failed",
            "message": "CloakBrowser 未返回论坛页面，请检查浏览器组件和网络",
        }

    @staticmethod
    def _browser_action(url: str, cookie: str, callback) -> Optional[Dict[str, Any]]:
        from app.helper.browser import PlaywrightHelper

        return PlaywrightHelper().action(
            url=url,
            callback=callback,
            cookies=cookie,
            ua=DESKTOP_UA,
            headless=True,
            timeout=60,
        )

    @staticmethod
    def _decorate_result(
        site: str,
        result: Dict[str, Any],
        manual: bool,
    ) -> Dict[str, Any]:
        return {
            "site": site,
            "site_name": SITE_NAMES[site],
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trigger": "manual" if manual else "scheduled",
            **dict(result or {}),
        }

    def _append_history(self, record: Dict[str, Any]) -> None:
        with self._history_lock:
            history = list(self.get_data("history") or [])
            history.append(record)
            self.save_data(
                "history",
                prune_history(history, keep_days=self._history_days),
            )

    def _notify_result(self, record: Dict[str, Any]) -> None:
        if not self._notify or record.get("status") == "busy":
            return
        status_labels = {
            "success": "成功",
            "already": "今日已完成",
            "failed": "失败",
        }
        details = [
            f"状态：{status_labels.get(record.get('status'), record.get('status'))}",
            f"说明：{record.get('message') or '-'}",
        ]
        for key, label in (
            ("username", "账号"),
            ("days", "连续签到"),
            ("points", "积分"),
            ("experience", "经验"),
            ("gold", "金币"),
        ):
            value = str(record.get(key) or "").strip()
            if value:
                suffix = " 天" if key == "days" else ""
                details.append(f"{label}：{value}{suffix}")
        details.extend([
            f"触发：{'手动' if record.get('trigger') == 'manual' else '定时'}",
            f"时间：{record.get('date')}",
        ])
        try:
            self.post_message(
                mtype=NotificationType.Plugin,
                title=f"签到助手：{record.get('site_name')}",
                text="\n".join(details),
            )
        except Exception as error:
            logger.warning(
                f"签到助手：{record.get('site_name')} 结果通知发送失败：{error}"
            )

    def stop_service(self) -> None:
        pass

    def close(self) -> None:
        self.stop_service()
