"""Task-scoped qB source renaming, independent from MoviePilot target naming."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


INVALID_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
CHINESE_TEXT = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
NOISE_WORDS = {
    "国语", "国配", "國語", "國配", "粤语", "普通话", "双语", "多语",
    "国粤双语", "中英双语", "中字", "简中", "繁中", "简繁", "简体", "繁体",
    "简英双语", "繁英双语", "简日双语", "繁日双语", "简粤双语", "繁粤双语",
    "简体中文", "繁体中文", "中文字幕", "内封", "字幕", "章节", "特效",
    "特效字幕", "杜比视界", "杜比全景声", "高帧率", "高质量", "纯净版",
    "导演剪辑版", "加长版", "终极版", "未删减版", "重制版", "国版",
    "remux", "web-dl", "web", "蓝光", "原盘", "c版", "s版", "u版",
}
LABEL_ONLY_PATTERN = re.compile(
    r"(?:^|[-_.\[\]()（）\s])(?:国语|国配|中字|双语|简体|繁体|内封|字幕|章节|特效|特效字幕)(?=$|[-_.\[\]()（）\s])",
    re.IGNORECASE,
)
REGEX_RULE_PATTERN = re.compile(r"^/(.*)/([a-zA-Z]*)$")
TECHNICAL_TITLE_SUFFIX = re.compile(
    r"(?:CC\s*标准收藏版|标准收藏版|criterion(?:\s+collection)?|"
    r"4\s*[Kk]|UHD|BluRay|原盘|remux|web(?:-dl)?|蓝光|国语|国配|國語|國配|"
    r"双语|多语|简体|繁体|中字|字幕|特效|内封|音轨|章节|"
    r"导演剪辑版|剧场(?:剪辑)?版|完整修正版|修复版|主演\s*[:：]?|类型\s*[:：]?)",
    re.IGNORECASE,
)
LEADING_RELEASE_BADGE = re.compile(
    r"^\s*【(?=[^】]*(?:原盘|remux))[^】]*】\s*",
    re.IGNORECASE,
)
TECHNICAL_EDITION_SUFFIX = re.compile(
    r"\s+(?:国|美|英|韩|日|德|意大利|意|澳|法|加|西班牙|西|港|台)"
    r"[^/|\[\]]{0,24}?版(?=\s*(?:4\s*[Kk]|UHD|BluRay|蓝光|原盘|REMUX))",
    re.IGNORECASE,
)


class RssRenameError(RuntimeError):
    """A qB rename failure that should not cause the torrent to be re-added."""


@dataclass(frozen=True)
class RenameRule:
    source: str
    replacement: str
    regex: bool = False
    flags: int = 0
    raw: str = ""

    def apply(self, value: str) -> str:
        if self.regex:
            return re.sub(self.source, self.replacement, value, flags=self.flags)
        return value.replace(self.source, self.replacement)


def parse_rename_rules(value: object) -> List[RenameRule]:
    rules: List[RenameRule] = []
    for line_number, raw_line in enumerate(str(value or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=>" not in line:
            raise RssRenameError(f"重命名规则第 {line_number} 行缺少 =>")
        source, replacement = (part.strip() for part in line.split("=>", 1))
        if not source:
            raise RssRenameError(f"重命名规则第 {line_number} 行的匹配内容为空")
        match = REGEX_RULE_PATTERN.fullmatch(source)
        if not match:
            rules.append(RenameRule(
                source=source,
                replacement=replacement,
                raw=line,
            ))
            continue
        pattern, flag_text = match.groups()
        unsupported = set(flag_text.casefold()) - {"i", "m", "s", "g"}
        if unsupported:
            flags = "".join(sorted(unsupported))
            raise RssRenameError(f"重命名规则第 {line_number} 行包含不支持的标志：{flags}")
        re_flags = 0
        if "i" in flag_text.casefold():
            re_flags |= re.IGNORECASE
        if "m" in flag_text.casefold():
            re_flags |= re.MULTILINE
        if "s" in flag_text.casefold():
            re_flags |= re.DOTALL
        try:
            re.compile(pattern, re_flags)
        except re.error as error:
            raise RssRenameError(
                f"重命名规则第 {line_number} 行正则无效：{error}"
            ) from error
        rules.append(RenameRule(
            source=pattern,
            replacement=replacement,
            regex=True,
            flags=re_flags,
            raw=line,
        ))
    return rules


def extract_chinese_title(rss_title: object) -> str:
    title = re.sub(r"<!\[CDATA\[|\]\]>", "", str(rss_title or ""), flags=re.IGNORECASE)
    candidates: List[str] = []
    for bracket in _top_level_brackets(title):
        bracket = LEADING_RELEASE_BADGE.sub("", bracket)
        bracket = re.split(r"\s*\|\s*", bracket, maxsplit=1)[0]
        for raw_candidate in re.split(r"\s*/\s*", bracket):
            raw_candidate = _trim_technical_title_suffix(raw_candidate)
            candidate = re.sub(
                r"\([^)]*\)|（[^）]*）", "", raw_candidate
            ).strip(" ._-[]")
            if not candidate or not CHINESE_TEXT.search(candidate):
                continue
            if not has_meaningful_chinese(candidate):
                continue
            candidates.append(candidate)
    if not candidates:
        return ""
    preferred = [item for item in candidates if 2 <= len(item) <= 20]
    return (preferred or candidates)[0]


def _trim_technical_title_suffix(value: str) -> str:
    text = str(value or "").strip()
    cutoffs = []
    edition = TECHNICAL_EDITION_SUFFIX.search(text)
    if edition:
        cutoffs.append(edition.start())
    for match in TECHNICAL_TITLE_SUFFIX.finditer(text):
        if match.start() == 0 or text[match.start() - 1].isspace():
            cutoffs.append(match.start())
    if cutoffs:
        return text[:min(cutoffs)].rstrip(" ._-：:")
    return text


def has_meaningful_chinese(value: object) -> bool:
    cleaned = LABEL_ONLY_PATTERN.sub(" ", str(value or ""))
    for noise in sorted(NOISE_WORDS, key=len, reverse=True):
        cleaned = re.sub(re.escape(noise), " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"第\s*\d+\s*[季集部期]", " ", cleaned)
    return bool(CHINESE_TEXT.search(cleaned))


def transform_name(
    name: str,
    *,
    is_file: bool,
    rules: Sequence[RenameRule] = (),
    chinese_title: str = "",
    add_cn: bool = False,
    add_fx: bool = False,
) -> str:
    transformed = str(name or "")
    for rule in rules:
        transformed = rule.apply(transformed)
    if chinese_title and not has_meaningful_chinese(transformed):
        stem, suffix = _split_extension(transformed, is_file)
        transformed = f"[{chinese_title}].{stem}{suffix}"
    transformed = normalize_markers(
        transformed,
        is_file=is_file,
        add_cn=add_cn,
        add_fx=add_fx,
        anchors=[rule.replacement for rule in rules if rule.replacement],
    )
    _validate_name(transformed)
    return transformed


def normalize_markers(
    name: str,
    *,
    is_file: bool,
    add_cn: bool,
    add_fx: bool,
    anchors: Sequence[str] = (),
) -> str:
    stem, suffix = _split_extension(name, is_file)
    separator = r"[-._\s]"
    detected_cn = bool(re.search(
        rf"(?:^|{separator})(?:国配)(?={separator}|$)", stem
    ))
    detected_fx = bool(re.search(
        rf"(?:^|{separator})(?:特效)(?={separator}|$)", stem
    ))
    if not (add_cn or add_fx or detected_cn or detected_fx):
        return name
    stem = re.sub(
        rf"(?:^|{separator})(?:国配|特效)(?={separator}|$)", "", stem
    )
    stem = re.sub(r"-{2,}", "-", stem).strip("-")
    markers = []
    if add_cn or detected_cn:
        markers.append("国配")
    if add_fx or detected_fx:
        markers.append("特效")
    marker_text = "-".join(markers)
    for anchor_text in reversed(list(anchors)):
        anchor_text = str(anchor_text or "").strip()
        if not anchor_text or re.search(r"\\\d|\\g<|\$\d", anchor_text):
            continue
        positions = list(re.finditer(
            re.escape(anchor_text), stem, flags=re.IGNORECASE
        ))
        if not positions:
            continue
        matched = positions[-1]
        position = matched.start()
        prefix_end = position
        if position > 0 and re.fullmatch(separator, stem[position - 1]):
            prefix_end -= 1
        prefix = stem[:prefix_end].rstrip("-._ ")
        tail = stem[position:].lstrip("-._ ")
        if prefix:
            return f"{prefix}-{marker_text}-{tail}{suffix}"
        return f"{marker_text}-{tail}{suffix}"
    anchor = list(re.finditer(
        rf"(?i)(?:^|{separator})REMUX(?={separator}|$)", stem
    ))
    if anchor:
        matched = anchor[-1]
        position = matched.start()
        remux_start = matched.end() - len("REMUX")
        prefix = stem[:position].rstrip("-._ ")
        tail = stem[remux_start:].lstrip("-._ ")
        if prefix:
            return f"{prefix}-{marker_text}-{tail}{suffix}"
        return f"{marker_text}-{tail}{suffix}"
    return f"{stem}-{marker_text}{suffix}"


class QbSourceRenameService:
    """Execute a rename plan against qB and re-read the authoritative paths."""

    def __init__(self, gateway: Any, sleeper: Any = None):
        self.gateway = gateway
        self.sleeper = sleeper or __import__("time").sleep

    def apply(
        self,
        server: Any,
        info_hash: str,
        *,
        rss_title: str,
        rename_enabled: bool,
        rename_rules: object,
        add_chinese_title: bool,
        add_cn: bool = False,
        add_fx: bool = False,
    ) -> Dict[str, Any]:
        enabled = bool(rename_enabled or add_chinese_title or add_cn or add_fx)
        chinese_title = extract_chinese_title(rss_title) if add_chinese_title else ""
        rules = parse_rename_rules(rename_rules) if rename_enabled else []
        if not enabled:
            return self._result("skipped", chinese_title, rules, [], [], [])
        try:
            files = self._wait_for_files(server, info_hash)
        except Exception as error:
            return self._result(
                "failed", chinese_title, rules, [], [], [],
                error=f"读取 qB 文件列表失败：{error}",
            )
        if not files:
            return self._result(
                "failed", chinese_title, rules, [], [], [],
                error="qB 文件列表为空，未执行改名",
            )
        file_ops, directory_ops = build_rename_plan(
            files,
            rules=rules,
            chinese_title=chinese_title,
            add_cn=add_cn,
            add_fx=add_fx,
        )
        if not file_ops and not directory_ops:
            final_files, read_error = self._safe_list(server, info_hash)
            return self._result(
                "failed" if read_error else "unchanged",
                chinese_title,
                rules,
                [],
                [],
                final_files,
                error=read_error,
            )

        completed: List[Tuple[str, str, str]] = []
        try:
            for old_path, new_path in file_ops:
                self._rename_and_confirm(
                    server,
                    info_hash,
                    kind="file",
                    old_path=old_path,
                    new_path=new_path,
                )
                completed.append(("file", old_path, new_path))
            for old_path, new_path in directory_ops:
                self._rename_and_confirm(
                    server,
                    info_hash,
                    kind="folder",
                    old_path=old_path,
                    new_path=new_path,
                )
                completed.append(("folder", old_path, new_path))
            expected_paths = _expected_paths_after_renames(
                files,
                file_ops=file_ops,
                directory_ops=directory_ops,
            )
            final_files = self._wait_for_expected_paths(
                server,
                info_hash,
                expected_paths,
            )
        except Exception as error:
            rollback_errors = self._rollback(server, info_hash, completed)
            final_files, read_error = self._safe_list(server, info_hash)
            return self._result(
                "failed", chinese_title, rules, file_ops, directory_ops,
                final_files,
                error="；".join(item for item in (str(error), read_error) if item),
                rolled_back=not rollback_errors,
                rollback_errors=rollback_errors,
            )

        return self._result(
            "renamed",
            chinese_title,
            rules,
            file_ops,
            directory_ops,
            final_files,
        )

    def _rename_and_confirm(
        self,
        server: Any,
        info_hash: str,
        *,
        kind: str,
        old_path: str,
        new_path: str,
    ) -> None:
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                if kind == "file":
                    self.gateway.rename_torrent_file(
                        server, info_hash, old_path, new_path
                    )
                else:
                    self.gateway.rename_torrent_folder(
                        server, info_hash, old_path, new_path
                    )
            except Exception as error:
                last_error = error
            if self._wait_for_path_change(
                server,
                info_hash,
                kind=kind,
                old_path=old_path,
                new_path=new_path,
            ):
                return
            if attempt < 2:
                self.sleeper(0.2)
        label = "文件" if kind == "file" else "目录"
        detail = f"：{last_error}" if last_error else ""
        raise RssRenameError(
            f"qB {label}改名未落地：{old_path} -> {new_path}{detail}"
        )

    def _wait_for_path_change(
        self,
        server: Any,
        info_hash: str,
        *,
        kind: str,
        old_path: str,
        new_path: str,
    ) -> bool:
        old_identity = old_path.casefold()
        new_identity = new_path.casefold()
        for poll in range(5):
            try:
                paths = _file_path_identities(
                    self.gateway.list_torrent_files(server, info_hash)
                )
            except Exception:
                paths = set()
            if kind == "file":
                changed = new_identity in paths and old_identity not in paths
            else:
                old_prefix = f"{old_identity}/"
                new_prefix = f"{new_identity}/"
                changed = (
                    any(path.startswith(new_prefix) for path in paths)
                    and not any(path.startswith(old_prefix) for path in paths)
                )
            if changed:
                return True
            if poll < 4:
                self.sleeper(0.2)
        return False

    def _wait_for_expected_paths(
        self,
        server: Any,
        info_hash: str,
        expected_paths: Sequence[str],
    ) -> List[Any]:
        expected = {path.casefold() for path in expected_paths}
        final_files: List[Any] = []
        for poll in range(6):
            final_files = list(
                self.gateway.list_torrent_files(server, info_hash) or []
            )
            if _file_path_identities(final_files) == expected:
                return final_files
            if poll < 5:
                self.sleeper(0.2)
        actual = sorted(_file_path_identities(final_files))
        missing = sorted(expected - set(actual))
        raise RssRenameError(
            "qB 改名结果与计划不一致"
            + (f"，缺少：{missing[0]}" if missing else "")
        )

    def _wait_for_files(self, server: Any, info_hash: str) -> List[Any]:
        files: List[Any] = []
        for attempt in range(4):
            files = list(self.gateway.list_torrent_files(server, info_hash) or [])
            if files:
                return files
            if attempt < 3:
                self.sleeper(1)
        return files

    def _safe_list(self, server: Any, info_hash: str) -> Tuple[List[Any], str]:
        try:
            return list(self.gateway.list_torrent_files(server, info_hash) or []), ""
        except Exception as error:
            return [], f"重新读取 qB 文件列表失败：{error}"

    def _rollback(
        self,
        server: Any,
        info_hash: str,
        completed: Sequence[Tuple[str, str, str]],
    ) -> List[str]:
        errors: List[str] = []
        for kind, old_path, new_path in reversed(completed):
            try:
                if kind == "file":
                    self.gateway.rename_torrent_file(
                        server, info_hash, new_path, old_path
                    )
                else:
                    self.gateway.rename_torrent_folder(
                        server, info_hash, new_path, old_path
                    )
            except Exception as error:
                errors.append(f"{new_path} -> {old_path}: {error}")
        return errors

    @staticmethod
    def _result(
        status: str,
        chinese_title: str,
        rules: Sequence[RenameRule],
        file_ops: Sequence[Tuple[str, str]],
        directory_ops: Sequence[Tuple[str, str]],
        final_files: Iterable[Any],
        *,
        error: str = "",
        rolled_back: bool = False,
        rollback_errors: Sequence[str] = (),
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "chinese_title": chinese_title,
            "rules": [rule.raw for rule in rules],
            "file_renames": [
                {"old_path": old_path, "new_path": new_path}
                for old_path, new_path in file_ops
            ],
            "directory_renames": [
                {"old_path": old_path, "new_path": new_path}
                for old_path, new_path in directory_ops
            ],
            "final_files": [_file_payload(item) for item in final_files or []],
            "error": str(error or "")[:500],
            "rolled_back": bool(rolled_back),
            "rollback_errors": list(rollback_errors),
        }


def build_rename_plan(
    files: Iterable[Any],
    *,
    rules: Sequence[RenameRule],
    chinese_title: str,
    add_cn: bool,
    add_fx: bool,
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    file_items = list(files or [])
    file_ops: List[Tuple[str, str]] = []
    directories = set()
    for item in file_items:
        payload = _file_payload(item)
        old_path = PurePosixPath(payload["name"])
        if not payload["name"] or old_path.is_absolute() or ".." in old_path.parts:
            raise RssRenameError(f"qB 返回了无效文件路径：{payload['name']}")
        for parent in old_path.parents:
            if parent.as_posix() != ".":
                directories.add(parent.as_posix())
        new_name = transform_name(
            old_path.name,
            is_file=True,
            rules=rules,
            chinese_title=chinese_title,
            add_cn=add_cn,
            add_fx=add_fx,
        )
        new_path = old_path.with_name(new_name).as_posix()
        if new_path != old_path.as_posix():
            file_ops.append((old_path.as_posix(), new_path))

    directory_ops: List[Tuple[str, str]] = []
    for old_value in sorted(
        directories,
        key=lambda value: (-len(PurePosixPath(value).parts), value.casefold()),
    ):
        old_path = PurePosixPath(old_value)
        new_name = transform_name(
            old_path.name,
            is_file=False,
            rules=rules,
            chinese_title=chinese_title,
            add_cn=add_cn,
            add_fx=add_fx,
        )
        new_path = old_path.with_name(new_name).as_posix()
        if new_path != old_path.as_posix():
            directory_ops.append((old_path.as_posix(), new_path))
    _preflight_conflicts(
        file_ops,
        "文件",
        [str(_file_payload(item).get("name") or "") for item in file_items],
    )
    _preflight_conflicts(directory_ops, "目录", list(directories))
    return file_ops, directory_ops


def _file_path_identities(files: Iterable[Any]) -> set[str]:
    return {
        str(_file_payload(item).get("name") or "").casefold()
        for item in files or []
        if str(_file_payload(item).get("name") or "")
    }


def _expected_paths_after_renames(
    files: Iterable[Any],
    *,
    file_ops: Sequence[Tuple[str, str]],
    directory_ops: Sequence[Tuple[str, str]],
) -> List[str]:
    file_map = {old.casefold(): new for old, new in file_ops}
    paths = []
    for item in files or []:
        path = str(_file_payload(item).get("name") or "")
        path = file_map.get(path.casefold(), path)
        for old_dir, new_dir in directory_ops:
            old_prefix = f"{old_dir}/"
            if path.casefold().startswith(old_prefix.casefold()):
                path = f"{new_dir}/{path[len(old_prefix):]}"
        paths.append(path)
    return paths


def _file_payload(item: Any) -> Dict[str, Any]:
    if hasattr(item, "model_dump"):
        raw = item.model_dump(mode="json")
    elif isinstance(item, dict):
        raw = dict(item)
    else:
        try:
            raw = dict(item)
        except (TypeError, ValueError):
            raw = dict(vars(item))
    return {
        "index": raw.get("index", raw.get("id")),
        "name": str(raw.get("name") or raw.get("path") or "").replace("\\", "/"),
        "size": int(raw.get("size") or 0),
        "progress": raw.get("progress"),
        "priority": raw.get("priority"),
    }


def _top_level_brackets(value: str) -> List[str]:
    result: List[str] = []
    start = -1
    depth = 0
    for index, char in enumerate(value):
        if char == "[":
            if depth == 0:
                start = index + 1
            depth += 1
        elif char == "]" and depth:
            depth -= 1
            if depth == 0 and start >= 0:
                result.append(value[start:index].strip())
                start = -1
    return result


def _split_extension(name: str, is_file: bool) -> Tuple[str, str]:
    if not is_file:
        return name, ""
    suffix = PurePosixPath(name).suffix
    return (name[:-len(suffix)], suffix) if suffix else (name, "")


def _validate_name(name: str) -> None:
    if not name or name in {".", ".."}:
        raise RssRenameError("重命名结果为空或无效")
    if INVALID_NAME_CHARS.search(name):
        raise RssRenameError(f"重命名结果包含非法字符：{name}")
    if len(name.encode("utf-8")) > 255:
        raise RssRenameError(f"重命名结果超过 255 字节：{name}")


def _preflight_conflicts(
    operations: Sequence[Tuple[str, str]],
    label: str,
    existing_paths: Sequence[str],
) -> None:
    targets: Dict[str, str] = {}
    existing = {str(path or "").casefold(): str(path or "") for path in existing_paths}
    for old_path, new_path in operations:
        identity = new_path.casefold()
        previous = targets.get(identity)
        if previous and previous.casefold() != old_path.casefold():
            raise RssRenameError(
                f"{label}重命名目标冲突：{previous} 与 {old_path} -> {new_path}"
            )
        occupied = existing.get(identity)
        if occupied and occupied.casefold() != old_path.casefold():
            raise RssRenameError(
                f"{label}重命名目标已存在：{old_path} -> {new_path}"
            )
        targets[identity] = old_path
