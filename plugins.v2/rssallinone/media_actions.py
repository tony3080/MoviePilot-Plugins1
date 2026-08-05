"""Stateful media-card actions backed by persisted source/target mappings."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .database import SQLiteStore, utc_now
from .domain import can_transition


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

    def __init__(self, store: SQLiteStore):
        self.store = store

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

    def _queue_import(self, item: Dict[str, Any]) -> Dict[str, Any]:
        state = str(item.get("state") or "")
        if state == "pending":
            return {"message": "已经处于待入库状态", "state": state}
        if state not in {"identified", "rolled_back"}:
            raise MediaActionError("只有已识别或已回退项目可以转为待入库")
        if not can_transition(state, "pending"):
            raise MediaActionError(f"不允许从 {state} 转为 pending")
        updated = copy.deepcopy(item)
        updated.update({
            "state": "pending",
            "failure_code": "",
            "failure_message": "",
            "updated_at": utc_now(),
        })
        self.store.upsert_media_item(updated)
        return {"message": "已转为待入库", "state": "pending"}

    def _import(self, item: Dict[str, Any]) -> Dict[str, Any]:
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
        if not missing:
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
                    reused_count += 1
                else:
                    os.link(source, target)
                    created.append(target)
                    created_count += 1
                    owned = True
                details.update({
                    "hardlink_owned": owned,
                    "hardlink_reused": target not in created,
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
            "state": "imported",
            "created_count": created_count,
            "reused_count": reused_count,
            "inventory_skipped_count": skipped_count,
            "completed_at": utc_now(),
        }
        completed.update({
            "state": "imported",
            "failure_code": "",
            "failure_message": "",
            "rolled_back": False,
            "details": details,
            "updated_at": utc_now(),
        })
        self.store.upsert_media_item(completed)
        return {
            "message": (
                f"入库完成：新建 {created_count}，复用 {reused_count}，"
                f"库存跳过 {skipped_count}"
            ),
            "state": "imported",
            "created": created_count,
            "reused": reused_count,
            "skipped": skipped_count,
            "mappings": len(persisted),
        }

    def _delete_source(
        self, item: Dict[str, Any], mappings: Sequence[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if str(item.get("state") or "") == "imported":
            raise MediaActionError("已入库项目请使用“删除硬链接和源文件”")
        deleted, missing = self._unlink_sources(mappings)
        self.store.delete_media_item(item.get("id"))
        return {
            "message": f"已删除源文件 {deleted} 个，缺失 {missing} 个，并移除记录",
            "deleted": deleted,
            "missing": missing,
            "state": "deleted",
        }

    def _delete_hardlinks(
        self, item: Dict[str, Any], mappings: Sequence[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if str(item.get("state") or "") != "imported":
            raise MediaActionError("只有已入库项目可以删除硬链接")
        updated, deleted, missing, preserved = self._unlink_hardlinks(mappings)
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
                f"缺失 {missing} 个，保留非插件目标 {preserved} 个"
            ),
            "deleted": deleted,
            "missing": missing,
            "preserved": preserved,
            "state": "rolled_back",
        }

    def _delete_both(
        self, item: Dict[str, Any], mappings: Sequence[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if str(item.get("state") or "") != "imported":
            raise MediaActionError("只有已入库项目可以执行硬链接和源文件双删")
        self._validated_source_paths(mappings)
        self._validated_owned_hardlinks(mappings)
        _updated, links_deleted, links_missing, preserved = self._unlink_hardlinks(mappings)
        sources_deleted, sources_missing = self._unlink_sources(mappings)
        self.store.delete_media_item(item.get("id"))
        return {
            "message": (
                f"双删完成：硬链接 {links_deleted}，源文件 {sources_deleted}，"
                f"缺失 {links_missing + sources_missing}，保留非插件目标 {preserved}"
            ),
            "hardlinks_deleted": links_deleted,
            "sources_deleted": sources_deleted,
            "missing": links_missing + sources_missing,
            "preserved": preserved,
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

    @staticmethod
    def _unlink_sources(mappings: Sequence[Dict[str, Any]]) -> Tuple[int, int]:
        paths = MediaActionService._validated_source_paths(mappings)
        deleted = 0
        missing = 0
        for path in paths:
            if not path.exists():
                missing += 1
                continue
            path.unlink()
            deleted += 1
        return deleted, missing

    @staticmethod
    def _unlink_hardlinks(
        mappings: Sequence[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], int, int, int]:
        updated = copy.deepcopy(list(mappings))
        deleted = 0
        missing = 0
        preserved = 0
        MediaActionService._validated_owned_hardlinks(mappings)
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
            else:
                missing += 1
            details.update({
                "hardlink_owned": False,
                "hardlink_deleted_at": utc_now(),
            })
            mapping.update({"state": "rolled_back", "details": details})
        return updated, deleted, missing, preserved

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
