"""Local directory browsing and MoviePilot-backed batch recognition."""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .database import SQLiteStore, utc_now
from .inventory import LocalInventoryChecker, inventory_title_for_tmdb_folder
from .layout import LibraryLayout
from .qb_sync import (
    MoviePilotQbGateway,
    build_source_target_mappings,
    preserve_refresh_workflow_state,
)


FALLBACK_MEDIA_EXTENSIONS = {
    ".avi", ".iso", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".rmvb", ".ts",
}
FILE_BATCH_TASK_TYPE = "file_batch_recognition"


class FileManagerError(RuntimeError):
    """Raised when a local browse or recognition request is unsafe."""


class LocalFileManagerService:
    """Browse local folders and turn one selected folder into one media card."""

    SOURCE_DOWNLOADER = "FILE"

    def __init__(
        self,
        store: SQLiteStore,
        *,
        gateway: Optional[MoviePilotQbGateway] = None,
        inventory_checker: Optional[LocalInventoryChecker] = None,
        library_layout: Optional[LibraryLayout] = None,
        logger: Any = None,
    ):
        self.store = store
        self.gateway = gateway or MoviePilotQbGateway()
        self.inventory_checker = inventory_checker or LocalInventoryChecker([])
        self.library_layout = library_layout or LibraryLayout("", [])
        self.logger = logger

    @staticmethod
    def browse(
        path: object = "/",
        source_roots: Sequence[object] = (),
    ) -> Dict[str, Any]:
        roots = _accessible_source_roots(source_roots)
        raw = str(path or "/").strip() or "/"
        if roots and raw == "/":
            return {
                "path": "/",
                "parent": "",
                "items": [
                    {"name": item.name, "path": str(item), "type": "dir"}
                    for item in roots
                ],
                "total": len(roots),
            }
        directory = _local_directory(path)
        if roots and not _inside_any(directory, roots):
            raise FileManagerError("只能浏览已配置的源路径路由")
        try:
            entries = sorted(
                (
                    item for item in directory.iterdir()
                    if item.is_dir() or item.is_file()
                ),
                key=lambda item: (not item.is_dir(), item.name.casefold()),
            )
        except OSError as error:
            raise FileManagerError(f"目录读取失败：{error}") from error
        parent = directory.parent if directory.parent != directory else None
        if roots and directory in roots:
            parent = Path("/")
        return {
            "path": str(directory),
            "parent": str(parent) if parent else "",
            "items": [
                {
                    "name": item.name,
                    "path": str(item.resolve(strict=False)),
                    "type": "dir" if item.is_dir() else "file",
                }
                for item in entries
            ],
            "total": len(entries),
        }

    def browse_sources(self, path: object = "/") -> Dict[str, Any]:
        return self.browse(path, self._source_roots())

    def recognize_folder(
        self,
        path: object,
        *,
        manual_override: Optional[Dict[str, Any]] = None,
        refresh_media_id: object = "",
        task_id: object = "",
        task_name: object = "文件管理",
        site_id: object = "",
        recognize_cn: bool = False,
        recognize_fx: bool = False,
        cn_keywords: object = "国语,国配",
        query_interval: object = 60,
        rename_rules: object = "",
    ) -> Dict[str, Any]:
        source = _local_entry(path)
        if not source.is_dir():
            raise FileManagerError("所选项目不是文件夹")
        return self.recognize_entry(
            source,
            manual_override=manual_override,
            refresh_media_id=refresh_media_id,
            task_id=task_id,
            task_name=task_name,
            site_id=site_id,
            recognize_cn=recognize_cn,
            recognize_fx=recognize_fx,
            cn_keywords=cn_keywords,
            query_interval=query_interval,
            rename_rules=rename_rules,
        )

    def recognize_entry(
        self,
        path: object,
        *,
        stop_event: Optional[threading.Event] = None,
        manual_override: Optional[Dict[str, Any]] = None,
        refresh_media_id: object = "",
        task_id: object = "",
        task_name: object = "文件管理",
        site_id: object = "",
        recognize_cn: bool = False,
        recognize_fx: bool = False,
        cn_keywords: object = "国语,国配",
        query_interval: object = 60,
        rename_rules: object = "",
        site_search_title: object = "",
    ) -> Dict[str, Any]:
        if stop_event and stop_event.is_set():
            raise FileManagerError("手动添加处理已停止")
        source = _local_entry(path)
        roots = self._source_roots()
        if roots and not _inside_any(source, roots):
            raise FileManagerError("只能识别已配置的源路径路由中的项目")
        if source.is_dir():
            files = self._media_files(source)
            recursive = True
            source_kind = "local_folder"
        else:
            if not _is_media_file(source):
                raise FileManagerError("所选文件不是 MoviePilot 支持的媒体文件")
            files = [source.resolve(strict=True)]
            recursive = False
            source_kind = "local_file"
        if not files:
            raise FileManagerError("所选项目中没有可识别的媒体文件")
        site_search_name = str(site_search_title or "").strip() or (
            source.name
        )
        if str(rename_rules or "").strip():
            files = self._rename_local_files(files, rename_rules)
            if source.is_dir():
                old_source = source
                source = self._rename_local_directory(source, rename_rules)
                files = [
                    source / item.relative_to(old_source)
                    for item in files
                ]
            elif files:
                source = files[0]
        return self._recognize_source(
            source=source,
            files=files,
            recursive=recursive,
            source_kind=source_kind,
            manual_override=manual_override,
            refresh_media_id=refresh_media_id,
            task_id=task_id,
            task_name=task_name,
            site_id=site_id,
            recognize_cn=recognize_cn,
            recognize_fx=recognize_fx,
            cn_keywords=cn_keywords,
            query_interval=query_interval,
            rename_rules=rename_rules,
            site_search_title=site_search_name,
            stop_event=stop_event,
        )

    def recognize_current_directory(
        self,
        path: object,
        *,
        progress: Any = None,
        stop_event: Optional[threading.Event] = None,
        max_items: Optional[int] = None,
        task_id: object = "",
        task_name: object = "文件管理",
        site_id: object = "",
        recognize_cn: bool = False,
        recognize_fx: bool = False,
        cn_keywords: object = "国语,国配",
        query_interval: object = 60,
        rename_rules: object = "",
    ) -> Dict[str, Any]:
        directory = _local_directory(path)
        roots = self._source_roots()
        if roots and not _inside_any(directory, roots):
            raise FileManagerError("只能批量识别已配置的源路径路由")
        try:
            candidates = sorted(
                (
                    item.resolve(strict=True)
                    for item in directory.iterdir()
                    if item.is_dir() or _is_media_file(item)
                ),
                key=lambda item: (not item.is_dir(), item.name.casefold()),
            )
        except OSError as error:
            raise FileManagerError(f"目录读取失败：{error}") from error
        if not candidates:
            raise FileManagerError("当前目录没有可批量识别的文件夹或媒体文件")

        results = []
        succeeded = duplicate = failed = 0
        cancelled = False
        handled = 0
        examined = 0
        item_limit = max(0, int(max_items or 0))
        for index, candidate in enumerate(candidates, start=1):
            if stop_event and stop_event.is_set():
                cancelled = True
                break
            examined = index
            if callable(progress):
                progress(candidate.name, index - 1, succeeded + duplicate, failed, len(candidates))
            try:
                result = self.recognize_entry(
                    candidate,
                    stop_event=stop_event,
                    task_id=task_id,
                    task_name=task_name,
                    site_id=site_id,
                    recognize_cn=recognize_cn,
                    recognize_fx=recognize_fx,
                    cn_keywords=cn_keywords,
                    query_interval=query_interval,
                    rename_rules=rename_rules,
                    site_search_title=candidate.name,
                )
                results.append({"path": str(candidate), **result})
                if result.get("duplicate"):
                    duplicate += 1
                else:
                    succeeded += 1
                    handled += 1
            except Exception as error:
                if stop_event and stop_event.is_set():
                    cancelled = True
                    break
                failed += 1
                handled += 1
                results.append({
                    "path": str(candidate),
                    "success": False,
                    "message": str(error),
                })
            if callable(progress):
                progress(candidate.name, index, succeeded + duplicate, failed, len(candidates))
            if stop_event and stop_event.is_set():
                cancelled = True
                break
            if item_limit and handled >= item_limit:
                break
        exhausted = not cancelled and examined >= len(candidates)
        return {
            "success": failed == 0 and not cancelled,
            "cancelled": cancelled,
            "partial": bool((failed or cancelled) and (succeeded or duplicate)),
            "path": str(directory),
            "total": len(candidates),
            "succeeded": succeeded,
            "duplicate": duplicate,
            "failed": failed,
            "handled": handled,
            "exhausted": exhausted,
            "limit_reached": bool(item_limit and handled >= item_limit),
            "results": results,
            "message": (
                (
                    f"批量识别已停止：新增或更新 {succeeded} 项，"
                    f"已存在 {duplicate} 项，失败 {failed} 项"
                )
                if cancelled else
                (
                    f"批量识别完成：新增或更新 {succeeded} 项，"
                    f"已存在 {duplicate} 项，失败 {failed} 项"
                )
            ),
        }

    def _recognize_source(
        self,
        *,
        source: Path,
        files: Sequence[Path],
        recursive: bool,
        source_kind: str,
        manual_override: Optional[Dict[str, Any]],
        refresh_media_id: object,
        task_id: object = "",
        task_name: object = "文件管理",
        site_id: object = "",
        recognize_cn: bool = False,
        recognize_fx: bool = False,
        cn_keywords: object = "国语,国配",
        query_interval: object = 60,
        rename_rules: object = "",
        site_search_title: object = "",
        stop_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        if stop_event and stop_event.is_set():
            raise FileManagerError("手动添加处理已停止")
        media_id, source_hash = _source_identity(source)
        requested_media_id = str(refresh_media_id or "").strip()
        if requested_media_id and requested_media_id != media_id:
            raise FileManagerError("刷新记录与当前源项目身份不一致")

        existing = self.store.find_media_by_source_path(str(source))
        if existing and not requested_media_id:
            return self._duplicate_result(existing, "源项目已经在入库管理中")

        source_paths = [str(item.resolve(strict=True)) for item in files]
        owners = self.store.find_media_owners_by_source_paths(
            source_paths,
            exclude_media_id=media_id if requested_media_id else "",
        )
        if owners and not requested_media_id:
            owner = self.store.get_media_item(owners[0]) or {"id": owners[0]}
            return self._duplicate_result(owner, "源文件已经属于入库管理卡片")

        override = _normalize_override(manual_override)
        title = source.name
        if override.get("media_type") and override.get("tmdb_id"):
            meta, media = self.gateway.recognize_manual(
                title,
                override["media_type"],
                override["tmdb_id"],
                override.get("season"),
            )
        else:
            meta, media = self.gateway.recognize(title)

        now = utc_now()
        total_size = sum(item.stat().st_size for item in files)
        torrent_files = [
            {
                "index": index,
                "name": (
                    item.relative_to(source).as_posix()
                    if source.is_dir()
                    else item.name
                ),
                "size": item.stat().st_size,
                "priority": 1,
            }
            for index, item in enumerate(files)
        ]
        details: Dict[str, Any] = {
            "torrent": {
                "name": title,
                "content_path": str(source),
                "size": total_size,
            },
            "file_browser": {
                "path": str(source),
                "scanned_at": now,
                "recursive": recursive,
            },
            "manual_override": override,
            "source_identity": {
                "kind": source_kind,
                "source_path": str(source),
                "deletion_scope": "persisted_file_mappings_only",
            },
            "import_control": {
                "task_id": str(task_id or "").strip(),
                "task_name": str(task_name or "文件管理").strip(),
                "import_enabled": True,
                "torrent_completed": True,
            },
        }

        if site_id and (recognize_cn or recognize_fx):
            try:
                from .rss_execute import MoviePilotRssGateway
                from .rss_site_labels import SiteLabelService
                access = MoviePilotRssGateway.site_access(site_id)
                labels = SiteLabelService(
                    MoviePilotRssGateway(),
                    sleeper=(
                        lambda seconds: _interruptible_wait(stop_event, seconds)
                    ),
                    logger=self.logger,
                    min_request_interval_seconds=query_interval,
                ).detect(
                    access=access,
                    title=str(site_search_title or title),
                    detail_url="",
                    torrent_id="",
                    cn_keywords=cn_keywords,
                    recognize_cn=recognize_cn,
                    recognize_fx=recognize_fx,
                    allow_search_without_detail=True,
                )
                if stop_event and stop_event.is_set():
                    raise FileManagerError("手动添加处理已停止")
                details["site_labels"] = labels
                details["rss_source"] = {
                    "task_id": str(task_id or "").strip(),
                    "task_name": str(task_name or "").strip(),
                    "detail_url_masked": str(labels.get("request_url_masked") or ""),
                }
            except Exception as error:
                if stop_event and stop_event.is_set():
                    raise FileManagerError("手动添加处理已停止") from error
                details["site_labels"] = {
                    "status": "failed",
                    "reason": str(error)[:500],
                }

        media_type = ""
        media_title = ""
        recognized_media_title = ""
        inventory_title = ""
        tmdb_id = None
        season = override.get("season")
        category = str(override.get("category") or "").strip()
        target_name = ""
        failure_code = ""
        failure_message = ""
        state = "unidentified"
        mappings: List[Dict[str, Any]] = []

        if media:
            media_type = self.gateway.media_type(media)
            media_title = str(getattr(media, "title", "") or "")
            recognized_media_title = media_title
            tmdb_id = getattr(media, "tmdb_id", None)
            season = getattr(media, "season", None)
            if season is None:
                season = getattr(meta, "begin_season", None)
            automatic_category = str(getattr(media, "category", "") or "")
            category = str(override.get("category") or automatic_category).strip()
            details["automatic_category"] = automatic_category
            details["media"] = self.gateway.media_payload(media)
            details["meta"] = self.gateway.meta_payload(meta)
            if _positive_int(tmdb_id):
                inventory_plan = self.gateway.plan_inventory_files(
                    media,
                    torrent_files,
                    torrent_meta=meta,
                )
                path_plan = self.library_layout.plan(
                    source_path=str(source),
                    category=category,
                    expected_files=inventory_plan.get("expected_files") or [],
                    media_type=media_type,
                )
                folder = self.inventory_checker.locate_root(
                    path_plan.get("inventory_base") or "",
                    tmdb_id,
                    inventory_plan.get("expected_directory") or "",
                )
                inventory_title = inventory_title_for_tmdb_folder(folder)
                if (
                    folder.status == "exists"
                    and inventory_title
                    and inventory_title.casefold() != media_title.casefold()
                ):
                    inventory_plan = self.gateway.plan_inventory_files(
                        media,
                        torrent_files,
                        title_override=inventory_title,
                        torrent_meta=meta,
                    )
                    path_plan = self.library_layout.plan(
                        source_path=str(source),
                        category=category,
                        expected_files=inventory_plan.get("expected_files") or [],
                        media_type=media_type,
                    )
                inventory_state, inventory = self.inventory_checker.check_root(
                    path_plan.get("inventory_base") or "",
                    inventory_plan.get("expected_files") or [],
                    tmdb_id=tmdb_id,
                    expected_directory=inventory_plan.get("expected_directory") or "",
                    media_title=inventory_title or media_title,
                    alternate_titles=[recognized_media_title],
                    folder=folder,
                    plan_errors=inventory_plan.get("plan_errors") or [],
                    total_files=inventory_plan.get("total_files"),
                )
                inventory["category"] = path_plan.get("category") or category
                inventory["group"] = path_plan.get("group") or ""
                inventory["layout_errors"] = path_plan.get("errors") or []
                if inventory_title:
                    media_title = inventory_title
                    media_payload = details.get("media") or {}
                    if isinstance(media_payload, dict):
                        details["media"] = {**media_payload, "title": media_title}
                mappings = build_source_target_mappings(
                    downloader_id=self.SOURCE_DOWNLOADER,
                    info_hash=source_hash,
                    media_id=media_id,
                    torrent={"content_path": str(source)},
                    expected_files=inventory_plan.get("expected_files") or [],
                    path_plan=path_plan,
                    inventory_details=inventory,
                )
                details.update({
                    "inventory_plan": inventory_plan,
                    "path_plan": path_plan,
                    "inventory": inventory,
                    "file_mappings": mappings,
                })
                target_name = str(
                    (path_plan.get("inventory_files") or [{}])[0].get("path") or ""
                )
                if not target_name:
                    target_name = str(inventory_plan.get("inventory_target_name") or "")
                state = "existing" if inventory_state == "exists" else "identified"
            else:
                failure_code = "missing_tmdb_id"
                failure_message = "MoviePilot 未返回有效 TMDB ID"
        else:
            details["media"] = {}
            details["meta"] = self.gateway.meta_payload(meta)
            failure_code = "recognition_failed"
            failure_message = "MoviePilot 未识别到可靠媒体信息"

        details["recognized_title"] = recognized_media_title
        details["inventory_title"] = inventory_title
        previous = self.store.get_media_item(media_id) or existing or {}
        state = preserve_refresh_workflow_state(previous.get("state"), state)
        self.store.upsert_media_item({
            "id": media_id,
            "state": state,
            "media_type": media_type,
            "title": media_title or title,
            "source_name": title,
            "source_path": str(source),
            "downloader_id": self.SOURCE_DOWNLOADER,
            "info_hash": source_hash,
            "tmdb_id": tmdb_id,
            "season": season,
            "category": category,
            "target_name": target_name,
            "failure_code": failure_code,
            "failure_message": failure_message,
            "rolled_back": bool(previous.get("rolled_back")),
            "details": details,
            "created_at": previous.get("created_at") or now,
            "updated_at": now,
        })
        persisted = self.store.replace_file_mappings(
            self.SOURCE_DOWNLOADER,
            source_hash,
            mappings,
        )
        details["file_mappings"] = persisted
        item = self.store.get_media_item(media_id) or {}
        item["details"] = details
        self.store.upsert_media_item(item)
        return {
            "success": True,
            "duplicate": False,
            "media_id": media_id,
            "state": state,
            "item": self.store.get_media_item(media_id),
            "message": "识别完成，已更新入库管理卡片",
        }

    @staticmethod
    def _rename_local_files(files: Sequence[Path], rules_text: object) -> List[Path]:
        from .rss_rename import parse_rename_rules, transform_name
        rules = parse_rename_rules(rules_text)
        renamed: List[Path] = []
        for file_path in files:
            current = Path(file_path)
            new_name = transform_name(
                current.name,
                is_file=True,
                rules=rules,
            )
            if new_name == current.name:
                renamed.append(current)
                continue
            target = current.with_name(new_name)
            if target.exists() and target.resolve() != current.resolve():
                raise FileManagerError(f"本地重命名目标已存在：{target}")
            current.rename(target)
            renamed.append(target.resolve(strict=True))
        return renamed

    @staticmethod
    def _rename_local_directory(directory: Path, rules_text: object) -> Path:
        from .rss_rename import parse_rename_rules, transform_name
        rules = parse_rename_rules(rules_text)
        current = Path(directory)
        new_name = transform_name(
            current.name,
            is_file=False,
            rules=rules,
        )
        if new_name == current.name:
            return current
        target = current.with_name(new_name)
        if target.exists() and target.resolve() != current.resolve():
            raise FileManagerError(f"本地重命名目标已存在：{target}")
        current.rename(target)
        return target.resolve(strict=True)

    @staticmethod
    def _duplicate_result(item: Dict[str, Any], reason: str) -> Dict[str, Any]:
        return {
            "success": True,
            "duplicate": True,
            "media_id": str(item.get("id") or ""),
            "state": str(item.get("state") or ""),
            "item": item,
            "message": f"{reason}，已跳过重复识别",
        }

    @staticmethod
    def _media_files(directory: Path) -> List[Path]:
        extensions = _moviepilot_media_extensions()
        result = []
        try:
            for item in directory.rglob("*"):
                if not item.is_file() or item.suffix.casefold() not in extensions:
                    continue
                lowered = {part.casefold() for part in item.relative_to(directory).parts}
                if "sample" in lowered or "sample" in item.stem.casefold():
                    continue
                result.append(item.resolve(strict=True))
        except OSError as error:
            raise FileManagerError(f"扫描媒体文件失败：{error}") from error
        return sorted(result, key=lambda item: str(item).casefold())

    def _source_roots(self) -> List[Path]:
        return _accessible_source_roots(
            route.prefix for route in self.library_layout.routes if route.enabled
        )


def _local_directory(value: object) -> Path:
    raw = str(value or "/").strip() or "/"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise FileManagerError("目录必须是绝对路径")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise FileManagerError(f"目录不存在或不可访问：{raw}") from error
    if not resolved.is_dir():
        raise FileManagerError(f"路径不是文件夹：{resolved}")
    return resolved


def _local_entry(value: object) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise FileManagerError("缺少要识别的文件或文件夹")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise FileManagerError("路径必须是绝对路径")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise FileManagerError(f"路径不存在或不可访问：{raw}") from error
    if not resolved.is_dir() and not resolved.is_file():
        raise FileManagerError(f"路径不是普通文件或文件夹：{resolved}")
    return resolved


def _is_media_file(path: Path) -> bool:
    if not path.is_file() or path.suffix.casefold() not in _moviepilot_media_extensions():
        return False
    return "sample" not in path.stem.casefold()


def _accessible_source_roots(values: Iterable[object]) -> List[Path]:
    roots = []
    seen = set()
    for value in values or []:
        try:
            path = _local_directory(value)
        except FileManagerError:
            continue
        identity = os.path.normcase(os.path.normpath(str(path)))
        if identity not in seen:
            seen.add(identity)
            roots.append(path)
    return sorted(roots, key=lambda item: item.name.casefold())


def _inside_any(path: Path, roots: Sequence[Path]) -> bool:
    identity = os.path.normcase(os.path.normpath(str(path)))
    for root in roots:
        root_identity = os.path.normcase(os.path.normpath(str(root)))
        try:
            if os.path.commonpath([identity, root_identity]) == root_identity:
                return True
        except ValueError:
            continue
    return False


def _source_identity(path: Path) -> Tuple[str, str]:
    identity = os.path.normcase(os.path.normpath(str(path.resolve(strict=False))))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"file:{digest}", digest


def _interruptible_wait(
    stop_event: Optional[threading.Event], seconds: object
) -> None:
    try:
        timeout = max(0.0, float(seconds or 0))
    except (TypeError, ValueError):
        timeout = 0.0
    waiter = stop_event or threading.Event()
    if waiter.wait(timeout) and stop_event:
        raise FileManagerError("手动添加处理已停止")


def _moviepilot_media_extensions() -> set[str]:
    try:
        from app.core.config import settings

        values: Iterable[object] = settings.RMT_MEDIAEXT
    except Exception:
        return set(FALLBACK_MEDIA_EXTENSIONS)
    result = set()
    for value in values or []:
        extension = str(value or "").strip().casefold()
        if extension:
            result.add(extension if extension.startswith(".") else f".{extension}")
    return result or set(FALLBACK_MEDIA_EXTENSIONS)


def _positive_int(value: object) -> bool:
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        return False


def _normalize_override(value: object) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    media_type = str(raw.get("media_type") or "").strip().casefold()
    if media_type == "series":
        media_type = "tv"
    if media_type not in {"movie", "tv"}:
        media_type = ""
    try:
        tmdb_id = int(raw.get("tmdb_id") or 0)
    except (TypeError, ValueError):
        tmdb_id = 0
    try:
        season = int(raw.get("season") or 0) if media_type == "tv" else None
    except (TypeError, ValueError):
        season = 0 if media_type == "tv" else None
    return {
        "media_type": media_type,
        "tmdb_id": tmdb_id if tmdb_id > 0 else 0,
        "season": max(0, season) if season is not None else None,
        "category": LibraryLayout.canonical_category(
            str(raw.get("category") or "").strip()
        ),
    }
