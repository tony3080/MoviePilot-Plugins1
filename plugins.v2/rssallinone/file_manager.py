"""Local directory browsing and MoviePilot-backed batch recognition."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .database import SQLiteStore, utc_now
from .inventory import LocalInventoryChecker
from .layout import LibraryLayout
from .qb_sync import MoviePilotQbGateway, build_source_target_mappings


FALLBACK_MEDIA_EXTENSIONS = {
    ".avi", ".iso", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".rmvb", ".ts",
}


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
    def browse(path: object = "/") -> Dict[str, Any]:
        directory = _local_directory(path)
        try:
            folders = sorted(
                (item for item in directory.iterdir() if item.is_dir()),
                key=lambda item: item.name.casefold(),
            )
        except OSError as error:
            raise FileManagerError(f"目录读取失败：{error}") from error
        parent = directory.parent if directory.parent != directory else None
        return {
            "path": str(directory),
            "parent": str(parent) if parent else "",
            "items": [
                {"name": item.name, "path": str(item.resolve(strict=False))}
                for item in folders
            ],
            "total": len(folders),
        }

    def recognize_folder(
        self,
        path: object,
        *,
        manual_override: Optional[Dict[str, Any]] = None,
        refresh_media_id: object = "",
    ) -> Dict[str, Any]:
        directory = _local_directory(path)
        media_id, source_hash = _source_identity(directory)
        requested_media_id = str(refresh_media_id or "").strip()
        if requested_media_id and requested_media_id != media_id:
            raise FileManagerError("刷新记录与当前文件夹身份不一致")

        files = self._media_files(directory)
        if not files:
            raise FileManagerError("所选文件夹中没有可识别的媒体文件")

        existing = self.store.find_media_by_source_path(str(directory))
        if existing and not requested_media_id:
            return self._duplicate_result(existing, "文件夹已经在入库管理中")

        source_paths = [str(item.resolve(strict=True)) for item in files]
        owners = self.store.find_media_owners_by_source_paths(
            source_paths,
            exclude_media_id=media_id if requested_media_id else "",
        )
        if owners and not requested_media_id:
            owner = self.store.get_media_item(owners[0]) or {"id": owners[0]}
            return self._duplicate_result(owner, "文件夹中的源文件已经属于入库管理卡片")

        override = _normalize_override(manual_override)
        title = directory.name
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
                "name": item.relative_to(directory).as_posix(),
                "size": item.stat().st_size,
                "priority": 1,
            }
            for index, item in enumerate(files)
        ]
        details: Dict[str, Any] = {
            "torrent": {
                "name": title,
                "content_path": str(directory),
                "size": total_size,
            },
            "file_browser": {
                "path": str(directory),
                "scanned_at": now,
                "recursive": True,
            },
            "manual_override": override,
            "source_identity": {
                "kind": "local_folder",
                "source_path": str(directory),
                "deletion_scope": "persisted_file_mappings_only",
            },
            "import_control": {
                "task_id": "",
                "task_name": "文件管理",
                "import_enabled": True,
                "torrent_completed": True,
            },
        }

        media_type = ""
        media_title = ""
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
                    source_path=str(directory),
                    category=category,
                    expected_files=inventory_plan.get("expected_files") or [],
                    media_type=media_type,
                )
                folder = self.inventory_checker.locate_root(
                    path_plan.get("inventory_base") or "",
                    tmdb_id,
                    inventory_plan.get("expected_directory") or "",
                )
                inventory_title = str(folder.title or "").strip()
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
                        source_path=str(directory),
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
                    folder=folder,
                    plan_errors=inventory_plan.get("plan_errors") or [],
                    total_files=inventory_plan.get("total_files"),
                )
                inventory["category"] = path_plan.get("category") or category
                inventory["group"] = path_plan.get("group") or ""
                inventory["layout_errors"] = path_plan.get("errors") or []
                mappings = build_source_target_mappings(
                    downloader_id=self.SOURCE_DOWNLOADER,
                    info_hash=source_hash,
                    media_id=media_id,
                    torrent={"content_path": str(directory)},
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

        previous = self.store.get_media_item(media_id) or existing or {}
        self.store.upsert_media_item({
            "id": media_id,
            "state": state,
            "media_type": media_type,
            "title": media_title or title,
            "source_name": title,
            "source_path": str(directory),
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


def _source_identity(path: Path) -> Tuple[str, str]:
    identity = os.path.normcase(os.path.normpath(str(path.resolve(strict=False))))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"file:{digest}", digest


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
