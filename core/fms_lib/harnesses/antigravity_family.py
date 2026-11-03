"""Shared parser for the Google Antigravity conversation stores.

Every Antigravity edition keeps one SQLite database per conversation under
``conversations/<conversation id>.db``, metadata and archive state in
``conversation_summaries.db``, and the readable transcript under
``brain/<conversation id>/.system_generated/logs``. The desktop app and the
retired Antigravity IDE share one store and one ref namespace; the Antigravity
CLI keeps a separate store and is exposed as its own harness.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from collections import Counter, OrderedDict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import unquote, urlparse

from ..models import Exchange, SessionDetail, SessionSummary, ToolCall, UserPrompt
from ..util import (
    UTC,
    block_text,
    iter_head_records,
    iter_tail_records,
    load_json_object,
    normalize_text,
    one_line,
    parse_timestamp,
)
from .base import HarnessAdapter

MAX_PROMPT_CHARS = 4_000
MAX_ASSISTANT_CHARS = 5_000
MAX_TODOS = 400
HEAD_BYTES = 400_000
HEAD_RECORDS = 600
TAIL_BYTES = 400_000

SUMMARY_DB = "conversation_summaries.db"
CONVERSATIONS_DIR = "conversations"
BRAIN_DIR = "brain"
TRANSCRIPT_NAMES = (
    ".system_generated/logs/transcript_full.jsonl",
    ".system_generated/logs/transcript.jsonl",
)

USER_REQUEST_RE = re.compile(r"<USER_REQUEST>(.*?)</USER_REQUEST>", re.S | re.I)
INJECTED_TAGS = ("ADDITIONAL_METADATA", "USER_SETTINGS_CHANGE", "SKILL")
CHECKBOX_RE = re.compile(r"^\s*[-*+]\s*\[([ xX])\]\s*(.+?)\s*$")

GENERIC_PROMPTS = {
    "continue",
    "go on",
    "keep going",
    "next",
    "ok",
    "yes",
    "继续",
    "接着",
    "继续吧",
    "好的",
    "好",
    "下一步",
    "?",
    "？",
}

EDIT_TOOLS = {
    "write_to_file",
    "write_file",
    "replace_file_content",
    "edit_file",
}

FILE_KEYS = ("TargetFile", "Path", "AbsolutePath", "file_path", "path")
DETAIL_KEYS = (
    "toolSummary",
    "toolAction",
    "Description",
    "description",
    "CommandLine",
    "Command",
    "Query",
    "query",
    "SearchPath",
    "DirectoryPath",
    "Url",
    "Prompt",
    "name",
)


def _is_generic(value: str) -> bool:
    compact = re.sub(r"\s+", " ", value).strip().casefold()
    if not compact or len(compact) <= 1:
        return True
    if re.fullmatch(r"[\d\W_]+", compact):
        return True
    return compact in GENERIC_PROMPTS


def _clean_prompt(value: str) -> str:
    text = value
    for tag in INJECTED_TAGS:
        text = re.sub(
            r"<%s>.*?</%s>" % (tag, tag), "", text, flags=re.S | re.I
        )
    return text.strip()


def _prompt_text(record: Dict[str, Any]) -> str:
    if record.get("type") != "USER_INPUT":
        return ""
    source = record.get("source")
    if isinstance(source, str) and source and source != "USER_EXPLICIT":
        return ""
    content = record.get("content")
    if not isinstance(content, str) or not content.strip():
        return ""
    match = USER_REQUEST_RE.search(content)
    text = match.group(1) if match else content
    return _clean_prompt(text)


def _record_timestamp(record: Dict[str, Any]) -> Optional[datetime]:
    return parse_timestamp(record.get("created_at"))


def _arguments(call: Dict[str, Any]) -> Dict[str, Any]:
    value = call.get("args")
    return value if isinstance(value, dict) else {}


def _tool_detail(arguments: Dict[str, Any]) -> str:
    for key in DETAIL_KEYS:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
    for value in arguments.values():
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
    return ""


def _file_path(arguments: Dict[str, Any], cwd: str) -> str:
    value = ""
    for key in FILE_KEYS:
        candidate = arguments.get(key)
        if isinstance(candidate, str) and candidate.strip():
            value = candidate.strip()
            break
    if not value:
        return ""
    value = os.path.expanduser(value)
    if cwd and not os.path.isabs(value):
        value = os.path.join(cwd, value)
    return os.path.normpath(value)


def _workspace_paths(raw: Any) -> List[str]:
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return []
    elif isinstance(raw, list):
        data = raw
    else:
        return []
    if not isinstance(data, list):
        return []
    paths: List[str] = []
    for item in data:
        if not isinstance(item, str) or not item.strip():
            continue
        parsed = urlparse(item)
        if parsed.scheme == "file":
            path = unquote(parsed.path)
            if re.match(r"^/[A-Za-z]:/", path):
                path = path[1:]
            if path:
                paths.append(path)
        else:
            paths.append(item)
    return paths


def _checkpoint_todos(content: str) -> List[Dict[str, Any]]:
    todos: List[Dict[str, Any]] = []
    for line in content.splitlines():
        match = CHECKBOX_RE.match(line)
        if match is None:
            continue
        subject = one_line(match.group(2), 200)
        if not subject:
            continue
        status = "completed" if match.group(1).strip().lower() == "x" else "pending"
        todos.append({"subject": subject, "status": status})
        if len(todos) >= MAX_TODOS:
            break
    return todos


class AntigravityBaseAdapter(HarnessAdapter):
    """Antigravity SQLite metadata plus JSONL brain transcripts."""

    variants = "desktop, ide"
    home_dirname = ".gemini/antigravity"
    home_env = "FMS_ANTIGRAVITY_HOME"
    entrypoint_label = "desktop"
    archive_source = False

    def __init__(self) -> None:
        self._snapshot_lock = threading.Lock()
        self._snapshot_cache: Optional[
            Tuple[Tuple[str, int, int], Dict[str, Dict[str, Any]], frozenset]
        ] = None

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / self.home_dirname

    def _summary_db(self) -> Path:
        return self.home() / SUMMARY_DB

    def _conversations_root(self) -> Path:
        return self.home() / CONVERSATIONS_DIR

    def _brain_roots(self) -> List[Tuple[Path, str]]:
        return [(self.home() / BRAIN_DIR, self.entrypoint_label)]

    def session_roots(self) -> List[Path]:
        return [self._conversations_root()]

    @staticmethod
    def _connect(db: Path) -> sqlite3.Connection:
        db = db.expanduser()
        if not db.is_absolute():
            db = db.resolve()
        uri = db.as_uri()
        last_error: Optional[Exception] = None
        # A WAL database without a -shm file cannot be opened read-only, so
        # fall back to an immutable snapshot; no store file is ever created.
        for suffix in ("?mode=ro", "?mode=ro&immutable=1"):
            connection: Optional[sqlite3.Connection] = None
            try:
                connection = sqlite3.connect(uri + suffix, uri=True, timeout=1.0)
                connection.execute(
                    "SELECT name FROM sqlite_master LIMIT 1"
                ).fetchone()
                return connection
            except (OSError, sqlite3.Error) as exc:
                last_error = exc
                if connection is not None:
                    connection.close()
        raise sqlite3.OperationalError(str(last_error) if last_error else "cannot open")

    @staticmethod
    def _table_columns(connection: sqlite3.Connection, table: str) -> set:
        try:
            rows = connection.execute("PRAGMA table_info(%s)" % table).fetchall()
        except sqlite3.Error:
            return set()
        return {str(row[1]) for row in rows}

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        try:
            row = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
        except sqlite3.Error:
            return False
        return row is not None

    def _snapshot(self) -> Tuple[Dict[str, Dict[str, Any]], frozenset]:
        db = self._summary_db()
        if not db.is_file():
            return {}, frozenset()
        try:
            stat = db.stat()
        except OSError:
            return {}, frozenset()
        key = (str(db), stat.st_mtime_ns, stat.st_size)
        cached = self._snapshot_cache
        if cached is not None and cached[0] == key:
            return cached[1], cached[2]
        with self._snapshot_lock:
            cached = self._snapshot_cache
            if cached is not None and cached[0] == key:
                return cached[1], cached[2]
            metadata: Dict[str, Dict[str, Any]] = {}
            archived: frozenset = frozenset()
            try:
                connection = self._connect(db)
            except (OSError, sqlite3.Error, ValueError):
                connection = None
            if connection is not None:
                try:
                    metadata = self._read_metadata(connection)
                    if self.archive_source:
                        archived = self._read_archived(connection)
                except sqlite3.Error:
                    metadata = {}
                    archived = frozenset()
                finally:
                    connection.close()
            self._snapshot_cache = (key, metadata, archived)
            return metadata, archived

    @staticmethod
    def _read_metadata(
        connection: sqlite3.Connection,
    ) -> Dict[str, Dict[str, Any]]:
        columns = AntigravityBaseAdapter._table_columns(
            connection, "conversation_summaries"
        )
        wanted = (
            "conversation_id",
            "title",
            "preview",
            "last_modified_time",
            "workspace_uris",
            "nesting_depth",
            "parent_conversation_id",
            "project_id",
        )
        selected = [column for column in wanted if column in columns]
        if "conversation_id" not in selected:
            return {}
        query = "SELECT %s FROM conversation_summaries" % ", ".join(selected)
        metadata: Dict[str, Dict[str, Any]] = {}
        for row in connection.execute(query):
            record = dict(zip(selected, row))
            raw_id = record.get("conversation_id")
            if raw_id:
                metadata[str(raw_id)] = record
        return metadata

    @staticmethod
    def _read_archived(connection: sqlite3.Connection) -> frozenset:
        if not AntigravityBaseAdapter._table_exists(connection, "conversations_fts"):
            return frozenset()
        try:
            rows = connection.execute(
                "SELECT conversation_id FROM conversations_fts "
                "GROUP BY conversation_id "
                "HAVING MAX(CAST(archived AS INTEGER)) > 0"
            ).fetchall()
        except sqlite3.Error:
            return frozenset()
        return frozenset(str(row[0]) for row in rows if row and row[0])

    @staticmethod
    def _is_nested(row: Dict[str, Any]) -> bool:
        depth = row.get("nesting_depth")
        if isinstance(depth, int) and depth > 0:
            return True
        parent = row.get("parent_conversation_id")
        return isinstance(parent, str) and bool(parent.strip())

    def iter_session_paths(self) -> Iterator[Path]:
        root = self._conversations_root()
        if not root.is_dir():
            return
        metadata, _ = self._snapshot()
        paths = [path for path in root.glob("*.db") if path.is_file()]
        paths.sort(key=lambda path: path.name)
        for path in paths:
            row = metadata.get(path.stem)
            if row is not None and self._is_nested(row):
                continue
            yield path

    def _transcript(self, raw_id: str) -> Tuple[Optional[Path], str]:
        for root, label in self._brain_roots():
            for name in TRANSCRIPT_NAMES:
                path = root / raw_id / name
                if path.is_file():
                    return path, label
        return None, ""

    def _entrypoint(
        self, raw_id: str, row: Dict[str, Any], label: str
    ) -> str:
        if label:
            return label
        project = row.get("project_id")
        if isinstance(project, str) and not project.strip():
            return "ide"
        return self.entrypoint_label

    def _prompt_pairs(
        self, records: Sequence[Dict[str, Any]]
    ) -> List[Tuple[str, Optional[datetime]]]:
        prompts: List[Tuple[str, Optional[datetime]]] = []
        for record in records:
            text = _prompt_text(record)
            if text:
                prompts.append((text, _record_timestamp(record)))
        return prompts

    def summarize(self, path: Path) -> SessionSummary:
        raw_id = path.stem
        metadata, archived_ids = self._snapshot()
        row = metadata.get(raw_id) or {}
        transcript, label = self._transcript(raw_id)
        head: List[Dict[str, Any]] = []
        tail: List[Dict[str, Any]] = []
        if transcript is not None:
            head = list(
                iter_head_records(transcript, HEAD_BYTES, HEAD_RECORDS)
            )
            tail = iter_tail_records(transcript, TAIL_BYTES)
        head_prompts = self._prompt_pairs(head)
        tail_prompts = self._prompt_pairs(tail)
        first_prompt = (
            block_text(head_prompts[0][0], MAX_PROMPT_CHARS)
            if head_prompts
            else ""
        )
        last_prompt = (
            block_text(tail_prompts[-1][0], MAX_PROMPT_CHARS)
            if tail_prompts
            else ""
        )
        if not first_prompt and tail_prompts:
            first_prompt = block_text(tail_prompts[0][0], MAX_PROMPT_CHARS)
        if not last_prompt and head_prompts:
            last_prompt = block_text(head_prompts[-1][0], MAX_PROMPT_CHARS)
        if not first_prompt:
            first_prompt = last_prompt
        if not last_prompt:
            last_prompt = first_prompt

        workspaces = _workspace_paths(row.get("workspace_uris"))
        cwd = workspaces[0] if workspaces else ""

        started: Optional[datetime] = None
        for record in head:
            started = _record_timestamp(record)
            if started is not None:
                break
        updated = parse_timestamp(row.get("last_modified_time"))
        if updated is None and tail:
            for record in reversed(tail):
                updated = _record_timestamp(record)
                if updated is not None:
                    break
        if updated is None:
            try:
                updated = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError:
                updated = datetime.now(tz=UTC)
        if started is None:
            started = updated

        title = ""
        value = row.get("title")
        if isinstance(value, str) and value.strip() and not _is_generic(value):
            title = one_line(value, 100)
        if not title:
            candidates = [prompt for prompt, _ in reversed(tail_prompts)]
            candidates += [prompt for prompt, _ in head_prompts]
            chosen = next(
                (
                    prompt
                    for prompt in candidates
                    if prompt and not _is_generic(prompt)
                ),
                "",
            )
            title = one_line(chosen, 100)
        if not title:
            preview = row.get("preview")
            if isinstance(preview, str) and preview.strip():
                title = one_line(preview, 100)
        if not title:
            title = one_line(last_prompt or first_prompt, 100) or raw_id

        try:
            size = path.stat().st_size
        except OSError:
            size = 0

        entrypoint = self._entrypoint(raw_id, row, label)
        return SessionSummary(
            harness=self.name,
            session_id=raw_id,
            path=path,
            cwd=cwd,
            updated=updated,
            title=title,
            first_prompt=first_prompt,
            last_prompt=last_prompt,
            started=started,
            branch="",
            model="",
            entrypoint=entrypoint,
            version="",
            size=size,
            variants=entrypoint,
            archived=raw_id in archived_ids,
        )

    @staticmethod
    def _iter_records(path: Path) -> Iterator[Dict[str, Any]]:
        try:
            handle = open(path, "rb")
        except OSError:
            return
        with handle:
            for raw in handle:
                record = load_json_object(raw)
                if record is not None:
                    yield record

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        transcript, _ = self._transcript(summary.session_id)
        if transcript is None:
            return
        for record in self._iter_records(transcript):
            text = _prompt_text(record)
            if not text:
                continue
            yield UserPrompt(text=text, timestamp=_record_timestamp(record))

    def load(self, summary: SessionSummary) -> SessionDetail:
        transcript, _ = self._transcript(summary.session_id)
        exchanges: Deque[Exchange] = deque(maxlen=50)
        current: Optional[Exchange] = None
        tool_counts: Counter = Counter()
        recent_tools: Deque[ToolCall] = deque(maxlen=20)
        edited: "OrderedDict[str, int]" = OrderedDict()
        cwd = summary.cwd
        first_prompt = summary.first_prompt
        last_prompt = summary.last_prompt
        started = summary.started
        updated = summary.updated
        turn_count = 0
        todos: List[Dict[str, Any]] = []

        def append_current() -> None:
            nonlocal current
            if current is None:
                return
            if current.user_text or current.assistant_texts or current.tools:
                exchanges.append(current)
            current = None

        if transcript is not None:
            for record in self._iter_records(transcript):
                timestamp = _record_timestamp(record)
                if timestamp is not None:
                    if started is None or timestamp < started:
                        started = timestamp
                    if updated is None or timestamp > updated:
                        updated = timestamp

                prompt = _prompt_text(record)
                if prompt:
                    append_current()
                    cleaned = block_text(prompt, MAX_PROMPT_CHARS)
                    current = Exchange(user_text=cleaned, timestamp=timestamp)
                    turn_count += 1
                    last_prompt = cleaned
                    if not first_prompt:
                        first_prompt = cleaned
                    continue

                kind = record.get("type")
                if kind == "CHECKPOINT":
                    content = record.get("content")
                    if isinstance(content, str):
                        parsed = _checkpoint_todos(content)
                        if parsed:
                            todos = parsed
                    continue
                if kind != "PLANNER_RESPONSE":
                    continue

                content = record.get("content")
                if isinstance(content, str) and content.strip():
                    if current is None:
                        current = Exchange(timestamp=timestamp)
                    current.assistant_texts.append(
                        block_text(content, MAX_ASSISTANT_CHARS)
                    )
                    if len(current.assistant_texts) > 3:
                        current.assistant_texts = current.assistant_texts[-3:]

                calls = record.get("tool_calls")
                if not isinstance(calls, list):
                    continue
                for call in calls:
                    if not isinstance(call, dict):
                        continue
                    name = str(call.get("name") or "tool")
                    arguments = _arguments(call)
                    tool = ToolCall(
                        name=name,
                        detail=_tool_detail(arguments),
                        timestamp=timestamp,
                    )
                    if current is None:
                        current = Exchange(timestamp=timestamp)
                    current.tools.append(tool)
                    if len(current.tools) > 8:
                        current.tools = current.tools[-8:]
                    tool_counts[name] += 1
                    recent_tools.append(tool)
                    if name.casefold() in EDIT_TOOLS:
                        file_path = _file_path(arguments, cwd)
                        if file_path:
                            edited[file_path] = edited.pop(file_path, 0) + 1

        append_current()

        if not first_prompt:
            first_prompt = last_prompt
        summary.cwd = cwd or summary.cwd
        summary.first_prompt = first_prompt
        summary.last_prompt = last_prompt
        summary.started = started
        summary.updated = updated or summary.updated

        edited_files = [
            {"path": path, "count": count}
            for path, count in list(edited.items())[-30:]
        ]
        return SessionDetail(
            summary=summary,
            compact_summary="",
            todos=todos,
            exchanges=list(exchanges),
            edited_files=edited_files,
            tool_counts=dict(tool_counts.most_common()),
            recent_tools=list(recent_tools),
            turn_count=turn_count,
        )

    @staticmethod
    def _scan(path: Path, remaining: set) -> None:
        overlap = b""
        try:
            handle = open(path, "rb")
        except OSError:
            return
        with handle:
            while remaining:
                chunk = handle.read(4 * 1024 * 1024)
                if not chunk:
                    break
                data = overlap + chunk
                text = normalize_text(data.decode("utf-8", "ignore"))
                for token in tuple(remaining):
                    if token in text:
                        remaining.discard(token)
                overlap = data[-512:]

    def contains(self, summary: SessionSummary, tokens: Sequence[str]) -> bool:
        remaining = {normalize_text(token) for token in tokens if token}
        remaining.discard("")
        if not remaining:
            return True
        transcript, _ = self._transcript(summary.session_id)
        if transcript is not None:
            self._scan(transcript, remaining)
        elif summary.path.is_file():
            self._scan(summary.path, remaining)
        return not remaining
