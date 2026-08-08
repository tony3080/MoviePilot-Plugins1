"""Stateful media-card actions backed by persisted source/target mappings."""

from __future__ import annotations

import copy
import os
import threading
import uuid
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .database import SQLiteStore, utc_now
from .domain import can_transition
from .inventory import LocalInventoryChecker
from .layout import LibraryLayout


class MediaActionError(RuntimeError):
    """Raised when a requested card action cannot be completed safely."""


class MediaActionService:
    """Execute library-card operations without inferring paths from names."""

    ACTIONS = {
        "queue_import",
        "import",
        "delete_source",
        "delete_hardlinks",
        "delete_both",
    }
    DESTRUCTIVE_ACTIONS = {"delete_source", "delete_hardlinks", "delete_both"}
    _destructive_lock = threading.RLock()

    def __init__(
        self,
        store: SQLiteStore,
        library_layout: Optional[LibraryLayout] = None,
    ):
        self.store = store
        self.library_layout = library_layout

    def execute(self, action: object, media_ids: Iterable[object]) -> Dict[str, Any]:
        normalized_action = str(action or "").strip().casefold()
        if normalized_action not in self.ACTIONS:
            raise MediaActionError(f"不支持的媒体操作：{normalized_action or '<empty>'}")
        identities = []
        for value in media_ids or []:
            identity = str(value or "").strip()
            if identity and identity not in identities:
                identities.append(identity)
        if not identities:
            raise MediaActionError("请至少选择一个媒体项目")

        results = []
        for media_id in identities:
            try:
                result = self._execute_one(normalized_action, media_id)
                results.append({"media_id": media_id, "success": True, **result})
            except Exception as error:
                results.append({
                    "media_id": media_id,
                    "success": False,
                    "message": str(error),
                })
        succeeded = sum(1 for item in results if item["success"])
        return {
            "success": succeeded == len(results),
            "partial": 0 < succeeded < len(results),
            "action": normalized_action,
            "total": len(results),
            "succeeded": succeeded,
            "failed": len(results) - succeeded,
            "results": results,
        }

    def _execute_one(self, action: str, media_id: str) -> Dict[str, Any]:
        item = self.store.get_media_item(media_id)
        if not item:
            raise MediaActionError("媒体记录不存在")
        if action == "queue_import":
            return self._queue_import(item)
        if action == "import":
            return self._import(item)
        mappings = self._mappings(item)
        if action == "delete_source":
            return self._delete_source(item, mappings)
        if action == "delete_hardlinks":
            return self._delete_hardlinks(item, mappings)
        return self._delete_both(item, mappings)

    def prepare_monitored_import(self, media_id: object) -> Dict[str, Any]:
        item = self.store.get_media_item(media_id)
        if not item:
            raise MediaActionError("媒体记录不存在")
        return self._import(item, finalize=False)

    def finalize_monitored_import(self, media_id: object) -> Dict[str, Any]:
        item = self.store.get_media_item(media_id)
        if not item:
            raise MediaActionError("媒体记录不存在")
        if str(item.get("state") or "") == "imported":
            return {"message": "项目已经入库", "state": "imported"}
        if str(item.get("state") or "") != "importing":
            raise MediaActionError("只有入库中的项目可以完成 CD2 入库")
        completed = copy.deepcopy(item)
        details = dict(completed.get("details") or {})
        import_result = dict(details.get("import_result") or {})
        import_result.update({"state": "imported", "completed_at": utc_now()})
        details["import_result"] = import_result
        completed.update({
            "state": "imported",
            "failure_code": "",
            "failure_message": "",
            "rolled_back": False,
            "details": details,
            "updated_at": utc_now(),
        })
        self.store.upsert_media_item(completed)
        return {"message": "CD2 秒传监控完成", "state": "imported"}

    def rollback_monitored_import(
        self,
        media_id: object,
        *,
        failure_code: str,
        failure_message: str,
    ) -> Dict[str, Any]:
        item = self.store.get_media_item(media_id)
        if not item:
            raise MediaActionError("媒体记录不存在")
        mappings = self._mappings(item)
        updated = copy.deepcopy(mappings)
        operation_id = str(
            ((item.get("details") or {}).get("import_result") or {}).get("operation_id")
            or ""
        )
        deleted = 0
        missing = 0
        for mapping in updated:
            details = dict(mapping.get("details") or {})
            if (
                not details.get("hardlink_created_in_operation")
                or str(details.get("hardlink_operation_id") or "") != operation_id
            ):
                continue
            target_text = str(mapping.get("local_hardlink_path") or "").strip()
            target = Path(target_text).expanduser()
            source_text = str(mapping.get("current_source_path") or "").strip()
            source = Path(source_text).expanduser()
            if target.exists():
                if not target.is_file():
                    raise MediaActionError(f"回滚目标不是普通文件：{target}")
                if source.exists() and not os.path.samefile(source, target):
                    raise MediaActionError(f"回滚目标已不再指向原始源文件：{target}")
                target.unlink()
                deleted += 1
            else:
                missing += 1
            details.update({
                "hardlink_owned": False,
                "hardlink_created_in_operation": False,
                "hardlink_deleted_at": utc_now(),
            })
            mapping.update({"state": "rolled_back", "details": details})
        self.store.replace_file_mappings(
            item.get("downloader_id"), item.get("info_hash"), updated
        )
        rolled_back = copy.deepcopy(item)
        details = dict(rolled_back.get("details") or {})
        details["rollback"] = {
            "reason": failure_message,
            "deleted_count": deleted,
            "missing_count": missing,
            "completed_at": utc_now(),
        }
        rolled_back.update({
            "state": "identified",
            "failure_code": str(failure_code or "cd2_import_failed"),
            "failure_message": str(failure_message or "CD2 入库失败"),
            "rolled_back": False,
            "details": details,
            "updated_at": utc_now(),
        })
        self.store.upsert_media_item(rolled_back)
        return {
            "message": f"已回滚本次硬链接 {deleted} 个，缺失 {missing} 个",
            "state": "identified",
            "deleted": deleted,
            "missing": missing,
        }

    def _queue_import(self, item: Dict[str, Any]) -> Dict[str, Any]:
        state = str(item.get("state") or "")
        if state == "pending":
            return {"message": "已经处于待入库状态", "state": state}
        if state not in {"identified", "rolled_back"}:
            raise MediaActionError("只有已识别或已回退项目可以转为待入库")
        if not can_transition(state, "pending"):
            raise MediaActionError(f"不允许从 {state} 转为 pending")
        updated = copy.deepcopy(item)
        details = dict(updated.get("details") or {})
        details["pending_import"] = {
            "queued_at": utc_now(),
        }
        updated.update({
            "state": "pending",
            "failure_code": "",
            "failure_message": "",
            "details": details,
            "updated_at": utc_now(),
        })
        self.store.upsert_media_item(updated)
        return {"message": "已转为待入库", "state": "pending"}

    def _import(self, item: Dict[str, Any], *, finalize: bool = True) -> Dict[str, Any]:
        original_state = str(item.get("state") or "")
        if original_state == "imported":
            return {"message": "项目已经入库", "state": "imported"}
        if original_state == "unidentified":
            raise MediaActionError("未识别项目不能入库")
        if original_state == "existing":
            raise MediaActionError("库存已经完整，无需创建硬链接")
        if original_state not in {"identified", "pending", "rolled_back"}:
            raise MediaActionError(f"状态 {original_state or '<empty>'} 不能入库")
        if not can_transition(original_state, "importing"):
            raise MediaActionError(f"不允许从 {original_state} 转为 importing")

        mappings = self._mappings(item)
        missing = [mapping for mapping in mappings if not mapping.get("inventory_exists")]
        if not mappings:
            raise MediaActionError("没有持久化的文件映射，无法安全入库")
        if not missing and finalize:
            raise MediaActionError("所有文件均已存在于库存，无需创建硬链接")

        working = copy.deepcopy(item)
        working.update({
            "state": "importing",
            "failure_code": "",
            "failure_message": "",
            "updated_at": utc_now(),
        })
        self.store.upsert_media_item(working)

        created: List[Path] = []
        operation_id = uuid.uuid4().hex
        updated_mappings = copy.deepcopy(mappings)
        created_count = 0
        reused_count = 0
        skipped_count = 0
        try:
            for mapping in updated_mappings:
                if mapping.get("inventory_exists"):
                    mapping["state"] = "existing"
                    skipped_count += 1
                    continue
                source, target = self._source_target(mapping)
                target.parent.mkdir(parents=True, exist_ok=True)
                target = target.parent.resolve(strict=True).joinpath(target.name)
                if source == target:
                    raise MediaActionError(f"硬链接源和目标不能相同：{source}")

                details = dict(mapping.get("details") or {})
                if target.exists():
                    if not target.is_file() or not os.path.samefile(source, target):
                        raise FileExistsError(f"硬链接目标已存在且不是同一文件：{target}")
                    owned = bool(details.get("hardlink_owned"))
                    if not finalize and not owned:
                        raise FileExistsError(
                            f"待入库目标已存在但不属于当前插件记录：{target}"
                        )
                    reused_count += 1
                else:
                    os.link(source, target)
                    created.append(target)
                    created_count += 1
                    owned = True
                details.update({
                    "hardlink_owned": owned,
                    "hardlink_reused": target not in created,
                    "hardlink_created_in_operation": target in created,
                    "hardlink_operation_id": operation_id,
                    "hardlink_created_at": utc_now(),
                })
                mapping.update({
                    "local_hardlink_path": str(target),
                    "state": "hardlinked" if owned else "linked_existing",
                    "details": details,
                })
        except Exception as error:
            for target in reversed(created):
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
            failed = copy.deepcopy(item)
            failed.update({
                "state": original_state,
                "failure_code": "hardlink_import_failed",
                "failure_message": str(error),
                "updated_at": utc_now(),
            })
            self.store.upsert_media_item(failed)
            raise

        persisted = self.store.replace_file_mappings(
            item.get("downloader_id"), item.get("info_hash"), updated_mappings
        )
        completed = copy.deepcopy(item)
        details = dict(completed.get("details") or {})
        details["import_result"] = {
            "state": "imported" if finalize else "monitoring",
            "operation_id": operation_id,
            "created_count": created_count,
            "reused_count": reused_count,
            "inventory_skipped_count": skipped_count,
            "completed_at": utc_now(),
        }
        completed.update({
            "state": "imported" if finalize else "importing",
            "failure_code": "",
            "failure_message": "",
            "rolled_back": False,
            "details": details,
            "updated_at": utc_now(),
        })
        self.store.upsert_media_item(completed)
        return {
            "message": (
                f"{'入库完成' if finalize else '硬链接已创建，等待 CD2'}："
                f"新建 {created_count}，复用 {reused_count}，"
                f"库存跳过 {skipped_count}"
            ),
            "state": "imported" if finalize else "importing",
            "created": created_count,
            "reused": reused_count,
            "skipped": skipped_count,
            "mappings": len(persisted),
            "operation_id": operation_id,
            "created_mappings": [
                mapping for mapping in persisted
                if (mapping.get("details") or {}).get("hardlink_operation_id") == operation_id
                and (mapping.get("details") or {}).get("hardlink_created_in_operation")
            ],
        }

    def _delete_source(
        self, item: Dict[str, Any], mappings: Sequence[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if str(item.get("state") or "") == "imported":
            raise MediaActionError("已入库项目请使用“删除硬链接和源文件”")
        with self._destructive_lock:
            protected = self._shared_source_paths(item, mappings)
            deleted, missing, preserved, cleaned = self._unlink_sources(
                mappings,
                preserved_paths=protected,
                stop_roots=self._source_cleanup_roots(mappings),
            )
            self.store.delete_media_item(item.get("id"))
        return {
            "message": (
                f"已删除源文件 {deleted} 个，缺失 {missing} 个，"
                f"保留共享源文件 {preserved} 个，清理空目录 {cleaned} 个，并移除记录"
            ),
            "deleted": deleted,
            "missing": missing,
            "preserved": preserved,
            "directories_cleaned": cleaned,
            "state": "deleted",
        }

    def _delete_hardlinks(
        self, item: Dict[str, Any], mappings: Sequence[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if str(item.get("state") or "") != "imported":
            raise MediaActionError("只有已入库项目可以删除硬链接")
        with self._destructive_lock:
            updated, deleted, missing, preserved, cleaned = self._unlink_hardlinks(
                mappings,
                stop_roots=self._hardlink_cleanup_roots(item, mappings),
                max_levels=self._hardlink_cleanup_levels(item),
            )
            self.store.replace_file_mappings(
                item.get("downloader_id"), item.get("info_hash"), updated
            )
            rolled_back = copy.deepcopy(item)
            details = dict(rolled_back.get("details") or {})
            details["rollback"] = {
                "reason": "只删除硬链接",
                "deleted_count": deleted,
                "missing_count": missing,
                "preserved_count": preserved,
                "completed_at": utc_now(),
            }
            rolled_back.update({
                "state": "rolled_back",
                "rolled_back": True,
                "failure_code": "",
                "failure_message": "",
                "details": details,
                "updated_at": utc_now(),
            })
            self.store.upsert_media_item(rolled_back)
        return {
            "message": (
                f"已删除插件创建的硬链接 {deleted} 个，"
                f"缺失 {missing} 个，保留非插件目标 {preserved} 个，"
                f"清理空目录 {cleaned} 个"
            ),
            "deleted": deleted,
            "missing": missing,
            "preserved": preserved,
            "directories_cleaned": cleaned,
            "state": "rolled_back",
        }

    def _delete_both(
        self, item: Dict[str, Any], mappings: Sequence[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if str(item.get("state") or "") != "imported":
            raise MediaActionError("只有已入库项目可以执行硬链接和源文件双删")
        with self._destructive_lock:
            self._validated_source_paths(mappings)
            self._validated_owned_hardlinks(mappings)
            protected = self._shared_source_paths(item, mappings)
            _updated, links_deleted, links_missing, preserved, link_dirs = (
                self._unlink_hardlinks(
                    mappings,
                    stop_roots=self._hardlink_cleanup_roots(item, mappings),
                    max_levels=self._hardlink_cleanup_levels(item),
                )
            )
            (
                sources_deleted,
                sources_missing,
                shared_sources,
                source_dirs,
            ) = self._unlink_sources(
                mappings,
                preserved_paths=protected,
                stop_roots=self._source_cleanup_roots(mappings),
            )
            cleanup = self.store.delete_completed_media_workflow(item.get("id"))
        return {
            "message": (
                f"双删完成：硬链接 {links_deleted}，源文件 {sources_deleted}，"
                f"缺失 {links_missing + sources_missing}，"
                f"保留非插件目标 {preserved}，保留共享源文件 {shared_sources}，"
                f"清理空目录 {link_dirs + source_dirs} 个"
            ),
            "hardlinks_deleted": links_deleted,
            "sources_deleted": sources_deleted,
            "missing": links_missing + sources_missing,
            "preserved": preserved,
            "shared_sources": shared_sources,
            "directories_cleaned": link_dirs + source_dirs,
            "database_cleanup": cleanup,
            "state": "deleted",
        }

    def _mappings(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        mappings = self.store.list_file_mappings(
            item.get("downloader_id"), item.get("info_hash")
        )
        if not mappings:
            raise MediaActionError("没有持久化的文件映射，拒绝猜测文件路径")
        return mappings

    @staticmethod
    def _source_target(mapping: Dict[str, Any]) -> Tuple[Path, Path]:
        source_text = str(mapping.get("current_source_path") or "").strip()
        target_text = str(mapping.get("local_hardlink_path") or "").strip()
        if not source_text or not target_text:
            raise MediaActionError("文件映射缺少源路径或硬链接目标路径")
        source = Path(source_text).expanduser()
        target = Path(target_text).expanduser()
        if not source.is_absolute() or not target.is_absolute():
            raise MediaActionError("源路径和硬链接目标路径必须是绝对路径")
        source = source.resolve(strict=True)
        if not source.is_file():
            raise MediaActionError(f"源文件不存在：{source_text}")
        return source, target

    @classmethod
    def _unlink_sources(
        cls,
        mappings: Sequence[Dict[str, Any]],
        *,
        preserved_paths: Iterable[Path] = (),
        stop_roots: Iterable[Path] = (),
    ) -> Tuple[int, int, int, int]:
        paths = cls._validated_source_paths(mappings)
        preserved_keys = {
            os.path.normcase(str(path.resolve(strict=False)))
            for path in preserved_paths or ()
        }
        deleted = 0
        missing = 0
        preserved = 0
        deleted_paths: List[Path] = []
        for path in paths:
            path_key = os.path.normcase(str(path.resolve(strict=False)))
            if path_key in preserved_keys:
                preserved += 1
                continue
            if not path.exists():
                missing += 1
                continue
            path.unlink()
            deleted += 1
            deleted_paths.append(path)
        cleaned = cls._cleanup_empty_parents(
            deleted_paths, stop_roots, max_levels=1
        )
        return deleted, missing, preserved, cleaned

    def _shared_source_paths(
        self,
        item: Dict[str, Any],
        mappings: Sequence[Dict[str, Any]],
    ) -> List[Path]:
        paths = self._validated_source_paths(mappings)
        media_id = str(item.get("id") or "").strip()
        shared = []
        for path in paths:
            owners = self.store.find_media_owners_by_source_paths(
                [str(path)], exclude_media_id=media_id
            )
            if owners:
                shared.append(path)
        return shared

    @classmethod
    def _unlink_hardlinks(
        cls,
        mappings: Sequence[Dict[str, Any]],
        *,
        stop_roots: Iterable[Path] = (),
        max_levels: int = 3,
    ) -> Tuple[List[Dict[str, Any]], int, int, int, int]:
        updated = copy.deepcopy(list(mappings))
        deleted = 0
        missing = 0
        preserved = 0
        deleted_paths: List[Path] = []
        cls._validated_owned_hardlinks(mappings)
        for mapping in updated:
            details = dict(mapping.get("details") or {})
            if not details.get("hardlink_owned"):
                preserved += 1
                continue
            target_text = str(mapping.get("local_hardlink_path") or "").strip()
            if not target_text:
                raise MediaActionError("插件创建的硬链接缺少持久化目标路径")
            target = Path(target_text).expanduser()
            if target.exists():
                target.unlink()
                deleted += 1
                deleted_paths.append(target)
            else:
                missing += 1
            details.update({
                "hardlink_owned": False,
                "hardlink_deleted_at": utc_now(),
            })
            mapping.update({"state": "rolled_back", "details": details})
        cleaned = cls._cleanup_empty_parents(
            deleted_paths, stop_roots, max_levels=max_levels
        )
        return updated, deleted, missing, preserved, cleaned

    def _source_cleanup_roots(
        self, mappings: Sequence[Dict[str, Any]]
    ) -> List[Path]:
        if not self.library_layout:
            return []
        roots: List[Path] = []
        for mapping in mappings:
            source = str(mapping.get("current_source_path") or "").strip()
            route = self.library_layout.select_route(source)
            if route:
                roots.append(Path(route.prefix).expanduser())
        return self._unique_paths(roots)

    def _hardlink_cleanup_roots(
        self,
        item: Dict[str, Any],
        mappings: Sequence[Dict[str, Any]],
    ) -> List[Path]:
        if not self.library_layout:
            return []
        roots: List[Path] = []
        for mapping in mappings:
            source = str(mapping.get("current_source_path") or "").strip()
            root, _error = self.library_layout.link_base(
                source,
                item.get("category") or "",
                item.get("media_type") or "",
            )
            if root:
                roots.append(Path(root).expanduser())
        return self._unique_paths(roots)

    @staticmethod
    def _hardlink_cleanup_levels(item: Dict[str, Any]) -> int:
        return 1 if str(item.get("media_type") or "").casefold() == "movie" else 3

    @classmethod
    def _cleanup_empty_parents(
        cls,
        deleted_paths: Iterable[Path],
        stop_roots: Iterable[Path],
        *,
        max_levels: int,
    ) -> int:
        if max_levels <= 0:
            return 0
        roots = [path.resolve(strict=False) for path in cls._unique_paths(stop_roots)]
        if not roots:
            return 0
        parents = {
            path.resolve(strict=False).parent
            for path in deleted_paths or ()
        }
        cleaned = 0
        for start in sorted(parents, key=lambda value: len(value.parts), reverse=True):
            matching = [
                root for root in roots
                if start == root or root in start.parents
            ]
            if not matching:
                continue
            stop_root = max(matching, key=lambda value: len(value.parts))
            directory = start
            levels = 0
            while directory != stop_root and levels < max_levels:
                if directory == directory.parent or len(directory.parts) <= 1:
                    break
                try:
                    if not directory.is_dir() or next(directory.iterdir(), None) is not None:
                        break
                    directory.rmdir()
                except OSError:
                    break
                cleaned += 1
                levels += 1
                directory = directory.parent
        return cleaned

    @staticmethod
    def _validated_source_paths(mappings: Sequence[Dict[str, Any]]) -> List[Path]:
        paths = MediaActionService._unique_paths(
            mapping.get("current_source_path") for mapping in mappings
        )
        if not paths:
            raise MediaActionError("文件映射中没有可删除的源路径")
        for path in paths:
            if path.exists() and not path.is_file():
                raise MediaActionError(f"源路径不是普通文件，拒绝删除：{path}")
        return paths

    @staticmethod
    def _validated_owned_hardlinks(
        mappings: Sequence[Dict[str, Any]],
    ) -> List[Path]:
        targets = []
        for mapping in mappings:
            details = dict(mapping.get("details") or {})
            if not details.get("hardlink_owned"):
                continue
            target_text = str(mapping.get("local_hardlink_path") or "").strip()
            if not target_text:
                raise MediaActionError("插件创建的硬链接缺少持久化目标路径")
            target = Path(target_text).expanduser()
            if not target.is_absolute():
                raise MediaActionError(f"硬链接目标不是绝对路径：{target_text}")
            if target.exists() and not target.is_file():
                raise MediaActionError(f"硬链接目标不是普通文件：{target}")
            targets.append(target)
        return targets

    @staticmethod
    def _unique_paths(values: Iterable[object]) -> List[Path]:
        paths: List[Path] = []
        seen = set()
        for value in values or []:
            text = str(value or "").strip()
            if not text:
                continue
            path = Path(text).expanduser()
            if not path.is_absolute():
                raise MediaActionError(f"文件路径不是绝对路径：{text}")
            key = os.path.normcase(str(path.resolve(strict=False)))
            if key not in seen:
                seen.add(key)
                paths.append(path)
        return paths


class MediaInventoryRefreshService:
    """Recheck imported inventory from saved mappings without re-identifying media."""

    def __init__(self, store: SQLiteStore, library_layout: LibraryLayout):
        self.store = store
        self.library_layout = library_layout

    def refresh(self, media_id: object) -> Dict[str, Any]:
        identity = str(media_id or "").strip()
        item = self.store.get_media_item(identity)
        if not item:
            raise MediaActionError("媒体记录不存在")
        if str(item.get("state") or "") != "imported":
            raise MediaActionError("只有已入库项目可以只复查库存")

        mappings = self.store.list_file_mappings(
            item.get("downloader_id"), item.get("info_hash")
        )
        if not mappings:
            raise MediaActionError("没有持久化的文件映射，无法复查已入库库存")
        category = self.library_layout.canonical_category(item.get("category") or "")
        inventory_base = self.library_layout.inventory_base(category)
        if not inventory_base:
            raise MediaActionError("当前分类没有配置库存根目录")

        expected_files = []
        expected_directory = ""
        for mapping in mappings:
            new_rel = str(mapping.get("new_rel") or "").strip().replace("\\", "/")
            if not new_rel:
                continue
            pure_new_rel = PurePosixPath(new_rel)
            if not expected_directory and len(pure_new_rel.parts) > 1:
                expected_directory = pure_new_rel.parts[0]
            expected_files.append({
                "file_index": mapping.get("file_index"),
                "source_name": str(mapping.get("source_relative_path") or ""),
                "relative_path": pure_new_rel.as_posix(),
                "inventory_relative_path": self._inventory_relative_path(
                    mapping, inventory_base, pure_new_rel
                ),
                "size": int(mapping.get("file_size") or 0),
            })
        if not expected_files:
            raise MediaActionError("文件映射中没有可用于库存复查的目标路径")

        checker = LocalInventoryChecker([])
        inventory_state, inventory_details = checker.check_root(
            inventory_base,
            expected_files,
            tmdb_id=item.get("tmdb_id"),
            expected_directory=expected_directory,
            media_title=item.get("title") or "",
            total_files=len(expected_files),
        )
        inventory_details.update({
            "category": category,
            "group": self.library_layout.media_group(item.get("media_type") or ""),
            "layout_errors": list(self.library_layout.config_errors),
            "refresh_mode": "saved_file_mappings",
            "refreshed_at": utc_now(),
        })

        results_by_index = {
            self._file_index(result.get("file_index")): result
            for result in inventory_details.get("files") or []
        }
        updated_mappings = copy.deepcopy(mappings)
        for mapping in updated_mappings:
            result = results_by_index.get(self._file_index(mapping.get("file_index"))) or {}
            mapping["inventory_exists"] = bool(result.get("inventory_exists"))
            mapping_details = dict(mapping.get("details") or {})
            mapping_details.update({
                "inventory_status": str(result.get("status") or ""),
                "matched_inventory_path": str(result.get("matched_path") or ""),
                "inventory_match_method": str(result.get("match_method") or ""),
                "inventory_refreshed_at": utc_now(),
            })
            mapping["details"] = mapping_details
        persisted_mappings = self.store.replace_file_mappings(
            item.get("downloader_id"), item.get("info_hash"), updated_mappings
        )

        updated_item = copy.deepcopy(item)
        details = dict(updated_item.get("details") or {})
        details["inventory"] = inventory_details
        details["file_mappings"] = persisted_mappings
        updated_item.update({"details": details, "updated_at": utc_now()})
        self.store.upsert_media_item(updated_item)
        return {
            "item": self.store.get_media_item(identity),
            "inventory_state": inventory_state,
            "folder_status": inventory_details.get("folder_status") or "",
            "total_files": int(inventory_details.get("total_files") or 0),
            "exists_count": int(inventory_details.get("exists_count") or 0),
            "missing_count": int(inventory_details.get("missing_count") or 0),
        }

    @staticmethod
    def _inventory_relative_path(
        mapping: Dict[str, Any], inventory_base: str, new_rel: PurePosixPath
    ) -> str:
        inventory_path = str(mapping.get("inventory_path") or "").strip().replace("\\", "/")
        if inventory_path:
            try:
                return PurePosixPath(inventory_path).relative_to(
                    PurePosixPath(str(inventory_base).replace("\\", "/"))
                ).as_posix()
            except ValueError:
                pass
        return new_rel.with_suffix(".strm").as_posix()

    @staticmethod
    def _file_index(value: object) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return -1
