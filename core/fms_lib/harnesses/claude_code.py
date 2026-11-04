from __future__ import annotations

import json
import os
import re
from collections import Counter, OrderedDict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, Iterator, List, Optional, Tuple

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
    file_path as _file_path,
)
from .common import (
    is_generic as _is_generic,
)
from .common import (
    tool_detail_for,
)

HEAD_BYTES = 2_000_000
HEAD_RECORDS = 400
TAIL_BYTES = 1_500_000
MAX_PROMPT_CHARS = 4_000
MAX_SUMMARY_CHARS = 20_000
MAX_ASSISTANT_CHARS = 5_000

_STRIP_BLOCK_RE = re.compile(
    r"<(system-reminder|user-prompt-submit-hook)(?:\s[^>]*)?>.*?</\1>",
    re.S,
)
_EXCLUDE_BLOCK_RE = re.compile(
    r"<(task-notification|command-name|command-message|command-args"
    r"|local-command-caveat|local-command-stdout|local-command-stderr"
    r"|bash-input|bash-stdout|bash-stderr)(?:\s[^>]*)?>",
    re.I,
)
_SLASH_COMMAND_RE = re.compile(r"/[A-Za-z0-9_:.-]+")
_INTERRUPT_RE = re.compile(r"\[Request interrupted by user[^\]]*\]")

EDIT_TOOLS = {
    "Edit",
    "Write",
    "MultiEdit",
    "NotebookEdit",
}

TOOL_DETAIL_KEYS = {
    "Bash": ("command",),
    "Read": ("file_path", "path"),
    "Write": ("file_path", "path"),
    "Edit": ("file_path", "path"),
    "MultiEdit": ("file_path", "path"),
    "NotebookEdit": ("notebook_path", "path"),
    "Grep": ("pattern",),
    "Glob": ("pattern",),
    "Task": ("description",),
    "Agent": ("description",),
    "Skill": ("skill",),
    "WebFetch": ("url",),
    "WebSearch": ("query",),
}


def _is_subagent_path(path: Path) -> bool:
    if path.name.startswith("agent-") and path.suffix == ".jsonl":
        return True
    return any(part == "subagents" for part in path.parts[:-1])


def _clean_prompt(value: str) -> str:
    return _STRIP_BLOCK_RE.sub("", value).strip()


def _prompt_from_text(value: str) -> str:
    if not value:
        return ""
    if _EXCLUDE_BLOCK_RE.search(value):
        return ""
    text = _clean_prompt(value)
    if not text:
        return ""
    lowered = text.casefold()
    if lowered.startswith("caveat:"):
        return ""
    if lowered.startswith("this session is being continued from a previous conversation"):
        return ""
    if _SLASH_COMMAND_RE.fullmatch(text):
        return ""
    if _INTERRUPT_RE.fullmatch(text):
        return ""
    return text


def _content_text(content: Any) -> Tuple[str, bool]:
    if isinstance(content, str):
        return content, False
    if not isinstance(content, list):
        return "", False
    parts: List[str] = []
    has_tool_result = False
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "tool_result":
            has_tool_result = True
            continue
        if block_type != "text":
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text)
    return "\n".join(parts), has_tool_result


def _prompt_from_record(record: Dict[str, Any]) -> str:
    if record.get("type") != "user":
        return ""
    if record.get("isMeta") or record.get("isSidechain"):
        return ""
    if record.get("isCompactSummary"):
        return ""
    if record.get("toolUseResult") is not None:
        return ""
    message = record.get("message")
    if not isinstance(message, dict) or message.get("role") != "user":
        return ""
    content, has_tool_result = _content_text(message.get("content"))
    if has_tool_result:
        return ""
    return _prompt_from_text(content)


def _assistant_text(record: Dict[str, Any]) -> str:
    if record.get("type") != "assistant" or record.get("isSidechain"):
        return ""
    message = record.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return ""
    content = message.get("content")
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


def _tool_use_blocks(record: Dict[str, Any]) -> Iterator[Tuple[str, Any]]:
    if record.get("type") != "assistant" or record.get("isSidechain"):
        return
    message = record.get("message")
    if not isinstance(message, dict):
        return
    content = message.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") not in ("tool_use", "server_tool_use"):
            continue
        name = block.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        yield name.strip(), block.get("input")


def _tool_detail(name: str, arguments: Any) -> str:
    return tool_detail_for(name, arguments, TOOL_DETAIL_KEYS)


def _ai_title(records: List[Dict[str, Any]]) -> str:
    for record in reversed(records):
        if record.get("type") != "ai-title":
            continue
        value = record.get("aiTitle")
        if isinstance(value, str) and value.strip():
            return one_line(value, 200)
    return ""


def _last_prompt_marker(records: List[Dict[str, Any]]) -> str:
    for record in reversed(records):
        if record.get("type") != "last-prompt":
            continue
        value = record.get("lastPrompt")
        if isinstance(value, str) and value.strip():
            text = _prompt_from_text(value)
            if text:
                return block_text(text, MAX_PROMPT_CHARS)
    return ""


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


def _model_from(records: List[Dict[str, Any]]) -> str:
    model = ""
    for record in records:
        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        value = message.get("model")
        if isinstance(value, str) and value.strip():
            model = value.strip()
    return model


def _last_string(records: List[Dict[str, Any]], key: str) -> str:
    value = ""
    for record in records:
        candidate = record.get(key)
        if isinstance(candidate, str) and candidate.strip():
            value = candidate.strip()
    return value


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


def _todo_from_tool_input(arguments: Any) -> List[Dict[str, Any]]:
    if not isinstance(arguments, dict):
        return []
    return _normalize_todos(arguments.get("todos"))


class ClaudeCodeAdapter(HarnessAdapter):
    """Claude Code CLI and IDE transcripts share one local store."""

    name = "claude-code"
    aliases = ("claude", "claude-code")
    variants = "cli, ide"
    store_hint = "~/.claude"
    home_env = "FMS_CLAUDE_HOME"

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".claude"

    def session_roots(self) -> List[Path]:
        return [self.home() / "projects"]

    def iter_session_paths(self) -> Iterator[Path]:
        root = self.home() / "projects"
        if not root.is_dir():
            return
        pending: List[Tuple[float, Path]] = []
        for path in root.glob("*/*.jsonl"):
            if not path.is_file() or path.name.startswith("agent-"):
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            pending.append((mtime, path))
        pending.sort(key=lambda item: item[0], reverse=True)
        for _, path in pending:
            yield path

    def summarize(self, path: Path) -> SessionSummary:
        if _is_subagent_path(path):
            raise ValueError(
                "Claude Code subagent transcript is not a resumable session: %s"
                % path
            )
        head = list(iter_head_records(path, HEAD_BYTES, HEAD_RECORDS))
        if not head:
            raise ValueError("cannot read Claude Code transcript: %s" % path)
        tail = iter_tail_records(path, TAIL_BYTES)
        recent = tail if tail else head

        session_id = _last_string(head, "sessionId") or _last_string(
            recent, "sessionId"
        )
        if not session_id:
            session_id = path.stem

        started = parse_timestamp(head[0].get("timestamp"))
        if started is None:
            for record in head:
                started = parse_timestamp(record.get("timestamp"))
                if started is not None:
                    break
        updated = _latest_timestamp(recent) or _latest_timestamp(head)

        first_prompt = _first_prompt(head)
        last_prompt = (
            _last_prompt(recent)
            or _last_prompt_marker(recent)
            or _last_prompt(head)
        )
        if not first_prompt:
            first_prompt = last_prompt
        if not last_prompt:
            last_prompt = first_prompt

        title = _ai_title(recent) or _ai_title(head)
        if not title or _is_generic(title):
            title = _choose_title(first_prompt, last_prompt) or session_id

        cwd = _last_string(recent, "cwd") or _last_string(head, "cwd")
        branch = _last_string(recent, "gitBranch") or _last_string(head, "gitBranch")
        version = _last_string(recent, "version") or _last_string(head, "version")
        entrypoint = _last_string(recent, "entrypoint") or _last_string(
            head, "entrypoint"
        )
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
            branch=branch,
            model=model,
            entrypoint=entrypoint,
            version=version,
            size=size,
            variants=self.variants,
            archived=False,
        )

    def resume_argv(self, summary: SessionSummary) -> Optional[List[str]]:
        return ["claude", "--resume", summary.session_id]

    def usage_summary(self, summary: SessionSummary) -> Optional[Dict[str, Any]]:
        """Sum the per-message usage the transcript itself records.

        Requires a full pass over the transcript — Claude Code stores
        usage per assistant message, not per session.
        """
        totals: Dict[str, Any] = {}
        wanted = {
            "input_tokens": "tokens_input",
            "output_tokens": "tokens_output",
            "cache_read_input_tokens": "tokens_cache_read",
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
                if not isinstance(record, dict) or record.get("type") != "assistant":
                    continue
                message = record.get("message")
                usage = message.get("usage") if isinstance(message, dict) else None
                if not isinstance(usage, dict):
                    continue
                for source, target in wanted.items():
                    value = usage.get(source)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        totals[target] = totals.get(target, 0) + value
        return totals or None

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        if _is_subagent_path(summary.path):
            return
        seen = set()
        for position, record in enumerate(iter_file_records(summary.path)):
            identifier = record.get("uuid")
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

    def _todos_for(
        self,
        session_id: str,
        transcript_todos: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        todos_dir = self.home() / "todos"
        candidates: List[Path] = []
        for path in todos_dir.glob("*.json"):
            name = path.name
            if name == session_id + ".json" or name.startswith(session_id + "-agent-"):
                candidates.append(path)
        if not candidates:
            return transcript_todos
        try:
            latest = max(candidates, key=lambda item: item.stat().st_mtime)
            data = json.loads(latest.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return transcript_todos
        return _normalize_todos(data)

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

        for position, record in enumerate(iter_file_records(summary.path)):
            timestamp = parse_timestamp(record.get("timestamp"))
            if timestamp is not None:
                if started is None or timestamp < started:
                    started = timestamp
                if updated is None or timestamp > updated:
                    updated = timestamp

            for key in ("cwd", "gitBranch", "version", "entrypoint"):
                value = record.get(key)
                if key == "cwd" and isinstance(value, str) and value:
                    cwd = value
                elif key == "gitBranch" and isinstance(value, str) and value:
                    summary.branch = value
                elif key == "version" and isinstance(value, str) and value:
                    summary.version = value
                elif key == "entrypoint" and isinstance(value, str) and value:
                    summary.entrypoint = value

            record_type = record.get("type")

            if record_type == "summary":
                candidate = record.get("summary")
                if isinstance(candidate, str) and candidate.strip():
                    compact_summary = block_text(candidate, MAX_SUMMARY_CHARS)
                continue

            if record_type == "system":
                continue

            if record_type == "assistant":
                message = record.get("message")
                if isinstance(message, dict):
                    candidate = message.get("model")
                    if isinstance(candidate, str) and candidate.strip():
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
                for name, arguments in _tool_use_blocks(record):
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
                    if name == "TodoWrite":
                        transcript_todos = _todo_from_tool_input(arguments)
                    if name in EDIT_TOOLS:
                        path_value = _file_path(arguments, cwd)
                        if path_value:
                            edited[path_value] = edited.get(path_value, 0) + 1
                continue

            if record_type != "user":
                continue

            if record.get("isCompactSummary"):
                message = record.get("message")
                content, _ = _content_text(
                    message.get("content") if isinstance(message, dict) else ""
                )
                if content.strip():
                    compact_summary = block_text(content, MAX_SUMMARY_CHARS)
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
        todos = self._todos_for(summary.session_id, transcript_todos)

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
