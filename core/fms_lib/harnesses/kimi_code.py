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

HEAD_BYTES = 1_000_000
HEAD_RECORDS = 300
TAIL_BYTES = 256_000
MAX_PROMPT_CHARS = 4_000
MAX_SUMMARY_CHARS = 20_000
MAX_ASSISTANT_CHARS = 5_000

PROMPT_SKIP_PREFIXES = (
    "<system-reminder>",
    "<task-notification>",
    "<notification",
    "<user-prompt-submit-hook>",
    "<local-command",
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
    "Edit",
    "Write",
    "MultiEdit",
    "NotebookEdit",
    "apply_patch",
}

FILE_KEYS = ("path", "file_path", "notebook_path", "target_file")


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


def _clean_prompt(value: str) -> str:
    text = value.strip()
    for tag in (
        "system-reminder",
        "task-notification",
        "command-message",
        "command-name",
        "user-prompt-submit-hook",
    ):
        text = re.sub(
            r"<%s>.*?</%s>" % (tag, tag), "", text, flags=re.S
        )
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


def _choose_title(first_prompt: str, last_prompt: str) -> str:
    for candidate in (last_prompt, first_prompt):
        if candidate and not _is_generic(candidate):
            return one_line(candidate, 100)
    return one_line(last_prompt or first_prompt, 100)


def _session_id_from_name(name: str) -> str:
    return name[len("session_") :] if name.startswith("session_") else name


def _payload_time(payload: Dict[str, Any]) -> Optional[datetime]:
    return parse_timestamp(payload.get("time"))


def _parse_tool_args(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _tool_detail(name: str, args: Any) -> str:
    if not isinstance(args, dict):
        return ""
    keys_by_name = {
        "Bash": ("command",),
        "Read": ("path",),
        "Write": ("path",),
        "Edit": ("path",),
        "Grep": ("pattern", "path"),
        "Glob": ("pattern", "path"),
        "Skill": ("skill",),
        "NotifyUser": ("title", "message"),
        "TaskOutput": ("task_id",),
        "ReadMediaFile": ("path",),
    }
    for key in keys_by_name.get(name, ()):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
    for value in args.values():
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
    return ""


def _file_path(args: Any, cwd: str) -> str:
    if not isinstance(args, dict):
        return ""
    value = ""
    for key in FILE_KEYS:
        candidate = args.get(key)
        if isinstance(candidate, str) and candidate.strip():
            value = candidate.strip()
            break
    if not value:
        return ""
    value = os.path.expanduser(value)
    if cwd and not os.path.isabs(value):
        value = os.path.join(cwd, value)
    return os.path.normpath(value)


def _is_composer_prompt(payload: Dict[str, Any]) -> bool:
    metadata = payload.get("clientMetadata")
    if not isinstance(metadata, list):
        return False
    for item in metadata:
        if isinstance(item, dict) and isinstance(
            item.get("kimi_code_composer"), dict
        ):
            return True
    return False


def _is_main_agent(payload: Dict[str, Any]) -> bool:
    agent_id = payload.get("agentId")
    return not agent_id or agent_id == "main"


def _origin_entrypoint(origin: Any) -> str:
    if not isinstance(origin, dict):
        return ""
    metadata = origin.get("clientMetadata")
    if isinstance(metadata, list):
        for item in metadata:
            if isinstance(item, dict) and isinstance(
                item.get("kimi_code_composer"), dict
            ):
                return "desktop"
    return "cli"


def _normalize_todos(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    todos: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        subject = one_line(item.get("title") or item.get("subject"), 200)
        if not subject:
            continue
        status = str(item.get("status") or "")
        if status == "done":
            status = "completed"
        todos.append({"subject": subject, "status": status})
    return todos


class KimiCodeAdapter(HarnessAdapter):
    """Kimi Code desktop and CLI share one local store and one session namespace."""

    name = "kimi-code"
    aliases = ("kimi-code", "kimi", "kimi-code-cli", "kimi-code-desktop")
    variants = "desktop, cli"
    store_hint = "~/.kimi-code"
    home_env = "FMS_KIMI_CODE_HOME"
    _index_cache: Optional[
        Tuple[Tuple[str, int, int], Dict[str, str]]
    ] = None

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".kimi-code"

    def session_roots(self) -> List[Path]:
        return [self.home() / "sessions", self.home() / "server" / "events"]

    def _session_dir_by_id(self, name: str) -> Optional[Path]:
        root = self.home() / "sessions"
        if not root.is_dir():
            return None
        if name.endswith(".jsonl"):
            name = name[: -len(".jsonl")]
        for candidate in root.glob("*/" + name):
            if candidate.is_dir():
                return candidate
        return None

    def _session_dir_for(self, path: Path) -> Optional[Path]:
        path = path.expanduser()
        if path.is_dir() and path.name.startswith("session_"):
            return path
        if path.name == "wire.jsonl":
            parents = path.parents
            if len(parents) >= 3:
                return parents[2]
        if path.name == "state.json":
            return path.parent
        if path.name.startswith("session_") and path.suffix == ".jsonl":
            return self._session_dir_by_id(path.name)
        for parent in path.parents:
            if parent.name.startswith("session_"):
                return parent
        return None

    @staticmethod
    def _read_state(session_dir: Optional[Path]) -> Dict[str, Any]:
        if session_dir is None:
            return {}
        path = session_dir / "state.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _wire_path(self, session_dir: Path) -> Path:
        return session_dir / "agents" / "main" / "wire.jsonl"

    def _event_path(self, session_dir: Path) -> Path:
        return self.home() / "server" / "events" / (session_dir.name + ".jsonl")

    def _index_cwds(self) -> Dict[str, str]:
        path = self.home() / "session_index.jsonl"
        try:
            stat = path.stat()
        except OSError:
            return {}
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        cached = self._index_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        mapping: Dict[str, str] = {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
                    if not isinstance(record, dict):
                        continue
                    session_id = record.get("sessionId")
                    work_dir = record.get("workDir")
                    if isinstance(session_id, str) and isinstance(work_dir, str):
                        mapping[_session_id_from_name(session_id)] = work_dir
        except (OSError, UnicodeDecodeError):
            return {}
        self._index_cache = (key, mapping)
        return mapping

    def _index_cwd(self, session_id: str) -> str:
        return self._index_cwds().get(_session_id_from_name(session_id), "")

    @staticmethod
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def iter_session_paths(self) -> Iterator[Path]:
        root = self.home() / "sessions"
        if not root.is_dir():
            return
        pending: List[Tuple[datetime, float, Path]] = []
        for session_dir in root.glob("*/session_*"):
            if not session_dir.is_dir():
                continue
            wire = self._wire_path(session_dir)
            state_path = session_dir / "state.json"
            if wire.is_file():
                path = wire
            elif state_path.is_file():
                path = state_path
            else:
                continue
            state = self._read_state(session_dir)
            updated = parse_timestamp(state.get("updatedAt"))
            mtime = self._mtime(path)
            if updated is None:
                updated = datetime.fromtimestamp(mtime, tz=UTC)
            pending.append((updated, mtime, path))
        pending.sort(key=lambda item: (item[0], item[1]), reverse=True)
        for _, _, path in pending:
            yield path

    def session_id_for(self, path: Path) -> str:
        if path.name == "wire.jsonl" and len(path.parents) >= 3:
            return _session_id_from_name(path.parents[2].name)
        if path.name == "state.json":
            return _session_id_from_name(path.parent.name)
        if path.name.startswith("session_"):
            return _session_id_from_name(path.stem)
        if path.is_dir():
            return _session_id_from_name(path.name)
        return _session_id_from_name(path.stem)

    def find(self, prefix: str) -> List[SessionSummary]:
        wanted = prefix.strip().casefold()
        if wanted.startswith("session_"):
            wanted = wanted[len("session_") :]
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

    @staticmethod
    def _iter_events(path: Path) -> Iterator[Dict[str, Any]]:
        for record in iter_file_records(path):
            if record.get("kind") == "journal_header":
                continue
            envelope = record.get("envelope")
            if isinstance(envelope, dict):
                yield envelope

    def _first_prompt_from_events(
        self, event_path: Path
    ) -> Tuple[str, str, str, Optional[datetime]]:
        first_prompt = ""
        cwd = ""
        entrypoint = ""
        started: Optional[datetime] = None
        for record in (
            iter_head_records(event_path, HEAD_BYTES, HEAD_RECORDS)
            if event_path.is_file()
            else ()
        ):
            envelope = record.get("envelope")
            if not isinstance(envelope, dict):
                continue
            envelope_type = envelope.get("type")
            payload = envelope.get("payload") or {}
            if not isinstance(payload, dict) or not _is_main_agent(payload):
                continue
            timestamp = _payload_time(payload)
            if started is None and timestamp is not None:
                started = timestamp
            if envelope_type == "event.session.created":
                session = payload.get("session") or {}
                metadata = session.get("metadata") or {}
                if isinstance(metadata, dict) and metadata.get("cwd"):
                    cwd = str(metadata["cwd"])
                continue
            if envelope_type != "prompt.submitted":
                continue
            text = _extract_text(payload.get("content"))
            if _meaningful_prompt(text):
                first_prompt = block_text(
                    _clean_prompt(text), MAX_PROMPT_CHARS
                )
                entrypoint = (
                    "desktop" if _is_composer_prompt(payload) else "cli"
                )
                break
        return first_prompt, cwd, entrypoint, started

    def _first_prompt_from_wire(
        self, wire_path: Path
    ) -> Tuple[str, str, Optional[datetime], str]:
        first_prompt = ""
        model = ""
        started: Optional[datetime] = None
        entrypoint = ""
        if not wire_path.is_file():
            return first_prompt, model, started, entrypoint
        for record in iter_head_records(wire_path, HEAD_BYTES, HEAD_RECORDS):
            record_type = record.get("type")
            timestamp = parse_timestamp(record.get("time"))
            if started is None and timestamp is not None:
                started = timestamp
            if record_type == "llm.request" and not model:
                model = str(record.get("model") or "")
            elif record_type == "profile.bind" and not model:
                alias = record.get("modelAlias")
                if isinstance(alias, str) and alias.strip():
                    model = alias.strip()
            if record_type != "turn.prompt":
                continue
            origin = record.get("origin") or {}
            if not isinstance(origin, dict) or origin.get("kind") != "user":
                continue
            text = _extract_text(record.get("input"))
            if _meaningful_prompt(text):
                first_prompt = block_text(
                    _clean_prompt(text), MAX_PROMPT_CHARS
                )
                entrypoint = _origin_entrypoint(origin)
                break
        return first_prompt, model, started, entrypoint

    def _tail_metadata(
        self, wire_path: Path
    ) -> Tuple[str, str]:
        last_prompt = ""
        model = ""
        if not wire_path.is_file():
            return last_prompt, model
        for record in iter_tail_records(wire_path, TAIL_BYTES):
            record_type = record.get("type")
            if record_type in ("llm.request", "usage.record"):
                candidate = record.get("model")
                if isinstance(candidate, str) and candidate.strip():
                    model = candidate.strip()
            if record_type == "turn.prompt":
                origin = record.get("origin") or {}
                if isinstance(origin, dict) and origin.get("kind") == "user":
                    text = _extract_text(record.get("input"))
                    if _meaningful_prompt(text):
                        last_prompt = block_text(
                            _clean_prompt(text), MAX_PROMPT_CHARS
                        )
            elif record_type == "turn.steer":
                origin = record.get("origin") or {}
                if isinstance(origin, dict) and origin.get("kind") == "user":
                    text = _extract_text(record.get("input"))
                    if _meaningful_prompt(text):
                        last_prompt = block_text(
                            _clean_prompt(text), MAX_PROMPT_CHARS
                        )
        return last_prompt, model

    def summarize(self, path: Path) -> SessionSummary:
        session_dir = self._session_dir_for(path)
        state = self._read_state(session_dir) if session_dir is not None else {}
        if session_dir is None:
            session_dir = path.parent
        wire = self._wire_path(session_dir)
        event = self._event_path(session_dir)
        if wire.is_file():
            primary = wire
        elif event.is_file():
            primary = event
        else:
            primary = path

        session_id = _session_id_from_name(
            str(state.get("id") or session_dir.name or self.session_id_for(path))
        )
        cwd = str(state.get("cwd") or state.get("workDir") or "")
        started = parse_timestamp(state.get("createdAt"))
        updated = parse_timestamp(state.get("updatedAt"))
        title = str(state.get("title") or "")
        last_prompt = ""
        raw_last = state.get("lastPrompt")
        if isinstance(raw_last, str) and _meaningful_prompt(raw_last):
            last_prompt = block_text(_clean_prompt(raw_last), MAX_PROMPT_CHARS)

        first_prompt = ""
        entrypoint = ""
        if event.is_file():
            first_prompt, event_cwd, entrypoint, event_started = (
                self._first_prompt_from_events(event)
            )
            if not cwd:
                cwd = event_cwd
            if started is None:
                started = event_started

        if not cwd:
            cwd = self._index_cwd(session_id)

        model = ""
        wire_started: Optional[datetime] = None
        if not first_prompt:
            (
                wire_first,
                model,
                wire_started,
                wire_entrypoint,
            ) = self._first_prompt_from_wire(wire)
            first_prompt = wire_first
            if not entrypoint:
                entrypoint = wire_entrypoint

        if not last_prompt or not model:
            tail_prompt, tail_model = self._tail_metadata(wire)
            if not last_prompt:
                last_prompt = tail_prompt
            model = tail_model or model

        if not model and wire.is_file():
            _, model, wire_started, _ = self._first_prompt_from_wire(wire)

        if started is None:
            started = wire_started

        if not first_prompt:
            first_prompt = last_prompt
        if not last_prompt:
            last_prompt = first_prompt
        if not updated:
            updated = datetime.fromtimestamp(self._mtime(primary), tz=UTC)
        if not title or _is_generic(title):
            title = _choose_title(first_prompt, last_prompt) or session_id

        try:
            size = primary.stat().st_size
        except OSError:
            size = 0

        return SessionSummary(
            harness=self.name,
            session_id=session_id,
            path=primary,
            cwd=cwd,
            updated=updated,
            title=title,
            first_prompt=first_prompt,
            last_prompt=last_prompt,
            started=started,
            model=model,
            entrypoint=entrypoint,
            size=size,
            variants=entrypoint or self.variants,
            archived=state.get("archived") is True,
        )

    def _iter_event_prompts(self, event_path: Path) -> Iterator[UserPrompt]:
        seen = set()
        for envelope in self._iter_events(event_path):
            envelope_type = envelope.get("type")
            payload = envelope.get("payload") or {}
            if not isinstance(payload, dict) or not _is_main_agent(payload):
                continue
            if envelope_type == "prompt.submitted":
                identifier = payload.get("promptId") or payload.get(
                    "userMessageId"
                )
                text = _extract_text(payload.get("content"))
            elif envelope_type == "turn.steer":
                origin = payload.get("origin") or {}
                if not isinstance(origin, dict) or origin.get("kind") != "user":
                    continue
                identifier = payload.get("messageId")
                text = _extract_text(payload.get("input"))
            else:
                continue
            if identifier in seen:
                continue
            if not _meaningful_prompt(text):
                continue
            if identifier:
                seen.add(identifier)
            yield UserPrompt(
                text=_clean_prompt(text),
                timestamp=_payload_time(payload),
            )

    def _iter_wire_prompts(self, wire_path: Path) -> Iterator[UserPrompt]:
        seen = set()
        for record in iter_file_records(wire_path):
            record_type = record.get("type")
            if record_type == "turn.prompt":
                identifier = record.get("promptId")
                origin = record.get("origin") or {}
                if not isinstance(origin, dict) or origin.get("kind") != "user":
                    continue
                text = _extract_text(record.get("input"))
            elif record_type == "turn.steer":
                identifier = record.get("messageId")
                origin = record.get("origin") or {}
                if not isinstance(origin, dict) or origin.get("kind") != "user":
                    continue
                text = _extract_text(record.get("input"))
            else:
                continue
            if identifier in seen:
                continue
            if not _meaningful_prompt(text):
                continue
            if identifier:
                seen.add(identifier)
            yield UserPrompt(
                text=_clean_prompt(text),
                timestamp=parse_timestamp(record.get("time")),
            )

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        session_dir = self._session_dir_for(summary.path)
        if session_dir is None:
            return
        event = self._event_path(session_dir)
        found = False
        if event.is_file():
            for prompt in self._iter_event_prompts(event):
                found = True
                yield prompt
        if found:
            return
        wire = self._wire_path(session_dir)
        if wire.is_file():
            yield from self._iter_wire_prompts(wire)

    def _load_wire(self, summary: SessionSummary, wire: Path) -> SessionDetail:
        exchanges: Deque[Exchange] = deque(maxlen=50)
        current: Optional[Exchange] = None
        compact_summary = ""
        tool_counts: Counter = Counter()
        recent_tools: Deque[ToolCall] = deque(maxlen=20)
        edited: "OrderedDict[str, int]" = OrderedDict()
        todos: List[Dict[str, Any]] = []
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

        for record in iter_file_records(wire):
            record_type = record.get("type")
            timestamp = parse_timestamp(record.get("time"))
            if timestamp is not None:
                if started is None or timestamp < started:
                    started = timestamp
                if updated is None or timestamp > updated:
                    updated = timestamp

            if record_type in ("turn.prompt", "turn.steer"):
                origin = record.get("origin") or {}
                if not isinstance(origin, dict) or origin.get("kind") != "user":
                    continue
                text = _extract_text(record.get("input"))
                if not _meaningful_prompt(text):
                    continue
                append_current()
                cleaned = block_text(
                    _clean_prompt(text), MAX_PROMPT_CHARS
                )
                current = Exchange(user_text=cleaned, timestamp=timestamp)
                turn_count += 1
                last_prompt = cleaned
                if not first_prompt:
                    first_prompt = cleaned
                continue

            if record_type == "agent.message.appended":
                message = record.get("message")
                if not isinstance(message, dict):
                    continue
                body = message.get("message")
                if not isinstance(body, dict) or body.get("role") != "assistant":
                    continue
                content = body.get("content")
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") != "text":
                            continue
                        text = block.get("text")
                        if not isinstance(text, str) or not text.strip():
                            continue
                        if current is None:
                            current = Exchange(timestamp=timestamp)
                        current.assistant_texts.append(
                            block_text(text, MAX_ASSISTANT_CHARS)
                        )
                        if len(current.assistant_texts) > 3:
                            current.assistant_texts = current.assistant_texts[-3:]
                for call in body.get("toolCalls") or []:
                    if not isinstance(call, dict):
                        continue
                    name = str(call.get("name") or "tool")
                    args = _parse_tool_args(call.get("arguments"))
                    tool = ToolCall(
                        name=name,
                        detail=_tool_detail(name, args),
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
                        file_path = _file_path(args, cwd)
                        if file_path:
                            edited[file_path] = edited.get(file_path, 0) + 1
                continue

            if record_type == "tools.update_store":
                if record.get("key") == "todo" and isinstance(
                    record.get("value"), list
                ):
                    todos = _normalize_todos(record.get("value"))
                continue

            if record_type == "context.apply_compaction":
                candidate = record.get("summary") or record.get(
                    "contextSummary"
                )
                if isinstance(candidate, str) and candidate.strip():
                    compact_summary = block_text(
                        candidate, MAX_SUMMARY_CHARS
                    )
                continue

            if record_type == "llm.request":
                candidate = record.get("model")
                if isinstance(candidate, str) and candidate.strip():
                    model = candidate.strip()

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

    def _load_events(
        self, summary: SessionSummary, event: Path
    ) -> SessionDetail:
        exchanges: Deque[Exchange] = deque(maxlen=50)
        current: Optional[Exchange] = None
        compact_summary = ""
        tool_counts: Counter = Counter()
        recent_tools: Deque[ToolCall] = deque(maxlen=20)
        edited: "OrderedDict[str, int]" = OrderedDict()
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

        for envelope in self._iter_events(event):
            envelope_type = envelope.get("type")
            payload = envelope.get("payload") or {}
            if not isinstance(payload, dict) or not _is_main_agent(payload):
                continue
            timestamp = _payload_time(payload)
            if envelope_type in ("prompt.submitted", "turn.steer"):
                if envelope_type == "turn.steer":
                    origin = payload.get("origin") or {}
                    if not isinstance(origin, dict) or origin.get("kind") != "user":
                        continue
                    text = _extract_text(payload.get("input"))
                else:
                    text = _extract_text(payload.get("content"))
                if not _meaningful_prompt(text):
                    continue
                append_current()
                cleaned = block_text(
                    _clean_prompt(text), MAX_PROMPT_CHARS
                )
                current = Exchange(user_text=cleaned, timestamp=timestamp)
                turn_count += 1
                last_prompt = cleaned
                if not first_prompt:
                    first_prompt = cleaned
                continue

            if envelope_type == "tool.call.started":
                name = str(payload.get("name") or "tool")
                args = payload.get("args")
                tool = ToolCall(
                    name=name,
                    detail=_tool_detail(name, args),
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
                    file_path = _file_path(args, summary.cwd)
                    if file_path:
                        edited[file_path] = edited.get(file_path, 0) + 1
                continue

            if envelope_type == "compaction.completed":
                result = payload.get("result") or {}
                candidate = result.get("summary")
                if isinstance(candidate, str) and candidate.strip():
                    compact_summary = block_text(
                        candidate, MAX_SUMMARY_CHARS
                    )

        append_current()
        summary.first_prompt = first_prompt
        summary.last_prompt = last_prompt
        edited_files = [
            {"path": path, "count": count}
            for path, count in list(edited.items())[-30:]
        ]
        return SessionDetail(
            summary=summary,
            compact_summary=compact_summary,
            todos=[],
            exchanges=list(exchanges),
            edited_files=edited_files,
            tool_counts=dict(tool_counts.most_common()),
            recent_tools=list(recent_tools),
            turn_count=turn_count,
        )

    def load(self, summary: SessionSummary) -> SessionDetail:
        session_dir = self._session_dir_for(summary.path)
        if session_dir is not None:
            wire = self._wire_path(session_dir)
            if wire.is_file():
                return self._load_wire(summary, wire)
            event = self._event_path(session_dir)
            if event.is_file():
                return self._load_events(summary, event)
        return SessionDetail(summary=summary)
