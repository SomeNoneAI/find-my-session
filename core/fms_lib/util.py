from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

UTC = timezone.utc

_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DURATION_RE = re.compile(r"^(\d+)([mhdw])$")

_UNIT_SECONDS = {
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
    "w": 7 * 24 * 60 * 60,
}


def parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 100_000_000_000:
            number /= 1000.0
        try:
            return datetime.fromtimestamp(number, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_since(value: Optional[str], now: Optional[datetime] = None) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    match = _DURATION_RE.fullmatch(text.lower())
    if match:
        current = now or datetime.now(tz=UTC)
        return current - timedelta(seconds=int(match.group(1)) * _UNIT_SECONDS[match.group(2)])
    if _DATE_RE.fullmatch(text):
        local_midnight = datetime.strptime(text, "%Y-%m-%d")
        return local_midnight.astimezone(UTC)
    parsed = parse_timestamp(text)
    if parsed and _DATETIME_RE.match(text):
        return parsed
    raise ValueError("invalid time value: %s" % value)


def to_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def format_local(value: Optional[datetime]) -> str:
    if value is None:
        return "-"
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return unicodedata.normalize("NFKC", value).casefold()


def one_line(value: Any, limit: int = 0) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    text = re.sub(r"\s+", " ", value).strip()
    if limit > 0 and len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + "…"
    return text


def block_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    text = value.strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if limit > 0 and len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + "…"
    return text


def abbreviate_path(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    try:
        home = str(Path.home().resolve())
    except OSError:
        home = str(Path.home())
    if text == home:
        return "~"
    prefix = home + os.sep
    if text.startswith(prefix):
        return "~" + text[len(home) :]
    return text


def path_key(value: Any) -> str:
    if not value:
        return ""
    text = os.path.normpath(os.path.abspath(os.path.expanduser(str(value))))
    if sys.platform == "darwin" or os.name == "nt":
        return text.casefold()
    return text


def cwd_matches(session_cwd: Any, target: Any) -> bool:
    session = path_key(session_cwd)
    wanted = path_key(target)
    if not session or not wanted:
        return False
    if session == wanted:
        return True
    return session.startswith(wanted + os.sep) or wanted.startswith(session + os.sep)


def load_json_object(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8", "replace")
        except Exception:
            return None
    if not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def iter_head_records(
    path: Path,
    max_bytes: int = 2_000_000,
    max_records: int = 200,
) -> Iterator[Dict[str, Any]]:
    try:
        handle = open(path, "rb")
    except OSError:
        return
    with handle:
        total = 0
        count = 0
        for raw in handle:
            total += len(raw)
            count += 1
            record = load_json_object(raw)
            if record is not None:
                yield record
            if total >= max_bytes or count >= max_records:
                break


def iter_tail_records(path: Path, max_bytes: int = 512_000) -> List[Dict[str, Any]]:
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size <= 0:
        return []
    start = max(0, size - max_bytes)
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
    elif lines and load_json_object(lines[-1]) is None:
        lines.pop()
    records: List[Dict[str, Any]] = []
    for raw in lines:
        record = load_json_object(raw)
        if record is not None:
            records.append(record)
    return records


def iter_file_records(path: Path) -> Iterator[Dict[str, Any]]:
    try:
        handle = open(path, "rb")
    except OSError:
        return
    with handle:
        for raw in handle:
            record = load_json_object(raw)
            if record is not None:
                yield record


def file_contains_all(path: Path, tokens: Iterable[str], chunk_size: int = 4 * 1024 * 1024) -> bool:
    remaining = {normalize_text(token) for token in tokens if token}
    remaining.discard("")
    if not remaining:
        return True
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
        return False
    return not remaining
