from __future__ import annotations

import codecs
import json
import os
import re
from collections import Counter, OrderedDict, deque
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Deque,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
)

from ..models import Exchange, SessionDetail, SessionSummary, ToolCall, UserPrompt
from ..util import (
    UTC,
    block_text,
    normalize_text,
    one_line,
    parse_timestamp,
)
from .base import HarnessAdapter

HEAD_BYTES = 1_000_000
HEAD_RECORDS = 400
TAIL_BYTES = 1_000_000
TAIL_BYTES_EXTENDED = 4_000_000
TAIL_BYTES_MAX = 16_000_000
ARRAY_SCAN_BYTES = 8_000_000
CHUNK_BYTES = 262_144
MAX_PROMPT_CHARS = 4_000
MAX_SUMMARY_CHARS = 20_000
MAX_ASSISTANT_CHARS = 5_000
MAX_TITLE_CHARS = 200
MAX_EXCHANGES = 50
MAX_ASSISTANT_PER_EXCHANGE = 3
MAX_TOOLS_PER_EXCHANGE = 8
MAX_RECENT_TOOLS = 20
MAX_EDITED_FILES = 30

MESSAGES_SUFFIX = ".messages.json"
COMPACTION_SUFFIX = ".compaction.json"

_ARRAY_START_RE = re.compile(rb'(?m)^[ \t]*"messages"[ \t]*:[ \t]*\[')
_MESSAGE_START_RE = re.compile(rb"(?m)^ {2,8}(?=\{[ \t]*$)")
_HEAD_UPDATED_RE = re.compile(r'"updated_at"\s*:\s*"([^"]+)"')
_USER_INPUT_RE = re.compile(r"<user_input(?:\s[^>]*)?>(.*?)</user_input>", re.S)
_USER_INPUT_OPEN_RE = re.compile(r"<user_input(?:\s[^>]*)?>")

GENERIC_PROMPTS = {
    "continue",
    "go on",
    "keep going",
    "next",
    "ok",
    "yes",
    "hi",
    "hello",
    "继续",
    "接着",
    "继续吧",
    "好的",
    "好",
    "下一步",
    "你好",
    "?",
    "？",
}

INJECTED_PREFIXES = (
    "[SYSTEM]",
    "System-delivered ",
    "Your previous response was cut off",
)

EDIT_TOOLS = {"editor"}

_TOOL_DETAIL_KEYS = {
    "run_commands": ("commands",),
    "editor": ("path",),
    "read_files": ("files",),
    "search_codebase": ("queries",),
    "fetch_web_content": ("requests",),
    "skills": ("skill", "args"),
    "ask_question": ("question",),
    "team_task": ("title", "description"),
    "team_spawn_teammate": ("agentId", "rolePrompt"),
    "team_run_task": ("agentId", "task"),
    "submit_and_exit": ("summary",),
}

_NESTED_DETAIL_KEYS = ("path", "url", "query", "prompt", "command")


def _ref_id(session_id: str) -> str:
    tail = session_id.rsplit("_", 1)[-1]
    if tail != session_id and len(tail) >= 4:
        return tail
    return session_id[-8:]


def _id_keys(session_id: str) -> Tuple[str, ...]:
    keys = [session_id, _ref_id(session_id)]
    if session_id.startswith("session_"):
        keys.append(session_id[len("session_") :])
    return tuple(keys)


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _array_offset(path: Path) -> Optional[int]:
    try:
        with open(path, "rb") as handle:
            data = handle.read(ARRAY_SCAN_BYTES)
    except OSError:
        return None
    match = _ARRAY_START_RE.search(data)
    return match.end() if match else None


def _read_chunk(handle: Any, remaining: Optional[int]) -> bytes:
    size = CHUNK_BYTES if remaining is None else max(
        0, min(CHUNK_BYTES, remaining)
    )
    if size <= 0:
        return b""
    return handle.read(size)


def _iter_messages(
    path: Path,
    offset: int,
    max_bytes: Optional[int] = None,
    max_records: Optional[int] = None,
) -> Iterator[Dict[str, Any]]:
    decoder = json.JSONDecoder()
    incremental = codecs.getincrementaldecoder("utf-8")("replace")
    try:
        handle = open(path, "rb")
    except OSError:
        return
    with handle:
        try:
            handle.seek(offset)
        except OSError:
            return
        remaining = max_bytes
        eof = False
        buffer = ""
        count = 0
        while True:
            while True:
                buffer = buffer.lstrip()
                if buffer.startswith(","):
                    buffer = buffer[1:].lstrip()
                if buffer.startswith("]"):
                    return
                if buffer:
                    break
                if eof:
                    return
                chunk = _read_chunk(handle, remaining)
                if remaining is not None:
                    remaining -= len(chunk)
                if not chunk:
                    eof = True
                buffer += incremental.decode(chunk, final=eof)
            try:
                obj, end = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                if eof:
                    return
                chunk = _read_chunk(handle, remaining)
                if remaining is not None:
                    remaining -= len(chunk)
                if not chunk:
                    eof = True
                buffer += incremental.decode(chunk, final=eof)
                continue
            buffer = buffer[end:]
            if isinstance(obj, dict):
                yield obj
                count += 1
                if max_records is not None and count >= max_records:
                    return


def _looks_like_message(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("role") in ("user", "assistant")
        and isinstance(value.get("content"), list)
    )


def _tail_messages(
    path: Path, offset: int, window: int
) -> List[Dict[str, Any]]:
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size <= 0:
        return []
    start = max(0, size - window)
    try:
        with open(path, "rb") as handle:
            handle.seek(start)
            data = handle.read()
    except OSError:
        return []
    base = start
    if start > 0:
        first_newline = data.find(b"\n")
        if first_newline < 0:
            return []
        base = start + first_newline + 1
        data = data[first_newline + 1 :]
    for match in list(_MESSAGE_START_RE.finditer(data))[:32]:
        records = list(_iter_messages(path, base + match.end(), window))
        if records and _looks_like_message(records[0]):
            return records
    return []


def _head_updated_at(path: Path) -> Optional[datetime]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            head = handle.read(65_536)
    except OSError:
        return None
    match = _HEAD_UPDATED_RE.search(head)
    return parse_timestamp(match.group(1)) if match else None


def _message_time(message: Dict[str, Any]) -> Optional[datetime]:
    return parse_timestamp(message.get("ts"))


def _prompt_text(message: Dict[str, Any]) -> str:
    if message.get("role") != "user":
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "tool_result":
            return ""
        if block_type != "text":
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text)
    if not parts:
        return ""
    return _clean_prompt("\n".join(parts))


def _clean_prompt(value: str) -> str:
    if not value:
        return ""
    matches = _USER_INPUT_RE.findall(value)
    if matches:
        text = "\n".join(part for part in matches if part.strip())
    else:
        if _USER_INPUT_OPEN_RE.search(value) or "</user_input>" in value:
            text = _USER_INPUT_OPEN_RE.sub("", value).replace(
                "</user_input>", ""
            )
        else:
            text = value
    text = text.strip()
    if not text or text.startswith(INJECTED_PREFIXES):
        return ""
    if text.startswith("Context summary:"):
        return ""
    return text


def _assistant_text(message: Dict[str, Any]) -> str:
    if message.get("role") != "assistant":
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text)
    return "\n".join(parts)


def _tool_uses(message: Dict[str, Any]) -> Iterator[Tuple[str, Any]]:
    if message.get("role") != "assistant":
        return
    content = message.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = block.get("name")
        if isinstance(name, str) and name.strip():
            yield name.strip(), block.get("input")


def _detail_from_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            for key in _NESTED_DETAIL_KEYS:
                nested = first.get(key)
                if isinstance(nested, str) and nested.strip():
                    return nested
    return ""


def _tool_detail(name: str, arguments: Any) -> str:
    if not isinstance(arguments, dict):
        return ""
    for key in _TOOL_DETAIL_KEYS.get(name, ()):
        value = _detail_from_value(arguments.get(key))
        if value.strip():
            return one_line(value, 160)
    for value in arguments.values():
        text = _detail_from_value(value)
        if text.strip():
            return one_line(text, 160)
    return ""


def _remove_found_tokens(
    path: Path,
    remaining: Set[str],
    chunk_size: int = 4 * 1024 * 1024,
) -> None:
    overlap = b""
    try:
        with open(path, "rb") as handle:
            while remaining:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                data = overlap + chunk
                text = normalize_text(data.decode("utf-8", "ignore"))
                for token in tuple(remaining):
                    if token in text:
                        remaining.discard(token)
                overlap = data[-512:]
    except OSError:
        return


def _edited_path(arguments: Any, cwd: str) -> str:
    if not isinstance(arguments, dict):
        return ""
    value = arguments.get("path")
    if not isinstance(value, str) or not value.strip():
        return ""
    path = os.path.expanduser(value.strip())
    if cwd and not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.normpath(path)


def _is_generic(value: str) -> bool:
    compact = re.sub(r"\s+", " ", value).strip().casefold()
    if not compact or len(compact) <= 1:
        return True
    if re.fullmatch(r"[\d\W_]+", compact):
        return True
    return compact in GENERIC_PROMPTS


def _choose_title(first_prompt: str, last_prompt: str) -> str:
    for candidate in (last_prompt, first_prompt):
        if candidate and not _is_generic(candidate):
            return one_line(candidate, 100)
    return one_line(last_prompt or first_prompt, 100)


class ClineAdapter(HarnessAdapter):
    """Cline CLI and desktop app share one session store under ~/.cline."""

    name = "cline"
    aliases = ("cline",)
    variants = "desktop, cli"
    store_hint = "~/.cline/data/sessions"
    home_env = "FMS_CLINE_HOME"

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".cline"

    def session_roots(self) -> List[Path]:
        return [self.home() / "data" / "sessions"]

    def iter_session_paths(self) -> Iterator[Path]:
        root = self.home() / "data" / "sessions"
        if not root.is_dir():
            return
        pending: List[Tuple[float, Path]] = []
        try:
            entries = list(root.iterdir())
        except OSError:
            return
        for entry in entries:
            if not entry.is_dir():
                continue
            messages = entry / (entry.name + MESSAGES_SUFFIX)
            if not messages.is_file():
                continue
            try:
                mtime = messages.stat().st_mtime
            except OSError:
                mtime = 0.0
            pending.append((mtime, messages))
        pending.sort(key=lambda item: item[0], reverse=True)
        for _, path in pending:
            yield path

    def session_id_for(self, path: Path) -> str:
        name = path.name
        for suffix in (MESSAGES_SUFFIX, COMPACTION_SUFFIX):
            if name.endswith(suffix):
                return name[: -len(suffix)]
        if name.endswith(".json"):
            return name[: -len(".json")]
        return name

    def _messages_path(self, path: Path) -> Path:
        path = Path(path).expanduser()
        if path.is_dir():
            return path / (path.name + MESSAGES_SUFFIX)
        if path.name.endswith(MESSAGES_SUFFIX):
            return path
        session_id = self.session_id_for(path)
        return path.parent / (session_id + MESSAGES_SUFFIX)

    def _validate(self, messages: Path) -> int:
        if not messages.is_file():
            raise ValueError("cannot read Cline transcript: %s" % messages)
        session_id = messages.name[: -len(MESSAGES_SUFFIX)]
        if messages.parent.name != session_id:
            raise ValueError(
                "Cline subagent transcript is not a resumable session: %s"
                % messages
            )
        offset = _array_offset(messages)
        if offset is None:
            raise ValueError("cannot read Cline transcript: %s" % messages)
        return offset

    def summarize(self, path: Path) -> SessionSummary:
        messages = self._messages_path(path)
        offset = self._validate(messages)

        meta_path = messages.parent / (
            messages.name[: -len(MESSAGES_SUFFIX)] + ".json"
        )
        meta = _load_json(meta_path)
        metadata = meta.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        origin = metadata.get("sessionHistoryOrigin")
        if not isinstance(origin, dict):
            origin = {}
        git = metadata.get("git")
        if not isinstance(git, dict):
            git = {}

        first_prompt = ""
        first_time: Optional[datetime] = None
        for message in _iter_messages(
            messages, offset, HEAD_BYTES, HEAD_RECORDS
        ):
            if first_time is None:
                first_time = _message_time(message)
            text = _prompt_text(message)
            if text:
                first_prompt = block_text(text, MAX_PROMPT_CHARS)
                break

        tail = _tail_messages(messages, offset, TAIL_BYTES)
        last_prompt = ""
        last_time: Optional[datetime] = None
        for message in reversed(tail):
            if last_time is None:
                last_time = _message_time(message)
            text = _prompt_text(message)
            if text:
                last_prompt = block_text(text, MAX_PROMPT_CHARS)
                break
        for window in (TAIL_BYTES_EXTENDED, TAIL_BYTES_MAX):
            if last_prompt:
                break
            tail = _tail_messages(messages, offset, window)
            for message in reversed(tail):
                text = _prompt_text(message)
                if text:
                    last_prompt = block_text(text, MAX_PROMPT_CHARS)
                    break

        if not first_prompt:
            first_prompt = block_text(
                _clean_prompt(str(meta.get("prompt") or "")),
                MAX_PROMPT_CHARS,
            )
        if not first_prompt:
            first_prompt = last_prompt
        if not last_prompt:
            last_prompt = first_prompt

        title = one_line(str(metadata.get("title") or ""), MAX_TITLE_CHARS)
        if not title or _is_generic(title):
            chosen = _choose_title(first_prompt, last_prompt)
            if chosen:
                title = chosen
        if not title:
            title = self.session_id_for(messages)

        started = parse_timestamp(meta.get("started_at")) or first_time
        updated = (
            parse_timestamp(meta.get("ended_at"))
            or _head_updated_at(messages)
            or last_time
        )
        if updated is None:
            try:
                updated = datetime.fromtimestamp(
                    messages.stat().st_mtime, tz=UTC
                )
            except OSError:
                updated = datetime.now(tz=UTC)
        if started is None:
            started = updated

        try:
            size = messages.stat().st_size
        except OSError:
            size = 0

        session_id = self.session_id_for(messages)
        return SessionSummary(
            harness=self.name,
            session_id=session_id,
            path=messages,
            cwd=str(meta.get("cwd") or ""),
            updated=updated,
            title=title,
            first_prompt=first_prompt,
            last_prompt=last_prompt,
            started=started,
            branch=str(git.get("branch") or ""),
            model=str(meta.get("model") or ""),
            entrypoint=str(meta.get("source") or ""),
            version=str(origin.get("version") or ""),
            size=size,
            variants=self.variants,
            archived=False,
            ref_id=_ref_id(session_id),
        )

    def find(self, needle: str) -> List[SessionSummary]:
        wanted = needle.casefold()
        matches: List[SessionSummary] = []
        for path in self.iter_session_paths():
            keys = _id_keys(self.session_id_for(path))
            if not any(key.casefold().startswith(wanted) for key in keys):
                continue
            try:
                matches.append(self.summarize(path))
            except (OSError, ValueError):
                continue
        return matches

    def _compaction_path(self, messages: Path) -> Path:
        session_id = messages.name[: -len(MESSAGES_SUFFIX)]
        return messages.parent / (session_id + COMPACTION_SUFFIX)

    def _compaction_summary(self, messages: Path) -> str:
        compaction = self._compaction_path(messages)
        if not compaction.is_file():
            return ""
        offset = _array_offset(compaction)
        if offset is None:
            return ""
        for message in _iter_messages(
            compaction, offset, HEAD_BYTES, HEAD_RECORDS
        ):
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "text":
                    continue
                text = block.get("text")
                if isinstance(text, str) and text.strip().startswith(
                    "Context summary:"
                ):
                    return block_text(text, MAX_SUMMARY_CHARS)
        return ""

    def contains(
        self, summary: SessionSummary, tokens: Sequence[str]
    ) -> bool:
        remaining = {normalize_text(token) for token in tokens if token}
        remaining.discard("")
        if not remaining:
            return True
        files = [summary.path]
        compaction = self._compaction_path(summary.path)
        if compaction.is_file():
            files.append(compaction)
        for path in files:
            _remove_found_tokens(path, remaining)
            if not remaining:
                return True
        return not remaining

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        messages = self._messages_path(summary.path)
        offset = self._validate(messages)
        for message in _iter_messages(messages, offset):
            text = _prompt_text(message)
            if not text:
                continue
            yield UserPrompt(text=text, timestamp=_message_time(message))

    def load(self, summary: SessionSummary) -> SessionDetail:
        messages = self._messages_path(summary.path)
        offset = self._validate(messages)

        exchanges: Deque[Exchange] = deque(maxlen=MAX_EXCHANGES)
        current: Optional[Exchange] = None
        tool_counts: Counter = Counter()
        recent_tools: Deque[ToolCall] = deque(maxlen=MAX_RECENT_TOOLS)
        edited: "OrderedDict[str, int]" = OrderedDict()
        cwd = summary.cwd
        first_prompt = summary.first_prompt
        last_prompt = summary.last_prompt
        turn_count = 0

        def append_current() -> None:
            nonlocal current
            if current is None:
                return
            if current.user_text or current.assistant_texts or current.tools:
                exchanges.append(current)
            current = None

        for message in _iter_messages(messages, offset):
            timestamp = _message_time(message)
            role = message.get("role")

            if role == "user":
                text = _prompt_text(message)
                if not text:
                    continue
                append_current()
                cleaned = block_text(text, MAX_PROMPT_CHARS)
                current = Exchange(user_text=cleaned, timestamp=timestamp)
                turn_count += 1
                last_prompt = cleaned
                if not first_prompt:
                    first_prompt = cleaned
                continue

            if role != "assistant":
                continue

            text = _assistant_text(message)
            if text:
                if current is None:
                    current = Exchange(timestamp=timestamp)
                current.assistant_texts.append(
                    block_text(text, MAX_ASSISTANT_CHARS)
                )
                if len(current.assistant_texts) > MAX_ASSISTANT_PER_EXCHANGE:
                    current.assistant_texts = current.assistant_texts[
                        -MAX_ASSISTANT_PER_EXCHANGE:
                    ]

            for name, arguments in _tool_uses(message):
                call = ToolCall(
                    name=name,
                    detail=_tool_detail(name, arguments),
                    timestamp=timestamp,
                )
                if current is None:
                    current = Exchange(timestamp=timestamp)
                current.tools.append(call)
                if len(current.tools) > MAX_TOOLS_PER_EXCHANGE:
                    current.tools = current.tools[-MAX_TOOLS_PER_EXCHANGE:]
                tool_counts[name] += 1
                recent_tools.append(call)
                if name in EDIT_TOOLS:
                    edited_path = _edited_path(arguments, cwd)
                    if edited_path:
                        edited[edited_path] = edited.get(edited_path, 0) + 1

        append_current()

        if not first_prompt:
            first_prompt = last_prompt
        summary.first_prompt = first_prompt
        summary.last_prompt = last_prompt
        if not summary.title:
            summary.title = _choose_title(first_prompt, last_prompt)

        edited_files = [
            {"path": path, "count": count}
            for path, count in list(edited.items())[-MAX_EDITED_FILES:]
        ]

        return SessionDetail(
            summary=summary,
            compact_summary=self._compaction_summary(messages),
            todos=[],
            exchanges=list(exchanges),
            edited_files=edited_files,
            tool_counts=dict(tool_counts.most_common()),
            recent_tools=list(recent_tools),
            turn_count=turn_count,
        )
