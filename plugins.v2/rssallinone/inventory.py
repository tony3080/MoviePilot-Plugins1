"""Direct local filesystem inventory checks for the final mounted media library."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, List, Sequence, Tuple


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


@dataclass(frozen=True)
class InventoryRoot:
    media_type: str
    path: Path

    def to_dict(self) -> Dict[str, str]:
        return {"media_type": self.media_type, "path": str(self.path)}


def parse_inventory_roots(value: object) -> Tuple[List[InventoryRoot], List[str]]:
    """Parse one local final-library root per line.

    Supported forms are ``movie => /media/Movies``, ``tv => /media/TV`` and a
    bare path that applies to both types. Invalid lines are reported instead of
    aborting plugin startup.
    """

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
    """Verify exact expected files under configured local library roots."""

    def __init__(self, roots: Sequence[InventoryRoot], errors: Iterable[str] = ()):
        self.roots = list(roots)
        self.config_errors = list(errors)

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
    ) -> Tuple[str, Dict[str, Any]]:
        selected_roots = self._roots_for(media_type)
        details: Dict[str, Any] = {
            "method": "local_filesystem",
            "scope": "mp_library_path",
            "roots": [root.to_dict() for root in selected_roots],
            "config_errors": list(self.config_errors),
            "total": 0,
            "exists": 0,
            "missing": 0,
            "size_mismatch": 0,
            "unavailable": 0,
            "files": [],
        }
        if not selected_roots:
            details["reason"] = "未配置适用于该媒体类型的最终媒体库根目录"
            return "unconfigured", details

        accessible_roots = [root for root in selected_roots if root.path.is_dir()]
        details["unavailable_roots"] = [
            root.to_dict() for root in selected_roots if not root.path.is_dir()
        ]
        if not accessible_roots:
            details["reason"] = "已配置的最终媒体库根目录均不可访问"
            return "unavailable", details

        normalized, plan_errors = self._normalize_expected_files(expected_files)
        details["plan_errors"] = plan_errors
        details["total"] = len(normalized)
        if plan_errors or not normalized:
            details["reason"] = "没有可安全核对的预期文件路径"
            return "unknown", details

        for expected in normalized:
            result = self._check_one(accessible_roots, expected)
            details["files"].append(result)
            if result["status"] == "exists":
                details["exists"] += 1
            elif result["status"] == "size_mismatch":
                details["size_mismatch"] += 1
            elif result["status"] == "unavailable":
                details["unavailable"] += 1
            else:
                details["missing"] += 1

        if details["exists"] == details["total"]:
            return "exists", details
        if details["unavailable"]:
            return (
                "partial"
                if details["exists"] or details["size_mismatch"]
                else "unavailable"
            ), details
        if details["exists"] or details["size_mismatch"]:
            return "partial", details
        return "missing", details

    def _roots_for(self, media_type: str) -> List[InventoryRoot]:
        normalized = MEDIA_TYPE_ALIASES.get(str(media_type or "").casefold(), "")
        return [
            root for root in self.roots
            if root.media_type == "*" or root.media_type == normalized
        ]

    @staticmethod
    def _normalize_expected_files(
        expected_files: Sequence[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        normalized: List[Dict[str, Any]] = []
        errors: List[str] = []
        seen = set()
        for index, item in enumerate(expected_files or [], start=1):
            relative = str(item.get("relative_path") or "").strip().replace("\\", "/")
            pure_path = PurePosixPath(relative)
            if (
                not relative
                or pure_path.is_absolute()
                or any(part in {"", ".", ".."} for part in pure_path.parts)
            ):
                errors.append(f"第 {index} 个预期文件路径无效：{relative or '<empty>'}")
                continue
            identity = pure_path.as_posix().casefold()
            if identity in seen:
                errors.append(f"预期文件路径重复：{pure_path.as_posix()}")
                continue
            seen.add(identity)
            try:
                size = max(0, int(item.get("size") or 0))
            except (TypeError, ValueError):
                size = 0
            normalized.append({
                "relative_path": pure_path.as_posix(),
                "size": size,
                "source_name": str(item.get("source_name") or ""),
            })
        return normalized, errors

    @staticmethod
    def _check_one(
        roots: Sequence[InventoryRoot], expected: Dict[str, Any]
    ) -> Dict[str, Any]:
        relative = PurePosixPath(expected["relative_path"])
        expected_size = int(expected.get("size") or 0)
        candidates: List[str] = []
        mismatches: List[Dict[str, Any]] = []
        errors: List[str] = []
        for root in roots:
            root_path = root.path.resolve(strict=False)
            candidate = root_path.joinpath(*relative.parts)
            candidates.append(str(candidate))
            try:
                resolved = candidate.resolve(strict=False)
                if not resolved.is_relative_to(root_path):
                    errors.append(f"目标路径逃出媒体库根目录：{candidate}")
                    continue
                if not resolved.is_file():
                    continue
                actual_size = resolved.stat().st_size
                if expected_size and actual_size != expected_size:
                    mismatches.append({
                        "path": str(resolved),
                        "expected_size": expected_size,
                        "actual_size": actual_size,
                    })
                    continue
                return {
                    **expected,
                    "status": "exists",
                    "matched_path": str(resolved),
                    "actual_size": actual_size,
                    "candidates": candidates,
                }
            except OSError as error:
                errors.append(f"{candidate}: {error}")
        if mismatches:
            status = "size_mismatch"
        elif errors:
            status = "unavailable"
        else:
            status = "missing"
        return {
            **expected,
            "status": status,
            "matched_path": "",
            "candidates": candidates,
            "mismatches": mismatches,
            "errors": errors,
        }


def _is_absolute_path(value: str) -> bool:
    return (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )
