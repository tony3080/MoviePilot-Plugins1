"""Durable RSS execution and qBittorrent enqueue workflow."""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .database import SQLiteStore, utc_now
from .rss_feed import (
    FetchResult,
    MAX_FEED_BYTES,
    ParsedEntry,
    RssFeedError,
    classify_entry,
    fetch_feed,
    parse_feed,
    prepare_entry,
    validate_feed_url,
)
from .rss_rename import QbSourceRenameService
from .rss_site_labels import SiteHttpError, SiteLabelService


RSS_RUN_TASK_TYPE = "rss_run"
RETRY_DELAYS = (3, 10, 30)
MAX_TORRENT_BYTES = 20 * 1024 * 1024
MANDARIN_MEDIA_CATEGORIES = {
    "",
    "外语电影",
    "动画电影",
    "未识别",
    "未分类",
}


class RssExecutionError(RuntimeError):
    """A task-level execution failure safe for UI display."""


class RssExecutionCancelled(RuntimeError):
    """The RSS runtime switch stopped the active batch."""


@dataclass(frozen=True)
class SiteAccess:
    site_key: str = ""
    site_name: str = ""
    site_url: str = ""
    cookie: str = ""
    user_agent: str = ""
    referer: str = ""
    proxies: Any = None
    timeout: int = 20


@dataclass(frozen=True)
class AddResult:
    success: bool
    info_hash: str = ""
    existing: bool = False
    reason: str = ""


class MoviePilotRssGateway:
    """MoviePilot-native access to site credentials and qB services."""

    @staticmethod
    def qb_server(downloader: str) -> Any:
        from app.helper.downloader import DownloaderHelper

        service = DownloaderHelper().get_service(
            name=str(downloader or "").strip(),
            type_filter="qbittorrent",
        )
        server = getattr(service, "instance", None) if service else None
        if not server:
            raise RssExecutionError(f"qBittorrent 节点不可用：{downloader}")
        try:
            if server.is_inactive():
                server.reconnect()
        except Exception:
            pass
        if not getattr(server, "qbc", None):
            raise RssExecutionError(f"qBittorrent 登录失败：{downloader}")
        return server

    @staticmethod
    def site_access(site_id: object) -> SiteAccess:
        from app.core.config import settings

        user_agent = str(getattr(settings, "NORMAL_USER_AGENT", "") or "")
        raw_id = str(site_id or "").strip()
        if not raw_id:
            return SiteAccess(user_agent=user_agent)
        try:
            from app.db.site_oper import SiteOper

            site = SiteOper().get(int(raw_id)) if raw_id.isdigit() else None
        except Exception as error:
            raise RssExecutionError(f"读取 MoviePilot 站点身份失败：{error}") from error
        if not site:
            raise RssExecutionError(f"MoviePilot 站点身份不存在：{raw_id}")
        proxies = settings.PROXY if bool(getattr(site, "proxy", False)) else None
        return SiteAccess(
            site_key=str(getattr(site, "site_key", "") or ""),
            site_name=str(getattr(site, "name", "") or ""),
            site_url=str(getattr(site, "url", "") or ""),
            cookie=str(getattr(site, "cookie", "") or ""),
            user_agent=str(getattr(site, "ua", "") or user_agent),
            referer=str(getattr(site, "url", "") or ""),
            proxies=proxies,
            timeout=25,
        )

    @staticmethod
    def fetch_site_html(url: str, access: SiteAccess) -> str:
        from app.utils.http import RequestUtils

        try:
            response = RequestUtils(
                ua=access.user_agent or None,
                cookies=access.cookie or None,
                proxies=access.proxies,
                timeout=access.timeout,
                referer=access.referer or access.site_url or None,
                accept_type="text/html,application/xhtml+xml,*/*",
            ).get_res(url)
        except Exception as error:
            raise RssExecutionError(
                f"站点标签请求失败：{error.__class__.__name__}"
            ) from error
        if not response:
            raise RssExecutionError("站点标签请求无响应")
        status_code = int(getattr(response, "status_code", 200) or 0)
        if status_code != 200:
            raise SiteHttpError(status_code)
        return str(getattr(response, "text", "") or "")

    @staticmethod
    def fetch_torrent(url: str, access: SiteAccess) -> bytes:
        from app.utils.http import RequestUtils

        try:
            response = RequestUtils(
                ua=access.user_agent or None,
                cookies=access.cookie or None,
                proxies=access.proxies,
                timeout=access.timeout,
                referer=access.referer or None,
                accept_type="application/x-bittorrent,application/octet-stream,*/*",
            ).get_res(url)
        except Exception as error:
            raise RssExecutionError(
                f"下载种子文件失败：{error.__class__.__name__}"
            ) from error
        if not response:
            raise RssExecutionError("下载种子文件无响应")
        status_code = int(getattr(response, "status_code", 200) or 0)
        if status_code != 200:
            raise RssExecutionError(f"下载种子文件 HTTP {status_code}")
        content = getattr(response, "content", b"") or b""
        if isinstance(content, str):
            content = content.encode("utf-8")
        content = bytes(content)
        if not content:
            raise RssExecutionError("下载到的种子文件为空")
        if len(content) > MAX_TORRENT_BYTES:
            raise RssExecutionError("种子文件超过 20 MiB 安全上限")
        if not torrent_hash_candidates(content):
            raise RssExecutionError("下载内容不是有效的 BitTorrent 种子文件")
        return content

    @staticmethod
    def find_existing(server: Any, candidates: Sequence[str]) -> str:
        normalized = [str(item or "").strip().lower() for item in candidates if item]
        if not normalized:
            return ""
        torrents, error = server.get_torrents(ids=normalized)
        if error:
            return ""
        for item in torrents or []:
            info_hash = str(item.get("hash") or "").strip().lower()
            if info_hash:
                return info_hash
        return ""

    @staticmethod
    def clear_temporary_tag(server: Any, tag: str, info_hash: str = "") -> None:
        """Remove the internal lookup tag so qB keeps only the task category."""
        torrent_ids: List[str] = []
        if info_hash:
            torrent_ids.append(str(info_hash).strip().lower())
        else:
            try:
                torrents, error = server.get_torrents(tags=[tag])
                if not error:
                    torrent_ids.extend(
                        str(item.get("hash") or "").strip().lower()
                        for item in torrents or []
                    )
            except Exception:
                return
        torrent_ids = [item for item in dict.fromkeys(torrent_ids) if item]
        if not torrent_ids:
            return
        try:
            server.delete_torrents_tag(torrent_ids, tag)
        except Exception:
            pass

    def add_torrent(
        self,
        server: Any,
        *,
        content: Any,
        mode: str,
        save_path: str,
        category: str,
        paused: bool,
        cookie: str,
        hash_candidates: Sequence[str],
    ) -> AddResult:
        tag = f"rssallinone-{uuid.uuid4().hex[:12]}"
        try:
            state, added_ids = server.add_torrent(
                content=content,
                download_dir=save_path or None,
                is_paused=bool(paused),
                tag=[tag],
                cookie=cookie or None,
                category=category,
                ignore_category_check=True,
            )
        except Exception as error:
            return AddResult(False, reason=f"qB 添加异常：{error.__class__.__name__}")

        info_hash = str(next(iter(added_ids or []), "") or "").strip().lower()
        if not info_hash and hash_candidates:
            for _ in range(6):
                info_hash = self.find_existing(server, hash_candidates)
                if info_hash:
                    break
                time.sleep(0.5)
        if state and not info_hash:
            try:
                info_hash = str(server.get_torrent_id_by_tag(tags=tag) or "").lower()
            except Exception:
                info_hash = ""
        if state and info_hash:
            self.clear_temporary_tag(server, tag, info_hash)
            return AddResult(True, info_hash=info_hash)
        if not state:
            existing = self.find_existing(server, hash_candidates)
            if existing:
                self.clear_temporary_tag(server, tag, existing)
                return AddResult(True, info_hash=existing, existing=True)
        self.clear_temporary_tag(server, tag)
        if state:
            return AddResult(False, reason=f"{mode} 模式添加成功但未取得 info-hash")
        return AddResult(False, reason=f"qB 拒绝 {mode} 模式添加")

    @staticmethod
    def set_upload_limit(server: Any, info_hash: str, limit_kbps: int) -> bool:
        limit_kbps = max(0, int(limit_kbps or 0))
        if limit_kbps == 0:
            return True
        try:
            return bool(server.change_torrent(
                hash_string=info_hash,
                upload_limit=limit_kbps,
            ))
        except Exception:
            return False

    @staticmethod
    def list_torrent_files(server: Any, info_hash: str) -> List[Any]:
        try:
            return list(server.get_files(info_hash, retry=6, interval=0.5) or [])
        except Exception as error:
            raise RssExecutionError(f"读取 qB 文件列表失败：{error}") from error

    @staticmethod
    def rename_torrent_file(
        server: Any,
        info_hash: str,
        old_path: str,
        new_path: str,
    ) -> None:
        try:
            server.qbc.torrents_rename_file(
                torrent_hash=info_hash,
                old_path=old_path,
                new_path=new_path,
            )
        except Exception as error:
            raise RssExecutionError(
                f"qB 文件改名失败：{old_path} -> {new_path}：{error}"
            ) from error

    @staticmethod
    def rename_torrent_folder(
        server: Any,
        info_hash: str,
        old_path: str,
        new_path: str,
    ) -> None:
        try:
            server.qbc.torrents_rename_folder(
                torrent_hash=info_hash,
                old_path=old_path,
                new_path=new_path,
            )
        except Exception as error:
            raise RssExecutionError(
                f"qB 目录改名失败：{old_path} -> {new_path}：{error}"
            ) from error


class RssExecutionService:
    """Execute one saved RSS task and persist durable source/content identities."""

    def __init__(
        self,
        store: SQLiteStore,
        gateway: Optional[MoviePilotRssGateway] = None,
        renamer: Optional[QbSourceRenameService] = None,
        feed_fetcher: Any = None,
        sleeper: Any = None,
        on_enqueued: Any = None,
        on_source_ready: Any = None,
        label_service: Any = None,
        media_category_resolver: Any = None,
        logger: Any = None,
    ) -> None:
        self.store = store
        self.gateway = gateway or MoviePilotRssGateway()
        self.feed_fetcher = feed_fetcher or fetch_feed
        self.sleeper = sleeper or time.sleep
        self.on_source_ready = on_source_ready or on_enqueued
        self.renamer = renamer or QbSourceRenameService(
            self.gateway,
            sleeper=self.sleeper,
        )
        self.label_service = label_service or SiteLabelService(
            self.gateway,
            sleeper=self.sleeper,
            logger=logger,
        )
        self.media_category_resolver = (
            media_category_resolver or self._moviepilot_media_category
        )
        self.logger = logger

    def run(
        self,
        background_task_id: str,
        task: Dict[str, Any],
        *,
        stop_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        task_id = str(task.get("id") or "").strip()
        task_name = str(task.get("name") or task_id).strip()
        config = task.get("config") if isinstance(task.get("config"), dict) else {}
        if not task.get("enabled"):
            raise RssExecutionError("RSS 任务未启用")
        rss_url = validate_feed_url(config.get("rss_url"))
        downloader = str(config.get("qb_downloader") or "").strip()
        category = str(config.get("qb_category") or "").strip()
        if not downloader:
            raise RssExecutionError("RSS 任务未配置 QB 下载器")
        if not category:
            raise RssExecutionError("RSS 任务未配置 QB 分类")

        fetched: FetchResult = self.feed_fetcher(rss_url)
        body = bytes(fetched.body or b"")
        if not body:
            raise RssExecutionError("RSS 请求成功，但响应内容为空")
        if len(body) > MAX_FEED_BYTES:
            raise RssExecutionError(
                f"RSS 响应超过 {MAX_FEED_BYTES // 1024 // 1024} MiB 安全上限"
            )
        _feed, entries = parse_feed(body)
        prepared = [prepare_entry(task_id, entry) for entry in entries]
        existing_sources = self.store.find_rss_source_keys(
            task_id,
            [item.get("source_key") for item in prepared],
        )
        server = self.gateway.qb_server(downloader)
        access = self.gateway.site_access(config.get("site_id"))
        total = len(prepared)
        result: Dict[str, Any] = {
            "task_id": task_id,
            "task_name": task_name,
            "downloader": downloader,
            "category": category,
            "total": total,
            "queued": 0,
            "queued_warning": 0,
            "content_duplicate": 0,
            "existing": 0,
            "filtered": 0,
            "missing_enclosure": 0,
            "duplicate_source": 0,
            "invalid": 0,
            "failed": 0,
            "qb_recognized": 0,
            "qb_recognition_failed": 0,
            "qb_recognition_deferred": 0,
            "errors": [],
        }
        self.store.update_background_task(
            background_task_id,
            total=total,
            result=result,
        )
        processed = succeeded = failed = 0
        seen = set()

        for position, (entry, prepared_entry) in enumerate(
            zip(entries, prepared), start=1
        ):
            if stop_event and stop_event.is_set():
                self.store.finish_background_task(
                    background_task_id,
                    "cancelled",
                    result=result,
                    error_message="插件正在停止",
                )
                return result
            title = str(prepared_entry.get("title") or f"条目 {position}")
            status, reason = classify_entry(
                prepared_entry,
                name_contains=str(config.get("name_contains") or "").strip(),
                existing=set(existing_sources),
                seen=seen,
            )
            source_key = str(prepared_entry.get("source_key") or "")
            if source_key:
                seen.add(source_key)

            if status == "duplicate":
                result["duplicate_source"] += 1
                succeeded += 1
            elif status != "ready":
                result[status] += 1
                self._save_history(
                    task_id=task_id,
                    prepared=prepared_entry,
                    status=status,
                    reason=reason,
                    payload={"task_name": task_name},
                )
                succeeded += 1
            else:
                try:
                    outcome = self._enqueue(
                        entry=entry,
                        prepared=prepared_entry,
                        config=config,
                        downloader=downloader,
                        category=category,
                        server=server,
                        access=access,
                        stop_event=stop_event,
                    )
                    outcome_status = outcome["status"]
                    result[outcome_status] += 1
                    self._save_history(
                        task_id=task_id,
                        prepared=prepared_entry,
                        status=outcome_status,
                        reason=outcome["reason"],
                        content_key=outcome.get("content_key") or "",
                        payload={
                            "task_name": task_name,
                            "downloader": downloader,
                            "category": category,
                            "info_hash": outcome.get("info_hash") or "",
                            "mode": outcome.get("mode") or "",
                            "source_rename": outcome.get("source_rename") or {},
                            "site_labels": outcome.get("site_labels") or {},
                        },
                    )
                    if source_key:
                        existing_sources.add(source_key)
                    info_hash = str(outcome.get("info_hash") or "").strip().lower()
                    if (
                        self.on_source_ready
                        and info_hash
                        and outcome_status in {
                            "queued", "queued_warning", "existing"
                        }
                    ):
                        source_rename = outcome.get("source_rename") or {}
                        if source_rename.get("status") == "failed":
                            result["qb_recognition_deferred"] += 1
                        else:
                            try:
                                self.on_source_ready(downloader, info_hash)
                                result["qb_recognized"] += 1
                            except Exception as error:
                                result["qb_recognition_failed"] += 1
                                result["errors"].append({
                                    "title": title,
                                    "message": f"QB 初始识别失败：{str(error)[:400]}",
                                })
                                self._log(
                                    "error",
                                    f"RSS一条龙：QB 初始识别失败 "
                                    f"{downloader}/{info_hash}：{error}",
                                )
                    succeeded += 1
                except RssExecutionCancelled:
                    self.store.finish_background_task(
                        background_task_id,
                        "cancelled",
                        result=result,
                        error_message="RSS 调度已暂停",
                    )
                    return result
                except Exception as error:
                    failed += 1
                    result["failed"] += 1
                    safe_reason = str(error)[:500]
                    result["errors"].append({"title": title, "message": safe_reason})
                    self._save_history(
                        task_id=task_id,
                        prepared=prepared_entry,
                        status="failed",
                        reason=safe_reason,
                        payload={
                            "task_name": task_name,
                            "downloader": downloader,
                            "category": category,
                        },
                    )
                    self._log("error", f"RSS一条龙：处理 {task_name}/{title} 失败：{error}")

            processed += 1
            self.store.update_background_task(
                background_task_id,
                current_item=title,
                processed=processed,
                succeeded=succeeded,
                failed=failed,
                total=total,
                result=result,
            )

        self.store.finish_background_task(
            background_task_id,
            "succeeded",
            result=result,
        )
        return result

    def _enqueue(
        self,
        *,
        entry: ParsedEntry,
        prepared: Dict[str, Any],
        config: Dict[str, Any],
        downloader: str,
        category: str,
        server: Any,
        access: SiteAccess,
        stop_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        if stop_event and stop_event.is_set():
            raise RssExecutionCancelled()
        torrent_content = b""
        fetch_error = ""
        try:
            torrent_content = self.gateway.fetch_torrent(
                entry.enclosure_url,
                access,
            )
        except Exception as error:
            fetch_error = str(error)
        hash_candidates = torrent_hash_candidates(torrent_content)
        content_keys = [f"{downloader}:{item}" for item in hash_candidates]
        known_content = self.store.find_rss_content_keys(content_keys)
        if known_content:
            content_key = sorted(known_content)[0]
            return {
                "status": "content_duplicate",
                "reason": "相同 info-hash 已存在于 RSS 历史",
                "content_key": content_key,
                "info_hash": content_key.split(":", 1)[-1],
                "mode": "history",
            }
        existing_hash = self.gateway.find_existing(server, hash_candidates)
        if existing_hash:
            return {
                "status": "existing",
                "reason": "qBittorrent 中已存在相同 info-hash",
                "content_key": f"{downloader}:{existing_hash}",
                "info_hash": existing_hash,
                "mode": "qb_existing",
            }

        prefer_file = bool(config.get("push_torrent_file"))
        modes = ["file", "url"] if prefer_file else ["url", "file"]
        errors: List[str] = []
        for mode in modes:
            if stop_event and stop_event.is_set():
                raise RssExecutionCancelled()
            if mode == "file" and not torrent_content:
                errors.append(fetch_error or "无法取得种子文件")
                continue
            content = torrent_content if mode == "file" else entry.enclosure_url
            for attempt in range(4):
                if stop_event and stop_event.is_set():
                    raise RssExecutionCancelled()
                outcome = self.gateway.add_torrent(
                    server,
                    content=content,
                    mode=mode,
                    save_path=str(config.get("save_path") or "").strip(),
                    category=category,
                    paused=bool(config.get("pause_on_add")),
                    cookie=access.cookie,
                    hash_candidates=hash_candidates,
                )
                if outcome.success and outcome.info_hash:
                    info_hash = outcome.info_hash.lower()
                    if outcome.existing:
                        return {
                            "status": "existing",
                            "reason": "qBittorrent 中已存在相同种子",
                            "content_key": f"{downloader}:{info_hash}",
                            "info_hash": info_hash,
                            "mode": mode,
                        }
                    limit_ok = self.gateway.set_upload_limit(
                        server,
                        info_hash,
                        int(config.get("upload_limit_kbps") or 0),
                    )
                    base_rename = self.renamer.apply(
                        server,
                        info_hash,
                        rss_title=str(prepared.get("title") or entry.title or ""),
                        rename_enabled=bool(config.get("rename_enabled")),
                        rename_rules=config.get("rename_rules") or "",
                        add_chinese_title=bool(config.get("add_chinese_title")),
                    )
                    site_labels: Dict[str, Any] = {}
                    marker_rename: Dict[str, Any] = {}
                    if base_rename.get("status") != "failed":
                        requested_cn = bool(config.get("recognize_cn"))
                        requested_fx = bool(config.get("recognize_fx"))
                        media_category = ""
                        allow_cn = requested_cn
                        if requested_cn:
                            media_category = self._resolve_media_category(
                                _recognition_title_after_rename(
                                    base_rename,
                                    str(prepared.get("title") or entry.title or ""),
                                )
                            )
                            allow_cn = _allows_mandarin_category(media_category)
                        if not requested_cn and not requested_fx:
                            site_labels = self.label_service.detect(
                                access=access,
                                title=str(prepared.get("title") or entry.title or ""),
                                detail_url=str(entry.detail_url or ""),
                                torrent_id=str(prepared.get("torrent_id") or ""),
                                cn_keywords=config.get("cn_keywords") or "",
                                recognize_cn=False,
                                recognize_fx=False,
                            )
                        elif allow_cn or requested_fx:
                            site_labels = self.label_service.detect(
                                access=access,
                                title=str(prepared.get("title") or entry.title or ""),
                                detail_url=str(entry.detail_url or ""),
                                torrent_id=str(prepared.get("torrent_id") or ""),
                                cn_keywords=config.get("cn_keywords") or "",
                                recognize_cn=allow_cn,
                                recognize_fx=requested_fx,
                            )
                        else:
                            site_labels = {
                                "requested": True,
                                "status": "skipped",
                                "site_kind": "",
                                "mandarin": False,
                                "effects": False,
                                "torrent_id": str(
                                    prepared.get("torrent_id") or ""
                                ).strip(),
                                "request_url_masked": "",
                                "reason": (
                                    f"媒体分类“{media_category}”不检查国语标签"
                                ),
                            }
                        if requested_cn:
                            site_labels["media_category"] = media_category
                            site_labels["mandarin_allowed"] = allow_cn
                            if not allow_cn and requested_fx:
                                site_labels["mandarin_skip_reason"] = (
                                    f"媒体分类“{media_category}”不检查国语标签"
                                )
                        if site_labels.get("mandarin") or site_labels.get("effects"):
                            marker_rename = self.renamer.apply(
                                server,
                                info_hash,
                                rss_title="",
                                rename_enabled=False,
                                rename_rules="",
                                add_chinese_title=False,
                                add_cn=bool(site_labels.get("mandarin")),
                                add_fx=bool(site_labels.get("effects")),
                            )
                    source_rename = _merge_source_processing(
                        base_rename,
                        site_labels,
                        marker_rename,
                    )
                    warnings = []
                    if not limit_ok:
                        warnings.append("上传限速设置失败")
                    if source_rename.get("status") == "failed":
                        warnings.append(
                            "qB 源名称处理失败："
                            f"{source_rename.get('error') or '未知错误'}"
                        )
                    if site_labels.get("status") == "failed":
                        warnings.append(
                            "站点标签识别已跳过："
                            f"{site_labels.get('reason') or '未知错误'}"
                        )
                    status = "queued_warning" if warnings else "queued"
                    reason = "种子已加入 qBittorrent"
                    if warnings:
                        reason = f"{reason}，但{'；'.join(warnings)}"
                    return {
                        "status": status,
                        "reason": reason,
                        "content_key": f"{downloader}:{info_hash}",
                        "info_hash": info_hash,
                        "mode": mode,
                        "source_rename": source_rename,
                        "site_labels": site_labels,
                    }
                errors.append(outcome.reason or f"{mode} 模式添加失败")
                existing_hash = self.gateway.find_existing(server, hash_candidates)
                if existing_hash:
                    return {
                        "status": "existing",
                        "reason": "qBittorrent 中已存在相同种子",
                        "content_key": f"{downloader}:{existing_hash}",
                        "info_hash": existing_hash,
                        "mode": mode,
                    }
                if attempt < len(RETRY_DELAYS):
                    delay = RETRY_DELAYS[attempt]
                    if stop_event:
                        if stop_event.wait(delay):
                            raise RssExecutionCancelled()
                    else:
                        self.sleeper(delay)
        raise RssExecutionError("；".join(dict.fromkeys(errors))[:500])

    def _resolve_media_category(self, title: str) -> str:
        try:
            return str(self.media_category_resolver(title) or "").strip()
        except Exception as error:
            self._log(
                "warning",
                f"RSS一条龙：MoviePilot 分类预识别失败，将按未识别处理：{error}",
            )
            return ""

    @staticmethod
    def _moviepilot_media_category(title: str) -> str:
        from .qb_sync import MoviePilotQbGateway

        _meta, media = MoviePilotQbGateway.recognize(str(title or ""))
        return str(getattr(media, "category", "") or "").strip() if media else ""

    def _save_history(
        self,
        *,
        task_id: str,
        prepared: Dict[str, Any],
        status: str,
        reason: str,
        content_key: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = utc_now()
        self.store.upsert_rss_history({
            "task_id": task_id,
            "source_key": prepared.get("source_key") or "",
            "content_key": content_key,
            "title": prepared.get("title") or "",
            "status": status,
            "reason": reason,
            "detail_url_masked": prepared.get("detail_url_masked") or "",
            "payload": {
                **(payload or {}),
                "torrent_id": prepared.get("torrent_id") or "",
                "identity_type": prepared.get("identity_type") or "",
                "published": prepared.get("published") or "",
                "enclosure_url_masked": prepared.get("enclosure_url_masked") or "",
            },
            "updated_at": now,
        })

    def _log(self, level: str, message: str) -> None:
        callback = getattr(self.logger, level, None) if self.logger else None
        if callable(callback):
            callback(message)


def _merge_source_processing(
    base_rename: Dict[str, Any],
    site_labels: Dict[str, Any],
    marker_rename: Dict[str, Any],
) -> Dict[str, Any]:
    base = dict(base_rename or {})
    markers = dict(marker_rename or {})
    statuses = [
        str(item.get("status") or "")
        for item in (base, markers)
        if item
    ]
    status = (
        "failed" if "failed" in statuses
        else "renamed" if "renamed" in statuses
        else "unchanged" if "unchanged" in statuses
        else "skipped"
    )
    errors = [
        str(item.get("error") or "").strip()
        for item in (base, markers)
        if str(item.get("error") or "").strip()
    ]
    final_files = (
        markers.get("final_files")
        if markers.get("final_files") is not None
        else base.get("final_files") or []
    )
    return {
        **base,
        "status": status,
        "error": "；".join(errors)[:500],
        "final_files": list(final_files or []),
        "base_rename": base,
        "site_labels": dict(site_labels or {}),
        "marker_rename": markers,
    }


def _allows_mandarin_category(category: object) -> bool:
    return str(category or "").strip() in MANDARIN_MEDIA_CATEGORIES


def _recognition_title_after_rename(
    rename_result: Dict[str, Any],
    fallback: str,
) -> str:
    paths = [
        str(item.get("name") or "").strip().replace("\\", "/")
        for item in list(rename_result.get("final_files") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    top_levels = {
        path.split("/", 1)[0].strip()
        for path in paths
        if "/" in path and path.split("/", 1)[0].strip()
    }
    if len(top_levels) == 1:
        return next(iter(top_levels))
    if len(paths) == 1:
        return paths[0].rsplit("/", 1)[-1]
    return str(fallback or "").strip()


def torrent_hash_candidates(content: bytes) -> List[str]:
    """Return v1 and v2 candidates from the exact bencoded info dictionary."""
    raw = bytes(content or b"")
    try:
        start, end = _find_info_slice(raw)
    except (TypeError, ValueError):
        return []
    info = raw[start:end]
    return [
        hashlib.sha1(info).hexdigest(),
        hashlib.sha256(info).hexdigest(),
    ]


def _find_info_slice(data: bytes) -> Tuple[int, int]:
    if not data or data[:1] != b"d":
        raise ValueError("torrent root is not a dictionary")
    position = 1
    while position < len(data) and data[position:position + 1] != b"e":
        key, position = _read_bencoded_bytes(data, position)
        value_start = position
        value_end = _skip_bencoded(data, position, 0)
        if key == b"info":
            return value_start, value_end
        position = value_end
    raise ValueError("torrent info dictionary is missing")


def _read_bencoded_bytes(data: bytes, position: int) -> Tuple[bytes, int]:
    colon = data.find(b":", position)
    if colon <= position:
        raise ValueError("invalid bencoded byte string")
    length_bytes = data[position:colon]
    if not length_bytes.isdigit():
        raise ValueError("invalid bencoded byte string length")
    length = int(length_bytes)
    start = colon + 1
    end = start + length
    if end > len(data):
        raise ValueError("truncated bencoded byte string")
    return data[start:end], end


def _skip_bencoded(data: bytes, position: int, depth: int) -> int:
    if depth > 100 or position >= len(data):
        raise ValueError("invalid bencoded structure")
    token = data[position:position + 1]
    if token.isdigit():
        _value, end = _read_bencoded_bytes(data, position)
        return end
    if token == b"i":
        end = data.find(b"e", position + 1)
        if end < 0:
            raise ValueError("truncated bencoded integer")
        number = data[position + 1:end]
        if not number or number in {b"-0", b"+0"}:
            raise ValueError("invalid bencoded integer")
        int(number)
        return end + 1
    if token == b"l":
        position += 1
        while position < len(data) and data[position:position + 1] != b"e":
            position = _skip_bencoded(data, position, depth + 1)
        if position >= len(data):
            raise ValueError("truncated bencoded list")
        return position + 1
    if token == b"d":
        position += 1
        while position < len(data) and data[position:position + 1] != b"e":
            _key, position = _read_bencoded_bytes(data, position)
            position = _skip_bencoded(data, position, depth + 1)
        if position >= len(data):
            raise ValueError("truncated bencoded dictionary")
        return position + 1
    raise ValueError("unknown bencoded token")
