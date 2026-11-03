from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from collections import Counter, OrderedDict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, Iterator, List, Optional, Set, Tuple

from ..models import Exchange, SessionDetail, SessionSummary, ToolCall, UserPrompt
from ..util import (
    UTC,
    block_text,
    iter_file_records,
    iter_head_records,
    iter_tail_records,
    one_line,
    parse_timestamp,
)
from .base import HarnessAdapter
from .common import (
    choose_title as _choose_title,
)
from .common import (
    file_path,
)

HEAD_BYTES = 2_000_000
HEAD_RECORDS = 200
TAIL_BYTES = 512_000
TAIL_BYTES_EXTENDED = 4_000_000
MAX_PROMPT_CHARS = 4_000
MAX_SUMMARY_CHARS = 20_000

PROMPT_SKIP_PREFIXES = (
    "<system-reminder>",
    "<task-notification>",
    "<user-prompt-submit-hook>",
    "<local-command",
)

CONTINUATION_PREFIXES = (
    "this session is being continued from a previous conversation",
    "the conversation is being continued",
)

EDIT_TOOLS = {
    "Edit",
    "Write",
    "MultiEdit",
    "NotebookEdit",
    "apply_patch",
    "StrReplace",
}

TEXT_KEYS = (
    "description",
    "command",
    "query",
    "file_path",
    "path",
    "pattern",
    "prompt",
    "subject",
    "skill",
    "url",
)

FILE_KEYS = ("file_path", "notebook_path", "path", "target_file", "absolute_path")

ARCHIVE_QUERY = (
    "SELECT session_id FROM chat_sessions "
    "WHERE archived = 1 OR deleted_at IS NOT NULL"
)


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
    return "\n".join(parts)


def _record_text(record: Dict[str, Any]) -> str:
    human = record.get("humanInput")
    if isinstance(human, dict):
        text = human.get("text")
        if isinstance(text, str) and text.strip():
            return text
    elif isinstance(human, str) and human.strip():
        return human
    message = record.get("message")
    if isinstance(message, dict):
        return _extract_text(message.get("content"))
    return ""


def _compact_summary_text(record: Dict[str, Any]) -> str:
    message = record.get("message")
    if isinstance(message, dict):
        text = _extract_text(message.get("content"))
        if text.strip():
            return text
    content = record.get("content")
    if isinstance(content, str):
        return content
    return ""


def _clean_prompt(value: str) -> str:
    text = value.strip()
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S)
    text = re.sub(r"<task-notification>.*?</task-notification>", "", text, flags=re.S)
    text = re.sub(r"<command-message>.*?</command-message>", "", text, flags=re.S)
    text = re.sub(r"<command-name>.*?</command-name>", "", text, flags=re.S)
    text = re.sub(r"<user-prompt-submit-hook>.*?</user-prompt-submit-hook>", "", text, flags=re.S)
    return text.strip()


def _meaningful_prompt(value: str) -> bool:
    text = _clean_prompt(value)
    if not text:
        return False
    lowered = text.casefold()
    if lowered.startswith(PROMPT_SKIP_PREFIXES):
        return False
    if lowered.startswith(CONTINUATION_PREFIXES):
        return False
    if re.fullmatch(r"/\S+", text):
        return False
    if text.startswith("[Image #") and len(text) < 12:
        return False
    return True


def _is_tool_result(record: Dict[str, Any]) -> bool:
    if "toolUseResult" in record:
        return True
    message = record.get("message")
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if not isinstance(content, list) or not content:
        return False
    return all(isinstance(block, dict) and block.get("type") == "tool_result" for block in content)


def _tool_detail(name: str, tool_input: Any) -> str:
    if not isinstance(tool_input, dict):
        return ""
    if name == "mcp_call":
        tool_name = tool_input.get("toolName")
        detail_parts: List[str] = []
        if isinstance(tool_name, str) and tool_name.strip():
            detail_parts.append(tool_name.strip())
        arguments = tool_input.get("arguments")
        if isinstance(arguments, dict):
            for key in ("query", "path", "url", "command", "toolName"):
                value = arguments.get(key)
                if isinstance(value, str) and value.strip():
                    detail_parts.append(one_line(value, 100))
                    break
        return one_line(" ".join(detail_parts), 160)
    for key in TEXT_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
    for value in tool_input.values():
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
    return ""


def _file_path(tool_input: Any, cwd: str) -> str:
    return file_path(tool_input, cwd, FILE_KEYS)


class QoderFamilyAdapter(HarnessAdapter):
    """Qoder CN and international Qoder share a transcript schema but not a store."""

    default_home_dir = ""
    home_env = ""
    app_bundle_dirs: Tuple[str, ...] = ()
    app_db_env = ""
    _archive_cache: Optional[Tuple[Tuple[str, int, int], Set[str]]] = None

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / self.default_home_dir

    def _app_support_dirs(self) -> List[Path]:
        if sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        elif os.name == "nt":
            appdata = os.environ.get("APPDATA")
            base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        else:
            xdg = os.environ.get("XDG_CONFIG_HOME")
            base = Path(xdg) if xdg else Path.home() / ".config"
        return [base / name for name in self.app_bundle_dirs]

    def _app_db_path(self) -> Optional[Path]:
        override = os.environ.get(self.app_db_env)
        if override:
            path = Path(override).expanduser()
            return path if path.is_file() else None
        for directory in self._app_support_dirs():
            candidate = directory / "main.sqlite"
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _read_archived_ids(db: Path) -> Set[str]:
        try:
            uri = db.as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=1.0)
        except (OSError, sqlite3.Error, ValueError):
            return set()
        try:
            rows = connection.execute(ARCHIVE_QUERY).fetchall()
        except sqlite3.Error:
            return set()
        finally:
            connection.close()
        return {str(row[0]) for row in rows if row and row[0]}

    def _archived_ids(self) -> Set[str]:
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
        archived = self._read_archived_ids(db)
        self._archive_cache = (key, archived)
        return archived

    def _is_archived(self, session_id: str) -> bool:
        return session_id in self._archived_ids()

    def iter_session_paths(self) -> Iterator[Path]:
        root = self.home() / "projects"
        if not root.is_dir():
            return
        paths = [path for path in root.glob("*/*.jsonl") if path.is_file()]
        paths.sort(key=self._mtime, reverse=True)
        for path in paths:
            yield path

    @staticmethod
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def summarize(self, path: Path) -> SessionSummary:
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        cwd = ""
        branch = ""
        model = ""
        entrypoint = ""
        version = ""
        started: Optional[datetime] = None
        first_prompt = ""

        for record in iter_head_records(path, HEAD_BYTES, HEAD_RECORDS):
            record_type = record.get("type")
            timestamp = parse_timestamp(record.get("timestamp"))
            if timestamp is not None and started is None:
                started = timestamp
            if record_type == "workspace-directories" and not cwd:
                directories = record.get("directories")
                if isinstance(directories, list) and directories and isinstance(directories[0], str):
                    cwd = directories[0]
            if record_type == "runtime-config" and not model:
                model = str(record.get("model") or "")
            if not cwd and isinstance(record.get("cwd"), str):
                cwd = record["cwd"]
            if not branch and isinstance(record.get("gitBranch"), str):
                branch = record["gitBranch"]
            if not entrypoint and isinstance(record.get("entrypoint"), str):
                entrypoint = record["entrypoint"]
            if not version and isinstance(record.get("version"), str):
                version = record["version"]
            if (
                record_type != "user"
                or record.get("isCompactSummary")
                or record.get("isMeta")
                or record.get("isSidechain")
                or _is_tool_result(record)
            ):
                continue
            text = _record_text(record)
            if _meaningful_prompt(text):
                first_prompt = block_text(_clean_prompt(text), MAX_PROMPT_CHARS)
                break

        tail_records = iter_tail_records(path, TAIL_BYTES)
        if not any(record.get("type") == "last-prompt" for record in tail_records):
            tail_records = iter_tail_records(path, TAIL_BYTES_EXTENDED)

        last_prompt = ""
        last_human = ""
        updated: Optional[datetime] = None
        for record in tail_records:
            timestamp = parse_timestamp(record.get("timestamp"))
            if timestamp is not None and (updated is None or timestamp > updated):
                updated = timestamp
            if isinstance(record.get("gitBranch"), str):
                branch = record["gitBranch"]
            if isinstance(record.get("entrypoint"), str):
                entrypoint = record["entrypoint"]
            if isinstance(record.get("version"), str):
                version = record["version"]
            if record.get("type") == "last-prompt":
                candidate = record.get("lastPrompt")
                if isinstance(candidate, str) and _meaningful_prompt(candidate):
                    last_prompt = block_text(_clean_prompt(candidate), MAX_PROMPT_CHARS)
            if (
                record.get("type") != "user"
                or record.get("isCompactSummary")
                or record.get("isMeta")
                or record.get("isSidechain")
                or _is_tool_result(record)
            ):
                continue
            text = _record_text(record)
            if _meaningful_prompt(text):
                last_human = block_text(_clean_prompt(text), MAX_PROMPT_CHARS)

        if not last_prompt:
            last_prompt = last_human
        if not first_prompt:
            first_prompt = last_human or last_prompt
        if updated is None:
            updated = mtime

        return SessionSummary(
            harness=self.name,
            session_id=path.stem,
            path=path,
            cwd=cwd,
            updated=updated,
            title=_choose_title(first_prompt, last_prompt) or path.stem,
            first_prompt=first_prompt,
            last_prompt=last_prompt,
            started=started,
            branch=branch,
            model=model,
            entrypoint=entrypoint,
            version=version,
            size=stat.st_size,
            variants=self.variants,
            archived=self._is_archived(path.stem),
        )

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        for record in iter_file_records(summary.path):
            if record.get("isSidechain"):
                continue
            if record.get("type") != "user":
                continue
            if (
                record.get("isCompactSummary")
                or record.get("isMeta")
                or _is_tool_result(record)
            ):
                continue
            text = _record_text(record)
            if not _meaningful_prompt(text):
                continue
            yield UserPrompt(
                text=_clean_prompt(text),
                timestamp=parse_timestamp(record.get("timestamp")),
            )

    def load(self, summary: SessionSummary) -> SessionDetail:
        exchanges: Deque[Exchange] = deque(maxlen=50)
        current: Optional[Exchange] = None
        compact_summary = ""
        tool_counts: Counter = Counter()
        recent_tools: Deque[ToolCall] = deque(maxlen=20)
        edited: "OrderedDict[str, int]" = OrderedDict()
        cwd = summary.cwd
        branch = summary.branch
        model = summary.model
        entrypoint = summary.entrypoint
        version = summary.version
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
            if record.get("isSidechain"):
                continue
            record_type = record.get("type")
            timestamp = parse_timestamp(record.get("timestamp"))
            if timestamp is not None:
                if started is None or timestamp < started:
                    started = timestamp
                if updated is None or timestamp > updated:
                    updated = timestamp
            if isinstance(record.get("cwd"), str) and record["cwd"]:
                cwd = record["cwd"]
            if isinstance(record.get("gitBranch"), str):
                branch = record["gitBranch"]
            if isinstance(record.get("entrypoint"), str):
                entrypoint = record["entrypoint"]
            if isinstance(record.get("version"), str):
                version = record["version"]

            if record_type == "user":
                if record.get("isCompactSummary"):
                    text = _compact_summary_text(record)
                    if text.strip() and not text.strip().startswith("Conversation compacted"):
                        compact_summary = block_text(text, MAX_SUMMARY_CHARS)
                    continue
                if record.get("isMeta") or _is_tool_result(record):
                    continue
                text = _record_text(record)
                if not _meaningful_prompt(text):
                    continue
                append_current()
                cleaned = block_text(_clean_prompt(text), MAX_PROMPT_CHARS)
                current = Exchange(user_text=cleaned, timestamp=timestamp)
                turn_count += 1
                last_prompt = cleaned
                if not first_prompt:
                    first_prompt = cleaned
                continue

            if record_type != "assistant":
                continue
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    text_value = block.get("text")
                    if not isinstance(text_value, str) or not text_value.strip():
                        continue
                    if current is None:
                        current = Exchange(timestamp=timestamp)
                    current.assistant_texts.append(block_text(text_value, 5_000))
                    if len(current.assistant_texts) > 3:
                        current.assistant_texts = current.assistant_texts[-3:]
                elif block_type == "tool_use":
                    name = str(block.get("name") or "tool")
                    detail = _tool_detail(name, block.get("input"))
                    call = ToolCall(name=name, detail=detail, timestamp=timestamp)
                    if current is None:
                        current = Exchange(timestamp=timestamp)
                    current.tools.append(call)
                    if len(current.tools) > 8:
                        current.tools = current.tools[-8:]
                    tool_counts[name] += 1
                    recent_tools.append(call)
                    if name in EDIT_TOOLS:
                        file_path = _file_path(block.get("input"), cwd)
                        if file_path:
                            count = edited.pop(file_path, 0) + 1
                            edited[file_path] = count

        append_current()

        if not first_prompt:
            first_prompt = last_prompt
        summary.cwd = cwd or summary.cwd
        summary.branch = branch
        summary.model = model
        summary.entrypoint = entrypoint
        summary.version = version
        summary.first_prompt = first_prompt
        summary.last_prompt = last_prompt
        summary.started = started
        summary.updated = updated or summary.updated
        summary.title = _choose_title(first_prompt, last_prompt) or summary.title

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

    def _load_todos(self, session_id: str) -> List[Dict[str, Any]]:
        tasks_dir = self.home() / "tasks" / session_id
        if not tasks_dir.is_dir():
            return []
        paths = [path for path in tasks_dir.glob("*.json") if path.stem.isdigit()]
        paths.sort(key=lambda path: int(path.stem))
        todos: List[Dict[str, Any]] = []
        for path in paths[-400:]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            subject = one_line(data.get("subject"), 200)
            if not subject:
                continue
            todos.append(
                {
                    "id": str(data.get("id") or path.stem),
                    "subject": subject,
                    "description": one_line(data.get("description"), 500),
                    "status": str(data.get("status") or ""),
                }
            )
        return todos
