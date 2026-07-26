"""RSS-driven Douban to TMDB subscription plugin for MoviePilot V2."""

from __future__ import annotations

import datetime
import threading
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.metainfo import MetaInfo
from app.db.models.subscribe import Subscribe
from app.db.subscribe_oper import SubscribeOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import MediaType
from app.chain.subscribe import SubscribeChain
from app.utils.http import RequestUtils

from .core import (
    FeedItem,
    MatchDecision,
    ScoredCandidate,
    TmdbCandidate,
    build_search_hypotheses,
    build_title_hypotheses,
    choose_match,
    extract_total_episode,
    parse_feed,
    person_names,
    score_candidate,
)


DEFAULT_RSS_URL = "http://192.168.110.31:9150/rsshub/hot_tv"
DEFAULT_CRON = "0 */6 * * *"
PLUGIN_USERNAME = "豆瓣订阅助手"
SUCCESS_STATUSES = {"subscribed", "existing"}


class DoubanSubscribe(_PluginBase):
    """Create locked MoviePilot subscriptions from user-provided RSS feeds."""

    plugin_name = "豆瓣订阅助手"
    plugin_desc = "从 RSS 获取剧集，经豆瓣与 TMDB 匹配后创建锁定豆瓣总集数的订阅。"
    plugin_icon = (
        "https://raw.githubusercontent.com/jxxghp/"
        "MoviePilot-Plugins/main/icons/douban.png"
    )
    plugin_version = "0.2.1"
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
    _minimum_score = 80
    _minimum_margin = 15
    _candidate_limit = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sync_lock = threading.Lock()

    def init_plugin(self, config: dict = None) -> None:
        """Load configuration and optionally start a one-time run."""
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        self._onlyonce = bool(config.get("onlyonce", False))
        self._proxy = bool(config.get("proxy", False))
        self._rss_urls = config.get("rss_urls") or DEFAULT_RSS_URL
        self._cron = str(config.get("cron") or DEFAULT_CRON).strip()
        self._max_items = self._bounded_int(config.get("max_items"), 50, 1, 200)
        self._minimum_score = self._bounded_int(config.get("minimum_score"), 80, 0, 300)
        self._minimum_margin = self._bounded_int(config.get("minimum_margin"), 15, 0, 100)
        self._candidate_limit = self._bounded_int(config.get("candidate_limit"), 10, 1, 30)

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
            "minimum_score": self._minimum_score,
            "minimum_margin": self._minimum_margin,
            "candidate_limit": self._candidate_limit,
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
        }

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled or not self._configured_urls() or not self._cron:
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
                                "props": {"cols": 6, "md": 2},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "minimum_score",
                                        "label": "最低匹配分",
                                        "type": "number",
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 6, "md": 2},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "minimum_margin",
                                        "label": "最低领先分",
                                        "type": "number",
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
            "minimum_score": 80,
            "minimum_margin": 15,
            "candidate_limit": 10,
        }

    def get_page(self) -> List[dict]:
        history = list(reversed(self.get_data("history") or []))
        if not history:
            return [{
                "component": "VAlert",
                "props": {"type": "info", "variant": "tonal", "text": "暂无处理记录"},
            }]
        items = []
        for record in history[:200]:
            items.append({
                "title": record.get("title") or "",
                "status": record.get("status") or "",
                "douban_total": record.get("douban_total") or "",
                "tmdb": (
                    f"{record.get('tmdb_id')} / S{int(record.get('season') or 1):02d}"
                    if record.get("tmdb_id") else ""
                ),
                "score": record.get("score") if record.get("score") is not None else "",
                "time": record.get("time") or "",
                "reason": record.get("reason") or "",
            })
        return [{
            "component": "VDataTable",
            "props": {
                "headers": [
                    {"title": "标题", "key": "title"},
                    {"title": "状态", "key": "status"},
                    {"title": "豆瓣总集数", "key": "douban_total"},
                    {"title": "TMDB / 季", "key": "tmdb"},
                    {"title": "得分", "key": "score"},
                    {"title": "时间", "key": "time"},
                    {"title": "原因", "key": "reason"},
                ],
                "items": items,
                "items-per-page": 20,
                "density": "compact",
            },
        }]

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
        }
        try:
            urls = self._configured_urls()
            if not urls:
                summary.update({"success": False, "message": "未配置有效 RSS 地址"})
                return summary
            if not hasattr(Subscribe, "manual_total_episode"):
                summary.update({
                    "success": False,
                    "message": "当前 MoviePilot 不支持手动总集数锁定，请升级到 v2.15.0 或更高版本",
                })
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
            base_record.update({
                "douban_id": douban_id,
                "douban_title": douban_info.get("title") or item.title,
                "douban_year": douban_info.get("year") or item.year or "",
                "douban_total": total_episode,
            })
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
        return choose_match(scored, self._minimum_score, self._minimum_margin), media_by_key

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

    @staticmethod
    def _create_subscription(
        mediainfo,
        douban_id: str,
        season: int,
        total_episode: int,
    ) -> Dict[str, Any]:
        subscribe_oper = SubscribeOper()
        existing = subscribe_oper.get_by(
            type=MediaType.TV.value,
            season=season,
            tmdbid=mediainfo.tmdb_id,
        )
        if existing:
            return {
                "status": "existing",
                "subscribe_id": existing.id,
                "reason": "MoviePilot 中已存在相同 TMDB 与季度的订阅，未修改原订阅",
                "locked": bool(existing.manual_total_episode),
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
        return {
            "status": "subscribed",
            "subscribe_id": subscribe_id,
            "reason": f"已按豆瓣总集数 {total_episode} 创建并锁定订阅",
            "locked": True,
        }

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
