"""Pure parsing and matching logic for the Douban subscription plugin."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from xml.etree import ElementTree


DOUBAN_SUBJECT_RE = re.compile(r"(?:movie\.)?douban\.com/subject/(\d+)", re.IGNORECASE)
YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
IMAGE_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
MATCH_ACCEPT_SCORE = 80
MATCH_MIN_LEAD = 15

MEDIA_CATEGORY_LABELS = {
    "domestic": "国产剧",
    "western": "欧美剧",
    "japan_korea": "日韩剧",
    "other": "其他地区",
}
DOMESTIC_COUNTRIES = {
    "中国", "中国大陆", "大陆", "中国香港", "香港", "中国台湾", "台湾",
    "中国澳门", "澳门",
}
JAPAN_KOREA_COUNTRIES = {
    "日本", "韩国", "南韩", "朝鲜", "北朝鲜",
}
WESTERN_COUNTRIES = {
    "美国", "英国", "法国", "德国", "意大利", "西班牙", "葡萄牙", "加拿大",
    "澳大利亚", "新西兰", "爱尔兰", "奥地利", "瑞士", "比利时", "荷兰",
    "丹麦", "瑞典", "挪威", "芬兰", "冰岛", "波兰", "捷克", "匈牙利",
    "希腊", "俄罗斯", "乌克兰", "墨西哥", "巴西", "阿根廷", "智利",
    "南非",
}


@dataclass(frozen=True)
class FeedItem:
    """A normalized RSS or Atom entry."""

    title: str
    link: str = ""
    guid: str = ""
    description: str = ""
    published: str = ""
    source_url: str = ""
    douban_id: Optional[str] = None
    year: Optional[str] = None
    poster: str = ""

    @property
    def key(self) -> str:
        if self.douban_id:
            return f"douban:{self.douban_id}"
        raw = "\n".join((self.link, self.guid, self.title, self.year or ""))
        return f"rss:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["key"] = self.key
        return result


@dataclass(frozen=True)
class TitleHypothesis:
    """One possible interpretation of a source title."""

    title: str
    season: Optional[int]
    mode: str
    strength: str


@dataclass(frozen=True)
class TmdbCandidate:
    """TMDB facts needed by the deterministic scorer."""

    tmdb_id: int
    title: str
    original_title: str = ""
    names: Tuple[str, ...] = ()
    year: Optional[str] = None
    season: int = 1
    season_year: Optional[str] = None
    season_episode_count: Optional[int] = None
    actors: Tuple[str, ...] = ()
    directors: Tuple[str, ...] = ()
    mode: str = "exact_title"
    strength: str = "exact"
    hypothesis_title: str = ""


@dataclass(frozen=True)
class ScoredCandidate:
    """A TMDB candidate with its evidence trail."""

    candidate: TmdbCandidate
    identity_score: int
    structure_score: int
    score: int
    evidence: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["candidate"] = asdict(self.candidate)
        return result


@dataclass(frozen=True)
class MatchDecision:
    """Final threshold and margin decision."""

    accepted: bool
    status: str
    reason: str
    winner: Optional[ScoredCandidate] = None
    alternatives: Tuple[ScoredCandidate, ...] = field(default_factory=tuple)


def _local_name(tag: str) -> str:
    return str(tag or "").rsplit("}", 1)[-1].lower()


def _element_text(element: ElementTree.Element) -> str:
    return "".join(element.itertext()).strip()


def _child_text(node: ElementTree.Element, names: Iterable[str]) -> str:
    wanted = {name.lower() for name in names}
    for child in list(node):
        if _local_name(child.tag) in wanted:
            value = _element_text(child)
            if value:
                return value
    return ""


def _entry_link(node: ElementTree.Element) -> str:
    for child in list(node):
        if _local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href") or "").strip()
        rel = str(child.attrib.get("rel") or "alternate").lower()
        if href and rel in {"alternate", ""}:
            return href
        value = _element_text(child)
        if value:
            return value
    return ""


def _entry_categories(node: ElementTree.Element) -> str:
    values = []
    for child in list(node):
        if _local_name(child.tag) != "category":
            continue
        value = str(child.attrib.get("term") or _element_text(child) or "").strip()
        if value:
            values.append(value)
    return " ".join(values)


def extract_douban_id(*values: str) -> Optional[str]:
    """Extract a Douban subject ID from links or entry HTML."""
    for value in values:
        match = DOUBAN_SUBJECT_RE.search(html.unescape(str(value or "")))
        if match:
            return match.group(1)
    return None


def _extract_year(*values: str) -> Optional[str]:
    for value in values:
        match = YEAR_RE.search(str(value or ""))
        if match:
            return match.group(1)
    return None


def _extract_poster(value: str) -> str:
    match = IMAGE_RE.search(html.unescape(str(value or "")))
    return html.unescape(match.group(1)) if match else ""


def parse_feed(xml_text: str, source_url: str = "") -> List[FeedItem]:
    """Parse RSS 2.0 or Atom without requiring a third-party dependency."""
    if not str(xml_text or "").strip():
        return []
    root = ElementTree.fromstring(str(xml_text).lstrip("\ufeff"))
    entries = [
        node for node in root.iter()
        if _local_name(node.tag) in {"item", "entry"}
    ]
    result: List[FeedItem] = []
    seen = set()
    for node in entries:
        title = _child_text(node, {"title"}).strip()
        link = _entry_link(node)
        guid = _child_text(node, {"guid", "id"})
        description = _child_text(node, {"description", "summary", "content", "encoded"})
        published = _child_text(node, {"pubdate", "published", "updated"})
        categories = _entry_categories(node)
        if not title:
            continue
        douban_id = extract_douban_id(link, guid, description)
        item = FeedItem(
            title=title,
            link=link,
            guid=guid,
            description=description,
            published=published,
            source_url=source_url,
            douban_id=douban_id,
            year=_extract_year(title, categories, description),
            poster=_extract_poster(description),
        )
        if item.key in seen:
            continue
        seen.add(item.key)
        result.append(item)
    return result


def normalize_title(value: str) -> str:
    """Normalize titles for evidence comparison without losing source text."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return "".join(
        character for character in normalized
        if not unicodedata.category(character).startswith(("P", "Z"))
    )


_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_ROMAN_NUMBERS = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
}


def parse_season_number(value: str) -> Optional[int]:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if text.isdigit():
        number = int(text)
        return number if 0 <= number <= 50 else None
    roman = _ROMAN_NUMBERS.get(text.upper())
    if roman is not None:
        return roman
    if text == "十":
        return 10
    if "十" in text:
        left, right = text.split("十", 1)
        tens = _CHINESE_DIGITS.get(left, 1) if left else 1
        units = _CHINESE_DIGITS.get(right, 0) if right else 0
        number = tens * 10 + units
        return number if 0 <= number <= 50 else None
    if len(text) == 1:
        return _CHINESE_DIGITS.get(text)
    return None


def _append_hypothesis(
    result: List[TitleHypothesis],
    seen: set,
    title: str,
    season: Optional[int],
    mode: str,
    strength: str,
) -> None:
    clean_title = str(title or "").strip(" -_.")
    if not clean_title or season is not None and not 0 <= season <= 50:
        return
    key = (normalize_title(clean_title), season, mode)
    if key in seen:
        return
    seen.add(key)
    result.append(TitleHypothesis(clean_title, season, mode, strength))


def build_title_hypotheses(title: str) -> List[TitleHypothesis]:
    """Build exact and season-aware title paths, keeping weak suffixes optional."""
    source = unicodedata.normalize("NFKC", str(title or "")).strip()
    result: List[TitleHypothesis] = []
    seen = set()
    _append_hypothesis(result, seen, source, None, "exact_title", "exact")
    if not source or source.isdigit():
        return result

    strong_patterns = (
        re.compile(r"^(?P<base>.+?)\s*第\s*(?P<num>[零〇一二两三四五六七八九十\d]+)\s*季\s*$", re.I),
        re.compile(r"^(?P<base>.+?)[\s._-]+S0*(?P<num>\d{1,2})\s*$", re.I),
        re.compile(r"^(?P<base>.+?)[\s._-]+Season\s*0*(?P<num>\d{1,2})\s*$", re.I),
    )
    for pattern in strong_patterns:
        match = pattern.match(source)
        if not match:
            continue
        season = parse_season_number(match.group("num"))
        if season is not None:
            _append_hypothesis(
                result, seen, match.group("base"), season,
                "base_and_season", "strong",
            )

    part_match = re.match(
        r"^(?P<base>.+?)\s*第\s*(?P<num>[零〇一二两三四五六七八九十\d]+)\s*部\s*$",
        source,
        re.I,
    )
    if part_match:
        season = parse_season_number(part_match.group("num"))
        if season is not None:
            _append_hypothesis(
                result, seen, part_match.group("base"), season,
                "base_and_season", "weak",
            )

    arabic_match = re.match(r"^(?P<base>.*\D)(?P<num>[2-9]|1\d|20)$", source)
    if arabic_match and not YEAR_RE.search(arabic_match.group("num")):
        _append_hypothesis(
            result, seen, arabic_match.group("base"), int(arabic_match.group("num")),
            "base_and_season", "weak",
        )

    chinese_match = re.match(r"^(?P<base>.+?)(?P<num>[二两三四五六七八九十])$", source)
    if chinese_match:
        season = parse_season_number(chinese_match.group("num"))
        if season is not None and season >= 2:
            _append_hypothesis(
                result, seen, chinese_match.group("base"), season,
                "base_and_season", "weak",
            )

    roman_match = re.match(r"^(?P<base>.+?)[\s._-]+(?P<num>I{2,3}|IV|V|VI{0,3}|IX|X)$", source, re.I)
    if roman_match:
        season = parse_season_number(roman_match.group("num"))
        if season is not None and season >= 2:
            _append_hypothesis(
                result, seen, roman_match.group("base"), season,
                "base_and_season", "weak",
            )
    return result


def build_search_hypotheses(
    title: str,
    original_title: str = "",
    aliases: Sequence[str] = (),
) -> List[TitleHypothesis]:
    """Build deduplicated search paths from the primary and alternate titles."""
    result: List[TitleHypothesis] = []
    seen = set()
    title_sources = ((title, "exact_title"), (original_title, "original_title"))
    title_sources += tuple((alias, "alias_title") for alias in (aliases or [])[:8])
    for source_title, exact_mode in title_sources:
        for hypothesis in build_title_hypotheses(source_title):
            mode = exact_mode if hypothesis.mode == "exact_title" else hypothesis.mode
            key = (normalize_title(hypothesis.title), hypothesis.season)
            if not key[0] or key in seen:
                continue
            seen.add(key)
            result.append(TitleHypothesis(
                title=hypothesis.title,
                season=hypothesis.season,
                mode=mode,
                strength=hypothesis.strength,
            ))
    return result


def _positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _year_number(value: Any) -> Optional[int]:
    match = YEAR_RE.search(str(value or ""))
    return int(match.group(1)) if match else None


def extract_total_episode(douban_info: Dict[str, Any]) -> Optional[int]:
    """Read a declared total episode count from Douban detail fields only."""
    info = douban_info or {}
    for field_name in (
        "episodes_count",
        "episode_count",
        "total_episode",
        "total_episodes",
        "webisode_count",
    ):
        value = _positive_int(info.get(field_name))
        if value:
            return value
    for field_name in ("episodes_info", "card_subtitle"):
        text = str(info.get(field_name) or "")
        for pattern in (
            r"(?:全|共)\s*(\d{1,4})\s*集",
            r"(\d{1,4})\s*集\s*(?:全|完结)",
        ):
            match = re.search(pattern, text)
            if match:
                return _positive_int(match.group(1))
    return None


def has_started_airing(
    douban_info: Dict[str, Any],
    today: Optional[date] = None,
) -> bool:
    """Determine whether Douban provides reliable evidence that airing has begun."""
    info = douban_info or {}
    released = info.get("is_released")
    if released is not None:
        if isinstance(released, str):
            normalized = released.strip().casefold()
            if normalized in {"false", "0", "no", "否", "未上映", "未开播"}:
                return False
            if normalized in {"true", "1", "yes", "是", "已上映", "已开播"}:
                return True
        return bool(released)
    for field_name in (
        "last_episode_number", "current_episode", "current_episode_number",
    ):
        if _positive_int(info.get(field_name)):
            return True
    episodes_info = str(info.get("episodes_info") or "")
    if re.search(r"(?:更新至|已播至|播至)\s*(?:第\s*)?\d+\s*集?", episodes_info):
        return True

    current_date = today or date.today()
    date_values = []
    for field_name in ("release_date", "pubdate"):
        value = info.get(field_name)
        date_values.extend(value if isinstance(value, list) else [value])
    for value in date_values:
        match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", str(value or ""))
        if not match:
            continue
        try:
            release_date = date(*(int(part) for part in match.groups()))
        except ValueError:
            continue
        if release_date <= current_date:
            return True
    return False


def classify_media_region(douban_info: Dict[str, Any]) -> str:
    """Classify a Douban television entry by its first recognized production country."""
    info = douban_info or {}
    countries = info.get("countries") or []
    if isinstance(countries, str):
        countries = re.split(r"[/,，、\s]+", countries)
    normalized_countries = [
        str(country.get("name") if isinstance(country, dict) else country).strip()
        for country in countries
    ]
    if not any(normalized_countries):
        normalized_countries = re.split(
            r"[/,，、\s]+",
            str(info.get("card_subtitle") or ""),
        )
    for country in normalized_countries:
        if country in DOMESTIC_COUNTRIES:
            return "domestic"
        if country in JAPAN_KOREA_COUNTRIES:
            return "japan_korea"
        if country in WESTERN_COUNTRIES:
            return "western"
    return "other"


def person_names(items: Sequence[Any]) -> Tuple[str, ...]:
    """Normalize person dictionaries or strings into unique names."""
    result = []
    seen = set()
    for item in items or []:
        value = item.get("name") if isinstance(item, dict) else item
        value = str(value or "").strip()
        normalized = normalize_title(value)
        if not value or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return tuple(result)


def _normalized_set(values: Iterable[Any]) -> set:
    return {
        normalized for normalized in (normalize_title(str(value or "")) for value in values)
        if normalized
    }


def score_candidate(source: Dict[str, Any], candidate: TmdbCandidate) -> ScoredCandidate:
    """Score work identity and season structure as separate evidence groups."""
    identity_score = 0
    structure_score = 0
    evidence: List[str] = []
    source_title = normalize_title(source.get("title") or "")
    source_original = normalize_title(source.get("original_title") or "")
    source_aliases = _normalized_set(source.get("aliases") or [])
    candidate_titles = _normalized_set(
        (candidate.title, candidate.original_title, *candidate.names)
    )

    if source_title and source_title in candidate_titles:
        identity_score += 35
        evidence.append("主标题一致")
    if source_original and source_original != source_title and source_original in candidate_titles:
        identity_score += 25
        evidence.append("原标题一致")
    if source_aliases.intersection(candidate_titles):
        identity_score += 25
        evidence.append("别名一致")

    source_year = _year_number(source.get("year"))
    candidate_year = _year_number(candidate.year)
    if candidate.mode != "base_and_season":
        if source_year and candidate_year == source_year:
            identity_score += 25
            evidence.append("作品年份一致")
        elif source_year and candidate_year and abs(source_year - candidate_year) > 1:
            identity_score -= 40
            evidence.append("作品年份冲突")

    source_actors = _normalized_set(source.get("actors") or [])
    actor_overlap = source_actors.intersection(_normalized_set(candidate.actors))
    if len(actor_overlap) >= 2:
        identity_score += 15
        evidence.append("主要演员重合")
    elif len(actor_overlap) == 1:
        identity_score += 8
        evidence.append("演员部分重合")
    source_directors = _normalized_set(source.get("directors") or [])
    if source_directors.intersection(_normalized_set(candidate.directors)):
        identity_score += 10
        evidence.append("主创重合")

    if candidate.mode == "base_and_season":
        structure_score += 50 if candidate.strength == "strong" else 5
        evidence.append("明确季度标题" if candidate.strength == "strong" else "弱季度标题候选")
        hypothesis_title = normalize_title(candidate.hypothesis_title)
        if hypothesis_title and hypothesis_title in candidate_titles:
            structure_score += 20
            evidence.append("基础剧存在")
        if candidate.season_episode_count is None:
            structure_score -= 100
            evidence.append("TMDB 不存在目标季度")
        else:
            structure_score += 30
            evidence.append("TMDB 存在目标季度")
        season_year = _year_number(candidate.season_year)
        if source_year and season_year == source_year:
            structure_score += 30
            evidence.append("季度年份一致")
        elif source_year and season_year:
            difference = abs(source_year - season_year)
            if difference <= 1:
                structure_score += 10
                evidence.append("季度年份接近")
            else:
                structure_score -= 30
                evidence.append("季度年份冲突")
        source_total = _positive_int(source.get("total_episode"))
        if source_total and candidate.season_episode_count == source_total:
            structure_score += 25
            evidence.append("季度集数一致")
        elif source_total and candidate.season_episode_count is not None \
                and abs(candidate.season_episode_count - source_total) <= 1:
            structure_score += 10
            evidence.append("季度集数接近")
        if source_title and source_title in candidate_titles and source_title != hypothesis_title:
            structure_score += 20
            evidence.append("TMDB 别名包含完整续季标题")

    total = identity_score + structure_score
    return ScoredCandidate(
        candidate=candidate,
        identity_score=identity_score,
        structure_score=structure_score,
        score=total,
        evidence=tuple(evidence),
    )


def choose_match(
    scored_candidates: Sequence[ScoredCandidate],
) -> MatchDecision:
    """Select a candidate only when its internal evidence score is safely ahead."""
    best_by_key: Dict[Tuple[int, int], ScoredCandidate] = {}
    for scored in scored_candidates:
        key = (scored.candidate.tmdb_id, scored.candidate.season)
        current = best_by_key.get(key)
        if current is None or scored.score > current.score:
            best_by_key[key] = scored
    ordered = sorted(best_by_key.values(), key=lambda item: item.score, reverse=True)
    if not ordered:
        return MatchDecision(False, "no_candidate", "未找到 TMDB 候选")
    winner = ordered[0]
    alternatives = tuple(ordered[1:6])
    if winner.score < MATCH_ACCEPT_SCORE:
        return MatchDecision(
            False,
            "low_score",
            f"最高候选内部匹配分 {winner.score}，低于固定可信线 {MATCH_ACCEPT_SCORE}",
            winner,
            alternatives,
        )
    if alternatives and winner.score - alternatives[0].score < MATCH_MIN_LEAD:
        return MatchDecision(
            False,
            "ambiguous",
            (
                f"前两名内部匹配分仅相差 {winner.score - alternatives[0].score}，"
                f"低于固定领先线 {MATCH_MIN_LEAD}"
            ),
            winner,
            alternatives,
        )
    return MatchDecision(
        True,
        "matched",
        "内部匹配证据达到固定可信线",
        winner,
        alternatives,
    )
