"""Adapter for DeepSeek Harness (``dsh``) sessions.

DeepSeek Harness keeps one zstd-compressed JSONL event log per session under
``~/.dsh/sessions/<encoded-cwd>/<session-dir>/session[.vN].jsonl.zstd``.
A session directory can hold several schema versions at once; the highest
``vN`` is the authoritative full snapshot. Human prompts are ``user/message``
records whose ``source.kind`` is ``user``; injected context uses the same
record type with other source kinds. Archive state lives outside the
transcript in ``storages/workspace.json``.

Everything here is read-only. Compressed logs are streamed through
``compression.zstd`` on Python 3.14+ or the ``zstd`` CLI; without either, the
store cannot be decoded and sessions are skipped.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections import Counter, OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Deque,
    Dict,
    Iterator,
    List,
    Literal,
    Optional,
    Sequence,
    Set,
    Tuple,
)

from ..models import Exchange, SessionDetail, SessionSummary, ToolCall, UserPrompt
from ..util import (
    UTC,
    block_text,
    load_json_object,
    normalize_text,
    one_line,
    parse_timestamp,
)
from .base import HarnessAdapter
from .common import choose_title as _choose_title
from .common import file_path

try:  # Python 3.14+
    from compression import zstd as _zstd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised on older interpreters
    _zstd = None

TRANSCRIPT_RE = re.compile(r"^session(?:\.v(\d+))?\.jsonl\.zstd$")

MAX_PROMPT_CHARS = 4_000
MAX_SUMMARY_CHARS = 20_000
MAX_ASSISTANT_CHARS = 5_000

EDIT_TOOLS = {"edit", "write"}

DETAIL_KEYS = {
    "bash": ("command",),
    "read": ("file_path",),
    "edit": ("file_path",),
    "write": ("file_path",),
    "read_image": ("file_path",),
    "grep": ("pattern",),
    "glob": ("pattern",),
    "web_fetch": ("url",),
    "skill": ("name",),
    "subagent": ("description",),
    "send_message": ("agent_id",),
    "job_output": ("job_id",),
    "job_kill": ("job_id",),
    "present": ("files",),
}


class _ProcessStream:
    """Wrap a ``zstd`` subprocess stdout as a context-managed binary stream."""

    def __init__(self, process: "subprocess.Popen[bytes]") -> None:
        self._process = process

    def __enter__(self):
        return self._process.stdout

    def __exit__(self, exc_type, exc, tb) -> "Literal[False]":
        stream = self._process.stdout
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
        if self._process.poll() is None:
            self._process.kill()
        try:
            self._process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        return False


def _open_zstd(path: Path):
    if _zstd is not None:
        return _zstd.ZstdFile(path, "rb")
    executable = shutil.which("zstd")
    if not executable:
        raise ValueError(
            "zstd decoder unavailable; install the zstd CLI or use Python 3.14+"
        )
    process = subprocess.Popen(
        [executable, "-dc", "--quiet", "--", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return _ProcessStream(process)


def _iter_raw_lines(path: Path) -> Iterator[bytes]:
    with _open_zstd(path) as handle:
        iterator = iter(handle)
        while True:
            try:
                raw = next(iterator)
            except StopIteration:
                return
            except OSError:
                raise
            except Exception as exc:
                raise OSError("cannot decompress %s: %s" % (path, exc)) from exc
            yield raw


def _iter_raw_chunks(
    path: Path, chunk_size: int = 4 * 1024 * 1024
) -> Iterator[bytes]:
    with _open_zstd(path) as handle:
        while True:
            try:
                chunk = handle.read(chunk_size)
            except OSError:
                raise
            except Exception as exc:
                raise OSError("cannot decompress %s: %s" % (path, exc)) from exc
            if not chunk:
                return
            yield chunk


def _iter_records(path: Path) -> Iterator[Dict[str, Any]]:
    for raw in _iter_raw_lines(path):
        record = load_json_object(raw)
        if record is not None:
            yield record


def _content_text(content: Any) -> str:
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


def _human_prompt(record: Dict[str, Any]) -> str:
    if record.get("type") != "user/message":
        return ""
    data = record.get("data")
    if not isinstance(data, dict):
        return ""
    source = data.get("source")
    if not isinstance(source, dict) or source.get("kind") != "user":
        return ""
    return _content_text(data.get("content")).strip()


def _record_time(record: Dict[str, Any]) -> Optional[datetime]:
    return parse_timestamp(record.get("time"))


def _bare_session_id(value: Any) -> str:
    text = str(value or "").strip()
    prefix = "session-"
    if text.casefold().startswith(prefix):
        return text[len(prefix) :]
    return text


def _model_of(record: Dict[str, Any]) -> str:
    data = record.get("data")
    if not isinstance(data, dict):
        return ""
    model: Any = None
    if record.get("type") == "request/header":
        header = data.get("header")
        config = header.get("config") if isinstance(header, dict) else None
        model = config.get("model") if isinstance(config, dict) else None
    elif record.get("type") == "model/selection":
        model = data.get("model")
    return model.strip() if isinstance(model, str) else ""


def _cwd_of(record: Dict[str, Any]) -> str:
    data = record.get("data")
    if not isinstance(data, dict):
        return ""
    value = data.get("cwd")
    return value.strip() if isinstance(value, str) else ""


def _title_of(record: Dict[str, Any]) -> str:
    data = record.get("data")
    if not isinstance(data, dict):
        return ""
    value = data.get("title")
    return value.strip() if isinstance(value, str) else ""


@dataclass
class _Scan:
    header: Optional[Dict[str, Any]]
    first_prompt: str
    last_prompt: str
    title: str
    cwd: str
    model: str
    updated: Optional[datetime]


def _scan_session(path: Path) -> _Scan:
    """Stream one compressed log, keeping only bounded summary state."""

    header: Optional[Dict[str, Any]] = None
    first_prompt = ""
    last_prompt = ""
    title = ""
    cwd = ""
    model = ""
    updated: Optional[datetime] = None
    last_line: Optional[bytes] = None

    for raw in _iter_raw_lines(path):
        if header is None:
            header = load_json_object(raw)
            if header is not None and header.get("type") != "session":
                header = None
        if b"user/message" in raw:
            record = load_json_object(raw)
            if record is not None:
                text = _human_prompt(record)
                if text:
                    cleaned = block_text(text, MAX_PROMPT_CHARS)
                    if not first_prompt:
                        first_prompt = cleaned
                    last_prompt = cleaned
                    stamp = _record_time(record)
                    if stamp is not None:
                        updated = stamp
        if b"session/title" in raw:
            record = load_json_object(raw)
            if record is not None and record.get("type") == "session/title":
                candidate = _title_of(record)
                if candidate:
                    title = candidate
                stamp = _record_time(record)
                if stamp is not None:
                    updated = stamp
        if b"working-directory/change" in raw:
            record = load_json_object(raw)
            if record is not None and record.get("type") == "working-directory/change":
                candidate = _cwd_of(record)
                if candidate:
                    cwd = candidate
        if b"request/header" in raw or b"model/selection" in raw:
            record = load_json_object(raw)
            if record is not None:
                candidate = _model_of(record)
                if candidate:
                    model = candidate
        last_line = raw

    if last_line is not None:
        record = load_json_object(last_line)
        if record is not None:
            stamp = _record_time(record)
            if stamp is not None:
                updated = stamp

    return _Scan(
        header=header,
        first_prompt=first_prompt,
        last_prompt=last_prompt,
        title=title,
        cwd=cwd,
        model=model,
        updated=updated,
    )


def _transcript_version(name: str) -> Optional[int]:
    match = TRANSCRIPT_RE.match(name)
    if match is None:
        return None
    return int(match.group(1) or 1)


def _best_transcript(session_dir: Path) -> Optional[Path]:
    best: Optional[Tuple[Tuple[int, float], Path]] = None
    try:
        entries = list(session_dir.iterdir())
    except OSError:
        return None
    for path in entries:
        if not path.is_file():
            continue
        version = _transcript_version(path.name)
        if version is None:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size <= 0:
            continue
        key = (version, stat.st_mtime)
        if best is None or key > best[0]:
            best = (key, path)
    return best[1] if best is not None else None


def _file_path(value: Any, cwd: str) -> str:
    if not isinstance(value, str):
        return ""
    return file_path({"path": value.strip()}, cwd, ("path",))


def _tool_detail(name: str, arguments: Dict[str, Any]) -> str:
    for key in DETAIL_KEYS.get(name, ()):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
        if isinstance(value, list):
            parts = [
                item for item in value if isinstance(item, str) and item.strip()
            ]
            if parts:
                return one_line(", ".join(parts), 160)
    for value in arguments.values():
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
    return ""


def _normalize_todos(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    todos: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        subject = one_line(item.get("content") or item.get("subject"), 200)
        if not subject:
            continue
        todos.append({"subject": subject, "status": str(item.get("status") or "")})
    return todos


class DeepSeekAdapter(HarnessAdapter):
    """DeepSeek Harness desktop sessions under ``~/.dsh``."""

    name = "deepseek"
    aliases = ("deepseek", "deepseek-harness", "dsh")
    variants = "desktop"
    store_hint = "~/.dsh"
    home_env = "FMS_DEEPSEEK_HOME"

    def __init__(self) -> None:
        self._archive_cache: Optional[Tuple[Tuple[str, int, int], Set[str]]] = None

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".dsh"

    def session_roots(self) -> List[Path]:
        return [self.home() / "sessions"]

    def _archived_ids(self) -> Set[str]:
        path = self.home() / "storages" / "workspace.json"
        try:
            stat = path.stat()
        except OSError:
            return set()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        cached = self._archive_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        ids: Set[str] = set()
        try:
            data = load_json_object(path.read_bytes())
        except OSError:
            data = None
        if data is not None:
            global_state = data.get("global")
            values = (
                global_state.get("archivedSessionIds")
                if isinstance(global_state, dict)
                else None
            )
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str):
                        ids.add(_bare_session_id(value).casefold())
        self._archive_cache = (key, ids)
        return ids

    def iter_session_paths(self) -> Iterator[Path]:
        root = self.home() / "sessions"
        if not root.is_dir():
            return
        try:
            groups = list(root.iterdir())
        except OSError:
            return
        pending: List[Tuple[float, Path]] = []
        for group in groups:
            if not group.is_dir():
                continue
            try:
                entries = list(group.iterdir())
            except OSError:
                continue
            for session_dir in entries:
                if not session_dir.is_dir():
                    continue
                if not session_dir.name.startswith("session-"):
                    continue
                transcript = _best_transcript(session_dir)
                if transcript is None:
                    continue
                try:
                    mtime = transcript.stat().st_mtime
                except OSError:
                    continue
                pending.append((mtime, transcript))
        pending.sort(key=lambda item: item[0], reverse=True)
        for _, path in pending:
            yield path

    def session_id_for(self, path: Path) -> str:
        return _bare_session_id(path.parent.name)

    def summarize(self, path: Path) -> SessionSummary:
        scan = _scan_session(path)
        header = scan.header
        if header is None:
            raise ValueError("cannot read DeepSeek session header: %s" % path)
        depth = header.get("delegationDepth")
        if isinstance(depth, int) and not isinstance(depth, bool) and depth > 0:
            raise ValueError(
                "DeepSeek subagent session is not resumable: %s" % path
            )

        session_id = _bare_session_id(header.get("id") or path.parent.name)
        cwd = scan.cwd
        if not cwd:
            value = header.get("cwd")
            cwd = value.strip() if isinstance(value, str) else ""

        started = parse_timestamp(header.get("createdAt"))
        updated = scan.updated
        if updated is None:
            try:
                updated = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError:
                updated = datetime.now(tz=UTC)
        if started is None:
            started = updated

        title = one_line(scan.title, 200)
        if not title:
            title = _choose_title(scan.first_prompt, scan.last_prompt) or session_id

        try:
            size = path.stat().st_size
        except OSError:
            size = 0

        return SessionSummary(
            harness=self.name,
            session_id=session_id,
            path=path,
            cwd=cwd,
            updated=updated,
            title=title,
            first_prompt=scan.first_prompt,
            last_prompt=scan.last_prompt,
            started=started,
            branch="",
            model=scan.model,
            entrypoint="desktop",
            version="",
            size=size,
            variants=self.variants,
            archived=session_id.casefold() in self._archived_ids(),
        )

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        for record in _iter_records(summary.path):
            text = _human_prompt(record)
            if not text:
                continue
            yield UserPrompt(text=text, timestamp=_record_time(record))

    def contains(self, summary: SessionSummary, tokens: Sequence[str]) -> bool:
        remaining = {normalize_text(token) for token in tokens if token}
        remaining.discard("")
        if not remaining:
            return True
        overlap = b""
        try:
            for chunk in _iter_raw_chunks(summary.path):
                data = overlap + chunk
                text = normalize_text(data.decode("utf-8", "ignore"))
                for token in tuple(remaining):
                    if token in text:
                        remaining.discard(token)
                if not remaining:
                    return True
                overlap = data[-512:]
        except (OSError, ValueError):
            return False
        return not remaining

    def load(self, summary: SessionSummary) -> SessionDetail:
        exchanges: Deque[Exchange] = deque(maxlen=50)
        current: Optional[Exchange] = None
        tool_counts: Counter = Counter()
        recent_tools: Deque[ToolCall] = deque(maxlen=20)
        edited: "OrderedDict[str, int]" = OrderedDict()
        cwd = summary.cwd
        model = summary.model
        first_prompt = summary.first_prompt
        last_prompt = summary.last_prompt
        started = summary.started
        updated = summary.updated
        compact_summary = ""
        todos: List[Dict[str, Any]] = []
        turn_count = 0

        def append_current() -> None:
            nonlocal current
            if current is None:
                return
            if current.user_text or current.assistant_texts or current.tools:
                exchanges.append(current)
            current = None

        for record in _iter_records(summary.path):
            timestamp = _record_time(record)
            if timestamp is not None:
                if started is None or timestamp < started:
                    started = timestamp
                if updated is None or timestamp > updated:
                    updated = timestamp

            record_type = record.get("type")
            data = record.get("data")
            data = data if isinstance(data, dict) else {}

            if record_type == "session":
                value = record.get("cwd")
                if isinstance(value, str) and value.strip():
                    cwd = value.strip()
                created = parse_timestamp(record.get("createdAt"))
                if created is not None:
                    started = created
                continue
            if record_type == "working-directory/change":
                value = _cwd_of(record)
                if value:
                    cwd = value
                continue
            if record_type == "request/header" or record_type == "model/selection":
                value = _model_of(record)
                if value:
                    model = value
                continue
            if record_type == "user/message":
                text = _human_prompt(record)
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
            if record_type == "assistant/message":
                message = data.get("message")
                text = (
                    _content_text(message.get("content"))
                    if isinstance(message, dict)
                    else ""
                )
                if not text.strip():
                    continue
                if current is None:
                    current = Exchange(timestamp=timestamp)
                current.assistant_texts.append(
                    block_text(text, MAX_ASSISTANT_CHARS)
                )
                if len(current.assistant_texts) > 3:
                    current.assistant_texts = current.assistant_texts[-3:]
                continue
            if record_type == "assistant/chunk":
                chunk = data.get("chunk")
                reason = chunk.get("reason") if isinstance(chunk, dict) else None
                if not isinstance(reason, dict) or reason.get("kind") != "error":
                    continue
                failure = reason.get("failure")
                message = (
                    failure.get("message") if isinstance(failure, dict) else None
                )
                if not isinstance(message, str) or not message.strip():
                    continue
                cleaned = block_text(message, MAX_ASSISTANT_CHARS)
                if current is None:
                    current = Exchange(timestamp=timestamp)
                if not current.assistant_texts or current.assistant_texts[-1] != cleaned:
                    current.assistant_texts.append(cleaned)
                    if len(current.assistant_texts) > 3:
                        current.assistant_texts = current.assistant_texts[-3:]
                continue
            if record_type == "tool/call":
                name = str(data.get("name") or "tool")
                arguments = load_json_object(data.get("arguments")) or {}
                call = ToolCall(
                    name=name,
                    detail=_tool_detail(name, arguments),
                    timestamp=timestamp,
                )
                if current is None:
                    current = Exchange(timestamp=timestamp)
                current.tools.append(call)
                if len(current.tools) > 8:
                    current.tools = current.tools[-8:]
                tool_counts[name] += 1
                recent_tools.append(call)
                if name in EDIT_TOOLS:
                    path_value = _file_path(arguments.get("file_path"), cwd)
                    if path_value:
                        edited[path_value] = edited.get(path_value, 0) + 1
                if name == "todo_write":
                    todos = _normalize_todos(arguments.get("todos"))
                continue
            if record_type == "todo/write":
                todos = _normalize_todos(data.get("todos"))
                continue
            if record_type == "compaction/summary":
                text = _content_text(data.get("summary")) or _content_text(
                    data.get("rawOutput")
                )
                if text.strip():
                    compact_summary = block_text(text, MAX_SUMMARY_CHARS)
                continue

        append_current()

        if not first_prompt:
            first_prompt = last_prompt
        summary.cwd = cwd or summary.cwd
        summary.model = model
        summary.first_prompt = first_prompt
        summary.last_prompt = last_prompt
        summary.started = started
        summary.updated = updated or summary.updated
        if not summary.title:
            summary.title = _choose_title(first_prompt, last_prompt) or summary.title

        edited_files = [
            {"path": path, "count": count}
            for path, count in list(edited.items())[-30:]
        ]

        return SessionDetail(
            summary=summary,
            compact_summary=compact_summary,
            todos=todos,
            exchanges=list(exchanges),
            edited_files=edited_files,
            tool_counts=dict(tool_counts.most_common()),
            recent_tools=list(recent_tools),
            turn_count=turn_count,
        )
