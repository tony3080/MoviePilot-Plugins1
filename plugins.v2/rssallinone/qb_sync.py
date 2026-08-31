"""Read-only qBittorrent synchronization through MoviePilot runtime services."""

from __future__ import annotations

import copy
import hashlib
import html
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlencode, urlparse, urlunparse

from .database import SQLiteStore, utc_now
from .inventory import LocalInventoryChecker, inventory_title_for_tmdb_folder
from .layout import LibraryLayout
from .rss_feed import extract_torrent_id, mask_url


QB_TASK_TYPE = "qb_refresh"
QB_DOWNLOADER_KEYS = (
    "qb_downloader",
    "qb_downloader_id",
    "downloader",
    "downloader_id",
)
QB_CATEGORY_KEYS = (
    "qb_category",
    "qbittorrent_category",
    "download_category",
    "category",
)
NAMING_META_FIELDS = (
    "resource_type",
    "resource_effect",
    "resource_pix",
    "resource_team",
    "customization",
    "video_encode",
    "audio_encode",
)
CUSTOMIZATION_EXCLUDED_TOKENS = {
    "中字",
    "字幕",
    "简体",
    "繁体",
    "简中",
    "繁中",
    "内封",
    "双语",
    "中英字幕",
    "简繁字幕",
}
REALTIME_MEDIA_EXTENSIONS = {
    ".avi", ".iso", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".rmvb", ".ts",
}


@dataclass(frozen=True)
class DownloaderView:
    name: str
    type: str
    enabled: bool
    default: bool
    ready: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "enabled": self.enabled,
            "default": self.default,
            "ready": self.ready,
        }


@dataclass(frozen=True)
class RssTaskQbRule:
    task_id: str
    task_name: str
    downloader: str
    category: str
    enabled: bool
    import_enabled: bool
    realtime_hardlink_enabled: bool
    realtime_source_root: str
    realtime_link_root: str
    delete_after_minutes: int
    delete_files: bool
    hr_enabled: bool = False
    site_id: str = ""
    hr_cron: str = ""
    task_type: str = "rss"
    query_interval: int = 60
    rename_rules: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "downloader": self.downloader,
            "category": self.category,
            "enabled": self.enabled,
            "import_enabled": self.import_enabled,
            "realtime_hardlink_enabled": self.realtime_hardlink_enabled,
            "realtime_source_root": self.realtime_source_root,
            "realtime_link_root": self.realtime_link_root,
            "delete_after_minutes": self.delete_after_minutes,
            "delete_files": self.delete_files,
            "hr_enabled": self.hr_enabled,
            "site_id": self.site_id,
            "hr_cron": self.hr_cron,
            "task_type": self.task_type,
            "query_interval": self.query_interval,
            "rename_rules": self.rename_rules,
        }


class RssTaskQbScope:
    """Exact qB downloader/category pairs declared by saved VT+ RSS tasks."""

    def __init__(
        self,
        rules: Sequence[RssTaskQbRule],
        ignored_tasks: Sequence[Dict[str, str]] = (),
    ):
        self.rules = list(rules)
        self.ignored_tasks = list(ignored_tasks)
        self._categories: Dict[str, List[str]] = {}
        for rule in self.rules:
            categories = self._categories.setdefault(rule.downloader, [])
            if rule.category not in categories:
                categories.append(rule.category)

    @classmethod
    def from_tasks(cls, tasks: Iterable[Dict[str, Any]]) -> "RssTaskQbScope":
        rules: List[RssTaskQbRule] = []
        ignored: List[Dict[str, str]] = []
        for index, task in enumerate(tasks or [], start=1):
            task_id = str(task.get("id") or f"task-{index}").strip()
            task_name = str(task.get("name") or task_id).strip()
            config = task.get("config") if isinstance(task.get("config"), dict) else {}
            qb_config = config.get("qb") if isinstance(config.get("qb"), dict) else {}
            sources = (qb_config, config, task)
            downloader = _first_text(sources, QB_DOWNLOADER_KEYS)
            category = _first_text(sources, QB_CATEGORY_KEYS)
            if not downloader or not category:
                missing = []
                if not downloader:
                    missing.append("QB下载器")
                if not category:
                    missing.append("QB分类")
                ignored.append({
                    "task_id": task_id,
                    "task_name": task_name,
                    "reason": f"缺少{'和'.join(missing)}",
                })
                continue
            rules.append(RssTaskQbRule(
                task_id=task_id,
                task_name=task_name,
                downloader=downloader,
                category=category,
                enabled=bool(task.get("enabled")),
                import_enabled=_as_bool(config.get("import_enabled", True)),
                realtime_hardlink_enabled=_as_bool(
                    config.get("realtime_hardlink_enabled", False)
                ),
                realtime_source_root=str(
                    config.get("realtime_source_root") or ""
                ).strip(),
                realtime_link_root=str(
                    config.get("realtime_link_root") or ""
                ).strip(),
                delete_after_minutes=max(
                    0, int(config.get("delete_after_minutes") or 0)
                ),
                delete_files=_as_bool(config.get("delete_files", False)),
                hr_enabled=_as_bool(config.get("hr_enabled", False)),
                site_id=str(config.get("site_id") or "").strip(),
                hr_cron=str(config.get("hr_cron") or "").strip(),
                task_type=str(config.get("task_type") or "rss").strip().casefold(),
                query_interval=_safe_positive_int(config.get("query_interval"), 60),
                rename_rules=str(config.get("rename_rules") or "").strip(),
            ))
        return cls(rules, ignored)

    @property
    def ready(self) -> bool:
        return bool(self.rules)

    def categories_for(self, downloader: str) -> List[str]:
        return list(self._categories.get(str(downloader or "").strip(), []))

    def downloader_categories(self) -> Dict[str, List[str]]:
        return {
            downloader: list(categories)
            for downloader, categories in self._categories.items()
        }

    def matches(self, downloader: str, category: str) -> bool:
        return str(category or "").strip() in self.categories_for(downloader)

    def rule_for(
        self,
        downloader: object,
        category: object,
        task_id: object = "",
        preferred_task_type: object = "",
    ) -> Optional[RssTaskQbRule]:
        normalized_task_id = str(task_id or "").strip()
        if normalized_task_id:
            for rule in self.rules:
                if rule.task_id == normalized_task_id:
                    return rule
        normalized_downloader = str(downloader or "").strip()
        normalized_category = str(category or "").strip()
        matches = [
            rule for rule in self.rules
            if rule.downloader == normalized_downloader
            and rule.category == normalized_category
        ]
        preferred_type = str(preferred_task_type or "").strip().casefold()
        if preferred_type:
            preferred_matches = [
                rule for rule in matches if rule.task_type == preferred_type
            ]
            if len(preferred_matches) == 1:
                return preferred_matches[0]
        if len(matches) == 1:
            return matches[0]
        if matches and len({
            (
                rule.import_enabled,
                rule.realtime_hardlink_enabled,
                rule.realtime_source_root,
                rule.realtime_link_root,
                rule.delete_after_minutes,
                rule.delete_files,
                rule.hr_enabled,
                rule.site_id,
                rule.hr_cron,
            )
            for rule in matches
        }) == 1:
            return matches[0]
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ready": self.ready,
            "downloaders": self.downloader_categories(),
            "rules": [rule.to_dict() for rule in self.rules],
            "ignored_tasks": list(self.ignored_tasks),
        }


class MoviePilotQbGateway:
    """Narrow adapter around MoviePilot downloader, recognition, and naming."""

    @staticmethod
    def list_downloaders() -> List[DownloaderView]:
        from app.helper.downloader import DownloaderHelper

        helper = DownloaderHelper()
        configs = helper.get_configs()
        services = helper.get_services(type_filter="qbittorrent")
        result = []
        for name, config in configs.items():
            if str(config.type or "").casefold() != "qbittorrent":
                continue
            result.append(DownloaderView(
                name=name,
                type="qbittorrent",
                enabled=bool(config.enabled),
                default=bool(config.default),
                ready=name in services,
            ))
        return sorted(result, key=lambda item: (not item.default, item.name.casefold()))

    @staticmethod
    def list_torrents(downloader: str) -> List[Any]:
        from app.chain.download import DownloadChain
        from app.helper.downloader import DownloaderHelper

        service = DownloaderHelper().get_service(
            name=downloader, type_filter="qbittorrent"
        )
        if not service or not service.instance:
            raise RuntimeError(f"qBittorrent 节点不可用：{downloader}")
        torrents = DownloadChain().list_torrents(
            downloader=downloader,
            include_all_tags=True,
        )
        if torrents is None:
            raise RuntimeError(f"读取 qBittorrent 任务失败：{downloader}")
        return list(torrents)

    @staticmethod
    def resume_torrents(downloader: str, info_hashes: Sequence[str]) -> bool:
        """Resume qB tasks through MoviePilot's downloader chain."""
        hashes = [
            str(value or "").strip().lower()
            for value in (info_hashes or [])
            if str(value or "").strip()
        ]
        if not hashes:
            return True
        from app.chain.download import DownloadChain
        from app.helper.downloader import DownloaderHelper

        chain = DownloadChain()
        starter = getattr(chain, "set_downloading", None)
        if callable(starter):
            results = [
                bool(starter(info_hash, "start", downloader))
                for info_hash in hashes
            ]
            return all(results)

        # Compatibility fallback for older MoviePilot downloader wrappers.
        service = DownloaderHelper().get_service(
            name=str(downloader or "").strip(),
            type_filter="qbittorrent",
        )
        server = getattr(service, "instance", None) if service else None
        client = getattr(server, "qbc", None) if server else None
        candidates = [client, server]
        for target in candidates:
            if not target:
                continue
            for method_name in ("torrents_resume", "resume_torrents", "start_torrents"):
                method = getattr(target, method_name, None)
                if not callable(method):
                    continue
                try:
                    method(torrent_hashes=hashes)
                except TypeError:
                    method(hashes)
                return True
        raise RuntimeError(f"qB 节点不支持恢复任务：{downloader}")

    @staticmethod
    def torrent_dict(torrent: Any) -> Dict[str, Any]:
        if hasattr(torrent, "model_dump"):
            return torrent.model_dump(mode="json")
        if isinstance(torrent, dict):
            return dict(torrent)
        return dict(vars(torrent))

    @staticmethod
    def torrent_properties(server: Any, info_hash: str) -> Dict[str, Any]:
        """Read qB per-torrent properties, including the comment URL."""
        normalized = str(info_hash or "").strip().lower()
        if not normalized or not server:
            return {}
        for target in (getattr(server, "qbc", None), server):
            if not target:
                continue
            for method_name in (
                "torrents_properties",
                "get_torrent_properties",
                "torrent_properties",
            ):
                method = getattr(target, method_name, None)
                if not callable(method):
                    continue
                try:
                    value = method(torrent_hash=normalized)
                except TypeError:
                    try:
                        value = method(normalized)
                    except Exception:
                        continue
                except Exception:
                    continue
                if isinstance(value, (list, tuple)):
                    value = value[0] if value else None
                if value:
                    try:
                        return MoviePilotQbGateway.torrent_dict(value)
                    except (TypeError, ValueError):
                        continue
        return {}

    @staticmethod
    def list_torrent_files(downloader: str, info_hash: str) -> List[Any]:
        if not isinstance(downloader, str):
            server = downloader
            try:
                return list(server.get_files(info_hash, retry=6, interval=0.5) or [])
            except Exception as error:
                raise RuntimeError(f"读取 qB 文件列表失败：{error}") from error
        from app.chain.download import DownloadChain

        files = DownloadChain().torrent_files(
            tid=info_hash,
            downloader=downloader,
        )
        if files is None:
            raise RuntimeError(f"读取 qBittorrent 文件清单失败：{downloader}/{info_hash}")
        return list(files)

    @staticmethod
    def rename_torrent_file(server: Any, info_hash: str, old_path: str, new_path: str) -> None:
        server.qbc.torrents_rename_file(
            torrent_hash=info_hash, old_path=old_path, new_path=new_path
        )

    @staticmethod
    def rename_torrent_folder(server: Any, info_hash: str, old_path: str, new_path: str) -> None:
        server.qbc.torrents_rename_folder(
            torrent_hash=info_hash, old_path=old_path, new_path=new_path
        )

    @staticmethod
    def rename_torrent_name(server: Any, info_hash: str, name: str) -> bool:
        """Synchronize qB's display name after manual file/folder renaming."""
        value = str(name or "").strip()
        if not value:
            return False
        for target in (getattr(server, "qbc", None), server):
            if not target:
                continue
            for method_name in (
                "torrents_rename",
                "torrents_rename_name",
                "torrents_set_name",
            ):
                method = getattr(target, method_name, None)
                if not callable(method):
                    continue
                try:
                    method(torrent_hash=info_hash, name=value)
                except TypeError:
                    try:
                        method(info_hash, value)
                    except Exception:
                        continue
                except Exception:
                    continue
                return True
        return False

    @staticmethod
    def get_server(downloader: str) -> Any:
        from app.helper.downloader import DownloaderHelper
        service = DownloaderHelper().get_service(
            name=str(downloader or "").strip(), type_filter="qbittorrent"
        )
        server = getattr(service, "instance", None) if service else None
        if not server:
            raise RuntimeError(f"qBittorrent 节点不可用：{downloader}")
        return server

    @staticmethod
    def remove_torrent(
        downloader: str, info_hash: str, delete_files: bool
    ) -> bool:
        from app.chain.download import DownloadChain

        return bool(DownloadChain().remove_torrents(
            hashs=[str(info_hash or "").strip().lower()],
            downloader=str(downloader or "").strip(),
            delete_file=bool(delete_files),
        ))

    @staticmethod
    def torrent_file_dict(file_item: Any) -> Dict[str, Any]:
        if hasattr(file_item, "model_dump"):
            return file_item.model_dump(mode="json")
        if isinstance(file_item, dict):
            return dict(file_item)
        try:
            return dict(file_item)
        except (TypeError, ValueError):
            return dict(vars(file_item))

    @staticmethod
    def recognize(title: str) -> Tuple[Any, Optional[Any]]:
        from app.chain.media import MediaChain
        from app.core.metainfo import MetaInfo

        meta = MetaInfo(title=title)
        MoviePilotQbGateway.refresh_customization(meta, title)
        media = MediaChain().recognize_by_meta(meta, obtain_images=False)
        return meta, media

    @staticmethod
    def recognize_manual(
        title: str,
        media_type: str,
        tmdb_id: int,
        season: Optional[int] = None,
    ) -> Tuple[Any, Optional[Any]]:
        from app.chain.media import MediaChain
        from app.core.metainfo import MetaInfo
        from app.schemas.types import MediaType

        normalized_type = str(media_type or "").strip().casefold()
        if normalized_type == "movie":
            mtype = MediaType.MOVIE
            normalized_season = None
        elif normalized_type in {"tv", "series"}:
            mtype = MediaType.TV
            normalized_season = int(season or 0)
        else:
            raise ValueError("媒体类型必须是 movie 或 tv")
        normalized_tmdb = int(tmdb_id or 0)
        if normalized_tmdb <= 0:
            raise ValueError("TMDB ID 必须大于 0")

        meta = MetaInfo(title=title)
        meta.type = mtype
        meta.begin_season = normalized_season
        MoviePilotQbGateway.refresh_customization(meta, title)
        media = MediaChain().recognize_media(
            meta=meta,
            mtype=mtype,
            tmdbid=normalized_tmdb,
            cache=False,
        )
        if media and normalized_type != "movie":
            media.season = normalized_season
        return meta, media

    @staticmethod
    def restore_media(payload: Dict[str, Any]) -> Optional[Any]:
        if not payload:
            return None
        from app.core.context import MediaInfo

        data = dict(payload)
        for field in ("seasons", "season_years"):
            value = data.get(field)
            if isinstance(value, dict):
                data[field] = {
                    int(key) if str(key).lstrip("-").isdigit() else key: item
                    for key, item in value.items()
                }
        media = MediaInfo()
        media.from_dict(data)
        return media

    @staticmethod
    def restore_meta(title: str, _payload: Dict[str, Any]) -> Any:
        from app.core.metainfo import MetaInfo

        meta = MetaInfo(title=title)
        MoviePilotQbGateway.refresh_customization(meta, title)
        return meta

    @staticmethod
    def plan_inventory_files(
        media: Any,
        torrent_files: Sequence[Any],
        title_override: str = "",
        torrent_meta: Any = None,
    ) -> Dict[str, Any]:
        """Use the complete MoviePilot naming pipeline for media and STRM paths."""

        from app.core.config import settings
        from app.core import metainfo as metainfo_module
        from app.modules.filemanager import FileManagerModule

        media_type = MoviePilotQbGateway.media_type(media)
        candidates: List[Dict[str, Any]] = []
        ignored: List[Dict[str, str]] = []
        plan_errors: List[Dict[str, str]] = []
        media_extensions = {str(ext).casefold() for ext in settings.RMT_MEDIAEXT}
        for fallback_index, file_item in enumerate(torrent_files):
            raw = MoviePilotQbGateway.torrent_file_dict(file_item)
            name = str(raw.get("name") or raw.get("path") or "").strip()
            source_path = PurePosixPath(name.replace("\\", "/"))
            suffix = source_path.suffix.casefold()
            if not name or suffix not in media_extensions:
                continue
            if str(raw.get("priority", "")).strip() == "0":
                ignored.append({"source_name": name, "reason": "qB 文件未选择下载"})
                continue
            lowered_parts = {part.casefold() for part in source_path.parts}
            if "sample" in lowered_parts or "sample" in source_path.stem.casefold():
                ignored.append({"source_name": name, "reason": "样片文件"})
                continue
            try:
                size = max(0, int(raw.get("size") or 0))
            except (TypeError, ValueError):
                size = 0
            file_index = raw.get("index")
            if file_index is None:
                file_index = raw.get("id")
            try:
                file_index = int(
                    fallback_index if file_index is None else file_index
                )
            except (TypeError, ValueError):
                file_index = fallback_index
            candidates.append({
                "file_index": file_index,
                "source_name": name,
                "size": size,
            })

        if media_type == "movie" and candidates:
            candidates = [max(candidates, key=lambda item: item["size"])]

        naming_media = media
        normalized_title = str(title_override or "").strip()
        if normalized_title:
            if hasattr(media, "model_copy"):
                naming_media = media.model_copy(deep=False)
            else:
                naming_media = copy.copy(media)
            setattr(naming_media, "title", normalized_title)

        expected_files: List[Dict[str, Any]] = []
        seen_paths = set()
        for item in candidates:
            source_name = item["source_name"]
            source_path = Path(source_name.replace("\\", "/"))
            meta_path_class = getattr(metainfo_module, "MetaInfoPath", None)
            if meta_path_class:
                file_meta = meta_path_class(path=source_path)
            else:
                file_meta = metainfo_module.MetaInfo(title=source_path.name)
            MoviePilotQbGateway.refresh_customization(file_meta, source_name)
            inherited_fields = MoviePilotQbGateway.merge_naming_meta(
                file_meta, torrent_meta
            )
            if media_type == "tv":
                season = getattr(file_meta, "begin_season", None)
                episode = getattr(file_meta, "begin_episode", None)
                if season is None:
                    season = getattr(media, "season", None)
                    if season is not None:
                        file_meta.begin_season = season
                if episode is None:
                    plan_errors.append({
                        "source_name": source_name,
                        "reason": "无法从文件名解析集号",
                    })
                    continue
            if getattr(file_meta, "year", None) is None:
                file_meta.year = getattr(media, "year", None)
            relative_path = str(
                FileManagerModule.recommend_name(file_meta, naming_media) or ""
            ).strip().replace("\\", "/")
            pure_path = PurePosixPath(relative_path)
            if not relative_path or pure_path.is_absolute() or ".." in pure_path.parts:
                plan_errors.append({
                    "source_name": source_name,
                    "reason": f"MoviePilot 生成了无效目标路径：{relative_path}",
                })
                continue
            identity = pure_path.as_posix().casefold()
            if identity in seen_paths:
                plan_errors.append({
                    "source_name": source_name,
                    "reason": f"多个源文件生成了相同目标路径：{pure_path.as_posix()}",
                })
                continue
            seen_paths.add(identity)
            inventory_path = (
                pure_path.with_suffix(".strm")
                if pure_path.suffix
                else pure_path.with_name(f"{pure_path.name}.strm")
            )
            expected_files.append({
                "file_index": item["file_index"],
                "source_name": source_name,
                "relative_path": pure_path.as_posix(),
                "new_rel": pure_path.as_posix(),
                "inventory_relative_path": inventory_path.as_posix(),
                "size": item["size"],
                "recognition": {
                    "meta": MoviePilotQbGateway.meta_payload(file_meta),
                    "resource_tokens": MoviePilotQbGateway.resource_tokens(
                        file_meta
                    ),
                    "apply_words": MoviePilotQbGateway.recognition_words(
                        file_meta
                    ),
                    "customization": str(
                        getattr(file_meta, "customization", "") or ""
                    ),
                    "inherited_fields": inherited_fields,
                },
            })

        expected_directory = ""
        if expected_files:
            first_path = PurePosixPath(expected_files[0]["relative_path"])
            if len(first_path.parts) > 1:
                expected_directory = first_path.parts[0]
        return {
            "method": "moviepilot_naming",
            "media_type": media_type,
            "title_override": normalized_title,
            "total_files": len(candidates),
            "expected_files": expected_files,
            "ignored_files": ignored,
            "plan_errors": plan_errors,
            "expected_directory": expected_directory,
            "target_name": expected_files[0]["relative_path"] if expected_files else "",
            "inventory_target_name": (
                expected_files[0]["inventory_relative_path"]
                if expected_files else ""
            ),
        }

    @staticmethod
    def media_payload(media: Any) -> Dict[str, Any]:
        return media.to_dict() if media else {}

    @staticmethod
    def meta_payload(meta: Any) -> Dict[str, Any]:
        if not meta:
            return {}
        to_dict = getattr(meta, "to_dict", None)
        if callable(to_dict):
            payload = to_dict()
            return dict(payload) if isinstance(payload, dict) else {}
        model_dump = getattr(meta, "model_dump", None)
        if callable(model_dump):
            payload = model_dump(mode="json")
            return dict(payload) if isinstance(payload, dict) else {}
        fields = (
            "title",
            "year",
            "begin_season",
            "begin_episode",
            "end_episode",
            *NAMING_META_FIELDS,
            "apply_words",
        )
        return {
            field: getattr(meta, field)
            for field in fields
            if hasattr(meta, field)
        }

    @staticmethod
    def merge_naming_meta(file_meta: Any, torrent_meta: Any) -> List[str]:
        """Fill file-level naming gaps from the already parsed qB task title."""

        if not file_meta or not torrent_meta:
            return []
        inherited = []
        for field in NAMING_META_FIELDS:
            if field == "customization":
                continue
            current = getattr(file_meta, field, None)
            fallback = getattr(torrent_meta, field, None)
            if MoviePilotQbGateway._has_meta_value(current):
                continue
            if not MoviePilotQbGateway._has_meta_value(fallback):
                continue
            setattr(file_meta, field, copy.deepcopy(fallback))
            inherited.append(field)

        file_customization = getattr(file_meta, "customization", None)
        torrent_customization = getattr(torrent_meta, "customization", None)
        merged_customization = MoviePilotQbGateway.merge_customizations(
            torrent_customization,
            file_customization,
        )
        if merged_customization and merged_customization != file_customization:
            setattr(file_meta, "customization", merged_customization)
            inherited.append("customization")

        current_words = list(getattr(file_meta, "apply_words", None) or [])
        fallback_words = list(getattr(torrent_meta, "apply_words", None) or [])
        for word in fallback_words:
            if word not in current_words:
                current_words.append(copy.deepcopy(word))
        if current_words != list(getattr(file_meta, "apply_words", None) or []):
            setattr(file_meta, "apply_words", current_words)
            inherited.append("apply_words")
        return inherited

    @staticmethod
    def refresh_customization(meta: Any, title: str) -> str:
        """Re-evaluate MoviePilot custom placeholders against current settings."""

        if not meta:
            return ""
        existing = getattr(meta, "customization", None)
        detected = ""
        try:
            from app.core.meta.customization import CustomizationMatcher
            from app.core.meta.words import WordsMatcher

            prepared_title, _ = WordsMatcher().prepare(str(title or ""))
            detected = CustomizationMatcher().match(
                title=prepared_title
            ) or ""
        except Exception:
            detected = ""
        merged = MoviePilotQbGateway.merge_customizations(detected, existing)
        setattr(meta, "customization", merged)
        return merged

    @staticmethod
    def merge_customizations(*values: Any) -> str:
        tokens: List[str] = []
        identities = set()
        for value in values:
            parts = value if isinstance(value, (list, tuple, set)) else [value]
            for part in parts:
                for token in str(part or "").split("@"):
                    text = token.strip()
                    identity = text.casefold()
                    if (
                        text
                        and identity not in CUSTOMIZATION_EXCLUDED_TOKENS
                        and identity not in identities
                    ):
                        identities.add(identity)
                        tokens.append(text)
        return "@".join(tokens)

    @staticmethod
    def resource_tokens(meta: Any) -> List[str]:
        tokens: List[str] = []
        for field in NAMING_META_FIELDS:
            value = getattr(meta, field, None)
            if hasattr(value, "value"):
                value = value.value
            values = value if isinstance(value, (list, tuple, set)) else [value]
            for item in values:
                text = str(item or "").strip()
                if text and text.casefold() not in {token.casefold() for token in tokens}:
                    tokens.append(text)
        return tokens

    @staticmethod
    def recognition_words(meta: Any) -> List[str]:
        result: List[str] = []
        for word in list(getattr(meta, "apply_words", None) or []):
            text = MoviePilotQbGateway._recognition_word_text(word)
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _recognition_word_text(word: Any) -> str:
        if isinstance(word, str):
            return word.strip()
        if isinstance(word, (list, tuple)):
            values = [str(item or "").strip() for item in word]
            values = [item for item in values if item]
            return " => ".join(values)
        if isinstance(word, dict):
            source = next((
                word.get(key)
                for key in ("regexp", "regex", "pattern", "source", "word", "origin")
                if word.get(key) not in (None, "")
            ), "")
            target = next((
                word.get(key)
                for key in ("replacement", "replace", "target", "result")
                if word.get(key) not in (None, "")
            ), "")
            if source or target:
                return f"{source} => {target}".strip()
            return ", ".join(
                f"{key}={value}"
                for key, value in word.items()
                if value not in (None, "", [], {})
            )
        return str(word or "").strip()

    @staticmethod
    def _has_meta_value(value: Any) -> bool:
        return value not in (None, "", [], {}, ())

    @staticmethod
    def poster(media: Any) -> str:
        if not media:
            return ""
        getter = getattr(media, "get_poster_image", None)
        if callable(getter):
            return str(getter(default=False) or "")
        return str(getattr(media, "poster_path", "") or "")

    @staticmethod
    def media_type(media: Any) -> str:
        value = getattr(getattr(media, "type", None), "value", None)
        value = str(value or getattr(media, "type", "") or "").casefold()
        if value in {"电影", "movie"}:
            return "movie"
        if value in {"电视剧", "tv", "series"}:
            return "tv"
        return ""

def _task_rule_uses_hr_scan(task_rule: Optional[RssTaskQbRule]) -> bool:
    # HR is a separate deletion policy. Once enabled, the normal due-delete
    # policy must never be scheduled, even if the site identity is invalid.
    return bool(task_rule and task_rule.hr_enabled)

class QbSyncService:
    """Synchronize qB state, recognition, and inventory without mutating qB."""

    def __init__(
        self,
        store: SQLiteStore,
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

    def find_torrent_downloader(self, info_hash: object) -> str:
        normalized_hash = str(info_hash or "").strip().lower()
        if not normalized_hash:
            raise ValueError("缺少 info-hash")
        scope = RssTaskQbScope.from_tasks(self.store.list_all_rss_tasks())
        for downloader in self.gateway.list_downloaders():
            if not downloader.ready or not scope.categories_for(downloader.name):
                continue
            for torrent in self.gateway.list_torrents(downloader.name):
                raw = self.gateway.torrent_dict(torrent)
                if str(raw.get("hash") or "").strip().lower() != normalized_hash:
                    continue
                if scope.matches(downloader.name, raw.get("category") or ""):
                    return downloader.name
        raise LookupError("已配置的 RSS qB 任务中没有找到该 info-hash")

    def refresh_item(
        self,
        downloader_id: object,
        info_hash: object,
        manual_override: Optional[Dict[str, Any]] = None,
        *,
        schedule_delete: bool = False,
        completion_confirmed: bool = False,
        allow_completion_transition: bool = True,
    ) -> Dict[str, Any]:
        downloader_name = str(downloader_id or "").strip()
        normalized_hash = str(info_hash or "").strip().lower()
        if not downloader_name or not normalized_hash:
            raise ValueError("缺少 qB 节点或 info-hash")

        downloader = next(
            (
                item for item in self.gateway.list_downloaders()
                if item.name == downloader_name
            ),
            None,
        )
        if not downloader or not downloader.ready:
            raise RuntimeError(f"qBittorrent 节点不可用：{downloader_name}")
        raw = None
        for torrent in self.gateway.list_torrents(downloader_name):
            candidate = self.gateway.torrent_dict(torrent)
            if str(candidate.get("hash") or "").strip().lower() == normalized_hash:
                raw = candidate
                break
        if not raw:
            raise RuntimeError("qBittorrent 中没有找到该任务")
        scope = RssTaskQbScope.from_tasks(self.store.list_all_rss_tasks())
        if not scope.matches(downloader_name, raw.get("category") or ""):
            raise LookupError("该任务不属于任何已保存的 VT+ RSS 分类")

        self._sync_one(
            downloader=downloader,
            raw=raw,
            force_recognition=True,
            manual_override=manual_override,
            scope=scope,
            schedule_delete=schedule_delete,
            completion_confirmed=completion_confirmed,
            allow_completion_transition=allow_completion_transition,
        )
        snapshot = self.store.get_torrent_snapshot(
            downloader_name, normalized_hash
        )
        if snapshot:
            return snapshot
        media = self.store.get_media_item(
            f"qb:{downloader_name}:{normalized_hash}"
        )
        return {
            "downloader_id": downloader_name,
            "info_hash": normalized_hash,
            "completed": True,
            "transitioned_to_library": bool(media),
            "media_id": media.get("id") if media else None,
        }

    def refresh_media_from_saved_files(
        self,
        media_id: object,
        manual_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Refresh a library card from persisted local files without querying qB."""

        identity = str(media_id or "").strip()
        item = self.store.get_media_item(identity)
        if not item:
            raise LookupError("媒体记录不存在")
        if str(item.get("state") or "") == "imported":
            raise ValueError("已入库卡片只能执行库存复查")

        downloader_id = str(item.get("downloader_id") or "").strip()
        info_hash = str(item.get("info_hash") or "").strip().lower()
        saved_mappings = self.store.list_file_mappings(downloader_id, info_hash)
        repaired_sources = _repair_saved_local_source_paths(item, saved_mappings)
        if repaired_sources:
            saved_mappings = self.store.replace_file_mappings(
                downloader_id,
                info_hash,
                saved_mappings,
            )
        local_files = _saved_local_torrent_files(item, saved_mappings)
        if not local_files:
            raise RuntimeError("已保存的本地媒体文件不存在，无法重新识别")

        refreshed_source_path = _refreshed_item_source_path(item, local_files)
        if refreshed_source_path:
            previous_source_path = str(item.get("source_path") or "").strip()
            item["source_path"] = refreshed_source_path
            details_for_source = copy.deepcopy(item.get("details") or {})
            source_identity = dict(details_for_source.get("source_identity") or {})
            source_identity["source_path"] = refreshed_source_path
            details_for_source["source_identity"] = source_identity
            torrent_details = dict(details_for_source.get("torrent") or {})
            for key in ("content_path", "path"):
                current_value = str(torrent_details.get(key) or "").strip()
                if current_value == previous_source_path or (
                    current_value and not Path(current_value).expanduser().exists()
                ):
                    torrent_details[key] = refreshed_source_path
            if torrent_details:
                details_for_source["torrent"] = torrent_details
            item["details"] = details_for_source

        details = copy.deepcopy(item.get("details") or {})
        stored_override = details.get("manual_override") or {}
        override = _normalize_manual_override(
            stored_override if manual_override is None else manual_override
        )
        recognition_title = _saved_local_recognition_title(item, local_files)
        if override.get("media_type") and override.get("tmdb_id"):
            meta, media = self.gateway.recognize_manual(
                recognition_title,
                override["media_type"],
                override["tmdb_id"],
                override.get("season"),
            )
        else:
            meta, media = self.gateway.recognize(recognition_title)

        now = utc_now()
        media_type = ""
        media_title = ""
        recognized_media_title = ""
        inventory_title = ""
        tmdb_id = override.get("tmdb_id") or None
        season = override.get("season")
        category = str(override.get("category") or "").strip()
        target_name = ""
        failure_code = ""
        failure_message = ""
        refreshed_mappings: List[Dict[str, Any]] = []
        inventory_plan: Dict[str, Any] = {}
        path_plan: Dict[str, Any] = {}
        inventory_details: Dict[str, Any] = {}
        state = "unidentified"

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
            if _valid_tmdb_id(tmdb_id):
                inventory_plan = self.gateway.plan_inventory_files(
                    media,
                    local_files,
                    torrent_meta=meta,
                )
                path_plan = self.library_layout.plan(
                    source_path=str(item.get("source_path") or ""),
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
                        local_files,
                        title_override=inventory_title,
                        torrent_meta=meta,
                    )
                    path_plan = self.library_layout.plan(
                        source_path=str(item.get("source_path") or ""),
                        category=category,
                        expected_files=inventory_plan.get("expected_files") or [],
                        media_type=media_type,
                    )
                inventory_state, inventory_details = self.inventory_checker.check_root(
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
                inventory_details["category"] = path_plan.get("category") or category
                inventory_details["group"] = path_plan.get("group") or ""
                inventory_details["layout_errors"] = path_plan.get("errors") or []
                if inventory_title:
                    media_title = inventory_title
                    media_payload = details.get("media") or {}
                    if isinstance(media_payload, dict):
                        details["media"] = {**media_payload, "title": media_title}
                refreshed_mappings = build_source_target_mappings(
                    downloader_id=downloader_id,
                    info_hash=info_hash,
                    media_id=identity,
                    torrent={"content_path": str(item.get("source_path") or "")},
                    expected_files=inventory_plan.get("expected_files") or [],
                    path_plan=path_plan,
                    inventory_details=inventory_details,
                )
                refreshed_mappings = _restore_saved_source_paths(
                    refreshed_mappings,
                    saved_mappings,
                    local_files,
                )
                state = "existing" if inventory_state == "exists" else "identified"
                if path_plan.get("inventory_files"):
                    target_name = str(
                        path_plan["inventory_files"][0].get("path") or ""
                    )
                if not target_name:
                    target_name = str(
                        inventory_plan.get("inventory_target_name") or ""
                    )
            else:
                failure_code = "missing_tmdb_id"
                failure_message = "MoviePilot 未返回有效 TMDB ID"
        else:
            details["media"] = {}
            details["meta"] = self.gateway.meta_payload(meta)
            failure_code = "recognition_failed"
            failure_message = "MoviePilot 未识别到可靠媒体信息"

        details.update({
            "recognition_signature": hashlib.sha256(
                f"{recognition_title}\n{item.get('source_path') or ''}".encode("utf-8")
            ).hexdigest(),
            "inventory_plan": inventory_plan,
            "path_plan": path_plan,
            "inventory": inventory_details,
            "file_mappings": refreshed_mappings,
            "manual_override": override,
            "recognized_title": recognized_media_title,
            "inventory_title": inventory_title,
        })
        previous_state = str(item.get("state") or "")
        state = preserve_refresh_workflow_state(previous_state, state)
        previous_failure = str(item.get("failure_code") or "")
        if not failure_code and previous_failure not in {
            "recognition_failed",
            "missing_tmdb_id",
        }:
            failure_code = previous_failure
            failure_message = str(item.get("failure_message") or "")
        self.store.upsert_media_item({
            **item,
            "state": state,
            "media_type": media_type,
            "title": media_title or recognition_title,
            "source_name": recognition_title,
            "tmdb_id": tmdb_id,
            "season": season,
            "category": category,
            "target_name": target_name,
            "failure_code": failure_code,
            "failure_message": failure_message,
            "details": details,
            "updated_at": now,
        })
        if media and _valid_tmdb_id(tmdb_id):
            persisted = self.store.replace_file_mappings(
                downloader_id,
                info_hash,
                refreshed_mappings,
            )
            details["file_mappings"] = persisted
            refreshed_item = self.store.get_media_item(identity) or {}
            refreshed_item["details"] = details
            self.store.upsert_media_item(refreshed_item)
        return self.store.get_media_item(identity) or {}

    def run(
        self,
        task_id: str,
        *,
        force_recognition: bool = False,
        schedule_delete: bool = False,
        stop_event: Optional[threading.Event] = None,
        rss_task_id: Optional[str] = None,
        max_items: Optional[int] = None,
        finish_task: bool = True,
        run_mode: str = "all",
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "downloaders": 0,
            "scanned": 0,
            "filtered_out": 0,
            "recognized": 0,
            "unrecognized": 0,
            "existing": 0,
            "completed": 0,
            "completed_skipped": 0,
            "handled": 0,
            "limit_reached": False,
            "errors": [],
        }
        item_limit = max(0, int(max_items or 0))
        result["run_mode"] = "single" if run_mode == "single" else "all"
        configured_tasks = self.store.list_all_rss_tasks()
        if rss_task_id:
            selected_id = str(rss_task_id).strip()
            configured_tasks = [
                task for task in configured_tasks
                if str(task.get("id") or "").strip() == selected_id
            ]
            if configured_tasks:
                selected_config = configured_tasks[0].get("config") or {}
                result["mode"] = str(
                    selected_config.get("task_type") or "rss"
                ).strip().casefold()
                result["rss_task_id"] = selected_id
        scope = RssTaskQbScope.from_tasks(configured_tasks)
        manual_pairs = {
            (rule.downloader, rule.category)
            for rule in scope.rules
            if rule.task_type == "manual"
        }
        result["managed_scope"] = scope.to_dict()
        result["out_of_scope"] = (
            self.store.mark_torrents_outside_scope(
                scope.downloader_categories(),
                utc_now(),
            )
            if not rss_task_id
            else 0
        )
        if not scope.ready:
            message = "VT+ 没有已保存且同时配置 QB下载器、QB分类的 RSS 任务"
            result["errors"].append({"message": message})
            if finish_task:
                self.store.finish_background_task(
                    task_id,
                    "failed",
                    result=result,
                    error_message=message,
                )
            return result

        batches: List[Tuple[DownloaderView, List[Dict[str, Any]]]] = []
        downloaders = self.gateway.list_downloaders()
        if not downloaders:
            raise RuntimeError("当前 MoviePilot 没有已启用的 qBittorrent 下载器")

        for downloader in downloaders:
            if stop_event and stop_event.is_set():
                return self._cancel(task_id, result, finish_task=finish_task)
            categories = scope.categories_for(downloader.name)
            if not categories:
                # A task-scoped refresh must not mark unrelated categories as
                # missing.  They are intentionally outside this run's scope.
                if not rss_task_id:
                    self.store.mark_downloader_seen(downloader.name, [], utc_now())
                continue
            if not downloader.ready:
                result["errors"].append({
                    "downloader": downloader.name,
                    "message": "MoviePilot 中的 qBittorrent 实例未就绪",
                })
                continue
            try:
                all_torrents = [
                    self.gateway.torrent_dict(item)
                    for item in self.gateway.list_torrents(downloader.name)
                ]
                managed_torrents = [
                    item for item in all_torrents
                    if scope.matches(downloader.name, item.get("category") or "")
                ]
                manual_torrents = []
                torrents = []
                for item in managed_torrents:
                    pair = (downloader.name, str(item.get("category") or "").strip())
                    if not rss_task_id and pair in manual_pairs:
                        manual_torrents.append(item)
                    else:
                        torrents.append(item)
                torrents = sorted(torrents, key=lambda item: str(
                    item.get("title") or item.get("name") or ""
                ).casefold())
                result["filtered_out"] += len(all_torrents) - len(torrents)
                result["manual_skipped"] = int(
                    result.get("manual_skipped") or 0
                ) + len(manual_torrents)
                seen_at = utc_now()
                seen_hashes = [
                    str(item.get("hash") or "").lower()
                    for item in [*torrents, *manual_torrents]
                ]
                # Only a full qB refresh owns downloader-wide presence state.
                # Trial/single-task runs must leave other RSS/manual cards
                # untouched, otherwise they temporarily disappear from qB
                # management as "not seen".
                if not rss_task_id:
                    self.store.mark_downloader_seen(
                        downloader.name, seen_hashes, seen_at
                    )
                batches.append((downloader, torrents))
            except Exception as error:
                result["errors"].append({
                    "downloader": downloader.name,
                    "message": str(error),
                })
                self._log("error", f"RSS一条龙：读取 {downloader.name} 失败：{error}")

        result["downloaders"] = len(batches)
        total = sum(len(items) for _, items in batches)
        self.store.update_background_task(task_id, total=total, result=result)
        processed = succeeded = failed = 0
        handled = 0
        limit_reached = False

        for downloader, torrents in batches:
            for raw in torrents:
                if stop_event and stop_event.is_set():
                    return self._cancel(task_id, result, finish_task=finish_task)
                title = str(raw.get("title") or raw.get("name") or "").strip()
                info_hash = str(raw.get("hash") or "").strip().lower()
                processed += 1
                if not info_hash:
                    failed += 1
                    handled += 1
                    result["handled"] = handled
                    result["errors"].append({
                        "downloader": downloader.name,
                        "title": title,
                        "message": "qB 任务缺少 info-hash",
                    })
                    self._update_progress(
                        task_id, title, processed, succeeded, failed, total, result
                    )
                    if item_limit and handled >= item_limit:
                        limit_reached = True
                        break
                    continue
                try:
                    history = self.store.latest_rss_history_for_torrent(
                        downloader.name, info_hash
                    ) or {}
                    rule = scope.rule_for(
                        downloader.name,
                        raw.get("category") or "",
                        history.get("task_id") or "",
                        preferred_task_type="rss" if not history else "",
                    )
                    if _torrent_completed(raw):
                        if rule and rule.task_type == "manual" and not history:
                            history = self._ensure_manual_history(
                                task_rule=rule,
                                downloader_id=downloader.name,
                                info_hash=info_hash,
                                raw=raw,
                            )
                        # A manual card can be deleted while its RSS history is
                        # intentionally retained.  In that case the old
                        # completion marker must not suppress the qB task from
                        # being processed again.
                        if (
                            rule
                            and rule.task_type == "manual"
                            and history
                            and bool(
                                (history.get("payload") or {}).get(
                                    "completion_processed"
                                )
                            )
                            and bool(
                                (history.get("payload") or {}).get(
                                    "imported_to_library"
                                )
                            )
                            and not self.store.get_media_item(
                                f"qb:{downloader.name}:{info_hash}"
                            )
                        ):
                            self.store.reopen_rss_torrent(
                                history,
                                downloader_id=downloader.name,
                                info_hash=info_hash,
                            )
                            history = (
                                self.store.latest_rss_history_for_torrent(
                                    downloader.name, info_hash
                                )
                                or history
                            )
                        history_payload = history.get("payload") or {}
                        if (
                            bool(history_payload.get("completion_processed"))
                            and not _completion_requires_processing(rule, history)
                        ):
                            self.store.delete_torrent_snapshot(
                                downloader.name, info_hash
                            )
                            succeeded += 1
                            result["completed_skipped"] += 1
                            self._update_progress(
                                task_id,
                                title,
                                processed,
                                succeeded,
                                failed,
                                total,
                                result,
                            )
                            continue
                    outcome = self._sync_one(
                        downloader=downloader,
                        raw=raw,
                        force_recognition=force_recognition,
                        scope=scope,
                        schedule_delete=schedule_delete,
                        stop_event=stop_event,
                    )
                    succeeded += 1
                    handled += 1
                    result["handled"] = handled
                    result["scanned"] += 1
                    result[outcome] += 1
                    if _torrent_completed(raw):
                        result["completed"] += 1
                except Exception as error:
                    if stop_event and stop_event.is_set():
                        return self._cancel(
                            task_id, result, finish_task=finish_task
                        )
                    failed += 1
                    handled += 1
                    result["handled"] = handled
                    result["errors"].append({
                        "downloader": downloader.name,
                        "hash": info_hash,
                        "title": title,
                        "message": str(error),
                    })
                    self._save_item_error(downloader.name, raw, str(error))
                    self._log(
                        "error",
                        f"RSS一条龙：同步 {downloader.name}/{info_hash} 失败：{error}",
                    )
                self._update_progress(
                    task_id, title, processed, succeeded, failed, total, result
                )
                if item_limit and handled >= item_limit:
                    limit_reached = True
                    break
            if limit_reached:
                break

        if stop_event and stop_event.is_set():
            return self._cancel(task_id, result, finish_task=finish_task)
        result["handled"] = handled
        result["limit_reached"] = limit_reached
        state = "succeeded" if batches else "failed"
        error_message = "" if batches else "所有 qBittorrent 节点均读取失败"
        if finish_task:
            self.store.finish_background_task(
                task_id, state, result=result, error_message=error_message
            )
        return result

    def _schedule_qb_delete(
        self,
        *,
        task_rule: Optional[RssTaskQbRule],
        downloader_id: str,
        info_hash: str,
        source_path: str,
        completed: bool,
    ) -> Dict[str, Any]:
        if (
            not completed
            or not task_rule
            or task_rule.delete_after_minutes <= 0
            or _task_rule_uses_hr_scan(task_rule)
        ):
            return {}
        due_at = (
            datetime.now(timezone.utc)
            + timedelta(minutes=task_rule.delete_after_minutes)
        ).isoformat(timespec="seconds")
        job = self.store.schedule_qb_delete(
            task_id=task_rule.task_id,
            task_name=task_rule.task_name,
            downloader_id=downloader_id,
            info_hash=info_hash,
            source_path=source_path,
            delete_files=task_rule.delete_files,
            due_at=due_at,
            details={
                "source_kind": "qb_download",
                "deletion_scope": "qb_task_and_save_path",
            },
        )
        return {
            "job_id": str(job.get("id") or ""),
            "due_at": str(job.get("due_at") or due_at),
            "delete_files": bool(job.get("delete_files")),
            "source_path": str(job.get("source_path") or source_path),
            "deletion_scope": "qb_task_and_save_path",
        }

    def _ensure_manual_history(
        self,
        *,
        task_rule: RssTaskQbRule,
        downloader_id: str,
        info_hash: str,
        raw: Dict[str, Any],
    ) -> Dict[str, Any]:
        existing = self.store.latest_rss_history_for_torrent(
            downloader_id, info_hash
        ) or {}
        if existing:
            return existing
        source_url = _extract_torrent_source_url(raw)
        torrent_id = extract_torrent_id(source_url)
        media = self.store.get_media_item(
            f"qb:{downloader_id}:{info_hash}"
        ) or self.store.find_media_by_source_path(
            str(raw.get("content_path") or raw.get("path") or "")
        ) or {}
        already_processed = bool(media)
        payload: Dict[str, Any] = {
            "downloader": downloader_id,
            "info_hash": info_hash,
            "manual_source": True,
        }
        if torrent_id:
            payload["torrent_id"] = torrent_id
        if already_processed:
            payload.update({
                "completion_processed": True,
                "completion_processed_at": utc_now(),
                "imported_to_library": True,
            })
        source_key = hashlib.sha256(
            f"manual\n{task_rule.task_id}\n{downloader_id}\n{info_hash}".encode(
                "utf-8"
            )
        ).hexdigest()
        self.store.upsert_rss_history({
            "task_id": task_rule.task_id,
            "source_key": source_key,
            "content_key": f"{downloader_id}:{info_hash}",
            "title": str(raw.get("title") or raw.get("name") or "").strip(),
            "status": "processed" if already_processed else "queued",
            "reason": (
                "已有手动添加卡片，已补齐处理记录"
                if already_processed else "等待手动添加处理"
            ),
            "detail_url_masked": mask_url(source_url),
            "payload": payload,
        })
        return self.store.latest_rss_history_for_torrent(
            downloader_id, info_hash
        ) or {}

    def _sync_one(
        self,
        *,
        downloader: DownloaderView,
        raw: Dict[str, Any],
        force_recognition: bool,
        manual_override: Optional[Dict[str, Any]] = None,
        scope: Optional[RssTaskQbScope] = None,
        schedule_delete: bool = False,
        completion_confirmed: bool = False,
        allow_completion_transition: bool = True,
        stop_event: Optional[threading.Event] = None,
    ) -> str:
        if stop_event and stop_event.is_set():
            raise RuntimeError("手动添加处理已停止")
        now = utc_now()
        info_hash = str(raw.get("hash") or "").strip().lower()
        title = str(raw.get("title") or raw.get("name") or "").strip()
        content_path = str(raw.get("content_path") or raw.get("path") or "")
        existing = self.store.get_torrent_snapshot(downloader.name, info_hash) or {}
        existing_details = existing.get("details") or {}
        rss_history = self.store.latest_rss_history_for_torrent(
            downloader.name, info_hash
        ) or {}
        media_id = f"qb:{downloader.name}:{info_hash}"
        persisted_media = self.store.get_media_item(media_id) or {}
        persisted_media_state = str(persisted_media.get("state") or "")
        completion_already_processed = bool(
            (rss_history.get("payload") or {}).get("completion_processed")
        )
        live_completed = _torrent_completed(raw)
        if completion_confirmed:
            torrent_completed = True
        elif allow_completion_transition:
            torrent_completed = live_completed
            if completion_already_processed and not live_completed:
                if persisted_media_state in {"importing", "imported"}:
                    torrent_completed = True
                else:
                    self.store.reopen_rss_torrent(
                        rss_history,
                        downloader_id=downloader.name,
                        info_hash=info_hash,
                    )
                    rss_history = self.store.latest_rss_history_for_torrent(
                        downloader.name, info_hash
                    ) or rss_history
        else:
            torrent_completed = completion_already_processed
        task_scope = scope or RssTaskQbScope.from_tasks(
            self.store.list_all_rss_tasks()
        )
        task_rule = task_scope.rule_for(
            downloader.name,
            raw.get("category") or "",
            rss_history.get("task_id") or "",
            preferred_task_type="rss" if not rss_history else "",
        )
        if task_rule and task_rule.task_type == "manual" and not rss_history:
            rss_history = self._ensure_manual_history(
                task_rule=task_rule,
                downloader_id=downloader.name,
                info_hash=info_hash,
                raw=raw,
            )
            completion_already_processed = bool(
                (rss_history.get("payload") or {}).get("completion_processed")
            )
        manual_labels: Dict[str, Any] = {}
        if task_rule and task_rule.task_type == "manual":
            raw = dict(raw)
            comment_url = _extract_torrent_source_url(raw)
            if not comment_url:
                try:
                    properties = self.gateway.torrent_properties(
                        self.gateway.get_server(downloader.name), info_hash
                    )
                except Exception as error:
                    properties = {}
                    self._log(
                        "warning",
                        f"RSS一条龙：读取 qB 注释失败 {downloader.name}/{info_hash}：{error}",
                    )
                if properties:
                    for key, value in properties.items():
                        if raw.get(key) in (None, "") and value not in (None, ""):
                            raw[key] = value
                    comment_url = _extract_torrent_source_url(properties)
                if comment_url:
                    self._log(
                        "info",
                        f"RSS一条龙：读取手动 qB 注释链接成功，任务={title}，"
                        f"链接={mask_url(comment_url)}",
                    )
            if comment_url:
                raw["comment"] = comment_url
                raw["source_url_masked"] = mask_url(comment_url)
        if task_rule and task_rule.task_type == "manual" and task_rule.site_id:
            try:
                from .rss_execute import MoviePilotRssGateway
                from .rss_rename import QbSourceRenameService
                from .rss_site_labels import SiteLabelService
                comment_url = _extract_torrent_source_url(raw)
                access = MoviePilotRssGateway.site_access(task_rule.site_id)
                torrent_id = ""
                match = re.search(r"[?&]id=(\d+)", comment_url)
                if match:
                    torrent_id = match.group(1)
                label_service = SiteLabelService(
                    MoviePilotRssGateway(),
                    sleeper=lambda seconds: _interruptible_wait(
                        stop_event, seconds
                    ),
                    logger=self.logger,
                    min_request_interval_seconds=task_rule.query_interval,
                )
                manual_labels = label_service.detect(
                    access=access,
                    title=title,
                    detail_url=comment_url,
                    torrent_id=torrent_id,
                    cn_keywords="国语,国配",
                    recognize_cn=True,
                    recognize_fx=True,
                    allow_search_without_detail=True,
                )
                if stop_event and stop_event.is_set():
                    raise RuntimeError("手动添加处理已停止")
                manual_source_url = str(
                    manual_labels.get("request_url_masked") or comment_url or ""
                ).strip()
                if manual_source_url:
                    raw["source_url_masked"] = mask_url(manual_source_url)
                    raw["comment"] = manual_source_url
                if (
                    manual_labels.get("mandarin")
                    or manual_labels.get("effects")
                    or task_rule.rename_rules
                ):
                    server = self.gateway.get_server(downloader.name)
                    rename_result = QbSourceRenameService(self.gateway).apply(
                        server,
                        info_hash,
                        rss_title=title,
                        rename_enabled=bool(task_rule.rename_rules),
                        rename_rules=task_rule.rename_rules,
                        add_chinese_title=False,
                        add_cn=bool(manual_labels.get("mandarin")),
                        add_fx=bool(manual_labels.get("effects")),
                    )
                    manual_labels["rename"] = rename_result
                    if rename_result.get("status") in {"renamed", "unchanged"}:
                        display_name = _rename_result_display_name(rename_result)
                        if display_name:
                            self.gateway.rename_torrent_name(
                                server, info_hash, display_name
                            )
                            # Recognition and the eventual qB snapshot must
                            # use the authoritative post-rename title.  The
                            # snapshot is persisted only after this block.
                            title = display_name
                            raw["title"] = display_name
                            raw["name"] = display_name
                    raw = dict(raw)
                    raw["manual_labels"] = manual_labels
            except Exception as error:
                if stop_event and stop_event.is_set():
                    raise RuntimeError("手动添加处理已停止") from error
                manual_labels = {"status": "failed", "reason": str(error)[:500]}
        import_enabled = bool(task_rule and task_rule.import_enabled)
        completion_requires_processing = _completion_requires_processing(
            task_rule, rss_history
        )
        source_url_masked = _source_url_for_torrent(
            rss_history,
            raw,
            existing.get("source_url_masked") or "",
        )
        qb_delete = (
            self._schedule_qb_delete(
                task_rule=task_rule,
                downloader_id=downloader.name,
                info_hash=info_hash,
                source_path=content_path,
                completed=torrent_completed,
            )
            if schedule_delete
            else {}
        )
        if (
            torrent_completed
            and not import_enabled
            and not completion_requires_processing
        ):
            existing_media = self.store.get_media_item(media_id) or {}
            if str(existing_media.get("state") or "") not in {
                "importing", "imported"
            }:
                self.store.delete_media_item(media_id)
            self.store.delete_torrent_snapshot(downloader.name, info_hash)
            self.store.mark_rss_torrent_completed(
                rss_history,
                downloader_id=downloader.name,
                info_hash=info_hash,
                imported=False,
                qb_delete=qb_delete,
            )
            return "recognized"
        local_torrent_files = (
            _discover_local_torrent_files(content_path)
            if torrent_completed
            else []
        )
        recognition_title = (
            _local_recognition_title(content_path, local_torrent_files)
            or title
        )
        signature = hashlib.sha256(
            f"{recognition_title}\n{content_path}".encode("utf-8")
        ).hexdigest()
        stored_override = existing_details.get("manual_override") or {}
        override = _normalize_manual_override(
            stored_override if manual_override is None else manual_override
        )
        media_payload = existing_details.get("media") or {}
        recognition_needed = (
            force_recognition
            or not existing
            or existing_details.get("recognition_signature") != signature
            or existing.get("recognition_state") != "identified"
            or not media_payload
        )

        meta = media = None
        if recognition_needed:
            if override.get("media_type") and override.get("tmdb_id"):
                meta, media = self.gateway.recognize_manual(
                    recognition_title,
                    override["media_type"],
                    override["tmdb_id"],
                    override.get("season"),
                )
            else:
                meta, media = self.gateway.recognize(recognition_title)
        else:
            media = self.gateway.restore_media(media_payload)
            if media:
                meta = self.gateway.restore_meta(
                    recognition_title, existing_details.get("meta") or {}
                )
            else:
                if override.get("media_type") and override.get("tmdb_id"):
                    meta, media = self.gateway.recognize_manual(
                        recognition_title,
                        override["media_type"],
                        override["tmdb_id"],
                        override.get("season"),
                    )
                else:
                    meta, media = self.gateway.recognize(recognition_title)

        recognition_error = ""
        inventory_state = "unknown"
        inventory_details: Dict[str, Any] = {}
        inventory_plan: Dict[str, Any] = {}
        path_plan: Dict[str, Any] = {}
        file_mappings: List[Dict[str, Any]] = []
        mapping_refresh_succeeded = False
        recognized_media_title = ""
        inventory_title = ""
        if media:
            media_type = self.gateway.media_type(media)
            media_payload = self.gateway.media_payload(media)
            meta_payload = self.gateway.meta_payload(meta)
            media_title = str(getattr(media, "title", "") or "")
            recognized_media_title = media_title
            media_year = str(getattr(media, "year", "") or "")
            tmdb_id = getattr(media, "tmdb_id", None)
            season = getattr(media, "season", None)
            if season is None:
                season = getattr(meta, "begin_season", None)
            automatic_category = str(getattr(media, "category", "") or "")
            category = str(override.get("category") or automatic_category).strip()
            poster = self.gateway.poster(media)
            pending_labels = _pending_mandarin_labels(rss_history)
            if (
                _valid_tmdb_id(tmdb_id)
                and pending_labels
                and _allows_mandarin_category(category)
            ):
                rename_result = self._apply_pending_mandarin_label(
                    history=rss_history,
                    downloader_id=downloader.name,
                    info_hash=info_hash,
                    category=category,
                )
                if rename_result and rename_result.get("status") != "failed":
                    # Re-read the renamed qB files and run recognition again so
                    # MoviePilot can derive the final customization markers.
                    return self._sync_one(
                        downloader=downloader,
                        raw=raw,
                        force_recognition=True,
                        manual_override=override,
                        scope=scope,
                        schedule_delete=schedule_delete,
                        completion_confirmed=completion_confirmed,
                        allow_completion_transition=allow_completion_transition,
                        stop_event=stop_event,
                    )
            if not _valid_tmdb_id(tmdb_id):
                recognition_error = "MoviePilot 未返回有效 TMDB ID"
                inventory_details = {
                    "method": "tmdb_strm_features",
                    "scope": "mp_library_path",
                    "folder_status": "unknown",
                    "total_files": 0,
                    "exists_count": 0,
                    "missing_count": 0,
                    "files": [],
                    "reason": recognition_error,
                }
                media_state = "unidentified"
                recognition_state = "unidentified"
                outcome = "unrecognized"
            else:
                try:
                    torrent_files = local_torrent_files or self.gateway.list_torrent_files(
                        downloader.name, info_hash
                    )
                    inventory_plan = self.gateway.plan_inventory_files(
                        media, torrent_files, torrent_meta=meta
                    )
                    path_plan = self.library_layout.plan(
                        source_path=content_path,
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
                            source_path=content_path,
                            category=category,
                            expected_files=inventory_plan.get("expected_files") or [],
                            media_type=media_type,
                        )
                    inventory_state, inventory_details = (
                        self.inventory_checker.check_root(
                            path_plan.get("inventory_base") or "",
                            inventory_plan.get("expected_files") or [],
                            tmdb_id=tmdb_id,
                            expected_directory=(
                                inventory_plan.get("expected_directory") or ""
                            ),
                            media_title=inventory_title or media_title,
                            alternate_titles=[recognized_media_title],
                            folder=folder,
                            plan_errors=inventory_plan.get("plan_errors") or [],
                            total_files=inventory_plan.get("total_files"),
                        )
                    )
                    inventory_details["category"] = (
                        path_plan.get("category") or category
                    )
                    inventory_details["group"] = path_plan.get("group") or ""
                    inventory_details["layout_errors"] = path_plan.get("errors") or []
                    file_mappings = build_source_target_mappings(
                        downloader_id=downloader.name,
                        info_hash=info_hash,
                        media_id=media_id,
                        torrent=raw,
                        expected_files=inventory_plan.get("expected_files") or [],
                        path_plan=path_plan,
                        inventory_details=inventory_details,
                    )
                    mapping_refresh_succeeded = True
                except Exception as error:
                    inventory_state = "unknown"
                    inventory_details = {
                        "method": "tmdb_strm_features",
                        "scope": "mp_library_path",
                        "error": str(error),
                    }
                if inventory_title:
                    media_title = inventory_title
                    if isinstance(media_payload, dict):
                        media_payload = {**media_payload, "title": media_title}
                media_state = (
                    "existing" if inventory_state == "exists" else "identified"
                )
                recognition_state = "identified"
                outcome = "existing" if inventory_state == "exists" else "recognized"
        else:
            media_type = ""
            media_state = "unidentified"
            media_payload = {}
            meta_payload = self.gateway.meta_payload(meta)
            media_title = ""
            media_year = ""
            tmdb_id = override.get("tmdb_id") or None
            season = (
                override.get("season")
                if override.get("media_type") == "tv"
                else getattr(meta, "begin_season", None) if meta else None
            )
            automatic_category = ""
            category = str(override.get("category") or "").strip()
            poster = ""
            recognition_state = "unidentified"
            recognition_error = "MoviePilot 未识别到可靠媒体信息"
            outcome = "unrecognized"

        details = {
            "torrent": raw,
            "recognition_signature": signature,
            "meta": meta_payload,
            "media": media_payload,
            "inventory_plan": inventory_plan,
            "path_plan": path_plan,
            "inventory": inventory_details,
            "file_mappings": file_mappings,
            "manual_override": override,
            "automatic_category": automatic_category,
            "recognized_title": recognized_media_title,
            "inventory_title": inventory_title,
            "rss_source": {
                "task_id": str(rss_history.get("task_id") or ""),
                "source_key": str(rss_history.get("source_key") or ""),
                "detail_url_masked": source_url_masked,
            } if rss_history or source_url_masked else {},
            "import_control": {
                "task_id": task_rule.task_id if task_rule else "",
                "task_name": task_rule.task_name if task_rule else "",
                "import_enabled": import_enabled,
                "torrent_completed": torrent_completed,
                "realtime_hardlink_enabled": bool(
                    task_rule and task_rule.realtime_hardlink_enabled
                ),
            },
            "source_identity": {
                "kind": "qb_download",
                "source_path": content_path,
                "deletion_scope": "qb_task_and_save_path",
            },
            "qb_delete": qb_delete,
            "manual_labels": manual_labels,
            "site_labels": (rss_history.get("payload") or {}).get("site_labels") or {},
        }
        target_name = ""
        if path_plan.get("inventory_files"):
            target_name = str(path_plan["inventory_files"][0].get("path") or "")
        if not target_name:
            target_name = str(inventory_plan.get("inventory_target_name") or "")
        existing_media = self.store.get_media_item(media_id) or {}
        imported_record = str(existing_media.get("state") or "") in {
            "importing", "imported"
        }
        create_candidate = import_enabled and torrent_completed
        media_source_path = content_path
        realtime_hardlink: Dict[str, Any] = {}
        realtime_error = ""
        completion_payload = rss_history.get("payload") or {}
        previous_realtime = completion_payload.get("realtime_hardlink") or {}
        realtime_already_linked = (
            isinstance(previous_realtime, dict)
            and str(previous_realtime.get("state") or "") == "linked"
        )
        realtime_candidate = bool(
            torrent_completed
            and task_rule
            and task_rule.realtime_hardlink_enabled
            and not imported_record
            and (
                not realtime_already_linked
                or (
                    create_candidate
                    and not bool(completion_payload.get("imported_to_library"))
                )
            )
        )
        if (
            realtime_candidate
            and task_rule
        ):
            try:
                realtime_mappings = (
                    bind_local_source_paths(file_mappings, local_torrent_files)
                    if file_mappings
                    else build_realtime_source_mappings(
                        downloader_id=downloader.name,
                        info_hash=info_hash,
                        media_id=media_id,
                        files=local_torrent_files,
                    )
                )
                file_mappings, media_source_path, realtime_hardlink = (
                    create_realtime_hardlinks(
                        content_path=content_path,
                        file_mappings=realtime_mappings,
                        source_root=task_rule.realtime_source_root,
                        link_root=task_rule.realtime_link_root,
                    )
                )
                details["file_mappings"] = file_mappings
                details["realtime_hardlink"] = realtime_hardlink
                details["source_identity"] = {
                    "kind": "realtime_hardlink",
                    "source_path": media_source_path,
                    "qb_source_path": content_path,
                    "deletion_scope": "persisted_file_mappings_only",
                }
            except Exception as error:
                realtime_error = str(error)
                realtime_hardlink = {
                    "enabled": True,
                    "source_root": task_rule.realtime_source_root,
                    "link_root": task_rule.realtime_link_root,
                    "state": "failed",
                    "error": realtime_error,
                }
                details["realtime_hardlink"] = realtime_hardlink
        if create_candidate and not imported_record:
            self.store.upsert_media_item({
                "id": media_id,
                "state": media_state,
                "media_type": media_type,
                "title": media_title or title,
                "source_name": recognition_title,
                "source_path": media_source_path,
                "downloader_id": downloader.name,
                "info_hash": info_hash,
                "tmdb_id": tmdb_id,
                "season": season,
                "category": category,
                "target_name": target_name,
                "failure_code": (
                    "realtime_hardlink_failed"
                    if realtime_error
                    else "recognition_failed"
                    if not media
                    else "missing_tmdb_id"
                    if not _valid_tmdb_id(tmdb_id)
                    else ""
                ),
                "failure_message": realtime_error or recognition_error,
                "rolled_back": bool(existing_media.get("rolled_back")),
                "details": details,
                "updated_at": now,
            })
        elif not imported_record:
            self.store.delete_media_item(media_id)
        should_persist_mappings = bool(
            create_candidate
            and not imported_record
            and (
                (
                    media
                    and _valid_tmdb_id(tmdb_id)
                    and mapping_refresh_succeeded
                )
                or str(realtime_hardlink.get("state") or "") == "linked"
            )
        )
        if should_persist_mappings:
            self.store.replace_file_mappings(
                downloader.name,
                info_hash,
                file_mappings,
            )
        if torrent_completed:
            self.store.delete_torrent_snapshot(downloader.name, info_hash)
            self.store.mark_rss_torrent_completed(
                rss_history,
                downloader_id=downloader.name,
                info_hash=info_hash,
                imported=create_candidate,
                realtime_hardlink=realtime_hardlink,
                qb_delete=qb_delete,
            )
        else:
            self.store.upsert_torrent_snapshot({
                "downloader_id": downloader.name,
                "info_hash": info_hash,
                "name": title,
                "state": str(raw.get("state") or ""),
                "category": str(raw.get("category") or ""),
                "content_path": content_path,
                "progress": float(raw.get("progress") or 0),
                "size": int(raw.get("size") or 0),
                "media_id": None,
                "source_url_masked": source_url_masked,
                "present": 1,
                "recognition_state": recognition_state,
                "inventory_state": inventory_state,
                "media_title": media_title,
                "media_type": media_type,
                "media_year": media_year,
                "tmdb_id": tmdb_id,
                "season": season,
                "poster": poster,
                "recognition_error": recognition_error,
                "recognized_at": now,
                "last_seen_at": now,
                "missing_since": None,
                "details": details,
                "updated_at": now,
            })
        return outcome

    def _save_item_error(
        self, downloader: str, raw: Dict[str, Any], message: str
    ) -> None:
        info_hash = str(raw.get("hash") or "").strip().lower()
        if not info_hash:
            return
        now = utc_now()
        existing = self.store.get_torrent_snapshot(downloader, info_hash) or {}
        self.store.upsert_torrent_snapshot({
            "downloader_id": downloader,
            "info_hash": info_hash,
            "name": str(raw.get("title") or raw.get("name") or ""),
            "state": str(raw.get("state") or ""),
            "category": str(raw.get("category") or ""),
            "content_path": str(raw.get("content_path") or raw.get("path") or ""),
            "progress": float(raw.get("progress") or 0),
            "size": int(raw.get("size") or 0),
            "media_id": existing.get("media_id"),
            "source_url_masked": existing.get("source_url_masked") or "",
            "present": 1,
            "recognition_state": "error",
            "inventory_state": existing.get("inventory_state") or "unknown",
            "media_title": existing.get("media_title") or "",
            "media_type": existing.get("media_type") or "",
            "media_year": existing.get("media_year") or "",
            "tmdb_id": existing.get("tmdb_id"),
            "season": existing.get("season"),
            "poster": existing.get("poster") or "",
            "recognition_error": message,
            "recognized_at": existing.get("recognized_at"),
            "last_seen_at": now,
            "missing_since": None,
            "details": {**(existing.get("details") or {}), "torrent": raw},
            "updated_at": now,
        })

    def _apply_pending_mandarin_label(
        self,
        *,
        history: Dict[str, Any],
        downloader_id: str,
        info_hash: str,
        category: str,
    ) -> Optional[Dict[str, Any]]:
        payload = dict(history.get("payload") or {})
        labels = dict(payload.get("site_labels") or {})
        if not labels.get("mandarin_pending") or not labels.get("mandarin"):
            return None
        if not _allows_mandarin_category(category):
            labels["mandarin_pending"] = False
            labels["mandarin_skipped"] = True
            payload["site_labels"] = labels
            self.store.upsert_rss_history({
                **history,
                "payload": payload,
                "updated_at": utc_now(),
            })
            return None
        try:
            from .rss_rename import QbSourceRenameService

            result = QbSourceRenameService(self.gateway).apply(
                self.gateway.get_server(downloader_id),
                info_hash,
                rss_title="",
                rename_enabled=False,
                rename_rules="",
                add_chinese_title=False,
                add_cn=True,
                add_fx=False,
            )
        except Exception as error:
            self._log(
                "error",
                f"RSS一条龙：延迟添加国配标签失败 "
                f"{downloader_id}/{info_hash}：{error}",
            )
            return {"status": "failed", "error": str(error)}
        if result.get("status") != "failed":
            labels["mandarin_pending"] = False
            labels["mandarin_applied"] = True
            payload["site_labels"] = labels
            self.store.upsert_rss_history({
                **history,
                "payload": payload,
                "updated_at": utc_now(),
            })
            self._log(
                "info",
                f"RSS一条龙：延迟添加国配标签完成 "
                f"{downloader_id}/{info_hash}，分类={category}",
            )
        return result

    def _update_progress(
        self,
        task_id: str,
        title: str,
        processed: int,
        succeeded: int,
        failed: int,
        total: int,
        result: Dict[str, Any],
    ) -> None:
        self.store.update_background_task(
            task_id,
            current_item=title,
            processed=processed,
            succeeded=succeeded,
            failed=failed,
            total=total,
            result=result,
        )

    def _cancel(
        self,
        task_id: str,
        result: Dict[str, Any],
        *,
        finish_task: bool = True,
    ) -> Dict[str, Any]:
        result["cancelled"] = True
        if finish_task:
            self.store.finish_background_task(
                task_id,
                "cancelled",
                result=result,
                error_message="刷新任务已取消",
            )
        return result

    def _log(self, level: str, message: str) -> None:
        if self.logger and hasattr(self.logger, level):
            getattr(self.logger, level)(message)


def _first_text(
    sources: Iterable[Dict[str, Any]],
    keys: Sequence[str],
) -> str:
    for source in sources:
        for key in keys:
            if key not in source:
                continue
            value = source.get(key)
            if isinstance(value, dict):
                value = value.get("value") or value.get("name") or value.get("id")
            text = str(value or "").strip()
            if text:
                return text
    return ""


def _source_url_for_torrent(
    history: Dict[str, Any],
    torrent: Dict[str, Any],
    existing: object = "",
) -> str:
    for candidate in (
        history.get("detail_url_masked"),
        torrent.get("comment"),
        torrent.get("source_url_masked"),
        torrent.get("source_url"),
        torrent.get("detail_url"),
        existing,
    ):
        value = mask_url(candidate)
        if value.casefold().startswith(("http://", "https://")):
            return value

    torrent_id = str((history.get("payload") or {}).get("torrent_id") or "").strip()
    tracker = str(torrent.get("tracker") or "").strip()
    parsed = urlparse(tracker)
    if torrent_id.isdigit() and parsed.scheme.casefold() in {"http", "https"} and parsed.netloc:
        return urlunparse((
            parsed.scheme,
            parsed.netloc.rsplit("@", 1)[-1],
            "/details.php",
            "",
            urlencode({"id": torrent_id}),
            "",
        ))
    return ""


def _interruptible_wait(
    stop_event: Optional[threading.Event], seconds: object
) -> None:
    try:
        timeout = max(0.0, float(seconds or 0))
    except (TypeError, ValueError):
        timeout = 0.0
    waiter = stop_event or threading.Event()
    if waiter.wait(timeout) and stop_event:
        raise RuntimeError("手动添加处理已停止")


def _extract_torrent_source_url(value: object) -> str:
    """Extract the first HTTP(S) source URL from qB fields or nested values."""
    values: List[object] = []

    def collect(item: object) -> None:
        if isinstance(item, dict):
            for key in (
                "comment", "url", "source_url", "detail_url", "rss_source",
            ):
                if key in item:
                    collect(item.get(key))
            return
        if isinstance(item, (list, tuple, set)):
            for child in item:
                collect(child)
            return
        values.append(item)

    collect(value)
    for item in values:
        text = html.unescape(str(item or "")).strip()
        if not text:
            continue
        match = re.search(r"https?://[^\s\"'<>]+", text, flags=re.IGNORECASE)
        if match:
            return match.group(0).rstrip(".,;)]}>")
    return ""


def _rename_result_display_name(result: Dict[str, Any]) -> str:
    """Pick the renamed torrent root for qB's display name."""
    directory_renames = result.get("directory_renames") or []
    for item in directory_renames:
        if not isinstance(item, dict):
            continue
        new_path = str(item.get("new_path") or "").strip().replace("\\", "/")
        if new_path and "/" not in new_path.strip("/"):
            return PurePosixPath(new_path).name
    final_files = result.get("final_files") or []
    for item in final_files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("name") or "").strip().replace("\\", "/")
        if path:
            parts = [part for part in path.split("/") if part]
            if parts:
                return parts[0] if len(parts) > 1 else PurePosixPath(parts[0]).stem
    return ""


def _torrent_completed(torrent: Dict[str, Any]) -> bool:
    raw_progress = torrent.get("progress")
    if raw_progress not in (None, ""):
        try:
            progress = float(raw_progress)
        except (TypeError, ValueError):
            pass
        else:
            return progress >= 99.999 or 0.999999 <= progress <= 1.0
    state = str(torrent.get("state") or "").strip().casefold()
    return state in {
        "completed",
        "uploading",
        "stalledup",
        "pausedup",
        "queuedup",
        "checkingup",
        "forcedup",
    }


def _pending_mandarin_labels(history: Dict[str, Any]) -> bool:
    labels = (history.get("payload") or {}).get("site_labels") or {}
    return bool(labels.get("mandarin_pending") and labels.get("mandarin"))


def _allows_mandarin_category(category: object) -> bool:
    from .rss_execute import MANDARIN_MEDIA_CATEGORIES

    return str(category or "").strip() in MANDARIN_MEDIA_CATEGORIES


def _completion_requires_processing(
    task_rule: Optional[RssTaskQbRule],
    history: Dict[str, Any],
) -> bool:
    """Return whether a completed RSS item still needs a configured transition."""

    if not task_rule:
        return False
    payload = history.get("payload") or {}
    if task_rule.import_enabled and not bool(payload.get("imported_to_library")):
        return True
    if task_rule.realtime_hardlink_enabled:
        realtime = payload.get("realtime_hardlink") or {}
        return not (
            isinstance(realtime, dict)
            and str(realtime.get("state") or "") == "linked"
        )
    return False


def _as_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "是"}
    return bool(value)


def _safe_positive_int(value: object, fallback: int = 60) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(1, parsed)


def build_source_target_mappings(
    *,
    downloader_id: str,
    info_hash: str,
    media_id: str,
    torrent: Dict[str, Any],
    expected_files: Sequence[Dict[str, Any]],
    path_plan: Dict[str, Any],
    inventory_details: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Bind authoritative qB source paths to independent MP target paths."""

    link_files = _index_planned_files(path_plan.get("link_files") or [])
    inventory_files = _index_planned_files(path_plan.get("inventory_files") or [])
    inventory_results = _index_planned_files(
        inventory_details.get("files") or []
    )
    mappings: List[Dict[str, Any]] = []
    for fallback_index, expected in enumerate(expected_files or []):
        source_relative = str(expected.get("source_name") or "").replace("\\", "/")
        if not source_relative:
            continue
        file_index = expected.get("file_index")
        try:
            file_index = int(
                fallback_index if file_index is None else file_index
            )
        except (TypeError, ValueError):
            file_index = fallback_index
        key = _planned_file_key(expected, fallback_index)
        link = link_files.get(key) or link_files.get(source_relative.casefold()) or {}
        inventory = (
            inventory_files.get(key)
            or inventory_files.get(source_relative.casefold())
            or {}
        )
        checked = (
            inventory_results.get(key)
            or inventory_results.get(source_relative.casefold())
            or {}
        )
        inventory_exists = bool(checked.get("inventory_exists"))
        mappings.append({
            "downloader_id": str(downloader_id or ""),
            "info_hash": str(info_hash or "").lower(),
            "file_index": file_index,
            "media_id": str(media_id or ""),
            "source_relative_path": source_relative,
            "current_source_path": resolve_current_source_path(
                torrent,
                source_relative,
            ),
            "new_rel": str(expected.get("new_rel") or expected.get("relative_path") or ""),
            "local_hardlink_path": str(link.get("path") or ""),
            "inventory_path": str(inventory.get("path") or ""),
            "inventory_exists": inventory_exists,
            "file_size": max(0, int(expected.get("size") or 0)),
            "state": "existing" if inventory_exists else "planned",
            "details": {
                "inventory_status": str(checked.get("status") or ""),
                "matched_inventory_path": str(checked.get("matched_path") or ""),
                "recognition": expected.get("recognition") or {},
            },
        })
    return mappings


def build_realtime_source_mappings(
    *,
    downloader_id: str,
    info_hash: str,
    media_id: str,
    files: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build source-only mappings when MP recognition cannot plan an import."""

    mappings: List[Dict[str, Any]] = []
    for fallback_index, item in enumerate(files or []):
        source_text = str(item.get("current_source_path") or "").strip()
        if not source_text:
            continue
        source = Path(source_text).expanduser()
        if source.suffix.casefold() not in REALTIME_MEDIA_EXTENSIONS:
            continue
        try:
            file_index = int(item.get("index", fallback_index))
        except (TypeError, ValueError):
            file_index = fallback_index
        mappings.append({
            "downloader_id": str(downloader_id or ""),
            "info_hash": str(info_hash or "").lower(),
            "file_index": file_index,
            "media_id": str(media_id or ""),
            "source_relative_path": str(item.get("name") or source.name),
            "current_source_path": source_text,
            "new_rel": "",
            "local_hardlink_path": "",
            "inventory_path": "",
            "inventory_exists": False,
            "file_size": max(0, int(item.get("size") or 0)),
            "state": "planned",
            "details": {},
        })
    return mappings


def bind_local_source_paths(
    mappings: Sequence[Dict[str, Any]],
    files: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Bind planned names to source paths verified by the local filesystem scan."""

    updated = copy.deepcopy(list(mappings or []))
    local_files = list(files or [])
    if not updated or not local_files:
        return updated

    by_index: Dict[int, Dict[str, Any]] = {}
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    by_basename: Dict[str, List[Dict[str, Any]]] = {}
    for fallback_index, item in enumerate(local_files):
        source_path = str(item.get("current_source_path") or "").strip()
        if not source_path:
            continue
        try:
            file_index = int(item.get("index", fallback_index))
        except (TypeError, ValueError):
            file_index = fallback_index
        by_index[file_index] = item
        name = str(item.get("name") or "").replace("\\", "/").casefold()
        if name:
            by_name.setdefault(name, []).append(item)
            by_basename.setdefault(PurePosixPath(name).name, []).append(item)

    for fallback_index, mapping in enumerate(updated):
        try:
            file_index = int(mapping.get("file_index", fallback_index))
        except (TypeError, ValueError):
            file_index = fallback_index
        relative = str(
            mapping.get("source_relative_path") or ""
        ).replace("\\", "/").casefold()
        candidate = by_index.get(file_index)
        if candidate is None and len(by_name.get(relative, [])) == 1:
            candidate = by_name[relative][0]
        basename = PurePosixPath(relative).name if relative else ""
        if candidate is None and len(by_basename.get(basename, [])) == 1:
            candidate = by_basename[basename][0]
        source_path = str(
            (candidate or {}).get("current_source_path") or ""
        ).strip()
        if source_path:
            mapping["current_source_path"] = source_path
    return updated


def create_realtime_hardlinks(
    *,
    content_path: object,
    file_mappings: Sequence[Dict[str, Any]],
    source_root: object,
    link_root: object,
) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
    """Mirror completed qB media files as hardlinks while preserving identity."""

    source_root_text = str(source_root or "").strip()
    link_root_text = str(link_root or "").strip()
    if not source_root_text or not link_root_text:
        raise ValueError("实时硬链接必须同时配置源根目录和目标根目录")
    source_base_input = Path(source_root_text).expanduser()
    if not source_base_input.is_absolute():
        raise ValueError("实时硬链接源根目录必须是绝对路径")
    source_base = source_base_input.resolve(strict=True)
    if not source_base.is_dir():
        raise ValueError(f"实时硬链接源根目录不存在：{source_root_text}")
    link_base = Path(link_root_text).expanduser()
    if not link_base.is_absolute():
        raise ValueError("实时硬链接目标根目录必须是绝对路径")
    link_base.mkdir(parents=True, exist_ok=True)
    link_base = link_base.resolve(strict=True)
    if source_base == link_base:
        raise ValueError("实时硬链接源根目录和目标根目录不能相同")
    if not file_mappings:
        raise ValueError("没有可用于实时硬链接的媒体文件映射")

    created: List[Path] = []
    linked_files: List[Dict[str, Any]] = []
    updated_mappings: List[Dict[str, Any]] = []
    try:
        for mapping in file_mappings:
            original_source = str(mapping.get("current_source_path") or "").strip()
            if not original_source:
                raise ValueError("实时硬链接文件缺少 qB 源路径")
            source = Path(original_source).expanduser().resolve(strict=True)
            if not source.is_file():
                raise ValueError(f"实时硬链接源文件不存在：{original_source}")
            try:
                relative = source.relative_to(source_base)
            except ValueError as error:
                raise ValueError(
                    f"qB 源文件不在实时硬链接源根目录内：{original_source}"
                ) from error
            target = link_base.joinpath(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target_parent = target.parent.resolve(strict=True)
            target = target_parent.joinpath(target.name)
            try:
                target.relative_to(link_base)
            except ValueError as error:
                raise ValueError(f"实时硬链接目标越界：{target}") from error

            reused = False
            if target.exists():
                if not target.is_file() or not os.path.samefile(source, target):
                    raise FileExistsError(f"实时硬链接目标已存在且不是同一文件：{target}")
                reused = True
            else:
                os.link(source, target)
                created.append(target)

            updated = copy.deepcopy(mapping)
            updated["current_source_path"] = str(target)
            updated["state"] = "realtime_linked"
            updated_details = dict(updated.get("details") or {})
            updated_details.update({
                "qb_source_path": str(source),
                "realtime_hardlink_path": str(target),
                "realtime_hardlink_reused": reused,
            })
            updated["details"] = updated_details
            updated_mappings.append(updated)
            linked_files.append({
                "file_index": updated.get("file_index"),
                "source": str(source),
                "target": str(target),
                "reused": reused,
            })
    except Exception:
        for target in reversed(created):
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    mapped_content_path = _map_realtime_content_path(
        content_path,
        source_base,
        link_base,
        linked_files,
    )
    return updated_mappings, mapped_content_path, {
        "enabled": True,
        "state": "linked",
        "source_root": str(source_base),
        "link_root": str(link_base),
        "content_path": mapped_content_path,
        "files": linked_files,
        "created_count": sum(1 for item in linked_files if not item["reused"]),
        "reused_count": sum(1 for item in linked_files if item["reused"]),
        "completed_at": utc_now(),
    }


def _map_realtime_content_path(
    content_path: object,
    source_root: Path,
    link_root: Path,
    linked_files: Sequence[Dict[str, Any]],
) -> str:
    raw_content = str(content_path or "").strip()
    if raw_content:
        try:
            content = Path(raw_content).expanduser().resolve(strict=False)
            return str(link_root.joinpath(content.relative_to(source_root)))
        except ValueError:
            pass
    targets = [Path(str(item.get("target") or "")) for item in linked_files]
    if len(targets) == 1:
        return str(targets[0])
    if targets:
        return os.path.commonpath([str(item.parent) for item in targets])
    return str(link_root)


def resolve_current_source_path(
    torrent: Dict[str, Any],
    source_relative_path: str,
) -> str:
    source = PurePosixPath(str(source_relative_path or "").replace("\\", "/"))
    save_path = str(torrent.get("save_path") or "").strip().replace("\\", "/")
    if save_path:
        return PurePosixPath(save_path).joinpath(source).as_posix()

    content_value = str(
        torrent.get("content_path") or torrent.get("path") or ""
    ).strip().replace("\\", "/")
    if not content_value:
        return source.as_posix()
    content = PurePosixPath(content_value)
    if content.name.casefold() == source.name.casefold() and len(source.parts) == 1:
        return content.as_posix()
    if source.parts and content.name.casefold() == source.parts[0].casefold():
        return content.parent.joinpath(source).as_posix()
    return content.joinpath(source).as_posix()


def _discover_local_torrent_files(content_path: object) -> List[Dict[str, Any]]:
    """Read a completed download directly from the filesystem when available."""

    raw = str(content_path or "").strip()
    if not raw:
        return []
    source = Path(raw).expanduser()
    try:
        source = source.resolve(strict=True)
    except OSError:
        return []
    try:
        paths = [source] if source.is_file() else sorted(
            (item for item in source.rglob("*") if item.is_file()),
            key=lambda item: item.as_posix().casefold(),
        )
    except OSError:
        return []
    result = []
    for index, path in enumerate(paths):
        try:
            relative = (
                path.name
                if source.is_file()
                else path.relative_to(source.parent).as_posix()
            )
            size = path.stat().st_size
        except OSError:
            continue
        result.append({
            "index": index,
            "name": relative,
            "size": size,
            "priority": 1,
            "current_source_path": str(path),
        })
    return result


def _local_recognition_title(
    content_path: object,
    files: Sequence[Dict[str, Any]],
) -> str:
    if not files:
        return ""
    raw = str(content_path or "").strip()
    if raw:
        name = Path(raw).name.strip()
        if name:
            return name
    if files:
        return Path(str(files[0].get("name") or "")).name
    return ""


def _saved_local_torrent_files(
    item: Dict[str, Any],
    mappings: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    result = []
    for fallback_index, mapping in enumerate(mappings or []):
        raw_path = str(mapping.get("current_source_path") or "").strip()
        if not raw_path:
            continue
        path = Path(raw_path).expanduser()
        try:
            path = path.resolve(strict=True)
            if not path.is_file():
                continue
            size = path.stat().st_size
        except OSError:
            continue
        try:
            file_index = int(mapping.get("file_index", fallback_index))
        except (TypeError, ValueError):
            file_index = fallback_index
        result.append({
            "index": file_index,
            "name": str(mapping.get("source_relative_path") or path.name),
            "size": size,
            "priority": 1,
            "current_source_path": str(path),
        })
    if result:
        return sorted(result, key=lambda value: int(value["index"]))
    return _discover_local_torrent_files(item.get("source_path") or "")


def _repair_saved_local_source_paths(
    item: Dict[str, Any],
    mappings: Sequence[Dict[str, Any]],
) -> bool:
    """Repair a renamed local source only when its replacement is unambiguous."""

    changed = False
    claimed: set[str] = set()
    for mapping in mappings or []:
        current_text = str(mapping.get("current_source_path") or "").strip()
        if not current_text:
            continue
        current = Path(current_text).expanduser()
        try:
            if current.is_file():
                claimed.add(os.path.normcase(str(current.resolve(strict=True))))
                continue
        except OSError:
            pass

        parent = current.parent
        try:
            if not parent.is_dir():
                continue
            candidates = [
                path for path in parent.iterdir()
                if path.is_file()
                and path.suffix.casefold() == current.suffix.casefold()
                and os.path.normcase(str(path.resolve(strict=False))) not in claimed
            ]
        except OSError:
            continue

        try:
            expected_size = int(mapping.get("file_size") or 0)
        except (TypeError, ValueError):
            expected_size = 0
        if expected_size > 0:
            size_matches = []
            for candidate in candidates:
                try:
                    if candidate.stat().st_size == expected_size:
                        size_matches.append(candidate)
                except OSError:
                    continue
            candidates = size_matches
        if len(candidates) != 1:
            continue

        replacement = candidates[0].resolve(strict=True)
        mapping["current_source_path"] = str(replacement)
        relative_text = str(mapping.get("source_relative_path") or "").replace(
            "\\", "/"
        )
        relative = PurePosixPath(relative_text)
        mapping["source_relative_path"] = (
            relative.with_name(replacement.name).as_posix()
            if relative_text and relative.name
            else replacement.name
        )
        mapping_details = dict(mapping.get("details") or {})
        mapping_details.update({
            "source_path_repaired_from": current_text,
            "source_path_repaired_at": utc_now(),
        })
        mapping["details"] = mapping_details
        claimed.add(os.path.normcase(str(replacement)))
        changed = True
    return changed


def _refreshed_item_source_path(
    item: Dict[str, Any],
    files: Sequence[Dict[str, Any]],
) -> str:
    source_text = str(item.get("source_path") or "").strip()
    if not source_text or len(files) != 1:
        return ""
    source = Path(source_text).expanduser()
    try:
        if source.exists():
            return ""
    except OSError:
        pass
    actual_text = str(files[0].get("current_source_path") or "").strip()
    if not actual_text:
        return ""
    actual = Path(actual_text).expanduser()
    try:
        if not actual.is_file():
            return ""
        return str(actual.resolve(strict=True))
    except OSError:
        return ""


def _saved_local_recognition_title(
    item: Dict[str, Any],
    files: Sequence[Dict[str, Any]],
) -> str:
    source_path = str(item.get("source_path") or "").strip()
    if source_path:
        source = Path(source_path).expanduser()
        try:
            if source.resolve(strict=True).is_dir():
                return source.name
        except OSError:
            pass
    actual_paths = [
        Path(str(file.get("current_source_path") or ""))
        for file in files
        if str(file.get("current_source_path") or "").strip()
    ]
    if len(actual_paths) > 1:
        try:
            common = Path(os.path.commonpath([str(path.parent) for path in actual_paths]))
            if common.name:
                return common.name
        except ValueError:
            pass
    if actual_paths:
        return actual_paths[0].name
    return str(item.get("source_name") or item.get("title") or "").strip()


def _restore_saved_source_paths(
    refreshed: Sequence[Dict[str, Any]],
    saved: Sequence[Dict[str, Any]],
    local_files: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    saved_by_index = {
        int(item.get("file_index", index)): item
        for index, item in enumerate(saved or [])
    }
    local_by_index = {
        int(item.get("index", index)): item
        for index, item in enumerate(local_files or [])
    }
    result = []
    for index, mapping in enumerate(refreshed or []):
        try:
            file_index = int(mapping.get("file_index", index))
        except (TypeError, ValueError):
            file_index = index
        previous = saved_by_index.get(file_index) or {}
        local = local_by_index.get(file_index) or {}
        updated = copy.deepcopy(mapping)
        updated["current_source_path"] = str(
            local.get("current_source_path")
            or previous.get("current_source_path")
            or updated.get("current_source_path")
            or ""
        )
        previous_details = dict(previous.get("details") or {})
        previous_details.update(updated.get("details") or {})
        updated["details"] = previous_details
        result.append(updated)
    return result


def _index_planned_files(
    items: Sequence[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for fallback_index, item in enumerate(items or []):
        result[_planned_file_key(item, fallback_index)] = item
        source_name = str(item.get("source_name") or "").replace("\\", "/")
        if source_name:
            result.setdefault(source_name.casefold(), item)
    return result


def _planned_file_key(item: Dict[str, Any], fallback_index: int) -> str:
    file_index = item.get("file_index")
    if file_index is not None:
        try:
            return f"index:{int(file_index)}"
        except (TypeError, ValueError):
            pass
    source_name = str(item.get("source_name") or "").replace("\\", "/")
    return source_name.casefold() or f"fallback:{fallback_index}"


def _valid_tmdb_id(value: object) -> bool:
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        return False


def preserve_refresh_workflow_state(previous_state: object, refreshed_state: object) -> str:
    """Keep queue and rollback states while refreshing recognition data."""

    previous = str(previous_state or "").strip()
    refreshed = str(refreshed_state or "").strip()
    if previous in {"pending", "pending_import", "rolled_back"} and refreshed in {
        "identified",
        "existing",
    }:
        return previous
    return refreshed


def _normalize_manual_override(value: object) -> Dict[str, Any]:
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
        "tmdb_id": tmdb_id if tmdb_id > 0 else None,
        "season": season,
        "category": LibraryLayout.canonical_category(raw.get("category") or ""),
    }
