"""Direct local filesystem inventory checks for the final STRM library."""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


MEDIA_TYPE_ALIASES = {
    "*": "*",
    "all": "*",
    "全部": "*",
    "movie": "movie",
    "movies": "movie",
    "电影": "movie",
    "tv": "tv",
    "series": "tv",
    "电视剧": "tv",
    "剧集": "tv",
}
TMDB_MARKER_PATTERN = re.compile(
    r"(?:\[\s*tmdbid\s*=\s*(\d+)\s*\]|\{\s*tmdbid\s*=\s*(\d+)\s*\})",
    re.IGNORECASE,
)
YEAR_SUFFIX_PATTERN = re.compile(r"\s*\(\d{4}\)\s*$")
SEPARATOR_PATTERN = re.compile(r"[\s._-]+")


@dataclass(frozen=True)
class InventoryRoot:
    media_type: str
    path: Path

    def to_dict(self) -> Dict[str, str]:
        return {"media_type": self.media_type, "path": str(self.path)}


@dataclass(frozen=True)
class InventoryFolder:
    status: str
    category_root: Path
    path: Optional[Path] = None
    match_method: str = ""
    title: str = ""
    reason: str = ""
    candidates: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "category_root": str(self.category_root),
            "path": str(self.path) if self.path else "",
            "match_method": self.match_method,
            "title": self.title,
            "reason": self.reason,
            "candidates": list(self.candidates),
        }


def parse_inventory_roots(value: object) -> Tuple[List[InventoryRoot], List[str]]:
    """Parse one local final-library root per line."""

    roots: List[InventoryRoot] = []
    errors: List[str] = []
    seen = set()
    for number, raw_line in enumerate(str(value or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=>" in line:
            raw_type, raw_path = (part.strip() for part in line.split("=>", 1))
        else:
            raw_type, raw_path = "*", line
        media_type = MEDIA_TYPE_ALIASES.get(raw_type.casefold())
        if media_type is None:
            errors.append(f"第 {number} 行媒体类型无效：{raw_type}")
            continue
        if not raw_path:
            errors.append(f"第 {number} 行缺少媒体库路径")
            continue
        if not _is_absolute_path(raw_path):
            errors.append(f"第 {number} 行必须使用绝对路径：{raw_path}")
            continue
        root = InventoryRoot(media_type=media_type, path=Path(raw_path).expanduser())
        identity = (root.media_type, str(root.path))
        if identity not in seen:
            roots.append(root)
            seen.add(identity)
    return roots, errors


class LocalInventoryChecker:
    """Locate a TMDB media folder and compare its STRM files one by one."""

    def __init__(self, roots: Sequence[InventoryRoot], errors: Iterable[str] = ()):
        self.roots = list(roots)
        self.config_errors = list(errors)
        self._directory_cache: Dict[str, List[Path]] = {}

    @classmethod
    def from_config(cls, value: object) -> "LocalInventoryChecker":
        roots, errors = parse_inventory_roots(value)
        return cls(roots=roots, errors=errors)

    def capability(self) -> Dict[str, Any]:
        accessible = [root for root in self.roots if root.path.is_dir()]
        return {
            "ready": bool(accessible),
            "phase": "local_filesystem",
            "configured": len(self.roots),
            "accessible": len(accessible),
            "config_errors": list(self.config_errors),
        }

    def check(
        self,
        media_type: str,
        expected_files: Sequence[Dict[str, Any]],
        **kwargs: Any,
    ) -> Tuple[str, Dict[str, Any]]:
        selected = self._roots_for(media_type)
        if not selected:
            return self.check_root("", expected_files, **kwargs)
        accessible = [root for root in selected if root.path.is_dir()]
        root = accessible[0] if accessible else selected[0]
        return self.check_root(root.path, expected_files, **kwargs)

    def locate_root(
        self,
        root: object,
        tmdb_id: object,
        expected_directory: object = "",
    ) -> InventoryFolder:
        raw_root = str(root or "").strip()
        category_root = Path(raw_root) if raw_root else Path()
        if not raw_root:
            return InventoryFolder(
                status="unconfigured",
                category_root=category_root,
                reason="未生成最终媒体库分类目录",
            )
        if not category_root.is_dir():
            return InventoryFolder(
                status="unavailable",
                category_root=category_root,
                reason="最终媒体库分类目录不可访问",
            )
        normalized_tmdb = _positive_int(tmdb_id)
        if normalized_tmdb is None:
            return InventoryFolder(
                status="unknown",
                category_root=category_root,
                reason="MoviePilot 未返回有效 TMDB ID",
            )

        try:
            cache_key = str(category_root.resolve(strict=False))
            directories = self._directory_cache.get(cache_key)
            if directories is None:
                directories = sorted(
                    (item for item in category_root.iterdir() if item.is_dir()),
                    key=lambda item: item.name.casefold(),
                )
                self._directory_cache[cache_key] = directories
        except OSError as error:
            return InventoryFolder(
                status="unavailable",
                category_root=category_root,
                reason=str(error),
            )

        tmdb_matches = [
            item for item in directories
            if normalized_tmdb in _tmdb_ids(item.name)
        ]
        if len(tmdb_matches) == 1:
            matched = tmdb_matches[0]
            return InventoryFolder(
                status="exists",
                category_root=category_root,
                path=matched,
                match_method="tmdb_id",
                title=_directory_title(matched.name),
            )
        if len(tmdb_matches) > 1:
            return InventoryFolder(
                status="ambiguous",
                category_root=category_root,
                reason=f"存在多个 TMDB ID 为 {normalized_tmdb} 的库存目录",
                candidates=tuple(str(item) for item in tmdb_matches),
            )

        expected_name = str(expected_directory or "").strip()
        name_matches = [
            item for item in directories
            if expected_name and item.name.casefold() == expected_name.casefold()
        ]
        if len(name_matches) == 1:
            matched = name_matches[0]
            return InventoryFolder(
                status="exists",
                category_root=category_root,
                path=matched,
                match_method="expected_directory",
                title=_directory_title(matched.name),
            )
        if len(name_matches) > 1:
            return InventoryFolder(
                status="ambiguous",
                category_root=category_root,
                reason=f"存在多个名称为 {expected_name} 的库存目录",
                candidates=tuple(str(item) for item in name_matches),
            )
        return InventoryFolder(
            status="missing",
            category_root=category_root,
            reason="未找到匹配 TMDB ID 或预期名称的库存目录",
        )

    def check_root(
        self,
        root: object,
        expected_files: Sequence[Dict[str, Any]],
        *,
        tmdb_id: object = None,
        expected_directory: object = "",
        media_title: object = "",
        folder: Optional[InventoryFolder] = None,
        plan_errors: Sequence[Dict[str, Any]] = (),
        total_files: Optional[int] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        located = folder or self.locate_root(root, tmdb_id, expected_directory)
        normalized, normalize_errors = self._normalize_expected_files(expected_files)
        planned_total = len(normalized)
        source_total = max(planned_total, int(total_files or 0))
        errors = [*list(plan_errors or []), *normalize_errors]
        details: Dict[str, Any] = {
            "method": "tmdb_strm_features",
            "scope": "mp_library_path",
            "folder_status": located.status,
            "folder": located.to_dict(),
            "total_files": source_total,
            "exists_count": 0,
            "missing_count": source_total,
            "total": source_total,
            "exists": 0,
            "missing": source_total,
            "files": [],
            "plan_errors": errors,
        }
        if located.status in {"unconfigured", "unavailable", "unknown", "ambiguous"}:
            details["reason"] = located.reason
            return located.status, details
        if errors and not normalized:
            details["reason"] = "没有可安全核对的 MoviePilot 目标路径"
            return "unknown", details
        if not normalized:
            details["reason"] = "没有可用于库存核对的媒体文件"
            return "empty", details
        if located.status == "missing" or not located.path:
            details["reason"] = located.reason
            details["files"] = [self._missing_result(item) for item in normalized]
            return "missing", details

        inventory_index = self._strm_index(located.path)
        title = str(located.title or media_title or "").strip()
        for expected in normalized:
            result = self._check_one(located, inventory_index, expected, title)
            details["files"].append(result)
            if result["inventory_exists"]:
                details["exists_count"] += 1

        details["missing_count"] = source_total - details["exists_count"]
        details["exists"] = details["exists_count"]
        details["missing"] = details["missing_count"]
        if inventory_index["errors"]:
            details["scan_errors"] = inventory_index["errors"]
            details["reason"] = "库存媒体目录未能完整读取"
            return ("partial" if details["exists_count"] else "unavailable"), details
        if errors:
            details["reason"] = "部分媒体文件无法生成可靠的 MoviePilot 目标名称"
            return ("partial" if details["exists_count"] else "unknown"), details
        if details["exists_count"] == source_total:
            return "exists", details
        if details["exists_count"]:
            return "partial", details
        details["reason"] = "库存目录存在，但没有匹配的 STRM 文件"
        return "missing", details

    @staticmethod
    def _normalize_expected_files(
        expected_files: Sequence[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        normalized: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        seen = set()
        for index, item in enumerate(expected_files or [], start=1):
            relative = str(item.get("relative_path") or "").strip().replace("\\", "/")
            pure_path = PurePosixPath(relative)
            if (
                not relative
                or pure_path.is_absolute()
                or any(part in {"", ".", ".."} for part in pure_path.parts)
            ):
                errors.append({
                    "source_name": str(item.get("source_name") or ""),
                    "reason": f"第 {index} 个预期文件路径无效：{relative or '<empty>'}",
                })
                continue
            inventory_relative = str(
                item.get("inventory_relative_path") or _with_strm_suffix(pure_path)
            ).strip().replace("\\", "/")
            inventory_path = PurePosixPath(inventory_relative)
            if (
                inventory_path.is_absolute()
                or any(part in {"", ".", ".."} for part in inventory_path.parts)
                or inventory_path.suffix.casefold() != ".strm"
            ):
                errors.append({
                    "source_name": str(item.get("source_name") or ""),
                    "reason": f"第 {index} 个 STRM 预期路径无效：{inventory_relative}",
                })
                continue
            identity = inventory_path.as_posix().casefold()
            if identity in seen:
                errors.append({
                    "source_name": str(item.get("source_name") or ""),
                    "reason": f"STRM 预期路径重复：{inventory_path.as_posix()}",
                })
                continue
            seen.add(identity)
            normalized.append({
                "file_index": item.get("file_index"),
                "source_name": str(item.get("source_name") or ""),
                "relative_path": pure_path.as_posix(),
                "new_rel": pure_path.as_posix(),
                "inventory_relative_path": inventory_path.as_posix(),
                "size": max(0, _int_value(item.get("size"))),
            })
        return normalized, errors

    @staticmethod
    def _strm_index(media_root: Path) -> Dict[str, Any]:
        exact: Dict[str, List[Path]] = {}
        files: List[Path] = []
        errors: List[str] = []

        def record_error(error: OSError) -> None:
            errors.append(str(error))

        for current, _directories, names in os.walk(
            media_root,
            topdown=True,
            onerror=record_error,
            followlinks=False,
        ):
            current_path = Path(current)
            for name in names:
                candidate = current_path / name
                if candidate.suffix.casefold() != ".strm":
                    continue
                try:
                    if not candidate.is_file():
                        continue
                except OSError as error:
                    errors.append(str(error))
                    continue
                relative = candidate.relative_to(media_root).as_posix()
                exact.setdefault(relative.casefold(), []).append(candidate)
                files.append(candidate)
        return {"exact": exact, "files": files, "errors": errors}

    @classmethod
    def _check_one(
        cls,
        folder: InventoryFolder,
        inventory_index: Dict[str, Any],
        expected: Dict[str, Any],
        media_title: str,
    ) -> Dict[str, Any]:
        inventory_relative = PurePosixPath(expected["inventory_relative_path"])
        inside_media = _inside_media_directory(inventory_relative, folder.path.name)
        exact_matches = inventory_index["exact"].get(inside_media.as_posix().casefold(), [])
        if len(exact_matches) == 1:
            return cls._exists_result(expected, exact_matches[0], "exact_relative_path")
        if len(exact_matches) > 1:
            return cls._ambiguous_result(expected, exact_matches, "exact_relative_path")

        expected_feature = _feature_key(inventory_relative.stem, media_title)
        feature_matches = [
            item for item in inventory_index["files"]
            if _feature_key(item.stem, media_title) == expected_feature
        ]
        if len(feature_matches) == 1:
            return cls._exists_result(expected, feature_matches[0], "filename_features")
        if len(feature_matches) > 1:
            return cls._ambiguous_result(expected, feature_matches, "filename_features")
        return cls._missing_result(expected, expected_feature)

    @staticmethod
    def _exists_result(
        expected: Dict[str, Any], matched: Path, match_method: str
    ) -> Dict[str, Any]:
        return {
            **expected,
            "status": "exists",
            "inventory_exists": True,
            "matched_path": str(matched),
            "match_method": match_method,
        }

    @staticmethod
    def _ambiguous_result(
        expected: Dict[str, Any], matches: Sequence[Path], match_method: str
    ) -> Dict[str, Any]:
        return {
            **expected,
            "status": "ambiguous",
            "inventory_exists": False,
            "matched_path": "",
            "match_method": match_method,
            "candidates": [str(item) for item in matches],
        }

    @staticmethod
    def _missing_result(
        expected: Dict[str, Any], expected_feature: str = ""
    ) -> Dict[str, Any]:
        return {
            **expected,
            "status": "missing",
            "inventory_exists": False,
            "matched_path": "",
            "match_method": "",
            "expected_feature": expected_feature,
        }

    def _roots_for(self, media_type: str) -> List[InventoryRoot]:
        normalized = MEDIA_TYPE_ALIASES.get(str(media_type or "").casefold(), "")
        return [
            root for root in self.roots
            if root.media_type == "*" or root.media_type == normalized
        ]


def _tmdb_ids(name: str) -> List[int]:
    result = []
    for match in TMDB_MARKER_PATTERN.finditer(str(name or "")):
        value = match.group(1) or match.group(2)
        if value:
            result.append(int(value))
    return result


def _directory_title(name: str) -> str:
    value = TMDB_MARKER_PATTERN.sub("", str(name or "")).strip()
    value = value.rstrip(" ._-")
    value = YEAR_SUFFIX_PATTERN.sub("", value).strip()
    return value.rstrip(" ._-")


def _inside_media_directory(path: PurePosixPath, folder_name: str) -> PurePosixPath:
    if len(path.parts) > 1 and path.parts[0].casefold() == folder_name.casefold():
        return PurePosixPath(*path.parts[1:])
    return path


def _feature_key(value: str, media_title: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    normalized = SEPARATOR_PATTERN.sub(" ", normalized).strip()
    title = unicodedata.normalize("NFKC", str(media_title or "")).casefold()
    title = SEPARATOR_PATTERN.sub(" ", title).strip()
    if title:
        normalized = normalized.replace(title, "", 1).strip(" -._")
    return SEPARATOR_PATTERN.sub(" ", normalized).strip()


def _with_strm_suffix(path: PurePosixPath) -> PurePosixPath:
    return path.with_suffix(".strm") if path.suffix else path.with_name(f"{path.name}.strm")


def _positive_int(value: object) -> Optional[int]:
    number = _int_value(value)
    return number if number > 0 else None


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_absolute_path(value: str) -> bool:
    return (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )
