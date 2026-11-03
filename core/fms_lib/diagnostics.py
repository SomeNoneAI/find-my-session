"""Sanitized diagnostics for session-store readability.

The shared search path silently skips sessions whose transcripts cannot be
read (missing zstd decoder, corrupt files, permission errors, format drift).
This module gives ``fms doctor`` and ``search --verbose`` a way to surface
those skips without leaking session content: entries carry only a coarse
error category, a path-stripped detail line, and an optional store path that
callers may show only under an explicit verbose flag.
"""

from __future__ import annotations

import importlib
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from . import __version__
from .util import one_line

CATEGORY_DECODER_MISSING = "decoder-missing"
CATEGORY_UNREADABLE = "unreadable"
CATEGORY_PARSE_ERROR = "parse-error"
CATEGORY_UNKNOWN = "unknown"

# Actionable advice per category, shown when the exception text itself does
# not already contain it.
CATEGORY_HINTS: Dict[str, str] = {
    CATEGORY_DECODER_MISSING: "install the zstd CLI or use Python 3.14+",
}


def hint_for(reason: str, detail: str) -> str:
    hint = CATEGORY_HINTS.get(reason, "")
    if hint and hint.casefold() in detail.casefold():
        return ""
    return hint


def classify(exc: BaseException) -> str:
    text = str(exc).casefold()
    if "decoder unavailable" in text:
        return CATEGORY_DECODER_MISSING
    if "decompress" in text or "zstandard data" in text:
        return CATEGORY_PARSE_ERROR
    if isinstance(exc, OSError):
        return CATEGORY_UNREADABLE
    if isinstance(exc, ValueError):
        return CATEGORY_PARSE_ERROR
    return CATEGORY_UNKNOWN


def sanitize_detail(exc: BaseException, path: Optional[Path] = None) -> str:
    """One-line, path-stripped description safe to print or share."""
    if isinstance(exc, OSError) and exc.strerror:
        text = exc.strerror
    else:
        text = str(exc)
    if path is not None:
        text = text.replace(str(path), "<session>")
        text = text.replace(str(Path(path).parent), "<session-dir>")
    return one_line(text, 160)


@dataclass
class SkippedEntry:
    harness: str
    reason: str
    detail: str
    path: Optional[Path] = None

    def to_dict(self, include_path: bool = False) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "harness": self.harness,
            "reason": self.reason,
            "detail": self.detail,
        }
        if include_path and self.path is not None:
            data["path"] = str(self.path)
        return data


def store_home(path: Path) -> str:
    try:
        relative = path.expanduser().relative_to(Path.home())
    except (OSError, RuntimeError, ValueError):
        return "<custom>"
    return "~" if str(relative) == "." else "~/" + relative.as_posix()


@dataclass
class ScanReport:
    """Counts and sanitized skips gathered while summarizing candidate files."""

    candidates: int = 0
    readable: int = 0
    skipped: List[SkippedEntry] = field(default_factory=list)
    _lock: Any = field(default_factory=Lock, repr=False)

    def note_readable(self) -> None:
        with self._lock:
            self.readable += 1

    def record(
        self, harness: str, exc: BaseException, path: Optional[Path] = None
    ) -> None:
        entry = SkippedEntry(
            harness=harness,
            reason=classify(exc),
            detail=sanitize_detail(exc, path),
            path=path,
        )
        with self._lock:
            self.skipped.append(entry)

    def note_store_error(self, harness: str, exc: BaseException) -> None:
        entry = SkippedEntry(
            harness=harness,
            reason=CATEGORY_UNREADABLE,
            detail="cannot enumerate session store",
            path=None,
        )
        with self._lock:
            self.skipped.append(entry)

    def grouped(self) -> List[Tuple[str, str, int, str, List[Path]]]:
        """Collapse skips into (harness, reason, count, detail, paths) groups."""
        groups: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for entry in self.skipped:
            key = (entry.harness, entry.reason)
            group = groups.setdefault(
                key, {"count": 0, "detail": entry.detail, "paths": []}
            )
            group["count"] += 1
            if entry.path is not None:
                group["paths"].append(entry.path)
        return [
            (harness, reason, group["count"], group["detail"], group["paths"])
            for (harness, reason), group in groups.items()
        ]

    def to_dict(self, include_paths: bool = False) -> Dict[str, Any]:
        return {
            "candidates": self.candidates,
            "readable": self.readable,
            "skipped": len(self.skipped),
            "issues": issue_dicts(self),
        }


def issue_dicts(report: ScanReport) -> List[Dict[str, Any]]:
    """Group a report's skips into category rows with counts and hints."""
    groups: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for entry in report.skipped:
        key = (entry.reason, entry.detail)
        issue = groups.setdefault(
            key, {"reason": entry.reason, "count": 0, "detail": entry.detail}
        )
        issue["count"] += 1
    issues = list(groups.values())
    for issue in issues:
        hint = hint_for(issue["reason"], issue["detail"])
        if hint:
            issue["hint"] = hint
    return issues


def _python_zstd() -> bool:
    try:  # Python 3.14+
        importlib.import_module("compression.zstd")

        return True
    except ImportError:  # pragma: no cover - depends on interpreter
        return False


def zstd_status() -> Dict[str, Any]:
    module = _python_zstd()
    cli = shutil.which("zstd") is not None
    available = module or cli
    return {
        "available": available,
        "python_compression": module,
        "cli": cli,
        "hint": "" if available else CATEGORY_HINTS[CATEGORY_DECODER_MISSING],
    }


def environment() -> Dict[str, Any]:
    return {
        "fms": __version__,
        "python": platform.python_version(),
        "platform": "%s %s %s"
        % (platform.system(), platform.release(), platform.machine()),
        "zstd": zstd_status(),
    }


def _fingerprint_lines(fingerprint: Dict[str, Any], indent: str) -> List[str]:
    kinds = fingerprint.get("kinds") or {}
    if not kinds:
        return []
    lines = [
        "%sfingerprint: %s"
        % (
            indent,
            ", ".join(
                "%s x%d" % (name, kinds[name].get("files", 0))
                for name in sorted(kinds)
            ),
        )
    ]
    inner = indent + "  "
    for name in sorted(kinds):
        entry = kinds[name]
        if "tables" in entry:
            lines.append(
                "%s%s: %d rows; tables:" % (inner, name, entry.get("records", 0))
            )
            for table in entry.get("tables", [])[:8]:
                columns = ", ".join(
                    ("%s %s" % (col["name"], col["type"] or "?")).strip()
                    for col in table.get("columns", [])
                )
                lines.append(
                    "%s  %s: %d rows (%s)"
                    % (inner, table.get("name", "?"), table.get("rows", 0), columns)
                )
            if entry.get("truncated_tables"):
                lines.append("%s  … more tables" % inner)
            continue
        if "fields" not in entry:
            continue
        records = entry.get("records", 0)
        unparsed = entry.get("records_unparsed", 0)
        summary = "%s%s: %d records sampled" % (inner, name, records)
        if unparsed:
            summary += ", %d unparsed" % unparsed
        lines.append(summary + "; fields:")
        fields = entry.get("fields") or {}
        shown = 0
        for field_name, types in fields.items():
            if shown >= 8:
                lines.append("%s  … more field names" % inner)
                break
            rendered = ", ".join(
                "%s x%d" % (type_name, count) for type_name, count in types.items()
            )
            lines.append("%s  %s: %s" % (inner, field_name, rendered))
            shown += 1
        if not fields:
            lines.append("%s  (no top-level JSON objects)" % inner)
        elif entry.get("truncated_fields"):
            lines[-1] += " …"
    return lines


def render_doctor_text(payload: Dict[str, Any]) -> str:
    lines = [
        "fms %s" % payload.get("fms", "?"),
        "python: %s" % payload.get("python", "?"),
        "platform: %s" % payload.get("platform", "?"),
    ]
    zstd = payload.get("zstd") or {}
    if zstd.get("available"):
        via = []
        if zstd.get("python_compression"):
            via.append("python")
        if zstd.get("cli"):
            via.append("cli")
        lines.append("zstd: available (%s)" % ("+".join(via) or "unknown"))
    else:
        lines.append("zstd: missing (%s)" % zstd.get("hint", "no decoder found"))
    for store in payload.get("stores", []):
        lines.append("")
        state = "present" if store.get("present") else "not found"
        lines.append(
            "%s (%s) [%s]" % (store.get("harness"), store.get("store"), state)
        )
        lines.append(
            "  candidates: %d, readable: %d, skipped: %d"
            % (
                store.get("candidates", 0),
                store.get("readable", 0),
                store.get("skipped", 0),
            )
        )
        for issue in store.get("issues", []):
            line = "  - %s x%d: %s" % (
                issue.get("reason"),
                issue.get("count"),
                issue.get("detail"),
            )
            hint = issue.get("hint") or ""
            if hint:
                line += " — %s" % hint
            lines.append(line)
        if store.get("fingerprint"):
            lines.extend(_fingerprint_lines(store["fingerprint"], "  "))
    return "\n".join(lines) + "\n"
