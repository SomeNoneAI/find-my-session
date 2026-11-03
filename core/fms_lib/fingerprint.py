"""Opt-in redacted shape fingerprints for ``fms doctor``.

A fingerprint describes how a session store is *shaped*, never what it
contains, so schema drift can be diagnosed from output that is safe to paste
into a public issue.

Included, per store:

- the layout kind of every candidate transcript file (``jsonl``, ``json``,
  ``sqlite``, ``text``, ``empty``, plus unreadable/undecodable states);
- for record-shaped stores, the top-level field names with the JSON type of
  their values and how often each combination occurs in the sample;
- for sqlite stores, table and column names with declared types and row
  counts.

Excluded: every value except its type name — prompts, completions, paths,
session ids, timestamps, emails, tokens, and other free-form content never
reach the output. Field and table names come from the app's schema, not from
session content.

Sampling is bounded and deterministic: at most ``HEAD_BYTES`` per file
(decompressed when needed), at most ``JSON_DOC_BYTES`` for single-document
JSON, ``MAX_RECORDS_PER_FILE`` records per file, and ``MAX_FIELDS`` field
names per kind, so output stays stable and cheap on huge stores.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .util import load_json_object

try:
    from compression import zstd as _zstd_module  # type: ignore[import-not-found]
except ImportError:
    _zstd_module = None  # type: ignore[assignment]

HEAD_BYTES = 2_000_000
JSON_DOC_BYTES = 8_000_000
MAX_RECORDS_PER_FILE = 200
MAX_FIELDS = 64
MAX_TABLES = 32
MAX_COLUMNS = 64

SQLITE_MAGIC = b"SQLite format 3\x00"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

_TYPE_NAMES: Tuple[Tuple[type, str], ...] = (
    (type(None), "null"),
    (bool, "bool"),
    (int, "int"),
    (float, "float"),
    (str, "str"),
    (list, "list"),
    (dict, "object"),
)


def _type_name(value: Any) -> str:
    for cls, name in _TYPE_NAMES:
        if isinstance(value, cls):
            return name
    return "other"


def _kind_entry(kinds: Dict[str, Dict[str, Any]], kind: str) -> Dict[str, Any]:
    return kinds.setdefault(kind, {"files": 0})


def _add_record(entry: Dict[str, Any], record: Dict[str, Any]) -> None:
    fields = entry.setdefault("fields", {})
    for key, value in record.items():
        if key not in fields and len(fields) >= MAX_FIELDS:
            entry["truncated_fields"] = True
            continue
        types = fields.setdefault(key, {})
        name = _type_name(value)
        types[name] = types.get(name, 0) + 1
    entry["records"] = entry.get("records", 0) + 1


def _decompress_head(path: Path, cap: int) -> Optional[bytes]:
    """Decompress at most ``cap`` bytes of a zstd file.

    Returns None when no decoder is available, and b"" when the stream is
    broken. Only the standard-library decoder or the ``zstd`` CLI is used.
    """
    if _zstd_module is not None:
        try:
            with _zstd_module.ZstdFile(str(path), "rb") as handle:
                return handle.read(cap)
        except (EOFError, OSError, ValueError):
            return b""
    exe = shutil.which("zstd")
    if exe is None:
        return None
    try:
        process = subprocess.Popen(
            [exe, "-dc", "--", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return b""
    try:
        assert process.stdout is not None
        data = process.stdout.read(cap)
    finally:
        process.kill()
        process.wait()
        if process.stdout is not None:
            process.stdout.close()
    return data


def _jsonl_records(entry: Dict[str, Any], data: bytes) -> None:
    if len(data) >= HEAD_BYTES and not data.endswith(b"\n"):
        data = data[: data.rfind(b"\n") + 1]
    counted = 0
    for raw in data.split(b"\n"):
        if not raw.strip():
            continue
        counted += 1
        if counted > MAX_RECORDS_PER_FILE:
            break
        record = load_json_object(raw)
        if record is None:
            entry["records_unparsed"] = entry.get("records_unparsed", 0) + 1
        else:
            _add_record(entry, record)


def _json_records(entry: Dict[str, Any], text: str) -> bool:
    """Record one JSON document's top-level shape; False when unparsable."""
    try:
        document = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return False
    if isinstance(document, dict):
        _add_record(entry, document)
        return True
    if isinstance(document, list):
        for element in document[:MAX_RECORDS_PER_FILE]:
            if isinstance(element, dict):
                _add_record(entry, element)
            else:
                entry["records_unparsed"] = entry.get("records_unparsed", 0) + 1
    return True


def _parses_as_json(data: bytes) -> bool:
    try:
        json.loads(data.decode("utf-8", "replace"))
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def _text_kind(head: bytes) -> str:
    text = head.decode("utf-8", "replace")
    for raw in text.splitlines():
        if raw.strip():
            if load_json_object(raw) is not None:
                return "jsonl"
            break
    try:
        json.loads(text)
        return "json"
    except (json.JSONDecodeError, ValueError):
        return "text"


def _read_doc(path: Path, head: bytes) -> bytes:
    """Whole file for small single-document JSON, otherwise the head."""
    try:
        size = path.stat().st_size
    except OSError:
        return head
    if len(head) < size <= JSON_DOC_BYTES:
        try:
            with path.open("rb") as handle:
                return handle.read(JSON_DOC_BYTES)
        except OSError:
            return head
    return head


def _fingerprint_file(path: Path, kinds: Dict[str, Dict[str, Any]]) -> None:
    with path.open("rb") as handle:
        head = handle.read(HEAD_BYTES)

    if head.startswith(SQLITE_MAGIC):
        shape = _sqlite_shape(path)
        entry = _kind_entry(kinds, "sqlite")
        entry["files"] += 1
        if shape is None:
            entry["unreadable"] = entry.get("unreadable", 0) + 1
        else:
            entry["records"] = entry.get("records", 0) + shape["records"]
            entry.setdefault("tables", []).extend(shape["tables"])
            if shape["truncated_tables"]:
                entry["truncated_tables"] = True
        return

    if head.startswith(ZSTD_MAGIC):
        inner = _decompress_head(path, HEAD_BYTES)
        if inner is None:
            _kind_entry(kinds, "zstd-undecodable")["files"] += 1
        elif not inner.strip() or b"\x00" in inner:
            _kind_entry(kinds, "binary")["files"] += 1
        else:
            _record_textlike(kinds, _text_kind(inner), inner)
        return

    if not head.strip():
        _kind_entry(kinds, "empty")["files"] += 1
        return

    if path.suffix.casefold() == ".json":
        data = _read_doc(path, head)
        kind = "json" if _parses_as_json(data) else "text"
        _record_textlike(kinds, kind, data)
        return

    if b"\x00" in head:
        _kind_entry(kinds, "binary")["files"] += 1
        return

    _record_textlike(kinds, _text_kind(head), head)


def _record_textlike(
    kinds: Dict[str, Dict[str, Any]], kind: str, data: bytes
) -> bool:
    """Fold one file of ``kind`` into the aggregate; False when unparsable."""
    entry = _kind_entry(kinds, kind)
    if kind == "json":
        if not _json_records(entry, data.decode("utf-8", "replace")):
            return False
    elif kind == "jsonl":
        entry.setdefault("records_unparsed", 0)
        _jsonl_records(entry, data)
    entry["files"] += 1
    return True


def _sqlite_shape(path: Path) -> Optional[Dict[str, Any]]:
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=1.0)
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        return None
    try:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' ORDER BY name"
            ).fetchall()
        ]
        truncated = len(names) > MAX_TABLES
        tables: List[Dict[str, Any]] = []
        for name in names[:MAX_TABLES]:
            quoted = '"%s"' % name.replace('"', '""')
            columns: List[Dict[str, str]] = []
            for row in connection.execute("PRAGMA table_info(%s)" % quoted):
                columns.append({"name": row[1], "type": row[2] or ""})
                if len(columns) >= MAX_COLUMNS:
                    break
            try:
                count = connection.execute(
                    "SELECT COUNT(*) FROM %s" % quoted
                ).fetchone()
                rows = int(count[0]) if count is not None else 0
            except sqlite3.Error:
                rows = 0
            tables.append({"name": name, "rows": rows, "columns": columns})
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    return {
        "records": sum(table["rows"] for table in tables),
        "tables": tables,
        "truncated_tables": truncated,
    }


def _stable(entry: Dict[str, Any]) -> Dict[str, Any]:
    stable = dict(entry)
    fields = stable.get("fields")
    if isinstance(fields, dict):
        stable["fields"] = {
            name: dict(sorted(fields[name].items())) for name in sorted(fields)
        }
    return stable


def fingerprint_store(paths: Iterable[Path]) -> Dict[str, Any]:
    """Aggregate a redacted shape fingerprint over candidate transcript paths."""
    kinds: Dict[str, Dict[str, Any]] = {}
    for path in paths:
        try:
            _fingerprint_file(Path(path), kinds)
        except OSError:
            _kind_entry(kinds, "unreadable")["files"] += 1
    return {
        "bounds": {
            "head_bytes": HEAD_BYTES,
            "records_per_file": MAX_RECORDS_PER_FILE,
            "fields_per_kind": MAX_FIELDS,
        },
        "kinds": {name: _stable(kinds[name]) for name in sorted(kinds)},
    }
