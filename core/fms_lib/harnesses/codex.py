"""Adapter for OpenAI ChatGPT Codex sessions.

Codex stores one rollout JSONL per thread segment under
``~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-<timestamp>-<id>.jsonl`` (often
zstd-compressed as ``.jsonl.zst``). Resumed threads rotate into a new segment
whose ``session_meta.history_base`` points at the previous segment and whose
top-level ``ordinal`` continues the thread, so the full transcript is the
concatenation of the segment chain. Archived threads move to
``~/.codex/archived_sessions/``. Titles live in ``session_index.jsonl``.

Everything here is read-only. Compressed rollouts are streamed through
``compression.zstd`` on Python 3.14+ or the ``zstd`` CLI; without either, the
compressed sessions cannot be decoded and are skipped.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections import Counter, OrderedDict, deque
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Deque,
    Dict,
    Iterator,
    List,
    Literal,
    Optional,
    Sequence,
    Tuple,
)

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
from .common import choose_title as _choose_title
from .common import file_path
from .common import is_generic as _is_generic

try:  # Python 3.14+
    from compression import zstd as _zstd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised on older interpreters
    _zstd = None

HEAD_BYTES = 512_000
HEAD_RECORDS = 120
TAIL_BYTES = 1_000_000
MAX_PROMPT_CHARS = 4_000
MAX_SUMMARY_CHARS = 20_000
MAX_ASSISTANT_CHARS = 5_000

ROLLOUT_RE = re.compile(
    r"^rollout-(\d{4}-\d{2}-\d{2})T(\d{2}-\d{2}-\d{2})-"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"(?:_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}))?"
    r"\.jsonl(?:\.zst)?$"
)

PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$", re.M)
TIMESTAMP_RE = re.compile(rb'"timestamp"\s*:\s*"([^"]+)"')
USER_ROLE_RE = re.compile(rb'"role"\s*:\s*"user"')
TURN_CONTEXT_RE = re.compile(rb'"type"\s*:\s*"turn_context"')

BROWSER_CONTEXT_RE = re.compile(
    r"<in-app-browser-context\b[^>]*>.*?</in-app-browser-context>", re.S
)
REMINDER_RE = re.compile(r"<system-reminder\b[^>]*>.*?</system-reminder>", re.S)
PROMPT_HOOK_RE = re.compile(
    r"<user-prompt-submit-hook>.*?</user-prompt-submit-hook>", re.S
)
ENVIRONMENT_RE = re.compile(r"<environment_context>.*?</environment_context>", re.S)

REQUEST_MARKER = "## My request for Codex:"
BROWSER_COMMENT_MARKER = "\nComment:"

INJECTED_PREFIXES = (
    "# agents.md instructions",
    "# browser comments:",
    "# files mentioned by the user:",
    "<environment_context>",
    "<skill>",
    "<turn_aborted>",
    "<recommended_plugins>",
    "<user_instructions>",
    "<system-reminder",
    "<task-notification>",
    "## referenced chatgpt conversation:",
    "the following is the codex agent history",
)

EDIT_TOOLS = {"apply_patch"}


def _parse_rollout_name(path: Path) -> Optional[Tuple[str, str, Tuple[str, str]]]:
    """Return ``(session id, segment id, timestamp key)`` for a rollout file."""

    match = ROLLOUT_RE.match(path.name)
    if match is None:
        return None
    session_id = match.group(3)
    segment_id = match.group(4) or session_id
    stamp = (match.group(1), match.group(2))
    return session_id, segment_id, stamp


class _ProcessStream:
    """Wrap a ``zstd`` subprocess stdout as a context-managed binary stream."""

    def __init__(self, process: "subprocess.Popen[bytes]") -> None:
        self._process = process

    def __enter__(self):
        return self._process.stdout

    def __exit__(self, exc_type, exc, tb) -> "Literal[False]":
        stream = self._process.stdout
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
        if self._process.poll() is None:
            self._process.kill()
        try:
            self._process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        return False


def _open_zstd(path: Path):
    if _zstd is not None:
        return _zstd.ZstdFile(path, "rb")
    executable = shutil.which("zstd")
    if not executable:
        raise ValueError(
            "zstd decoder unavailable; install the zstd CLI or use Python 3.14+"
        )
    process = subprocess.Popen(
        [executable, "-dc", "--quiet", "--", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return _ProcessStream(process)


def _iter_raw_lines(path: Path) -> Iterator[bytes]:
    if not path.name.endswith(".zst"):
        with open(path, "rb") as handle:
            for raw in handle:
                yield raw
        return

    with _open_zstd(path) as handle:
        iterator = iter(handle)
        while True:
            try:
                raw = next(iterator)
            except StopIteration:
                return
            except OSError:
                raise
            except Exception as exc:
                raise OSError("cannot decompress %s: %s" % (path, exc)) from exc
            yield raw


def _iter_head_records(
    path: Path,
    max_bytes: int = HEAD_BYTES,
    max_records: int = HEAD_RECORDS,
) -> Iterator[Dict[str, Any]]:
    total = 0
    count = 0
    for raw in _iter_raw_lines(path):
        total += len(raw)
        count += 1
        record = load_json_object(raw)
        if record is not None:
            yield record
        if total >= max_bytes or count >= max_records:
            break


def _iter_records(path: Path) -> Iterator[Dict[str, Any]]:
    for raw in _iter_raw_lines(path):
        record = load_json_object(raw)
        if record is not None:
            yield record


def _iter_raw_chunks(
    path: Path, chunk_size: int = 4 * 1024 * 1024
) -> Iterator[bytes]:
    """Yield decompressed bytes without whole-file JSON parsing."""

    if not path.name.endswith(".zst"):
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    return
                yield chunk

    with _open_zstd(path) as handle:
        while True:
            try:
                chunk = handle.read(chunk_size)
            except OSError:
                raise
            except Exception as exc:
                raise OSError("cannot decompress %s: %s" % (path, exc)) from exc
            if not chunk:
                return
            yield chunk


def _parse_lines(lines: Sequence[bytes]) -> List[Dict[str, Any]]:
    return [record for record in (load_json_object(raw) for raw in lines) if record]


def _scan_session(path: Path) -> Tuple[List[bytes], List[bytes]]:
    """One streaming pass returning bounded head lines and tail lines.

    The split point is included in the head, so every line of a short session
    ends up in the head and the tail stays empty.
    """

    head: List[bytes] = []
    tail: Deque[bytes] = deque()
    head_total = 0
    tail_total = 0
    head_done = False
    for raw in _iter_raw_lines(path):
        if not head_done:
            head.append(raw)
            head_total += len(raw)
            if len(head) >= HEAD_RECORDS or head_total >= HEAD_BYTES:
                head_done = True
            continue
        tail.append(raw)
        tail_total += len(raw)
        while tail_total > TAIL_BYTES and len(tail) > 1:
            tail_total -= len(tail.popleft())
    return head, list(tail)


def _latest_timestamp(lines: Sequence[bytes]) -> Optional[datetime]:
    for raw in reversed(lines):
        match = TIMESTAMP_RE.search(raw)
        if match is not None:
            parsed = parse_timestamp(match.group(1).decode("utf-8", "replace"))
            if parsed is not None:
                return parsed
    return None


def _meta_from_records(records: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for record in records:
        if record.get("type") != "session_meta":
            continue
        payload = record.get("payload")
        return payload if isinstance(payload, dict) else None
    return None


def _content_text(payload: Dict[str, Any]) -> str:
    content = payload.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text)
    return "\n".join(parts)


def _strip_context_blocks(value: str) -> str:
    text = BROWSER_CONTEXT_RE.sub("", value)
    index = text.find("<in-app-browser-context")
    if index >= 0:
        text = text[:index]
    return text.strip()


def _clean_prompt(value: str) -> str:
    text = REMINDER_RE.sub("", value)
    text = PROMPT_HOOK_RE.sub("", text)
    text = ENVIRONMENT_RE.sub("", text)
    return text.strip()


def _request_section(value: str) -> str:
    index = value.rfind(REQUEST_MARKER)
    if index < 0:
        return ""
    return value[index + len(REQUEST_MARKER) :].strip()


def _browser_comment(value: str) -> str:
    index = value.find(BROWSER_COMMENT_MARKER)
    if index < 0:
        return ""
    return value[index + len(BROWSER_COMMENT_MARKER) :].strip()


def _prompt_from_record(record: Dict[str, Any]) -> str:
    if record.get("type") != "response_item":
        return ""
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return ""
    if payload.get("type") != "message" or payload.get("role") != "user":
        return ""
    metadata = payload.get("internal_chat_message_metadata_passthrough")
    kinds = metadata.get("content_item_kinds") if isinstance(metadata, dict) else None
    if isinstance(kinds, list) and kinds:
        if not all(
            isinstance(kind, str) and kind.casefold().startswith("user.")
            for kind in kinds
        ):
            return ""

    text = _content_text(payload)
    if not text.strip():
        return ""
    text = _strip_context_blocks(text)
    request = _request_section(text)
    if request:
        text = request
    elif text.lstrip().casefold().startswith("# browser comments:"):
        text = _browser_comment(text)
    if not text.strip():
        return ""
    text = _clean_prompt(text)
    if not text:
        return ""
    if text.casefold().startswith(INJECTED_PREFIXES):
        return ""
    if re.fullmatch(r"/\S+", text):
        return ""
    return text


def _last_prompt_from_lines(lines: Sequence[bytes]) -> str:
    for raw in reversed(lines):
        if USER_ROLE_RE.search(raw) is None:
            continue
        record = load_json_object(raw)
        if record is None:
            continue
        text = _prompt_from_record(record)
        if text:
            return block_text(text, MAX_PROMPT_CHARS)
    return ""


def _model_from_lines(lines: Sequence[bytes]) -> str:
    for raw in reversed(lines):
        if TURN_CONTEXT_RE.search(raw) is None:
            continue
        record = load_json_object(raw)
        if record is None:
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        value = payload.get("model")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _content_kind(payload: Dict[str, Any]) -> str:
    kind = payload.get("type")
    return kind if isinstance(kind, str) else ""


def _record_position(record: Dict[str, Any], fallback: int) -> int:
    ordinal = record.get("ordinal")
    if isinstance(ordinal, int) and not isinstance(ordinal, bool):
        return ordinal
    return fallback


def _entrypoint(meta: Dict[str, Any]) -> str:
    originator = str(meta.get("originator") or "")
    lowered = originator.casefold()
    source = meta.get("source")
    if "desktop" in lowered:
        return "desktop"
    if "cli" in lowered or "tui" in lowered:
        return "cli"
    if isinstance(source, str):
        normalized = source.strip().casefold()
        if normalized == "vscode" or lowered.startswith("codex-web"):
            return "ide"
        if normalized:
            return normalized
    return originator


def _is_subagent(meta: Dict[str, Any]) -> bool:
    if meta.get("thread_source") == "subagent":
        return True
    source = meta.get("source")
    return isinstance(source, dict) and "subagent" in source


def _branch_of(meta: Dict[str, Any]) -> str:
    git = meta.get("git")
    if isinstance(git, dict):
        branch = git.get("branch")
        if isinstance(branch, str):
            return branch
    return ""


def _patch_paths(text: str) -> List[str]:
    return [match.group(1).strip() for match in PATCH_FILE_RE.finditer(text)]


def _file_path(value: str, cwd: str) -> str:
    if not isinstance(value, str):
        return ""
    return file_path({"path": value.strip()}, cwd, ("path",))


def _tool_arguments(payload: Dict[str, Any]) -> Any:
    kind = _content_kind(payload)
    if kind == "custom_tool_call":
        value = payload.get("input")
        return value if isinstance(value, str) else ""
    if kind == "function_call":
        value = payload.get("arguments")
        if isinstance(value, str):
            return load_json_object(value) or {}
        return value if isinstance(value, dict) else {}
    return {}


def _tool_detail(name: str, arguments: Any) -> str:
    if isinstance(arguments, dict):
        for key in ("cmd", "file_path", "path", "task_name", "query", "description"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return one_line(value, 160)
        session_id = arguments.get("session_id")
        if session_id is not None:
            return "session %s" % session_id
        return ""
    text = str(arguments or "").strip()
    if not text:
        return ""
    if name == "apply_patch":
        paths = _patch_paths(text)
        if paths:
            return one_line(", ".join(paths), 160)
    return one_line(text, 160)


class CodexAdapter(HarnessAdapter):
    """ChatGPT Codex rollout segments under ``~/.codex``."""

    name = "codex"
    aliases = ("codex", "chatgpt-codex")
    variants = "desktop, ide, cli"
    store_hint = "~/.codex"
    home_env = "FMS_CODEX_HOME"

    def __init__(self) -> None:
        self._index_cache: Optional[Tuple[str, Dict[str, Path]]] = None
        self._meta_cache: Dict[Tuple[str, int, int], Optional[Dict[str, Any]]] = {}
        self._title_cache: Optional[
            Tuple[Tuple[str, int, int], Dict[str, Tuple[str, Optional[datetime]]]]
        ] = None

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".codex"

    def session_roots(self) -> List[Path]:
        return [self.home() / "sessions", self.home() / "archived_sessions"]

    def _all_session_paths(self) -> Iterator[Path]:
        for root in self.session_roots():
            if not root.is_dir():
                continue
            for path in root.rglob("rollout-*.jsonl*"):
                name = path.name
                if not (name.endswith(".jsonl") or name.endswith(".jsonl.zst")):
                    continue
                if path.is_file():
                    yield path

    @staticmethod
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _is_archived_path(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(
                (self.home() / "archived_sessions").resolve()
            )
            return True
        except (OSError, ValueError):
            return False

    def _thread_map(self) -> Dict[str, Path]:
        key = str(self.home())
        cached = self._index_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        mapping: Dict[str, Path] = {}
        for path in self._all_session_paths():
            parsed = _parse_rollout_name(path)
            if parsed is None:
                continue
            session_id, segment_id, _ = parsed
            if segment_id == session_id:
                mapping[session_id] = path
            else:
                mapping.setdefault(session_id, path)
                mapping[segment_id] = path
        self._index_cache = (key, mapping)
        return mapping

    def _session_meta(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            stat = path.stat()
        except OSError:
            return None
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if key in self._meta_cache:
            return self._meta_cache[key]
        meta: Optional[Dict[str, Any]] = None
        try:
            for record in _iter_head_records(path, 256_000, 20):
                if record.get("type") != "session_meta":
                    continue
                payload = record.get("payload")
                if isinstance(payload, dict):
                    meta = payload
                break
        except (OSError, ValueError):
            meta = None
        self._meta_cache[key] = meta
        return meta

    def _remember_meta(self, path: Path, meta: Dict[str, Any]) -> None:
        try:
            stat = path.stat()
        except OSError:
            return
        self._meta_cache[(str(path), stat.st_mtime_ns, stat.st_size)] = meta

    def _index_entries(self) -> Dict[str, Tuple[str, Optional[datetime]]]:
        path = self.home() / "session_index.jsonl"
        try:
            stat = path.stat()
        except OSError:
            return {}
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        cached = self._title_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        entries: Dict[str, Tuple[str, Optional[datetime]]] = {}
        try:
            handle = open(path, "rb")
        except OSError:
            return {}
        with handle:
            for raw in handle:
                record = load_json_object(raw)
                if record is None:
                    continue
                session_id = record.get("id")
                title = record.get("thread_name")
                if not isinstance(session_id, str) or not isinstance(title, str):
                    continue
                if not title.strip():
                    continue
                entries[session_id] = (
                    title.strip(),
                    parse_timestamp(record.get("updated_at")),
                )
        self._title_cache = (key, entries)
        return entries

    def _chain(
        self, path: Path
    ) -> List[Tuple[Path, Optional[int], Optional[int]]]:
        """Return ``(segment, end ordinal, end byte)`` oldest first.

        Both caps are exclusive and come from the child segment's
        ``history_base``, so a capped segment only contributes the history
        that the newer segment actually built on.
        """

        segments: List[Tuple[Path, Optional[int], Optional[int]]] = []
        current: Optional[Path] = path
        cap: Optional[int] = None
        byte_cap: Optional[int] = None
        visited = set()
        while current is not None and current not in visited:
            visited.add(current)
            segments.append((current, cap, byte_cap))
            meta = self._session_meta(current)
            base = meta.get("history_base") if meta else None
            if not isinstance(base, dict):
                break
            thread_id = base.get("thread_id")
            if not isinstance(thread_id, str):
                break
            base_path = self._thread_map().get(thread_id)
            if base_path is None:
                break
            value = base.get("end_ordinal_exclusive")
            cap = value if isinstance(value, int) and not isinstance(value, bool) else None
            offset = base.get("end_byte_offset")
            byte_cap = (
                offset
                if isinstance(offset, int) and not isinstance(offset, bool) and offset > 0
                else None
            )
            current = base_path
        segments.reverse()
        return segments

    def iter_session_paths(self) -> Iterator[Path]:
        best: Dict[str, Tuple[Tuple[Tuple[str, str], bool], Path]] = {}
        for path in self._all_session_paths():
            parsed = _parse_rollout_name(path)
            if parsed is None:
                continue
            session_id, _, stamp = parsed
            key = (stamp, not self._is_archived_path(path))
            current = best.get(session_id)
            if current is None or key > current[0]:
                best[session_id] = (key, path)
        paths = [entry[1] for entry in best.values()]
        paths.sort(key=self._mtime, reverse=True)
        yield from paths

    def session_id_for(self, path: Path) -> str:
        parsed = _parse_rollout_name(path)
        if parsed is not None:
            return parsed[0]
        return path.name.split(".jsonl", 1)[0]

    def _first_prompt(
        self, records: Sequence[Dict[str, Any]], cap: Optional[int]
    ) -> str:
        for position, record in enumerate(records):
            if cap is not None and _record_position(record, position) >= cap:
                break
            text = _prompt_from_record(record)
            if text:
                return block_text(text, MAX_PROMPT_CHARS)
        return ""

    @staticmethod
    def _last_prompt(records: Sequence[Dict[str, Any]]) -> str:
        for record in reversed(records):
            text = _prompt_from_record(record)
            if text:
                return block_text(text, MAX_PROMPT_CHARS)
        return ""

    @staticmethod
    def _model_from(records: Sequence[Dict[str, Any]]) -> str:
        model = ""
        for record in records:
            if record.get("type") != "turn_context":
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            value = payload.get("model")
            if isinstance(value, str) and value.strip():
                model = value.strip()
        return model

    def summarize(self, path: Path) -> SessionSummary:
        head_lines, tail_lines = _scan_session(path)
        head_records = _parse_lines(head_lines)
        meta = _meta_from_records(head_records) or self._session_meta(path)
        if meta is None:
            raise ValueError("cannot read codex session metadata: %s" % path)
        self._remember_meta(path, meta)
        if _is_subagent(meta):
            raise ValueError("codex subagent session is not resumable: %s" % path)

        chain = self._chain(path)
        oldest, oldest_cap, _ = chain[0]
        if oldest == path:
            oldest_head = head_records
        else:
            oldest_head = list(_iter_head_records(oldest))

        first_prompt = self._first_prompt(oldest_head, oldest_cap)
        if not first_prompt:
            first_prompt = self._first_prompt(head_records, None)

        recent_lines: Sequence[bytes] = tail_lines or head_lines
        last_prompt = _last_prompt_from_lines(recent_lines)
        if not last_prompt:
            last_prompt = self._last_prompt(head_records)
        if not first_prompt:
            first_prompt = last_prompt

        session_id = meta.get("id") or meta.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            parsed = _parse_rollout_name(path)
            session_id = parsed[0] if parsed else path.name
        session_id = session_id.strip()

        entries = self._index_entries()
        index_title, index_updated = entries.get(session_id, ("", None))
        title = index_title if index_title and not _is_generic(index_title) else ""
        if not title:
            title = _choose_title(first_prompt, last_prompt) or session_id

        raw_cwd = meta.get("cwd")
        cwd = raw_cwd if isinstance(raw_cwd, str) else ""
        model = _model_from_lines(recent_lines) or self._model_from(head_records)

        oldest_meta = meta if oldest == path else self._session_meta(oldest)
        started: Optional[datetime] = None
        if oldest_meta is not None:
            started = parse_timestamp(oldest_meta.get("timestamp"))
            if started is None:
                started = parse_timestamp(oldest_meta.get("created_at"))
        if started is None:
            for record in oldest_head:
                started = parse_timestamp(record.get("timestamp"))
                if started is not None:
                    break

        updated = _latest_timestamp(recent_lines) or index_updated or started
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
            branch=_branch_of(meta),
            model=model,
            entrypoint=_entrypoint(meta),
            version=str(meta.get("cli_version") or ""),
            size=size,
            variants=self.variants,
            archived=self._is_archived_path(path),
        )

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        seen = set()
        for segment, cap, _ in self._chain(summary.path):
            for position, record in enumerate(_iter_records(segment)):
                ordinal = record.get("ordinal")
                if isinstance(ordinal, int) and not isinstance(ordinal, bool):
                    if cap is not None and ordinal >= cap:
                        break
                    key: Any = ordinal
                else:
                    key = (str(segment), position)
                if key in seen:
                    continue
                seen.add(key)
                text = _prompt_from_record(record)
                if not text:
                    continue
                yield UserPrompt(
                    text=text,
                    timestamp=parse_timestamp(record.get("timestamp")),
                )

    def contains(self, summary: SessionSummary, tokens: Sequence[str]) -> bool:
        remaining = {normalize_text(token) for token in tokens if token}
        remaining.discard("")
        if not remaining:
            return True
        try:
            for segment, _, byte_cap in self._chain(summary.path):
                overlap = b""
                consumed = 0
                for chunk in _iter_raw_chunks(segment):
                    if byte_cap is not None:
                        room = byte_cap - consumed
                        if room <= 0:
                            break
                        if len(chunk) > room:
                            chunk = chunk[:room]
                    consumed += len(chunk)
                    data = overlap + chunk
                    text = normalize_text(data.decode("utf-8", "ignore"))
                    for token in tuple(remaining):
                        if token in text:
                            remaining.discard(token)
                    if not remaining:
                        return True
                    overlap = data[-512:]
        except (OSError, ValueError):
            return False
        return not remaining

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
        turn_count = 0

        def append_current() -> None:
            nonlocal current
            if current is None:
                return
            if current.user_text or current.assistant_texts or current.tools:
                exchanges.append(current)
            current = None

        for segment, cap, _ in self._chain(summary.path):
            for position, record in enumerate(_iter_records(segment)):
                ordinal = _record_position(record, position)
                if cap is not None and ordinal >= cap:
                    break
                timestamp = parse_timestamp(record.get("timestamp"))
                if timestamp is not None:
                    if started is None or timestamp < started:
                        started = timestamp
                    if updated is None or timestamp > updated:
                        updated = timestamp

                record_type = record.get("type")
                if record_type == "event_msg":
                    continue
                if record_type == "session_meta":
                    payload = record.get("payload")
                    if not isinstance(payload, dict):
                        continue
                    if isinstance(payload.get("cwd"), str) and payload["cwd"]:
                        cwd = payload["cwd"]
                    if _branch_of(payload):
                        summary.branch = _branch_of(payload)
                    if payload.get("cli_version"):
                        summary.version = str(payload["cli_version"])
                    entry = _entrypoint(payload)
                    if entry:
                        summary.entrypoint = entry
                    continue
                if record_type == "turn_context":
                    payload = record.get("payload")
                    if isinstance(payload, dict):
                        if isinstance(payload.get("cwd"), str) and payload["cwd"]:
                            cwd = payload["cwd"]
                        if isinstance(payload.get("model"), str) and payload["model"].strip():
                            model = payload["model"].strip()
                    continue
                if record_type == "compacted":
                    payload = record.get("payload")
                    if isinstance(payload, dict):
                        message = payload.get("message")
                        if isinstance(message, str) and message.strip():
                            compact_summary = block_text(message, MAX_SUMMARY_CHARS)
                    continue
                if record_type != "response_item":
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue

                text = _prompt_from_record(record)
                if text:
                    append_current()
                    cleaned = block_text(text, MAX_PROMPT_CHARS)
                    current = Exchange(user_text=cleaned, timestamp=timestamp)
                    turn_count += 1
                    last_prompt = cleaned
                    if not first_prompt:
                        first_prompt = cleaned
                    continue

                kind = _content_kind(payload)
                if kind == "message" and payload.get("role") == "assistant":
                    text = _content_text(payload)
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

                if kind not in ("custom_tool_call", "function_call"):
                    continue
                name = str(payload.get("name") or "tool")
                arguments = _tool_arguments(payload)
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
                if name in EDIT_TOOLS and isinstance(arguments, str):
                    for raw in _patch_paths(arguments):
                        path_value = _file_path(raw, cwd)
                        if not path_value:
                            continue
                        edited[path_value] = edited.get(path_value, 0) + 1

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
            todos=[],
            exchanges=list(exchanges),
            edited_files=edited_files,
            tool_counts=dict(tool_counts.most_common()),
            recent_tools=list(recent_tools),
            turn_count=turn_count,
        )
