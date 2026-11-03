"""Build a synthetic Cursor store for tests.

The layout mirrors Cursor 3.23: one JSONL transcript per agent conversation
under ``projects/<encoded-cwd>/agent-transcripts/<session-id>/<session-id>.jsonl``,
subagent transcripts under ``.../<parent-id>/subagents/``, a desktop
``User/globalStorage/conversation-search.db`` index that carries titles and the
archive flag, and ``User/workspaceStorage/<hash>/workspace.json`` manifests that
map an encoded project directory back to a real folder.

Every identifier, path, and prompt below is invented.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

SESSION_MAIN = "f1c00001-1111-4a1b-8c1d-111111111111"
SESSION_PLAIN = "f1c00002-2222-4b2c-9d2e-222222222222"
SESSION_ARCHIVED = "f1c00003-3333-4c3d-9e4f-333333333333"
SESSION_ERROR = "f1c00004-4444-4d4e-8f5a-444444444444"
SESSION_EMPTY = "f1c00005-5555-4e5f-9a6b-555555555555"
SESSION_JSON = "f1c00006-6666-4f6a-8b7c-666666666666"
SESSION_SUBAGENT = "f1c00007-7777-4a7b-9c8d-777777777777"
SESSION_DECOY = "f1c00008-8888-4b8c-8d9e-888888888888"

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_BETA = "/Users/example/project-beta"
PROJECT_GAMMA = "/Users/example/project-gamma"

SLUG_ALPHA = "Users-example-project-alpha"
SLUG_BETA = "Users-example-project-beta"
SLUG_GAMMA = "Users-example-project-gamma"

TITLE_MAIN = "Bound the handoff digest for the Cursor CLI"
TITLE_ARCHIVED = "Archived Cursor conversation"
TITLE_PLAIN = ""
TITLE_GENERIC = "General chat"

PROMPTS_MAIN = (
    "Refactor the handoff digest so the CLI stays bounded. cursor-main-needle",
    "继续",
    "Ship the compact summary fallback.",
    "Tighten the digest tests.",
)
PROMPT_PLAIN = "Investigate the migration drift in project gamma."
PROMPT_ARCHIVED = "Archived request that must stay hidden by default."
PROMPT_SUBAGENT = "Subagent scratch work. cursor-subagent-needle."
PROMPT_DECOY = "Decoy transcript that must never be listed. cursor-decoy-needle."
PROMPT_INJECTED = "Injected context only. cursor-injected-needle."

NEEDLE_MAIN = "cursor-main-needle"
NEEDLE_DEEP_ONLY = "cursor-deep-only-needle"
NEEDLE_SUBAGENT = "cursor-subagent-needle"
NEEDLE_DECOY = "cursor-decoy-needle"
NEEDLE_INJECTED = "cursor-injected-needle"
NEEDLE_ARCHIVED = "cursor-archived-needle"

INJECTED_CONTEXT = (
    "<system_reminder>\nThe workspace is open. cursor-injected-needle\n"
    "</system_reminder>"
)
SUMMARY_REQUEST = (
    "<user_query>\n<summary_request>\nPlease summarize the conversation so far."
    "\n</summary_request>\n</user_query>"
)
THINKING_BLOCK = "<think>internal reasoning that must not leak</think>"
API_ERROR = "API error: quota exceeded for this plan."
TURN_ERROR = "Named models unavailable Free plans can only use Auto."

OVERVIEW = (
    "Summary of the conversation so far:\n"
    "The user asked to bound the handoff digest for the Cursor adapter."
)

TZ = timezone(timedelta(hours=8))
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def _stamp(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> str:
    """Format a Cursor ``<timestamp>`` payload in a fixed +08:00 zone."""

    moment = datetime(year, month, day, hour, minute, tzinfo=TZ)
    ampm = "AM" if moment.hour < 12 else "PM"
    display_hour = moment.hour % 12 or 12
    return "%s, %s %d, %d, %d:%02d %s (UTC+8)" % (
        WEEKDAYS[moment.weekday()],
        MONTHS[moment.month - 1],
        moment.day,
        moment.year,
        display_hour,
        moment.minute,
        ampm,
    )


def _epoch_ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    moment = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


def _user(text: str) -> Dict[str, Any]:
    return {
        "role": "user",
        "message": {"content": [{"type": "text", "text": text}]},
    }


def _assistant(text: str) -> Dict[str, Any]:
    return {
        "role": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
    }


def _assistant_with_tool(text: str, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "role": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": text},
                {"type": "tool_use", "name": name, "input": arguments},
            ]
        },
    }


def _turn_ended(status: str = "success", error: str = "") -> Dict[str, Any]:
    record: Dict[str, Any] = {"type": "turn_ended", "status": status}
    if error:
        record["error"] = error
    return record


def _metadata(overview: str) -> Dict[str, Any]:
    return {"type": "metadata", "metadata": {"overview": overview}}


def _prompt_body(stamp: str, text: str) -> str:
    return "<timestamp>%s</timestamp>\n<user_query>\n%s\n</user_query>" % (stamp, text)


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def _write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _session_path(home: Path, slug: str, session_id: str) -> Path:
    return (
        home
        / "projects"
        / slug
        / "agent-transcripts"
        / session_id
        / (session_id + ".jsonl")
    )


def _main_records() -> List[Dict[str, Any]]:
    return [
        _metadata(OVERVIEW),
        _user(
            _prompt_body(
                _stamp(2026, 10, 20, 9, 10),
                PROMPTS_MAIN[0],
            )
        ),
        _assistant("I'll read the adapter first."),
        _assistant_with_tool(
            "Reading the adapter.",
            "read_file",
            {"file_path": PROJECT_ALPHA + "/src/adapter.py"},
        ),
        _assistant_with_tool(
            "Applying the edit.",
            "edit_file",
            {"file_path": PROJECT_ALPHA + "/src/adapter.py"},
        ),
        _assistant_with_tool(
            "Recording the plan.",
            "todo_write",
            {
                "todos": [
                    {"content": "Bound the digest", "status": "completed"},
                    {"content": "Add prompt paging", "status": "in_progress"},
                ]
            },
        ),
        _user(_prompt_body(_stamp(2026, 10, 20, 9, 20), PROMPTS_MAIN[1])),
        _assistant("Continuing with the bounded digest."),
        _user(_prompt_body(_stamp(2026, 10, 20, 9, 30), PROMPTS_MAIN[2])),
        _assistant("The compact summary fallback is in place."),
        _user(_prompt_body(_stamp(2026, 10, 20, 9, 40), PROMPTS_MAIN[3])),
        _assistant(THINKING_BLOCK + "All bounded and ready."),
        _turn_ended("success"),
    ]


def _plain_records() -> List[Dict[str, Any]]:
    return [
        _user(_prompt_body(_stamp(2026, 10, 27, 15, 0), PROMPT_PLAIN)),
        _user(INJECTED_CONTEXT),
        _assistant("Checking the migration ledger. %s found here." % NEEDLE_DEEP_ONLY),
        _assistant(API_ERROR),
        _turn_ended("error", API_ERROR),
    ]


def _archived_records() -> List[Dict[str, Any]]:
    return [
        _user(_prompt_body(_stamp(2026, 10, 21, 10, 5), PROMPT_ARCHIVED)),
        _user(SUMMARY_REQUEST),
        _assistant("Archived reply. %s" % NEEDLE_ARCHIVED),
        _turn_ended("success"),
    ]


def _error_records() -> List[Dict[str, Any]]:
    return [_turn_ended("error", TURN_ERROR)]


def _subagent_records() -> List[Dict[str, Any]]:
    return [
        _user(_prompt_body(_stamp(2026, 10, 20, 9, 15), PROMPT_SUBAGENT)),
        _assistant("Subagent output."),
    ]


def _json_messages() -> List[Dict[str, Any]]:
    return [
        {
            "role": "user",
            "text": _prompt_body(_stamp(2026, 10, 22, 11, 0), "Document the Cursor store."),
        },
        {
            "role": "assistant",
            "text": "Documented.",
            "toolCalls": [
                {"toolName": "write_file", "args": {"file_path": PROJECT_BETA + "/docs/store.md"}}
            ],
        },
    ]


def _build_index(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute(
            "CREATE TABLE conversations ("
            "fts_rowid INTEGER, "
            "source TEXT, "
            "scope TEXT, "
            "id TEXT, "
            "title TEXT, "
            "branches TEXT, "
            "updated_at INTEGER, "
            "is_archived INTEGER DEFAULT 0, "
            "root_fingerprint TEXT, "
            "cache_fingerprint TEXT)"
        )
        rows = [
            (
                SESSION_MAIN,
                TITLE_MAIN,
                json.dumps(["feature/handoff"]),
                _epoch_ms(2026, 10, 20, 9, 45),
                0,
            ),
            (
                SESSION_PLAIN,
                TITLE_GENERIC,
                "",
                _epoch_ms(2026, 10, 27, 15, 30),
                0,
            ),
            (
                SESSION_ARCHIVED,
                TITLE_ARCHIVED,
                json.dumps(["main"]),
                _epoch_ms(2026, 10, 21, 10, 5),
                1,
            ),
            (
                SESSION_ERROR,
                TITLE_GENERIC,
                "",
                _epoch_ms(2026, 10, 19, 8, 0),
                0,
            ),
            (
                SESSION_EMPTY,
                TITLE_GENERIC,
                "",
                _epoch_ms(2026, 10, 19, 7, 55),
                1,
            ),
            (
                SESSION_JSON,
                TITLE_PLAIN,
                "",
                _epoch_ms(2026, 10, 22, 11, 5),
                0,
            ),
        ]
        connection.executemany(
            "INSERT INTO conversations "
            "(source, scope, id, title, branches, updated_at, is_archived) "
            "VALUES ('local', '', ?, ?, ?, ?, ?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()
    return path


def build_cursor_home(home: Path) -> Path:
    """Create a synthetic Cursor store under ``home``.

    The returned directory holds both the ``~/.cursor`` transcript store and a
    desktop ``User`` directory that holds the conversation index and the
    workspace manifests.
    """

    home.mkdir(parents=True, exist_ok=True)

    _write_jsonl(_session_path(home, SLUG_ALPHA, SESSION_MAIN), _main_records())
    _write_jsonl(_session_path(home, SLUG_GAMMA, SESSION_PLAIN), _plain_records())
    _write_jsonl(_session_path(home, SLUG_BETA, SESSION_ARCHIVED), _archived_records())
    _write_jsonl(_session_path(home, SLUG_BETA, SESSION_ERROR), _error_records())
    _write_jsonl(_session_path(home, SLUG_ALPHA, SESSION_EMPTY), _error_records())

    # --- JSON transcript variant -------------------------------------------
    _write_json(
        _session_path(home, SLUG_BETA, SESSION_JSON).with_suffix(".json"),
        {"mode": "agent", "messages": _json_messages()},
    )

    # --- subagent transcript: never a top-level session --------------------
    _write_jsonl(
        home
        / "projects"
        / SLUG_ALPHA
        / "agent-transcripts"
        / SESSION_MAIN
        / "subagents"
        / (SESSION_SUBAGENT + ".jsonl"),
        _subagent_records(),
    )

    # --- decoy files that must never be listed -----------------------------
    _write_jsonl(
        home / "projects" / SLUG_ALPHA / "canvases" / (SESSION_DECOY + ".jsonl"),
        [_user(_prompt_body(_stamp(2026, 10, 18, 12, 0), PROMPT_DECOY))],
    )
    _write_jsonl(
        home / "projects" / SLUG_GAMMA / "mcps" / "server" / (SESSION_DECOY + ".jsonl"),
        [_user(_prompt_body(_stamp(2026, 10, 18, 12, 5), PROMPT_DECOY))],
    )

    # --- desktop conversation index ----------------------------------------
    _build_index(home / "User" / "globalStorage" / "conversation-search.db")

    # --- workspace manifests that recover the real cwd ---------------------
    _write_json(
        home
        / "User"
        / "workspaceStorage"
        / "wsalpha0001"
        / "workspace.json",
        {"folder": "file://" + PROJECT_ALPHA},
    )
    _write_json(
        home
        / "User"
        / "workspaceStorage"
        / "wsbeta0001"
        / "workspace.json",
        {"folder": "file://" + PROJECT_BETA},
    )
    _write_json(
        home
        / "User"
        / "workspaceStorage"
        / "wsgamma001"
        / "workspace.json",
        {"folder": "file://" + PROJECT_GAMMA},
    )

    return home
