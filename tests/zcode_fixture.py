"""Build a synthetic ZCode store for tests.

ZCode sessions live in SQLite databases, which cannot be committed as text
fixtures, so every test class builds an invented store in a temporary
directory. All identifiers, paths, and prompts are synthetic.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

SESSION_DESKTOP = "session_c0de0001aaaabbbbcccc111111111111"
SESSION_CLI = "sess_c0de0002-2222-4b2c-9d2e-222222222222"
SESSION_ARCHIVED = "sess_c0de0003-3333-4c3d-9e4f-333333333333"
SESSION_DELETED = "sess_c0de0004-4444-4d4e-8f5a-444444444444"
SESSION_ARCHIVED_IN_PLACE = "sess_c0de0005-5555-4e5f-9a6b-555555555555"
SESSION_SUBAGENT = "sess_subagent_agent_c0de0006-6666-4f6a-8b7c-666666666666"

DISPLAY_DESKTOP = SESSION_DESKTOP[len("session_") :]
DISPLAY_CLI = SESSION_CLI[len("sess_") :]
DISPLAY_ARCHIVED = SESSION_ARCHIVED[len("sess_") :]
DISPLAY_DELETED = SESSION_DELETED[len("sess_") :]
DISPLAY_ARCHIVED_IN_PLACE = SESSION_ARCHIVED_IN_PLACE[len("sess_") :]

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_GAMMA = "/Users/example/project-gamma"
PROJECT_BETA = "/Users/example/project-beta"

PROMPTS_DESKTOP = (
    "Please refactor the handoff parser so the CLI digest stays bounded.",
    "继续",
    "Also add a compaction summary fallback when summaryMessageId is present.",
    "Run the parser tests and fix the two failures.",
    "别再改了，先记下欠账。",
)

MAIN_SCHEMA = """
CREATE TABLE session (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    workspace_id TEXT,
    directory TEXT,
    title TEXT,
    version TEXT,
    time_created INTEGER,
    time_updated INTEGER,
    time_archived INTEGER,
    time_deleted INTEGER,
    task_type TEXT
);
CREATE TABLE message (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    time_created INTEGER,
    time_updated INTEGER,
    sequence INTEGER,
    data TEXT
);
CREATE TABLE part (
    id TEXT PRIMARY KEY,
    message_id TEXT,
    session_id TEXT,
    time_created INTEGER,
    time_updated INTEGER,
    sequence INTEGER,
    data TEXT
);
CREATE TABLE todo (
    session_id TEXT,
    content TEXT,
    status TEXT,
    priority TEXT,
    position INTEGER,
    time_created INTEGER,
    time_updated INTEGER
);
"""

TASKS_SCHEMA = """
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    cli_deleted INTEGER NOT NULL DEFAULT 0
);
"""


def _ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp()
        * 1000
    )


def _human(cwd: str = "", branch: str = "") -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "role": "user",
        "semantics": {
            "origin": "real_user",
            "kind": "user_prompt",
            "uiVisibility": "visible",
            "providerVisibility": "visible",
            "transcriptVisibility": "visible",
        },
    }
    if cwd:
        data["contextSnapshot"] = {
            "envInfo": {
                "cwd": cwd,
                "gitBranch": branch,
                "platform": "darwin",
            }
        }
    return data


def _runtime_user(kind: str) -> Dict[str, Any]:
    return {
        "role": "user",
        "synthetic": True,
        "semantics": {
            "origin": "agent_runtime",
            "kind": kind,
            "uiVisibility": "hidden",
            "providerVisibility": "visible",
            "transcriptVisibility": "hidden",
        },
    }


def _assistant(model_id: str = "zcode-synthetic-1") -> Dict[str, Any]:
    return {
        "role": "assistant",
        "modelId": model_id,
        "semantics": {
            "origin": "agent_runtime",
            "kind": "assistant_response",
            "uiVisibility": "visible",
            "providerVisibility": "visible",
            "transcriptVisibility": "visible",
        },
    }


def _text(value: str) -> Dict[str, Any]:
    return {"type": "text", "text": value}


def _reasoning(value: str) -> Dict[str, Any]:
    return {"type": "reasoning", "text": value}


def _tool(name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "tool",
        "tool": name,
        "callID": "call_synthetic",
        "state": {"status": "completed", "input": tool_input},
    }


def _file_part(name: str) -> Dict[str, Any]:
    return {"type": "file", "filename": name, "url": "file:///Users/example/notes.txt"}


class _Writer:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.sequence = 0

    def session(
        self,
        session_id: str,
        directory: str,
        title: str,
        created: int,
        updated: int,
        version: str = "0.17.0",
        task_type: str = "interactive",
        parent_id: Optional[str] = None,
        time_archived: Optional[int] = None,
        time_deleted: Optional[int] = None,
    ) -> None:
        self.connection.execute(
            "INSERT INTO session (id, parent_id, workspace_id, directory, title, "
            "version, time_created, time_updated, time_archived, time_deleted, "
            "task_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                parent_id,
                "workspace_synthetic",
                directory,
                title,
                version,
                created,
                updated,
                time_archived,
                time_deleted,
                task_type,
            ),
        )

    def message(
        self,
        message_id: str,
        session_id: str,
        when: int,
        data: Dict[str, Any],
        parts: Iterable[Dict[str, Any]],
    ) -> None:
        payload = dict(data)
        payload.setdefault("time", {"created": when})
        self.connection.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, "
            "sequence, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                message_id,
                session_id,
                when,
                when,
                self.sequence,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        self.sequence += 1
        for index, part in enumerate(parts):
            self.connection.execute(
                "INSERT INTO part (id, message_id, session_id, time_created, "
                "time_updated, sequence, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "%s_p%d" % (message_id, index),
                    message_id,
                    session_id,
                    when,
                    when,
                    index,
                    json.dumps(part, ensure_ascii=False),
                ),
            )

    def todo(self, session_id: str, content: str, status: str, position: int) -> None:
        self.connection.execute(
            "INSERT INTO todo (session_id, content, status, priority, position, "
            "time_created, time_updated) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, content, status, "medium", position, _ms(2026, 10, 20), _ms(2026, 10, 20)),
        )


def build_zcode_home(home: Path) -> Path:
    """Create cli/db/db.sqlite and v2/tasks-index.sqlite under ``home``."""

    home.mkdir(parents=True, exist_ok=True)
    db_path = home / "cli" / "db" / "db.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.executescript(MAIN_SCHEMA)
        writer = _Writer(connection)

        writer.session(
            SESSION_DESKTOP,
            PROJECT_ALPHA,
            "Refactor handoff parser for the CLI",
            _ms(2026, 10, 20, 9, 10),
            _ms(2026, 10, 20, 10, 40),
        )
        writer.message(
            "msg_a01",
            SESSION_DESKTOP,
            _ms(2026, 10, 20, 9, 10),
            _human(PROJECT_ALPHA, "feature/handoff"),
            [_text(PROMPTS_DESKTOP[0])],
        )
        writer.message(
            "msg_a02",
            SESSION_DESKTOP,
            _ms(2026, 10, 20, 9, 11),
            _assistant(),
            [
                _reasoning("Synthetic planning notes."),
                _text("I'll start by reading the parser and its tests."),
                _tool("Read", {"file_path": "src/handoff.ts"}),
                _tool("Write", {"file_path": "src/handoff.ts"}),
            ],
        )
        writer.message(
            "msg_a03",
            SESSION_DESKTOP,
            _ms(2026, 10, 20, 10, 0),
            _runtime_user("todo_reminder"),
            [
                _text(
                    "<system-reminder>You have not used the TodoWrite tool "
                    "recently. Please update your todos.</system-reminder>"
                )
            ],
        )
        writer.message(
            "msg_a04",
            SESSION_DESKTOP,
            _ms(2026, 10, 20, 10, 5),
            {"role": "user"},
            [_text(PROMPTS_DESKTOP[1])],
        )
        writer.message(
            "msg_a05",
            SESSION_DESKTOP,
            _ms(2026, 10, 20, 10, 20),
            _human(),
            [_text(PROMPTS_DESKTOP[2]), _file_part("notes.txt")],
        )
        writer.message(
            "msg_a06",
            SESSION_DESKTOP,
            _ms(2026, 10, 20, 10, 25),
            {
                "role": "user",
                "semantics": {
                    "origin": "agent_runtime",
                    "kind": "compact_summary",
                    "uiVisibility": "hidden",
                    "providerVisibility": "visible",
                    "transcriptVisibility": "hidden",
                },
            },
            [_text("Handoff parser work summarized.")],
        )
        hidden = _human()
        hidden["semantics"]["transcriptVisibility"] = "hidden"
        writer.message(
            "msg_a07",
            SESSION_DESKTOP,
            _ms(2026, 10, 20, 10, 30),
            hidden,
            [_text("This hidden row must not appear.")],
        )
        writer.message(
            "msg_a08",
            SESSION_DESKTOP,
            _ms(2026, 10, 20, 10, 31),
            _assistant(),
            [
                _text("Added the fallback."),
                _tool("Edit", {"file_path": "src/handoff.ts"}),
                _tool("Edit", {"file_path": "docs/handoff.md"}),
                _tool(
                    "Bash",
                    {
                        "command": "python3 -m unittest tests.test_handoff",
                        "description": "Run parser tests",
                    },
                ),
            ],
        )
        writer.message(
            "msg_a09",
            SESSION_DESKTOP,
            _ms(2026, 10, 20, 10, 35),
            _human(),
            [_text(PROMPTS_DESKTOP[3])],
        )
        error = _assistant()
        error["error"] = {"name": "APIError", "data": {"message": "exceed quota limit"}}
        writer.message(
            "msg_a10",
            SESSION_DESKTOP,
            _ms(2026, 10, 20, 10, 36),
            error,
            [],
        )
        writer.message(
            "msg_a11",
            SESSION_DESKTOP,
            _ms(2026, 10, 20, 10, 40),
            {"role": "user"},
            [_text(PROMPTS_DESKTOP[4])],
        )
        writer.todo(SESSION_DESKTOP, "Refactor handoff parser", "pending", 0)
        writer.todo(SESSION_DESKTOP, "Document compaction fallback", "in_progress", 1)
        writer.todo(SESSION_DESKTOP, "Trim digest output", "completed", 2)

        writer.session(
            SESSION_CLI,
            PROJECT_GAMMA,
            "",
            _ms(2026, 10, 27, 15, 0),
            _ms(2026, 10, 27, 15, 30),
        )
        writer.message(
            "msg_b01",
            SESSION_CLI,
            _ms(2026, 10, 27, 15, 0),
            _human(PROJECT_GAMMA, "main"),
            [_text("Investigate the migration drift in project gamma.")],
        )
        writer.message(
            "msg_b02",
            SESSION_CLI,
            _ms(2026, 10, 27, 15, 1),
            _assistant("zcode-synthetic-2"),
            [
                _text("Checking the migration ledger."),
                _text("deep-only-needle found in the transcript."),
                _tool("Edit", {"file_path": "src/migrate.ts"}),
            ],
        )
        writer.message(
            "msg_b03",
            SESSION_CLI,
            _ms(2026, 10, 27, 15, 20),
            _runtime_user("system_reminder"),
            [_text("Compaction fallback summary for project gamma.")],
        )
        writer.message(
            "msg_b04",
            SESSION_CLI,
            _ms(2026, 10, 27, 15, 21),
            _assistant("zcode-synthetic-2"),
            [
                {"type": "compaction", "summaryMessageId": "msg_b03"},
                _text("Resuming after compaction."),
            ],
        )
        writer.message(
            "msg_b05",
            SESSION_CLI,
            _ms(2026, 10, 27, 15, 30),
            {"role": "user"},
            [_text("继续")],
        )

        writer.session(
            SESSION_ARCHIVED,
            PROJECT_BETA,
            "Quota recovery notes",
            _ms(2026, 10, 21, 9, 30),
            _ms(2026, 10, 21, 10, 5),
        )
        writer.message(
            "msg_c01",
            SESSION_ARCHIVED,
            _ms(2026, 10, 21, 9, 30),
            _human(PROJECT_BETA, "main"),
            [_text("The archived-needle lives here.")],
        )
        writer.message(
            "msg_c02",
            SESSION_ARCHIVED,
            _ms(2026, 10, 21, 10, 5),
            _assistant(),
            [_text("Archived work.")],
        )

        writer.session(
            SESSION_DELETED,
            PROJECT_ALPHA,
            "Deleted scratch session",
            _ms(2026, 10, 24, 10, 0),
            _ms(2026, 10, 24, 11, 10),
        )
        writer.message(
            "msg_d01",
            SESSION_DELETED,
            _ms(2026, 10, 24, 10, 0),
            _human(PROJECT_ALPHA),
            [_text("Scratch notes that were deleted.")],
        )

        writer.session(
            SESSION_ARCHIVED_IN_PLACE,
            PROJECT_GAMMA,
            "Session archived in place",
            _ms(2026, 10, 25, 7, 0),
            _ms(2026, 10, 25, 8, 0),
            time_archived=_ms(2026, 10, 25, 9, 0),
        )
        writer.message(
            "msg_e01",
            SESSION_ARCHIVED_IN_PLACE,
            _ms(2026, 10, 25, 7, 0),
            _human(PROJECT_GAMMA),
            [_text("Archived in place.")],
        )

        writer.session(
            SESSION_SUBAGENT,
            PROJECT_ALPHA,
            "Subagent child work",
            _ms(2026, 10, 26, 11, 0),
            _ms(2026, 10, 26, 12, 0),
            task_type="subagent_child",
            parent_id=SESSION_DESKTOP,
        )
        writer.message(
            "msg_f01",
            SESSION_SUBAGENT,
            _ms(2026, 10, 26, 11, 0),
            _human(PROJECT_ALPHA),
            [_text("Subagent should not be listed.")],
        )

        connection.commit()
    finally:
        connection.close()

    app_path = home / "v2" / "tasks-index.sqlite"
    app_path.parent.mkdir(parents=True, exist_ok=True)
    app_connection = sqlite3.connect(str(app_path))
    try:
        app_connection.execute("PRAGMA journal_mode=DELETE")
        app_connection.executescript(TASKS_SCHEMA)
        app_connection.executemany(
            "INSERT INTO tasks (task_id, title, archived, deleted, cli_deleted) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                (SESSION_ARCHIVED, "Quota recovery notes", 1, 0, 0),
                (SESSION_DELETED, "Deleted scratch session", 0, 0, 1),
            ),
        )
        app_connection.commit()
    finally:
        app_connection.close()
    return home
