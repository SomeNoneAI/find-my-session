"""Adapter for Qwen Code, the Qwen terminal coding agent.

Qwen Code (a Gemini CLI fork with a Claude Code-style record envelope)
stores one JSONL session log per chat under
``~/.qwen/projects/<encoded-cwd>/chats/<session-uuid>.jsonl``. Each line is
one record:

``{"uuid", "parentUuid", "sessionId", "timestamp", "type", "cwd",
"gitBranch", "version", "message": {"role", "parts": [...]}}``

with ``type`` ``user`` (``text`` parts are the human turns),
``assistant`` (``model``, ``usageMetadata``, ``text`` and ``functionCall``
parts), ``tool_result`` (``toolCallResult`` with ``callId``,
``resultDisplay``, ``status``, plus a ``functionResponse`` part) and
``system`` (``subtype: "ui_telemetry"``, skipped). Todos live beside the
store in ``~/.qwen/todos/<session-id>.json``.
"""

from __future__ import annotations

import json
import os
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, Iterator, List, Optional

from ..models import Exchange, SessionDetail, SessionSummary, ToolCall, UserPrompt
from ..util import (
    UTC,
    block_text,
    one_line,
    parse_timestamp,
)
from .base import HarnessAdapter
from .common import is_generic as _is_generic
from .common import tool_detail

MAX_PROMPT_CHARS = 4_000
MAX_ASSISTANT_CHARS = 5_000
PROMPT_HEAD_LIMIT = 200
PROMPT_TAIL_LIMIT = 200
MAX_TODOS = 400

PROMPT_SKIP_PREFIXES = (
    "<session_context>",
    "<environment_context>",
    "<memory>",
)

TEXT_KEYS = (
    "filePath",
    "file_path",
    "path",
    "absolute_path",
    "command",
    "description",
    "pattern",
    "prompt",
    "url",
    "query",
)


def _clean_prompt(value: str) -> str:
    return value.strip()


def _parts(message: Any) -> List[Dict[str, Any]]:
    if not isinstance(message, dict):
        return []
    parts = message.get("parts")
    return [part for part in parts if isinstance(part, dict)] if isinstance(parts, list) else []


def _message_text(message: Any) -> str:
    texts = []
    for part in _parts(message):
        text = part.get("text")
        if isinstance(text, str) and text:
            texts.append(text)
    return "\n".join(texts)


def _is_human_prompt(record: Dict[str, Any]) -> bool:
    if record.get("type") != "user":
        return False
    text = _clean_prompt(_message_text(record.get("message")))
    if not text:
        return False
    lowered = text.casefold()
    return not any(
        lowered.startswith(prefix) for prefix in PROMPT_SKIP_PREFIXES
    )


def _tool_calls(record: Dict[str, Any]) -> List[ToolCall]:
    calls: List[ToolCall] = []
    for part in _parts(record.get("message")):
        call = part.get("functionCall")
        if not isinstance(call, dict):
            continue
        name = str(call.get("name") or "tool")
        calls.append(
            ToolCall(
                name=name,
                detail=tool_detail(call.get("args"), TEXT_KEYS),
                timestamp=parse_timestamp(record.get("timestamp")),
            )
        )
    return calls


class QwenAdapter(HarnessAdapter):
    """Qwen Code keeps one JSONL session log per chat under ~/.qwen."""

    name = "qwen"
    aliases = ("qwen",)
    variants = "cli"
    store_hint = "~/.qwen"
    home_env = "FMS_QWEN_HOME"

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".qwen"

    def session_roots(self) -> List[Path]:
        return [self.home() / "projects"]

    def iter_session_paths(self) -> Iterator[Path]:
        projects = self.home() / "projects"
        if not projects.is_dir():
            return
        try:
            chats = sorted(
                path
                for path in projects.glob("*/chats/*.jsonl")
                if path.is_file()
            )
        except OSError:
            return
        chats.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for path in chats:
            yield path

    def _stream(self, path: Path) -> Iterator[Dict[str, Any]]:
        try:
            handle = path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            return
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict):
                    yield record

    def summarize(self, path: Path) -> SessionSummary:
        if not path.is_file():
            raise ValueError("qwen session not found: %s" % path)
        size = path.stat().st_size
        head: Deque[str] = deque(maxlen=PROMPT_HEAD_LIMIT)
        tail: Deque[str] = deque(maxlen=PROMPT_TAIL_LIMIT)
        session_id = path.stem
        cwd = ""
        branch = ""
        version = ""
        model = ""
        started: Optional[datetime] = None
        updated: Optional[datetime] = None
        for record in self._stream(path):
            timestamp = parse_timestamp(record.get("timestamp"))
            if timestamp is not None:
                if started is None or timestamp < started:
                    started = timestamp
                if updated is None or timestamp > updated:
                    updated = timestamp
            if not cwd and record.get("cwd"):
                cwd = str(record["cwd"])
            if not branch and record.get("gitBranch"):
                branch = str(record["gitBranch"])
            if not version and record.get("version"):
                version = str(record["version"])
            if record.get("sessionId"):
                session_id = str(record["sessionId"])
            record_model = record.get("model")
            if isinstance(record_model, str) and record_model.strip():
                model = record_model.strip()
            if _is_human_prompt(record):
                text = _clean_prompt(_message_text(record.get("message")))
                head.append(block_text(text, MAX_PROMPT_CHARS))
                tail.append(block_text(text, MAX_PROMPT_CHARS))

        first_prompt = head[0] if head else ""
        last_prompt = tail[-1] if tail else ""
        if not first_prompt:
            first_prompt = last_prompt
        if not last_prompt:
            last_prompt = first_prompt

        if updated is None:
            try:
                updated = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError:
                updated = started
        if updated is None:
            updated = datetime.now(tz=UTC)
        if started is None:
            started = updated

        title = one_line(last_prompt or first_prompt, 100)
        if not title or _is_generic(title):
            candidates = list(reversed(tail)) + list(head)
            chosen = next(
                (prompt for prompt in candidates if prompt and not _is_generic(prompt)),
                "",
            )
            title = one_line(chosen, 100) or session_id[:8]

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
            entrypoint="cli",
            version=version,
            size=size,
            variants=self.variants,
            archived=False,
        )

    def resume_argv(self, summary: SessionSummary) -> Optional[List[str]]:
        return ["qwen", "--resume", summary.session_id]

    def usage_summary(self, summary: SessionSummary) -> Optional[Dict[str, Any]]:
        """Sum the per-record usageMetadata the log itself records."""
        totals: Dict[str, Any] = {}
        wanted = {
            "promptTokenCount": "tokens_input",
            "candidatesTokenCount": "tokens_output",
            "cachedContentTokenCount": "tokens_cache_read",
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
                meta = record.get("usageMetadata")
                if not isinstance(meta, dict):
                    continue
                for source, target in wanted.items():
                    value = meta.get(source)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        totals[target] = totals.get(target, 0) + value
        return totals or None

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        for record in self._stream(summary.path):
            if not _is_human_prompt(record):
                continue
            yield UserPrompt(
                text=_clean_prompt(_message_text(record.get("message"))),
                timestamp=parse_timestamp(record.get("timestamp")),
            )

    def _load_todos(self, session_id: str) -> List[Dict[str, Any]]:
        path = self.home() / "todos" / ("%s.json" % session_id)
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        try:
            data = json.loads(raw)
        except ValueError:
            return []
        todos = data.get("todos") if isinstance(data, dict) else None
        if not isinstance(todos, list):
            return []
        rows: List[Dict[str, Any]] = []
        for todo in todos[-MAX_TODOS:]:
            if not isinstance(todo, dict):
                continue
            subject = one_line(todo.get("content"), 200)
            if not subject:
                continue
            status = str(todo.get("status") or "")
            if status == "done":
                status = "completed"
            rows.append({"subject": subject, "status": status})
        return rows

    def load(self, summary: SessionSummary) -> SessionDetail:
        exchanges: Deque[Exchange] = deque(maxlen=50)
        current: Optional[Exchange] = None
        tool_counts: Counter = Counter()
        recent_tools: Deque[ToolCall] = deque(maxlen=20)
        started = summary.started
        updated = summary.updated
        model = summary.model
        first_prompt = summary.first_prompt
        last_prompt = summary.last_prompt
        turn_count = 0

        def append_current() -> None:
            nonlocal current
            if current is None:
                return
            if current.user_text or current.assistant_texts or current.tools:
                exchanges.append(current)
            current = None

        for record in self._stream(summary.path):
            timestamp = parse_timestamp(record.get("timestamp"))
            if timestamp is not None:
                if started is None or timestamp < started:
                    started = timestamp
                if updated is None or timestamp > updated:
                    updated = timestamp

            rtype = record.get("type")
            if rtype == "system":
                continue

            if _is_human_prompt(record):
                append_current()
                cleaned = block_text(
                    _clean_prompt(_message_text(record.get("message"))),
                    MAX_PROMPT_CHARS,
                )
                current = Exchange(user_text=cleaned, timestamp=timestamp)
                turn_count += 1
                last_prompt = cleaned
                if not first_prompt:
                    first_prompt = cleaned
                continue

            tools = _tool_calls(record)
            if tools:
                if current is None:
                    current = Exchange(timestamp=timestamp)
                for tool in tools:
                    current.tools.append(tool)
                    tool_counts[tool.name] += 1
                    recent_tools.append(tool)
                if len(current.tools) > 8:
                    current.tools = current.tools[-8:]
                continue

            if rtype == "assistant":
                record_model = record.get("model")
                if isinstance(record_model, str) and record_model.strip():
                    model = record_model.strip()
                text = _message_text(record.get("message"))
                if text.strip():
                    if current is None:
                        current = Exchange(timestamp=timestamp)
                    current.assistant_texts.append(
                        block_text(text, MAX_ASSISTANT_CHARS)
                    )
                    if len(current.assistant_texts) > 3:
                        current.assistant_texts = current.assistant_texts[-3:]
                continue

        append_current()

        if not first_prompt:
            first_prompt = last_prompt
        summary.model = model
        summary.first_prompt = first_prompt
        summary.last_prompt = last_prompt
        summary.started = started
        summary.updated = updated or summary.updated

        return SessionDetail(
            summary=summary,
            compact_summary="",
            todos=self._load_todos(summary.session_id),
            exchanges=list(exchanges),
            edited_files=[],
            tool_counts=dict(tool_counts.most_common()),
            recent_tools=list(recent_tools),
            turn_count=turn_count,
        )
