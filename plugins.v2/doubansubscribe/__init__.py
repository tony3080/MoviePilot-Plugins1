"""RSS-driven Douban to TMDB subscription plugin for MoviePilot V2."""

from __future__ import annotations

import datetime
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from apscheduler.triggers.cron import CronTrigger

from app.core.event import Event, eventmanager
from app.core.config import settings
from app.core.metainfo import MetaInfo
from app.db.models.subscribe import Subscribe
from app.db.subscribe_oper import SubscribeOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import LimitException, SubscribeCompletionCheckEventData
from app.schemas.types import ChainEventType, MediaType
from app.chain.subscribe import SubscribeChain
from app.chain.tmdb import TmdbChain
from app.utils.http import RequestUtils

from .core import (
    FeedItem,
    MEDIA_CATEGORY_LABELS,
    MatchDecision,
    ScoredCandidate,
    TmdbCandidate,
    arc_name_match_score,
    build_search_hypotheses,
    build_title_hypotheses,
    classify_media_region,
    choose_match,
    extract_total_episode,
    has_started_airing,
    parse_feed,
    person_names,
    score_candidate,
)


DEFAULT_RSS_URL = "http://192.168.110.31:9150/rsshub/hot_tv"
DEFAULT_CRON = "0 */6 * * *"
MAOYAN_HEAT_URL = "https://piaofang.maoyan.com/dashboard/webHeatData"
MAOYAN_LIST_TYPES = {
    "tv": {"label": "电视剧热度榜", "series_type": 0},
    "web": {"label": "网剧热度榜", "series_type": 1},
}
DEFAULT_MAOYAN_TYPES = tuple(MAOYAN_LIST_TYPES)
DAILY_SUPPLEMENT_SNAPSHOT_CRON = "0 8 * * *"
DEFAULT_SUPPLEMENT_CRON = "0 23 * * *"
SUPPLEMENT_SEARCH_INTERVAL_SECONDS = 120
DOUBAN_QUERY_INTERVAL_SECONDS = 3
IMDB_ID_PATTERN = re.compile(r"\btt\d{7,10}\b", re.IGNORECASE)
ACTIVE_SUBSCRIBE_STATES = {"N", "R", "P"}
SUPPLEMENT_DATA_KEY = "daily_supplement_snapshot"
CATEGORY_SKIP_DATA_KEY = "category_skip_items"
PLUGIN_USERNAME = "豆瓣订阅助手"
SUCCESS_STATUSES = {"subscribed", "existing", "history_existing"}
SKIPPED_STATUSES = {"category_skipped"}
FAILURE_STATUSES = {
    "ambiguous",
    "douban_not_found",
    "douban_rate_limited",
    "douban_total_missing",
    "error",
    "feed_error",
    "lock_failed",
    "low_score",
    "maoyan_error",
    "no_candidate",
    "subscribe_failed",
    "tmdb_detail_missing",
    "tmdb_search_empty",
    "tmdb_search_error",
}
STATUS_GROUPS = {
    "success": SUCCESS_STATUSES,
    "skipped": SKIPPED_STATUSES,
    "failure": FAILURE_STATUSES,
}
TMDB_RETRY_DELAYS = (2, 5)
DEFAULT_MEDIA_CATEGORIES = tuple(MEDIA_CATEGORY_LABELS)
RECENT_HISTORY_LIMIT = 50
UNKNOWN_TOTAL_EPISODE = 100


class DoubanSubscribe(_PluginBase):
    """Create locked MoviePilot subscriptions from user-provided RSS feeds."""

    plugin_name = "豆瓣订阅助手"
    plugin_desc = "从 RSS 和猫眼榜单发现剧集，锁定豆瓣总集数，并补搜今日未更新订阅。"
    plugin_icon = (
        "https://raw.githubusercontent.com/jxxghp/"
        "MoviePilot-Plugins/main/icons/douban.png"
    )
    plugin_version = "0.5.6"
    plugin_author = "tony3080"
    author_url = "https://github.com/tony3080"
    plugin_config_prefix = "doubansubscribe_"
    plugin_order = 50
    auth_level = 2

    _enabled = False
    _onlyonce = False
    _proxy = False
    _rss_urls = DEFAULT_RSS_URL
    _maoyan_enabled = False
    _maoyan_types = list(DEFAULT_MAOYAN_TYPES)
    _maoyan_num = 10
    _cron = DEFAULT_CRON
    _supplement_cron = DEFAULT_SUPPLEMENT_CRON
    _max_items = 50
    _candidate_limit = 10
    _confirmation_days = 7
    _notify_subscription = True
    _media_categories = list(DEFAULT_MEDIA_CATEGORIES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sync_lock = threading.Lock()
        self._data_lock = threading.RLock()
        self._supplement_lock = threading.Lock()
        self._douban_query_lock = threading.Lock()
        self._last_douban_query_at = 0.0
        self._douban_imdb_cache: Dict[str, str] = {}

    def init_plugin(self, config: dict = None) -> None:
        """Load configuration and optionally start a one-time run."""
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        self._onlyonce = bool(config.get("onlyonce", False))
        self._proxy = bool(config.get("proxy", False))
        self._rss_urls = (
            config.get("rss_urls")
            if "rss_urls" in config
            else DEFAULT_RSS_URL
        )
        self._maoyan_enabled = bool(config.get("maoyan_enabled", False))
        maoyan_types = config.get("maoyan_types", list(DEFAULT_MAOYAN_TYPES))
        if isinstance(maoyan_types, str):
            maoyan_types = [value.strip() for value in maoyan_types.split(",")]
        self._maoyan_types = [
            value for value in (maoyan_types or [])
            if value in MAOYAN_LIST_TYPES
        ]
        self._maoyan_num = self._bounded_int(
            config.get("maoyan_num"),
            10,
            1,
            30,
        )
        self._cron = str(config.get("cron") or DEFAULT_CRON).strip()
        self._supplement_cron = str(
            config.get("supplement_cron") or DEFAULT_SUPPLEMENT_CRON
        ).strip()
        self._max_items = self._bounded_int(config.get("max_items"), 50, 1, 200)
        self._candidate_limit = self._bounded_int(config.get("candidate_limit"), 10, 1, 30)
        self._confirmation_days = self._bounded_int(
            config.get("confirmation_days"), 7, 1, 365,
        )
        self._notify_subscription = bool(config.get("notify_subscription", True))
        categories = config.get("media_categories", list(DEFAULT_MEDIA_CATEGORIES))
        if isinstance(categories, str):
            categories = [value.strip() for value in categories.split(",")]
        self._media_categories = [
            value for value in (categories or [])
            if value in MEDIA_CATEGORY_LABELS
        ]

        if self._onlyonce:
            self._onlyonce = False
            self._save_config()
            self._start_sync_thread()

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
            "proxy": self._proxy,
            "rss_urls": self._rss_urls,
            "maoyan_enabled": self._maoyan_enabled,
            "maoyan_types": self._maoyan_types,
            "maoyan_num": self._maoyan_num,
            "cron": self._cron,
            "supplement_cron": self._supplement_cron,
            "max_items": self._max_items,
            "candidate_limit": self._candidate_limit,
            "confirmation_days": self._confirmation_days,
            "notify_subscription": self._notify_subscription,
            "media_categories": self._media_categories,
        })

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/run",
                "endpoint": self.api_run,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即处理 RSS",
            },
            {
                "path": "/history",
                "endpoint": self.api_history,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "查询最近处理历史",
            },
            {
                "path": "/history/search",
                "endpoint": self.api_search_history,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "搜索全部处理历史",
            },
            {
                "path": "/history/retry",
                "endpoint": self.api_retry_history,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "重试单条失败记录",
            },
        ]

    def api_run(self) -> Dict[str, Any]:
        if self._sync_lock.locked():
            return {"success": False, "message": "内容源处理正在运行"}
        self._start_sync_thread()
        return {"success": True, "message": "内容源处理已启动"}

    def api_history(self) -> Dict[str, Any]:
        history = list(reversed(self.get_data("history") or []))
        return {
            "success": True,
            "last_run": self.get_data("last_run") or {},
            "total": len(history),
            "items": history[:RECENT_HISTORY_LIMIT],
            "managed": self._managed_records(),
            "supplement": self._supplement_snapshot(),
        }

    def api_search_history(
        self,
        keyword: str = "",
        status: str = "",
        group: str = "",
        category: str = "",
        offset: int = 0,
        limit: int = RECENT_HISTORY_LIMIT,
    ) -> Dict[str, Any]:
        """Search the complete, untrimmed RSS processing history."""
        safe_offset = self._bounded_int(offset, 0, 0, 1_000_000_000)
        safe_limit = self._bounded_int(limit, RECENT_HISTORY_LIMIT, 1, 200)
        keyword = str(keyword or "").strip().casefold()
        status = str(status or "").strip()
        group = str(group or "").strip()
        category = str(category or "").strip()
        records = list(reversed(self.get_data("history") or []))
        matches = [
            record for record in records
            if (not status or str(record.get("status") or "") == status)
            and (
                not group
                or str(record.get("status") or "") in STATUS_GROUPS.get(group, set())
            )
            and (not category or str(record.get("category") or "") == category)
            and (not keyword or keyword in self._history_search_text(record))
        ]
        items = [dict(record) for record in matches[safe_offset:safe_offset + safe_limit]]
        for record in items:
            record["retryable"] = self._is_retryable_history_record(record)
        return {
            "success": True,
            "total": len(matches),
            "offset": safe_offset,
            "limit": safe_limit,
            "items": items,
        }

    def api_retry_history(
        self,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Retry one failed content item without starting a complete source run."""
        key = str((payload or {}).get("key") or "").strip()
        if not key:
            return {"success": False, "message": "缺少记录 key"}
        if not self._sync_lock.acquire(blocking=False):
            return {"success": False, "message": "内容源处理正在运行，请稍后重试"}
        try:
            history = self.get_data("history") or []
            source = next(
                (record for record in history if str(record.get("key") or "") == key),
                None,
            )
            if not source:
                return {"success": False, "message": "未找到该处理记录"}
            if not self._is_retryable_history_record(source):
                return {"success": False, "message": "该记录不是可重试的失败条目"}
            item = FeedItem(
                title=str(source.get("title") or ""),
                link=str(source.get("link") or ""),
                guid=str(source.get("guid") or ""),
                description=str(source.get("description") or ""),
                published=str(source.get("published") or ""),
                source_url=str(source.get("source_url") or ""),
                douban_id=str(source.get("douban_id") or "") or None,
                year=str(source.get("year") or "") or None,
                poster=str(source.get("poster") or ""),
            )
            record = self._process_item(item)
            record["key"] = key
            self._record_history(history, record)
            self.save_data("history", history)
            if record.get("status") in SUCCESS_STATUSES:
                processed = self._processed_index(history)
                self._mark_processed(processed, key, record)
            return {
                "success": True,
                "message": "重试完成",
                "item": record,
            }
        except Exception as error:
            logger.error(f"豆瓣订阅助手：重试记录 {key} 失败：{error}", exc_info=True)
            return {"success": False, "message": str(error)}
        finally:
            self._sync_lock.release()

    @staticmethod
    def _is_retryable_history_record(record: Dict[str, Any]) -> bool:
        return (
            str(record.get("status") or "") in FAILURE_STATUSES
            and str(record.get("status") or "") not in {"feed_error", "maoyan_error"}
            and bool(record.get("title"))
        )

    @staticmethod
    def _history_search_text(record: Dict[str, Any]) -> str:
        fields = (
            "key", "title", "douban_title", "douban_id", "tmdb_id",
            "source_url", "status", "category", "reason",
        )
        values = []
        for field in fields:
            value = record.get(field)
            if isinstance(value, (list, tuple, set)):
                values.extend(str(item) for item in value)
            elif value is not None:
                values.append(str(value))
        return " ".join(values).casefold()

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        services = []
        if self._cron:
            try:
                services.append({
                    "id": "DoubanSubscribe.Sync",
                    "name": "豆瓣订阅助手 内容源处理",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.sync,
                    "kwargs": {},
                })
            except (TypeError, ValueError) as error:
                logger.error(
                    f"豆瓣订阅助手：无效的 RSS Cron 表达式 {self._cron}：{error}"
                )
        if self._supplement_cron:
            try:
                services.extend([
                    {
                        "id": "DoubanSubscribe.SupplementSnapshot",
                        "name": "豆瓣订阅助手 今日更新快照",
                        "trigger": CronTrigger.from_crontab(
                            DAILY_SUPPLEMENT_SNAPSHOT_CRON
                        ),
                        "func": self.capture_daily_supplement_snapshot,
                        "kwargs": {},
                    },
                    {
                        "id": "DoubanSubscribe.SupplementSearch",
                        "name": "豆瓣订阅助手 订阅补齐",
                        "trigger": CronTrigger.from_crontab(self._supplement_cron),
                        "func": self.run_daily_supplement,
                        "kwargs": {},
                    },
                ])
            except (TypeError, ValueError) as error:
                logger.error(
                    "豆瓣订阅助手：无效的订阅补齐 Cron 表达式 "
                    f"{self._supplement_cron}：{error}"
                )
        return services

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [], self._default_config()

    def _legacy_get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
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
                                    "props": {"model": "proxy", "label": "RSS 使用代理"},
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {
                                        "model": "notify_subscription",
                                        "label": "订阅成功通知",
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VTextarea",
                                    "props": {
                                        "model": "rss_urls",
                                        "label": "RSS 地址（每行一个）",
                                        "rows": 4,
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "supplement_cron",
                                        "label": "订阅补齐执行周期",
                                        "hint": "每天 08:00 记录今日更新订阅；到此周期仍无进度时触发搜索",
                                        "persistent-hint": True,
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {"model": "cron", "label": "执行周期"},
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "max_items",
                                        "label": "每个 RSS 最大条目数",
                                        "type": "number",
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "confirmation_days",
                                        "label": "确认完成天数",
                                        "type": "number",
                                        "min": 1,
                                        "max": 365,
                                        "hint": "订阅完成后暂停，等待该天数再查看豆瓣总集数是否增加",
                                        "persistent-hint": True,
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VSelect",
                                    "props": {
                                        "model": "media_categories",
                                        "label": "需要订阅的剧集类型",
                                        "items": [
                                            {"title": label, "value": value}
                                            for value, label in MEDIA_CATEGORY_LABELS.items()
                                        ],
                                        "multiple": True,
                                        "chips": True,
                                        "closable-chips": True,
                                        "clearable": True,
                                        "hint": "RSS 识别出豆瓣条目后，先按国家或地区分类再决定是否订阅",
                                        "persistent-hint": True,
                                    },
                                }],
                            },
                        ],
                    }
                ],
            }
        ], self._default_config()

    @staticmethod
    def _default_config() -> Dict[str, Any]:
        return {
            "enabled": False,
            "onlyonce": False,
            "proxy": False,
            "rss_urls": DEFAULT_RSS_URL,
            "maoyan_enabled": False,
            "maoyan_types": list(DEFAULT_MAOYAN_TYPES),
            "maoyan_num": 10,
            "cron": DEFAULT_CRON,
            "supplement_cron": DEFAULT_SUPPLEMENT_CRON,
            "max_items": 50,
            "candidate_limit": 10,
            "confirmation_days": 7,
            "notify_subscription": True,
            "media_categories": list(DEFAULT_MEDIA_CATEGORIES),
        }

    def get_page(self) -> List[dict]:
        return []

    def _legacy_get_page(self) -> List[dict]:
        history = list(reversed(self.get_data("history") or []))
        managed = self._managed_records()
        supplement = self._supplement_snapshot()
        if not history and not managed and not supplement:
            return [{
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "variant": "tonal",
                    "text": "暂无 RSS 处理记录或受管订阅",
                },
            }]
        status_labels = {
            "active": "订阅中",
            "awaiting_douban_total": "订阅中，等待豆瓣总集数",
            "waiting_confirmation": "已暂停，等待复核豆瓣",
            "confirming": "正在复核豆瓣",
            "finalizing": "正在正常完成",
            "completed": "已完成",
            "manual_review": "等待手动处理",
            "verification_error": "确认失败，等待重试",
            "missing_subscription": "订阅卡片不存在",
        }
        managed_items = []
        for record in managed:
            managed_items.append({
                "subscribe_id": record.get("subscribe_id") or "",
                "title": record.get("title") or "",
                "category": MEDIA_CATEGORY_LABELS.get(
                    record.get("category"), record.get("category") or "",
                ),
                "total": (
                    "待获取"
                    if record.get("total_pending")
                    else record.get("expected_total") or ""
                ),
                "mp_total": record.get("manual_total") or record.get("expected_total") or "",
                "status": status_labels.get(
                    record.get("status"), record.get("status") or "",
                ),
                "check_after": record.get("check_after") or "",
                "reason": record.get("reason") or "",
            })

        history_items = []
        for record in history[:RECENT_HISTORY_LIMIT]:
            history_items.append({
                "title": record.get("title") or "",
                "status": record.get("status") or "",
                "category": MEDIA_CATEGORY_LABELS.get(
                    record.get("category"), record.get("category") or "",
                ),
                "douban_total": record.get("douban_total") or "",
                "tmdb": (
                    f"{record.get('tmdb_id')} / {self._season_label(record.get('season'))}"
                    if record.get("tmdb_id") else ""
                ),
                "time": record.get("time") or "",
                "reason": record.get("reason") or "",
            })

        supplement_status_labels = {
            "pending": "等待晚间检查",
            "needs_search": "等待触发搜索",
            "updated": "今日已有更新",
            "search_triggered": "已触发补齐搜索",
            "search_error": "补齐搜索失败",
            "missing_subscription": "订阅卡片不存在",
            "inactive": "订阅已暂停或完成",
            "identity_changed": "订阅信息已变化",
        }
        supplement_items = []
        for item in (supplement.get("items") or {}).values():
            baseline_completed = item.get("baseline_completed")
            baseline_total = item.get("baseline_total")
            current_completed = item.get("current_completed")
            current_total = item.get("current_total")
            supplement_items.append({
                "subscribe_id": item.get("subscribe_id") or "",
                "title": item.get("title") or "",
                "episodes": ", ".join(
                    f"E{number}" for number in (item.get("scheduled_episodes") or [])
                ),
                "morning_progress": (
                    f"{baseline_completed}/{baseline_total}"
                    if baseline_completed is not None and baseline_total is not None
                    else ""
                ),
                "current_progress": (
                    f"{current_completed}/{current_total}"
                    if current_completed is not None and current_total is not None
                    else ""
                ),
                "status": supplement_status_labels.get(
                    item.get("status"), item.get("status") or "",
                ),
                "reason": item.get("reason") or "",
            })
        return [{
            "component": "VRow",
            "content": [
                {
                    "component": "VCol",
                    "props": {"cols": 12},
                    "content": [{
                        "component": "VCard",
                        "props": {
                            "title": "受管订阅",
                            "subtitle": "完成后暂停、豆瓣总集数复核及手动接管状态",
                            "variant": "tonal",
                        },
                        "content": [{
                            "component": "VCardText",
                            "content": [{
                                "component": "VDataTableVirtual",
                                "props": {
                                    "headers": [
                                        {"title": "订阅ID", "key": "subscribe_id"},
                                        {"title": "标题", "key": "title"},
                                        {"title": "类型", "key": "category"},
                                        {"title": "豆瓣总集数", "key": "total"},
                                        {"title": "MP总集数", "key": "mp_total"},
                                        {"title": "状态", "key": "status"},
                                        {"title": "下次确认", "key": "check_after"},
                                        {"title": "说明", "key": "reason"},
                                    ],
                                    "items": managed_items,
                                    "height": "22rem",
                                    "density": "compact",
                                    "fixed-header": True,
                                    "hide-no-data": False,
                                    "hover": True,
                                },
                            }],
                        }],
                    }],
                },
                {
                    "component": "VCol",
                    "props": {"cols": 12},
                    "content": [{
                        "component": "VCard",
                        "props": {
                            "title": "RSS 处理记录",
                            "subtitle": "仅展示最近 50 条；可通过历史搜索接口查询全部记录",
                            "variant": "tonal",
                        },
                        "content": [{
                            "component": "VCardText",
                            "content": [{
                                "component": "VDataTableVirtual",
                                "props": {
                                    "headers": [
                                        {"title": "标题", "key": "title"},
                                        {"title": "状态", "key": "status"},
                                        {"title": "类型", "key": "category"},
                                        {"title": "豆瓣总集数", "key": "douban_total"},
                                        {"title": "TMDB / 季", "key": "tmdb"},
                                        {"title": "时间", "key": "time"},
                                        {"title": "原因", "key": "reason"},
                                    ],
                                    "items": history_items,
                                    "height": "30rem",
                                    "density": "compact",
                                    "fixed-header": True,
                                    "hide-no-data": False,
                                    "hover": True,
                                },
                            }],
                        }],
                    }],
                },
                {
                    "component": "VCol",
                    "props": {"cols": 12},
                    "content": [{
                        "component": "VCard",
                        "props": {
                            "title": "今日订阅补齐",
                            "subtitle": (
                                f"{supplement.get('date') or '尚无快照'}；"
                                "每天 08:00 记录进度，补齐周期仅处理当天未更新订阅"
                            ),
                            "variant": "tonal",
                        },
                        "content": [{
                            "component": "VCardText",
                            "content": [{
                                "component": "VDataTableVirtual",
                                "props": {
                                    "headers": [
                                        {"title": "订阅ID", "key": "subscribe_id"},
                                        {"title": "标题", "key": "title"},
                                        {"title": "今日排期", "key": "episodes"},
                                        {"title": "08:00 进度", "key": "morning_progress"},
                                        {"title": "当前进度", "key": "current_progress"},
                                        {"title": "状态", "key": "status"},
                                        {"title": "说明", "key": "reason"},
                                    ],
                                    "items": supplement_items,
                                    "height": "22rem",
                                    "density": "compact",
                                    "fixed-header": True,
                                    "hide-no-data": False,
                                    "hover": True,
                                },
                            }],
                        }],
                    }],
                },
            ],
        }]

    @staticmethod
    def _season_label(value: Any) -> str:
        try:
            return f"S{int(value or 1):02d}"
        except (TypeError, ValueError):
            return str(value or "")

    def stop_service(self) -> None:
        return None

    def _start_sync_thread(self) -> None:
        threading.Thread(
            target=self.sync,
            name="DoubanSubscribeSync",
            daemon=True,
        ).start()

    def capture_daily_supplement_snapshot(self) -> Dict[str, Any]:
        """Record progress for active TV subscriptions with episodes airing today."""
        if not self._supplement_lock.acquire(blocking=False):
            return {"success": False, "message": "订阅补齐任务正在运行"}
        try:
            now = self._now_datetime()
            today = now.date().isoformat()
            existing = self._supplement_snapshot()
            if existing.get("date") == today:
                return {
                    "success": True,
                    "message": "今日订阅快照已存在",
                    "date": today,
                    "today_updates": len(existing.get("items") or {}),
                    "already_captured": True,
                }

            items: Dict[str, Dict[str, Any]] = {}
            checked = 0
            failed = 0
            subscriptions = SubscribeOper().list(state="N,R,P") or []
            for subscribe in subscriptions:
                if not self._is_active_tv_subscription(subscribe):
                    continue
                checked += 1
                subscribe_id = getattr(subscribe, "id", None)
                tmdb_id = getattr(subscribe, "tmdbid", None)
                season = getattr(subscribe, "season", None)
                episode_group = getattr(subscribe, "episode_group", None)
                try:
                    episodes = TmdbChain().tmdb_episodes(
                        tmdbid=int(tmdb_id),
                        season=int(season),
                        episode_group=episode_group,
                    ) or []
                except Exception as error:
                    failed += 1
                    logger.error(
                        f"豆瓣订阅助手：查询订阅 {subscribe_id} 今日 TMDB 排期失败：{error}"
                    )
                    continue
                scheduled_episodes = self._episodes_airing_on(episodes, today)
                if not scheduled_episodes:
                    continue
                total, lack, completed = self._subscription_progress(subscribe)
                items[str(subscribe_id)] = {
                    "subscribe_id": subscribe_id,
                    "title": getattr(subscribe, "name", "") or "",
                    "tmdb_id": int(tmdb_id),
                    "season": int(season),
                    "episode_group": episode_group or "",
                    "scheduled_episodes": scheduled_episodes,
                    "baseline_completed": completed,
                    "baseline_total": total,
                    "baseline_lack": lack,
                    "current_completed": None,
                    "current_total": None,
                    "current_lack": None,
                    "status": "pending",
                    "checked_at": "",
                    "reason": "等待订阅补齐周期检查",
                }

            snapshot = {
                "date": today,
                "captured_at": self._format_datetime(now),
                "finished_at": "",
                "checked_subscriptions": checked,
                "tmdb_failures": failed,
                "items": items,
            }
            self._save_supplement_snapshot(snapshot)
            logger.info(
                f"豆瓣订阅助手：今日更新快照完成，检查 {checked} 个订阅，"
                f"记录 {len(items)} 个今日更新订阅"
            )
            return {
                "success": True,
                "date": today,
                "checked": checked,
                "today_updates": len(items),
                "failed": failed,
            }
        finally:
            self._supplement_lock.release()

    def run_daily_supplement(self) -> Dict[str, Any]:
        """Search today's scheduled subscriptions whose MoviePilot progress did not grow."""
        if not self._supplement_lock.acquire(blocking=False):
            return {"success": False, "message": "订阅补齐任务正在运行"}
        try:
            now = self._now_datetime()
            today = now.date().isoformat()
            snapshot = self._supplement_snapshot()
            if not snapshot:
                return {
                    "success": False,
                    "message": "没有今日 08:00 订阅快照，已跳过补齐",
                    "date": today,
                }
            if snapshot.get("date") != today:
                return {
                    "success": False,
                    "message": "订阅快照不是今天的数据，已跳过补齐",
                    "date": today,
                }
            if snapshot.get("finished_at"):
                return {
                    "success": True,
                    "message": "今日订阅补齐已经执行",
                    "date": today,
                    "already_finished": True,
                }

            items = snapshot.get("items") or {}
            search_items = []
            oper = SubscribeOper()
            checked_at = self._format_datetime(now)
            for item in items.values():
                status = str(item.get("status") or "pending")
                if status not in {"pending", "needs_search"}:
                    continue
                subscribe = oper.get(item.get("subscribe_id"))
                if not subscribe:
                    self._set_supplement_item_status(
                        item, "missing_subscription", checked_at,
                        "订阅卡片已不存在",
                    )
                    continue
                if not self._is_active_tv_subscription(subscribe):
                    self._set_supplement_item_status(
                        item, "inactive", checked_at,
                        "订阅已不在活动状态",
                    )
                    continue
                if (
                    self._safe_int(getattr(subscribe, "tmdbid", None)) !=
                    self._safe_int(item.get("tmdb_id"))
                    or self._safe_int(getattr(subscribe, "season", None)) !=
                    self._safe_int(item.get("season"))
                ):
                    self._set_supplement_item_status(
                        item, "identity_changed", checked_at,
                        "订阅的 TMDB 或季度已变化",
                    )
                    continue

                total, lack, completed = self._subscription_progress(subscribe)
                item.update({
                    "current_completed": completed,
                    "current_total": total,
                    "current_lack": lack,
                    "checked_at": checked_at,
                })
                baseline = self._safe_int(item.get("baseline_completed"), 0)
                if completed > baseline:
                    item.update({
                        "status": "updated",
                        "reason": f"订阅进度已从 {baseline} 增加到 {completed}",
                    })
                else:
                    item.update({
                        "status": "needs_search",
                        "reason": f"订阅进度仍为 {completed}，等待触发补齐搜索",
                    })
                    search_items.append(item)

            self._save_supplement_snapshot(snapshot)

            searched = 0
            search_failed = 0
            for index, item in enumerate(search_items):
                if index:
                    time.sleep(SUPPLEMENT_SEARCH_INTERVAL_SECONDS)
                subscribe_id = item.get("subscribe_id")
                try:
                    SubscribeChain().search(sid=subscribe_id, manual=True)
                    searched += 1
                    self._set_supplement_item_status(
                        item,
                        "search_triggered",
                        self._format_datetime(self._now_datetime()),
                        "已触发 MoviePilot 搜索全部缺失集数",
                    )
                except Exception as error:
                    search_failed += 1
                    self._set_supplement_item_status(
                        item,
                        "search_error",
                        self._format_datetime(self._now_datetime()),
                        f"触发 MoviePilot 搜索失败：{error}",
                    )
                    logger.error(
                        f"豆瓣订阅助手：订阅 {subscribe_id} 补齐搜索失败：{error}"
                    )
                self._save_supplement_snapshot(snapshot)

            snapshot["finished_at"] = self._format_datetime(self._now_datetime())
            self._save_supplement_snapshot(snapshot)
            updated = sum(
                1 for item in items.values() if item.get("status") == "updated"
            )
            skipped = len(items) - updated - searched - search_failed
            logger.info(
                f"豆瓣订阅助手：今日订阅补齐完成，已更新 {updated} 个，"
                f"触发搜索 {searched} 个，搜索失败 {search_failed} 个"
            )
            return {
                "success": True,
                "date": today,
                "items": len(items),
                "updated": updated,
                "searched": searched,
                "search_failed": search_failed,
                "skipped": skipped,
            }
        finally:
            self._supplement_lock.release()

    def _supplement_snapshot(self) -> Dict[str, Any]:
        value = self.get_data(SUPPLEMENT_DATA_KEY)
        return value if isinstance(value, dict) else {}

    def _save_supplement_snapshot(self, snapshot: Dict[str, Any]) -> None:
        with self._data_lock:
            self.save_data(SUPPLEMENT_DATA_KEY, snapshot)

    @staticmethod
    def _set_supplement_item_status(
        item: Dict[str, Any],
        status: str,
        checked_at: str,
        reason: str,
    ) -> None:
        item.update({
            "status": status,
            "checked_at": checked_at,
            "reason": reason,
        })

    @staticmethod
    def _is_active_tv_subscription(subscribe: Any) -> bool:
        return bool(
            subscribe
            and getattr(subscribe, "state", None) in ACTIVE_SUBSCRIBE_STATES
            and getattr(subscribe, "type", None) == MediaType.TV.value
            and getattr(subscribe, "tmdbid", None) is not None
            and getattr(subscribe, "season", None) is not None
        )

    @classmethod
    def _subscription_progress(cls, subscribe: Any) -> Tuple[int, int, int]:
        total = max(cls._safe_int(getattr(subscribe, "total_episode", None), 0), 0)
        lack_value = getattr(subscribe, "lack_episode", None)
        lack = total if lack_value is None else max(cls._safe_int(lack_value, total), 0)
        completed = max(total - lack, 0)
        return total, lack, min(completed, total)

    @staticmethod
    def _episodes_airing_on(episodes: List[Any], date_value: str) -> List[int]:
        numbers = set()
        for episode in episodes:
            if isinstance(episode, dict):
                air_date = episode.get("air_date")
                episode_number = episode.get("episode_number")
            else:
                air_date = getattr(episode, "air_date", None)
                episode_number = getattr(episode, "episode_number", None)
            if str(air_date or "") != date_value:
                continue
            try:
                number = int(episode_number)
            except (TypeError, ValueError):
                continue
            if number > 0:
                numbers.add(number)
        return sorted(numbers)

    @staticmethod
    def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _configured_urls(self) -> List[str]:
        values = self._rss_urls if isinstance(self._rss_urls, list) else str(self._rss_urls or "").splitlines()
        result = []
        seen = set()
        for value in values:
            url = str(value or "").strip()
            parsed = urlparse(url)
            if not url or parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            if url in seen:
                continue
            seen.add(url)
            result.append(url)
        return result

    def _fetch_feed(self, url: str) -> List[FeedItem]:
        response = (
            RequestUtils(proxies=settings.PROXY).get_res(url)
            if self._proxy else RequestUtils().get_res(url)
        )
        if not response:
            raise RuntimeError("RSS 请求无响应")
        if response.status_code != 200:
            raise RuntimeError(f"RSS HTTP 状态码 {response.status_code}")
        return parse_feed(response.text, source_url=url)

    def _fetch_maoyan_list(
        self,
        list_type: str,
        cookies: Optional[Dict[str, str]] = None,
    ) -> List[FeedItem]:
        config = MAOYAN_LIST_TYPES.get(list_type)
        if not config:
            return []
        url = (
            f"{MAOYAN_HEAT_URL}?seriesType={config['series_type']}"
            "&platformType=&showDate=2"
        )
        request = (
            RequestUtils(proxies=settings.PROXY)
            if self._proxy
            else RequestUtils()
        )
        response = request.get_res(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/121.0.0.0 Safari/537.36"
                ),
                "Referer": "https://piaofang.maoyan.com/",
            },
            cookies=cookies or None,
        )
        if not response:
            raise RuntimeError("猫眼请求无响应")
        if response.status_code != 200:
            raise RuntimeError(f"猫眼 HTTP 状态码 {response.status_code}")
        try:
            payload = response.json()
        except Exception as error:
            raise RuntimeError(f"猫眼返回内容不是有效 JSON：{error}") from error
        if payload.get("status") is False:
            raise RuntimeError("猫眼接口返回失败状态")
        return self._parse_maoyan_items(
            payload=payload,
            list_type=list_type,
            source_url=url,
            limit=self._maoyan_num,
        )

    @classmethod
    def _parse_maoyan_items(
        cls,
        payload: Dict[str, Any],
        list_type: str,
        source_url: str,
        limit: int,
        now: Optional[datetime.datetime] = None,
    ) -> List[FeedItem]:
        rows = ((payload or {}).get("dataList") or {}).get("list") or []
        result: List[FeedItem] = []
        seen = set()
        for row in rows:
            info = (row or {}).get("seriesInfo") or {}
            title = str(info.get("name") or "").strip()
            normalized = re.sub(r"\s+", "", title).casefold()
            if not title or normalized in seen:
                continue
            seen.add(normalized)
            release_info = str(info.get("releaseInfo") or "").strip()
            platform = str(info.get("platformDesc") or "").strip()
            series_id = (
                info.get("movieId")
                or info.get("seriesId")
                or info.get("id")
                or (row or {}).get("movieId")
                or (row or {}).get("seriesId")
            )
            guid = (
                f"maoyan:{list_type}:{series_id}"
                if series_id
                else f"maoyan:{list_type}:{normalized}"
            )
            link = (
                f"https://piaofang.maoyan.com/dashboard/web-heat?movieId={series_id}"
                if series_id
                else ""
            )
            result.append(FeedItem(
                title=title,
                link=link,
                guid=guid,
                description=" / ".join(
                    value for value in (release_info, platform) if value
                ),
                source_url=source_url,
                year=cls._maoyan_release_year(release_info, now=now),
                poster=str(
                    info.get("imgUrl")
                    or info.get("img")
                    or info.get("image")
                    or ""
                ),
            ))
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _maoyan_release_year(
        release_info: str,
        now: Optional[datetime.datetime] = None,
    ) -> Optional[str]:
        text = str(release_info or "")
        explicit = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)
        if explicit:
            return explicit.group(1)
        days = re.search(r"(\d+)\s*天", text)
        if not days:
            return None
        current = now or datetime.datetime.now()
        return str((current - datetime.timedelta(days=int(days.group(1)))).year)

    @staticmethod
    def _maoyan_cookies() -> Dict[str, str]:
        try:
            from app.helper.browser import PlaywrightHelper

            def page_handler(page) -> Dict[str, str]:
                return {
                    str(cookie.get("name")): str(cookie.get("value"))
                    for cookie in page.context.cookies()
                    if cookie.get("name")
                }

            return PlaywrightHelper().action(
                url="https://piaofang.maoyan.com",
                callback=page_handler,
                headless=True,
            ) or {}
        except Exception as error:
            logger.warning(f"豆瓣订阅助手：获取猫眼 Cookie 失败，将尝试直接请求：{error}")
            return {}

    def sync(self) -> Dict[str, Any]:
        """Fetch enabled sources and process unseen entries serially."""
        if not self._sync_lock.acquire(blocking=False):
            return {"success": False, "message": "内容源处理正在运行"}
        started_at = self._now()
        summary = {
            "success": True,
            "started_at": started_at,
            "finished_at": "",
            "feeds": 0,
            "maoyan_lists": 0,
            "items": 0,
            "subscribed": 0,
            "existing": 0,
            "skipped": 0,
            "failed": 0,
            "confirmations": 0,
            "resumed": 0,
            "completed": 0,
            "manual_review": 0,
            "verification_failed": 0,
            "pending_total_checks": 0,
            "totals_resolved": 0,
            "total_check_failed": 0,
            "douban_rate_limited": False,
        }
        try:
            if not hasattr(Subscribe, "manual_total_episode"):
                summary.update({
                    "success": False,
                    "message": "当前 MoviePilot 不支持手动总集数锁定，请升级到 v2.15.0 或更高版本",
                })
                return summary
            pending_total_summary = self._process_pending_totals()
            douban_rate_limited = bool(
                pending_total_summary.pop("douban_rate_limited", False)
            )
            summary.update(pending_total_summary)
            if not douban_rate_limited:
                confirmation_summary = self._process_due_confirmations()
                douban_rate_limited = bool(
                    confirmation_summary.pop("douban_rate_limited", False)
                )
                summary.update(confirmation_summary)

            urls = self._configured_urls()
            maoyan_types = self._maoyan_types if self._maoyan_enabled else []
            if not urls and not maoyan_types:
                if douban_rate_limited:
                    summary.update({
                        "success": False,
                        "douban_rate_limited": True,
                        "message": "豆瓣请求受限，受管订阅复核已提前停止",
                    })
                    return summary
                if summary["confirmations"] or summary["pending_total_checks"]:
                    summary["message"] = "未配置有效内容来源，仅完成受管订阅复核"
                    return summary
                summary.update({"success": False, "message": "未配置有效 RSS 或猫眼榜单"})
                return summary

            history = self.get_data("history") or []
            processed_items = self._processed_index(history)
            completed_keys = set(processed_items)
            for url in urls if not douban_rate_limited else []:
                try:
                    items = self._fetch_feed(url)
                    summary["feeds"] += 1
                except Exception as error:
                    logger.error(f"豆瓣订阅助手：获取 RSS 失败 {url}：{error}")
                    summary["failed"] += 1
                    self._record_history(history, {
                        "key": f"feed:{url}",
                        "title": url,
                        "source_url": url,
                        "status": "feed_error",
                        "reason": str(error),
                        "time": self._now(),
                    })
                    continue
                douban_rate_limited = self._process_source_items(
                    items=items[:self._max_items],
                    history=history,
                    processed_items=processed_items,
                    completed_keys=completed_keys,
                    summary=summary,
                )
                if douban_rate_limited:
                    break

            if maoyan_types and not douban_rate_limited:
                cookies: Optional[Dict[str, str]] = None
                for list_type in maoyan_types:
                    config = MAOYAN_LIST_TYPES.get(list_type) or {}
                    try:
                        try:
                            items = self._fetch_maoyan_list(list_type)
                        except Exception:
                            if cookies is None:
                                cookies = self._maoyan_cookies()
                            if not cookies:
                                raise
                            items = self._fetch_maoyan_list(
                                list_type,
                                cookies=cookies,
                            )
                        summary["maoyan_lists"] += 1
                        douban_rate_limited = self._process_source_items(
                            items=items,
                            history=history,
                            processed_items=processed_items,
                            completed_keys=completed_keys,
                            summary=summary,
                        )
                        if douban_rate_limited:
                            break
                    except Exception as error:
                        label = config.get("label") or list_type
                        logger.error(f"豆瓣订阅助手：获取猫眼{label}失败：{error}")
                        summary["failed"] += 1
                        self._record_history(history, {
                            "key": f"maoyan:{list_type}:fetch",
                            "title": f"猫眼{label}",
                            "source_url": MAOYAN_HEAT_URL,
                            "status": "maoyan_error",
                            "reason": str(error),
                            "time": self._now(),
                        })
            if douban_rate_limited:
                summary.update({
                    "success": False,
                    "douban_rate_limited": True,
                    "message": (
                        "豆瓣请求受限，本批次已提前停止；"
                        "未处理条目将在下次执行时重试"
                    ),
                })
            self.save_data("history", history)
            return summary
        except Exception as error:
            logger.error(f"豆瓣订阅助手：RSS 处理失败：{error}", exc_info=True)
            summary.update({"success": False, "message": str(error)})
            return summary
        finally:
            summary["finished_at"] = self._now()
            self.save_data("last_run", summary)
            self._sync_lock.release()

    def _process_source_items(
        self,
        items: List[FeedItem],
        history: List[dict],
        processed_items: Dict[str, Dict[str, Any]],
        completed_keys: set,
        summary: Dict[str, Any],
    ) -> bool:
        """逐条处理内容源，并在豆瓣限流后停止当前批次。"""
        for item in items:
            summary["items"] += 1
            if item.key in completed_keys:
                summary["skipped"] += 1
                continue
            cached_skip = self._cached_category_skip(item)
            if cached_skip:
                self._record_history(history, cached_skip)
                summary["skipped"] += 1
                continue
            record = self._process_item(item)
            self._record_history(history, record)
            status = record.get("status")
            if status == "subscribed":
                summary["subscribed"] += 1
                completed_keys.add(item.key)
                self._mark_processed(processed_items, item.key, record)
            elif status in {"existing", "history_existing"}:
                summary["existing"] += 1
                completed_keys.add(item.key)
                self._mark_processed(processed_items, item.key, record)
            elif status in SKIPPED_STATUSES:
                summary["skipped"] += 1
            else:
                summary["failed"] += 1
            if status == "douban_rate_limited":
                return True
        return False

    def _process_item(self, item: FeedItem) -> Dict[str, Any]:
        base_record = {
            **item.to_dict(),
            "status": "processing",
            "reason": "",
            "time": self._now(),
        }
        try:
            douban_info = self._resolve_douban(item)
            if not douban_info:
                return self._failed_record(base_record, "douban_not_found", "未匹配到豆瓣电视剧条目")
            douban_id = str(douban_info.get("id") or item.douban_id or "")
            total_episode = extract_total_episode(douban_info)
            airing_started = has_started_airing(douban_info)
            category = classify_media_region(douban_info)
            base_record.update({
                "douban_id": douban_id,
                "douban_title": douban_info.get("title") or item.title,
                "douban_year": douban_info.get("year") or item.year or "",
                "douban_total": total_episode,
                "imdb_id": "",
                "airing_started": airing_started,
                "total_pending": not bool(total_episode),
                "category": category,
                "countries": douban_info.get("countries") or [],
            })
            if category not in self._media_categories:
                record = self._failed_record(
                    base_record,
                    "category_skipped",
                    f"{MEDIA_CATEGORY_LABELS.get(category, category)}未在订阅类型中启用",
                )
                self._remember_category_skip(item, record)
                return record
            imdb_id = self._resolve_douban_imdb_id(douban_info)
            if imdb_id:
                douban_info["imdb_id"] = imdb_id
                base_record["imdb_id"] = imdb_id
            if not total_episode and not airing_started:
                return self._failed_record(
                    base_record,
                    "douban_total_missing",
                    "豆瓣详情没有明确总集数，且没有可靠的已开播证据，未创建订阅",
                )

            decision, media_by_key, search_attempts = self._match_tmdb(
                douban_info,
                total_episode or 0,
            )
            base_record["search_attempts"] = search_attempts
            if decision.winner:
                winner = decision.winner
                base_record.update({
                    "tmdb_id": winner.candidate.tmdb_id,
                    "season": winner.candidate.season,
                    "score": winner.score,
                    "identity_score": winner.identity_score,
                    "structure_score": winner.structure_score,
                    "evidence": list(winner.evidence),
                })
            base_record["alternatives"] = [item.to_dict() for item in decision.alternatives]
            if not decision.accepted or not decision.winner:
                return self._failed_record(base_record, decision.status, decision.reason)

            winner = decision.winner.candidate
            mediainfo = media_by_key.get((winner.tmdb_id, winner.season))
            if not mediainfo:
                return self._failed_record(base_record, "tmdb_detail_missing", "TMDB 详情加载失败")
            subscription = self._create_subscription(
                mediainfo=mediainfo,
                douban_id=douban_id,
                season=winner.season,
                total_episode=total_episode or UNKNOWN_TOTAL_EPISODE,
                category=category,
                source_key=item.key,
                total_pending=not bool(total_episode),
            )
            base_record.update(subscription)
            return base_record
        except LimitException as error:
            logger.warning(
                f"豆瓣订阅助手：处理《{item.title}》时豆瓣请求受限：{error}"
            )
            return self._failed_record(
                base_record,
                "douban_rate_limited",
                "豆瓣请求受限，本批次已暂停，未处理条目将在下次执行时重试",
            )
        except Exception as error:
            logger.error(f"豆瓣订阅助手：处理《{item.title}》失败：{error}", exc_info=True)
            return self._failed_record(base_record, "error", str(error))

    def _resolve_douban(self, item: FeedItem) -> Optional[Dict[str, Any]]:
        douban_id = item.douban_id
        if not douban_id:
            for title, year, season in self._douban_search_attempts(item):
                matched = self._call_douban(
                    self.chain.match_doubaninfo,
                    name=title,
                    mtype=MediaType.TV,
                    year=year,
                    season=season,
                )
                if matched and matched.get("id"):
                    douban_id = str(matched["id"])
                    break
        if not douban_id:
            return None
        detail = self._call_douban(
            self.chain.douban_info,
            doubanid=str(douban_id),
            mtype=MediaType.TV,
        )
        if detail:
            detail["id"] = str(detail.get("id") or douban_id)
        return detail

    def _resolve_douban_imdb_id(self, douban_info: Dict[str, Any]) -> Optional[str]:
        """优先读取豆瓣详情字段，缺失时再查询完整信息页。"""
        for field_name in ("imdb_id", "imdbid", "imdb", "extra"):
            imdb_id = self._extract_imdb_id(douban_info.get(field_name))
            if imdb_id:
                return imdb_id

        douban_id = str(douban_info.get("id") or "").strip()
        if douban_id and douban_id in self._douban_imdb_cache:
            return self._douban_imdb_cache[douban_id]

        info_url = str(douban_info.get("info_url") or "").strip()
        parsed = urlparse(info_url)
        hostname = str(parsed.hostname or "").casefold()
        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or hostname != "douban.com" and not hostname.endswith(".douban.com")
        ):
            return None

        try:
            response = self._run_douban_request(
                lambda: RequestUtils(
                    ua=getattr(settings, "NORMAL_USER_AGENT", None),
                    proxies=settings.PROXY if self._proxy else None,
                ).get_res(info_url)
            )
            if not response or getattr(response, "status_code", 200) != 200:
                return None
            imdb_id = self._extract_imdb_id(getattr(response, "text", ""))
            if imdb_id and douban_id:
                self._douban_imdb_cache[douban_id] = imdb_id
            return imdb_id
        except Exception as error:
            logger.warning(
                f"豆瓣订阅助手：读取豆瓣 {douban_id or '未知'} 的 IMDb ID 失败：{error}"
            )
            return None

    @staticmethod
    def _extract_imdb_id(value: Any) -> Optional[str]:
        match = IMDB_ID_PATTERN.search(str(value or ""))
        return match.group(0).lower() if match else None

    @staticmethod
    def _douban_search_attempts(
        item: FeedItem,
    ) -> List[Tuple[str, Optional[str], Optional[int]]]:
        """生成豆瓣标题、年份及明确季数的去重降级路径。"""
        source_title = str(item.title or "").strip()
        dequoted_title = re.sub(r"[\"'“”‘’「」『』]", "", source_title)
        dequoted_title = re.sub(r"\s+", " ", dequoted_title).strip()
        titles = list(dict.fromkeys(
            title for title in (source_title, dequoted_title) if title
        ))
        queries = []
        for title in titles:
            season_queries = [
                (hypothesis.title, hypothesis.season)
                for hypothesis in build_title_hypotheses(title)
                if hypothesis.mode == "base_and_season"
                and hypothesis.strength == "strong"
            ]
            queries.extend(season_queries or [(title, None)])
        queries = list(dict.fromkeys(queries))
        years = [item.year] if item.year else [None]
        if item.year:
            years.append(None)
        return [
            (title, year, season)
            for year in years
            for title, season in queries
        ]

    def _call_douban(self, method, **kwargs):
        """统一控制插件豆瓣查询间隔，并透传限流异常。"""
        return self._run_douban_request(
            lambda: method(**kwargs, raise_exception=True)
        )

    def _run_douban_request(self, callable_):
        """串行执行豆瓣请求，并保证相邻请求至少间隔三秒。"""
        with self._douban_query_lock:
            elapsed = time.monotonic() - self._last_douban_query_at
            wait_seconds = DOUBAN_QUERY_INTERVAL_SECONDS - elapsed
            if self._last_douban_query_at and wait_seconds > 0:
                time.sleep(wait_seconds)
            try:
                return callable_()
            finally:
                self._last_douban_query_at = time.monotonic()

    def _match_tmdb(
        self,
        douban_info: Dict[str, Any],
        total_episode: int,
    ) -> Tuple[
        MatchDecision,
        Dict[Tuple[int, int], Any],
        List[Dict[str, Any]],
    ]:
        title = str(douban_info.get("title") or "").strip()
        year = str(douban_info.get("year") or "").strip() or None
        source = {
            "title": title,
            "original_title": douban_info.get("original_title") or "",
            "aliases": douban_info.get("aka") or [],
            "year": year,
            "total_episode": total_episode,
            "actors": person_names(douban_info.get("actors") or []),
            "directors": person_names(douban_info.get("directors") or []),
        }
        scored: List[ScoredCandidate] = []
        media_by_key: Dict[Tuple[int, int], Any] = {}
        hydrated_by_id: Dict[int, Any] = {}
        seasons_by_id: Dict[int, List[Any]] = {}
        searched_keys = set()
        search_attempts: List[Dict[str, Any]] = []
        search_succeeded = False
        any_results = False
        any_hydrated = False
        any_season_detail = False
        arc_season_requested = False
        rejected_parent_seasons = set()
        search_errors: List[str] = []
        detail_errors: List[str] = []
        tmdb_chain = TmdbChain()
        hypotheses = build_search_hypotheses(
            title=title,
            original_title=str(douban_info.get("original_title") or ""),
            aliases=tuple(str(value) for value in (douban_info.get("aka") or []) if value),
        )
        parent_season_hypotheses = [
            hypothesis for hypothesis in hypotheses
            if hypothesis.mode == "base_and_season"
            and (hypothesis.season or 0) >= 2
        ]
        imdb_id = self._extract_imdb_id(douban_info.get("imdb_id"))
        if imdb_id:
            imdb_match = self._match_tmdb_by_imdb(
                imdb_id=imdb_id,
                source=source,
                hypotheses=hypotheses,
                tmdb_chain=tmdb_chain,
                search_attempts=search_attempts,
            )
            if imdb_match is not None:
                return imdb_match
            rejected_parent_seasons.update(
                search_attempts[-1].get("rejected_parent_seasons") or []
            )

        requested_queries = set()
        for hypothesis in hypotheses:
            for query_title in self._tmdb_query_titles(hypothesis):
                query_year = (
                    year
                    if hypothesis.mode not in {"base_and_season", "arc_title"}
                    else None
                )
                query_key = (query_title.casefold(), query_year)
                if query_key in requested_queries:
                    continue
                requested_queries.add(query_key)
                meta = MetaInfo(query_title)
                # MoviePilot's MetaInfo may strip season suffixes before TMDB search.
                # Keep the actual query intact; parent-season validation happens below.
                meta.name = query_title
                meta.type = MediaType.TV
                if query_year:
                    meta.year = query_year
                results, search_error, request_count = self._tmdb_call_with_retry(
                    lambda: self.chain.search_medias(meta=meta, source="themoviedb"),
                )
                results = results or []
                raw_fallback = False
                raw_error = ""
                if (
                    not search_error
                    and not results
                    and hypothesis.mode == "base_and_season"
                    and query_title == hypothesis.title
                ):
                    raw_fallback = True
                    raw_results, raw_error, raw_request_count = self._tmdb_call_with_retry(
                        lambda: self._tmdb_raw_tv_search(query_title, query_year),
                    )
                    request_count += raw_request_count
                    results = raw_results or []
                attempt = {
                    "query": query_title,
                    "season": hypothesis.season,
                    "mode": hypothesis.mode,
                    "raw_fallback": raw_fallback,
                    "result_count": len(results),
                    "hydrated_count": 0,
                    "parent_season_rejections": 0,
                    "request_count": request_count,
                    "error": search_error or raw_error,
                }
                search_attempts.append(attempt)
                if search_error:
                    search_errors.append(search_error)
                    continue
                search_succeeded = True
                if results:
                    any_results = True
                hydrated_in_attempt = set()
                for search_result in results:
                    tmdb_id = (
                        self._result_value(search_result, "tmdb_id")
                        or self._result_value(search_result, "id")
                    )
                    if not tmdb_id:
                        continue
                    tmdb_id = int(tmdb_id)
                    if len(hydrated_by_id) >= self._candidate_limit and tmdb_id not in hydrated_by_id:
                        continue
                    mediainfo = hydrated_by_id.get(tmdb_id)
                    if mediainfo is None:
                        detail_meta = MetaInfo(hypothesis.title)
                        detail_meta.type = MediaType.TV
                        mediainfo, detail_error, _ = self._tmdb_call_with_retry(
                            lambda: self.chain.recognize_media(
                                meta=detail_meta,
                                mtype=MediaType.TV,
                                tmdbid=tmdb_id,
                                cache=False,
                            ),
                        )
                        if detail_error:
                            detail_errors.append(detail_error)
                        if not mediainfo:
                            continue
                        hydrated_by_id[tmdb_id] = mediainfo
                    any_hydrated = True
                    hydrated_in_attempt.add(tmdb_id)
                    if hypothesis.mode == "arc_title":
                        arc_season_requested = True
                        if tmdb_id not in seasons_by_id:
                            season_rows, season_error, _ = self._tmdb_call_with_retry(
                                lambda: tmdb_chain.tmdb_seasons(tmdb_id),
                            )
                            seasons_by_id[tmdb_id] = list(season_rows or [])
                            if season_error:
                                detail_errors.append(season_error)
                        season_rows = seasons_by_id[tmdb_id]
                        if season_rows:
                            any_season_detail = True
                        for season_row in season_rows:
                            season = self._season_value(season_row, "season_number")
                            season_name = str(
                                self._season_value(season_row, "name") or ""
                            ).strip()
                            if not season or season <= 0:
                                continue
                            if not arc_name_match_score(hypothesis.arc_title, season_name):
                                continue
                            search_key = (
                                tmdb_id,
                                season,
                                hypothesis.mode,
                                hypothesis.arc_title,
                            )
                            if search_key in searched_keys:
                                continue
                            searched_keys.add(search_key)
                            air_date = str(
                                self._season_value(season_row, "air_date") or ""
                            )
                            episode_count = self._season_value(
                                season_row,
                                "episode_count",
                            )
                            try:
                                episode_count = int(episode_count)
                            except (TypeError, ValueError):
                                episode_count = None
                            candidate = self._build_tmdb_candidate(
                                mediainfo,
                                hypothesis,
                                season,
                                season_name=season_name,
                                season_episode_count=episode_count,
                                season_year=air_date[:4] if air_date else None,
                            )
                            scored.append(score_candidate(source, candidate))
                            media_by_key[(candidate.tmdb_id, candidate.season)] = mediainfo
                        continue

                    candidate_hypotheses = (
                        parent_season_hypotheses
                        if parent_season_hypotheses
                        and hypothesis.mode != "base_and_season"
                        else [hypothesis]
                    )
                    for candidate_hypothesis in candidate_hypotheses:
                        season = (
                            candidate_hypothesis.season
                            if candidate_hypothesis.season is not None
                            else 1
                        )
                        if (
                            candidate_hypothesis.mode == "base_and_season"
                            and season >= 2
                            and not self._media_has_season(mediainfo, season)
                        ):
                            rejected_parent_seasons.add(season)
                            attempt["parent_season_rejections"] += 1
                            continue
                        search_key = (
                            tmdb_id,
                            season,
                            candidate_hypothesis.mode,
                            "",
                        )
                        if search_key in searched_keys:
                            continue
                        searched_keys.add(search_key)
                        candidate = self._build_tmdb_candidate(
                            mediainfo,
                            candidate_hypothesis,
                            season,
                        )
                        scored.append(score_candidate(source, candidate))
                        media_by_key[(candidate.tmdb_id, candidate.season)] = mediainfo
                attempt["hydrated_count"] = len(hydrated_in_attempt)

        if not scored:
            if search_errors and not search_succeeded:
                decision = MatchDecision(
                    False,
                    "tmdb_search_error",
                    f"TMDB 搜索接口连续失败：{search_errors[-1]}",
                )
            elif rejected_parent_seasons:
                season_text = ", ".join(
                    f"S{season:02d}" for season in sorted(rejected_parent_seasons)
                )
                decision = MatchDecision(
                    False,
                    "no_candidate",
                    f"候选父剧不存在目标季度 {season_text}，已拒绝按独立续季条目的 S01 自动订阅",
                )
            elif not any_results:
                decision = MatchDecision(
                    False,
                    "tmdb_search_empty",
                    "TMDB 搜索正常返回，但没有候选结果",
                )
            elif (
                not any_hydrated
                or detail_errors and not any_season_detail
                or arc_season_requested and not any_season_detail
            ):
                decision = MatchDecision(
                    False,
                    "tmdb_detail_missing",
                    "找到 TMDB 搜索结果，但详情或分季数据加载失败",
                )
            else:
                decision = MatchDecision(
                    False,
                    "no_candidate",
                    "找到 TMDB 作品，但没有满足标题或分季名规则的候选",
                )
            return (
                self._with_imdb_fallback_context(decision, imdb_id, search_attempts),
                media_by_key,
                search_attempts,
            )
        decision = choose_match(scored)
        return (
            self._with_imdb_fallback_context(decision, imdb_id, search_attempts),
            media_by_key,
            search_attempts,
        )

    @classmethod
    def _tmdb_query_titles(cls, hypothesis: Any) -> Tuple[str, ...]:
        """Return real TMDB queries while keeping sequel-season intent separate."""
        titles = [str(hypothesis.title or "").strip()]
        season = hypothesis.season
        if hypothesis.mode == "base_and_season" and season and season >= 2:
            titles.extend((
                f"{hypothesis.title} 第{season}季",
                f"{hypothesis.title} 第{cls._chinese_number(season)}季",
            ))
        return tuple(dict.fromkeys(title for title in titles if title))

    @staticmethod
    def _chinese_number(value: int) -> str:
        digits = "零一二三四五六七八九"
        if value < 10:
            return digits[value]
        tens, units = divmod(value, 10)
        prefix = "十" if tens == 1 else f"{digits[tens]}十"
        return prefix if units == 0 else f"{prefix}{digits[units]}"

    @staticmethod
    def _media_has_season(mediainfo: Any, season: int) -> bool:
        seasons = getattr(mediainfo, "seasons", {}) or {}
        return isinstance(seasons, dict) and (
            season in seasons or str(season) in seasons
        )

    @staticmethod
    def _with_imdb_fallback_context(
        decision: MatchDecision,
        imdb_id: Optional[str],
        search_attempts: List[Dict[str, Any]],
    ) -> MatchDecision:
        if decision.accepted or not imdb_id:
            return decision
        attempt = next(
            (item for item in search_attempts if item.get("mode") == "imdb_exact"),
            None,
        )
        if not attempt:
            return decision
        if attempt.get("error"):
            prefix = f"IMDb {imdb_id} 反查 TMDB 失败"
        elif not attempt.get("result_count"):
            prefix = f"TMDB 未收录 IMDb {imdb_id}"
        else:
            return decision
        return MatchDecision(
            decision.accepted,
            decision.status,
            f"{prefix}；{decision.reason}",
            decision.winner,
            decision.alternatives,
        )

    def _match_tmdb_by_imdb(
        self,
        imdb_id: str,
        source: Dict[str, Any],
        hypotheses: List[Any],
        tmdb_chain: TmdbChain,
        search_attempts: List[Dict[str, Any]],
    ) -> Optional[Tuple[
        MatchDecision,
        Dict[Tuple[int, int], Any],
        List[Dict[str, Any]],
    ]]:
        """IMDb 精确反查；无结果或接口失败时返回 None 走标题兜底。"""
        payload, error, request_count = self._tmdb_call_with_retry(
            lambda: self._tmdb_find_by_imdb_id(imdb_id)
        )
        tv_results = list((payload or {}).get("tv_results") or [])
        attempt = {
            "query": imdb_id,
            "season": None,
            "mode": "imdb_exact",
            "result_count": len(tv_results),
            "hydrated_count": 0,
            "parent_season_rejections": 0,
            "rejected_parent_seasons": [],
            "request_count": request_count,
            "error": error,
        }
        search_attempts.append(attempt)
        if error or not tv_results:
            return None

        structural_hypotheses = [
            hypothesis for hypothesis in hypotheses
            if hypothesis.mode in {"base_and_season", "arc_title"}
        ]
        selected_hypotheses = structural_hypotheses or hypotheses[:1]
        scored: List[ScoredCandidate] = []
        media_by_key: Dict[Tuple[int, int], Any] = {}
        detail_errors: List[str] = []
        hydrated_ids = set()
        rejected_parent_seasons = set()

        for raw_result in tv_results[:self._candidate_limit]:
            tmdb_id = self._result_value(raw_result, "id")
            try:
                tmdb_id = int(tmdb_id)
            except (TypeError, ValueError):
                continue
            detail_meta = MetaInfo(str(source.get("title") or ""))
            detail_meta.type = MediaType.TV
            mediainfo, detail_error, _ = self._tmdb_call_with_retry(
                lambda tmdb_id=tmdb_id: self.chain.recognize_media(
                    meta=detail_meta,
                    mtype=MediaType.TV,
                    tmdbid=tmdb_id,
                    cache=False,
                )
            )
            if detail_error:
                detail_errors.append(detail_error)
            if not mediainfo:
                continue
            hydrated_ids.add(tmdb_id)

            for hypothesis in selected_hypotheses:
                if hypothesis.mode == "arc_title":
                    season_rows, season_error, _ = self._tmdb_call_with_retry(
                        lambda tmdb_id=tmdb_id: tmdb_chain.tmdb_seasons(tmdb_id)
                    )
                    if season_error:
                        detail_errors.append(season_error)
                    for season_row in season_rows or []:
                        season = self._season_value(season_row, "season_number")
                        season_name = str(
                            self._season_value(season_row, "name") or ""
                        ).strip()
                        if not season or season <= 0:
                            continue
                        if not arc_name_match_score(hypothesis.arc_title, season_name):
                            continue
                        air_date = str(
                            self._season_value(season_row, "air_date") or ""
                        )
                        episode_count = self._safe_int(
                            self._season_value(season_row, "episode_count"),
                            0,
                        ) or None
                        candidate = self._build_tmdb_candidate(
                            mediainfo,
                            hypothesis,
                            season,
                            season_name=season_name,
                            season_episode_count=episode_count,
                            season_year=air_date[:4] if air_date else None,
                            imdb_exact=True,
                        )
                        scored.append(score_candidate(source, candidate))
                        media_by_key[(candidate.tmdb_id, candidate.season)] = mediainfo
                    continue

                season = hypothesis.season if hypothesis.season is not None else 1
                if (
                    hypothesis.mode == "base_and_season"
                    and season >= 2
                    and not self._media_has_season(mediainfo, season)
                ):
                    rejected_parent_seasons.add(season)
                    attempt["parent_season_rejections"] += 1
                    continue
                candidate = self._build_tmdb_candidate(
                    mediainfo,
                    hypothesis,
                    season,
                    imdb_exact=True,
                )
                scored.append(score_candidate(source, candidate))
                media_by_key[(candidate.tmdb_id, candidate.season)] = mediainfo

        attempt["hydrated_count"] = len(hydrated_ids)
        attempt["rejected_parent_seasons"] = sorted(rejected_parent_seasons)
        if scored:
            return choose_match(scored), media_by_key, search_attempts
        if rejected_parent_seasons and not detail_errors:
            return None
        if detail_errors:
            decision = MatchDecision(
                False,
                "tmdb_detail_missing",
                f"IMDb 已关联 TMDB，但详情加载失败：{detail_errors[-1]}",
            )
        else:
            decision = MatchDecision(
                False,
                "no_candidate",
                "IMDb 已关联 TMDB 电视剧，但没有满足季度结构的候选",
            )
        return decision, media_by_key, search_attempts

    @staticmethod
    def _result_value(result: Any, field: str) -> Any:
        return result.get(field) if isinstance(result, dict) else getattr(result, field, None)

    @staticmethod
    def _tmdb_find_by_imdb_id(imdb_id: str) -> Dict[str, Any]:
        """使用 MoviePilot 内置 TMDB 客户端执行外部 ID 反查。"""
        from app.modules.themoviedb.tmdbv3api import Find

        finder = Find(language=getattr(settings, "TMDB_LOCALE", None))
        try:
            return finder.find_by_imdb_id(imdb_id) or {}
        finally:
            finder.close()

    @staticmethod
    def _tmdb_raw_tv_search(title: str, year: Optional[str]) -> List[Dict[str, Any]]:
        """绕过 MoviePilot 对 TMDB 搜索结果的严格标题子串过滤。"""
        from app.modules.themoviedb.tmdbv3api import Search

        searcher = Search(language=getattr(settings, "TMDB_LOCALE", None))
        try:
            results = searcher.tv_shows(
                term=title,
                release_year=year,
            ) or []
            return [
                {"tmdb_id": result.get("id")}
                for result in results
                if result.get("id")
            ]
        finally:
            searcher.close()

    @staticmethod
    def _tmdb_call_with_retry(callable_):
        last_error = ""
        for index in range(len(TMDB_RETRY_DELAYS) + 1):
            try:
                return callable_(), "", index + 1
            except Exception as error:
                last_error = str(error)
                if index < len(TMDB_RETRY_DELAYS):
                    time.sleep(TMDB_RETRY_DELAYS[index])
        return None, last_error, len(TMDB_RETRY_DELAYS) + 1

    @staticmethod
    def _season_value(season: Any, field: str) -> Any:
        if isinstance(season, dict):
            return season.get(field)
        return getattr(season, field, None)

    @staticmethod
    def _title_names(values: List[Any]) -> Tuple[str, ...]:
        result = []
        for value in values or []:
            if isinstance(value, dict):
                value = value.get("title") or value.get("name") or value.get("value")
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
        return tuple(result)

    def _build_tmdb_candidate(
        self,
        mediainfo,
        hypothesis,
        season: int,
        season_name: str = "",
        season_episode_count: Optional[int] = None,
        season_year: Optional[str] = None,
        imdb_exact: bool = False,
    ) -> TmdbCandidate:
        seasons = getattr(mediainfo, "seasons", {}) or {}
        episodes = seasons.get(season)
        if episodes is None:
            episodes = seasons.get(str(season))
        season_years = getattr(mediainfo, "season_years", {}) or {}
        detected_season_year = (
            season_years.get(season)
            or season_years.get(str(season))
        )
        if season_episode_count is None and episodes is not None:
            season_episode_count = len(episodes)
        return TmdbCandidate(
            tmdb_id=int(mediainfo.tmdb_id),
            title=str(getattr(mediainfo, "title", "") or ""),
            original_title=str(getattr(mediainfo, "original_title", "") or ""),
            names=self._title_names(getattr(mediainfo, "names", []) or []),
            year=str(getattr(mediainfo, "year", "") or "") or None,
            season=season,
            season_year=str(season_year or detected_season_year or "") or None,
            season_episode_count=season_episode_count,
            actors=person_names(getattr(mediainfo, "actors", []) or []),
            directors=person_names(getattr(mediainfo, "directors", []) or []),
            mode=hypothesis.mode,
            strength=hypothesis.strength,
            hypothesis_title=hypothesis.title,
            season_name=season_name,
            arc_title=hypothesis.arc_title,
            imdb_exact=imdb_exact,
        )

    def _create_subscription(
        self,
        mediainfo,
        douban_id: str,
        season: int,
        total_episode: int,
        category: str,
        source_key: str,
        total_pending: bool = False,
    ) -> Dict[str, Any]:
        subscribe_oper = SubscribeOper()
        existing = subscribe_oper.get_by(
            type=MediaType.TV.value,
            season=season,
            tmdbid=mediainfo.tmdb_id,
        )
        if existing:
            managed = str(getattr(existing, "username", "") or "") == PLUGIN_USERNAME
            if managed:
                managed_record = self._managed_record(existing.id)
                can_update = (
                    managed_record.get("status") != "manual_review"
                    and (
                        not total_pending
                        or not managed_record
                        or bool(managed_record.get("total_pending"))
                    )
                )
                if can_update:
                    old_total = int(existing.total_episode or 0)
                    old_lack = int(existing.lack_episode or 0)
                    subscribe_oper.update(existing.id, {
                        "total_episode": total_episode,
                        "lack_episode": max(old_lack + total_episode - old_total, 0),
                        "manual_total_episode": 1,
                    })
                    existing = subscribe_oper.get(existing.id)
                effective_pending = (
                    total_pending if can_update
                    else bool(managed_record.get("total_pending"))
                )
                effective_total = int(existing.total_episode or total_episode)
                self._register_managed_subscription(
                    subscribe_id=existing.id,
                    title=existing.name or mediainfo.title,
                    tmdb_id=mediainfo.tmdb_id,
                    douban_id=douban_id,
                    season=season,
                    expected_total=effective_total,
                    category=category,
                    status="awaiting_douban_total" if effective_pending else "active",
                    reason=(
                        f"豆瓣尚未提供总集数，暂按 {effective_total} 集订阅并周期复核"
                        if effective_pending else
                        "已接管此前由豆瓣订阅助手创建的订阅"
                    ),
                    source_key=source_key,
                    total_pending=effective_pending,
                )
            return {
                "status": "existing",
                "subscribe_id": existing.id,
                "reason": (
                    (
                        f"豆瓣尚未提供总集数，暂按 {int(existing.total_episode or total_episode)} "
                        "集订阅并周期复核"
                        if managed and effective_pending else
                        "已接管此前由豆瓣订阅助手创建的订阅"
                    )
                    if managed else
                    "MoviePilot 中已存在相同 TMDB 与季度的订阅，未接管用户原订阅"
                ),
                "locked": bool(getattr(existing, "manual_total_episode", False)),
                "managed": managed,
            }

        if subscribe_oper.exist_history(
            tmdbid=mediainfo.tmdb_id,
            season=season,
        ):
            return {
                "status": "history_existing",
                "reason": (
                    "MoviePilot 电视剧订阅历史中已存在相同 TMDB 与季度，"
                    "为避免重复订阅已跳过"
                ),
                "locked": False,
                "managed": False,
            }

        subscribe_id, message = SubscribeChain().add(
            title=mediainfo.title,
            year=mediainfo.year or "",
            mtype=MediaType.TV,
            tmdbid=mediainfo.tmdb_id,
            doubanid=douban_id,
            season=season,
            total_episode=total_episode,
            lack_episode=total_episode,
            manual_total_episode=1,
            exist_ok=True,
            username=PLUGIN_USERNAME,
            message=self._notify_subscription,
        )
        if not subscribe_id:
            return {
                "status": "subscribe_failed",
                "reason": message or "MoviePilot 创建订阅失败",
                "locked": False,
            }
        subscribe_oper.update(subscribe_id, {
            "total_episode": total_episode,
            "manual_total_episode": 1,
        })
        saved = subscribe_oper.get(subscribe_id)
        locked = bool(
            saved
            and saved.total_episode == total_episode
            and saved.manual_total_episode
        )
        if not locked:
            return {
                "status": "lock_failed",
                "subscribe_id": subscribe_id,
                "reason": "订阅已创建，但总集数锁定校验失败",
                "locked": False,
            }
        self._register_managed_subscription(
            subscribe_id=subscribe_id,
            title=saved.name or mediainfo.title,
            tmdb_id=mediainfo.tmdb_id,
            douban_id=douban_id,
            season=season,
            expected_total=total_episode,
            category=category,
            status="awaiting_douban_total" if total_pending else "active",
            reason=(
                f"豆瓣尚未提供总集数，暂按 {total_episode} 集订阅并周期复核"
                if total_pending else
                "订阅由豆瓣订阅助手管理"
            ),
            source_key=source_key,
            total_pending=total_pending,
        )
        return {
            "status": "subscribed",
            "subscribe_id": subscribe_id,
            "reason": (
                f"豆瓣尚未提供总集数，已暂按 {total_episode} 集创建并锁定订阅"
                if total_pending else
                f"已按豆瓣总集数 {total_episode} 创建并锁定订阅"
            ),
            "locked": True,
            "managed": True,
        }

    @eventmanager.register(ChainEventType.SubscribeCompletionCheck, priority=10)
    def on_subscribe_completion_check(self, event: Event) -> None:
        """Pause the first completion, but allow the post-confirmation completion."""
        if not self._enabled or not event or not event.event_data:
            return
        event_data: SubscribeCompletionCheckEventData = event.event_data
        subscribe = getattr(event_data, "subscribe", None)
        subscribe_id = getattr(subscribe, "id", None)
        if not subscribe_id:
            return
        managed = self._managed_record(subscribe_id)
        managed_status = managed.get("status") if managed else ""
        if managed_status in {"manual_review", "completed", "missing_subscription"}:
            return
        owned_by_plugin = (
            str(getattr(subscribe, "username", "") or "") == PLUGIN_USERNAME
        )
        if not owned_by_plugin:
            if managed:
                self._upsert_managed({
                    **managed,
                    "status": "manual_review",
                    "check_after": "",
                    "reason": "订阅归属已改变，插件停止接管",
                })
            return

        if managed_status == "finalizing":
            self._upsert_managed({
                **managed,
                "last_checked": self._now(),
                "reason": "豆瓣总集数没有增加，正在由 MoviePilot 正常完成订阅",
            })
            return

        event_data.cancel = True
        event_data.source = self.plugin_name
        if managed_status in {
            "awaiting_douban_total", "waiting_confirmation",
            "confirming", "verification_error",
        }:
            event_data.reason = "订阅处于完成确认流程，暂不删除卡片"
            SubscribeOper().update(subscribe_id, {"state": "S"})
            if managed_status == "awaiting_douban_total":
                self._upsert_managed({
                    **managed,
                    "pending_completed": True,
                    "reason": "100 集临时订阅已全部满足，等待豆瓣提供明确总集数",
                })
            return

        event_data.reason = "订阅已完成，暂停卡片并等待复核豆瓣总集数"
        try:
            SubscribeOper().update(subscribe_id, {
                "state": "S",
                "lack_episode": 0,
                "manual_total_episode": 1,
            })
            check_after = self._format_datetime(
                self._now_datetime() + datetime.timedelta(days=self._confirmation_days)
            )
            self._upsert_managed({
                "subscribe_id": subscribe_id,
                "title": (
                    getattr(subscribe, "name", "")
                    or (managed.get("title", "") if managed else "")
                ),
                "tmdb_id": getattr(subscribe, "tmdbid", None),
                "douban_id": str(getattr(subscribe, "doubanid", "") or ""),
                "season": getattr(subscribe, "season", 1) or 1,
                "expected_total": (
                    managed.get("expected_total")
                    if managed and managed.get("expected_total")
                    else getattr(subscribe, "total_episode", 0)
                ),
                "category": managed.get("category", "other") if managed else "other",
                "status": "waiting_confirmation",
                "completed_at": self._now(),
                "check_after": check_after,
                "reason": f"已完成并暂停，将在 {self._confirmation_days} 天后复核豆瓣总集数",
            })
            logger.info(
                f"豆瓣订阅助手：订阅 #{subscribe_id} 已完成，已暂停并保留卡片，"
                f"将在 {check_after} 后复核豆瓣总集数"
            )
        except Exception as error:
            logger.error(
                f"豆瓣订阅助手：暂停已完成订阅 #{subscribe_id} 失败：{error}",
                exc_info=True,
            )
            self._upsert_managed({
                "subscribe_id": subscribe_id,
                "title": getattr(subscribe, "name", "") or "",
                "status": "verification_error",
                "check_after": self._format_datetime(
                    self._now_datetime() + datetime.timedelta(days=1)
                ),
                "reason": f"完成时暂停失败：{error}",
            })

    def _process_pending_totals(self) -> Dict[str, int]:
        """Refresh provisional 100-episode subscriptions on every plugin cycle."""
        summary = {
            "pending_total_checks": 0,
            "totals_resolved": 0,
            "total_check_failed": 0,
            "douban_rate_limited": False,
        }
        for record in self._managed_records():
            status = record.get("status")
            if status != "awaiting_douban_total" and not (
                status == "active" and record.get("total_pending")
            ):
                continue
            summary["pending_total_checks"] += 1
            try:
                if self._resolve_pending_total(record):
                    summary["totals_resolved"] += 1
            except LimitException as error:
                summary["total_check_failed"] += 1
                summary["douban_rate_limited"] = True
                self._upsert_managed({
                    **record,
                    "status": "awaiting_douban_total",
                    "total_pending": True,
                    "last_checked": self._now(),
                    "reason": "豆瓣请求受限，本批剩余复核将在下次执行",
                })
                logger.warning(
                    f"豆瓣订阅助手：复核订阅 #{record.get('subscribe_id')} "
                    f"时豆瓣请求受限：{error}"
                )
                break
            except Exception as error:
                summary["total_check_failed"] += 1
                self._upsert_managed({
                    **record,
                    "status": "awaiting_douban_total",
                    "total_pending": True,
                    "last_checked": self._now(),
                    "reason": f"豆瓣总集数复核失败：{error}；下个执行周期继续复核",
                })
                logger.error(
                    f"豆瓣订阅助手：订阅 #{record.get('subscribe_id')} "
                    f"豆瓣总集数复核失败：{error}",
                    exc_info=True,
                )
        return summary

    def _resolve_pending_total(self, record: Dict[str, Any]) -> bool:
        subscribe_id = int(record.get("subscribe_id"))
        subscribe_oper = SubscribeOper()
        subscribe = subscribe_oper.get(subscribe_id)
        if not subscribe:
            self._upsert_managed({
                **record,
                "status": "missing_subscription",
                "check_after": "",
                "last_checked": self._now(),
                "reason": "等待豆瓣总集数期间，MoviePilot 中已找不到订阅卡片",
            })
            return False
        if str(getattr(subscribe, "username", "") or "") != PLUGIN_USERNAME:
            self._upsert_managed({
                **record,
                "status": "manual_review",
                "check_after": "",
                "last_checked": self._now(),
                "reason": "订阅归属已改变，插件停止复核豆瓣总集数",
            })
            return False

        provisional_total = int(record.get("expected_total") or UNKNOWN_TOTAL_EPISODE)
        if int(getattr(subscribe, "total_episode", 0) or 0) != provisional_total:
            self._upsert_managed({
                **record,
                "status": "manual_review",
                "check_after": "",
                "last_checked": self._now(),
                "reason": "等待豆瓣总集数期间订阅被手动修改，插件停止自动接管",
            })
            return False
        state = str(getattr(subscribe, "state", "") or "")
        if state == "S" and not record.get("pending_completed"):
            self._upsert_managed({
                **record,
                "status": "manual_review",
                "check_after": "",
                "last_checked": self._now(),
                "reason": "等待豆瓣总集数期间订阅被手动暂停，插件停止自动接管",
            })
            return False

        douban_id = str(record.get("douban_id") or getattr(subscribe, "doubanid", "") or "")
        if not douban_id:
            raise RuntimeError("订阅缺少豆瓣 ID")
        douban_info = self._call_douban(
            self.chain.douban_info,
            doubanid=douban_id,
            mtype=MediaType.TV,
        )
        douban_total = extract_total_episode(douban_info or {})
        if not douban_total:
            self._upsert_managed({
                **record,
                "status": "awaiting_douban_total",
                "total_pending": True,
                "last_checked": self._now(),
                "reason": (
                    f"豆瓣仍未提供明确总集数，继续暂按 {provisional_total} 集订阅，"
                    "下个执行周期再次复核"
                ),
            })
            return False

        old_lack = max(int(getattr(subscribe, "lack_episode", 0) or 0), 0)
        completed = max(provisional_total - old_lack, 0)
        new_lack = max(douban_total - completed, 0)
        subscribe_oper.update(subscribe_id, {
            "total_episode": douban_total,
            "lack_episode": new_lack,
            "manual_total_episode": 1,
            "state": "R",
        })
        self._upsert_managed({
            **record,
            "expected_total": douban_total,
            "manual_total": "",
            "total_pending": False,
            "pending_completed": False,
            "status": "active",
            "check_after": "",
            "last_checked": self._now(),
            "reason": (
                f"豆瓣已提供总集数 {douban_total}，已替换临时的 "
                f"{provisional_total} 集并更新缺失集数为 {new_lack}"
            ),
        })
        logger.info(
            f"豆瓣订阅助手：订阅 #{subscribe_id} 已取得豆瓣总集数 "
            f"{douban_total}，替换临时总集数 {provisional_total}"
        )
        try:
            SubscribeChain().search(sid=subscribe_id, state="R", manual=False)
        except Exception as error:
            logger.error(
                f"豆瓣订阅助手：订阅 #{subscribe_id} 总集数已回写，"
                f"但立即搜索失败：{error}",
                exc_info=True,
            )
            self._upsert_managed({
                "subscribe_id": subscribe_id,
                "reason": (
                    f"豆瓣总集数已更新为 {douban_total}；立即搜索失败，"
                    "订阅保持启用，将由 MoviePilot 后续继续搜索"
                ),
            })
        return True

    def _process_due_confirmations(self) -> Dict[str, int]:
        summary = {
            "confirmations": 0,
            "resumed": 0,
            "completed": 0,
            "manual_review": 0,
            "verification_failed": 0,
            "douban_rate_limited": False,
        }
        now = self._now_datetime()
        for record in self._managed_records():
            if record.get("status") not in {"waiting_confirmation", "verification_error"}:
                continue
            check_after = self._parse_datetime(record.get("check_after"))
            if check_after and check_after > now:
                continue
            summary["confirmations"] += 1
            try:
                outcome = self._confirm_managed_subscription(record)
                if outcome in summary:
                    summary[outcome] += 1
            except LimitException as error:
                summary["verification_failed"] += 1
                summary["douban_rate_limited"] = True
                self._mark_confirmation_error(record, error)
                break
            except Exception as error:
                summary["verification_failed"] += 1
                self._mark_confirmation_error(record, error)
        return summary

    def _confirm_managed_subscription(self, record: Dict[str, Any]) -> str:
        subscribe_id = int(record.get("subscribe_id"))
        subscribe_oper = SubscribeOper()
        subscribe = subscribe_oper.get(subscribe_id)
        if not subscribe:
            self._upsert_managed({
                **record,
                "status": "missing_subscription",
                "check_after": "",
                "last_checked": self._now(),
                "reason": "MoviePilot 中已找不到该订阅卡片，停止自动处理",
            })
            return "manual_review"
        if str(getattr(subscribe, "username", "") or "") != PLUGIN_USERNAME:
            self._upsert_managed({
                **record,
                "status": "manual_review",
                "check_after": "",
                "last_checked": self._now(),
                "reason": "订阅归属已改变，插件停止接管",
            })
            return "manual_review"

        expected_total = int(record.get("expected_total") or subscribe.total_episode or 0)
        if expected_total <= 0:
            raise RuntimeError("受管订阅缺少有效的预期总集数")
        if (
            str(getattr(subscribe, "state", "") or "") != "S"
            or int(subscribe.total_episode or 0) != expected_total
        ):
            self._upsert_managed({
                **record,
                "status": "manual_review",
                "check_after": "",
                "last_checked": self._now(),
                "reason": "等待确认期间订阅被手动修改，插件停止自动接管",
            })
            return "manual_review"

        self._upsert_managed({
            **record,
            "status": "confirming",
            "check_after": "",
            "last_checked": self._now(),
            "reason": "正在复核豆瓣总集数",
        })
        douban_id = str(record.get("douban_id") or getattr(subscribe, "doubanid", "") or "")
        douban_info = (
            self._call_douban(
                self.chain.douban_info,
                doubanid=douban_id,
                mtype=MediaType.TV,
            )
            if douban_id else None
        )
        douban_total = extract_total_episode(douban_info or {})
        if not douban_total:
            raise RuntimeError("豆瓣详情未返回明确总集数")
        if douban_total <= expected_total:
            return self._finish_after_unchanged_confirmation(
                record=record,
                subscribe=subscribe,
                expected_total=expected_total,
                douban_total=douban_total,
            )

        new_lack = douban_total - expected_total
        subscribe_oper.update(subscribe_id, {
            "total_episode": douban_total,
            "lack_episode": new_lack,
            "manual_total_episode": 1,
            "state": "R",
        })
        self._upsert_managed({
            **record,
            "expected_total": douban_total,
            "manual_total": "",
            "status": "active",
            "check_after": "",
            "last_checked": self._now(),
            "reason": (
                f"豆瓣总集数由 {expected_total} 增加为 {douban_total}，"
                f"继续订阅新增的 {new_lack} 集"
            ),
        })
        logger.info(
            f"豆瓣订阅助手：订阅 #{subscribe_id} 豆瓣总集数由 "
            f"{expected_total} 增加为 {douban_total}，恢复订阅"
        )
        try:
            SubscribeChain().search(sid=subscribe_id, state="R", manual=False)
        except Exception as error:
            logger.error(
                f"豆瓣订阅助手：订阅 #{subscribe_id} 总集数已更新，"
                f"但立即搜索失败：{error}",
                exc_info=True,
            )
            self._upsert_managed({
                "subscribe_id": subscribe_id,
                "reason": (
                    f"豆瓣总集数已更新为 {douban_total}；立即搜索失败，"
                    "订阅保持启用，将由 MoviePilot 后续继续搜索"
                ),
            })
        return "resumed"

    def _finish_after_unchanged_confirmation(
        self,
        record: Dict[str, Any],
        subscribe: Any,
        expected_total: int,
        douban_total: int,
    ) -> str:
        """Use MoviePilot's own finish path when Douban did not increase."""
        subscribe_id = int(record.get("subscribe_id"))
        subscribe_oper = SubscribeOper()
        subscribe_oper.update(subscribe_id, {
            "total_episode": expected_total,
            "lack_episode": 0,
            "manual_total_episode": 1,
            "state": "R",
        })
        subscribe = subscribe_oper.get(subscribe_id) or subscribe
        meta = MetaInfo(str(getattr(subscribe, "name", "") or record.get("title") or ""))
        meta.type = MediaType.TV
        meta.begin_season = int(getattr(subscribe, "season", 1) or 1)
        mediainfo = self.chain.recognize_media(
            meta=meta,
            mtype=MediaType.TV,
            tmdbid=getattr(subscribe, "tmdbid", None) or record.get("tmdb_id"),
            cache=False,
        )
        if not mediainfo:
            subscribe_oper.update(subscribe_id, {"state": "S"})
            raise RuntimeError("豆瓣总集数未增加，但 MoviePilot 无法识别媒体以完成订阅")

        self._upsert_managed({
            **record,
            "status": "finalizing",
            "check_after": "",
            "last_checked": self._now(),
            "reason": (
                f"豆瓣总集数为 {douban_total}，没有超过 {expected_total}，"
                "正在由 MoviePilot 正常完成订阅"
            ),
        })
        SubscribeChain().finish_subscribe_or_not(
            subscribe=subscribe,
            meta=meta,
            mediainfo=mediainfo,
            force=True,
        )
        if subscribe_oper.get(subscribe_id):
            subscribe_oper.update(subscribe_id, {"state": "S"})
            raise RuntimeError("豆瓣总集数未增加，但 MoviePilot 未能完成订阅")
        self._upsert_managed({
            **record,
            "status": "completed",
            "check_after": "",
            "last_checked": self._now(),
            "reason": "豆瓣总集数没有增加，订阅已正常完成",
        })
        logger.info(
            f"豆瓣订阅助手：订阅 #{subscribe_id} 豆瓣总集数没有增加，"
            "已由 MoviePilot 正常完成"
        )
        return "completed"

    def _mark_confirmation_error(self, record: Dict[str, Any], error: Exception) -> None:
        subscribe_id = record.get("subscribe_id")
        if subscribe_id and not SubscribeOper().get(int(subscribe_id)):
            self._upsert_managed({
                **record,
                "status": "completed",
                "check_after": "",
                "last_checked": self._now(),
                "reason": "确认流程结束后订阅卡片已不存在，按正常完成记录",
            })
            return
        retry_at = self._format_datetime(
            self._now_datetime() + datetime.timedelta(days=1)
        )
        self._upsert_managed({
            **record,
            "status": "verification_error",
            "check_after": retry_at,
            "last_checked": self._now(),
            "reason": f"完成确认失败：{error}；将在 1 天后重试",
        })
        logger.error(
            f"豆瓣订阅助手：订阅 #{record.get('subscribe_id')} 完成确认失败：{error}",
            exc_info=True,
        )

    def _register_managed_subscription(
        self,
        subscribe_id: int,
        title: str,
        tmdb_id: int,
        douban_id: str,
        season: int,
        expected_total: int,
        category: str,
        status: str,
        reason: str,
        source_key: str = "",
        total_pending: bool = False,
    ) -> None:
        existing = self._managed_record(subscribe_id)
        preserved_status = existing.get("status") if existing else ""
        if existing and (
            preserved_status in {
                "waiting_confirmation", "confirming", "finalizing",
                "manual_review", "verification_error", "completed",
            }
            or (preserved_status == "awaiting_douban_total" and total_pending)
        ):
            status = existing["status"]
            reason = existing.get("reason") or reason
        self._upsert_managed({
            "subscribe_id": subscribe_id,
            "title": title,
            "tmdb_id": tmdb_id,
            "douban_id": str(douban_id or ""),
            "season": season,
            "expected_total": expected_total,
            "category": category,
            "source_key": source_key or existing.get("source_key", ""),
            "total_pending": (
                existing.get("total_pending")
                if existing and existing.get("status") == "manual_review"
                else total_pending
            ),
            "pending_completed": (
                bool(existing.get("pending_completed"))
                if total_pending and existing else False
            ),
            "status": status,
            "created_at": existing.get("created_at") if existing else self._now(),
            "reason": reason,
        })

    def _managed_record(self, subscribe_id: Any) -> Dict[str, Any]:
        key = str(subscribe_id or "")
        if not key:
            return {}
        with self._data_lock:
            raw = self.get_data("managed_subscriptions") or {}
            if isinstance(raw, dict):
                value = raw.get(key) or raw.get(subscribe_id)
                return dict(value) if isinstance(value, dict) else {}
            for record in raw if isinstance(raw, list) else []:
                if str(record.get("subscribe_id") or "") == key:
                    return dict(record)
        return {}

    def _managed_records(self) -> List[Dict[str, Any]]:
        with self._data_lock:
            raw = self.get_data("managed_subscriptions") or {}
            if isinstance(raw, dict):
                records = [dict(value) for value in raw.values() if isinstance(value, dict)]
            elif isinstance(raw, list):
                records = [dict(value) for value in raw if isinstance(value, dict)]
            else:
                records = []
        return sorted(
            records,
            key=lambda item: str(item.get("created_at") or ""),
            reverse=True,
        )

    def _upsert_managed(self, record: Dict[str, Any]) -> None:
        subscribe_id = record.get("subscribe_id")
        if not subscribe_id:
            return
        key = str(subscribe_id)
        with self._data_lock:
            raw = self.get_data("managed_subscriptions") or {}
            if isinstance(raw, list):
                raw = {
                    str(item.get("subscribe_id")): item
                    for item in raw if isinstance(item, dict) and item.get("subscribe_id")
                }
            elif not isinstance(raw, dict):
                raw = {}
            current = dict(raw.get(key) or {})
            current.update({
                field: value for field, value in record.items()
                if value is not None
            })
            raw[key] = current
            self.save_data("managed_subscriptions", raw)

    def _processed_index(
        self,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Return the durable success index, migrating successful old history."""
        with self._data_lock:
            raw = self.get_data("processed_items") or {}
            if isinstance(raw, list):
                processed = {
                    str(item.get("key")): dict(item)
                    for item in raw
                    if isinstance(item, dict) and item.get("key")
                }
            elif isinstance(raw, dict):
                processed = {
                    str(key): dict(value)
                    for key, value in raw.items()
                    if key and isinstance(value, dict)
                }
            else:
                processed = {}

            changed = False
            for record in history if history is not None else (self.get_data("history") or []):
                key = str(record.get("key") or "")
                if not key or record.get("status") not in SUCCESS_STATUSES or key in processed:
                    continue
                processed[key] = self._processed_record(key, record)
                changed = True
            if changed or not isinstance(raw, dict):
                self.save_data("processed_items", processed)
            return processed

    def _cached_category_skip(self, item: FeedItem) -> Optional[Dict[str, Any]]:
        """Return a fresh skip record when the cached category remains disabled."""
        index = self._category_skip_index()
        cached = None
        for key in self._category_skip_keys(item):
            value = index.get(key)
            if isinstance(value, dict):
                cached = value
                break
        if not cached:
            return None
        category = str(cached.get("category") or "")
        if not category or category in self._media_categories:
            return None
        return {
            **item.to_dict(),
            "douban_id": str(cached.get("douban_id") or item.douban_id or ""),
            "douban_title": cached.get("douban_title") or item.title,
            "douban_year": cached.get("douban_year") or item.year or "",
            "douban_total": cached.get("douban_total"),
            "imdb_id": cached.get("imdb_id") or "",
            "airing_started": bool(cached.get("airing_started")),
            "total_pending": bool(cached.get("total_pending")),
            "category": category,
            "countries": cached.get("countries") or [],
            "status": "category_skipped",
            "reason": (
                f"{MEDIA_CATEGORY_LABELS.get(category, category)}未在订阅类型中启用"
                "（地区缓存命中，未请求豆瓣）"
            ),
            "time": self._now(),
        }

    def _category_skip_index(self) -> Dict[str, Dict[str, Any]]:
        """Load the category cache and migrate disabled-category history."""
        with self._data_lock:
            raw = self.get_data(CATEGORY_SKIP_DATA_KEY) or {}
            index = {
                str(key): dict(value)
                for key, value in raw.items()
                if key and isinstance(value, dict)
            } if isinstance(raw, dict) else {}
            changed = not isinstance(raw, dict)
            for record in self.get_data("history") or []:
                if not isinstance(record, dict) or record.get("status") != "category_skipped":
                    continue
                cached = self._category_skip_cache_record(record)
                keys = [str(record.get("key") or "")]
                douban_id = str(record.get("douban_id") or "").strip()
                if douban_id:
                    keys.append(f"douban:{douban_id}")
                for key in dict.fromkeys(value for value in keys if value):
                    if key not in index:
                        index[key] = dict(cached)
                        changed = True
            if changed:
                self.save_data(CATEGORY_SKIP_DATA_KEY, index)
            return index

    def _remember_category_skip(
        self,
        item: FeedItem,
        record: Dict[str, Any],
    ) -> None:
        """Persist one disabled-category result under source and Douban aliases."""
        cached = self._category_skip_cache_record(record)
        with self._data_lock:
            index = self._category_skip_index()
            for key in self._category_skip_keys(
                item,
                douban_id=str(record.get("douban_id") or ""),
            ):
                index[key] = dict(cached)
            self.save_data(CATEGORY_SKIP_DATA_KEY, index)

    @staticmethod
    def _category_skip_cache_record(record: Dict[str, Any]) -> Dict[str, Any]:
        """Keep only fields needed to rebuild a cached category result."""
        return {
            field: record.get(field)
            for field in (
                "title", "douban_id", "douban_title", "douban_year",
                "douban_total", "imdb_id", "airing_started", "total_pending",
                "category", "countries", "time",
            )
        }

    @staticmethod
    def _category_skip_keys(item: FeedItem, douban_id: str = "") -> List[str]:
        """Build stable source and Douban aliases for a category skip."""
        keys = [item.key]
        resolved_douban_id = str(douban_id or item.douban_id or "").strip()
        if resolved_douban_id:
            keys.append(f"douban:{resolved_douban_id}")
        return list(dict.fromkeys(keys))

    def _mark_processed(
        self,
        processed: Dict[str, Dict[str, Any]],
        key: str,
        record: Dict[str, Any],
    ) -> None:
        if not key:
            return
        processed[str(key)] = self._processed_record(str(key), record)
        with self._data_lock:
            self.save_data("processed_items", processed)

    @staticmethod
    def _processed_record(key: str, record: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "key": key,
            "status": record.get("status") or "",
            "title": record.get("title") or "",
            "subscribe_id": record.get("subscribe_id"),
            "douban_id": record.get("douban_id") or "",
            "tmdb_id": record.get("tmdb_id"),
            "time": record.get("time") or "",
        }

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime.datetime]:
        try:
            parsed = datetime.datetime.fromisoformat(str(value or ""))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed

    @staticmethod
    def _now_datetime() -> datetime.datetime:
        return datetime.datetime.now().astimezone()

    @staticmethod
    def _format_datetime(value: datetime.datetime) -> str:
        return value.astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _failed_record(record: Dict[str, Any], status: str, reason: str) -> Dict[str, Any]:
        record.update({"status": status, "reason": reason})
        return record

    @staticmethod
    def _record_history(history: List[dict], record: Dict[str, Any]) -> None:
        key = record.get("key")
        if key:
            history[:] = [item for item in history if item.get("key") != key]
        history.append(record)

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now().astimezone().isoformat(timespec="seconds")
