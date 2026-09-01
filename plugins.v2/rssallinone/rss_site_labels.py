"""PT site-specific Mandarin and effects label detection for RSS entries."""

from __future__ import annotations

import html
import re
import threading
import time
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, quote, urljoin, urlparse

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


class ChdHrError(RuntimeError):
    """Rainbow Island HR list request or parse failure."""


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
        min_request_interval_seconds: Optional[float] = None,
    ) -> None:
        self.gateway = gateway
        self.sleeper = sleeper or time.sleep
        self.clock = clock or time.monotonic
        self.logger = logger
        if min_request_interval_seconds is not None:
            try:
                self.request_interval_seconds = max(1.0, float(min_request_interval_seconds))
            except (TypeError, ValueError):
                self.request_interval_seconds = float(MIN_REQUEST_INTERVAL_SECONDS)
        else:
            self.request_interval_seconds = float(MIN_REQUEST_INTERVAL_SECONDS)

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
        allow_search_without_detail: bool = False,
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
        search_query = ""
        if not requested:
            return result

        site_kind = identify_site_kind(access)
        result["site_kind"] = site_kind
        if not site_kind:
            result["reason"] = "所选站点没有已实现的标签解析规则"
            return result

        try:
            if site_kind == "ubits":
                request_url = _ubits_detail_url(access, detail_url, torrent_id)
                if request_url:
                    page = self._request(request_url, access)
                    mandarin, effects = parse_ubits_labels(
                        page, _keywords(cn_keywords)
                    )
                elif allow_search_without_detail:
                    base_url = str(
                        getattr(access, "site_url", "")
                        or getattr(access, "referer", "")
                        or ""
                    ).strip()
                    query = clean_search_title(title)
                    search_query = query
                    if not base_url:
                        raise SiteLabelError("站点身份缺少站点 URL")
                    if not query:
                        raise SiteLabelError("RSS 标题清理后无法用于站内搜索")
                    request_url = urljoin(
                        base_url.rstrip("/") + "/",
                        f"torrents.php?search={quote(query)}",
                    )
                    page = self._request(request_url, access)
                    block, selected_id = select_exact_result(
                        page, torrent_id, search_title=query
                    )
                    result["torrent_id"] = selected_id
                    base = urlparse(base_url)
                    request_url = (
                        f"{base.scheme}://{base.netloc}/details.php?id={selected_id}"
                    )
                    mandarin, effects = parse_ubits_labels(
                        block, _keywords(cn_keywords)
                    )
                else:
                    raise SiteLabelError("UBits RSS 条目缺少详情页链接")
            else:
                base_url = str(
                    getattr(access, "site_url", "")
                    or getattr(access, "referer", "")
                    or ""
                ).strip()
                if not base_url:
                    raise SiteLabelError("站点身份缺少站点 URL")
                query = clean_search_title(title)
                search_query = query
                if not query:
                    raise SiteLabelError("RSS 标题清理后无法用于站内搜索")
                request_url = urljoin(
                    base_url.rstrip("/") + "/",
                    f"torrents.php?search={quote(query)}",
                )
                page = self._request(request_url, access)
                block, selected_id = select_exact_result(
                    page, torrent_id, search_title=query
                )
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
                f"RSS一条龙：{'手动' if allow_search_without_detail else 'RSS'}站点标签识别失败 "
                f"{site_kind or 'unknown'}：{error}"
                + (f"，搜索名称={search_query}" if search_query else ""),
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
                + self.request_interval_seconds
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


CHD_HR_URL = "https://ptchdbits.co/hnr.php"
CHD_HR_PAGE_SIZE = 25
CHD_HR_DETAIL_ID_PATTERN = re.compile(
    r"details\.php\?id=(\d+)(?:&|&amp;)hit=1",
    re.IGNORECASE,
)
CHD_HR_DETAIL_HREF_PATTERN = re.compile(
    r"<a\b[^>]*\bhref\s*=\s*([\"'])(.*?)\1",
    re.IGNORECASE | re.DOTALL,
)
CHD_HR_USER_ID_PATTERN = re.compile(
    r"userdetails\.php\?id=(\d+)",
    re.IGNORECASE,
)
CHD_HR_COUNT_PATTERN = re.compile(
    r"href\s*=\s*[\"']hnr\.php\?id=\d+[\"'][^>]*>.*?"
    r"H\s*(?:&amp;|&)\s*R\s*:[^<]*</font>\s*</a>"
    r"(?:(?:\s|&nbsp;|<[^>]*>))*?(\d+)",
    re.IGNORECASE | re.DOTALL,
)


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


def chd_hr_list_url(access: Any = None, html_text: str = "") -> str:
    user_id = ""
    cookie = str(getattr(access, "cookie", "") or "")
    match = re.search(r"(?i)(?:^|;\s*)c_secure_uid=([^;]+)", cookie)
    if match:
        user_id = _decode_nexus_uid(match.group(1))
    if not user_id:
        found = CHD_HR_USER_ID_PATTERN.search(str(html_text or ""))
        if found:
            user_id = found.group(1)
    if not user_id:
        raise ChdHrError("彩虹岛站点身份无法确定 HR 用户 ID")
    return f"{CHD_HR_URL}?id={user_id}"


def chd_hr_page_url(list_url: str, page: int) -> str:
    """Return a numbered CHD HR page while preserving the user id query."""
    normalized = str(list_url or "").strip()
    try:
        page_number = max(0, int(page))
    except (TypeError, ValueError):
        page_number = 0
    if page_number == 0 or not normalized:
        return normalized
    separator = "&" if "?" in normalized else "?"
    return f"{normalized}{separator}page={page_number}"


def parse_chd_hr_total_count(page: str) -> int:
    """Read the total H&R count shown beside the CHD HR link."""
    text = html.unescape(str(page or ""))
    match = CHD_HR_COUNT_PATTERN.search(text)
    if not match:
        return 0
    try:
        return max(0, int(match.group(1)))
    except (TypeError, ValueError):
        return 0


def parse_chd_hr_torrent_ids(page: str) -> list[str]:
    text = str(page or "")
    if re.search(r"未登录|takelogin\.php|该页面必须在登录后才能访问", text):
        raise ChdHrError("彩虹岛 HR 页面未登录")
    if not re.search(
        r"<title[^>]*>\s*CHDBits\s*::\s*Hit\s+And\s+Runs\b",
        text,
        re.IGNORECASE,
    ):
        raise ChdHrError("彩虹岛 HR 页面内容无效")
    # CHDBits uses a fixed details.php?id=...&hit=1 link for every HR row.
    # Select the matching records table first, then count only those links;
    # header cells such as 类型/标题/H&R百分比 contain no matching link and are
    # therefore never included. If the site's markup changes enough that the
    # table cannot be isolated, retain the same strict link scan as a fallback.
    scope = _chd_hr_table(text)
    if scope:
        ids = CHD_HR_DETAIL_ID_PATTERN.findall(html.unescape(scope))
    else:
        search_scope = _search_results_table(text)
        ids = _detail_ids_from_links(search_scope) if search_scope else []
        if not ids:
            ids = CHD_HR_DETAIL_ID_PATTERN.findall(html.unescape(text))

    unique: list[str] = []
    seen = set()
    for torrent_id in ids:
        if torrent_id in seen:
            continue
        seen.add(torrent_id)
        unique.append(torrent_id)
    return unique


def count_chd_hr_torrent_links(page: str) -> int:
    """Count HR detail links before ID de-duplication."""
    text = str(page or "")
    if re.search(r"未登录|takelogin\.php|该页面必须在登录后才能访问", text):
        raise ChdHrError("彩虹岛 HR 页面未登录")
    if not re.search(
        r"<title[^>]*>\s*CHDBits\s*::\s*Hit\s+And\s+Runs\b",
        text,
        re.IGNORECASE,
    ):
        raise ChdHrError("彩虹岛 HR 页面内容无效")
    scope = _chd_hr_table(text)
    return len(CHD_HR_DETAIL_ID_PATTERN.findall(html.unescape(scope or text)))


def _chd_hr_table(page: object) -> str:
    """Return the fixed-width table used by NexusPHP's HR list page."""
    source = str(page or "")
    candidates: list[tuple[int, str]] = []
    for table in _html_tables(source):
        opening = table.split(">", 1)[0]
        # CHDBits uses border=1/cellspacing=0/cellpadding=5/width=1000
        # for the HR records table. Accept quoted or unquoted attributes and
        # tolerate arbitrary attribute order/whitespace.
        attr_matches = re.finditer(
            r"([\w:-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
            opening,
            flags=re.IGNORECASE,
        )
        attrs = {
            match.group(1).casefold(): str(
                match.group(2) or match.group(3) or match.group(4) or ""
            )
            for match in attr_matches
        }
        normalized = {key: str(value).strip().casefold() for key, value in attrs.items()}
        if (
            normalized.get("border") == "1"
            and normalized.get("width") == "1000"
            and normalized.get("cellspacing") == "0"
            and normalized.get("cellpadding") == "5"
        ):
            link_count = len(
                CHD_HR_DETAIL_ID_PATTERN.findall(html.unescape(table))
            )
            candidates.append((link_count, table))
    if not candidates:
        return ""
    link_count, table = max(candidates, key=lambda item: item[0])
    return table if link_count > 0 else ""


def _html_tables(page: object) -> list[str]:
    """Extract complete tables while respecting nested table elements."""
    source = str(page or "")
    token_pattern = re.compile(r"<table\b[^>]*>|</table\s*>", re.IGNORECASE)
    tokens = list(token_pattern.finditer(source))
    tables: list[str] = []
    for index, token in enumerate(tokens):
        if token.group(0).casefold().startswith("</table"):
            continue
        depth = 0
        for candidate in tokens[index:]:
            if candidate.group(0).casefold().startswith("</table"):
                depth -= 1
                if depth == 0:
                    tables.append(source[token.start():candidate.end()])
                    break
            else:
                depth += 1
    return tables


def _detail_ids_from_links(fragment: object) -> list[str]:
    ids: list[str] = []
    for match in CHD_HR_DETAIL_HREF_PATTERN.finditer(str(fragment or "")):
        href = html.unescape(str(match.group(2) or "")).strip()
        parsed = urlparse(href)
        if parsed.path.casefold().rstrip("/").split("/")[-1] != "details.php":
            continue
        torrent_id = str((parse_qs(parsed.query).get("id") or [""])[0]).strip()
        if torrent_id.isdigit():
            ids.append(torrent_id)
    return ids


def _decode_nexus_uid(value: object) -> str:
    import base64
    from urllib.parse import unquote

    raw = unquote(str(value or "").strip())
    if not raw:
        return ""
    padded = raw + ("=" * ((4 - len(raw) % 4) % 4))
    decoded = ""
    try:
        decoded = base64.b64decode(padded).decode("utf-8", errors="ignore")
    except Exception:
        decoded = ""
    match = re.search(r"\d+", decoded or "")
    if match:
        return match.group(0)
    match = re.search(r"\d+", raw)
    return match.group(0) if match else ""


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


def select_exact_result(
    page: str,
    torrent_id: object,
    *,
    search_title: object = "",
) -> Tuple[str, str]:
    candidates = _candidate_blocks(page)
    if not candidates:
        raise SiteLabelError("站内搜索没有找到种子详情结果")
    if len(candidates) == 1:
        return candidates[0][1], candidates[0][0]
    wanted = str(torrent_id or "").strip()
    if not wanted:
        raise SiteLabelError("站内搜索有多条结果，已跳过匹配")
    for candidate_id, block in candidates:
        if candidate_id == wanted:
            return block, candidate_id
    raise SiteLabelError("站内搜索有多条结果，但没有命中 RSS torrent ID")


def _normalized_search_title(value: object) -> str:
    """Normalize release titles for exact comparison across dots/spaces."""
    text = html.unescape(str(value or "")).casefold()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^0-9a-z\u3400-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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
    source = _search_results_table(page)
    if not source:
        return []
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


def _search_results_table(page: object) -> str:
    """Return only the site's torrent search table, excluding recommendations."""
    source = str(page or "")
    for table in re.findall(
        r"<table\b[^>]*>.*?</table>",
        source,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        opening = table.split(">", 1)[0]
        class_match = re.search(
            r"\bclass\s*=\s*(['\"])(.*?)\1",
            opening,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not class_match:
            continue
        classes = re.split(r"\s+", class_match.group(2).strip())
        if any(item.casefold() == "torrents" for item in classes):
            return table
    return ""


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
    text = _normalized_label_text(value)
    return any(
        _normalized_label_text(item) in text
        for item in candidates
        if _normalized_label_text(item)
    )


def _keywords(value: object) -> List[str]:
    items = re.split(r"[,，]", str(value or ""))
    return [item.strip() for item in items if item.strip()] or [
        "国语", "国配", "國語", "國配",
    ]


def _plain_text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", str(fragment or "")))


def _normalized_label_text(value: object) -> str:
    return re.sub(r"\s+", "", html.unescape(str(value or ""))).casefold()


def _ubits_detail_url(access: Any, detail_url: object, torrent_id: object) -> str:
    supplied = str(detail_url or "").strip()
    parsed = urlparse(supplied)
    query_id = str((parse_qs(parsed.query).get("id") or [""])[0]).strip()
    wanted_id = str(torrent_id or query_id).strip()
    if not wanted_id:
        match = re.search(r"details\.php\?[^#]*?\bid=(\d+)", supplied, flags=re.I)
        wanted_id = match.group(1) if match else ""
    base_url = str(
        getattr(access, "site_url", "")
        or getattr(access, "referer", "")
        or supplied
        or ""
    ).strip()
    if wanted_id and base_url:
        base = urlparse(base_url)
        if base.scheme and base.netloc:
            base_url = f"{base.scheme}://{base.netloc}/"
        return urljoin(base_url.rstrip("/") + "/", f"details.php?id={wanted_id}")
    return supplied


def _site_request_key(access: Any, url: str) -> str:
    site_url = str(
        getattr(access, "site_url", "")
        or getattr(access, "referer", "")
        or url
    )
    return str(urlparse(site_url).hostname or site_url).casefold()
