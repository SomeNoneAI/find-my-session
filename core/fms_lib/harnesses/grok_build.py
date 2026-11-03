from __future__ import annotations

import json
import os
import re
from collections import Counter, OrderedDict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple
from urllib.parse import unquote

from ..models import Exchange, SessionDetail, SessionSummary, ToolCall, UserPrompt
from ..util import (
    UTC,
    block_text,
    iter_file_records,
    iter_head_records,
    normalize_text,
    one_line,
    parse_timestamp,
)
from .base import HarnessAdapter
from .common import (
    choose_title as _choose_title,
)
from .common import (
    file_path,
    tool_detail_for,
)
from .common import (
    is_generic as _is_generic,
)

HEAD_BYTES = 2_000_000
HEAD_RECORDS = 400
TAIL_BYTES = 1_500_000
MAX_TAIL_BYTES = 16_000_000
MAX_PROMPT_CHARS = 4_000
MAX_SUMMARY_CHARS = 20_000
MAX_ASSISTANT_CHARS = 5_000
MAX_CHECKPOINT_BYTES = 4_000_000

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
_ABSOLUTE_RE = re.compile(r"^(?:/|[A-Za-z]:[\\/])")
_CONTINUATION_PREFIX = "This session is being continued from a previous conversation"

EDIT_TOOLS = {
    "search_replace",
    "write",
}

FILE_KEYS = ("file_path", "target_file", "path")

TOOL_DETAIL_KEYS = {
    "read_file": ("target_file", "file_path", "path"),
    "write": ("file_path", "path"),
    "search_replace": ("file_path", "path"),
    "run_terminal_command": ("command",),
    "monitor": ("command",),
    "grep": ("pattern",),
    "list_dir": ("target_directory", "path"),
    "spawn_subagent": ("description",),
    "memory_search": ("query",),
    "search_tool": ("query",),
    "web_fetch": ("url",),
    "image_gen": ("prompt",),
    "scheduler_create": ("prompt",),
    "scheduler_delete": ("id",),
}


def _strip_hash(path: Path) -> Path:
    text = str(path)
    if "#" in text:
        return Path(text.split("#", 1)[0]).expanduser()
    return path


def _update_of(record: Dict[str, Any]) -> Dict[str, Any]:
    params = record.get("params")
    if not isinstance(params, dict):
        return {}
    update = params.get("update")
    return update if isinstance(update, dict) else {}


def _iter_updates(path: Path) -> Iterator[Tuple[Dict[str, Any], Dict[str, Any]]]:
    for record in iter_file_records(path):
        update = _update_of(record)
        if update:
            yield record, update


def _text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if content.get("type") != "text":
            return ""
        text = content.get("text")
        return text if isinstance(text, str) else ""
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
    if text.startswith(_CONTINUATION_PREFIX):
        return ""
    if _SLASH_COMMAND_RE.fullmatch(text):
        return ""
    if _INTERRUPT_RE.fullmatch(text):
        return ""
    return text


def _prompt_from_update(record: Dict[str, Any], update: Dict[str, Any]) -> str:
    if update.get("sessionUpdate") != "user_message_chunk":
        return ""
    meta = update.get("_meta")
    if isinstance(meta, dict):
        if meta.get("hideFromScrollback") or meta.get("syntheticPrompt"):
            return ""
    return _prompt_from_text(_text_content(update.get("content")))


def _prompts_from_records(
    records: Iterable[Dict[str, Any]],
) -> Iterator[Tuple[str, Optional[datetime]]]:
    parts: List[str] = []
    stamp: Optional[datetime] = None
    key: Any = None
    pending = False

    def flush() -> Optional[Tuple[str, Optional[datetime]]]:
        nonlocal parts, stamp, key, pending
        cleaned = _prompt_from_text("\n".join(parts))
        result = (cleaned, stamp) if cleaned else None
        parts = []
        stamp = None
        key = None
        pending = False
        return result

    for record in records:
        update = _update_of(record)
        if not update:
            continue
        kind = update.get("sessionUpdate")
        if kind == "user_message_chunk":
            meta = update.get("_meta")
            if isinstance(meta, dict) and (
                meta.get("hideFromScrollback") or meta.get("syntheticPrompt")
            ):
                continue
            text = _text_content(update.get("content"))
            if not text.strip():
                continue
            next_key = meta.get("promptIndex") if isinstance(meta, dict) else None
            if pending and next_key == key:
                parts.append(text)
                continue
            if pending:
                item = flush()
                if item is not None:
                    yield item
            parts = [text]
            stamp = parse_timestamp(record.get("timestamp"))
            key = next_key
            pending = True
            continue
        if pending:
            item = flush()
            if item is not None:
                yield item
    if pending:
        item = flush()
        if item is not None:
            yield item


def _iter_prompt_events(
    path: Path,
) -> Iterator[Tuple[str, Optional[datetime]]]:
    return _prompts_from_records(iter_file_records(path))


def _load_json_object(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _read_jsonl_tail(
    path: Path,
    initial: int = TAIL_BYTES,
    maximum: int = MAX_TAIL_BYTES,
) -> List[Dict[str, Any]]:
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size <= 0:
        return []
    window = min(initial, size)
    while True:
        start = max(0, size - window)
        try:
            with open(path, "rb") as handle:
                handle.seek(start)
                data = handle.read()
        except OSError:
            return []
        lines = data.split(b"\n")
        if start > 0 and lines:
            lines = lines[1:]
        if lines and lines[-1] == b"":
            lines.pop()
        records: List[Dict[str, Any]] = []
        for raw in lines:
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
                continue
            if isinstance(record, dict):
                records.append(record)
        if records or start == 0 or window >= maximum:
            return records
        window = min(maximum, window * 2)


def _first_prompt(
    records: Iterable[Dict[str, Any]],
) -> Tuple[str, Optional[datetime]]:
    for text, stamp in _prompts_from_records(records):
        return block_text(text, MAX_PROMPT_CHARS), stamp
    return "", None


def _last_prompt(
    path: Path,
    head: Iterable[Dict[str, Any]],
) -> Tuple[str, Optional[datetime]]:
    last: Tuple[str, Optional[datetime]] = ("", None)
    for text, stamp in _prompts_from_records(_read_jsonl_tail(path)):
        last = (block_text(text, MAX_PROMPT_CHARS), stamp)
    if last[0]:
        return last
    for text, stamp in _prompts_from_records(head):
        last = (block_text(text, MAX_PROMPT_CHARS), stamp)
    return last


def _is_subagent_kind(value: Any) -> bool:
    return isinstance(value, str) and value.strip().casefold().startswith("subagent")


def _group_cwd(group: Path) -> str:
    marker = group / ".cwd"
    if marker.is_file():
        try:
            text = marker.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            text = ""
        if text:
            return text
    try:
        decoded = unquote(group.name)
    except ValueError:
        return ""
    return decoded if _ABSOLUTE_RE.match(decoded) else ""


def _file_mtime(path: Path) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return None


def _file_path(arguments: Any, cwd: str) -> str:
    return file_path(arguments, cwd, FILE_KEYS)


def _tool_detail(name: str, arguments: Any) -> str:
    return tool_detail_for(name, arguments, TOOL_DETAIL_KEYS)


def _normalize_todos(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("todos") or value.get("entries")
    if not isinstance(value, list):
        return []
    todos: List[Dict[str, Any]] = []
    for item in value:
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


def _remove_found_tokens(
    path: Path,
    remaining: Set[str],
    chunk_size: int = 4 * 1024 * 1024,
) -> None:
    overlap = b""
    try:
        with open(path, "rb") as handle:
            while remaining:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                data = overlap + chunk
                text = normalize_text(data.decode("utf-8", "ignore"))
                for token in tuple(remaining):
                    if token in text:
                        remaining.discard(token)
                overlap = data[-512:]
    except OSError:
        return


class GrokBuildAdapter(HarnessAdapter):
    """Grok Build TUI, headless, and ACP sessions share one local store."""

    name = "grok-build"
    aliases = ("grok-build", "grok", "grok-cli")
    variants = "tui, headless, acp"
    store_hint = "~/.grok"
    home_env = "FMS_GROK_HOME"

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".grok"

    def session_roots(self) -> List[Path]:
        return [self.home() / "sessions"]

    def _session_dir(self, path: Path) -> Optional[Path]:
        base = _strip_hash(path)
        try:
            candidate = base if base.is_dir() else base.parent
            root = (self.home() / "sessions").resolve()
            relative = candidate.resolve().relative_to(root)
        except (OSError, ValueError):
            return None
        parts = relative.parts
        if len(parts) != 2:
            return None
        if (candidate / "summary.json").is_file() or (
            candidate / "updates.jsonl"
        ).is_file():
            return candidate
        return None

    def _subagent_ids(self) -> Set[str]:
        root = self.home() / "sessions"
        ids: Set[str] = set()
        if not root.is_dir():
            return ids
        for group in root.iterdir():
            if not group.is_dir():
                continue
            try:
                sessions = list(group.iterdir())
            except OSError:
                continue
            for session_dir in sessions:
                subagents = session_dir / "subagents"
                if not subagents.is_dir():
                    continue
                try:
                    for child in subagents.iterdir():
                        if child.is_dir():
                            ids.add(child.name)
                except OSError:
                    continue
        return ids

    def _has_subagent_parent(self, session_dir: Path) -> bool:
        group = session_dir.parent
        name = session_dir.name
        try:
            for sibling in group.iterdir():
                if sibling.name == name or not sibling.is_dir():
                    continue
                if (sibling / "subagents" / name).is_dir():
                    return True
        except OSError:
            return False
        return False

    def _is_subagent(self, session_dir: Path, data: Dict[str, Any]) -> bool:
        if _is_subagent_kind(data.get("session_kind")):
            return True
        return self._has_subagent_parent(session_dir)

    def iter_session_paths(self) -> Iterator[Path]:
        root = self.home() / "sessions"
        if not root.is_dir():
            return
        subagents = self._subagent_ids()
        pending: List[Tuple[float, Path]] = []
        for group in root.iterdir():
            if not group.is_dir():
                continue
            try:
                sessions = list(group.iterdir())
            except OSError:
                continue
            for session_dir in sessions:
                if not session_dir.is_dir() or session_dir.name in subagents:
                    continue
                updates = session_dir / "updates.jsonl"
                summary = session_dir / "summary.json"
                if not updates.is_file() or not summary.is_file():
                    continue
                try:
                    if updates.stat().st_size <= 0:
                        continue
                    mtime = updates.stat().st_mtime
                except OSError:
                    continue
                pending.append((mtime, updates))
        pending.sort(key=lambda item: item[0], reverse=True)
        for _, path in pending:
            data = _load_json_object(path.parent / "summary.json")
            if data is None or _is_subagent_kind(data.get("session_kind")):
                continue
            yield path

    def session_id_for(self, path: Path) -> str:
        session_dir = self._session_dir(path)
        if session_dir is not None:
            return session_dir.name
        return _strip_hash(path).stem

    def owns(self, path: Path) -> bool:
        return self._session_dir(path) is not None

    def summarize(self, path: Path) -> SessionSummary:
        session_dir = self._session_dir(path)
        if session_dir is None:
            raise ValueError("not a Grok Build session: %s" % path)
        updates = session_dir / "updates.jsonl"
        if not updates.is_file():
            raise ValueError("cannot read Grok Build transcript: %s" % updates)
        data = _load_json_object(session_dir / "summary.json") or {}
        if self._is_subagent(session_dir, data):
            raise ValueError(
                "Grok Build subagent session is not resumable: %s" % path
            )

        info = data.get("info")
        info = info if isinstance(info, dict) else {}
        session_id = info.get("id")
        if not isinstance(session_id, str) or not session_id.strip():
            session_id = session_dir.name
        else:
            session_id = session_id.strip()

        cwd = info.get("cwd")
        cwd = cwd.strip() if isinstance(cwd, str) else ""
        if not cwd:
            cwd = _group_cwd(session_dir.parent)

        started = parse_timestamp(data.get("created_at"))
        updated = parse_timestamp(data.get("updated_at")) or parse_timestamp(
            data.get("last_active_at")
        )
        if updated is None:
            updated = _file_mtime(updates)
        if updated is None:
            updated = datetime.now(tz=UTC)
        if started is None:
            started = updated

        head = list(iter_head_records(updates, HEAD_BYTES, HEAD_RECORDS))
        first_prompt, _ = _first_prompt(head)
        last_prompt, _ = _last_prompt(updates, head)
        if not first_prompt:
            first_prompt = last_prompt
        if not last_prompt:
            last_prompt = first_prompt

        title = one_line(str(data.get("generated_title") or ""), 200)
        if not title or _is_generic(title):
            summary_text = one_line(str(data.get("session_summary") or ""), 200)
            if summary_text and not _is_generic(summary_text):
                title = summary_text
            else:
                title = _choose_title(first_prompt, last_prompt) or session_id

        branch = data.get("head_branch")
        branch = branch.strip() if isinstance(branch, str) else ""
        model = data.get("current_model_id")
        model = model.strip() if isinstance(model, str) else ""

        try:
            size = updates.stat().st_size
        except OSError:
            size = 0

        return SessionSummary(
            harness=self.name,
            session_id=session_id,
            path=updates,
            cwd=cwd,
            updated=updated,
            title=title,
            first_prompt=first_prompt,
            last_prompt=last_prompt,
            started=started,
            branch=branch,
            model=model,
            entrypoint="",
            version="",
            size=size,
            variants=self.variants,
            archived=False,
        )

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        for text, stamp in _iter_prompt_events(summary.path):
            yield UserPrompt(text=text, timestamp=stamp)

    def _compaction_summary(self, session_dir: Path) -> str:
        folder = session_dir / "compaction_checkpoints"
        if not folder.is_dir():
            return ""
        try:
            candidates = sorted(
                (path for path in folder.glob("*.json") if path.is_file()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )[:5]
        except OSError:
            return ""
        best_key: Optional[Tuple[int, int]] = None
        best = ""
        for path in candidates:
            try:
                if path.stat().st_size > MAX_CHECKPOINT_BYTES:
                    continue
            except OSError:
                continue
            data = _load_json_object(path)
            if data is None:
                continue
            index = data.get("prompt_index_at_compaction")
            index = index if isinstance(index, int) else -1
            try:
                key = (index, path.stat().st_mtime_ns)
            except OSError:
                key = (index, 0)
            history = data.get("compacted_history")
            if not isinstance(history, list):
                continue
            for item in history:
                if not isinstance(item, dict):
                    continue
                text = _text_content(item.get("content"))
                if not text.lstrip().startswith(_CONTINUATION_PREFIX):
                    continue
                if best_key is None or key > best_key:
                    best_key = key
                    best = block_text(text, MAX_SUMMARY_CHARS)
                break
        return best

    def load(self, summary: SessionSummary) -> SessionDetail:
        exchanges: Deque[Exchange] = deque(maxlen=50)
        current: Optional[Exchange] = None
        current_index: Any = None
        tool_counts: Counter = Counter()
        recent_tools: Deque[ToolCall] = deque(maxlen=20)
        edited: "OrderedDict[str, int]" = OrderedDict()
        cwd = summary.cwd
        model = summary.model
        first_prompt = summary.first_prompt
        last_prompt = summary.last_prompt
        todos: List[Dict[str, Any]] = []
        turn_count = 0

        def append_current() -> None:
            nonlocal current, current_index
            if current is None:
                return
            if current.user_text or current.assistant_texts or current.tools:
                exchanges.append(current)
            current = None
            current_index = None

        for record, update in _iter_updates(summary.path):
            kind = update.get("sessionUpdate")

            if kind == "user_message_chunk":
                meta = update.get("_meta")
                if isinstance(meta, dict):
                    candidate = meta.get("modelId")
                    if isinstance(candidate, str) and candidate.strip():
                        model = candidate.strip()
                    if meta.get("hideFromScrollback") or meta.get("syntheticPrompt"):
                        continue
                text = _prompt_from_update(record, update)
                if not text:
                    continue
                index = meta.get("promptIndex") if isinstance(meta, dict) else None
                cleaned = block_text(text, MAX_PROMPT_CHARS)
                if current is not None and index is not None and index == current_index:
                    current.user_text = (
                        current.user_text + "\n" + cleaned
                        if current.user_text
                        else cleaned
                    )
                    last_prompt = current.user_text
                    continue
                append_current()
                current = Exchange(
                    user_text=cleaned,
                    timestamp=parse_timestamp(record.get("timestamp")),
                )
                current_index = index
                turn_count += 1
                last_prompt = cleaned
                if not first_prompt:
                    first_prompt = cleaned
                continue

            if kind == "agent_message_chunk":
                text = _text_content(update.get("content"))
                if not text.strip():
                    continue
                if current is None:
                    current = Exchange(
                        timestamp=parse_timestamp(record.get("timestamp"))
                    )
                current.assistant_texts.append(
                    block_text(text, MAX_ASSISTANT_CHARS)
                )
                if len(current.assistant_texts) > 3:
                    current.assistant_texts = current.assistant_texts[-3:]
                continue

            if kind == "tool_call":
                title = update.get("title")
                if not isinstance(title, str) or not title.strip():
                    continue
                name = title.strip().rstrip(":").strip()
                if not name:
                    continue
                arguments = update.get("rawInput")
                call = ToolCall(
                    name=name,
                    detail=_tool_detail(name, arguments),
                    timestamp=parse_timestamp(record.get("timestamp")),
                )
                if current is None:
                    current = Exchange(
                        timestamp=parse_timestamp(record.get("timestamp"))
                    )
                current.tools.append(call)
                if len(current.tools) > 8:
                    current.tools = current.tools[-8:]
                tool_counts[name] += 1
                recent_tools.append(call)
                if name == "todo_write":
                    todos = _normalize_todos(
                        arguments.get("todos") if isinstance(arguments, dict) else None
                    )
                if name in EDIT_TOOLS:
                    path_value = _file_path(arguments, cwd)
                    if path_value:
                        edited[path_value] = edited.get(path_value, 0) + 1
                continue

            if kind == "plan":
                todos = _normalize_todos(update.get("entries"))
                continue

        append_current()

        if not first_prompt:
            first_prompt = last_prompt
        summary.cwd = cwd or summary.cwd
        summary.model = model
        summary.first_prompt = first_prompt
        summary.last_prompt = last_prompt

        edited_files = [
            {"path": path, "count": count}
            for path, count in list(edited.items())[-30:]
        ]
        session_dir = summary.path.parent
        compact_summary = self._compaction_summary(session_dir)

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

    def contains(
        self, summary: SessionSummary, tokens: Sequence[str]
    ) -> bool:
        remaining = {normalize_text(token) for token in tokens if token}
        remaining.discard("")
        if not remaining:
            return True
        session_dir = summary.path.parent
        files: List[Path] = [summary.path]
        chat = session_dir / "chat_history.jsonl"
        if chat.is_file():
            files.append(chat)
        compaction = session_dir / "compaction"
        if compaction.is_dir():
            files.extend(sorted(compaction.glob("*.md")))
        checkpoints = session_dir / "compaction_checkpoints"
        if checkpoints.is_dir():
            files.extend(sorted(checkpoints.glob("*.json")))
        for path in files:
            _remove_found_tokens(path, remaining)
            if not remaining:
                return True
        return not remaining
