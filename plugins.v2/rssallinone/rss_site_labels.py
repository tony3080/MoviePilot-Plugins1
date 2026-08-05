"""PT site-specific Mandarin and effects label detection for RSS entries."""

from __future__ import annotations

import html
import re
import threading
import time
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Sequence, Tuple
from urllib.parse import quote, urljoin, urlparse

from .rss_feed import mask_url


TRANSIENT_HTTP_STATUS = {403, 429, 503}
MIN_REQUEST_INTERVAL_SECONDS = 60
SITE_COOLDOWN_SECONDS = 300


class SiteLabelError(RuntimeError):
    """A site-label request or exact-result selection failure."""


class SiteHttpError(SiteLabelError):
    def __init__(self, status_code: int):
        self.status_code = int(status_code or 0)
        super().__init__(f"站点请求 HTTP {self.status_code}")


class _ElementCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[Dict[str, Any]] = []
        self.elements: List[Dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str]]) -> None:
        node = {
            "tag": str(tag or "").casefold(),
            "attrs": {str(key or "").casefold(): str(value or "") for key, value in attrs},
            "text": [],
        }
        self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, str]]) -> None:
        node = {
            "tag": str(tag or "").casefold(),
            "attrs": {str(key or "").casefold(): str(value or "") for key, value in attrs},
            "text": [],
        }
        self.elements.append(node)

    def handle_data(self, data: str) -> None:
        for node in self.stack:
            node["text"].append(str(data or ""))

    def handle_endtag(self, tag: str) -> None:
        wanted = str(tag or "").casefold()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] != wanted:
                continue
            closing = self.stack[index:]
            del self.stack[index:]
            self.elements.extend(reversed(closing))
            break

    def close(self) -> None:
        super().close()
        if self.stack:
            self.elements.extend(reversed(self.stack))
            self.stack.clear()


class SiteLabelService:
    """Apply the deliberately site-specific label rules used by ReelHarbor V1."""

    _request_lock = threading.Lock()
    _request_state: Dict[str, Dict[str, float]] = {}

    def __init__(
        self,
        gateway: Any,
        *,
        sleeper: Any = None,
        clock: Any = None,
        logger: Any = None,
    ) -> None:
        self.gateway = gateway
        self.sleeper = sleeper or time.sleep
        self.clock = clock or time.monotonic
        self.logger = logger

    def detect(
        self,
        *,
        access: Any,
        title: str,
        detail_url: str,
        torrent_id: str,
        cn_keywords: object,
        recognize_cn: bool,
        recognize_fx: bool,
    ) -> Dict[str, Any]:
        requested = bool(recognize_cn or recognize_fx)
        result = {
            "requested": requested,
            "status": "skipped",
            "site_kind": "",
            "mandarin": False,
            "effects": False,
            "torrent_id": str(torrent_id or "").strip(),
            "request_url_masked": "",
            "reason": "未启用国语或特效识别" if not requested else "",
        }
        if not requested:
            return result

        site_kind = identify_site_kind(access)
        result["site_kind"] = site_kind
        if not site_kind:
            result["reason"] = "所选站点没有已实现的标签解析规则"
            return result

        try:
            if site_kind == "ubits":
                request_url = str(detail_url or "").strip()
                if not request_url:
                    raise SiteLabelError("UBits RSS 条目缺少详情页链接")
                page = self._request(request_url, access)
                mandarin, effects = parse_ubits_labels(
                    page, _keywords(cn_keywords)
                )
            else:
                base_url = str(
                    getattr(access, "site_url", "")
                    or getattr(access, "referer", "")
                    or ""
                ).strip()
                if not base_url:
                    raise SiteLabelError("站点身份缺少站点 URL")
                query = clean_search_title(title)
                if not query:
                    raise SiteLabelError("RSS 标题清理后无法用于站内搜索")
                request_url = urljoin(
                    base_url.rstrip("/") + "/",
                    f"torrents.php?search={quote(query)}",
                )
                page = self._request(request_url, access)
                block, selected_id = select_exact_result(page, torrent_id)
                result["torrent_id"] = selected_id
                if site_kind == "chd":
                    mandarin, effects = parse_chd_labels(
                        block, _keywords(cn_keywords)
                    )
                else:
                    mandarin, effects = parse_hdsky_labels(
                        block, _keywords(cn_keywords)
                    )
            applied_mandarin = bool(mandarin and recognize_cn)
            applied_effects = bool(effects and recognize_fx)
            result.update({
                "status": (
                    "matched" if applied_mandarin or applied_effects
                    else "not_matched"
                ),
                "mandarin": applied_mandarin,
                "effects": applied_effects,
                "request_url_masked": mask_url(request_url),
                "reason": "",
            })
        except Exception as error:
            result.update({
                "status": "failed",
                "reason": str(error)[:500],
            })
            self._log(
                "error",
                f"RSS一条龙：站点标签识别失败 {site_kind or 'unknown'}：{error}",
            )
        return result

    def _request(self, url: str, access: Any) -> str:
        site_key = _site_request_key(access, url)
        last_error: Exception | None = None
        for attempt in range(2):
            self._wait_for_site(site_key)
            try:
                return str(self.gateway.fetch_site_html(url, access) or "")
            except SiteHttpError as error:
                last_error = error
                if error.status_code not in TRANSIENT_HTTP_STATUS or attempt > 0:
                    raise
                with self._request_lock:
                    state = self._request_state.setdefault(site_key, {})
                    state["cooldown_until"] = self.clock() + SITE_COOLDOWN_SECONDS
            except Exception:
                raise
        raise last_error or SiteLabelError("站点标签请求失败")

    def _wait_for_site(self, site_key: str) -> None:
        with self._request_lock:
            state = self._request_state.setdefault(site_key, {})
            now = self.clock()
            wait_seconds = max(
                0.0,
                float(state.get("last_request", 0.0))
                + MIN_REQUEST_INTERVAL_SECONDS
                - now,
                float(state.get("cooldown_until", 0.0)) - now,
            )
        if wait_seconds > 0:
            self.sleeper(wait_seconds)
        with self._request_lock:
            self._request_state.setdefault(site_key, {})["last_request"] = self.clock()

    def _log(self, level: str, message: str) -> None:
        method = getattr(self.logger, level, None) if self.logger else None
        if callable(method):
            method(message)


def identify_site_kind(access: Any) -> str:
    name = str(
        getattr(access, "site_key", "")
        or getattr(access, "site_name", "")
        or ""
    ).casefold()
    site_url = str(
        getattr(access, "site_url", "")
        or getattr(access, "referer", "")
        or ""
    )
    host = str(urlparse(site_url).hostname or "").casefold()
    if "ubits" in name.replace(" ", "") or host == "ubits.club":
        return "ubits"
    if any(value in name for value in ("ptchdbits", "chdbits", "ptchd", "彩虹")) \
            or host in {"ptchdbits.co", "ptchdbits.net"}:
        return "chd"
    if any(value in name for value in ("hdsky", "hd sky", "天空")) \
            or host == "hdsky.me":
        return "hdsky"
    return ""


def parse_ubits_labels(page: str, keywords: Sequence[str]) -> Tuple[bool, bool]:
    scope = _ubits_tag_scope(page)
    elements = _elements(scope)
    mandarin = any(
        "tag_id5=1" in str(item["attrs"].get("href") or "").casefold()
        for item in elements
    ) or any(
        _has_class(item, "tag") and _contains_any(item["text"], keywords)
        for item in elements
    )
    effects = any(
        _has_class(item, "tag")
        and _contains_any(item["text"], ("特效", "特效字幕"))
        for item in elements
    )
    return mandarin, effects


def parse_chd_labels(block: str, keywords: Sequence[str]) -> Tuple[bool, bool]:
    elements = _elements(block)
    mandarin = any(
        _has_class(item, "tag-gy") and _contains_any(item["text"], keywords)
        for item in elements
    )
    effects = any(_has_class(item, "tag-txsub") for item in elements)
    return mandarin, effects


def parse_hdsky_labels(block: str, keywords: Sequence[str]) -> Tuple[bool, bool]:
    tags = [
        item for item in _elements(block)
        if item["tag"] == "span" and _has_class(item, "optiontag")
    ]
    mandarin = any(_contains_any(item["text"], keywords) for item in tags)
    effects = any(
        _contains_any(item["text"], ("特效", "特效字幕")) for item in tags
    )
    return mandarin, effects


def select_exact_result(page: str, torrent_id: object) -> Tuple[str, str]:
    candidates = _candidate_blocks(page)
    if not candidates:
        raise SiteLabelError("站内搜索没有找到种子详情结果")
    if len(candidates) == 1:
        return candidates[0][1], candidates[0][0]
    wanted = str(torrent_id or "").strip()
    if not wanted:
        raise SiteLabelError("站内搜索有多条结果，但 RSS 条目没有 torrent ID")
    for candidate_id, block in candidates:
        if candidate_id == wanted:
            return block, candidate_id
    raise SiteLabelError("站内搜索有多条结果，但没有命中 RSS torrent ID")


def clean_search_title(value: object) -> str:
    title = re.sub(r"<!\[CDATA\[|\]\]>", "", str(value or ""), flags=re.I)
    bracket_values = re.findall(r"\[([^\]]*)\]|【([^】]*)】", title)
    outside = re.sub(r"\[[^\]]*\]|【[^】]*】", " ", title)
    outside = re.sub(r"\s+", " ", outside).strip(" ._-|")
    if outside:
        return outside
    for groups in bracket_values:
        bracket = next((item for item in groups if item), "")
        for candidate in re.split(r"\s*(?:/|\|)\s*", bracket):
            candidate = re.sub(r"\([^)]*\)|（[^）]*）", " ", candidate)
            candidate = re.sub(r"\s+", " ", candidate).strip(" ._-|")
            if candidate and not re.fullmatch(
                r"(?i)(?:remux|web-?dl|web|bluray|蓝光|原盘|国语|国配|中字|特效字幕?)",
                candidate,
            ):
                return candidate
    return ""


def _candidate_blocks(page: str) -> List[Tuple[str, str]]:
    source = str(page or "")
    matches = list(re.finditer(
        r"details\.php\?[^\"'<>]*?\bid=(\d+)", source, flags=re.I
    ))
    candidates: List[Tuple[str, str]] = []
    seen = set()
    for match in matches:
        torrent_id = match.group(1)
        if torrent_id in seen:
            continue
        seen.add(torrent_id)
        start = source.rfind("<tr", 0, match.start())
        end = source.find("</tr>", match.end())
        if start < 0 or end < 0:
            start = max(0, match.start() - 3000)
            end = min(len(source), match.end() + 5000)
        else:
            end += len("</tr>")
        candidates.append((torrent_id, source[start:end]))
    return candidates


def _ubits_tag_scope(page: str) -> str:
    source = str(page or "")
    for row in re.findall(r"<tr\b[^>]*>.*?</tr>", source, flags=re.I | re.S):
        text = _plain_text(row).casefold()
        if "标签" in text or "tags" in text:
            return row
    return source[:20000]


def _elements(fragment: str) -> List[Dict[str, Any]]:
    parser = _ElementCollector()
    try:
        parser.feed(str(fragment or ""))
        parser.close()
    except Exception:
        return []
    result = []
    for item in parser.elements:
        result.append({
            **item,
            "text": re.sub(r"\s+", " ", "".join(item["text"])).strip(),
        })
    return result


def _has_class(element: Dict[str, Any], expected: str) -> bool:
    classes = re.split(r"\s+", str(element["attrs"].get("class") or "").casefold())
    wanted = str(expected or "").casefold()
    return any(wanted in item for item in classes if item)


def _contains_any(value: object, candidates: Iterable[str]) -> bool:
    text = str(value or "").casefold()
    return any(str(item or "").strip().casefold() in text for item in candidates if str(item or "").strip())


def _keywords(value: object) -> List[str]:
    items = re.split(r"[,，]", str(value or ""))
    return [item.strip() for item in items if item.strip()] or ["国语", "国配"]


def _plain_text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", str(fragment or "")))


def _site_request_key(access: Any, url: str) -> str:
    site_url = str(
        getattr(access, "site_url", "")
        or getattr(access, "referer", "")
        or url
    )
    return str(urlparse(site_url).hostname or site_url).casefold()
