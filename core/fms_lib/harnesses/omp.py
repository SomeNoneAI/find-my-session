"""Oh My Pi (omp) session store adapter.

Verified against omp 18.16.0 on macOS. OMP is a fork of Pi with its own
store at ``~/.omp/agent`` and its own session schema: title records,
``attribution`` on user messages, flat ``toolResult`` messages, and
subagent transcripts stored in a sibling directory.
"""

from __future__ import annotations

import json
import os
import re
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
from .common import choose_title as _choose_title
from .common import file_path as _file_path
from .common import is_generic as _is_generic
from .common import tool_detail_for

HEAD_BYTES = 2_000_000
HEAD_RECORDS = 400
TAIL_BYTES = 1_500_000
MAX_PROMPT_CHARS = 4_000
MAX_SUMMARY_CHARS = 20_000
MAX_ASSISTANT_CHARS = 5_000

_SYSTEM_REMINDER_RE = re.compile(
    r"<system-reminder(?:\s[^>]*)?>.*?</system-reminder>", re.S
)
_TIMESTAMP_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[^_]*_")
_USER_ATTRIBUTIONS = frozenset({"", "user"})

EDIT_TOOLS = {
    "edit",
    "write",
    "multi_edit",
    "apply_patch",
    "ast_edit",
    "notebook_edit",
}

TOOL_DETAIL_KEYS = {
    "read": ("path", "file_path"),
    "write": ("path", "file_path"),
    "edit": ("path", "file_path"),
    "ast_edit": ("path", "file_path"),
    "bash": ("command",),
    "grep": ("pattern",),
    "glob": ("pattern",),
    "find": ("pattern",),
    "task": ("description", "prompt"),
    "agent": ("description", "prompt"),
}


def _clean_prompt(value: str) -> str:
    return _SYSTEM_REMINDER_RE.sub("", value).strip()


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
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


def _message(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if record.get("type") != "message":
        return None
    message = record.get("message")
    return message if isinstance(message, dict) else None


def _prompt_from_record(record: Dict[str, Any]) -> str:
    message = _message(record)
    if message is None or message.get("role") != "user":
        return ""
    attribution = message.get("attribution")
    if isinstance(attribution, str) and attribution.strip().casefold() not in _USER_ATTRIBUTIONS:
        return ""
    return _clean_prompt(_content_text(message.get("content")))


def _assistant_text(record: Dict[str, Any]) -> str:
    message = _message(record)
    if message is None or message.get("role") != "assistant":
        return ""
    text = _content_text(message.get("content"))
    error = message.get("errorMessage")
    if isinstance(error, str) and error.strip():
        text = (text + "\n" + error).strip() if text else error.strip()
    return text


def _tool_blocks(record: Dict[str, Any]) -> Iterator[Tuple[str, Any]]:
    message = _message(record)
    if message is None or message.get("role") != "assistant":
        return
    content = message.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "toolCall":
            continue
        name = block.get("name")
        if isinstance(name, str) and name.strip():
            yield name.strip(), block.get("arguments")


def _tool_detail(name: str, arguments: Any) -> str:
    return tool_detail_for(name.casefold(), arguments, TOOL_DETAIL_KEYS)


def _title_from(records: List[Dict[str, Any]]) -> str:
    title = ""
    for record in records:
        if record.get("type") not in ("title", "title_change"):
            continue
        value = record.get("title")
        if isinstance(value, str) and value.strip():
            title = one_line(value, 200)
    return title


def _model_from(records: List[Dict[str, Any]]) -> str:
    event_model = ""
    message_model = ""
    for record in records:
        if record.get("type") == "model_change":
            value = record.get("model")
            if isinstance(value, str) and value.strip():
                event_model = value.strip()
            continue
        message = _message(record)
        if message is None or message.get("role") != "assistant":
            continue
        value = message.get("model")
        if isinstance(value, str) and value.strip():
            message_model = value.strip()
    return event_model or message_model


def _first_prompt(records: List[Dict[str, Any]]) -> str:
    for record in records:
        text = _prompt_from_record(record)
        if text:
            return block_text(text, MAX_PROMPT_CHARS)
    return ""


def _last_prompt(records: List[Dict[str, Any]]) -> str:
    for record in reversed(records):
        text = _prompt_from_record(record)
        if text:
            return block_text(text, MAX_PROMPT_CHARS)
    return ""


def _latest_timestamp(records: List[Dict[str, Any]]) -> Optional[datetime]:
    latest: Optional[datetime] = None
    for record in records:
        timestamp = parse_timestamp(record.get("timestamp"))
        if timestamp is not None and (latest is None or timestamp > latest):
            latest = timestamp
    return latest


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
            item.get("content") or item.get("subject") or item.get("activeForm"),
            200,
        )
        if not subject:
            continue
        status = str(item.get("status") or "")
        if status == "done":
            status = "completed"
        todos.append({"subject": subject, "status": status})
    return todos


def _todo_from_tool(name: str, arguments: Any) -> List[Dict[str, Any]]:
    if "todo" not in name.casefold() or not isinstance(arguments, dict):
        return []
    return _normalize_todos(arguments.get("todos"))


def _session_id_from_path(path: Path) -> str:
    stem = path.stem
    match = _TIMESTAMP_PREFIX_RE.match(stem)
    if match:
        return stem[match.end() :]
    if "_" in stem:
        return stem.split("_", 1)[1]
    return stem


def _read_header(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    for record in records:
        if record.get("type") == "session":
            return record
    return {}


def _is_subagent_path(path: Path) -> bool:
    if any(part == "subagents" for part in path.parts[:-1]):
        return True
    try:
        sibling = path.parent.parent / (path.parent.name + ".jsonl")
    except OSError:
        return False
    return sibling.is_file()


class OmpAdapter(HarnessAdapter):
    """Oh My Pi (omp) CLI store."""

    name = "omp"
    aliases = ("omp", "oh-my-pi")
    variants = "cli"
    store_hint = "~/.omp/agent/sessions"
    home_env = "FMS_OMP_HOME"

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".omp" / "agent"

    def _sessions_root(self) -> Path:
        override = os.environ.get("PI_CODING_AGENT_SESSION_DIR")
        if override:
            return Path(override).expanduser()
        return self.home() / "sessions"

    def session_roots(self) -> List[Path]:
        return [self._sessions_root()]

    def iter_session_paths(self) -> Iterator[Path]:
        root = self._sessions_root()
        if not root.is_dir():
            return
        pending: List[Tuple[float, Path]] = []
        for path in root.glob("*/*.jsonl"):
            if not path.is_file() or path.name.startswith("."):
                continue
            if _is_subagent_path(path):
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            pending.append((mtime, path))
        pending.sort(key=lambda item: item[0], reverse=True)
        for _, path in pending:
            yield path

    def session_id_for(self, path: Path) -> str:
        return _session_id_from_path(path)

    def summarize(self, path: Path) -> SessionSummary:
        if _is_subagent_path(path):
            raise ValueError(
                "Oh My Pi subagent transcript is not a resumable session: %s" % path
            )
        head = list(iter_head_records(path, HEAD_BYTES, HEAD_RECORDS))
        if not head:
            raise ValueError("cannot read Oh My Pi session transcript: %s" % path)
        tail = iter_tail_records(path, TAIL_BYTES)
        recent = tail if tail else head

        header = _read_header(head)
        session_id = header.get("id")
        if not isinstance(session_id, str) or not session_id.strip():
            session_id = _session_id_from_path(path)
        session_id = session_id.strip()

        started = parse_timestamp(header.get("timestamp"))
        if started is None:
            for record in head:
                started = parse_timestamp(record.get("timestamp"))
                if started is not None:
                    break
        updated = _latest_timestamp(recent) or _latest_timestamp(head)

        first_prompt = _first_prompt(head)
        last_prompt = _last_prompt(recent) or _last_prompt(head)
        if not first_prompt:
            first_prompt = last_prompt
        if not last_prompt:
            last_prompt = first_prompt

        title = _title_from(recent) or _title_from(head)
        if not title or _is_generic(title):
            title = _choose_title(first_prompt, last_prompt) or session_id

        cwd = header.get("cwd")
        cwd = cwd.strip() if isinstance(cwd, str) else ""
        version = header.get("version")
        version = str(version) if version not in (None, "") else ""
        model = _model_from(recent) or _model_from(head)

        if updated is None:
            try:
                updated = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError:
                updated = datetime.now(tz=UTC)
        if started is None:
            started = updated

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
            first_prompt=first_prompt,
            last_prompt=last_prompt,
            started=started,
            model=model,
            entrypoint="cli",
            version=version,
            size=size,
            variants=self.variants,
            archived=False,
        )

    def resume_argv(self, summary: SessionSummary) -> Optional[List[str]]:
        return ["omp", "--resume", summary.session_id]

    def usage_summary(self, summary: SessionSummary) -> Optional[Dict[str, Any]]:
        totals: Dict[str, Any] = {}
        cost_total = 0.0
        seen_cost = False
        wanted = {
            "input": "tokens_input",
            "output": "tokens_output",
            "cacheRead": "tokens_cache_read",
        }
        try:
            handle = summary.path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            return None
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                message = _message(record) if isinstance(record, dict) else None
                if message is None or message.get("role") != "assistant":
                    continue
                usage = message.get("usage")
                if not isinstance(usage, dict):
                    continue
                for source, target in wanted.items():
                    value = usage.get(source)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        totals[target] = totals.get(target, 0) + value
                cost = usage.get("cost")
                if isinstance(cost, dict):
                    value = cost.get("total")
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        cost_total += value
                        seen_cost = True
        if seen_cost:
            totals["cost"] = cost_total
        return totals or None

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        if _is_subagent_path(summary.path):
            return
        seen: Set[Any] = set()
        for position, record in enumerate(iter_file_records(summary.path)):
            identifier = record.get("id")
            key: Any = identifier if isinstance(identifier, str) else position
            if key in seen:
                continue
            text = _prompt_from_record(record)
            if not text:
                continue
            seen.add(key)
            yield UserPrompt(
                text=text,
                timestamp=parse_timestamp(record.get("timestamp")),
            )

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
        transcript_todos: List[Dict[str, Any]] = []
        turn_count = 0

        def append_current() -> None:
            nonlocal current
            if current is None:
                return
            if current.user_text or current.assistant_texts or current.tools:
                exchanges.append(current)
            current = None

        for record in iter_file_records(summary.path):
            timestamp = parse_timestamp(record.get("timestamp"))
            if timestamp is not None:
                if started is None or timestamp < started:
                    started = timestamp
                if updated is None or timestamp > updated:
                    updated = timestamp

            record_type = record.get("type")

            if record_type == "session":
                header_cwd = record.get("cwd")
                if isinstance(header_cwd, str) and header_cwd.strip():
                    cwd = header_cwd.strip()
                version = record.get("version")
                if version not in (None, ""):
                    summary.version = str(version)
                continue

            if record_type in ("title", "title_change"):
                title = record.get("title")
                if isinstance(title, str) and title.strip():
                    summary.title = one_line(title, 200)
                continue

            if record_type == "model_change":
                candidate = record.get("model")
                if isinstance(candidate, str) and candidate.strip():
                    model = candidate.strip()
                continue

            if record_type == "compaction":
                candidate = record.get("summary")
                if isinstance(candidate, str) and candidate.strip():
                    compact_summary = block_text(candidate, MAX_SUMMARY_CHARS)
                continue

            message = _message(record)
            if message is None:
                continue
            role = message.get("role")

            if role == "assistant":
                candidate = message.get("model")
                if not model and isinstance(candidate, str) and candidate.strip():
                    model = candidate.strip()
                text = _assistant_text(record)
                if text:
                    if current is None:
                        current = Exchange(timestamp=timestamp)
                    current.assistant_texts.append(
                        block_text(text, MAX_ASSISTANT_CHARS)
                    )
                    if len(current.assistant_texts) > 3:
                        current.assistant_texts = current.assistant_texts[-3:]
                for name, arguments in _tool_blocks(record):
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
                    todos = _todo_from_tool(name, arguments)
                    if todos:
                        transcript_todos = todos
                    if name.casefold() in EDIT_TOOLS:
                        path_value = _file_path(arguments, cwd)
                        if path_value:
                            edited[path_value] = edited.get(path_value, 0) + 1
                continue

            if role != "user":
                continue

            text = _prompt_from_record(record)
            if not text:
                continue
            append_current()
            cleaned = block_text(text, MAX_PROMPT_CHARS)
            current = Exchange(user_text=cleaned, timestamp=timestamp)
            turn_count += 1
            last_prompt = cleaned
            if not first_prompt:
                first_prompt = cleaned

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
            todos=transcript_todos,
            exchanges=list(exchanges),
            edited_files=edited_files,
            tool_counts=dict(tool_counts.most_common()),
            recent_tools=list(recent_tools),
            turn_count=turn_count,
        )
