"""Category-driven path planning for local hardlinks and final inventory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_INVENTORY_ROOT = "/SSD/云盘/strm/影视库"
DEFAULT_SOURCE_ROUTES = [
    {
        "name": "UP",
        "prefix": "/MP",
        "link_roots": {
            "movie": "/MP/电影UP",
            "series": "/MP/剧集UP",
        },
        "enabled": True,
    },
    {
        "name": "SSD",
        "prefix": "/SSD",
        "link_roots": {"default": "/SSD/云盘/l"},
        "enabled": True,
    },
]
MEDIA_GROUP_ALIASES = {
    "movie": "movie",
    "movies": "movie",
    "电影": "movie",
    "tv": "series",
    "series": "series",
    "电视剧": "series",
    "剧集": "series",
}


@dataclass(frozen=True)
class SourceRoute:
    name: str
    prefix: str
    link_roots: Dict[str, str]
    enabled: bool = True

    def matches(self, source_path: str) -> bool:
        source = _pure_path(source_path)
        prefix = _pure_path(self.prefix)
        return len(source.parts) >= len(prefix.parts) and (
            source.parts[:len(prefix.parts)] == prefix.parts
        )

    def link_root(self, group: str) -> str:
        return str(
            self.link_roots.get(group)
            or self.link_roots.get("default")
            or ""
        ).strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "prefix": self.prefix,
            "link_roots": dict(self.link_roots),
            "enabled": self.enabled,
        }


class LibraryLayout:
    """Resolve MP categories into exact inventory and staging destinations."""

    def __init__(
        self,
        inventory_root: str,
        routes: Sequence[SourceRoute],
        errors: Iterable[str] = (),
    ):
        self.inventory_root = str(inventory_root or "").strip()
        self.routes = list(routes)
        self.config_errors = list(errors)

    @classmethod
    def from_config(
        cls,
        inventory_root: object,
        source_routes: object,
    ) -> "LibraryLayout":
        errors: List[str] = []
        normalized_root = str(inventory_root or "").strip()
        if normalized_root and not _is_absolute(normalized_root):
            errors.append(f"最终媒体库根目录必须是绝对路径：{normalized_root}")
            normalized_root = ""

        route_payload = _structured_value(source_routes, [])
        routes: List[SourceRoute] = []
        if not isinstance(route_payload, list):
            errors.append("源路径路由必须是列表")
            route_payload = []
        for index, item in enumerate(route_payload, start=1):
            if not isinstance(item, dict):
                errors.append(f"第 {index} 条源路径路由格式无效")
                continue
            name = str(item.get("name") or f"route-{index}").strip()
            prefix = str(item.get("prefix") or "").strip()
            enabled = _as_bool(item.get("enabled", True))
            raw_roots = item.get("link_roots") or {}
            if not prefix or not _is_absolute(prefix):
                errors.append(f"路由 {name} 的源前缀必须是绝对路径")
                continue
            if not isinstance(raw_roots, dict):
                errors.append(f"路由 {name} 的硬链接根目录格式无效")
                continue
            link_roots: Dict[str, str] = {}
            for group, value in raw_roots.items():
                path = str(value or "").strip()
                if not path:
                    continue
                if not _is_absolute(path):
                    errors.append(f"路由 {name} 的 {group} 硬链接根目录必须是绝对路径")
                    continue
                link_roots[str(group)] = path
            routes.append(SourceRoute(
                name=name,
                prefix=_pure_path(prefix).as_posix(),
                link_roots=link_roots,
                enabled=enabled,
            ))

        return cls(normalized_root, routes, errors)

    @staticmethod
    def media_group(media_type: str) -> str:
        return MEDIA_GROUP_ALIASES.get(
            str(media_type or "").strip().casefold(),
            "",
        )

    @staticmethod
    def canonical_category(category: str) -> str:
        value = str(category or "").strip()
        path = _pure_path(value)
        if not value or len(path.parts) != 1 or path.parts[0] in {".", ".."}:
            return ""
        return value

    def inventory_base(self, category: str) -> str:
        canonical = self.canonical_category(category)
        if not self.inventory_root or not canonical:
            return ""
        return _join_path(self.inventory_root, canonical)

    def select_route(self, source_path: str) -> Optional[SourceRoute]:
        matches = [
            route for route in self.routes
            if route.enabled and route.matches(source_path)
        ]
        if not matches:
            return None
        return max(matches, key=lambda route: len(_pure_path(route.prefix).parts))

    def link_base(
        self,
        source_path: str,
        category: str,
        media_type: str,
    ) -> Tuple[str, str]:
        canonical = self.canonical_category(category)
        group = self.media_group(media_type)
        if not canonical:
            return "", "MoviePilot 未返回有效分类"
        if not group:
            return "", "MoviePilot 未返回可用的电影或剧集类型"
        route = self.select_route(source_path)
        if not route:
            return "", "源路径没有命中任何已启用路由"
        root = route.link_root(group)
        if not root:
            return "", f"路由 {route.name} 没有配置 {group} 或 default 硬链接根目录"
        return _join_path(root, canonical), ""

    def plan(
        self,
        source_path: str,
        category: str,
        expected_files: Sequence[Dict[str, Any]],
        media_type: str = "",
    ) -> Dict[str, Any]:
        canonical = self.canonical_category(category)
        group = self.media_group(media_type)
        inventory_base = self.inventory_base(category)
        route = self.select_route(source_path)
        link_base, link_error = self.link_base(source_path, category, media_type)
        inventory_files = []
        link_files = []
        path_errors: List[str] = []
        for item in expected_files or []:
            relative = str(item.get("relative_path") or "").strip().replace("\\", "/")
            if not _valid_relative(relative):
                path_errors.append(f"无效预期相对路径：{relative or '<empty>'}")
                continue
            pure_relative = PurePosixPath(relative)
            default_inventory = (
                pure_relative.with_suffix(".strm")
                if pure_relative.suffix
                else pure_relative.with_name(f"{pure_relative.name}.strm")
            )
            inventory_relative = str(
                item.get("inventory_relative_path") or default_inventory.as_posix()
            ).strip().replace("\\", "/")
            if not _valid_relative(inventory_relative):
                path_errors.append(
                    f"无效 STRM 库存相对路径：{inventory_relative or '<empty>'}"
                )
                continue
            payload = {
                "file_index": item.get("file_index"),
                "relative_path": pure_relative.as_posix(),
                "new_rel": pure_relative.as_posix(),
                "inventory_relative_path": PurePosixPath(
                    inventory_relative
                ).as_posix(),
                "source_name": str(item.get("source_name") or ""),
                "size": int(item.get("size") or 0),
            }
            if inventory_base:
                inventory_files.append({
                    **payload,
                    "path": _join_path(inventory_base, inventory_relative),
                })
            if link_base:
                link_files.append({
                    **payload,
                    "path": _join_path(link_base, relative),
                })
        errors = list(self.config_errors)
        if not canonical:
            errors.append(f"MoviePilot 分类无效：{category or '<empty>'}")
        if not inventory_base:
            errors.append("无法生成最终媒体库库存目录")
        errors.extend(path_errors)
        return {
            "category": canonical or str(category or ""),
            "group": group,
            "media_type": str(media_type or ""),
            "source_path": str(source_path or ""),
            "source_route": route.to_dict() if route else None,
            "inventory_base": inventory_base,
            "link_base": link_base,
            "link_error": link_error,
            "inventory_files": inventory_files,
            "link_files": link_files,
            "errors": errors,
        }

    def capability(self) -> Dict[str, Any]:
        root = Path(self.inventory_root) if self.inventory_root else None
        return {
            "ready": bool(root and root.is_dir()),
            "phase": "moviepilot_media_type_layout",
            "inventory_root": self.inventory_root,
            "inventory_accessible": bool(root and root.is_dir()),
            "routes": len([route for route in self.routes if route.enabled]),
            "category_scope": "all_moviepilot_categories",
            "config_errors": list(self.config_errors),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inventory_root": self.inventory_root,
            "source_routes": [route.to_dict() for route in self.routes],
            "config_errors": list(self.config_errors),
        }


def default_layout_config() -> Dict[str, Any]:
    return {
        "inventory_root": DEFAULT_INVENTORY_ROOT,
        "source_routes": json.loads(json.dumps(DEFAULT_SOURCE_ROUTES, ensure_ascii=False)),
    }


def _structured_value(value: object, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _pure_path(value: object) -> PurePosixPath:
    return PurePosixPath(str(value or "").strip().replace("\\", "/"))


def _is_absolute(value: object) -> bool:
    raw = str(value or "").strip()
    return _pure_path(raw).is_absolute() or PureWindowsPath(raw).is_absolute()


def _valid_relative(value: str) -> bool:
    path = _pure_path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def _join_path(base: str, *parts: str) -> str:
    path = _pure_path(base)
    for part in parts:
        path = path.joinpath(*_pure_path(part).parts)
    return path.as_posix()


def _as_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "是"}
    return bool(value)
