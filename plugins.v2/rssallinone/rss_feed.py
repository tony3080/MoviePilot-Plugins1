"""Read-only RSS/Atom fetching and preview classification."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from xml.etree import ElementTree


MAX_FEED_BYTES = 10 * 1024 * 1024
MAX_FEED_ITEMS = 2000
MAX_PREVIEW_ITEMS = 200
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36 MoviePilot/RssAllInOne"
)
TORRENT_ID_PATTERN = re.compile(
    r"(?:[?&](?:id|torrent[_-]?id)=)(\d+)(?:[&#]|$)",
    re.IGNORECASE,
)
SENSITIVE_QUERY_KEYS = {
    "accesstoken",
    "apikey",
    "auth",
    "authkey",
    "key",
    "passkey",
    "password",
    "pwd",
    "rsskey",
    "refreshtoken",
    "secret",
    "sig",
    "signature",
    "token",
}


class RssFeedError(RuntimeError):
    """A safe, user-facing RSS preview failure."""


@dataclass(frozen=True)
class FetchResult:
    body: bytes
    final_url: str
    content_type: str = ""


@dataclass(frozen=True)
class ParsedEntry:
    title: str
    detail_url: str
    guid: str
    enclosure_url: str
    enclosure_type: str
    published: str


Fetcher = Callable[[str], FetchResult]
ExistingKeys = Callable[[str, Sequence[str]], Iterable[str]]


class RssPreviewService:
    """Fetch and classify one configured task without mutating downstream state."""

    def __init__(
        self,
        fetcher: Optional[Fetcher] = None,
        existing_keys: Optional[ExistingKeys] = None,
    ) -> None:
        self.fetcher = fetcher or fetch_feed
        self.existing_keys = existing_keys or (lambda _task_id, _keys: ())

    def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_id = str(task.get("id") or "").strip()
        task_name = str(task.get("name") or "").strip()
        config = task.get("config") if isinstance(task.get("config"), dict) else {}
        rss_url = validate_feed_url(config.get("rss_url"))
        name_contains = str(config.get("name_contains") or "").strip()

        fetched = self.fetcher(rss_url)
        body = bytes(fetched.body or b"")
        if not body:
            raise RssFeedError("RSS 请求成功，但响应内容为空")
        if len(body) > MAX_FEED_BYTES:
            raise RssFeedError(
                f"RSS 响应超过 {MAX_FEED_BYTES // 1024 // 1024} MiB 安全上限"
            )

        feed, parsed_entries = parse_feed(body)
        prepared = [
            prepare_entry(task_id, entry)
            for entry in parsed_entries[:MAX_FEED_ITEMS]
        ]
        source_keys = [item["source_key"] for item in prepared if item["source_key"]]
        existing = set(self.existing_keys(task_id, source_keys) or ())
        seen: Set[str] = set()
        items: List[Dict[str, Any]] = []
        counts = {
            "total": len(prepared),
            "ready": 0,
            "filtered": 0,
            "missing_enclosure": 0,
            "duplicate": 0,
            "invalid": 0,
        }

        for position, prepared_entry in enumerate(prepared):
            status, reason = classify_entry(
                prepared_entry,
                name_contains=name_contains,
                existing=existing,
                seen=seen,
            )
            counts[status] += 1
            source_key = prepared_entry["source_key"]
            if source_key:
                seen.add(source_key)
            items.append({
                **prepared_entry,
                "row_key": f"{source_key or 'invalid'}:{position}",
                "status": status,
                "reason": reason,
            })

        counts["eligible"] = counts["ready"]
        preview_items = items[:MAX_PREVIEW_ITEMS]
        return {
            "task": {"id": task_id, "name": task_name},
            "feed": {
                **feed,
                "requested_url_masked": mask_url(rss_url),
                "final_url_masked": mask_url(fetched.final_url or rss_url),
                "content_type": str(fetched.content_type or ""),
            },
            "counts": counts,
            "items": preview_items,
            "truncated": len(items) > len(preview_items),
            "read_only": True,
        }


def fetch_feed(url: str) -> FetchResult:
    """Fetch through MoviePilot's HTTP utility so runtime networking stays native."""
    safe_url = validate_feed_url(url)
    try:
        from app.utils.http import RequestUtils

        response = RequestUtils(ua=USER_AGENT).get_res(safe_url)
    except Exception as error:
        raise RssFeedError(
            f"RSS 请求失败：{_safe_error_text(error)}（{mask_url(safe_url)}）"
        ) from error
    if not response:
        raise RssFeedError(f"RSS 请求无响应（{mask_url(safe_url)}）")
    status_code = int(getattr(response, "status_code", 200) or 0)
    if status_code != 200:
        raise RssFeedError(
            f"RSS HTTP 状态码 {status_code}（{mask_url(safe_url)}）"
        )
    body = getattr(response, "content", None)
    if body is None:
        body = str(getattr(response, "text", "") or "").encode("utf-8")
    elif isinstance(body, str):
        body = body.encode("utf-8")
    headers = getattr(response, "headers", {}) or {}
    return FetchResult(
        body=bytes(body),
        final_url=str(getattr(response, "url", safe_url) or safe_url),
        content_type=str(headers.get("Content-Type") or headers.get("content-type") or ""),
    )


def parse_feed(xml_content: bytes) -> Tuple[Dict[str, str], List[ParsedEntry]]:
    try:
        root = ElementTree.fromstring(xml_content)
    except (ElementTree.ParseError, ValueError) as error:
        raise RssFeedError(f"RSS XML 解析失败：{error}") from error

    root_name = _local_name(root.tag)
    feed_type = "atom" if root_name == "feed" else "rss"
    container = root
    if root_name in {"rss", "rdf"}:
        channel = next(
            (item for item in root if _local_name(item.tag) == "channel"),
            None,
        )
        if channel is not None:
            container = channel
    feed = {
        "type": feed_type,
        "title": _child_text(container, {"title"}),
    }
    entries: List[ParsedEntry] = []
    for node in root.iter():
        if _local_name(node.tag) not in {"item", "entry"}:
            continue
        entries.append(_parse_entry(node))
        if len(entries) >= MAX_FEED_ITEMS:
            break
    return feed, entries


def validate_feed_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as error:
        raise RssFeedError("RSS URL 端口无效") from error
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.netloc
        or port is not None and not 1 <= port <= 65535
    ):
        raise RssFeedError("RSS URL 必须是有效的 HTTP 或 HTTPS 地址")
    return url


def mask_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return url
    try:
        parsed_port = parsed.port
    except ValueError:
        return _mask_all_query_values(url)
    query = []
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
        query.append((key, "***" if _sensitive_query_key(key) else item_value))
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    port = f":{parsed_port}" if parsed_port else ""
    if parsed.username:
        credentials = str(parsed.username)
        if parsed.password is not None:
            credentials += ":***"
        credentials += "@"
    else:
        credentials = ""
    return urlunparse((
        parsed.scheme,
        f"{credentials}{hostname}{port}",
        parsed.path,
        parsed.params,
        urlencode(query, doseq=True, safe="*"),
        "",
    ))


def canonical_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return url
    try:
        parsed_port = parsed.port
    except ValueError:
        return url
    query = sorted(parse_qsl(parsed.query, keep_blank_values=True))
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    default_port = (scheme == "http" and parsed_port == 80) or (
        scheme == "https" and parsed_port == 443
    )
    port = f":{parsed_port}" if parsed_port and not default_port else ""
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    return urlunparse((
        scheme,
        f"{userinfo}{hostname}{port}",
        parsed.path or "/",
        parsed.params,
        urlencode(query, doseq=True),
        "",
    ))


def extract_torrent_id(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        match = TORRENT_ID_PATTERN.search(text)
        if match:
            return match.group(1)
    return ""


def _parse_entry(node: ElementTree.Element) -> ParsedEntry:
    detail_url = ""
    enclosure_candidates: List[Tuple[int, str, str]] = []
    for child in node:
        name = _local_name(child.tag)
        if name == "link":
            href = str(child.attrib.get("href") or "").strip()
            text = _text(child)
            link_url = href or text
            rel = str(child.attrib.get("rel") or "alternate").casefold()
            link_type = str(child.attrib.get("type") or "").strip()
            if rel == "enclosure" and link_url:
                priority = _enclosure_priority(link_url, link_type)
                if priority > 0:
                    enclosure_candidates.append((priority, link_url, link_type))
            elif rel in {"", "alternate"} and link_url and not detail_url:
                detail_url = link_url
        elif name == "enclosure":
            enclosure_url = str(
                child.attrib.get("url") or child.attrib.get("href") or ""
            ).strip()
            enclosure_type = str(child.attrib.get("type") or "").strip()
            if enclosure_url:
                priority = _enclosure_priority(enclosure_url, enclosure_type)
                if priority > 0:
                    enclosure_candidates.append(
                        (priority, enclosure_url, enclosure_type)
                    )

    enclosure_candidates.sort(key=lambda item: item[0], reverse=True)
    enclosure_url = enclosure_candidates[0][1] if enclosure_candidates else ""
    enclosure_type = enclosure_candidates[0][2] if enclosure_candidates else ""
    guid = _child_text(node, {"guid", "id"})
    if not detail_url and _looks_like_url(guid):
        detail_url = guid
    return ParsedEntry(
        title=_child_text(node, {"title"}),
        detail_url=detail_url,
        guid=guid,
        enclosure_url=enclosure_url,
        enclosure_type=enclosure_type,
        published=_child_text(node, {"pubdate", "published", "updated", "date"}),
    )


def prepare_entry(task_id: str, entry: ParsedEntry) -> Dict[str, Any]:
    torrent_id = extract_torrent_id(
        entry.detail_url,
        entry.guid if _looks_like_url(entry.guid) else "",
        entry.enclosure_url,
    )
    identity_type = ""
    identity = ""
    if torrent_id:
        identity_type = "torrent_id"
        identity = f"torrent_id:{torrent_id}"
    elif entry.guid and not _looks_like_url(entry.guid):
        identity_type = "opaque_guid"
        identity = f"guid:{entry.guid}"
    elif entry.enclosure_url:
        identity_type = "enclosure_url"
        identity = f"enclosure:{canonical_url(entry.enclosure_url)}"
    elif entry.detail_url:
        identity_type = "detail_url"
        identity = f"detail:{canonical_url(entry.detail_url)}"
    elif entry.title:
        identity_type = "title_published"
        identity = f"title_published:{entry.title}\n{entry.published}"
    source_key = hashlib.sha256(f"{task_id}{identity}".encode("utf-8")).hexdigest() if identity else ""
    return {
        "title": entry.title,
        "published": entry.published,
        "torrent_id": torrent_id,
        "identity_type": identity_type,
        "source_key": source_key,
        "detail_url_masked": mask_url(entry.detail_url),
        "enclosure_url_masked": mask_url(entry.enclosure_url),
        "enclosure_type": entry.enclosure_type,
        "has_enclosure": bool(entry.enclosure_url),
    }


def classify_entry(
    item: Dict[str, Any],
    *,
    name_contains: str,
    existing: Set[str],
    seen: Set[str],
) -> Tuple[str, str]:
    source_key = str(item.get("source_key") or "")
    if source_key and source_key in existing:
        return "duplicate", "RSS 历史中已存在相同来源身份"
    if source_key and source_key in seen:
        return "duplicate", "当前订阅中存在重复来源身份"
    title = str(item.get("title") or "").strip()
    if not title:
        return "invalid", "RSS 条目缺少标题"
    if not source_key:
        return "invalid", "无法生成稳定的 RSS 来源身份"
    if name_contains and name_contains.casefold() not in title.casefold():
        return "filtered", f"标题不包含：{name_contains}"
    if not item.get("has_enclosure"):
        return "missing_enclosure", "RSS 条目缺少 enclosure 种子链接"
    return "ready", "可进入后续种子推送阶段"


def _child_text(node: ElementTree.Element, names: Set[str]) -> str:
    for child in node:
        if _local_name(child.tag) in names:
            value = _text(child)
            if value:
                return value
    return ""


def _text(node: ElementTree.Element) -> str:
    return " ".join("".join(node.itertext()).split())


def _local_name(tag: object) -> str:
    value = str(tag or "")
    if "}" in value:
        value = value.rsplit("}", 1)[-1]
    if ":" in value:
        value = value.rsplit(":", 1)[-1]
    return value.casefold()


def _looks_like_url(value: object) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)


def _enclosure_priority(url: str, content_type: str) -> int:
    normalized_type = str(content_type or "").casefold()
    normalized_url = str(url or "").casefold()
    if "bittorrent" in normalized_type:
        return 4
    if normalized_url.endswith(".torrent") or ".torrent?" in normalized_url:
        return 3
    if any(marker in normalized_url for marker in ("download.php", "download/", "torrent")):
        return 2
    if not normalized_type or "octet-stream" in normalized_type:
        return 1
    return 0


def _sensitive_query_key(value: object) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(value or "").casefold())
    return normalized in SENSITIVE_QUERY_KEYS


def _safe_error_text(error: Exception) -> str:
    text = " ".join(str(error or "").split())
    text = re.sub(r"([?&][^=&\s]+)=([^&\s]+)", r"\1=***", text)
    return text[:300] or error.__class__.__name__


def _mask_all_query_values(value: str) -> str:
    masked = re.sub(r"([?&][^=&#\s]+)=([^&#\s]*)", r"\1=***", str(value or ""))
    return masked.split("#", 1)[0]
