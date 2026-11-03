"""Shared parser for the WorkBuddy JSONL transcript family.

Both WorkBuddy editions keep sessions as ``projects/<slug>/<session id>.jsonl``
with a per-session todo directory and one ``workbuddy.db`` that carries titles
and archive state. The stores and ref namespaces are separate; subclasses only
supply the home directory and environment overrides.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections import Counter, OrderedDict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, Iterator, List, Optional, Sequence, Tuple

from ..models import Exchange, SessionDetail, SessionSummary, ToolCall, UserPrompt
from ..util import (
    UTC,
    block_text,
    file_contains_all,
    iter_head_records,
    iter_tail_records,
    load_json_object,
    one_line,
    parse_timestamp,
)
from .base import HarnessAdapter
from .common import file_path, tool_detail
from .common import is_generic as _is_generic

MAX_PROMPT_CHARS = 4_000
MAX_SUMMARY_CHARS = 20_000
MAX_ASSISTANT_CHARS = 5_000
PROMPT_HEAD_LIMIT = 200
PROMPT_TAIL_LIMIT = 200
MAX_TODOS = 400
HEAD_BYTES = 2_000_000
TAIL_BYTES = 512_000

USER_QUERY_RE = re.compile(r"<user_query>(.*?)</user_query>", re.S)
CB_SUMMARY_RE = re.compile(r"<cb_summary>(.*?)</cb_summary>", re.S)
REMINDER_RE = re.compile(
    r"<system-reminder\b[^>]*>.*?</system-reminder>", re.S
)

PROMPT_SKIP_PREFIXES = (
    "<system-reminder",
    "<task-notification>",
    "<user-prompt-submit-hook>",
    "<local-command",
)

EDIT_TOOLS = {
    "edit",
    "write",
    "multiedit",
    "notebookedit",
    "apply_patch",
}

TEXT_KEYS = (
    "file_path",
    "filePath",
    "path",
    "command",
    "description",
    "pattern",
    "prompt",
    "skill",
    "url",
    "query",
)

FILE_KEYS = ("file_path", "filePath", "notebook_path", "path", "target_file")


def _strip_reminders(value: str) -> str:
    return REMINDER_RE.sub("", value).strip()


def _clean_prompt(value: str) -> str:
    text = _strip_reminders(value.strip())
    for tag in ("task-notification", "command-message", "command-name"):
        text = re.sub(r"<%s>.*?</%s>" % (tag, tag), "", text, flags=re.S)
    return text.strip()


def _meaningful_prompt(value: str) -> bool:
    text = _clean_prompt(value)
    if not text:
        return False
    if text.casefold().startswith(PROMPT_SKIP_PREFIXES):
        return False
    if re.fullmatch(r"/\S+", text):
        return False
    return True


def _part_text(part: Any) -> str:
    if not isinstance(part, dict):
        return ""
    kind = part.get("type")
    if kind not in ("input_text", "output_text", "text"):
        return ""
    text = part.get("text")
    return text if isinstance(text, str) else ""


def _content_text(record: Dict[str, Any]) -> str:
    content = record.get("content")
    if not isinstance(content, list):
        return ""
    return "\n".join(
        text for text in (_part_text(part) for part in content) if text
    )


def _provider_data(record: Dict[str, Any]) -> Dict[str, Any]:
    value = record.get("providerData")
    return value if isinstance(value, dict) else {}


def _is_compaction(record: Dict[str, Any], text: str) -> bool:
    provider = _provider_data(record)
    return bool(
        provider.get("isSummary")
        or provider.get("isCompacted")
        or provider.get("compactType")
        or "<cb_summary>" in text
    )


def _compaction_body(text: str) -> str:
    match = CB_SUMMARY_RE.search(text)
    return (match.group(1) if match else text).strip()


def _prompt_from_record(record: Dict[str, Any]) -> str:
    """Return the human prompt in one transcript record, or an empty string."""

    if record.get("type") != "message" or record.get("role") != "user":
        return ""
    if _provider_data(record).get("isMeta") is True:
        return ""
    text = _content_text(record)
    if not text:
        return ""
    if _is_compaction(record, text):
        return ""
    queries = [match.strip() for match in USER_QUERY_RE.findall(text)]
    queries = [query for query in queries if query]
    if queries:
        return _clean_prompt("\n".join(queries))
    provider = _provider_data(record)
    if provider.get("startsNewUserRequest") is True:
        candidate = _strip_reminders(text)
        if _meaningful_prompt(candidate):
            return _clean_prompt(candidate)
    return ""


def _initial_summary_prompt(records: Sequence[Dict[str, Any]]) -> str:
    """Read the denormalized initial prompt stored in a ``summary`` record."""

    for record in records:
        if record.get("type") != "summary":
            continue
        if _provider_data(record).get("source") != "initial-user-message":
            continue
        value = record.get("summary")
        if isinstance(value, str):
            text = _clean_prompt(value)
            if text:
                return text
    return ""


def _assistant_text(record: Dict[str, Any]) -> str:
    if record.get("type") != "message" or record.get("role") != "assistant":
        return ""
    return _content_text(record)


def _arguments(record: Dict[str, Any]) -> Dict[str, Any]:
    raw = record.get("arguments")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        return load_json_object(raw) or {}
    return {}


def _tool_detail(arguments: Dict[str, Any]) -> str:
    return tool_detail(arguments, TEXT_KEYS)


def _file_path(arguments: Dict[str, Any], cwd: str) -> str:
    return file_path(arguments, cwd, FILE_KEYS)


def _record_timestamp(record: Dict[str, Any]) -> Optional[datetime]:
    return parse_timestamp(record.get("timestamp"))


class WorkBuddyBaseAdapter(HarnessAdapter):
    """WorkBuddy desktop: JSONL transcripts plus one application database."""

    variants = "desktop"
    home_dirname = ""
    home_env = ""
    app_db_env = ""
    _archive_cache: Optional[Tuple[Tuple[str, int, int], Dict[str, str]]] = None

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / self.home_dirname

    def _db_path(self) -> Path:
        override = os.environ.get(self.app_db_env)
        if override:
            return Path(override).expanduser()
        return self.home() / "workbuddy.db"

    def session_roots(self) -> List[Path]:
        return [self.home() / "projects"]

    def iter_session_paths(self) -> Iterator[Path]:
        root = self.home() / "projects"
        if not root.is_dir():
            return
        paths = [
            path
            for path in root.glob("*/*.jsonl")
            if path.is_file() and not path.name.endswith(".file-rollback.ndjson")
        ]
        paths.sort(key=lambda path: self._mtime(path), reverse=True)
        yield from paths

    @staticmethod
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    @staticmethod
    def _connect(db: Path) -> sqlite3.Connection:
        db = db.expanduser()
        if not db.is_absolute():
            db = db.resolve()
        return sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=1.0)

    @staticmethod
    def _session_row(
        connection: sqlite3.Connection, raw_id: str
    ) -> Optional[Dict[str, Any]]:
        try:
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
            }
        except sqlite3.Error:
            return None
        wanted = (
            "id",
            "cwd",
            "title",
            "custom_title",
            "status",
            "model",
            "created_at",
            "updated_at",
            "last_activity_at",
            "deleted_at",
            "visibility",
        )
        selected = [column for column in wanted if column in columns]
        if "id" not in selected:
            return None
        row = connection.execute(
            "SELECT %s FROM sessions WHERE id = ?" % ", ".join(selected),
            (raw_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(selected, row))

    def _hidden_ids(self) -> Dict[str, str]:
        """Map hidden session id to a reason, cached per database state."""

        db = self._db_path()
        if not db.is_file():
            return {}
        try:
            stat = db.stat()
        except OSError:
            return {}
        key = (str(db), stat.st_mtime_ns, stat.st_size)
        cached = self._archive_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        hidden = self._read_hidden_ids(db)
        self._archive_cache = (key, hidden)
        return hidden

    def _read_hidden_ids(self, db: Path) -> Dict[str, str]:
        try:
            connection = self._connect(db)
        except (OSError, sqlite3.Error, ValueError):
            return {}
        try:
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "id" not in columns:
                return {}
            selected = ["id"]
            for column in ("status", "deleted_at", "visibility"):
                if column in columns:
                    selected.append(column)
            hidden: Dict[str, str] = {}
            for row in connection.execute(
                "SELECT %s FROM sessions" % ", ".join(selected)
            ):
                record = dict(zip(selected, row))
                raw_id = record.get("id")
                if not raw_id:
                    continue
                reason = self._hidden_reason(record)
                if reason:
                    hidden[str(raw_id)] = reason
            return hidden
        except sqlite3.Error:
            return {}
        finally:
            connection.close()

    @staticmethod
    def _hidden_reason(record: Dict[str, Any]) -> str:
        deleted_at = record.get("deleted_at")
        if isinstance(deleted_at, (int, float)) and not isinstance(deleted_at, bool):
            # Cloud rows use -1 as a "never deleted" sentinel, so only a real
            # positive timestamp counts as deleted.
            if deleted_at > 0:
                return "deleted"
        status = record.get("status")
        if isinstance(status, str) and status.strip().casefold() == "archived":
            return "archived"
        visibility = record.get("visibility")
        if isinstance(visibility, str) and visibility.strip().casefold() == "archived":
            return "archived"
        return ""

    def _archived(self, raw_id: str, row: Optional[Dict[str, Any]]) -> bool:
        if row is not None and self._hidden_reason(row):
            return True
        return raw_id in self._hidden_ids()

    @staticmethod
    def _prompts(records: Sequence[Dict[str, Any]]) -> List[Tuple[str, Optional[datetime]]]:
        prompts: List[Tuple[str, Optional[datetime]]] = []
        for record in records:
            text = _prompt_from_record(record)
            if text:
                prompts.append((text, _record_timestamp(record)))
        return prompts

    @staticmethod
    def _title_from(records: Sequence[Dict[str, Any]]) -> str:
        for record in records:
            if record.get("type") != "ai-title":
                continue
            value = record.get("aiTitle")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def summarize(self, path: Path) -> SessionSummary:
        head = list(iter_head_records(path, HEAD_BYTES, PROMPT_HEAD_LIMIT * 4))
        tail = iter_tail_records(path, TAIL_BYTES)
        if not head and not tail:
            raise ValueError("cannot read workbuddy transcript: %s" % path)

        head_prompts = self._prompts(head)
        tail_prompts = self._prompts(tail)
        initial_prompt = _initial_summary_prompt(head) or _initial_summary_prompt(tail)
        first_prompt = block_text(head_prompts[0][0], MAX_PROMPT_CHARS) if head_prompts else ""
        last_prompt = block_text(tail_prompts[-1][0], MAX_PROMPT_CHARS) if tail_prompts else ""
        if not first_prompt:
            first_prompt = block_text(initial_prompt, MAX_PROMPT_CHARS) or last_prompt
        if not last_prompt:
            last_prompt = first_prompt

        raw_id = path.stem
        row: Optional[Dict[str, Any]] = None
        db = self._db_path()
        if db.is_file():
            try:
                connection = self._connect(db)
            except (OSError, sqlite3.Error, ValueError):
                connection = None
            if connection is not None:
                try:
                    row = self._session_row(connection, raw_id)
                except sqlite3.Error:
                    row = None
                finally:
                    connection.close()

        cwd = str((row or {}).get("cwd") or "")
        model = str((row or {}).get("model") or "")
        started: Optional[datetime] = None
        updated: Optional[datetime] = None
        for record in head:
            if not cwd:
                value = record.get("cwd")
                if isinstance(value, str) and value.strip():
                    cwd = value.strip()
            if not model:
                candidate = _provider_data(record).get("requestModelId")
                if isinstance(candidate, str) and candidate.strip():
                    model = candidate.strip()
            if started is None:
                started = _record_timestamp(record)
            if cwd and model and started:
                break
        for record in reversed(tail):
            stamp = _record_timestamp(record)
            if stamp is not None:
                updated = stamp
                break

        row_started = parse_timestamp((row or {}).get("created_at"))
        row_updated = parse_timestamp((row or {}).get("updated_at"))
        started = row_started or started
        updated = row_updated or updated
        if updated is None:
            try:
                updated = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError:
                updated = started or datetime.now(tz=UTC)
        if started is None:
            started = updated

        title = ""
        if row:
            for key in ("custom_title", "title"):
                value = row.get(key)
                if isinstance(value, str) and value.strip() and not _is_generic(value):
                    title = one_line(value, 100)
                    break
        if not title:
            title = self._title_from(head)
        if not title:
            candidates = [prompt for prompt, _ in reversed(tail_prompts)]
            candidates += [prompt for prompt, _ in head_prompts]
            chosen = next(
                (prompt for prompt in candidates if prompt and not _is_generic(prompt)),
                "",
            )
            title = one_line(chosen, 100)
        if not title:
            title = one_line(last_prompt or first_prompt, 100) or raw_id

        try:
            size = path.stat().st_size
        except OSError:
            size = 0

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
            model=model,
            entrypoint="desktop",
            version="",
            size=size,
            variants="desktop",
            archived=self._archived(raw_id, row),
        )

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        for record in self._iter_records(summary.path):
            text = _prompt_from_record(record)
            if not text:
                continue
            yield UserPrompt(text=text, timestamp=_record_timestamp(record))

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

    def _load_todos(self, raw_id: str) -> List[Dict[str, Any]]:
        directory = self.home() / "tasks" / raw_id
        if not directory.is_dir():
            return []
        entries: List[Tuple[float, Dict[str, Any]]] = []
        for path in directory.glob("*.json"):
            try:
                data = load_json_object(path.read_bytes())
            except OSError:
                continue
            if data is None:
                continue
            entries.append((self._mtime(path), data))
        entries.sort(key=lambda item: item[0])
        todos: List[Dict[str, Any]] = []
        for _, data in entries[-MAX_TODOS:]:
            subject = one_line(data.get("subject") or data.get("content"), 200)
            if not subject:
                continue
            status = str(data.get("status") or "")
            if status == "done":
                status = "completed"
            todos.append({"subject": subject, "status": status})
        return todos

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
        initial_prompt = ""
        compact_summary = ""
        turn_count = 0

        def append_current() -> None:
            nonlocal current
            if current is None:
                return
            if current.user_text or current.assistant_texts or current.tools:
                exchanges.append(current)
            current = None

        for record in self._iter_records(summary.path):
            timestamp = _record_timestamp(record)
            if timestamp is not None:
                if started is None or timestamp < started:
                    started = timestamp
                if updated is None or timestamp > updated:
                    updated = timestamp

            if record.get("type") == "summary":
                if not initial_prompt:
                    initial_prompt = _initial_summary_prompt((record,))
                continue

            content = _content_text(record)
            if record.get("type") == "message" and _is_compaction(record, content):
                compact_summary = block_text(
                    _compaction_body(content), MAX_SUMMARY_CHARS
                )
                continue

            prompt = _prompt_from_record(record)
            if prompt:
                append_current()
                cleaned = block_text(prompt, MAX_PROMPT_CHARS)
                current = Exchange(user_text=cleaned, timestamp=timestamp)
                turn_count += 1
                last_prompt = cleaned
                if not first_prompt:
                    first_prompt = cleaned
                continue

            text = _assistant_text(record)
            if text.strip():
                if current is None:
                    current = Exchange(timestamp=timestamp)
                current.assistant_texts.append(block_text(text, MAX_ASSISTANT_CHARS))
                if len(current.assistant_texts) > 3:
                    current.assistant_texts = current.assistant_texts[-3:]
                continue

            if record.get("type") != "function_call":
                continue
            arguments = _arguments(record)
            name = str(record.get("name") or "tool")
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
            request_model = _provider_data(record).get("requestModelId")
            if isinstance(request_model, str) and request_model.strip():
                model = request_model.strip()

        append_current()

        if not first_prompt:
            first_prompt = (
                block_text(initial_prompt, MAX_PROMPT_CHARS) or last_prompt
            )
        summary.cwd = cwd or summary.cwd
        summary.model = model
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
            compact_summary=compact_summary,
            todos=self._load_todos(summary.session_id),
            exchanges=list(exchanges),
            edited_files=edited_files,
            tool_counts=dict(tool_counts.most_common()),
            recent_tools=list(recent_tools),
            turn_count=turn_count,
        )

    def contains(self, summary: SessionSummary, tokens: Sequence[str]) -> bool:
        return file_contains_all(summary.path, tokens)
