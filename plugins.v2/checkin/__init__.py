"""MoviePilot V2 check-in plugin for SMZDM and Chiphell."""

from __future__ import annotations

import json
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
SMZDM_API_CHECKIN_URL = "https://api.smzdm.com/v1/user/checkin"
SMZDM_API_INFO_URL = "https://api.smzdm.com/v1/user/info"
CHIPHELL_URL = "https://www.chiphell.com/forum.php"
SMZDM_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36"
)
SUCCESS_STATUSES = {"success", "already"}


class Checkin(_PluginBase):
    plugin_name = "签到助手"
    plugin_desc = "通过 MoviePilot CloakBrowser 执行什么值得买签到和 Chiphell 登录保活。"
    plugin_icon = (
        "https://raw.githubusercontent.com/jxxghp/"
        "MoviePilot-Plugins/main/icons/signin.png"
    )
    plugin_version = "0.1.5"
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

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {"model": "enabled", "label": "启用插件"},
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {"model": "onlyonce", "label": "立即运行一次"},
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {"model": "notify", "label": "失败结果通知（成功必发）"},
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "history_days",
                                        "label": "历史保留天数",
                                        "type": "number",
                                        "min": 1,
                                        "max": 365,
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {
                                        "model": "smzdm_enabled",
                                        "label": "什么值得买定时签到",
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 8},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "smzdm_cron",
                                        "label": "什么值得买执行周期",
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "smzdm_cookie",
                                        "label": "什么值得买 Cookie",
                                        "type": "password",
                                        "autocomplete": "new-password",
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {
                                        "model": "chiphell_enabled",
                                        "label": "Chiphell 定时保活",
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 8},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "chiphell_cron",
                                        "label": "Chiphell 执行周期",
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "chiphell_cookie",
                                        "label": "Chiphell Cookie",
                                        "type": "password",
                                        "autocomplete": "new-password",
                                    },
                                }],
                            },
                        ],
                    },
                ],
            }
        ], self._default_config()

    def get_page(self) -> List[dict]:
        return [{
            "component": "VCard",
            "props": {
                "title": "签到历史",
                "subtitle": "最近 50 条记录；打开此页面即可查看最新结果",
                "variant": "tonal",
            },
            "content": [{
                "component": "VCardText",
                "content": [{
                    "component": "VDataTableVirtual",
                    "props": {
                        "headers": [
                            {"title": "时间", "key": "date"},
                            {"title": "站点", "key": "site_name"},
                            {"title": "状态", "key": "status_label"},
                            {"title": "连续天数", "key": "streak_days"},
                            {"title": "说明", "key": "message"},
                            {"title": "触发", "key": "trigger_label"},
                        ],
                        "items": self._history_rows(),
                        "height": "32rem",
                        "density": "compact",
                        "fixed-header": True,
                        "hide-no-data": False,
                        "hover": True,
                    },
                }],
            }],
        }]

    def _history_rows(self) -> List[Dict[str, Any]]:
        status_labels = {
            "success": "成功",
            "already": "今日已完成",
            "failed": "失败",
            "busy": "执行中",
        }
        rows = []
        history = [
            record for record in (self.get_data("history") or [])
            if isinstance(record, dict)
        ]
        for record in reversed(history):
            if not isinstance(record, dict):
                continue
            streak_days = self._positive_int(record.get("streak_days"))
            if streak_days is None and record.get("status") in SUCCESS_STATUSES:
                streak_days = self._calculate_streak(record, records=history)
            row = {
                "date": str(record.get("date") or ""),
                "site_name": str(record.get("site_name") or SITE_NAMES.get(record.get("site"), "")),
                "status_label": status_labels.get(
                    str(record.get("status") or ""), str(record.get("status") or "未知")
                ),
                "streak_days": (
                    f"{streak_days} 天"
                    if streak_days is not None
                    else "-"
                ),
                "message": str(record.get("message") or ""),
                "trigger_label": "手动" if record.get("trigger") == "manual" else "定时",
            }
            rows.append(row)
            if len(rows) >= 50:
                break
        return rows

    def get_api(self) -> List[Dict[str, Any]]:
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
        result = self._browser_action(
            url=SMZDM_API_CHECKIN_URL,
            cookie=cookie,
            callback=self._smzdm_api_handler,
            ua=SMZDM_MOBILE_UA,
        )
        if result and result.get("status") in SUCCESS_STATUSES:
            return result

        checkin_url = f"{SMZDM_CHECKIN_URL}?_={int(time.time() * 1000)}"

        def page_handler(page) -> Dict[str, Any]:
            try:
                body = page.inner_text("body")
            except Exception:
                body = page.content()
            return parse_smzdm_response(body)

        fallback = self._browser_action(
            url=checkin_url,
            cookie=cookie,
            callback=page_handler,
        )
        if fallback:
            return fallback
        return result or {
            "status": "failed",
            "message": "CloakBrowser 未返回签到响应，请检查浏览器组件和网络",
        }

    @staticmethod
    def _smzdm_api_handler(page) -> Dict[str, Any]:
        payload = page.evaluate(
            """
            async ({url, body}) => {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
                    body,
                    credentials: 'include',
                });
                const checkin = await response.text();
                let info = '';
                try {
                    const infoResponse = await fetch(infoUrl, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
                        body,
                        credentials: 'include',
                    });
                    info = await infoResponse.text();
                } catch (_) {
                    info = '';
                }
                return {checkin, info};
            }
            """,
            {
                "url": SMZDM_API_CHECKIN_URL,
                "infoUrl": SMZDM_API_INFO_URL,
                "body": "weixin=1&f=android&v=8.7.8&captcha=",
            },
        )
        if isinstance(payload, dict) and "checkin" in payload:
            result = parse_smzdm_response(str(payload.get("checkin") or ""))
            info = str(payload.get("info") or "")
            if info:
                try:
                    info_result = parse_smzdm_response(info)
                except (TypeError, ValueError, json.JSONDecodeError):
                    info_result = {}
                if info_result.get("days"):
                    result["days"] = info_result["days"]
            return result
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, ensure_ascii=False)
        return parse_smzdm_response(str(payload or ""))

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
    def _browser_action(
        url: str,
        cookie: str,
        callback,
        ua: str = DESKTOP_UA,
    ) -> Optional[Dict[str, Any]]:
        from app.helper.browser import PlaywrightHelper

        return PlaywrightHelper().action(
            url=url,
            callback=callback,
            cookies=cookie,
            ua=ua,
            headless=True,
            timeout=60,
        )

    def _decorate_result(
        self,
        site: str,
        result: Dict[str, Any],
        manual: bool,
    ) -> Dict[str, Any]:
        record = {
            "site": site,
            "site_name": SITE_NAMES[site],
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trigger": "manual" if manual else "scheduled",
            **dict(result or {}),
        }
        if record.get("status") in SUCCESS_STATUSES:
            reported_days = self._positive_int(record.get("days"))
            record["streak_days"] = reported_days or self._calculate_streak(record)
        return record

    def _calculate_streak(
        self,
        current: Dict[str, Any],
        records: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        try:
            current_day = datetime.strptime(
                str(current.get("date") or ""), "%Y-%m-%d %H:%M:%S"
            ).date()
        except ValueError:
            return 1
        successful_days = {current_day}
        for record in records if records is not None else (self.get_data("history") or []):
            if not isinstance(record, dict):
                continue
            if record.get("site") != current.get("site"):
                continue
            if record.get("status") not in SUCCESS_STATUSES:
                continue
            try:
                day = datetime.strptime(
                    str(record.get("date") or ""), "%Y-%m-%d %H:%M:%S"
                ).date()
            except ValueError:
                continue
            if day > current_day:
                continue
            successful_days.add(day)
        streak = 0
        day = current_day
        while day in successful_days:
            streak += 1
            day = day.fromordinal(day.toordinal() - 1)
        return streak

    @staticmethod
    def _positive_int(value: Any) -> Optional[int]:
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    def _append_history(self, record: Dict[str, Any]) -> None:
        with self._history_lock:
            history = list(self.get_data("history") or [])
            history.append(record)
            self.save_data(
                "history",
                prune_history(history, keep_days=self._history_days),
            )

    def _notify_result(self, record: Dict[str, Any]) -> None:
        if record.get("status") == "busy":
            return
        if record.get("status") not in SUCCESS_STATUSES and not self._notify:
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
            ("streak_days", "连续天数"),
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
