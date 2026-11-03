"""Adapter for Gemini CLI, Google's terminal coding agent.

Gemini CLI records each chat as one JSONL file under
``~/.gemini/tmp/<project>/chats/session-<timestamp>-<uuid>.jsonl``. The
project directory also holds ``.project_root``, which recovers the working
directory the tmp directory name may only hint at.

The log mixes three record shapes and is replayed in order:

- a header line with ``sessionId``, ``startTime``, ``lastUpdated`` and
  ``kind``;
- ``{"$set": {"messages": [...], "lastUpdated": ...}}`` full-array
  snapshots, which replace the message list;
- ``{"$set": {"lastUpdated": ...}}`` metadata-only updates;
- bare message records (``id``, ``timestamp``, ``type``, ``content``,
  ``model``, ``thoughts``, ``tokens``) that append one message.

Messages carry ``type`` ``user`` (``content`` blocks are either ``text`` —
the human turns — or ``functionResponse`` tool results), ``gemini``
(assistant turns with ``thoughts`` and ``model``), ``info`` (CLI notices,
ignored) and ``error`` (API failures, kept for the digest). Injected
``<session_context>`` blocks never become prompts.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, Iterator, List, Optional, Sequence, Tuple

from ..models import Exchange, SessionDetail, SessionSummary, ToolCall, UserPrompt
from ..util import (
    UTC,
    block_text,
    file_contains_all,
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
MAX_TOOL_RESPONSE_CHARS = 300


PROMPT_SKIP_PREFIXES = ("<session_context>", "<environment_context>")

TOOL_RESPONSE_KEYS = ("output", "result", "content", "text")


def _clean_prompt(value: str) -> str:
    text = value.strip()
    for tag in ("system-reminder", "task-notification"):
        text = re.sub(r"<%s>.*?</%s>" % (tag, tag), "", text, flags=re.S)
    return text.strip()


def _is_human_prompt(message: Dict[str, Any]) -> bool:
    if message.get("type") != "user":
        return False
    text = _message_text(message)
    if not text:
        return False
    return not text.casefold().startswith(PROMPT_SKIP_PREFIXES)


def _message_text(message: Dict[str, Any]) -> str:
    blocks = message.get("content")
    if not isinstance(blocks, list):
        return ""
    texts = []
    for block in blocks:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            texts.append(block["text"])
    return "\n".join(text for text in texts if text)


def _plain_content(message: Dict[str, Any]) -> str:
    """info/error records keep a plain string in ``content``."""

    content = message.get("content")
    return content if isinstance(content, str) else ""


def _tool_responses(message: Dict[str, Any]) -> List[ToolCall]:
    blocks = message.get("content")
    if not isinstance(blocks, list):
        return []
    tools: List[ToolCall] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        response = block.get("functionResponse")
        if not isinstance(response, dict):
            continue
        name = str(response.get("name") or "tool")
        payload = response.get("response")
        detail = tool_detail(
            payload if isinstance(payload, dict) else {}, TOOL_RESPONSE_KEYS
        )
        if not detail and isinstance(payload, str) and payload.strip():
            detail = one_line(payload, MAX_TOOL_RESPONSE_CHARS)
        tools.append(
            ToolCall(
                name=name,
                detail=detail,
                timestamp=parse_timestamp(message.get("timestamp")),
            )
        )
    return tools


def _display_id(path: Path) -> str:
    stem = path.stem
    if stem.startswith("session-"):
        stem = stem[len("session-") :]
    return stem.rsplit("-", 1)[-1]


def _replay(
    lines: Iterator[str],
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Replay one chat log: header, $set snapshots, bare message appends."""

    header: Optional[Dict[str, Any]] = None
    messages: List[Dict[str, Any]] = []
    seen: set = set()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        if "sessionId" in record:
            header = record
            continue
        if "$set" in record:
            payload = record["$set"]
            if isinstance(payload, dict) and "messages" in payload:
                replacement = payload.get("messages")
                messages = [
                    message for message in replacement if isinstance(message, dict)
                ] if isinstance(replacement, list) else []
                seen = {message.get("id") for message in messages}
            continue
        message_id = record.get("id")
        if message_id is not None and message_id in seen:
            continue
        messages.append(record)
        if message_id is not None:
            seen.add(message_id)
    return header, messages


class GeminiCLIAdapter(HarnessAdapter):
    """Gemini CLI keeps one replayable JSONL chat log per session."""

    name = "gemini-cli"
    aliases = ("gemini-cli", "gemini")
    variants = "cli"
    store_hint = "~/.gemini"
    home_env = "FMS_GEMINI_CLI_HOME"

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".gemini"

    def session_roots(self) -> List[Path]:
        return [self.home() / "tmp"]

    def iter_session_paths(self) -> Iterator[Path]:
        tmp = self.home() / "tmp"
        if not tmp.is_dir():
            return
        try:
            chats = sorted(
                path
                for path in tmp.glob("*/chats/session-*.jsonl")
                if path.is_file()
            )
        except OSError:
            return
        chats.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for path in chats:
            yield path

    def _header_for(self, path: Path) -> Dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(record, dict) and "sessionId" in record:
                        return record
        except OSError:
            return {}
        return {}

    def find(self, prefix: str) -> List[SessionSummary]:
        wanted = prefix.strip().casefold()
        matches: List[SessionSummary] = []
        for path in self.iter_session_paths():
            display = _display_id(path).casefold()
            header_id = ""
            if not display.startswith(wanted):
                header_id = str(self._header_for(path).get("sessionId") or "")
                if not header_id.casefold().startswith(wanted):
                    continue
            try:
                summary = self.summarize(path)
            except (OSError, ValueError):
                continue
            matches.append(summary)
        return matches

    def session_id_for(self, path: Path) -> str:
        return _display_id(path)

    def summarize(self, path: Path) -> SessionSummary:
        if not path.is_file():
            raise ValueError("gemini-cli session not found: %s" % path)
        size = path.stat().st_size
        try:
            handle = path.open("r", encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ValueError("cannot read gemini-cli session: %s" % exc)
        with handle:
            header, messages = _replay(handle)

        head: Deque[str] = deque(maxlen=PROMPT_HEAD_LIMIT)
        tail: Deque[str] = deque(maxlen=PROMPT_TAIL_LIMIT)
        started = parse_timestamp((header or {}).get("startTime"))
        updated = parse_timestamp((header or {}).get("lastUpdated"))
        model = ""
        for message in messages:
            timestamp = parse_timestamp(message.get("timestamp"))
            if timestamp is not None and (updated is None or timestamp > updated):
                updated = timestamp
            record_model = message.get("model")
            if isinstance(record_model, str) and record_model.strip():
                model = record_model.strip()
            if _is_human_prompt(message):
                text = _clean_prompt(_message_text(message))
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

        display = _display_id(path)
        title = one_line(last_prompt or first_prompt, 100)
        if not title or _is_generic(title):
            candidates = list(reversed(tail)) + list(head)
            chosen = next(
                (prompt for prompt in candidates if prompt and not _is_generic(prompt)),
                "",
            )
            title = one_line(chosen, 100) or display

        cwd = ""
        try:
            project_root = path.parent.parent / ".project_root"
            if project_root.is_file():
                cwd = project_root.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            cwd = ""

        return SessionSummary(
            harness=self.name,
            session_id=display,
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
            variants=self.variants,
            archived=False,
        )

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        try:
            handle = summary.path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            return
        with handle:
            _, messages = _replay(handle)
            for message in messages:
                if not _is_human_prompt(message):
                    continue
                yield UserPrompt(
                    text=_clean_prompt(_message_text(message)),
                    timestamp=parse_timestamp(message.get("timestamp")),
                )

    def load(self, summary: SessionSummary) -> SessionDetail:
        try:
            handle = summary.path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            return SessionDetail(summary=summary)
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

        with handle:
            _, messages = _replay(handle)
            for message in messages:
                timestamp = parse_timestamp(message.get("timestamp"))
                if timestamp is not None:
                    if started is None or timestamp < started:
                        started = timestamp
                    if updated is None or timestamp > updated:
                        updated = timestamp

                mtype = message.get("type")
                if mtype == "info":
                    continue

                if _is_human_prompt(message):
                    append_current()
                    cleaned = block_text(
                        _clean_prompt(_message_text(message)), MAX_PROMPT_CHARS
                    )
                    current = Exchange(user_text=cleaned, timestamp=timestamp)
                    turn_count += 1
                    last_prompt = cleaned
                    if not first_prompt:
                        first_prompt = cleaned
                    continue

                tools = _tool_responses(message)
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

                if mtype == "gemini":
                    record_model = message.get("model")
                    if isinstance(record_model, str) and record_model.strip():
                        model = record_model.strip()
                    text = _message_text(message)
                    if text.strip():
                        if current is None:
                            current = Exchange(timestamp=timestamp)
                        current.assistant_texts.append(
                            block_text(text, MAX_ASSISTANT_CHARS)
                        )
                        if len(current.assistant_texts) > 3:
                            current.assistant_texts = current.assistant_texts[-3:]
                    continue

                if mtype == "error":
                    text = _plain_content(message)
                    if text.strip():
                        if current is None:
                            current = Exchange(timestamp=timestamp)
                        rendered = one_line(text, 300)
                        if not rendered.startswith("[API Error"):
                            rendered = "[API error] " + rendered
                        current.assistant_texts.append(rendered)
                        if len(current.assistant_texts) > 3:
                            current.assistant_texts = current.assistant_texts[-3:]
                    continue

        append_current()
        handle.close()

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
            todos=[],
            exchanges=list(exchanges),
            edited_files=[],
            tool_counts=dict(tool_counts.most_common()),
            recent_tools=list(recent_tools),
            turn_count=turn_count,
        )

    def contains(self, summary: SessionSummary, tokens: Sequence[str]) -> bool:
        return file_contains_all(summary.path, tokens)

