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
from .common import file_path, tool_detail
from .common import is_generic as _is_generic

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

EDIT_TOOLS = {
    "Edit",
    "Write",
    "MultiEdit",
    "NotebookEdit",
    "apply_patch",
}

TEXT_KEYS = (
    "command",
    "file_path",
    "path",
    "pattern",
    "description",
    "prompt",
    "skill",
    "url",
    "query",
)

FILE_KEYS = ("file_path", "notebook_path", "path", "target_file", "absolute_path")


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


def _display_id(raw_id: str) -> str:
    for prefix in ("session_", "sess_"):
        if raw_id.startswith(prefix):
            return raw_id[len(prefix) :]
    return raw_id


def _table_columns(connection: sqlite3.Connection, table: str) -> Set[str]:
    try:
        rows = connection.execute("PRAGMA table_info(%s)" % table).fetchall()
    except sqlite3.Error:
        return set()
    return {str(row[1]) for row in rows}


def _part_text(part: Dict[str, Any]) -> str:
    if part.get("type") != "text":
        return ""
    text = part.get("text")
    return text if isinstance(text, str) else ""


def _message_text(parts: Sequence[Dict[str, Any]]) -> str:
    return "\n".join(text for text in (_part_text(part) for part in parts) if text)


def _semantics(message: Dict[str, Any]) -> Dict[str, Any]:
    value = message.get("semantics")
    return value if isinstance(value, dict) else {}


def _is_human_message(message: Dict[str, Any], text: str) -> bool:
    if message.get("role") != "user":
        return False
    if message.get("synthetic") is True:
        return False
    semantics = _semantics(message)
    if semantics.get("transcriptVisibility") == "hidden":
        return False
    origin = semantics.get("origin")
    if origin is not None:
        if origin != "real_user":
            return False
        kind = semantics.get("kind")
        if kind and kind != "user_prompt":
            return False
    cleaned = _clean_prompt(text)
    if not _meaningful_prompt(cleaned):
        return False
    lowered = cleaned.casefold()
    if any(marker in lowered for marker in SYNTHETIC_MARKERS):
        return False
    return True


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


def _tool_detail(name: str, tool_input: Any) -> str:
    return tool_detail(tool_input, TEXT_KEYS)


def _file_path(tool_input: Any, cwd: str) -> str:
    return file_path(tool_input, cwd, FILE_KEYS)


def _context_info(message: Dict[str, Any]) -> Tuple[str, str]:
    snapshot = message.get("contextSnapshot")
    env = snapshot.get("envInfo") if isinstance(snapshot, dict) else None
    if not isinstance(env, dict):
        return "", ""
    cwd = env.get("cwd")
    branch = env.get("gitBranch")
    return (
        cwd if isinstance(cwd, str) else "",
        branch if isinstance(branch, str) else "",
    )


class ZCodeAdapter(HarnessAdapter):
    """ZCode desktop and its bundled CLI share one SQLite store and namespace."""

    name = "zcode"
    aliases = ("zcode", "z-code", "zai")
    variants = "desktop, cli"
    store_hint = "~/.zcode"
    home_env = "FMS_ZCODE_HOME"
    app_db_env = "FMS_ZCODE_APP_DB"
    _archive_cache: Optional[Tuple[Tuple[str, int, int], Set[str]]] = None

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".zcode"

    def _db_path(self) -> Path:
        return self.home() / "cli" / "db" / "db.sqlite"

    def _app_db_path(self) -> Optional[Path]:
        override = os.environ.get(self.app_db_env)
        if override:
            path = Path(override).expanduser()
            return path if path.is_file() else None
        candidate = self.home() / "v2" / "tasks-index.sqlite"
        return candidate if candidate.is_file() else None

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
        raise ValueError("not a zcode session source: %s" % path)

    def session_id_for(self, path: Path) -> str:
        return _display_id(self._raw_id(path))

    def find(self, prefix: str) -> List[SessionSummary]:
        wanted = prefix.strip().casefold()
        for name_prefix in ("session_", "sess_"):
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
            if "task_type" in columns:
                clauses.append("COALESCE(task_type, '') != 'subagent_child'")
            if "parent_id" in columns:
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
            "time_deleted",
        )
        selected = [column for column in wanted if column in columns]
        if "id" not in selected:
            return None
        row = connection.execute(
            "SELECT %s FROM session WHERE id = ?" % ", ".join(selected),
            (raw_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(selected, row))

    @staticmethod
    def _prompt_entries(
        connection: sqlite3.Connection,
        raw_id: str,
        descending: bool = False,
        limit: int = PROMPT_HEAD_LIMIT,
    ) -> List[Tuple[str, Optional[datetime], Dict[str, Any]]]:
        direction = "DESC" if descending else "ASC"
        query = (
            "SELECT m.id, m.time_created, m.data, p.data "
            "FROM message m JOIN part p ON p.message_id = m.id "
            "WHERE m.session_id = ? "
            "AND json_extract(m.data, '$.role') = 'user' "
            "AND json_extract(p.data, '$.type') = 'text' "
            "ORDER BY m.time_created {d}, m.id {d}, "
            "COALESCE(p.sequence, 0) {d}, p.id {d} LIMIT ?"
        ).format(d=direction)
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
                text = _part_text(part)
                if text:
                    texts.append(text)
        flush()
        return entries

    @staticmethod
    def _model_for(connection: sqlite3.Connection, raw_id: str) -> str:
        row = connection.execute(
            "SELECT "
            "(SELECT json_extract(data, '$.modelId') FROM message "
            " WHERE session_id = ? AND json_extract(data, '$.role') = 'assistant' "
            " AND json_extract(data, '$.modelId') IS NOT NULL "
            " ORDER BY time_created DESC LIMIT 1), "
            "(SELECT json_extract(data, '$.modelSelection.modelId') FROM message "
            " WHERE session_id = ? "
            " AND json_extract(data, '$.modelSelection.modelId') IS NOT NULL "
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
            raise ValueError("zcode store not found: %s" % db)
        try:
            connection = self._connect(db)
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise ValueError("cannot read zcode store: %s" % exc)
        try:
            row = self._session_row(connection, raw_id)
            if row is None:
                raise ValueError("zcode session not found: %s" % raw_id)
            head = self._prompt_entries(connection, raw_id, False, PROMPT_HEAD_LIMIT)
            tail = self._prompt_entries(connection, raw_id, True, PROMPT_TAIL_LIMIT)
            model = self._model_for(connection, raw_id)
        except sqlite3.Error as exc:
            raise ValueError("cannot read zcode store: %s" % exc)
        finally:
            connection.close()

        first_prompt = block_text(head[0][0], MAX_PROMPT_CHARS) if head else ""
        last_prompt = block_text(tail[0][0], MAX_PROMPT_CHARS) if tail else ""
        if not first_prompt:
            first_prompt = last_prompt
        if not last_prompt:
            last_prompt = first_prompt

        cwd = str(row.get("directory") or "")
        branch = ""
        for _, _, message in head:
            context_cwd, context_branch = _context_info(message)
            if not cwd and context_cwd:
                cwd = context_cwd
            if not branch and context_branch:
                branch = context_branch
            if cwd and branch:
                break

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

        entrypoint = "desktop" if raw_id.startswith("session_") else "cli"
        archived = bool(
            row.get("time_archived")
            or row.get("time_deleted")
            or raw_id in self._hidden_ids()
        )

        return SessionSummary(
            harness=self.name,
            session_id=display_id,
            path=path,
            cwd=cwd,
            updated=updated,
            title=title,
            first_prompt=first_prompt,
            last_prompt=last_prompt,
            started=started,
            branch=branch,
            model=model,
            entrypoint=entrypoint,
            version=str(row.get("version") or ""),
            size=0,
            variants=entrypoint,
            archived=archived,
        )

    def _hidden_ids(self) -> Set[str]:
        db = self._app_db_path()
        if db is None:
            return set()
        try:
            stat = db.stat()
        except OSError:
            return set()
        key = (str(db), stat.st_mtime_ns, stat.st_size)
        cached = self._archive_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        hidden = self._read_hidden_ids(db)
        self._archive_cache = (key, hidden)
        return hidden

    def _read_hidden_ids(self, db: Path) -> Set[str]:
        try:
            connection = self._connect(db)
        except (OSError, sqlite3.Error, ValueError):
            return set()
        try:
            columns = _table_columns(connection, "tasks")
            flags = [
                column
                for column in ("archived", "deleted", "cli_deleted")
                if column in columns
            ]
            if "task_id" not in columns or not flags:
                return set()
            query = "SELECT task_id FROM tasks WHERE " + " OR ".join(
                "%s = 1" % column for column in flags
            )
            return {
                str(row[0]) for row in connection.execute(query) if row and row[0]
            }
        except sqlite3.Error:
            return set()
        finally:
            connection.close()

    def _iter_message_groups(
        self, connection: sqlite3.Connection, raw_id: str
    ) -> Iterator[Tuple[Any, Dict[str, Any], List[Dict[str, Any]]]]:
        query = (
            "SELECT m.id, m.time_created, m.data, p.data "
            "FROM message m LEFT JOIN part p ON p.message_id = m.id "
            "WHERE m.session_id = ? "
            "ORDER BY m.time_created ASC, m.id ASC, "
            "COALESCE(p.sequence, 0) ASC, p.id ASC"
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
        try:
            rows = connection.execute(
                "SELECT content, status FROM todo WHERE session_id = ? "
                "ORDER BY position ASC",
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

    @staticmethod
    def _compaction_text(
        connection: sqlite3.Connection, message_id: str
    ) -> str:
        try:
            rows = connection.execute(
                "SELECT p.data FROM part p WHERE p.message_id = ? "
                "AND json_extract(p.data, '$.type') = 'text' "
                "ORDER BY COALESCE(p.sequence, 0) ASC, p.id ASC",
                (message_id,),
            ).fetchall()
        except sqlite3.Error:
            return ""
        texts = []
        for (raw_part,) in rows:
            part = load_json_object(raw_part)
            if part is not None:
                text = _part_text(part)
                if text:
                    texts.append(text)
        return "\n".join(texts)

    def resume_argv(self, summary: SessionSummary) -> Optional[List[str]]:
        return ["zcode", "--resume", self._raw_id(summary.path)]

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
        compaction_message_id = ""
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

            role = message.get("role")
            if role == "user":
                text = _message_text(parts)
                semantics = _semantics(message)
                if semantics.get("kind") == "compact_summary":
                    if text.strip():
                        compact_summary = block_text(text, MAX_SUMMARY_CHARS)
                    continue
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

            model_id = message.get("modelId")
            if isinstance(model_id, str) and model_id.strip():
                model = model_id.strip()

            for part in parts:
                part_type = part.get("type")
                if part_type == "text":
                    text = _part_text(part)
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
                    state = part.get("state")
                    tool_input = (
                        state.get("input") if isinstance(state, dict) else None
                    )
                    tool = ToolCall(
                        name=name,
                        detail=_tool_detail(name, tool_input),
                        timestamp=timestamp,
                    )
                    if current is None:
                        current = Exchange(timestamp=timestamp)
                    current.tools.append(tool)
                    if len(current.tools) > 8:
                        current.tools = current.tools[-8:]
                    tool_counts[name] += 1
                    recent_tools.append(tool)
                    if name in EDIT_TOOLS:
                        file_path = _file_path(tool_input, cwd)
                        if file_path:
                            count = edited.pop(file_path, 0) + 1
                            edited[file_path] = count
                    continue
                if part_type == "compaction":
                    candidate = part.get("summaryMessageId")
                    if isinstance(candidate, str) and candidate:
                        compaction_message_id = candidate

            error_text = _error_text(message)
            if error_text:
                if current is None:
                    current = Exchange(timestamp=timestamp)
                current.assistant_texts.append("[API error] " + error_text)
                if len(current.assistant_texts) > 3:
                    current.assistant_texts = current.assistant_texts[-3:]

        append_current()

        if not compact_summary and compaction_message_id:
            text = self._compaction_text(connection, compaction_message_id)
            if text.strip():
                compact_summary = block_text(text, MAX_SUMMARY_CHARS)

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
