"""Pure parsing helpers for the Checkin plugin."""

from __future__ import annotations

import html as html_module
import json
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


SITE_NAMES = {
    "smzdm": "什么值得买",
    "chiphell": "Chiphell",
}


def normalize_cookie(value: str) -> str:
    """Normalize a copied Cookie header without exposing it elsewhere."""
    parts = []
    for item in str(value or "").replace("\r", "").replace("\n", ";").split(";"):
        if "=" not in item:
            continue
        name, cookie_value = item.strip().split("=", 1)
        if name.strip() and cookie_value.strip():
            parts.append(f"{name.strip()}={cookie_value.strip()}")
    return "; ".join(parts)


def _json_object(raw: str) -> Dict[str, Any]:
    text = str(raw or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("响应中没有 JSON 对象")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("签到响应不是 JSON 对象")
    return value


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("public", "message", "msg", "detail", "error_msg"):
            text = _message_text(value.get(key))
            if text:
                return text
        for nested in value.values():
            text = _message_text(nested)
            if text:
                return text
    if isinstance(value, (list, tuple)):
        for nested in value:
            text = _message_text(nested)
            if text:
                return text
    return ""


def _dig_value(data: Dict[str, Any], keys: Iterable[str]) -> str:
    current: Any = data
    for _ in range(4):
        if not isinstance(current, dict):
            break
        for key in keys:
            value = current.get(key)
            if value not in (None, ""):
                return str(value)
        current = current.get("data") or current.get("checkin")
    return ""


def parse_smzdm_response(raw: str) -> Dict[str, Any]:
    """Parse both JSON and JSONP responses returned by SMZDM check-in APIs."""
    payload = _json_object(raw)
    code_value = payload.get("error_code")
    code = "" if code_value is None else str(code_value).strip()
    message = ""
    for key in ("error_msg", "error_msg_detail", "msg", "message", "detail"):
        message = _message_text(payload.get(key))
        if message:
            break

    already_markers = ("已签到", "已经签到", "今日已签", "明天再来", "重复签到")
    if code in {"0", "00"}:
        status = "success"
        message = message or "签到成功"
    elif any(marker in message for marker in already_markers):
        status = "already"
        message = message or "今天已经签到"
    else:
        status = "failed"
        message = message or f"签到接口返回 error_code={code or 'unknown'}"

    result = {
        "status": status,
        "message": message,
        "error_code": code,
    }
    values = {
        "days": ("daily_num", "daily_attendance_number", "attendance_days", "attendance_number", "checkin_days"),
        "points": ("cpoints", "points", "point"),
        "experience": ("cexperience", "experience"),
        "gold": ("cgold", "gold"),
    }
    for name, keys in values.items():
        value = _dig_value(payload, keys)
        if value:
            result[name] = value
    return result


def _visible_text(source: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", source, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_module.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_chiphell_page(
    source: str,
    cookies: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Validate the Discuz login state and extract the visible account summary."""
    page_source = str(source or "")
    page_text = _visible_text(page_source)
    cookie_auth = any(
        str(item.get("name") or "").lower().endswith("_auth")
        and bool(str(item.get("value") or "").strip())
        for item in (cookies or [])
        if isinstance(item, dict)
    )
    logout_marker = bool(re.search(
        r"member\.php\?mod=logging(?:&amp;|&)action=logout",
        page_source,
        flags=re.I,
    ))
    if not cookie_auth and not logout_marker:
        return {
            "status": "failed",
            "message": "未检测到 Chiphell 登录态，请更新 Cookie",
        }

    username = ""
    match = re.search(
        r"<strong[^>]*class=[\"'][^\"']*\bvwmy\b[^\"']*[\"'][^>]*>.*?<a[^>]*>(.*?)</a>",
        page_source,
        flags=re.I | re.S,
    )
    if match:
        username = _visible_text(match.group(1))

    points = ""
    match = re.search(
        r">\s*积分\s*[:：]\s*([^<]{1,80})</a>",
        page_source,
        flags=re.I,
    )
    if match:
        points = html_module.unescape(match.group(1)).replace("\xa0", " ").strip()
    if not points:
        match = re.search(
            r"积分\s*[:：]\s*([0-9][0-9,.]*(?:\s*[^\s]{0,6})?)",
            page_text,
            flags=re.I,
        )
        if match:
            points = match.group(1).strip(" -|，,")

    result = {
        "status": "success",
        "message": "论坛页访问成功，登录态有效",
    }
    if username:
        result["username"] = username
    if points:
        result["points"] = points
    return result


def prune_history(
    records: Iterable[Dict[str, Any]],
    keep_days: int,
    now: Optional[datetime] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Keep recent records while retaining malformed legacy rows for diagnosis."""
    current = now or datetime.now()
    kept = []
    for record in records:
        if not isinstance(record, dict):
            continue
        try:
            created = datetime.strptime(str(record.get("date") or ""), "%Y-%m-%d %H:%M:%S")
            if (current - created).days >= max(1, int(keep_days)):
                continue
        except (TypeError, ValueError):
            pass
        kept.append(dict(record))
    return kept[-max(1, int(limit)):]
