"""MiniMax Code (mcode) local runtime store.

Each session lives in a dated directory with a ``messages.jsonl`` transcript,
but ``sqlite/runtime-state.sqlite`` is authoritative for listing metadata, the
complete message history, todo events, and archive state. The transcript is
the session anchor and carries the latest compaction summary.
"""

from __future__ import annotations

import base64
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
    iter_file_records,
    iter_head_records,
    iter_tail_records,
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
MAX_TODOS = 400
HEAD_BYTES = 2_000_000
TAIL_BYTES = 512_000
MAX_EXCHANGES = 50
MAX_TOOLS_PER_EXCHANGE = 8
MAX_ASSISTANT_TEXTS = 3
MAX_RECENT_TOOLS = 20
MAX_EDITED_FILES = 30

REMINDER_RE = re.compile(r"<system-reminder\b[^>]*>.*?</system-reminder>", re.S)

PROMPT_SKIP_PREFIXES = (
    "<system-reminder",
    "<task-notification",
    "<user-prompt-submit-hook",
    "<local-command",
    "<questionnaire-response",
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

HUMAN_SOURCES = {"api", "code_review"}

EDIT_TOOLS = {
    "edit",
    "write",
    "multiedit",
    "notebookedit",
    "apply_patch",
}

TEXT_KEYS = (
    "file_path",
    "path",
    "command",
    "description",
    "pattern",
    "query",
    "name",
    "task_id",
    "prompt",
    "url",
)

FILE_KEYS = ("file_path", "notebook_path", "path", "target_file", "absolute_path")


def _clean_prompt(value: str) -> str:
    text = REMINDER_RE.sub("", value.strip())
    for tag in (
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
    lowered = text.casefold()
    if any(marker in lowered for marker in SYNTHETIC_MARKERS):
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
    if raw_id.startswith("mvs_"):
        return raw_id[len("mvs_") :]
    return raw_id


def _decode_folder_id(folder: str) -> str:
    marker = "-session_"
    index = folder.rfind(marker)
    if index < 0:
        return ""
    encoded = folder[index + len(marker) :]
    if not encoded:
        return ""
    padding = "=" * (-len(encoded) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            decoded = decoder(encoded + padding).decode("utf-8")
        except (ValueError, TypeError):
            continue
        if decoded.startswith("mvs_"):
            return decoded
    return ""


def _read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return load_json_object(data)


def _table_columns(connection: sqlite3.Connection, table: str) -> set:
    try:
        rows = connection.execute("PRAGMA table_info(%s)" % table).fetchall()
    except sqlite3.Error:
        return set()
    return {str(row[1]) for row in rows}


def _to_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _is_human_source(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip().casefold()
    if not text:
        return True
    return text in HUMAN_SOURCES


def _is_human_message(message: Dict[str, Any], source: Any = None) -> bool:
    if message.get("role") != "user":
        return False
    msg_type = message.get("msg_type")
    if msg_type is not None and msg_type != 1:
        return False
    if not _is_human_source(source if source is not None else message.get("source")):
        return False
    text = message.get("msg_content")
    if not isinstance(text, str):
        return False
    return _meaningful_prompt(text)


def _jsonl_content_text(message: Dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    texts: List[str] = []
    for part in content:
        if not isinstance(part, dict) or part.get("type") != "text":
            continue
        text = part.get("text")
        if isinstance(text, str):
            texts.append(text)
    return "\n".join(texts)


def _jsonl_prompt(message: Dict[str, Any]) -> str:
    if message.get("role") != "user":
        return ""
    text = _jsonl_content_text(message)
    if not text.strip():
        return ""
    span = message.get("canonicalTextRange")
    if isinstance(span, dict):
        start = _to_int(span.get("startOffset"))
        end = _to_int(span.get("endOffset"))
        if start is not None and end is not None and 0 <= start < end <= len(text):
            candidate = text[start:end].strip()
            if candidate:
                text = candidate
    if not _meaningful_prompt(text):
        return ""
    return _clean_prompt(text)


def _jsonl_timestamp(message: Dict[str, Any]) -> Optional[datetime]:
    return parse_timestamp(message.get("timestamp"))


def _tool_arguments(call: Dict[str, Any]) -> Dict[str, Any]:
    raw = call.get("tool_call_args")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        return load_json_object(raw) or {}
    return {}


def _tool_detail(arguments: Dict[str, Any]) -> str:
    for key in TEXT_KEYS:
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


def _normalize_todos(value: Any) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(value, list):
        return None
    todos: List[Dict[str, Any]] = []
    for item in value[-MAX_TODOS:]:
        if not isinstance(item, dict):
            continue
        subject = one_line(item.get("content") or item.get("subject"), 200)
        if not subject:
            continue
        status = str(item.get("status") or "")
        if status == "done":
            status = "completed"
        todos.append({"subject": subject, "status": status})
    return todos


def _todo_event(message: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    if message.get("msg_type") != 3:
        return None
    raw = message.get("msg_content")
    event = load_json_object(raw) if isinstance(raw, str) else None
    if not isinstance(event, dict) or event.get("eventType") != "todo_updated":
        return None
    return _normalize_todos(event.get("todos"))


class MiniMaxCodeAdapter(HarnessAdapter):
    """MiniMax Code CLI sessions: dated transcripts plus one runtime database."""

    name = "minimax-code"
    aliases = ("minimax-code", "minimax", "mcode")
    variants = "cli"
    store_hint = "~/.minimax/v2"
    home_env = "FMS_MINIMAX_CODE_HOME"
    app_db_env = "FMS_MINIMAX_CODE_APP_DB"

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".minimax" / "v2"

    def _db_path(self) -> Optional[Path]:
        override = os.environ.get(self.app_db_env)
        if override:
            path = Path(override).expanduser()
            return path if path.is_file() else None
        candidate = self.home() / "sqlite" / "runtime-state.sqlite"
        return candidate if candidate.is_file() else None

    def session_roots(self) -> List[Path]:
        return [self.home() / "sessions"]

    def owns(self, path: Path) -> bool:
        if path.name != "messages.jsonl":
            return False
        try:
            resolved = path.resolve()
        except OSError:
            return False
        for root in self.session_roots():
            try:
                resolved.relative_to(root.resolve())
                return True
            except (OSError, ValueError):
                continue
        return False

    @staticmethod
    def _connect(db: Path) -> sqlite3.Connection:
        db = db.expanduser()
        if not db.is_absolute():
            db = db.resolve()
        return sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=1.0)

    @staticmethod
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    @staticmethod
    def _path_for(root: Path, relative: Any) -> Optional[Path]:
        if not isinstance(relative, str) or not relative.strip():
            return None
        parts = Path(relative).parts
        if not parts or ".." in parts:
            return None
        return root.joinpath(*parts) / "messages.jsonl"

    def _raw_id(self, path: Path) -> str:
        manifest = _read_json_file(path.parent / "manifest.json") or {}
        candidate = manifest.get("sessionId")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        decoded = _decode_folder_id(path.parent.name)
        if decoded:
            return decoded
        raise ValueError("cannot determine minimax-code session id: %s" % path)

    def session_id_for(self, path: Path) -> str:
        return _display_id(self._raw_id(path))

    def find(self, prefix: str) -> List[SessionSummary]:
        wanted = prefix.strip().casefold()
        if wanted.startswith("mvs_"):
            wanted = wanted[len("mvs_") :]
        matches: List[SessionSummary] = []
        for path in self.iter_session_paths():
            try:
                session_id = self.session_id_for(path).casefold()
            except ValueError:
                continue
            if not session_id.startswith(wanted):
                continue
            try:
                matches.append(self.summarize(path))
            except (OSError, ValueError):
                continue
        return matches

    def iter_session_paths(self) -> Iterator[Path]:
        root = self.home() / "sessions"
        if not root.is_dir():
            return
        seen = set()
        db = self._db_path()
        if db is not None:
            try:
                connection = self._connect(db)
            except (OSError, sqlite3.Error, ValueError):
                connection = None
            if connection is not None:
                try:
                    columns = _table_columns(
                        connection, "local_runtime_sessions"
                    )
                    if "session_id" in columns:
                        clauses: List[str] = []
                        if "parent_session_id" in columns:
                            clauses.append("parent_session_id IS NULL")
                        if "session_kind" in columns:
                            clauses.append(
                                "session_kind IN ('conversation', 'task')"
                            )
                        if "visibility" in columns:
                            clauses.append(
                                "COALESCE(visibility, 'visible') != 'hidden'"
                            )
                        selected = ["session_id"]
                        if "history_relative_dir" in columns:
                            selected.append("history_relative_dir")
                        query = "SELECT %s FROM local_runtime_sessions" % (
                            ", ".join(selected)
                        )
                        if clauses:
                            query += " WHERE " + " AND ".join(clauses)
                        if "updated_at_ms" in columns:
                            query += " ORDER BY updated_at_ms DESC"
                        for row in connection.execute(query):
                            raw_id = str(row[0])
                            relative = row[1] if len(row) > 1 else ""
                            path = self._path_for(root, relative)
                            if path is None or not path.is_file():
                                continue
                            key = str(path)
                            if key in seen:
                                continue
                            seen.add(key)
                            yield path
                except sqlite3.Error:
                    pass
                finally:
                    connection.close()
        if seen:
            return
        paths = [path for path in root.rglob("messages.jsonl") if path.is_file()]
        paths.sort(key=self._mtime, reverse=True)
        yield from paths

    @staticmethod
    def _session_row(
        connection: sqlite3.Connection, raw_id: str
    ) -> Optional[Dict[str, Any]]:
        columns = _table_columns(connection, "local_runtime_sessions")
        if "session_id" not in columns:
            return None
        wanted = (
            "session_id",
            "record_json",
            "workspace_dir",
            "project_workspace_dir",
            "title",
            "created_at_ms",
            "updated_at_ms",
            "archived",
            "visibility",
            "status",
            "error_message",
            "error_code",
            "extra_data_json",
        )
        selected = [column for column in wanted if column in columns]
        row = connection.execute(
            "SELECT %s FROM local_runtime_sessions WHERE session_id = ?"
            % ", ".join(selected),
            (raw_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(selected, row))

    @staticmethod
    def _message_columns(connection: sqlite3.Connection) -> set:
        return _table_columns(connection, "local_runtime_message_rows")

    @staticmethod
    def _has_message_rows(connection: sqlite3.Connection, raw_id: str) -> bool:
        columns = MiniMaxCodeAdapter._message_columns(connection)
        if "session_id" not in columns:
            return False
        row = connection.execute(
            "SELECT 1 FROM local_runtime_message_rows WHERE session_id = ? LIMIT 1",
            (raw_id,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _max_message_ms(
        connection: sqlite3.Connection, raw_id: str
    ) -> Optional[int]:
        columns = MiniMaxCodeAdapter._message_columns(connection)
        if "session_id" not in columns or "created_at_ms" not in columns:
            return None
        row = connection.execute(
            "SELECT MAX(created_at_ms) FROM local_runtime_message_rows "
            "WHERE session_id = ?",
            (raw_id,),
        ).fetchone()
        if row is None:
            return None
        return _to_int(row[0])

    @staticmethod
    def _prompt_rows(
        connection: sqlite3.Connection, raw_id: str
    ) -> List[Tuple[str, Optional[datetime], Dict[str, Any]]]:
        columns = MiniMaxCodeAdapter._message_columns(connection)
        if "session_id" not in columns or "data_json" not in columns:
            return []
        selected = ["data_json"]
        if "created_at_ms" in columns:
            selected.append("created_at_ms")
        if "source" in columns:
            selected.append("source")
        query = (
            "SELECT %s FROM local_runtime_message_rows WHERE session_id = ?"
            % ", ".join(selected)
        )
        if "role" in columns:
            query += " AND role = 'user'"
        query += " ORDER BY "
        if "created_at_ms" in columns:
            query += "created_at_ms ASC, "
        query += "id ASC"
        prompts: List[Tuple[str, Optional[datetime], Dict[str, Any]]] = []
        for row in connection.execute(query, (raw_id,)):
            message = load_json_object(row[0])
            if message is None:
                continue
            created = (
                row[selected.index("created_at_ms")]
                if "created_at_ms" in selected
                else None
            )
            source = (
                row[selected.index("source")] if "source" in selected else None
            )
            if not _is_human_message(message, source):
                continue
            text = _clean_prompt(str(message.get("msg_content") or ""))
            if not text:
                continue
            prompts.append((text, parse_timestamp(created), message))
        return prompts

    @staticmethod
    def _extra_model(row: Dict[str, Any]) -> str:
        extra = load_json_object(row.get("extra_data_json")) or {}
        for key in ("effectiveModel", "effectiveModelVariant"):
            value = extra.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _row_archived(row: Dict[str, Any]) -> bool:
        archived = row.get("archived")
        if archived is True:
            return True
        number = _to_int(archived)
        if number is not None and number != 0:
            return True
        for key in ("visibility", "status"):
            value = row.get(key)
            if isinstance(value, str) and value.strip().casefold() in (
                "hidden",
                "archived",
                "deleted",
            ):
                return True
        return False

    @staticmethod
    def _later(
        current: Optional[datetime], candidate: Optional[datetime]
    ) -> Optional[datetime]:
        if candidate is None:
            return current
        if current is None or candidate > current:
            return candidate
        return current

    @staticmethod
    def _jsonl_prompts(
        records: Sequence[Dict[str, Any]]
    ) -> List[Tuple[str, Optional[datetime]]]:
        prompts: List[Tuple[str, Optional[datetime]]] = []
        for record in records:
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            text = _jsonl_prompt(message)
            if text:
                prompts.append((text, _jsonl_timestamp(message)))
        return prompts

    @staticmethod
    def _jsonl_model(records: Sequence[Dict[str, Any]]) -> str:
        for record in records:
            message = record.get("message")
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            value = message.get("model")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _jsonl_started(
        records: Sequence[Dict[str, Any]]
    ) -> Optional[datetime]:
        for record in records:
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            stamp = _jsonl_timestamp(message)
            if stamp is not None:
                return stamp
        return None

    @staticmethod
    def _jsonl_updated(
        records: Sequence[Dict[str, Any]]
    ) -> Optional[datetime]:
        for record in reversed(records):
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            stamp = _jsonl_timestamp(message)
            if stamp is not None:
                return stamp
        return None

    def _compaction_summary(self, path: Path) -> str:
        summary = ""
        if not path.is_file():
            return summary
        for record in iter_head_records(path, HEAD_BYTES, 50):
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            if message.get("role") != "compactionSummary":
                continue
            text = message.get("summary")
            if isinstance(text, str) and text.strip():
                summary = block_text(text, MAX_SUMMARY_CHARS)
        return summary

    def summarize(self, path: Path) -> SessionSummary:
        raw_id = self._raw_id(path)
        row: Optional[Dict[str, Any]] = None
        prompts: List[Tuple[str, Optional[datetime], Dict[str, Any]]] = []
        max_message_ms: Optional[int] = None
        db = self._db_path()
        connection: Optional[sqlite3.Connection] = None
        if db is not None:
            try:
                connection = self._connect(db)
            except (OSError, sqlite3.Error, ValueError):
                connection = None
        if connection is not None:
            try:
                row = self._session_row(connection, raw_id)
                prompts = self._prompt_rows(connection, raw_id)
                max_message_ms = self._max_message_ms(connection, raw_id)
            except sqlite3.Error:
                row = None
                prompts = []
            finally:
                connection.close()

        cwd = ""
        model = ""
        started: Optional[datetime] = None
        updated: Optional[datetime] = None
        title = ""
        archived = False
        if row is not None:
            cwd = str(
                row.get("workspace_dir")
                or row.get("project_workspace_dir")
                or ""
            )
            title = str(row.get("title") or "").strip()
            started = parse_timestamp(row.get("created_at_ms"))
            updated = parse_timestamp(row.get("updated_at_ms"))
            model = self._extra_model(row)
            archived = self._row_archived(row)
            record = load_json_object(row.get("record_json"))
            if record:
                if not cwd:
                    cwd = str(record.get("workspaceDir") or "")
                started = started or parse_timestamp(record.get("createdAtMs"))
                updated = updated or parse_timestamp(record.get("updatedAtMs"))
        updated = self._later(updated, parse_timestamp(max_message_ms))

        head: List[Dict[str, Any]] = []
        tail: List[Dict[str, Any]] = []
        head_prompts: List[Tuple[str, Optional[datetime]]] = []
        tail_prompts: List[Tuple[str, Optional[datetime]]] = []
        if not prompts and path.is_file():
            head = list(iter_head_records(path, HEAD_BYTES, PROMPT_HEAD_LIMIT))
            tail = iter_tail_records(path, TAIL_BYTES)
            head_prompts = self._jsonl_prompts(head)
            tail_prompts = self._jsonl_prompts(tail)
            if not model:
                model = self._jsonl_model(head) or self._jsonl_model(tail)
            started = started or self._jsonl_started(head)
            updated = self._later(updated, self._jsonl_updated(tail))

        manifest = _read_json_file(path.parent / "manifest.json") or {}
        started = started or parse_timestamp(manifest.get("createdAtMs"))
        updated = self._later(updated, parse_timestamp(manifest.get("updatedAtMs")))

        if prompts:
            first = prompts[0][0]
            last = prompts[-1][0]
            candidates = [text for text, _, _ in reversed(prompts)]
        else:
            first = head_prompts[0][0] if head_prompts else ""
            last = tail_prompts[-1][0] if tail_prompts else ""
            if not first and tail_prompts:
                first = tail_prompts[0][0]
            if not last and head_prompts:
                last = head_prompts[-1][0]
            candidates = [text for text, _ in reversed(tail_prompts)]
            candidates += [text for text, _ in head_prompts]

        if updated is None:
            try:
                updated = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError:
                updated = started or datetime.now(tz=UTC)
        if started is None:
            started = updated

        first_prompt = block_text(first, MAX_PROMPT_CHARS) if first else ""
        last_prompt = block_text(last, MAX_PROMPT_CHARS) if last else ""
        if not first_prompt:
            first_prompt = last_prompt
        if not last_prompt:
            last_prompt = first_prompt

        display_id = _display_id(raw_id)
        if not title or _is_generic(title):
            chosen = next(
                (
                    prompt
                    for prompt in candidates
                    if prompt and not _is_generic(prompt)
                ),
                "",
            )
            if chosen:
                title = one_line(chosen, 100)
        if not title:
            title = one_line(last_prompt or first_prompt, 100) or display_id

        try:
            size = path.stat().st_size
        except OSError:
            size = 0

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
            branch="",
            model=model,
            entrypoint="cli",
            version="",
            size=size,
            variants="cli",
            archived=archived,
        )

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        raw_id = self._raw_id(summary.path)
        db = self._db_path()
        if db is not None:
            connection: Optional[sqlite3.Connection] = None
            try:
                connection = self._connect(db)
            except (OSError, sqlite3.Error, ValueError):
                connection = None
            if connection is not None:
                try:
                    has_rows = self._has_message_rows(connection, raw_id)
                    prompts = (
                        self._prompt_rows(connection, raw_id) if has_rows else []
                    )
                finally:
                    connection.close()
                if has_rows:
                    for text, timestamp, _ in prompts:
                        yield UserPrompt(text=text, timestamp=timestamp)
                    return
        for record in iter_file_records(summary.path):
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            text = _jsonl_prompt(message)
            if not text:
                continue
            yield UserPrompt(text=text, timestamp=_jsonl_timestamp(message))

    @staticmethod
    def _append_text(exchange: Exchange, text: str) -> None:
        exchange.assistant_texts.append(block_text(text, MAX_ASSISTANT_CHARS))
        if len(exchange.assistant_texts) > MAX_ASSISTANT_TEXTS:
            exchange.assistant_texts = exchange.assistant_texts[
                -MAX_ASSISTANT_TEXTS:
            ]

    @staticmethod
    def _append_tool(
        exchange: Exchange,
        tool: ToolCall,
        tool_counts: Counter,
        recent_tools: Deque[ToolCall],
        edited: "OrderedDict[str, int]",
        arguments: Dict[str, Any],
        cwd: str,
    ) -> None:
        exchange.tools.append(tool)
        if len(exchange.tools) > MAX_TOOLS_PER_EXCHANGE:
            exchange.tools = exchange.tools[-MAX_TOOLS_PER_EXCHANGE:]
        tool_counts[tool.name] += 1
        recent_tools.append(tool)
        if tool.name.casefold() in EDIT_TOOLS:
            path = _file_path(arguments, cwd)
            if path:
                edited[path] = edited.pop(path, 0) + 1

    def _session_error(
        self, connection: sqlite3.Connection, raw_id: str
    ) -> str:
        columns = _table_columns(connection, "local_runtime_sessions")
        if "error_message" not in columns:
            return ""
        selected = ["error_message"]
        if "error_code" in columns:
            selected.append("error_code")
        row = connection.execute(
            "SELECT %s FROM local_runtime_sessions WHERE session_id = ?"
            % ", ".join(selected),
            (raw_id,),
        ).fetchone()
        if row is None:
            return ""
        message = row[0] if isinstance(row[0], str) else ""
        code = row[1] if len(row) > 1 else None
        message = message.strip()
        if message and code is not None:
            return one_line("%s (%s)" % (message, code), 300)
        if message:
            return one_line(message, 300)
        if code is not None:
            return one_line(str(code), 300)
        return ""

    def load(self, summary: SessionSummary) -> SessionDetail:
        detail: Optional[SessionDetail] = None
        raw_id = self._raw_id(summary.path)
        db = self._db_path()
        if db is not None:
            connection: Optional[sqlite3.Connection] = None
            try:
                connection = self._connect(db)
            except (OSError, sqlite3.Error, ValueError):
                connection = None
            if connection is not None:
                try:
                    if self._has_message_rows(connection, raw_id):
                        detail = self._load_from_db(
                            connection, raw_id, summary
                        )
                except sqlite3.Error:
                    detail = None
                finally:
                    connection.close()
        if detail is None:
            detail = self._load_from_jsonl(summary)
        if not detail.compact_summary:
            detail.compact_summary = self._compaction_summary(summary.path)
        return detail

    def _load_from_db(
        self,
        connection: sqlite3.Connection,
        raw_id: str,
        summary: SessionSummary,
    ) -> SessionDetail:
        exchanges: Deque[Exchange] = deque(maxlen=MAX_EXCHANGES)
        current: Optional[Exchange] = None
        compact_summary = ""
        todos: List[Dict[str, Any]] = []
        tool_counts: Counter = Counter()
        recent_tools: Deque[ToolCall] = deque(maxlen=MAX_RECENT_TOOLS)
        edited: "OrderedDict[str, int]" = OrderedDict()
        cwd = summary.cwd
        model = summary.model
        first_prompt = summary.first_prompt
        last_prompt = summary.last_prompt
        started = summary.started
        updated = summary.updated
        turn_count = 0
        error_text = self._session_error(connection, raw_id)

        def append_current() -> None:
            nonlocal current
            if current is None:
                return
            if current.user_text or current.assistant_texts or current.tools:
                exchanges.append(current)
            current = None

        query = (
            "SELECT role, created_at_ms, data_json, source "
            "FROM local_runtime_message_rows WHERE session_id = ? "
            "ORDER BY created_at_ms ASC, id ASC"
        )
        for column_role, created_at, data_json, source in connection.execute(
            query, (raw_id,)
        ):
            message = load_json_object(data_json) or {}
            timestamp = parse_timestamp(created_at)
            if timestamp is not None:
                if started is None or timestamp < started:
                    started = timestamp
                updated = self._later(updated, timestamp)

            role = message.get("role") or column_role
            if role == "user":
                if not _is_human_message(message, source):
                    continue
                text = block_text(
                    _clean_prompt(str(message.get("msg_content") or "")),
                    MAX_PROMPT_CHARS,
                )
                if not text:
                    continue
                append_current()
                current = Exchange(user_text=text, timestamp=timestamp)
                turn_count += 1
                last_prompt = text
                if not first_prompt:
                    first_prompt = text
                continue

            if role == "assistant":
                msg_type = message.get("msg_type")
                if msg_type is not None and msg_type not in (1, 2):
                    continue
                text = message.get("msg_content")
                if isinstance(text, str) and text.strip():
                    if current is None:
                        current = Exchange(timestamp=timestamp)
                    self._append_text(current, text)
                raw_calls = message.get("tool_calls")
                if isinstance(raw_calls, list):
                    for call in raw_calls:
                        if not isinstance(call, dict):
                            continue
                        name = str(call.get("tool_name") or "tool")
                        arguments = _tool_arguments(call)
                        tool = ToolCall(
                            name=name,
                            detail=_tool_detail(arguments),
                            timestamp=timestamp,
                        )
                        if current is None:
                            current = Exchange(timestamp=timestamp)
                        self._append_tool(
                            current,
                            tool,
                            tool_counts,
                            recent_tools,
                            edited,
                            arguments,
                            cwd,
                        )
                continue

            if role is None:
                event = _todo_event(message)
                if event is not None:
                    todos = event

        if error_text:
            if current is None:
                current = Exchange()
            self._append_text(current, "[API error] " + error_text)
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
            for path, count in list(edited.items())[-MAX_EDITED_FILES:]
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

    def _load_from_jsonl(self, summary: SessionSummary) -> SessionDetail:
        exchanges: Deque[Exchange] = deque(maxlen=MAX_EXCHANGES)
        current: Optional[Exchange] = None
        compact_summary = ""
        todos: List[Dict[str, Any]] = []
        tool_counts: Counter = Counter()
        recent_tools: Deque[ToolCall] = deque(maxlen=MAX_RECENT_TOOLS)
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

        for record in iter_file_records(summary.path):
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            timestamp = _jsonl_timestamp(message)
            if timestamp is not None:
                if started is None or timestamp < started:
                    started = timestamp
                updated = self._later(updated, timestamp)

            role = message.get("role")
            if role == "compactionSummary":
                text = message.get("summary")
                if isinstance(text, str) and text.strip():
                    compact_summary = block_text(text, MAX_SUMMARY_CHARS)
                continue

            if role == "user":
                text = _jsonl_prompt(message)
                if not text:
                    continue
                append_current()
                current = Exchange(
                    user_text=block_text(text, MAX_PROMPT_CHARS),
                    timestamp=timestamp,
                )
                turn_count += 1
                last_prompt = current.user_text
                if not first_prompt:
                    first_prompt = current.user_text
                continue

            if role != "assistant":
                continue

            value = message.get("model")
            if isinstance(value, str) and value.strip():
                model = value.strip()
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                kind = block.get("type")
                if kind == "text":
                    text = block.get("text")
                    if not isinstance(text, str) or not text.strip():
                        continue
                    if current is None:
                        current = Exchange(timestamp=timestamp)
                    self._append_text(current, text)
                    continue
                if kind != "toolCall":
                    continue
                name = str(block.get("name") or "tool")
                arguments = (
                    block.get("arguments")
                    if isinstance(block.get("arguments"), dict)
                    else {}
                )
                tool = ToolCall(
                    name=name,
                    detail=_tool_detail(arguments),
                    timestamp=timestamp,
                )
                if current is None:
                    current = Exchange(timestamp=timestamp)
                self._append_tool(
                    current,
                    tool,
                    tool_counts,
                    recent_tools,
                    edited,
                    arguments,
                    cwd,
                )
                if name.casefold() == "todowrite":
                    parsed = _normalize_todos(arguments.get("todos"))
                    if parsed is not None:
                        todos = parsed

        append_current()

        if not compact_summary:
            compact_summary = self._compaction_summary(summary.path)
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
            for path, count in list(edited.items())[-MAX_EDITED_FILES:]
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

    def contains(self, summary: SessionSummary, tokens: Sequence[str]) -> bool:
        remaining = {normalize_text(token) for token in tokens if token}
        remaining.discard("")
        if not remaining:
            return True
        raw_id = self._raw_id(summary.path)
        db = self._db_path()
        if db is not None:
            connection: Optional[sqlite3.Connection] = None
            try:
                connection = self._connect(db)
            except (OSError, sqlite3.Error, ValueError):
                connection = None
            if connection is not None:
                try:
                    columns = self._message_columns(connection)
                    if "session_id" in columns and "data_json" in columns:
                        for (data,) in connection.execute(
                            "SELECT data_json FROM local_runtime_message_rows "
                            "WHERE session_id = ?",
                            (raw_id,),
                        ):
                            text = normalize_text(data)
                            for token in tuple(remaining):
                                if token in text:
                                    remaining.discard(token)
                            if not remaining:
                                return True
                except sqlite3.Error:
                    pass
                finally:
                    connection.close()
        if remaining and summary.path.is_file():
            return file_contains_all(summary.path, remaining)
        return not remaining
