"""Adapter for CodeArts Agent, the Huawei desktop coding agent.

CodeArts Agent keeps every session in one SQLite database built on the
opencode schema: ``session``, ``message``, ``part``, ``todo``, ``workspace``.
Sessions are rows, not files, so the adapter uses virtual
``opencode.db#<session id>`` source paths and a per-session row scan for
``--deep``.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections import Counter, OrderedDict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, Iterator, List, Optional, Sequence, Set, Tuple

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

MAX_PROMPT_CHARS = 4_000
MAX_SUMMARY_CHARS = 20_000
MAX_ASSISTANT_CHARS = 5_000
PROMPT_HEAD_LIMIT = 200
PROMPT_TAIL_LIMIT = 200
MAX_TODOS = 400

PROMPT_SKIP_PREFIXES = (
    "<system-reminder>",
    "<task-notification>",
    "<user-prompt-submit-hook>",
    "<local-command",
)

SYNTHETIC_MARKERS = (
    "the todowrite tool hasn't been used recently",
    "this session is being continued from a previous conversation",
)

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
    "edit",
    "write",
    "multiedit",
    "patch",
    "apply_patch",
    "notebookedit",
}

TEXT_KEYS = (
    "filePath",
    "file_path",
    "path",
    "command",
    "description",
    "pattern",
    "prompt",
    "skill",
    "url",
    "query",
)

FILE_KEYS = (
    "filePath",
    "file_path",
    "path",
    "target_file",
    "absolute_path",
    "notebook_path",
)


def _clean_prompt(value: str) -> str:
    text = value.strip()
    for tag in (
        "system-reminder",
        "task-notification",
        "command-message",
        "command-name",
        "user-prompt-submit-hook",
    ):
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
    if text.startswith("[Image #") and len(text) < 12:
        return False
    return True


def _is_generic(value: str) -> bool:
    compact = re.sub(r"\s+", " ", value).strip().casefold()
    if not compact or len(compact) <= 1:
        return True
    if re.fullmatch(r"[\d\W_]+", compact):
        return True
    return compact in GENERIC_PROMPTS


def _display_id(raw_id: str) -> str:
    for prefix in ("session_", "ses_"):
        if raw_id.startswith(prefix):
            return raw_id[len(prefix) :]
    return raw_id


def _table_columns(connection: sqlite3.Connection, table: str) -> Set[str]:
    try:
        rows = connection.execute("PRAGMA table_info(%s)" % table).fetchall()
    except sqlite3.Error:
        return set()
    return {str(row[1]) for row in rows}


def _text_part(part: Dict[str, Any]) -> str:
    """Return human-visible text from one part, skipping synthetic text."""

    if part.get("type") != "text":
        return ""
    if part.get("synthetic") is True:
        return ""
    text = part.get("text")
    return text if isinstance(text, str) else ""


def _message_text(parts: Sequence[Dict[str, Any]]) -> str:
    return "\n".join(text for text in (_text_part(part) for part in parts) if text)


def _is_human_message(message: Dict[str, Any], text: str) -> bool:
    if message.get("role") != "user":
        return False
    if message.get("synthetic") is True:
        return False
    cleaned = _clean_prompt(text)
    if not _meaningful_prompt(cleaned):
        return False
    lowered = cleaned.casefold()
    if any(marker in lowered for marker in SYNTHETIC_MARKERS):
        return False
    return True


def _is_compaction_message(message: Dict[str, Any]) -> bool:
    if message.get("role") != "assistant":
        return False
    if message.get("summary") is True:
        return True
    return message.get("agent") == "compaction" or message.get("mode") == "compaction"


def _error_text(message: Dict[str, Any]) -> str:
    error = message.get("error")
    if not isinstance(error, dict):
        return ""
    data = error.get("data")
    candidate = data.get("message") if isinstance(data, dict) else None
    if not isinstance(candidate, str) or not candidate.strip():
        candidate = error.get("message")
    if not isinstance(candidate, str) or not candidate.strip():
        candidate = error.get("name")
    if not isinstance(candidate, str) or not candidate.strip():
        return ""
    return one_line(candidate, 300)


def _tool_detail(tool_input: Any) -> str:
    if not isinstance(tool_input, dict):
        return ""
    for key in TEXT_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
    for value in tool_input.values():
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
    return ""


def _file_path(tool_input: Any, cwd: str) -> str:
    if not isinstance(tool_input, dict):
        return ""
    value = ""
    for key in FILE_KEYS:
        candidate = tool_input.get(key)
        if isinstance(candidate, str) and candidate.strip():
            value = candidate.strip()
            break
    if not value:
        return ""
    value = os.path.expanduser(value)
    if cwd and not os.path.isabs(value):
        value = os.path.join(cwd, value)
    return os.path.normpath(value)


def _tool_state(part: Dict[str, Any]) -> Dict[str, Any]:
    state = part.get("state")
    return state if isinstance(state, dict) else {}


class CodeArtsAgentAdapter(HarnessAdapter):
    """CodeArts Agent desktop stores every session in one opencode-schema database."""

    name = "codearts-agent"
    aliases = ("codearts-agent", "codearts", "codeartsdoer", "codearts-doer")
    variants = "desktop"
    store_hint = "~/.codeartsdoer"
    home_env = "FMS_CODEARTS_HOME"
    db_env = "FMS_CODEARTS_DB"

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".codeartsdoer"

    def _db_path(self) -> Path:
        override = os.environ.get(self.db_env)
        if override:
            return Path(override).expanduser()
        return self.home() / "codearts-data" / "opencode.db"

    def session_roots(self) -> List[Path]:
        # Sessions are rows in one database; no per-session file exists.
        return []

    def owns(self, path: Path) -> bool:
        text = str(path)
        base_text = text.split("#", 1)[0]
        try:
            base = Path(base_text).expanduser().resolve()
            db = self._db_path().expanduser().resolve()
        except OSError:
            return False
        return base == db

    def _db_for_path(self, path: Path) -> Path:
        if "#" in path.name:
            base = Path(str(path).split("#", 1)[0]).expanduser()
            if base.is_file():
                return base
        return self._db_path()

    @staticmethod
    def _connect(db: Path) -> sqlite3.Connection:
        db = db.expanduser()
        if not db.is_absolute():
            db = db.resolve()
        return sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=1.0)

    def _virtual_path(self, raw_id: str) -> Path:
        return Path(str(self._db_path()) + "#" + raw_id)

    @staticmethod
    def _raw_id(path: Path) -> str:
        name = path.name
        if "#" in name:
            candidate = name.split("#", 1)[1]
            if candidate:
                return candidate
        raise ValueError("not a codearts-agent session source: %s" % path)

    def session_id_for(self, path: Path) -> str:
        return _display_id(self._raw_id(path))

    def find(self, prefix: str) -> List[SessionSummary]:
        wanted = prefix.strip().casefold()
        for name_prefix in ("session_", "ses_"):
            if wanted.startswith(name_prefix):
                wanted = wanted[len(name_prefix) :]
                break
        matches: List[SessionSummary] = []
        for path in self.iter_session_paths():
            session_id = self.session_id_for(path).casefold()
            if not session_id.startswith(wanted):
                continue
            try:
                matches.append(self.summarize(path))
            except (OSError, ValueError):
                continue
        return matches

    def iter_session_paths(self) -> Iterator[Path]:
        db = self._db_path()
        if not db.is_file():
            return
        try:
            connection = self._connect(db)
        except (OSError, sqlite3.Error, ValueError):
            return
        try:
            columns = _table_columns(connection, "session")
            if "id" not in columns:
                return
            clauses: List[str] = []
            if "parent_id" in columns:
                # Child sessions are subagent runs, not resumable sessions.
                clauses.append("parent_id IS NULL")
            query = "SELECT id FROM session"
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY " + (
                "time_updated DESC" if "time_updated" in columns else "id"
            )
            for (raw_id,) in connection.execute(query):
                if raw_id:
                    yield self._virtual_path(str(raw_id))
        except sqlite3.Error:
            return
        finally:
            connection.close()

    @staticmethod
    def _session_row(
        connection: sqlite3.Connection, raw_id: str
    ) -> Optional[Dict[str, Any]]:
        columns = _table_columns(connection, "session")
        wanted = (
            "id",
            "directory",
            "title",
            "version",
            "time_created",
            "time_updated",
            "time_archived",
            "parent_id",
            "workspace_id",
        )
        selected = [column for column in wanted if column in columns]
        if "id" not in selected:
            return None
        select = ["s.%s" % column for column in selected]
        names = list(selected)
        join = ""
        workspace_columns = _table_columns(connection, "workspace")
        if "branch" in workspace_columns and "workspace_id" in columns:
            select.append("w.branch")
            names.append("branch")
            join = " LEFT JOIN workspace w ON w.id = s.workspace_id"
        row = connection.execute(
            "SELECT %s FROM session s%s WHERE s.id = ?" % (", ".join(select), join),
            (raw_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(names, row))

    @staticmethod
    def _part_order(connection: sqlite3.Connection, descending: bool = False) -> str:
        direction = "DESC" if descending else "ASC"
        columns = _table_columns(connection, "part")
        if "sequence" in columns:
            return (
                "m.time_created {d}, m.id {d}, "
                "COALESCE(p.sequence, 0) {d}, p.id {d}"
            ).format(d=direction)
        return "m.time_created {d}, m.id {d}, p.time_created {d}, p.id {d}".format(
            d=direction
        )

    @classmethod
    def _prompt_entries(
        cls,
        connection: sqlite3.Connection,
        raw_id: str,
        descending: bool = False,
        limit: int = PROMPT_HEAD_LIMIT,
    ) -> List[Tuple[str, Optional[datetime], Dict[str, Any]]]:
        query = (
            "SELECT m.id, m.time_created, m.data, p.data "
            "FROM message m JOIN part p ON p.message_id = m.id "
            "WHERE m.session_id = ? "
            "AND json_valid(m.data) AND json_valid(p.data) "
            "AND json_extract(m.data, '$.role') = 'user' "
            "AND json_extract(p.data, '$.type') = 'text' "
            "ORDER BY %s LIMIT ?" % cls._part_order(connection, descending)
        )
        entries: List[Tuple[str, Optional[datetime], Dict[str, Any]]] = []
        current_id: Optional[str] = None
        current_time: Optional[int] = None
        current_message: Dict[str, Any] = {}
        texts: List[str] = []

        def flush() -> None:
            if current_id is None:
                return
            ordered = list(reversed(texts)) if descending else texts
            text = "\n".join(ordered)
            if _is_human_message(current_message, text):
                entries.append(
                    (
                        _clean_prompt(text),
                        parse_timestamp(current_time),
                        current_message,
                    )
                )

        for message_id, time_created, raw_message, raw_part in connection.execute(
            query, (raw_id, limit)
        ):
            if message_id != current_id:
                flush()
                current_id = str(message_id)
                current_time = time_created
                current_message = load_json_object(raw_message) or {}
                texts = []
            part = load_json_object(raw_part)
            if part is not None:
                text = _text_part(part)
                if text:
                    texts.append(text)
        flush()
        return entries

    @staticmethod
    def _model_for(connection: sqlite3.Connection, raw_id: str) -> str:
        row = connection.execute(
            "SELECT "
            "(SELECT json_extract(data, '$.modelID') FROM message "
            " WHERE session_id = ? AND json_valid(data) "
            " AND json_extract(data, '$.role') = 'assistant' "
            " AND json_extract(data, '$.modelID') IS NOT NULL "
            " ORDER BY time_created DESC LIMIT 1), "
            "(SELECT json_extract(data, '$.model.modelID') FROM message "
            " WHERE session_id = ? AND json_valid(data) "
            " AND json_extract(data, '$.model.modelID') IS NOT NULL "
            " ORDER BY time_created ASC LIMIT 1)",
            (raw_id, raw_id),
        ).fetchone()
        if row:
            for value in row:
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    def summarize(self, path: Path) -> SessionSummary:
        raw_id = self._raw_id(path)
        db = self._db_for_path(path)
        if not db.is_file():
            raise ValueError("codearts-agent store not found: %s" % db)
        try:
            connection = self._connect(db)
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise ValueError("cannot read codearts-agent store: %s" % exc)
        try:
            row = self._session_row(connection, raw_id)
            if row is None:
                raise ValueError("codearts-agent session not found: %s" % raw_id)
            head = self._prompt_entries(connection, raw_id, False, PROMPT_HEAD_LIMIT)
            tail = self._prompt_entries(connection, raw_id, True, PROMPT_TAIL_LIMIT)
            model = self._model_for(connection, raw_id)
        except sqlite3.Error as exc:
            raise ValueError("cannot read codearts-agent store: %s" % exc)
        finally:
            connection.close()

        first_prompt = block_text(head[0][0], MAX_PROMPT_CHARS) if head else ""
        last_prompt = block_text(tail[0][0], MAX_PROMPT_CHARS) if tail else ""
        if not first_prompt:
            first_prompt = last_prompt
        if not last_prompt:
            last_prompt = first_prompt

        started = parse_timestamp(row.get("time_created"))
        updated = parse_timestamp(row.get("time_updated"))
        if updated is None:
            try:
                updated = datetime.fromtimestamp(db.stat().st_mtime, tz=UTC)
            except OSError:
                updated = started or datetime.now(tz=UTC)
        if started is None:
            started = updated

        display_id = _display_id(raw_id)
        title = str(row.get("title") or "").strip()
        if not title or _is_generic(title):
            candidates = [entry[0] for entry in tail] + [entry[0] for entry in head]
            chosen = next(
                (prompt for prompt in candidates if prompt and not _is_generic(prompt)),
                "",
            )
            if chosen:
                title = one_line(chosen, 100)
        if not title:
            title = one_line(last_prompt or first_prompt, 100) or display_id

        return SessionSummary(
            harness=self.name,
            session_id=display_id,
            path=path,
            cwd=str(row.get("directory") or ""),
            updated=updated,
            title=title,
            first_prompt=first_prompt,
            last_prompt=last_prompt,
            started=started,
            branch=str(row.get("branch") or ""),
            model=model,
            entrypoint="desktop",
            version=str(row.get("version") or ""),
            size=0,
            variants="desktop",
            archived=bool(row.get("time_archived")),
        )

    def _iter_message_groups(
        self, connection: sqlite3.Connection, raw_id: str
    ) -> Iterator[Tuple[Any, Dict[str, Any], List[Dict[str, Any]]]]:
        query = (
            "SELECT m.id, m.time_created, m.data, p.data "
            "FROM message m LEFT JOIN part p ON p.message_id = m.id "
            "WHERE m.session_id = ? "
            "ORDER BY %s" % self._part_order(connection, False)
        )
        current_id: Optional[str] = None
        current_time: Any = None
        current_message: Dict[str, Any] = {}
        parts: List[Dict[str, Any]] = []
        for message_id, time_created, raw_message, raw_part in connection.execute(
            query, (raw_id,)
        ):
            if message_id != current_id:
                if current_id is not None:
                    yield current_time, current_message, parts
                current_id = str(message_id)
                current_time = time_created
                current_message = load_json_object(raw_message) or {}
                parts = []
            part = load_json_object(raw_part)
            if part is not None:
                parts.append(part)
        if current_id is not None:
            yield current_time, current_message, parts

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        raw_id = self._raw_id(summary.path)
        db = self._db_for_path(summary.path)
        if not db.is_file():
            return
        try:
            connection = self._connect(db)
        except (OSError, sqlite3.Error, ValueError):
            return
        try:
            for time_created, message, parts in self._iter_message_groups(
                connection, raw_id
            ):
                text = _message_text(parts)
                if not _is_human_message(message, text):
                    continue
                yield UserPrompt(
                    text=_clean_prompt(text),
                    timestamp=parse_timestamp(time_created),
                )
        except sqlite3.Error:
            return
        finally:
            connection.close()

    @staticmethod
    def _load_todos(
        connection: sqlite3.Connection, raw_id: str
    ) -> List[Dict[str, Any]]:
        columns = _table_columns(connection, "todo")
        if "content" not in columns or "status" not in columns:
            return []
        order = "position" if "position" in columns else "rowid"
        try:
            rows = connection.execute(
                "SELECT content, status FROM todo WHERE session_id = ? "
                "ORDER BY %s ASC" % order,
                (raw_id,),
            ).fetchall()
        except sqlite3.Error:
            return []
        todos: List[Dict[str, Any]] = []
        for content, status in rows[-MAX_TODOS:]:
            subject = one_line(content, 200)
            if not subject:
                continue
            normalized = str(status or "")
            if normalized == "done":
                normalized = "completed"
            todos.append({"subject": subject, "status": normalized})
        return todos

    def load(self, summary: SessionSummary) -> SessionDetail:
        raw_id = self._raw_id(summary.path)
        db = self._db_for_path(summary.path)
        if not db.is_file():
            return SessionDetail(summary=summary)
        try:
            connection = self._connect(db)
        except (OSError, sqlite3.Error, ValueError):
            return SessionDetail(summary=summary)
        try:
            detail = self._load_from(connection, raw_id, summary)
        except sqlite3.Error:
            detail = SessionDetail(summary=summary)
        finally:
            connection.close()
        return detail

    def _load_from(
        self,
        connection: sqlite3.Connection,
        raw_id: str,
        summary: SessionSummary,
    ) -> SessionDetail:
        exchanges: Deque[Exchange] = deque(maxlen=50)
        current: Optional[Exchange] = None
        compact_summary = ""
        tool_counts: Counter = Counter()
        recent_tools: Deque[ToolCall] = deque(maxlen=20)
        edited: "OrderedDict[str, int]" = OrderedDict()
        cwd = summary.cwd
        model = summary.model
        first_prompt = summary.first_prompt
        last_prompt = summary.last_prompt
        started = summary.started
        updated = summary.updated
        turn_count = 0

        def append_current() -> None:
            nonlocal current
            if current is None:
                return
            if current.user_text or current.assistant_texts or current.tools:
                exchanges.append(current)
            current = None

        for time_created, message, parts in self._iter_message_groups(
            connection, raw_id
        ):
            timestamp = parse_timestamp(time_created)
            if timestamp is not None:
                if started is None or timestamp < started:
                    started = timestamp
                if updated is None or timestamp > updated:
                    updated = timestamp

            if _is_compaction_message(message):
                text = _message_text(parts)
                if text.strip():
                    compact_summary = block_text(text, MAX_SUMMARY_CHARS)
                continue

            role = message.get("role")
            if role == "user":
                text = _message_text(parts)
                if not _is_human_message(message, text):
                    continue
                append_current()
                cleaned = block_text(_clean_prompt(text), MAX_PROMPT_CHARS)
                current = Exchange(user_text=cleaned, timestamp=timestamp)
                turn_count += 1
                last_prompt = cleaned
                if not first_prompt:
                    first_prompt = cleaned
                continue

            if role != "assistant":
                continue

            model_id = message.get("modelID")
            if isinstance(model_id, str) and model_id.strip():
                model = model_id.strip()

            for part in parts:
                part_type = part.get("type")
                if part_type == "text":
                    text = _text_part(part)
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
                if part_type == "tool":
                    name = str(part.get("tool") or "tool")
                    tool_input = _tool_state(part).get("input")
                    tool = ToolCall(
                        name=name,
                        detail=_tool_detail(tool_input),
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
                        file_path = _file_path(tool_input, cwd)
                        if file_path:
                            edited[file_path] = edited.pop(file_path, 0) + 1
                    continue

            error_text = _error_text(message)
            if error_text:
                if current is None:
                    current = Exchange(timestamp=timestamp)
                current.assistant_texts.append("[API error] " + error_text)
                if len(current.assistant_texts) > 3:
                    current.assistant_texts = current.assistant_texts[-3:]

        append_current()

        if not first_prompt:
            first_prompt = last_prompt
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
            todos=self._load_todos(connection, raw_id),
            exchanges=list(exchanges),
            edited_files=edited_files,
            tool_counts=dict(tool_counts.most_common()),
            recent_tools=list(recent_tools),
            turn_count=turn_count,
        )

    def contains(self, summary: SessionSummary, tokens: Sequence[str]) -> bool:
        remaining = {normalize_text(token) for token in tokens if token}
        remaining.discard("")
        if not remaining:
            return True
        raw_id = self._raw_id(summary.path)
        db = self._db_for_path(summary.path)
        if not db.is_file():
            return False
        try:
            connection = self._connect(db)
        except (OSError, sqlite3.Error, ValueError):
            return False
        try:
            for query in (
                "SELECT data FROM message WHERE session_id = ?",
                "SELECT data FROM part WHERE session_id = ?",
            ):
                for (data,) in connection.execute(query, (raw_id,)):
                    text = normalize_text(data)
                    for token in tuple(remaining):
                        if token in text:
                            remaining.discard(token)
                    if not remaining:
                        return True
        except sqlite3.Error:
            return False
        finally:
            connection.close()
        return not remaining
