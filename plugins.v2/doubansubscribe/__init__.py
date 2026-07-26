"""RSS-driven Douban to TMDB subscription plugin for MoviePilot V2."""

from __future__ import annotations

import datetime
import threading
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
from app.schemas import SubscribeCompletionCheckEventData
from app.schemas.types import ChainEventType, MediaType
from app.chain.subscribe import SubscribeChain
from app.utils.http import RequestUtils

from .core import (
    FeedItem,
    MEDIA_CATEGORY_LABELS,
    MatchDecision,
    ScoredCandidate,
    TmdbCandidate,
    build_search_hypotheses,
    build_title_hypotheses,
    classify_media_region,
    choose_match,
    decide_confirmation,
    extract_total_episode,
    parse_feed,
    person_names,
    score_candidate,
)


DEFAULT_RSS_URL = "http://192.168.110.31:9150/rsshub/hot_tv"
DEFAULT_CRON = "0 */6 * * *"
PLUGIN_USERNAME = "豆瓣订阅助手"
SUCCESS_STATUSES = {"subscribed", "existing"}
SKIPPED_STATUSES = {"category_skipped"}
DEFAULT_MEDIA_CATEGORIES = tuple(MEDIA_CATEGORY_LABELS)
MANUAL_REVIEW_TOTAL = 100


class DoubanSubscribe(_PluginBase):
    """Create locked MoviePilot subscriptions from user-provided RSS feeds."""

    plugin_name = "豆瓣订阅助手"
    plugin_desc = "按地区筛选 RSS 剧集，锁定豆瓣总集数，并在完成后暂停复查。"
    plugin_icon = (
        "https://raw.githubusercontent.com/jxxghp/"
        "MoviePilot-Plugins/main/icons/douban.png"
    )
    plugin_version = "0.3.0"
    plugin_author = "tony3080"
    author_url = "https://github.com/tony3080"
    plugin_config_prefix = "doubansubscribe_"
    plugin_order = 50
    auth_level = 2

    _enabled = False
    _onlyonce = False
    _proxy = False
    _rss_urls = DEFAULT_RSS_URL
    _cron = DEFAULT_CRON
    _max_items = 50
    _candidate_limit = 10
    _confirmation_days = 7
    _media_categories = list(DEFAULT_MEDIA_CATEGORIES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sync_lock = threading.Lock()
        self._data_lock = threading.RLock()

    def init_plugin(self, config: dict = None) -> None:
        """Load configuration and optionally start a one-time run."""
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        self._onlyonce = bool(config.get("onlyonce", False))
        self._proxy = bool(config.get("proxy", False))
        self._rss_urls = config.get("rss_urls") or DEFAULT_RSS_URL
        self._cron = str(config.get("cron") or DEFAULT_CRON).strip()
        self._max_items = self._bounded_int(config.get("max_items"), 50, 1, 200)
        self._candidate_limit = self._bounded_int(config.get("candidate_limit"), 10, 1, 30)
        self._confirmation_days = self._bounded_int(
            config.get("confirmation_days"), 7, 1, 365,
        )
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
            "cron": self._cron,
            "max_items": self._max_items,
            "candidate_limit": self._candidate_limit,
            "confirmation_days": self._confirmation_days,
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
                "summary": "查询处理历史",
            },
        ]

    def api_run(self) -> Dict[str, Any]:
        if self._sync_lock.locked():
            return {"success": False, "message": "RSS 处理正在运行"}
        self._start_sync_thread()
        return {"success": True, "message": "RSS 处理已启动"}

    def api_history(self) -> Dict[str, Any]:
        return {
            "success": True,
            "last_run": self.get_data("last_run") or {},
            "items": list(reversed(self.get_data("history") or [])),
            "managed": self._managed_records(),
        }

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled or not self._cron:
            return []
        try:
            trigger = CronTrigger.from_crontab(self._cron)
        except (TypeError, ValueError) as error:
            logger.error(f"豆瓣订阅助手：无效的 Cron 表达式 {self._cron}：{error}")
            return []
        return [{
            "id": "DoubanSubscribe.Sync",
            "name": "豆瓣订阅助手 RSS 处理",
            "trigger": trigger,
            "func": self.sync,
            "kwargs": {},
        }]

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
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {"model": "enabled", "label": "启用插件"},
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {"model": "onlyonce", "label": "立即运行一次"},
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {"model": "proxy", "label": "RSS 使用代理"},
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
                                        "hint": "订阅完成后暂停，等待该天数再核对豆瓣总集数",
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
            "cron": DEFAULT_CRON,
            "max_items": 50,
            "candidate_limit": 10,
            "confirmation_days": 7,
            "media_categories": list(DEFAULT_MEDIA_CATEGORIES),
        }

    def get_page(self) -> List[dict]:
        history = list(reversed(self.get_data("history") or []))
        managed = self._managed_records()
        if not history and not managed:
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
            "waiting_confirmation": "已暂停，等待复查",
            "manual_review": "等待手动处理",
            "verification_error": "复查失败，等待重试",
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
                "total": record.get("expected_total") or "",
                "mp_total": record.get("manual_total") or record.get("expected_total") or "",
                "status": status_labels.get(
                    record.get("status"), record.get("status") or "",
                ),
                "check_after": record.get("check_after") or "",
                "reason": record.get("reason") or "",
            })

        history_items = []
        for record in history[:200]:
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
                            "subtitle": "完成后暂停、豆瓣总集数复查及手动接管状态",
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
                                        {"title": "下次复查", "key": "check_after"},
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

    def sync(self) -> Dict[str, Any]:
        """Fetch all feeds and process unseen entries serially to respect API limits."""
        if not self._sync_lock.acquire(blocking=False):
            return {"success": False, "message": "RSS 处理正在运行"}
        started_at = self._now()
        summary = {
            "success": True,
            "started_at": started_at,
            "finished_at": "",
            "feeds": 0,
            "items": 0,
            "subscribed": 0,
            "existing": 0,
            "skipped": 0,
            "failed": 0,
            "confirmations": 0,
            "resumed": 0,
            "manual_review": 0,
            "verification_failed": 0,
        }
        try:
            if not hasattr(Subscribe, "manual_total_episode"):
                summary.update({
                    "success": False,
                    "message": "当前 MoviePilot 不支持手动总集数锁定，请升级到 v2.15.0 或更高版本",
                })
                return summary
            confirmation_summary = self._process_due_confirmations()
            summary.update(confirmation_summary)

            urls = self._configured_urls()
            if not urls:
                if summary["confirmations"]:
                    summary["message"] = "未配置有效 RSS 地址，仅完成到期订阅复查"
                    return summary
                summary.update({"success": False, "message": "未配置有效 RSS 地址"})
                return summary

            history = self.get_data("history") or []
            completed_keys = {
                record.get("key") for record in history
                if record.get("status") in SUCCESS_STATUSES
            }
            for url in urls:
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
                for item in items[:self._max_items]:
                    summary["items"] += 1
                    if item.key in completed_keys:
                        summary["skipped"] += 1
                        continue
                    record = self._process_item(item)
                    self._record_history(history, record)
                    status = record.get("status")
                    if status == "subscribed":
                        summary["subscribed"] += 1
                        completed_keys.add(item.key)
                    elif status == "existing":
                        summary["existing"] += 1
                        completed_keys.add(item.key)
                    elif status in SKIPPED_STATUSES:
                        summary["skipped"] += 1
                    else:
                        summary["failed"] += 1
            self.save_data("history", history[-500:])
            return summary
        except Exception as error:
            logger.error(f"豆瓣订阅助手：RSS 处理失败：{error}", exc_info=True)
            summary.update({"success": False, "message": str(error)})
            return summary
        finally:
            summary["finished_at"] = self._now()
            self.save_data("last_run", summary)
            self._sync_lock.release()

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
            category = classify_media_region(douban_info)
            base_record.update({
                "douban_id": douban_id,
                "douban_title": douban_info.get("title") or item.title,
                "douban_year": douban_info.get("year") or item.year or "",
                "douban_total": total_episode,
                "category": category,
                "countries": douban_info.get("countries") or [],
            })
            if category not in self._media_categories:
                return self._failed_record(
                    base_record,
                    "category_skipped",
                    f"{MEDIA_CATEGORY_LABELS.get(category, category)}未在订阅类型中启用",
                )
            if not total_episode:
                return self._failed_record(
                    base_record,
                    "douban_total_missing",
                    "豆瓣详情没有明确总集数，未创建订阅",
                )

            decision, media_by_key = self._match_tmdb(douban_info, total_episode)
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
                total_episode=total_episode,
                category=category,
            )
            base_record.update(subscription)
            return base_record
        except Exception as error:
            logger.error(f"豆瓣订阅助手：处理《{item.title}》失败：{error}", exc_info=True)
            return self._failed_record(base_record, "error", str(error))

    def _resolve_douban(self, item: FeedItem) -> Optional[Dict[str, Any]]:
        douban_id = item.douban_id
        if not douban_id:
            for hypothesis in build_title_hypotheses(item.title):
                if hypothesis.mode != "exact_title":
                    continue
                matched = self.chain.match_doubaninfo(
                    name=hypothesis.title,
                    mtype=MediaType.TV,
                    year=item.year,
                    season=hypothesis.season,
                    raise_exception=False,
                )
                if matched and matched.get("id"):
                    douban_id = str(matched["id"])
                    break
        if not douban_id:
            return None
        detail = self.chain.douban_info(
            doubanid=str(douban_id),
            mtype=MediaType.TV,
            raise_exception=False,
        )
        if detail:
            detail["id"] = str(detail.get("id") or douban_id)
        return detail

    def _match_tmdb(
        self,
        douban_info: Dict[str, Any],
        total_episode: int,
    ) -> Tuple[MatchDecision, Dict[Tuple[int, int], Any]]:
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
        searched_keys = set()
        for hypothesis in build_search_hypotheses(
            title=title,
            original_title=str(douban_info.get("original_title") or ""),
            aliases=tuple(str(value) for value in (douban_info.get("aka") or []) if value),
        ):
            meta = MetaInfo(hypothesis.title)
            meta.type = MediaType.TV
            if hypothesis.mode != "base_and_season" and year:
                meta.year = year
            results = self.chain.search_medias(meta=meta, source="themoviedb") or []
            for search_result in results:
                tmdb_id = getattr(search_result, "tmdb_id", None)
                season = hypothesis.season if hypothesis.season is not None else 1
                if not tmdb_id or (tmdb_id, season, hypothesis.mode) in searched_keys:
                    continue
                searched_keys.add((tmdb_id, season, hypothesis.mode))
                if len(hydrated_by_id) >= self._candidate_limit and tmdb_id not in hydrated_by_id:
                    continue
                mediainfo = hydrated_by_id.get(tmdb_id)
                if mediainfo is None:
                    detail_meta = MetaInfo(hypothesis.title)
                    detail_meta.type = MediaType.TV
                    mediainfo = self.chain.recognize_media(
                        meta=detail_meta,
                        mtype=MediaType.TV,
                        tmdbid=tmdb_id,
                        cache=False,
                    )
                    if not mediainfo:
                        continue
                    hydrated_by_id[tmdb_id] = mediainfo
                candidate = self._build_tmdb_candidate(mediainfo, hypothesis, season)
                scored.append(score_candidate(source, candidate))
                media_by_key[(candidate.tmdb_id, candidate.season)] = mediainfo
        return choose_match(scored), media_by_key

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

    def _build_tmdb_candidate(self, mediainfo, hypothesis, season: int) -> TmdbCandidate:
        seasons = getattr(mediainfo, "seasons", {}) or {}
        episodes = seasons.get(season)
        if episodes is None:
            episodes = seasons.get(str(season))
        season_years = getattr(mediainfo, "season_years", {}) or {}
        season_year = season_years.get(season) or season_years.get(str(season))
        return TmdbCandidate(
            tmdb_id=int(mediainfo.tmdb_id),
            title=str(getattr(mediainfo, "title", "") or ""),
            original_title=str(getattr(mediainfo, "original_title", "") or ""),
            names=self._title_names(getattr(mediainfo, "names", []) or []),
            year=str(getattr(mediainfo, "year", "") or "") or None,
            season=season,
            season_year=str(season_year or "") or None,
            season_episode_count=len(episodes) if episodes is not None else None,
            actors=person_names(getattr(mediainfo, "actors", []) or []),
            directors=person_names(getattr(mediainfo, "directors", []) or []),
            mode=hypothesis.mode,
            strength=hypothesis.strength,
            hypothesis_title=hypothesis.title,
        )

    def _create_subscription(
        self,
        mediainfo,
        douban_id: str,
        season: int,
        total_episode: int,
        category: str,
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
                if managed_record.get("status") != "manual_review":
                    old_total = int(existing.total_episode or 0)
                    old_lack = int(existing.lack_episode or 0)
                    subscribe_oper.update(existing.id, {
                        "total_episode": total_episode,
                        "lack_episode": max(old_lack + total_episode - old_total, 0),
                        "manual_total_episode": 1,
                    })
                    existing = subscribe_oper.get(existing.id)
                self._register_managed_subscription(
                    subscribe_id=existing.id,
                    title=existing.name or mediainfo.title,
                    tmdb_id=mediainfo.tmdb_id,
                    douban_id=douban_id,
                    season=season,
                    expected_total=total_episode,
                    category=category,
                    status="active",
                    reason="已接管此前由豆瓣订阅助手创建的订阅",
                )
            return {
                "status": "existing",
                "subscribe_id": existing.id,
                "reason": (
                    "已接管此前由豆瓣订阅助手创建的订阅"
                    if managed else
                    "MoviePilot 中已存在相同 TMDB 与季度的订阅，未接管用户原订阅"
                ),
                "locked": bool(getattr(existing, "manual_total_episode", False)),
                "managed": managed,
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
            message=False,
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
                "reason": "订阅已创建，但豆瓣总集数锁定校验失败",
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
            status="active",
            reason="订阅由豆瓣订阅助手管理",
        )
        return {
            "status": "subscribed",
            "subscribe_id": subscribe_id,
            "reason": f"已按豆瓣总集数 {total_episode} 创建并锁定订阅",
            "locked": True,
            "managed": True,
        }

    @eventmanager.register(ChainEventType.SubscribeCompletionCheck, priority=10)
    def on_subscribe_completion_check(self, event: Event) -> None:
        """Keep managed subscriptions as paused cards instead of letting MoviePilot delete them."""
        if not self._enabled or not event or not event.event_data:
            return
        event_data: SubscribeCompletionCheckEventData = event.event_data
        subscribe = getattr(event_data, "subscribe", None)
        subscribe_id = getattr(subscribe, "id", None)
        if not subscribe_id:
            return
        managed = self._managed_record(subscribe_id)
        if managed and managed.get("status") == "manual_review":
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

        event_data.cancel = True
        event_data.source = self.plugin_name
        event_data.reason = "订阅已完成，保留卡片并暂停，等待豆瓣总集数复查"
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
                "reason": f"已完成并暂停，将在 {self._confirmation_days} 天后复查豆瓣总集数",
            })
            logger.info(
                f"豆瓣订阅助手：订阅 #{subscribe_id} 已完成，已暂停并保留卡片，"
                f"将在 {check_after} 后复查"
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

    def _process_due_confirmations(self) -> Dict[str, int]:
        summary = {
            "confirmations": 0,
            "resumed": 0,
            "manual_review": 0,
            "verification_failed": 0,
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
        if (
            str(getattr(subscribe, "state", "") or "") != "S"
            or int(subscribe.total_episode or 0) != expected_total
        ):
            self._upsert_managed({
                **record,
                "status": "manual_review",
                "check_after": "",
                "last_checked": self._now(),
                "reason": "等待复查期间订阅被手动修改，插件停止自动接管",
            })
            return "manual_review"

        douban_id = str(record.get("douban_id") or subscribe.doubanid or "")
        if not douban_id:
            raise RuntimeError("订阅缺少豆瓣 ID")
        douban_info = self.chain.douban_info(
            doubanid=douban_id,
            mtype=MediaType.TV,
            raise_exception=False,
        )
        douban_total = extract_total_episode(douban_info or {})
        if not douban_total:
            raise RuntimeError("豆瓣详情未返回明确总集数")

        decision = decide_confirmation(
            expected_total=expected_total,
            douban_total=douban_total,
            current_lack=int(subscribe.lack_episode or 0),
            manual_total=MANUAL_REVIEW_TOTAL,
        )
        checked_at = self._now()
        if not decision.changed:
            subscribe_oper.update(subscribe_id, {
                "total_episode": decision.total_episode,
                "lack_episode": decision.lack_episode,
                "manual_total_episode": 1,
                "state": "S",
            })
            self._upsert_managed({
                **record,
                "expected_total": douban_total,
                "manual_total": decision.total_episode,
                "status": "manual_review",
                "check_after": "",
                "last_checked": checked_at,
                "reason": (
                    f"豆瓣总集数仍为 {douban_total}，订阅总集数已改为 "
                    f"{decision.total_episode} 并保持暂停，请手动处理"
                ),
            })
            logger.info(
                f"豆瓣订阅助手：订阅 #{subscribe_id} 复查后豆瓣总集数未变化，"
                f"已改为 {decision.total_episode} 并交由用户处理"
            )
            return "manual_review"

        resume = decision.lack_episode > 0
        subscribe_oper.update(subscribe_id, {
            "total_episode": decision.total_episode,
            "lack_episode": decision.lack_episode,
            "manual_total_episode": 1,
            "state": "R" if resume else "S",
        })
        if not resume:
            check_after = self._format_datetime(
                self._now_datetime() + datetime.timedelta(days=self._confirmation_days)
            )
            self._upsert_managed({
                **record,
                "expected_total": douban_total,
                "status": "waiting_confirmation",
                "check_after": check_after,
                "last_checked": checked_at,
                "reason": (
                    f"豆瓣总集数由 {expected_total} 调整为 {douban_total}，"
                    f"没有新增缺失集，保持暂停并将在 {self._confirmation_days} 天后再次确认"
                ),
            })
            return ""

        self._upsert_managed({
            **record,
            "expected_total": douban_total,
            "status": "active",
            "check_after": "",
            "last_checked": checked_at,
            "reason": (
                f"豆瓣总集数由 {expected_total} 增加为 {douban_total}，"
                f"已恢复订阅并立即搜索 {decision.lack_episode} 个缺失集"
            ),
        })
        logger.info(
            f"豆瓣订阅助手：订阅 #{subscribe_id} 豆瓣总集数由 "
            f"{expected_total} 变为 {douban_total}，立即搜索缺失集"
        )
        try:
            SubscribeChain().search(sid=subscribe_id, state="R", manual=True)
        except Exception as error:
            logger.error(
                f"豆瓣订阅助手：订阅 #{subscribe_id} 总集数已更新，但立即搜索失败：{error}",
                exc_info=True,
            )
            self._upsert_managed({
                "subscribe_id": subscribe_id,
                "reason": (
                    f"总集数已更新为 {douban_total}，立即搜索失败；"
                    "订阅保持启用，将由 MoviePilot 后续周期继续搜索"
                ),
            })
        return "resumed"

    def _mark_confirmation_error(self, record: Dict[str, Any], error: Exception) -> None:
        retry_at = self._format_datetime(
            self._now_datetime() + datetime.timedelta(days=1)
        )
        self._upsert_managed({
            **record,
            "status": "verification_error",
            "check_after": retry_at,
            "last_checked": self._now(),
            "reason": f"豆瓣总集数复查失败：{error}；将在 1 天后重试",
        })
        logger.error(
            f"豆瓣订阅助手：订阅 #{record.get('subscribe_id')} 复查失败：{error}",
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
    ) -> None:
        existing = self._managed_record(subscribe_id)
        if existing and existing.get("status") in {
            "waiting_confirmation", "manual_review", "verification_error",
        }:
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
