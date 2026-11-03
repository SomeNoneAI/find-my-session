"""Build a synthetic domestic WorkBuddy store for tests.

The domestic edition keeps the same JSONL layout as WorkBuddy AI but a separate
home and a ``sessions`` table without the ``visibility`` column. It also writes
``<cb_summary>`` compaction records and a trailing ``summary`` record holding
the initial prompt. Every identifier, path, and prompt is invented.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

SESSION_MAIN = "d0d0c001-aaaa-bbbb-cccc-111111111111"
SESSION_PLAIN = "d0d0c002-aaaa-bbbb-cccc-222222222222"
SESSION_ARCHIVED = "d0d0c003-aaaa-bbbb-cccc-333333333333"
SESSION_DELETED = "d0d0c004-aaaa-bbbb-cccc-444444444444"
SESSION_CLOUD = "d0d0c005-aaaa-bbbb-cccc-555555555555"
SESSION_ORPHAN = "d0d0c006-aaaa-bbbb-cccc-666666666666"
SESSION_EMPTY = "d0d0c007-aaaa-bbbb-cccc-777777777777"

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_GAMMA = "/Users/example/project-gamma"
PROJECT_BETA = "/Users/example/project-beta"

SLUG_ALPHA = "Users-example-project-alpha"
SLUG_GAMMA = "Users-example-project-gamma"
SLUG_BETA = "Users-example-project-beta"

PROMPTS_MAIN = (
    "Please refactor the handoff digest so the CLI stays bounded.",
    "继续",
    "Ship the compact summary fallback.",
)
PROMPT_PLAIN = "Investigate the migration drift in project gamma."
PROMPT_ORPHAN = "Orphan transcript without a row."
PROMPT_ARCHIVED = "The archived-needle lives here."
PROMPT_DELETED = "Deleted scratch notes."
PROMPT_CLOUD = "Cloud transport session."

COMPACT_SUMMARY = (
    "Summary of the conversation so far:\n"
    "The conversation is between an AI agent and a user.\n"
    "A previous turn asked to bound the handoff digest."
)

DB_SCHEMA = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    cwd TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT,
    custom_title TEXT,
    status TEXT NOT NULL DEFAULT 'Pending',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted_at INTEGER,
    is_playground INTEGER NOT NULL DEFAULT 0,
    model TEXT,
    last_activity_at INTEGER,
    source_mode TEXT,
    mode TEXT
);
CREATE TABLE session_usage (
    session_id TEXT PRIMARY KEY,
    used INTEGER,
    size INTEGER,
    updated_at INTEGER
);
"""

REMINDER = (
    '<system-reminder data-role="user-context">\n'
    "<user_info>\nOS Version: darwin\nWorkspace Folder: /Users/example/project-alpha\n"
    "</user_info>\n</system-reminder>"
)

_SESSION_CWD = {
    SESSION_MAIN: PROJECT_ALPHA,
    SESSION_PLAIN: PROJECT_GAMMA,
    SESSION_ARCHIVED: PROJECT_BETA,
    SESSION_DELETED: PROJECT_BETA,
    SESSION_CLOUD: PROJECT_BETA,
    SESSION_ORPHAN: PROJECT_GAMMA,
    SESSION_EMPTY: PROJECT_GAMMA,
}


def _ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp()
        * 1000
    )


def _record(record_type: str, session_id: str, when: int, **fields: Any) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "type": record_type,
        "sessionId": session_id,
        "timestamp": when,
    }
    cwd = _SESSION_CWD.get(session_id)
    if cwd:
        record["cwd"] = cwd
    record.update(fields)
    return record


def _user_message(
    session_id: str,
    when: int,
    text: str,
    message_id: str = "msg",
    local: bool = False,
    is_meta: bool = False,
) -> Dict[str, Any]:
    provider: Dict[str, Any] = {"agent": "cli"}
    if is_meta:
        provider["isMeta"] = True
    record = _record(
        "message",
        session_id,
        when,
        id=message_id,
        role="user",
        providerData=provider,
        content=[{"type": "input_text", "text": text}],
    )
    if local:
        record["__codebuddyLocal"] = {"sensitiveUserInputReviewed": True}
    return record


def _assistant_message(
    session_id: str, when: int, text: str, model: str = "wb-cn-synthetic-1"
) -> Dict[str, Any]:
    return _record(
        "message",
        session_id,
        when,
        id="msg-assistant-%d" % when,
        role="assistant",
        status="completed",
        providerData={
            "agent": "cli",
            "requestModelId": model,
            "requestModelName": model,
        },
        content=[{"type": "output_text", "text": text}],
    )


def _function_call(
    session_id: str, when: int, name: str, arguments: Dict[str, Any]
) -> Dict[str, Any]:
    return _record(
        "function_call",
        session_id,
        when,
        id="call-%d" % when,
        callId="call_synthetic_%d" % when,
        name=name,
        arguments=json.dumps(arguments, ensure_ascii=False),
        providerData={"agent": "cli", "requestModelId": "wb-cn-synthetic-1"},
    )


def _function_result(
    session_id: str, when: int, name: str, text: str = "synthetic output"
) -> Dict[str, Any]:
    return _record(
        "function_call_result",
        session_id,
        when,
        id="result-%d" % when,
        callId="call_synthetic_%d" % when,
        name=name,
        status="completed",
        output={"type": "text", "text": text},
    )


def _compaction_message(session_id: str, when: int) -> Dict[str, Any]:
    content = (
        "<cb_summary>\n%s\n\n"
        "<previous_user_message>\n<user_query>%s</user_query>\n</previous_user_message>\n"
        "<previous_user_message>\n<user_query>%s</user_query>\n</previous_user_message>\n"
        "</cb_summary>"
    ) % (COMPACT_SUMMARY, PROMPTS_MAIN[0], PROMPTS_MAIN[1])
    return _record(
        "message",
        session_id,
        when,
        id="compact-1",
        role="user",
        providerData={
            "agent": "cli",
            "skipRun": False,
            "compactType": "pre-message-auto",
            "isCompacted": True,
            "isCompactInternal": True,
            "isSummary": False,
        },
        content=[{"type": "input_text", "text": content}],
    )


def _summary_record(session_id: str, when: int, text: str) -> Dict[str, Any]:
    return _record(
        "summary",
        session_id,
        when,
        summary=text,
        providerData={"source": "initial-user-message"},
    )


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _session_row(
    connection: sqlite3.Connection,
    session_id: str,
    cwd: str,
    created: int,
    updated: int,
    title: Optional[str] = None,
    status: str = "completed",
    deleted_at: Optional[int] = None,
    model: str = "wb-cn-synthetic-1",
    custom_title: Optional[str] = None,
) -> None:
    connection.execute(
        "INSERT INTO sessions (id, cwd, user_id, title, custom_title, status, "
        "created_at, updated_at, deleted_at, is_playground, model, "
        "last_activity_at, source_mode, mode) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            cwd,
            "user_synthetic",
            title,
            custom_title,
            status,
            created,
            updated,
            deleted_at,
            0,
            model,
            updated,
            "craft",
            "craft",
        ),
    )


def build_workbuddy_cn_home(home: Path) -> Path:
    """Create ``projects/``, ``tasks/``, and ``workbuddy.db`` under ``home``."""

    home.mkdir(parents=True, exist_ok=True)
    projects = home / "projects"

    # --- main session: local prompts, tools, compaction, summary, todos -----
    main_path = projects / SLUG_ALPHA / (SESSION_MAIN + ".jsonl")
    main_records = [
        _user_message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 10),
            REMINDER + "\n<user_query>%s</user_query>" % PROMPTS_MAIN[0],
            message_id="msg-a01",
            local=True,
        ),
        _assistant_message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 11),
            "I'll read the parser first. main-only-needle.",
        ),
        _function_call(
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 12),
            "Read",
            {"file_path": "/Users/example/project-alpha/src/handoff.ts"},
        ),
        _function_result(SESSION_MAIN, _ms(2026, 10, 20, 9, 13), "Read"),
        _function_call(
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 14),
            "Edit",
            {
                "file_path": "/Users/example/project-alpha/src/handoff.ts",
                "old_string": "a",
                "new_string": "b",
            },
        ),
        _function_result(SESSION_MAIN, _ms(2026, 10, 20, 9, 15), "Edit"),
        _function_call(
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 16),
            "Edit",
            {"file_path": "docs/handoff.md", "old_string": "a", "new_string": "b"},
        ),
        _record(
            "ai-title",
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 17),
            id="title-1",
            aiTitle="AI title that the database should override",
        ),
        _record(
            "reasoning",
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 18),
            id="reason-1",
            content=[],
            rawContent=[{"type": "reasoning_text", "text": "Synthetic reasoning."}],
        ),
        _user_message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 0),
            REMINDER + "\n<user_query>%s</user_query>" % PROMPTS_MAIN[1],
            message_id="msg-a02",
        ),
        _function_call(
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 1),
            "Bash",
            {"command": "python3 -m unittest tests.test_handoff", "description": "Run tests"},
        ),
        _function_result(SESSION_MAIN, _ms(2026, 10, 20, 10, 2), "Bash"),
        _user_message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 3),
            "<task-notification>\n<task-id>AB12CD</task-id>\n<status>completed</status>\n"
            "</task-notification>",
            message_id="msg-a03",
            is_meta=True,
        ),
        _user_message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 4),
            REMINDER,
            message_id="msg-a04",
            is_meta=True,
        ),
        _compaction_message(SESSION_MAIN, _ms(2026, 10, 20, 10, 5)),
        _user_message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 6),
            REMINDER + "\n<user_query>%s</user_query>" % PROMPTS_MAIN[2],
            message_id="msg-a05",
            local=True,
        ),
        _assistant_message(
            SESSION_MAIN, _ms(2026, 10, 20, 10, 7), "Compaction recorded."
        ),
        _summary_record(SESSION_MAIN, _ms(2026, 10, 20, 10, 8), PROMPTS_MAIN[0]),
        _record(
            "file-history-snapshot",
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 9),
            id="snap-1",
            messageId="msg-a05",
            isSnapshotUpdate=False,
            snapshot={"messageId": "msg-a05", "trackedFileBackups": {}},
        ),
    ]
    _write_jsonl(main_path, main_records)
    _write_jsonl(
        projects / SLUG_ALPHA / (SESSION_MAIN + ".file-rollback.ndjson"),
        [{"type": "rollback", "sessionId": SESSION_MAIN, "path": "src/handoff.ts"}],
    )
    tool_results = projects / SLUG_ALPHA / SESSION_MAIN / "tool-results"
    tool_results.mkdir(parents=True, exist_ok=True)
    (tool_results / "call_synthetic_0.txt").write_text(
        "synthetic tool output\n", encoding="utf-8"
    )

    tasks = home / "tasks" / SESSION_MAIN
    tasks.mkdir(parents=True, exist_ok=True)
    for index, (subject, status) in enumerate(
        (
            ("Refactor handoff digest", "pending"),
            ("Document compaction fallback", "in_progress"),
            ("Trim digest output", "completed"),
        ),
        1,
    ):
        (tasks / ("%d.json" % index)).write_text(
            json.dumps(
                {
                    "subject": subject,
                    "description": "synthetic",
                    "activeForm": "synthetic",
                    "status": status,
                    "id": str(index),
                    "createdAt": _ms(2026, 10, 20, 9, 10),
                    "updatedAt": _ms(2026, 10, 20, 9, 20),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # --- plain session: no db title, no todos, deep-only needle -------------
    plain_path = projects / SLUG_GAMMA / (SESSION_PLAIN + ".jsonl")
    _write_jsonl(
        plain_path,
        [
            _user_message(
                SESSION_PLAIN,
                _ms(2026, 10, 27, 15, 0),
                REMINDER + "\n<user_query>%s</user_query>" % PROMPT_PLAIN,
                message_id="msg-b01",
                local=True,
            ),
            _assistant_message(
                SESSION_PLAIN,
                _ms(2026, 10, 27, 15, 1),
                "Checking the migration ledger. deep-only-needle found here.",
                model="wb-cn-synthetic-2",
            ),
            _user_message(
                SESSION_PLAIN,
                _ms(2026, 10, 27, 15, 30),
                REMINDER + "\n<user_query>继续</user_query>",
                message_id="msg-b02",
            ),
        ],
    )

    # --- archived session ---------------------------------------------------
    archived_path = projects / SLUG_BETA / (SESSION_ARCHIVED + ".jsonl")
    _write_jsonl(
        archived_path,
        [
            _user_message(
                SESSION_ARCHIVED,
                _ms(2026, 10, 21, 9, 30),
                REMINDER + "\n<user_query>%s</user_query>" % PROMPT_ARCHIVED,
                message_id="msg-c01",
            ),
            _assistant_message(
                SESSION_ARCHIVED, _ms(2026, 10, 21, 10, 5), "Archived work."
            ),
        ],
    )

    # --- deleted session ----------------------------------------------------
    deleted_path = projects / SLUG_BETA / (SESSION_DELETED + ".jsonl")
    _write_jsonl(
        deleted_path,
        [
            _user_message(
                SESSION_DELETED,
                _ms(2026, 10, 24, 10, 0),
                REMINDER + "\n<user_query>%s</user_query>" % PROMPT_DELETED,
                message_id="msg-d01",
            )
        ],
    )

    # --- cloud session: -1 is a "never deleted" sentinel --------------------
    cloud_path = projects / SLUG_BETA / (SESSION_CLOUD + ".jsonl")
    _write_jsonl(
        cloud_path,
        [
            _user_message(
                SESSION_CLOUD,
                _ms(2026, 10, 23, 9, 0),
                REMINDER + "\n<user_query>%s</user_query>" % PROMPT_CLOUD,
                message_id="msg-e01",
            )
        ],
    )

    # --- orphan transcript with no database row -----------------------------
    orphan_path = projects / SLUG_GAMMA / (SESSION_ORPHAN + ".jsonl")
    _write_jsonl(
        orphan_path,
        [
            _user_message(
                SESSION_ORPHAN,
                _ms(2026, 10, 25, 8, 0),
                REMINDER + "\n<user_query>%s</user_query>" % PROMPT_ORPHAN,
                message_id="msg-f01",
            )
        ],
    )

    # --- empty transcript: created when a session opens, never resumable ----
    empty_path = projects / SLUG_GAMMA / (SESSION_EMPTY + ".jsonl")
    empty_path.write_bytes(b"")

    stamps = {
        main_path: _ms(2026, 10, 20, 10, 9) / 1000,
        plain_path: _ms(2026, 10, 27, 15, 30) / 1000,
        archived_path: _ms(2026, 10, 21, 10, 5) / 1000,
        deleted_path: _ms(2026, 10, 24, 10, 0) / 1000,
        cloud_path: _ms(2026, 10, 23, 9, 0) / 1000,
        orphan_path: _ms(2026, 10, 25, 8, 0) / 1000,
        empty_path: _ms(2026, 10, 26, 12, 0) / 1000,
    }
    for path, stamp in stamps.items():
        os.utime(path, (stamp, stamp))

    db_path = home / "workbuddy.db"
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.executescript(DB_SCHEMA)
        _session_row(
            connection,
            SESSION_MAIN,
            PROJECT_ALPHA,
            _ms(2026, 10, 20, 9, 10),
            _ms(2026, 10, 20, 10, 9),
            title="Refactor handoff digest for the CLI",
        )
        _session_row(
            connection,
            SESSION_PLAIN,
            PROJECT_GAMMA,
            _ms(2026, 10, 27, 15, 0),
            _ms(2026, 10, 27, 15, 30),
            title=None,
            model="wb-cn-synthetic-2",
        )
        _session_row(
            connection,
            SESSION_ARCHIVED,
            PROJECT_BETA,
            _ms(2026, 10, 21, 9, 30),
            _ms(2026, 10, 21, 10, 5),
            title="Quota recovery notes",
            status="archived",
        )
        _session_row(
            connection,
            SESSION_DELETED,
            PROJECT_BETA,
            _ms(2026, 10, 24, 10, 0),
            _ms(2026, 10, 24, 11, 10),
            title="Deleted scratch session",
            deleted_at=_ms(2026, 10, 24, 11, 30),
        )
        _session_row(
            connection,
            SESSION_CLOUD,
            PROJECT_BETA,
            _ms(2026, 10, 23, 9, 0),
            _ms(2026, 10, 23, 9, 30),
            title="Cloud transport session",
            deleted_at=-1,
        )
        _session_row(
            connection,
            SESSION_EMPTY,
            PROJECT_GAMMA,
            _ms(2026, 10, 26, 12, 0),
            _ms(2026, 10, 26, 12, 0),
            title="Empty placeholder",
        )
        connection.commit()
    finally:
        connection.close()
    return home
