"""Build a synthetic CodeArts Agent store for tests.

CodeArts Agent keeps sessions in one SQLite database built on the opencode
schema, so the fixture is generated at runtime instead of being committed as
a binary file. Every identifier, path, and prompt is invented.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

SESSION_MAIN = "ses_c0de1001aaaabbbbcccc111111111111"
SESSION_PLAIN = "ses_c0de1002aaaabbbbcccc222222222222"
SESSION_ARCHIVED = "ses_c0de1003aaaabbbbcccc333333333333"
SESSION_CHILD = "ses_c0de1004aaaabbbbcccc444444444444"

DISPLAY_MAIN = SESSION_MAIN[len("ses_") :]
DISPLAY_PLAIN = SESSION_PLAIN[len("ses_") :]
DISPLAY_ARCHIVED = SESSION_ARCHIVED[len("ses_") :]

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_GAMMA = "/Users/example/project-gamma"
PROJECT_BETA = "/Users/example/project-beta"

BRANCH_MAIN = "feature/handoff"

PROMPTS_MAIN = (
    "Please refactor the handoff digest so the CLI stays bounded.",
    "继续",
    "Also cover the compaction fallback path.",
    "Run the parser tests and fix the failures.",
    "别再改了，先记下欠账。",
)

SCHEMA = """
CREATE TABLE project (
    id TEXT PRIMARY KEY,
    worktree TEXT NOT NULL,
    vcs TEXT,
    name TEXT,
    time_created INTEGER NOT NULL,
    time_updated INTEGER NOT NULL
);
CREATE TABLE workspace (
    id TEXT PRIMARY KEY,
    branch TEXT,
    project_id TEXT NOT NULL,
    type TEXT NOT NULL,
    name TEXT,
    directory TEXT,
    extra TEXT
);
CREATE TABLE session (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    parent_id TEXT,
    slug TEXT NOT NULL,
    directory TEXT NOT NULL,
    title TEXT NOT NULL,
    version TEXT NOT NULL,
    share_url TEXT,
    revert TEXT,
    permission TEXT,
    time_created INTEGER NOT NULL,
    time_updated INTEGER NOT NULL,
    time_compacting INTEGER,
    time_archived INTEGER,
    workspace_id TEXT
);
CREATE TABLE message (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    time_created INTEGER NOT NULL,
    time_updated INTEGER NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE part (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    time_created INTEGER NOT NULL,
    time_updated INTEGER NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE todo (
    session_id TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    position INTEGER NOT NULL,
    time_created INTEGER NOT NULL,
    time_updated INTEGER NOT NULL
);
CREATE TABLE cag_session_extra (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    has_origin_session INTEGER,
    origin_session_version TEXT,
    origin_session TEXT,
    extra_info TEXT,
    type TEXT,
    user TEXT,
    is_favorite INTEGER DEFAULT 0,
    favorite_at INTEGER
);
"""


def _ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp()
        * 1000
    )


def _human(prompt: str, cwd: str = "", model: str = "codearts-synthetic-1") -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "role": "user",
        "agent": "build",
        "model": {"providerID": "synthetic-provider", "modelID": model},
        "summary": {"diffs": []},
    }
    if cwd:
        data["path"] = {"cwd": cwd, "root": cwd}
    return data


def _assistant(
    cwd: str = "",
    model: str = "codearts-synthetic-1",
    agent: str = "build",
    summary: Optional[bool] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "role": "assistant",
        "agent": agent,
        "mode": agent,
        "modelID": model,
        "providerID": "synthetic-provider",
        "cost": 0,
        "tokens": {"input": 0, "output": 0, "reasoning": 0},
    }
    if summary is not None:
        data["summary"] = summary
    if cwd:
        data["path"] = {"cwd": cwd, "root": cwd}
    return data


def _text(value: str) -> Dict[str, Any]:
    return {"type": "text", "text": value, "metadata": {"isUserInput": True}}


def _synthetic_text(value: str) -> Dict[str, Any]:
    return {"type": "text", "text": value, "synthetic": True}


def _reasoning(value: str) -> Dict[str, Any]:
    return {"type": "reasoning", "text": value}


def _tool(name: str, tool_input: Dict[str, Any], status: str = "completed") -> Dict[str, Any]:
    state: Dict[str, Any] = {"status": status, "input": tool_input}
    if status == "completed":
        state["output"] = "synthetic tool output"
        state["title"] = tool_input.get("description") or ""
        state["metadata"] = {"truncated": False}
    else:
        state["error"] = "synthetic tool failure"
    return {"type": "tool", "tool": name, "callID": "call_synthetic", "state": state}


def _compaction_marker() -> Dict[str, Any]:
    return {"type": "compaction", "auto": True}


class _Writer:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def session(
        self,
        session_id: str,
        directory: str,
        title: str,
        created: int,
        updated: int,
        version: str = "1.0.0-synthetic",
        parent_id: Optional[str] = None,
        time_archived: Optional[int] = None,
        workspace_id: Optional[str] = None,
    ) -> None:
        self.connection.execute(
            "INSERT INTO session (id, project_id, parent_id, slug, directory, title, "
            "version, share_url, revert, permission, time_created, time_updated, "
            "time_compacting, time_archived, workspace_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                "project_synthetic",
                parent_id,
                "synthetic-slug",
                directory,
                title,
                version,
                None,
                None,
                None,
                created,
                updated,
                None,
                time_archived,
                workspace_id,
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
            "INSERT INTO message (id, session_id, time_created, time_updated, data) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                message_id,
                session_id,
                when,
                when,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        for index, part in enumerate(parts):
            self.connection.execute(
                "INSERT INTO part (id, message_id, session_id, time_created, "
                "time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "%s_p%d" % (message_id, index),
                    message_id,
                    session_id,
                    when,
                    when,
                    json.dumps(part, ensure_ascii=False),
                ),
            )

    def todo(self, session_id: str, content: str, status: str, position: int) -> None:
        self.connection.execute(
            "INSERT INTO todo (session_id, content, status, priority, position, "
            "time_created, time_updated) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                content,
                status,
                "medium",
                position,
                _ms(2026, 10, 20),
                _ms(2026, 10, 20),
            ),
        )


def build_codearts_home(home: Path) -> Path:
    """Create ``codearts-data/opencode.db`` under ``home``."""

    home.mkdir(parents=True, exist_ok=True)
    db_path = home / "codearts-data" / "opencode.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO project (id, worktree, vcs, name, time_created, "
            "time_updated) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "project_synthetic",
                PROJECT_ALPHA,
                "git",
                "",
                _ms(2026, 10, 20),
                _ms(2026, 10, 20),
            ),
        )
        connection.execute(
            "INSERT INTO workspace (id, branch, project_id, type, name, "
            "directory, extra) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "wrk_synthetic",
                BRANCH_MAIN,
                "project_synthetic",
                "local",
                "",
                PROJECT_ALPHA,
                None,
            ),
        )
        writer = _Writer(connection)

        writer.session(
            SESSION_MAIN,
            PROJECT_ALPHA,
            "Refactor handoff digest for the CLI",
            _ms(2026, 10, 20, 9, 10),
            _ms(2026, 10, 20, 10, 40),
            workspace_id="wrk_synthetic",
        )
        writer.message(
            "msg_a01",
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 10),
            _human(PROMPTS_MAIN[0], PROJECT_ALPHA),
            [
                _text(PROMPTS_MAIN[0]),
                _synthetic_text(
                    "<system-reminder>Always answer in the project language."
                    "</system-reminder>"
                ),
            ],
        )
        writer.message(
            "msg_a02",
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 11),
            _assistant(PROJECT_ALPHA),
            [
                {"type": "step-start"},
                _reasoning("Synthetic planning notes."),
                _text("I'll start by reading the parser and its tests."),
                _tool("read", {"filePath": "src/handoff.ts"}),
                _tool("write", {"filePath": "/Users/example/project-alpha/src/handoff.ts"}),
                {"type": "step-finish", "reason": "tool-calls"},
            ],
        )
        writer.message(
            "msg_a03",
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 0),
            {"role": "user", "agent": "build"},
            [
                _synthetic_text(
                    "<system-reminder>You have not used the TodoWrite tool "
                    "recently. Please update your todos.</system-reminder>"
                )
            ],
        )
        writer.message(
            "msg_a04",
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 5),
            _human(PROMPTS_MAIN[1], PROJECT_ALPHA),
            [_text(PROMPTS_MAIN[1]), _synthetic_text("<system-reminder>reminder</system-reminder>")],
        )
        writer.message(
            "msg_a05",
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 20),
            _assistant(PROJECT_ALPHA),
            [
                _text("Added the fallback."),
                _tool("edit", {"filePath": "/Users/example/project-alpha/src/handoff.ts"}),
                _tool("edit", {"filePath": "docs/handoff.md"}),
                _tool(
                    "bash",
                    {
                        "command": "python3 -m unittest tests.test_handoff",
                        "description": "Run parser tests",
                    },
                ),
            ],
        )
        writer.message(
            "msg_a06",
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 24),
            _human(PROMPTS_MAIN[2], PROJECT_ALPHA),
            [_text(PROMPTS_MAIN[2])],
        )
        writer.message(
            "msg_a07",
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 25),
            {"role": "user", "agent": "build"},
            [_compaction_marker()],
        )
        writer.message(
            "msg_a08",
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 26),
            _assistant(PROJECT_ALPHA, agent="compaction", summary=True),
            [_text("Handoff parser work summarized.")],
        )
        writer.message(
            "msg_a09",
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 30),
            _human(PROMPTS_MAIN[3], PROJECT_ALPHA),
            [_text(PROMPTS_MAIN[3])],
        )
        error = _assistant(PROJECT_ALPHA)
        error["error"] = {"name": "APIError", "data": {"message": "exceed quota limit"}}
        writer.message(
            "msg_a10",
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 36),
            error,
            [
                _text("Tests pass."),
                _tool("bash", {"command": "pnpm test", "description": "Run tests"}),
                _tool(
                    "edit",
                    {"filePath": "/Users/example/project-alpha/src/handoff.ts"},
                    status="error",
                ),
            ],
        )
        writer.message(
            "msg_a11",
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 40),
            _human(PROMPTS_MAIN[4], PROJECT_ALPHA),
            [_text(PROMPTS_MAIN[4])],
        )
        writer.todo(SESSION_MAIN, "Refactor handoff digest", "pending", 0)
        writer.todo(SESSION_MAIN, "Document compaction fallback", "in_progress", 1)
        writer.todo(SESSION_MAIN, "Trim digest output", "completed", 2)

        writer.session(
            SESSION_PLAIN,
            PROJECT_GAMMA,
            "",
            _ms(2026, 10, 27, 15, 0),
            _ms(2026, 10, 27, 15, 30),
        )
        writer.message(
            "msg_b01",
            SESSION_PLAIN,
            _ms(2026, 10, 27, 15, 0),
            _human("Investigate the migration drift in project gamma.", PROJECT_GAMMA),
            [_text("Investigate the migration drift in project gamma.")],
        )
        writer.message(
            "msg_b02",
            SESSION_PLAIN,
            _ms(2026, 10, 27, 15, 1),
            _assistant(PROJECT_GAMMA, model="codearts-synthetic-2"),
            [
                _text("Checking the migration ledger."),
                _text("deep-only-needle found in the transcript."),
                _tool("edit", {"filePath": "src/migrate.ts"}),
            ],
        )
        writer.message(
            "msg_b03",
            SESSION_PLAIN,
            _ms(2026, 10, 27, 15, 20),
            {"role": "user", "agent": "build"},
            [
                _synthetic_text(
                    "Continue if you have next steps, or stop and ask for "
                    "clarification if you are unsure."
                )
            ],
        )
        writer.message(
            "msg_b04",
            SESSION_PLAIN,
            _ms(2026, 10, 27, 15, 30),
            _human(PROMPTS_MAIN[1], PROJECT_GAMMA),
            [_text(PROMPTS_MAIN[1])],
        )
        # A partially written record must not break listing or prompt counting.
        connection.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "msg_b05",
                SESSION_PLAIN,
                _ms(2026, 10, 27, 15, 31),
                _ms(2026, 10, 27, 15, 31),
                '{"role": "user", "agent":',
            ),
        )

        writer.session(
            SESSION_ARCHIVED,
            PROJECT_BETA,
            "Quota recovery notes",
            _ms(2026, 10, 21, 9, 30),
            _ms(2026, 10, 21, 10, 5),
            time_archived=_ms(2026, 10, 22, 8, 0),
        )
        writer.message(
            "msg_c01",
            SESSION_ARCHIVED,
            _ms(2026, 10, 21, 9, 30),
            _human("The archived-needle lives here.", PROJECT_BETA),
            [_text("The archived-needle lives here.")],
        )
        writer.message(
            "msg_c02",
            SESSION_ARCHIVED,
            _ms(2026, 10, 21, 10, 5),
            _assistant(PROJECT_BETA),
            [_text("Archived work.")],
        )

        writer.session(
            SESSION_CHILD,
            PROJECT_ALPHA,
            "Subagent child work",
            _ms(2026, 10, 26, 11, 0),
            _ms(2026, 10, 26, 12, 0),
            parent_id=SESSION_MAIN,
        )
        writer.message(
            "msg_d01",
            SESSION_CHILD,
            _ms(2026, 10, 26, 11, 0),
            _human("Subagent should not be listed.", PROJECT_ALPHA),
            [_text("Subagent should not be listed.")],
        )

        connection.execute(
            "INSERT INTO cag_session_extra (id, session_id, has_origin_session, "
            "origin_session_version, origin_session, extra_info, type, user, "
            "is_favorite, favorite_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                SESSION_MAIN,
                SESSION_MAIN,
                None,
                None,
                None,
                json.dumps({"tokenUsageDetail": {"total": 0}}),
                "kernel",
                "synthetic-user",
                0,
                None,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return home
