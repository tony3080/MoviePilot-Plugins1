"""Normalization contract for editable VT+ RSS tasks."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List


DEFAULT_RSS_TASK_CONFIG: Dict[str, Any] = {
    "task_type": "rss",
    "rss_url": "",
    "qb_downloader": "",
    "rss_cron": "*/10 * * * *",
    "save_path": "",
    "qb_category": "",
    "name_contains": "",
    "start_cron": "*/5 * * * *",
    "delete_after_minutes": 0,
    "upload_limit_kbps": 0,
    "rename_rules": "",
    "site_id": "",
    "cn_keywords": "国语,国配",
    "pause_on_add": True,
    "push_torrent_file": False,
    "recognize_cn": False,
    "recognize_fx": False,
    "add_chinese_title": False,
    "import_enabled": True,
    "realtime_hardlink_enabled": False,
    "realtime_source_root": "",
    "realtime_link_root": "",
    "rename_enabled": False,
    "download_enabled": True,
    "delete_files": False,
    "hr_enabled": False,
    "hr_cron": "30 3 * * *",
    "local_path": "",
    "process_local_files": False,
    "force_reprocess_local": False,
    "local_initialized": False,
    "local_initialized_at": "",
    "local_path_fingerprint": "",
    "query_interval": 60,
}

TEXT_FIELDS = (
    "rss_url",
    "qb_downloader",
    "rss_cron",
    "save_path",
    "qb_category",
    "name_contains",
    "start_cron",
    "rename_rules",
    "site_id",
    "cn_keywords",
    "realtime_source_root",
    "realtime_link_root",
    "hr_cron",
    "local_path",
    "local_initialized_at",
    "local_path_fingerprint",
)
BOOLEAN_FIELDS = (
    "pause_on_add",
    "push_torrent_file",
    "recognize_cn",
    "recognize_fx",
    "add_chinese_title",
    "import_enabled",
    "realtime_hardlink_enabled",
    "rename_enabled",
    "download_enabled",
    "delete_files",
    "hr_enabled",
    "process_local_files",
    "force_reprocess_local",
    "local_initialized",
)
INTEGER_LIMITS = {
    "delete_after_minutes": (0, 525600),
    "upload_limit_kbps": (0, 1_000_000_000),
    "query_interval": (1, 86400),
}
TASK_ID_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


def default_rss_task(position: int = 0) -> Dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "name": f"RSS任务 {position + 1}",
        "enabled": True,
        "position": max(0, int(position)),
        "config": dict(DEFAULT_RSS_TASK_CONFIG),
    }


def normalize_rss_tasks(value: object) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("RSS 任务必须是列表")
    if len(value) > 100:
        raise ValueError("RSS 任务最多保存 100 条")
    normalized: List[Dict[str, Any]] = []
    seen_ids = set()
    seen_qb_pairs: Dict[tuple[str, str, str], str] = {}
    for position, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"第 {position + 1} 条 RSS 任务格式无效")
        task = normalize_rss_task(item, position)
        if task["id"] in seen_ids:
            raise ValueError(f"RSS 任务 ID 重复：{task['id']}")
        seen_ids.add(task["id"])
        config = task["config"]
        downloader = str(config.get("qb_downloader") or "").strip()
        category = str(config.get("qb_category") or "").strip()
        if downloader and category:
            task_type = str(config.get("task_type") or "rss").strip().casefold()
            pair = (task_type, downloader.casefold(), category.casefold())
            previous_name = seen_qb_pairs.get(pair)
            if previous_name:
                raise ValueError(
                    "RSS 任务不能共用相同的 QB 节点和分类："
                    f"“{previous_name}”与“{task['name']}”"
                )
            seen_qb_pairs[pair] = task["name"]
        normalized.append(task)
    return normalized


def normalize_rss_task(item: Dict[str, Any], position: int) -> Dict[str, Any]:
    raw_id = str(item.get("id") or uuid.uuid4().hex).strip()
    task_id = TASK_ID_PATTERN.sub("-", raw_id).strip("-._")[:128]
    if not task_id:
        task_id = uuid.uuid4().hex
    name = str(item.get("name") or f"RSS任务 {position + 1}").strip()[:200]
    config = item.get("config") if isinstance(item.get("config"), dict) else {}
    normalized_config = {**DEFAULT_RSS_TASK_CONFIG, **config}
    # Path routing is configured globally by the plugin, not per RSS task.
    normalized_config.pop("path_mappings", None)
    for field in TEXT_FIELDS:
        normalized_config[field] = str(normalized_config.get(field) or "").strip()
    if not normalized_config.get("hr_cron"):
        normalized_config["hr_cron"] = DEFAULT_RSS_TASK_CONFIG["hr_cron"]
    task_type = str(normalized_config.get("task_type") or "rss").strip().casefold()
    normalized_config["task_type"] = "manual" if task_type in {"manual", "手动", "手动添加"} else "rss"
    for field in BOOLEAN_FIELDS:
        normalized_config[field] = _as_bool(normalized_config.get(field))
    for field, (minimum, maximum) in INTEGER_LIMITS.items():
        normalized_config[field] = _bounded_int(
            normalized_config.get(field), minimum, maximum
        )
    return {
        "id": task_id,
        "name": name,
        "enabled": _as_bool(item.get("enabled", True)),
        "position": position,
        "config": normalized_config,
    }


def _bounded_int(value: object, minimum: int, maximum: int) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(number, maximum))


def _as_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "是"}
    return bool(value)
