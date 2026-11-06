"""CodeBuddy CN desktop agent session store adapter.

CodeBuddy CN keeps a session index in ``codebuddy-sessions.vscdb`` (an
SQLite ``ItemTable`` with one ``session:<id>`` row per conversation
carrying conversationId, cwd, title, status, and epoch-millisecond
timestamps), message bodies in per-queue JSON files under
``User/globalStorage/tencent-cloud.coding-copilot/message-queue/``,
per-session todos in ``todos/<id>.json``, edited-file snapshots in
``file-changes/<id>/``, and archive state in Electron Local Storage
(``Local Storage/leveldb/*.log``, key ``genie-archived-session-ids``).
Conversations directories under ``genie-history/`` only hold empty
per-session folders, and the workspace ``state.vscdb`` files only
carry the extension state, so neither is a message source.

Sessions without a message-queue file still list and search from the
index metadata; prompts and the digest simply carry no turns.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from ..models import Exchange, SessionDetail, SessionSummary, UserPrompt
from ..util import UTC, normalize_text, one_line, parse_timestamp
from .base import HarnessAdapter
from .common import is_generic as _is_generic

EXTENSION_DIRNAME = "tencent-cloud.coding-copilot"
SESSIONS_DB_NAME = "codebuddy-sessions.vscdb"
MESSAGE_QUEUE_DIRNAME = "message-queue"
TODOS_DIRNAME = "todos"
FILE_CHANGES_DIRNAME = "file-changes"
ARCHIVE_KEY = b"genie-archived-session-ids"
_ARCHIVE_RE = re.compile(rb"genie-archived-session-ids(.)\x01")

MAX_PROMPT_CHARS = 4_000
MAX_SUMMARY_CHARS = 20_000
MAX_ASSISTANT_CHARS = 5_000

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch"}

_SYSTEM_TAG_RES = (
    re.compile(r"<system-reminder\b[^>]*>.*?</system-reminder>", re.S),
    re.compile(r"<task-notification\b[^>]*>.*?</task-notification>", re.S),
)


def _clean_prompt(value: str) -> str:
    text = value.strip()
    for pattern in _SYSTEM_TAG_RES:
        text = pattern.sub("", text)
    return text.strip()


def _meaningful_prompt(value: str) -> bool:
    text = _clean_prompt(value)
    if not text or _is_generic(text):
        return False
    lowered = text.casefold()
    return lowered not in {"continue", "继续", "ok"}


def _choose_title(first: str, last: str) -> str:
    if _meaningful_prompt(last):
        return one_line(last, 120)
    if _meaningful_prompt(first):
        return one_line(first, 120)
    return ""


def _epoch_ms(value: Any) -> Optional[datetime]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    parsed = parse_timestamp(value)
    return parsed


def _decode_project_dir(name: str) -> str:
    padded = name + "=" * (-len(name) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", "replace")
    except Exception:
        return ""


def _block_text(block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    kind = block.get("type")
    if kind == "text":
        text = block.get("text")
        return text.strip() if isinstance(text, str) else ""
    # Images and other attachments are context, never prompts.
    return ""


def _item_prompt_text(item: Dict[str, Any]) -> str:
    parts: List[str] = []
    blocks = item.get("contentBlocks")
    if isinstance(blocks, list):
        for block in blocks:
            text = _block_text(block)
            if text:
                parts.append(text)
    if not parts:
        preview = item.get("previewText")
        if isinstance(preview, str) and preview.strip():
            parts.append(preview.strip())
    return _clean_prompt("\n".join(parts).strip())


def _item_role(item: Dict[str, Any]) -> str:
    status = item.get("status")
    return status.strip().casefold() if isinstance(status, str) else ""


def _is_user_item(item: Dict[str, Any]) -> bool:
    # Observed user turns carry status "sent". Anything else (empty,
    # received/completed assistant turns) is not a human prompt.
    return _item_role(item) == "sent" and bool(_item_prompt_text(item))


def _prompt_timestamp(item: Dict[str, Any]) -> Optional[datetime]:
    for key in ("createdAt", "updatedAt"):
        parsed = _epoch_ms(item.get(key))
        if parsed is not None:
            return parsed
    return None


class CodeBuddyCNAdapter(HarnessAdapter):
    """CodeBuddy CN desktop: vscdb session index plus JSON message queues."""

    name = "codebuddy-cn"
    aliases = ("codebuddy-cn", "codebuddycn", "cb-cn")
    variants = "desktop"
    store_hint = "CodeBuddy CN/codebuddy-sessions.vscdb"
    home_env = "FMS_CODEBUDDY_CN_HOME"

    def home(self) -> Path:
        override = os.environ.get(self.home_env)
        if override:
            return Path(override).expanduser()
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "CodeBuddy CN"
        )

    def _sessions_db(self) -> Path:
        return self.home() / SESSIONS_DB_NAME

    def _archived_ids(self) -> frozenset:
        # Archive state lives in Electron Local Storage (leveldb logs):
        # key genie-archived-session-ids holds a JSON id array. Logs are
        # append-only and rotate; the newest record across all logs wins.
        # A missing or unreadable store means no archive metadata, so
        # every session stays active.
        leveldb = self.home() / "Local Storage" / "leveldb"
        try:
            logs = sorted(
                (p for p in leveldb.glob("*.log") if p.is_file()),
                key=lambda p: p.stat().st_mtime,
            )
        except OSError:
            return frozenset()
        latest: List[str] = []
        for log_path in logs:
            try:
                data = log_path.read_bytes()
            except OSError:
                continue
            for match in _ARCHIVE_RE.finditer(data):
                size = match.group(1)[0] - 1
                chunk = data[match.end() : match.end() + size]
                try:
                    value = json.loads(chunk.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(value, list):
                    latest = [
                        str(item).strip().lower()
                        for item in value
                        if isinstance(item, str) and str(item).strip()
                    ]
        return frozenset(latest)

    def _extension_root(self) -> Path:
        return (
            self.home() / "User" / "globalStorage" / EXTENSION_DIRNAME
        )

    def _queue_dir(self) -> Path:
        return self._extension_root() / MESSAGE_QUEUE_DIRNAME

    def session_roots(self) -> List[Path]:
        return [self._extension_root()]

    def owns(self, path: Path) -> bool:
        text = str(path)
        if "#" in text:
            base_text = text.split("#", 1)[0]
            try:
                return (
                    Path(base_text).expanduser().resolve()
                    == self._sessions_db().expanduser().resolve()
                )
            except OSError:
                return False
        try:
            path.relative_to(self.home())
            return True
        except ValueError:
            return False

    def session_id_for(self, path: Path) -> str:
        name = path.name
        # Virtual paths look like db.sqlite#<session-id>; keep the full
        # id so it matches the session index.
        if "#" in name:
            return name.rsplit("#", 1)[1].strip().lower()
        stem = path.stem
        if name.startswith("session:"):
            return name.split(":", 1)[1].strip().lower()
        return stem.strip().lower()

    def _read_index(self) -> List[Dict[str, Any]]:
        db_path = self._sessions_db()
        if not db_path.is_file():
            return []
        try:
            db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.Error:
            return []
        try:
            rows = db.execute(
                "SELECT key, value FROM ItemTable WHERE key LIKE 'session:%'"
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            try:
                db.close()
            except Exception:
                pass
        entries: List[Dict[str, Any]] = []
        for key, value in rows:
            raw = value.decode() if isinstance(value, bytes) else value
            if not isinstance(raw, str):
                continue
            try:
                record = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if not isinstance(record, dict):
                continue
            session_id = record.get("conversationId")
            if not isinstance(session_id, str) or not session_id.strip():
                session_id = key.split(":", 1)[1] if ":" in key else ""
            session_id = session_id.strip().lower()
            if not session_id:
                continue
            entries.append(
                {
                    "session_id": session_id,
                    "cwd": record.get("cwd")
                    if isinstance(record.get("cwd"), str)
                    else "",
                    "title": record.get("title")
                    if isinstance(record.get("title"), str)
                    else "",
                    "status": record.get("status")
                    if isinstance(record.get("status"), str)
                    else "",
                    "created": _epoch_ms(record.get("createdAt")),
                    "updated": _epoch_ms(record.get("updatedAt")),
                }
            )
        return entries

    def _queue_files(self) -> List[Path]:
        queue_dir = self._queue_dir()
        if not queue_dir.is_dir():
            return []
        files: List[Path] = []
        for path in queue_dir.glob("*.json"):
            if path.is_file() and not path.name.startswith("."):
                files.append(path)
        return files

    def _queue_for(self, session_id: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        wanted = session_id.casefold()
        for path in self._queue_files():
            try:
                with open(path, encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, ValueError):
                continue
            conversations = (
                payload.get("conversations")
                if isinstance(payload, dict)
                else None
            )
            if not isinstance(conversations, dict):
                continue
            for conversation_id, conversation in conversations.items():
                if not isinstance(conversation, dict):
                    continue
                if str(conversation_id).casefold() != wanted:
                    continue
                records = conversation.get("items")
                if isinstance(records, list):
                    items.extend(
                        r for r in records if isinstance(r, dict)
                    )
        items.sort(
            key=lambda r: (
                r.get("order")
                if isinstance(r.get("order"), int)
                else 0,
                str(r.get("createdAt") or ""),
            )
        )
        return items

    def _todos_for(self, session_id: str) -> List[Dict[str, Any]]:
        path = self._extension_root() / TODOS_DIRNAME / (session_id + ".json")
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return []
        records = payload.get("todos") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            return []
        todos: List[Dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            content = record.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            status = record.get("status")
            todos.append(
                {
                    "subject": content.strip(),
                    "status": status.strip()
                    if isinstance(status, str) and status.strip()
                    else "pending",
                }
            )
        return todos

    def _edited_files_for(
        self, session_id: str, cwd: str
    ) -> List[Dict[str, Any]]:
        root = self._extension_root() / FILE_CHANGES_DIRNAME / session_id
        if not root.is_dir():
            return []
        counts: Dict[str, int] = {}
        try:
            names = sorted(p.name for p in root.iterdir())
        except OSError:
            return []
        for name in names:
            stem = name.rsplit("_", 1)[0] if "_" in name else name
            display = stem.strip() or name
            counts[display] = counts.get(display, 0) + 1
        edited = [
            {"path": path, "count": count}
            for path, count in sorted(counts.items())
        ]
        return edited

    def iter_session_paths(self) -> Iterator[Path]:
        entries = self._read_index()
        if not entries:
            return
        db_path = self._sessions_db()
        try:
            mtime = db_path.stat().st_mtime
        except OSError:
            mtime = 0.0
        pending: List[Tuple[float, Dict[str, Any]]] = []
        for entry in entries:
            updated = entry.get("updated") or entry.get("created")
            stamp = updated.timestamp() if updated else mtime
            pending.append((stamp, entry))
        pending.sort(key=lambda item: item[0], reverse=True)
        for _, entry in pending:
            # Absolute virtual path against the real index database, so
            # `show <path>` resolves through the shared `#` branch.
            yield Path("%s#%s" % (db_path, entry["session_id"]))

    def summarize(self, path: Path) -> SessionSummary:
        session_id = self.session_id_for(path)
        archived = session_id in self._archived_ids()
        index = {e["session_id"]: e for e in self._read_index()}
        entry = index.get(session_id)
        if entry is None:
            raise ValueError(
                "unknown CodeBuddy CN session: %s" % session_id
            )
        items = self._queue_for(session_id)
        prompts = [
            _item_prompt_text(item)
            for item in items
            if _is_user_item(item)
        ]
        prompts = [p for p in prompts if p]
        first_prompt = prompts[0] if prompts else ""
        last_prompt = prompts[-1] if prompts else ""
        model = ""
        for item in items:
            candidate = item.get("modelId")
            if isinstance(candidate, str) and candidate.strip():
                model = candidate.strip()
                break
        title = entry.get("title", "")
        if not title or _is_generic(title):
            title = _choose_title(first_prompt, last_prompt) or session_id
        updated = entry.get("updated") or entry.get("created")
        if updated is None:
            for item in reversed(items):
                updated = _prompt_timestamp(item)
                if updated is not None:
                    break
        if updated is None:
            try:
                updated = datetime.fromtimestamp(
                    self._sessions_db().stat().st_mtime, tz=UTC
                )
            except OSError:
                updated = datetime.now(tz=UTC)
        started = entry.get("created") or updated
        size = 0
        for queue_path in self._queue_files():
            try:
                size += queue_path.stat().st_size
            except OSError:
                continue
        return SessionSummary(
            harness=self.name,
            session_id=session_id,
            path=path,
            cwd=entry.get("cwd", ""),
            updated=updated,
            title=title,
            first_prompt=one_line(first_prompt, MAX_PROMPT_CHARS),
            last_prompt=one_line(last_prompt, MAX_PROMPT_CHARS),
            started=started,
            model=model,
            entrypoint="desktop",
            version="",
            size=size,
            variants=self.variants,
            archived=archived,
        )

    def load(self, summary: SessionSummary) -> SessionDetail:
        items = self._queue_for(summary.session_id)
        exchanges: List[Exchange] = []
        prompt_count = 0
        for item in items:
            if not _is_user_item(item):
                continue
            prompt_count += 1
            stamp = _prompt_timestamp(item)
            exchanges.append(
                Exchange(
                    user_text=_item_prompt_text(item)[:MAX_PROMPT_CHARS],
                    timestamp=stamp,
                )
            )
            if len(exchanges) >= 50:
                break
        todos_raw = self._todos_for(summary.session_id)
        todos = [
            {"subject": t["subject"], "status": t["status"]}
            for t in todos_raw[:400]
        ]
        edited = self._edited_files_for(
            summary.session_id, summary.cwd
        )[:30]
        return SessionDetail(
            summary=summary,
            compact_summary="",
            todos=todos,
            exchanges=exchanges[-50:],
            edited_files=edited,
            turn_count=prompt_count,
        )

    def iter_prompts(
        self, summary: SessionSummary
    ) -> Iterator[UserPrompt]:
        index = 0
        for item in self._queue_for(summary.session_id):
            if not _is_user_item(item):
                continue
            index += 1
            yield UserPrompt(
                timestamp=_prompt_timestamp(item),
                text=_item_prompt_text(item),
            )

    def contains(
        self, summary: SessionSummary, tokens: Sequence[str]
    ) -> bool:
        if not tokens:
            return True
        needles = [t.casefold() for t in tokens]
        for item in self._queue_for(summary.session_id):
            haystacks: List[str] = []
            text = _item_prompt_text(item)
            if text:
                haystacks.append(text.casefold())
            preview = item.get("previewText")
            if isinstance(preview, str) and preview.strip():
                haystacks.append(preview.casefold())
            blob = json.dumps(item, ensure_ascii=False).casefold()
            haystacks.append(blob)
            if all(
                any(needle in hay for hay in haystacks)
                for needle in needles
            ):
                return True
        return False

    def find(self, needle: str) -> List[SessionSummary]:
        matches: List[SessionSummary] = []
        for path in self.iter_session_paths():
            try:
                summary = self.summarize(path)
            except ValueError:
                continue
            if summary.session_id.startswith(needle.casefold()):
                matches.append(summary)
        return matches
