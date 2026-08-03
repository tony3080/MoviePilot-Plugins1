"""Read-only qBittorrent synchronization through MoviePilot runtime services."""

from __future__ import annotations

import copy
import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .database import SQLiteStore, utc_now
from .inventory import LocalInventoryChecker
from .layout import LibraryLayout


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "downloader": self.downloader,
            "category": self.category,
            "enabled": self.enabled,
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
    def torrent_dict(torrent: Any) -> Dict[str, Any]:
        if hasattr(torrent, "model_dump"):
            return torrent.model_dump(mode="json")
        if isinstance(torrent, dict):
            return dict(torrent)
        return dict(vars(torrent))

    @staticmethod
    def list_torrent_files(downloader: str, info_hash: str) -> List[Any]:
        from app.chain.download import DownloadChain

        files = DownloadChain().torrent_files(
            tid=info_hash,
            downloader=downloader,
        )
        if files is None:
            raise RuntimeError(f"读取 qBittorrent 文件清单失败：{downloader}/{info_hash}")
        return list(files)

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
        media = MediaChain().recognize_by_meta(meta, obtain_images=False)
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

        return MetaInfo(title=title)

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
        for file_item in torrent_files:
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
            candidates.append({"source_name": name, "size": size})

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
            current = getattr(file_meta, field, None)
            fallback = getattr(torrent_meta, field, None)
            if MoviePilotQbGateway._has_meta_value(current):
                continue
            if not MoviePilotQbGateway._has_meta_value(fallback):
                continue
            setattr(file_meta, field, copy.deepcopy(fallback))
            inherited.append(field)

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

    def run(
        self,
        task_id: str,
        *,
        force_recognition: bool = False,
        stop_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "downloaders": 0,
            "scanned": 0,
            "filtered_out": 0,
            "recognized": 0,
            "unrecognized": 0,
            "existing": 0,
            "errors": [],
        }
        scope = RssTaskQbScope.from_tasks(self.store.list_all_rss_tasks())
        result["managed_scope"] = scope.to_dict()
        result["out_of_scope"] = self.store.mark_torrents_outside_scope(
            scope.downloader_categories(),
            utc_now(),
        )
        if not scope.ready:
            message = "VT+ 没有已保存且同时配置 QB下载器、QB分类的 RSS 任务"
            result["errors"].append({"message": message})
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
                return self._cancel(task_id, result)
            categories = scope.categories_for(downloader.name)
            if not categories:
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
                torrents = [
                    item for item in all_torrents
                    if scope.matches(downloader.name, item.get("category") or "")
                ]
                result["filtered_out"] += len(all_torrents) - len(torrents)
                seen_at = utc_now()
                seen_hashes = [
                    str(item.get("hash") or "").lower()
                    for item in torrents
                ]
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

        for downloader, torrents in batches:
            for raw in torrents:
                if stop_event and stop_event.is_set():
                    return self._cancel(task_id, result)
                title = str(raw.get("title") or raw.get("name") or "").strip()
                info_hash = str(raw.get("hash") or "").strip().lower()
                processed += 1
                if not info_hash:
                    failed += 1
                    result["errors"].append({
                        "downloader": downloader.name,
                        "title": title,
                        "message": "qB 任务缺少 info-hash",
                    })
                    self._update_progress(
                        task_id, title, processed, succeeded, failed, total, result
                    )
                    continue
                try:
                    outcome = self._sync_one(
                        downloader=downloader,
                        raw=raw,
                        force_recognition=force_recognition,
                    )
                    succeeded += 1
                    result["scanned"] += 1
                    result[outcome] += 1
                except Exception as error:
                    failed += 1
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

        state = "succeeded" if batches else "failed"
        error_message = "" if batches else "所有 qBittorrent 节点均读取失败"
        self.store.finish_background_task(
            task_id, state, result=result, error_message=error_message
        )
        return result

    def _sync_one(
        self,
        *,
        downloader: DownloaderView,
        raw: Dict[str, Any],
        force_recognition: bool,
    ) -> str:
        now = utc_now()
        info_hash = str(raw.get("hash") or "").strip().lower()
        title = str(raw.get("title") or raw.get("name") or "").strip()
        content_path = str(raw.get("content_path") or raw.get("path") or "")
        signature = hashlib.sha256(
            f"{title}\n{content_path}".encode("utf-8")
        ).hexdigest()
        existing = self.store.get_torrent_snapshot(downloader.name, info_hash) or {}
        existing_details = existing.get("details") or {}
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
            meta, media = self.gateway.recognize(title)
        else:
            media = self.gateway.restore_media(media_payload)
            if media:
                meta = self.gateway.restore_meta(
                    title, existing_details.get("meta") or {}
                )
            else:
                meta, media = self.gateway.recognize(title)

        media_id = f"qb:{downloader.name}:{info_hash}"
        recognition_error = ""
        inventory_state = "unknown"
        inventory_details: Dict[str, Any] = {}
        inventory_plan: Dict[str, Any] = {}
        path_plan: Dict[str, Any] = {}
        if media:
            media_type = self.gateway.media_type(media)
            media_payload = self.gateway.media_payload(media)
            meta_payload = self.gateway.meta_payload(meta)
            media_title = str(getattr(media, "title", "") or "")
            media_year = str(getattr(media, "year", "") or "")
            tmdb_id = getattr(media, "tmdb_id", None)
            season = getattr(media, "season", None)
            if season is None:
                season = getattr(meta, "begin_season", None)
            category = str(getattr(media, "category", "") or "")
            poster = self.gateway.poster(media)
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
                    torrent_files = self.gateway.list_torrent_files(
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
                except Exception as error:
                    inventory_state = "unknown"
                    inventory_details = {
                        "method": "tmdb_strm_features",
                        "scope": "mp_library_path",
                        "error": str(error),
                    }
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
            tmdb_id = None
            season = getattr(meta, "begin_season", None) if meta else None
            category = ""
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
        }
        target_name = ""
        if path_plan.get("inventory_files"):
            target_name = str(path_plan["inventory_files"][0].get("path") or "")
        if not target_name:
            target_name = str(inventory_plan.get("inventory_target_name") or "")
        self.store.upsert_media_item({
            "id": media_id,
            "state": media_state,
            "media_type": media_type,
            "title": media_title or title,
            "source_name": title,
            "source_path": content_path,
            "downloader_id": downloader.name,
            "info_hash": info_hash,
            "tmdb_id": tmdb_id,
            "season": season,
            "category": category,
            "target_name": target_name,
            "failure_code": (
                "recognition_failed"
                if not media
                else "missing_tmdb_id"
                if not _valid_tmdb_id(tmdb_id)
                else ""
            ),
            "failure_message": recognition_error,
            "details": details,
            "updated_at": now,
        })
        self.store.upsert_torrent_snapshot({
            "downloader_id": downloader.name,
            "info_hash": info_hash,
            "name": title,
            "state": str(raw.get("state") or ""),
            "category": str(raw.get("category") or ""),
            "content_path": content_path,
            "progress": float(raw.get("progress") or 0),
            "size": int(raw.get("size") or 0),
            "media_id": media_id,
            "source_url_masked": "",
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

    def _cancel(self, task_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        self.store.finish_background_task(
            task_id,
            "cancelled",
            result=result,
            error_message="插件停止，刷新任务已取消",
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


def _valid_tmdb_id(value: object) -> bool:
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        return False
