"""Cursor (Anysphere) local agent sessions.

Cursor 3.x keeps one JSONL transcript per agent conversation under
``~/.cursor/projects/<project>/agent-transcripts/<session-id>/<session-id>.jsonl``.
The project directory name is a lossy encoding of the workspace folder, so the
real cwd is recovered from the desktop app's ``workspaceStorage`` metadata when
it is available.

The desktop app also maintains a conversation index at
``User/globalStorage/conversation-search.db``. It carries the conversation
title, the last-update timestamp, the git branch, and the archive flag, so the
adapter reads it read-only and never writes to it.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from collections import Counter, OrderedDict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Iterator, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from ..models import Exchange, SessionDetail, SessionSummary, ToolCall, UserPrompt
from ..util import (
    UTC,
    block_text,
    iter_file_records,
    one_line,
    parse_timestamp,
)
from .base import HarnessAdapter
from .common import file_path

MAX_PROMPT_CHARS = 4_000
MAX_SUMMARY_CHARS = 20_000
MAX_ASSISTANT_CHARS = 5_000

TRANSCRIPT_SUFFIXES = (".jsonl", ".json")

_USER_QUERY_RE = re.compile(r"<user_query>(.*?)</user_query>", re.S)
_TIMESTAMP_RE = re.compile(r"<timestamp>(.*?)</timestamp>", re.S)
_SUMMARY_REQUEST_RE = re.compile(r"<summary_request>", re.I)
_THINK_RE = re.compile(r"<(think|thinking)>.*?</\1>", re.S | re.I)
_NON_ALNUM_RE = re.compile(r"[^a-zA-Z0-9]")

_CURSOR_TS_RE = re.compile(
    r"^(?:[A-Za-z]+,\s*)?"
    r"(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4}),\s*"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<ampm>[AP]M)"
    r"(?:\s*\((?:UTC|GMT)(?P<sign>[+-])(?P<offhour>\d{1,2})"
    r"(?::(?P<offmin>\d{2}))?\))?$",
    re.I,
)

GENERIC_TITLES = {
    "general chat",
    "general chat conversation",
    "new chat",
    "new agent",
    "agent",
    "chat",
    "untitled",
    "untitled chat",
}

GENERIC_PROMPTS = {
    "continue",
    "go on",
    "keep going",
    "next",
    "ok",
    "okay",
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
    "edit_file",
    "editfile",
    "write",
    "write_file",
    "writefile",
    "create",
    "create_file",
    "createfile",
    "delete",
    "delete_file",
    "deletefile",
    "multiedit",
    "notebookedit",
    "apply_patch",
    "applypatch",
    "replace_in_file",
}

TODO_TOOLS = {
    "todo_write",
    "todowrite",
    "update_todos",
    "update_todo_list",
    "write_todos",
}

FILE_KEYS = (
    "file_path",
    "filePath",
    "path",
    "target_file",
    "absolute_path",
    "notebook_path",
    "file",
)

TOOL_DETAIL_KEYS = {
    "shell": ("command", "cmd"),
    "run_terminal_cmd": ("command", "cmd"),
    "run_terminal_command": ("command", "cmd"),
    "read_file": ("file_path", "path"),
    "read": ("file_path", "path"),
    "grep": ("pattern", "query"),
    "file_search": ("query", "pattern"),
    "glob_file_search": ("pattern", "query"),
    "semantic_search": ("query", "pattern"),
    "web_search": ("query", "pattern"),
    "list_dir": ("path", "relative_path"),
    "todo_write": (),
}

_INDEX_CACHE: Dict[str, Tuple[Tuple[int, int], Dict[str, Dict[str, Any]]]] = {}
_WORKSPACE_CACHE: Dict[str, Tuple[Tuple[int, int], Dict[str, str]]] = {}


def encode_project_dir(cwd: str) -> str:
    """Mirror Cursor's project-directory encoding of a workspace folder."""

    encoded = _NON_ALNUM_RE.sub("-", cwd)
    encoded = re.sub(r"-+", "-", encoded)
    return encoded.strip("-")


def _is_subagent_path(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    return "subagents" in parts[:-1]


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text)
    return "\n".join(parts)


def _tool_blocks(content: Any) -> Iterator[Tuple[str, Any]]:
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use":
            continue
        name = block.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        yield name.strip(), block.get("input")


def _extract_user_query(text: str) -> str:
    """Return the human request carried by a Cursor user message.

    Cursor wraps the typed request in ``<user_query>`` and keeps injected
    context in sibling tags, so only the wrapped request counts as a prompt.
    """

    if not text:
        return ""
    blocks: List[str] = []
    for match in _USER_QUERY_RE.findall(text):
        candidate = match.strip()
        if not candidate:
            continue
        if _SUMMARY_REQUEST_RE.search(candidate):
            continue
        blocks.append(candidate)
    if not blocks:
        return ""
    return "\n\n".join(blocks).strip()


def _extract_timestamp(text: str) -> Optional[datetime]:
    if not text:
        return None
    match = _TIMESTAMP_RE.search(text)
    if not match:
        return None
    return _parse_cursor_timestamp(match.group(1))


_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _parse_cursor_timestamp(raw: str) -> Optional[datetime]:
    text = (raw or "").strip()
    if not text:
        return None
    parsed = parse_timestamp(text)
    if parsed is not None:
        return parsed
    match = _CURSOR_TS_RE.match(text)
    if not match:
        return None
    month = _MONTHS.get(match.group("month").casefold())
    if month is None:
        return None
    try:
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        day = int(match.group("day"))
        year = int(match.group("year"))
    except (TypeError, ValueError):
        return None
    if match.group("ampm").upper() == "PM" and hour != 12:
        hour += 12
    elif match.group("ampm").upper() == "AM" and hour == 12:
        hour = 0
    try:
        naive = datetime(year, month, day, hour, minute)
    except ValueError:
        return None
    sign = match.group("sign")
    if sign:
        hours = int(match.group("offhour") or 0)
        minutes = int(match.group("offmin") or 0)
        delta = timedelta(hours=hours, minutes=minutes)
        if sign == "-":
            delta = -delta
        try:
            zone = timezone(delta)
        except ValueError:
            zone = UTC
    else:
        zone = UTC
    return naive.replace(tzinfo=zone).astimezone(UTC)


def _is_generic_prompt(value: str) -> bool:
    compact = re.sub(r"\s+", " ", value).strip().casefold()
    if not compact or len(compact) <= 1:
        return True
    if re.fullmatch(r"[\d\W_]+", compact):
        return True
    return compact in GENERIC_PROMPTS


def _choose_title(first_prompt: str, last_prompt: str) -> str:
    for candidate in (last_prompt, first_prompt):
        if candidate and not _is_generic_prompt(candidate):
            return one_line(candidate, 100)
    return one_line(last_prompt or first_prompt, 100)


def _tool_detail(name: str, arguments: Any) -> str:
    if not isinstance(arguments, dict):
        return ""
    for key in TOOL_DETAIL_KEYS.get(name.casefold(), ()):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
    for value in arguments.values():
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
    return ""


def _file_path(arguments: Any, cwd: str) -> str:
    return file_path(arguments, cwd, FILE_KEYS)


def _is_edit_tool(name: str) -> bool:
    lowered = name.casefold()
    if lowered in EDIT_TOOLS:
        return True
    return any(token in lowered for token in ("edit", "write", "create", "delete"))


def _normalize_todos(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("todos")
    if not isinstance(value, list):
        return []
    todos: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        subject = one_line(
            item.get("content") or item.get("subject") or item.get("title"),
            200,
        )
        if not subject:
            continue
        status = str(item.get("status") or "")
        if status == "done":
            status = "completed"
        todos.append({"subject": subject, "status": status})
    return todos


def _branch_from(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError, ValueError):
            return text
        return _branch_from(parsed)
    return ""


class CursorAdapter(HarnessAdapter):
    """Cursor desktop and CLI agent transcripts share one local store."""

    name = "cursor"
    aliases = ("cursor", "cursor-agent", "cursor-ide")
    variants = "desktop, cli"
    store_hint = "~/.cursor/projects"
    home_env = "FMS_CURSOR_HOME"
    app_db_env = "FMS_CURSOR_APP_DB"
    workspace_env = "FMS_CURSOR_WORKSPACE_STORAGE"

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".cursor"

    def session_roots(self) -> List[Path]:
        return [self.home() / "projects"]

    def user_dir(self) -> Path:
        override = os.environ.get(self.app_db_env)
        if override:
            return Path(override).expanduser().parent.parent
        if os.name == "nt":
            base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            return Path(base) / "Cursor" / "User"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "Cursor" / "User"
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        return Path(base) / "Cursor" / "User"

    def app_db(self) -> Path:
        override = os.environ.get(self.app_db_env)
        if override:
            return Path(override).expanduser()
        return self.user_dir() / "globalStorage" / "conversation-search.db"

    def workspace_storage(self) -> Path:
        override = os.environ.get(self.workspace_env)
        if override:
            return Path(override).expanduser()
        return self.user_dir() / "workspaceStorage"

    # -- conversation index -------------------------------------------------

    def conversation_index(self) -> Dict[str, Dict[str, Any]]:
        path = self.app_db()
        try:
            stat = path.stat()
        except OSError:
            return {}
        key = (int(stat.st_mtime), int(stat.st_size))
        cached = _INDEX_CACHE.get(str(path))
        if cached is not None and cached[0] == key:
            return cached[1]
        rows: Dict[str, Dict[str, Any]] = {}
        try:
            uri = "file:%s?mode=ro" % path
            connection = sqlite3.connect(uri, uri=True, timeout=2.0)
        except sqlite3.Error:
            _INDEX_CACHE[str(path)] = (key, rows)
            return rows
        try:
            cursor = connection.execute(
                "SELECT id, title, branches, updated_at, is_archived FROM conversations"
            )
            for row in cursor:
                rows[str(row[0])] = {
                    "title": row[1] if isinstance(row[1], str) else "",
                    "branches": row[2],
                    "updated_at": row[3],
                    "archived": bool(row[4]),
                }
        except sqlite3.Error:
            rows = {}
        finally:
            connection.close()
        _INDEX_CACHE[str(path)] = (key, rows)
        return rows

    def workspace_map(self) -> Dict[str, str]:
        """Map encoded project directory names back to real workspace folders."""

        root = self.workspace_storage()
        try:
            stat = root.stat()
        except OSError:
            return {}
        key = (int(stat.st_mtime), int(stat.st_size))
        cached = _WORKSPACE_CACHE.get(str(root))
        if cached is not None and cached[0] == key:
            return cached[1]
        mapping: Dict[str, str] = {}
        try:
            entries = sorted(root.iterdir())
        except OSError:
            entries = []
        for entry in entries:
            manifest = entry / "workspace.json"
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            for key_name in ("folder", "workspace"):
                raw = data.get(key_name)
                if not isinstance(raw, str) or not raw.strip():
                    continue
                path = _uri_to_path(raw)
                if not path:
                    continue
                mapping.setdefault(encode_project_dir(path), path)
        _WORKSPACE_CACHE[str(root)] = (key, mapping)
        return mapping

    def cwd_for(self, project_dir: str) -> str:
        if not project_dir:
            return ""
        return self.workspace_map().get(project_dir, "")

    # -- listing ------------------------------------------------------------

    def iter_session_paths(self) -> Iterator[Path]:
        root = self.home() / "projects"
        if not root.is_dir():
            return
        pending: List[Tuple[float, str, Path]] = []
        try:
            project_dirs = sorted(root.iterdir())
        except OSError:
            return
        for project_dir in project_dirs:
            if not project_dir.is_dir():
                continue
            transcripts = project_dir / "agent-transcripts"
            if not transcripts.is_dir():
                continue
            try:
                session_dirs = sorted(transcripts.iterdir())
            except OSError:
                continue
            for session_dir in session_dirs:
                if not session_dir.is_dir():
                    continue
                try:
                    files = sorted(session_dir.iterdir())
                except OSError:
                    continue
                for path in files:
                    if not path.is_file() or path.suffix not in TRANSCRIPT_SUFFIXES:
                        continue
                    if _is_subagent_path(path, transcripts):
                        continue
                    try:
                        mtime = path.stat().st_mtime
                    except OSError:
                        mtime = 0.0
                    pending.append((mtime, str(path), path))
        pending.sort(key=lambda item: (item[0], item[1]), reverse=True)
        for _, _, path in pending:
            yield path

    # -- transcript parsing -------------------------------------------------

    def _iter_transcript(self, path: Path) -> Iterator[Dict[str, Any]]:
        """Yield normalized transcript events for JSONL and JSON transcripts."""

        if path.suffix == ".json":
            for json_event in self._iter_json_transcript(path):
                yield json_event
            return
        for record in iter_file_records(path):
            event = self._event_from_record(record)
            if event is not None:
                yield event

    def _event_from_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        record_type = record.get("type")
        if record_type == "turn_ended":
            status = record.get("status")
            error = record.get("error")
            return {
                "kind": "turn_ended",
                "status": status if isinstance(status, str) else "",
                "error": error if isinstance(error, str) else "",
            }
        if record_type == "metadata":
            metadata = record.get("metadata")
            overview = ""
            if isinstance(metadata, dict):
                candidate = metadata.get("overview")
                if isinstance(candidate, str):
                    overview = candidate
            return {"kind": "metadata", "overview": overview}
        role = record.get("role")
        if role not in ("user", "assistant"):
            return None
        message = record.get("message")
        if not isinstance(message, dict):
            return None
        content = message.get("content")
        return {
            "kind": "message",
            "role": role,
            "text": _content_text(content),
            "tools": list(_tool_blocks(content)),
        }

    def _iter_json_transcript(self, path: Path) -> Iterator[Dict[str, Any]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return
        if not isinstance(data, dict):
            return
        messages = data.get("messages")
        if isinstance(messages, list):
            for message in messages:
                if not isinstance(message, dict):
                    continue
                role = message.get("role")
                if role not in ("user", "assistant"):
                    continue
                tools: List[Tuple[str, Any]] = []
                calls = message.get("toolCalls")
                if isinstance(calls, list):
                    for call in calls:
                        if not isinstance(call, dict):
                            continue
                        name = call.get("toolName")
                        if isinstance(name, str) and name.strip():
                            tools.append((name.strip(), call.get("args")))
                text = message.get("text")
                yield {
                    "kind": "message",
                    "role": role,
                    "text": text if isinstance(text, str) else "",
                    "tools": tools,
                }
        turn_ended = data.get("turnEnded")
        if isinstance(turn_ended, dict):
            error = turn_ended.get("error")
            yield {
                "kind": "turn_ended",
                "status": str(turn_ended.get("status") or ""),
                "error": error if isinstance(error, str) else "",
            }

    def _scan_prompts(self, path: Path) -> Tuple[str, str, Optional[datetime]]:
        """Return the first prompt, the last prompt, and the start time.

        One pass over the transcript keeps listing cheap: the same scan feeds
        the summary, so a session is not read three times.
        """

        first = ""
        last = ""
        started: Optional[datetime] = None
        for event in self._iter_transcript(path):
            if event.get("kind") != "message" or event.get("role") != "user":
                continue
            raw = event.get("text") or ""
            text = _extract_user_query(raw)
            if started is None:
                started = _extract_timestamp(raw)
            if not text:
                continue
            bounded = block_text(text, MAX_PROMPT_CHARS)
            if not first:
                first = bounded
            last = bounded
        return first, last, started

    # -- summary ------------------------------------------------------------

    def summarize(self, path: Path) -> SessionSummary:
        session_id = path.stem
        project_dir = ""
        transcripts = path.parent.parent
        if transcripts.name == "agent-transcripts":
            project_dir = transcripts.parent.name

        index = self.conversation_index()
        entry = index.get(session_id, {})

        first_prompt, last_prompt, started = self._scan_prompts(path)
        if not first_prompt:
            first_prompt = last_prompt
        if not last_prompt:
            last_prompt = first_prompt

        stored_title = entry.get("title") or ""
        stored_title = stored_title.strip()
        if stored_title and stored_title.casefold() not in GENERIC_TITLES:
            title = one_line(stored_title, 120)
        else:
            title = _choose_title(first_prompt, last_prompt)
            if not title and stored_title:
                title = one_line(stored_title, 120)
            if not title:
                title = session_id

        updated = parse_timestamp(entry.get("updated_at"))
        if updated is None:
            try:
                updated = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError:
                updated = datetime.now(tz=UTC)

        started = started or updated

        try:
            size = path.stat().st_size
        except OSError:
            size = 0

        return SessionSummary(
            harness=self.name,
            session_id=session_id,
            path=path,
            cwd=self.cwd_for(project_dir),
            updated=updated,
            title=title,
            first_prompt=first_prompt,
            last_prompt=last_prompt,
            started=started,
            branch=_branch_from(entry.get("branches")),
            model="",
            entrypoint="",
            version="",
            size=size,
            variants=self.variants,
            archived=bool(entry.get("archived")),
        )

    # -- prompts ------------------------------------------------------------

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        seen = set()
        for event in self._iter_transcript(summary.path):
            if event.get("kind") != "message" or event.get("role") != "user":
                continue
            raw = event.get("text") or ""
            text = _extract_user_query(raw)
            if not text:
                continue
            timestamp = _extract_timestamp(raw)
            key = (timestamp.isoformat() if timestamp else "", text)
            if key in seen:
                continue
            seen.add(key)
            yield UserPrompt(text=text, timestamp=timestamp)

    # -- digest -------------------------------------------------------------

    def load(self, summary: SessionSummary) -> SessionDetail:
        exchanges: Deque[Exchange] = deque(maxlen=50)
        current: Optional[Exchange] = None
        tool_counts: Counter = Counter()
        recent_tools: Deque[ToolCall] = deque(maxlen=20)
        edited: "OrderedDict[str, int]" = OrderedDict()
        cwd = summary.cwd
        compact_summary = ""
        todos: List[Dict[str, Any]] = []
        turn_count = 0
        last_prompt = summary.last_prompt
        first_prompt = summary.first_prompt

        def append_current() -> None:
            nonlocal current
            if current is None:
                return
            if current.user_text or current.assistant_texts or current.tools:
                exchanges.append(current)
            current = None

        for event in self._iter_transcript(summary.path):
            kind = event.get("kind")
            if kind == "metadata":
                overview = event.get("overview") or ""
                if overview.strip():
                    compact_summary = block_text(overview, MAX_SUMMARY_CHARS)
                continue
            if kind == "turn_ended":
                status = (event.get("status") or "").casefold()
                error = event.get("error") or ""
                if status == "error" and error:
                    if current is None:
                        current = Exchange()
                    current.assistant_texts.append(
                        block_text("Turn ended: error: %s" % error, MAX_ASSISTANT_CHARS)
                    )
                continue
            if kind != "message":
                continue

            role = event.get("role")
            if role == "user":
                raw = event.get("text") or ""
                text = _extract_user_query(raw)
                if not text:
                    continue
                append_current()
                cleaned = block_text(text, MAX_PROMPT_CHARS)
                current = Exchange(
                    user_text=cleaned,
                    timestamp=_extract_timestamp(raw),
                )
                turn_count += 1
                last_prompt = cleaned
                if not first_prompt:
                    first_prompt = cleaned
                continue

            text = event.get("text") or ""
            cleaned = _THINK_RE.sub("", text).strip()
            if cleaned:
                if current is None:
                    current = Exchange()
                current.assistant_texts.append(block_text(cleaned, MAX_ASSISTANT_CHARS))
                if len(current.assistant_texts) > 3:
                    current.assistant_texts = current.assistant_texts[-3:]
            for name, arguments in event.get("tools") or []:
                call = ToolCall(
                    name=name,
                    detail=_tool_detail(name, arguments),
                    timestamp=current.timestamp if current else None,
                )
                if current is None:
                    current = Exchange()
                current.tools.append(call)
                if len(current.tools) > 8:
                    current.tools = current.tools[-8:]
                tool_counts[name] += 1
                recent_tools.append(call)
                if name.casefold() in TODO_TOOLS and isinstance(arguments, dict):
                    candidate = _normalize_todos(arguments.get("todos"))
                    if candidate:
                        todos = candidate
                if _is_edit_tool(name):
                    path_value = _file_path(arguments, cwd)
                    if path_value:
                        edited[path_value] = edited.get(path_value, 0) + 1

        append_current()

        summary.cwd = cwd or summary.cwd
        summary.first_prompt = first_prompt
        summary.last_prompt = last_prompt
        if not summary.title:
            summary.title = _choose_title(first_prompt, last_prompt)

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


def _uri_to_path(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    if text.startswith("file://"):
        parsed = urlparse(text)
        path = unquote(parsed.path)
        if parsed.netloc and parsed.netloc not in ("", "localhost"):
            path = "//%s%s" % (parsed.netloc, path)
        return path
    if "://" in text:
        return ""
    return text
