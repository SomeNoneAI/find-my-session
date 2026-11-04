"""Build a synthetic OpenCode store for tests.

OpenCode keeps sessions as rows in one SQLite database, so the fixture is
generated at runtime instead of being committed as a binary file. Every
identifier, path, and prompt is invented. The database mirrors the 2.2.5
schema transition: ``session_v2`` is authoritative and one session exists
only there, while ``session`` holds an older mirror.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

SESSION_MAIN = "ses_0adc0001aaaa2222bbbb333333333333"
SESSION_PLAIN = "ses_0adc0002aaaa2222bbbb444444444444"
SESSION_ARCHIVED = "ses_0adc0003aaaa2222bbbb555555555555"
SESSION_CHILD = "ses_0adc0004aaaa2222bbbb666666666666"
SESSION_V2ONLY = "ses_0adc0005aaaa2222bbbb777777777777"
SESSION_NOTITLE = "ses_0adc0006aaaa2222bbbb888888888888"

DISPLAY_MAIN = SESSION_MAIN[len("ses_") :]
DISPLAY_PLAIN = SESSION_PLAIN[len("ses_") :]
DISPLAY_ARCHIVED = SESSION_ARCHIVED[len("ses_") :]
DISPLAY_V2ONLY = SESSION_V2ONLY[len("ses_") :]
DISPLAY_NOTITLE = SESSION_NOTITLE[len("ses_") :]

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_GAMMA = "/Users/example/project-gamma"

TITLE_MAIN = "Refactor the handoff digest"
TITLE_PLAIN = "Wire the fallback migration"
TITLE_V2ONLY = "Newest session lives in session_v2"

PROMPTS_MAIN = (
    "Please refactor the handoff digest so the CLI stays bounded.",
    "Continue with the tests.\nThen update the docs.",
    "Summarize the handoff digest limits for the README.",
)
PROMPT_PLAIN = "Check the fallback migration notes."
PROMPT_ARCHIVED = "Archived planning thread about the old parser."
PROMPT_V2ONLY = "Prompt that only session_v2 knows about."
PROMPT_NOTITLE = "Draft the migration notes for the digest."

COMPACT_SUMMARY = "Summary of the bounded digest work so far."
NEEDLE_DEEP_ONLY = "oc-deep-only-needle"
NEEDLE_SUBAGENT = "oc-subagent-needle"
NEEDLE_ARCHIVED = "oc-archived-needle"

MODEL_MAIN = "synthetic-oc-1"
VERSION_MAIN = "2.2.5"

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
    provider TEXT,
    binding TEXT,
    created_at INTEGER,
    last_used_at INTEGER
);
CREATE TABLE session_v2 (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    workspace_id TEXT,
    parent_id TEXT,
    fork_session_id TEXT,
    slug TEXT NOT NULL,
    directory TEXT NOT NULL,
    path TEXT,
    title TEXT NOT NULL,
    version TEXT NOT NULL,
    metadata TEXT,
    agent TEXT,
    model TEXT,
    time_created INTEGER NOT NULL,
    time_updated INTEGER NOT NULL,
    time_compacting INTEGER,
    time_archived INTEGER,
    cost REAL,
    tokens_input INTEGER,
    tokens_output INTEGER,
    tokens_reasoning INTEGER,
    tokens_cache_read INTEGER,
    tokens_cache_write INTEGER
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
    priority INTEGER,
    position INTEGER,
    time_created INTEGER NOT NULL,
    time_updated INTEGER NOT NULL
);
"""

_MESSAGE_SEQ = 0
_PART_SEQ = 0


def _ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp()
        * 1000
    )


def _next_message_id() -> str:
    global _MESSAGE_SEQ
    _MESSAGE_SEQ += 1
    return "msg_0adc%04xaaaa2222bbbb333333333333" % _MESSAGE_SEQ


def _next_part_id() -> str:
    global _PART_SEQ
    _PART_SEQ += 1
    return "prt_0adc%04xaaaa2222bbbb444444444444" % _PART_SEQ


def _human(agent: str = "build") -> Dict[str, Any]:
    return {
        "role": "user",
        "agent": agent,
        "model": {"id": MODEL_MAIN, "providerID": "synthetic"},
        "time": {"created": 0},
    }


def _assistant(
    model: str = MODEL_MAIN,
    agent: str = "build",
    summary: bool = False,
    error: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "role": "assistant",
        "agent": agent,
        "modelID": model,
        "providerID": "synthetic",
        "mode": "build",
        "summary": summary,
        "time": {"created": 0},
    }
    if error is not None:
        data["error"] = error
    return data


def _text(value: str) -> Dict[str, Any]:
    return {"type": "text", "text": value}


def _synthetic_text(value: str) -> Dict[str, Any]:
    return {"type": "text", "text": value, "synthetic": True, "time": {"created": 0}}


def _reasoning(value: str) -> Dict[str, Any]:
    return {"type": "reasoning", "text": value, "metadata": {}, "time": {"created": 0}}


def _tool(name: str, tool_input: Dict[str, Any], output: str = "") -> Dict[str, Any]:
    state: Dict[str, Any] = {"status": "completed", "input": tool_input}
    if output:
        state["output"] = output
    return {"type": "tool", "tool": name, "callID": "call_" + name, "state": state}


def _patch(files: Iterable[str]) -> Dict[str, Any]:
    return {"type": "patch", "hash": "0adc" * 16, "files": list(files)}


def _attachment(filename: str) -> Dict[str, Any]:
    return {
        "type": "file",
        "filename": filename,
        "mime": "text/plain",
        "url": "file:///Users/example/attachments/" + filename,
        "source": {},
    }


class _Writer:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def session(
        self,
        raw_id: str,
        directory: str,
        title: str,
        created: int,
        updated: int,
        *,
        parent_id: Optional[str] = None,
        model: Optional[str] = None,
        archived: Optional[int] = None,
        in_v1: bool = True,
        usage: Optional[Dict[str, float]] = None,
    ) -> None:
        slug = "synthetic-%s" % raw_id[-6:]
        usage = usage or {}
        self._connection.execute(
            "INSERT INTO session_v2 (id, project_id, workspace_id, parent_id, "
            "fork_session_id, slug, directory, path, title, version, metadata, "
            "agent, model, time_created, time_updated, time_compacting, "
            "time_archived, cost, tokens_input, tokens_output, "
            "tokens_reasoning, tokens_cache_read, tokens_cache_write) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                raw_id,
                "proj_synthetic",
                None,
                parent_id,
                None,
                slug,
                directory,
                None,
                title,
                VERSION_MAIN,
                None,
                "build",
                model,
                created,
                updated,
                None,
                archived,
                usage.get("cost"),
                usage.get("tokens_input"),
                usage.get("tokens_output"),
                usage.get("tokens_reasoning"),
                usage.get("tokens_cache_read"),
                usage.get("tokens_cache_write"),
            ),
        )
        if in_v1:
            self._connection.execute(
                "INSERT INTO session (id, project_id, parent_id, slug, directory, "
                "title, version, share_url, revert, permission, time_created, "
                "time_updated, time_compacting, time_archived, workspace_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    raw_id,
                    "proj_synthetic",
                    parent_id,
                    slug,
                    directory,
                    title,
                    VERSION_MAIN,
                    None,
                    None,
                    None,
                    created,
                    updated,
                    None,
                    archived,
                    None,
                ),
            )

    def message(
        self,
        session_id: str,
        created: int,
        data: Dict[str, Any],
        parts: Iterable[Dict[str, Any]],
        part_overrides: Optional[Dict[int, str]] = None,
    ) -> None:
        message_id = _next_message_id()
        self._connection.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data) "
            "VALUES (?,?,?,?,?)",
            (message_id, session_id, created, created, json.dumps(data)),
        )
        for index, part in enumerate(parts):
            raw = json.dumps(part)
            if part_overrides and index in part_overrides:
                raw = part_overrides[index]
            self._connection.execute(
                "INSERT INTO part (id, message_id, session_id, time_created, "
                "time_updated, data) VALUES (?,?,?,?,?,?)",
                (
                    _next_part_id(),
                    message_id,
                    session_id,
                    created,
                    created,
                    raw,
                ),
            )

    def todo(self, session_id: str, content: str, status: str, position: int) -> None:
        stamp = _ms(2026, 10, 1, 9)
        self._connection.execute(
            "INSERT INTO todo (session_id, content, status, priority, position, "
            "time_created, time_updated) VALUES (?,?,?,?,?,?,?)",
            (session_id, content, status, 1, position, stamp, stamp),
        )


def build_opencode_home(home: Path) -> Path:
    """Generate the synthetic store; returns the home directory."""
    home.mkdir(parents=True, exist_ok=True)
    db = home / "opencode.db"
    connection = sqlite3.connect(str(db))
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.executescript(SCHEMA)
        writer = _Writer(connection)
        connection.execute(
            "INSERT INTO project (id, worktree, vcs, name, time_created, "
            "time_updated) VALUES ('proj_synthetic', ?, 'git', 'synthetic', ?, ?)",
            (PROJECT_ALPHA, _ms(2026, 10, 1, 9), _ms(2026, 10, 1, 9)),
        )

        stamp = _ms(2026, 10, 20, 9)
        writer.session(
            SESSION_MAIN,
            PROJECT_ALPHA,
            TITLE_MAIN,
            stamp,
            _ms(2026, 10, 20, 10, 40),
            model=json.dumps({"id": MODEL_MAIN, "providerID": "synthetic"}),
            usage={
                "cost": 0.42,
                "tokens_input": 1500,
                "tokens_output": 800,
                "tokens_reasoning": 120,
                "tokens_cache_read": 200,
                "tokens_cache_write": 50,
            },
        )
        writer.message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 10),
            _human(PROMPTS_MAIN[0]),
            [
                _synthetic_text("<system-reminder>Context files follow.</system-reminder>"),
                _attachment("notes.txt"),
                _text(PROMPTS_MAIN[0]),
            ],
        )
        writer.message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 12),
            _assistant(),
            [
                _reasoning("Plan the bounded digest."),
                {"type": "step-start", "snapshot": None},
                _text("I'll read the parser first."),
                _tool(
                    "read",
                    {"filePath": PROJECT_ALPHA + "/src/handoff.py"},
                    output="parser module contents",
                ),
                _tool(
                    "bash",
                    {"command": "python3 -m unittest tests.test_handoff"},
                    output=NEEDLE_DEEP_ONLY,
                ),
                _patch([PROJECT_ALPHA + "/src/handoff.py"]),
                {"type": "step-finish", "cost": 0, "tokens": {}, "reason": "stop"},
            ],
        )
        writer.message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 30),
            _human(PROMPTS_MAIN[1]),
            [_text("Continue with the tests."), _text("Then update the docs.")],
        )
        writer.message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 31),
            _assistant(),
            [
                _text("Both are covered now."),
                _tool("edit", {"filePath": PROJECT_ALPHA + "/src/digest.py"}),
            ],
        )
        writer.message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 40),
            _human(agent="plan"),
            [_text("/agents ")],
        )
        writer.message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 41),
            _assistant(error={"data": {"message": "exceed quota limit"}}),
            [],
        )
        writer.message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 9, 50),
            _human(),
            [_text(PROMPTS_MAIN[2])],
        )
        writer.message(
            SESSION_MAIN,
            _ms(2026, 10, 20, 10, 0),
            _assistant(agent="compaction", summary=True),
            [_text(COMPACT_SUMMARY)],
        )
        writer.todo(SESSION_MAIN, "Refactor the digest parser", "completed", 0)
        writer.todo(SESSION_MAIN, "Add prompt paging", "in_progress", 1)
        writer.todo(SESSION_MAIN, "Update docs", "pending", 2)

        writer.session(
            SESSION_PLAIN,
            PROJECT_GAMMA,
            TITLE_PLAIN,
            _ms(2026, 10, 21, 10),
            _ms(2026, 10, 21, 10, 20),
        )
        writer.message(
            SESSION_PLAIN,
            _ms(2026, 10, 21, 10),
            _human(PROMPT_PLAIN),
            [_text(PROMPT_PLAIN)],
        )
        writer.message(
            SESSION_PLAIN,
            _ms(2026, 10, 21, 10, 10),
            _assistant(),
            [_text("Fallback migration is wired.")],
        )
        writer.message(
            SESSION_PLAIN,
            _ms(2026, 10, 21, 10, 15),
            _human(),
            [
                _text("Second prompt for the plain session."),
            ],
            part_overrides={0: '{"type":"text","text":"truncat'},
        )

        writer.session(
            SESSION_ARCHIVED,
            PROJECT_GAMMA,
            "Archived planning thread",
            _ms(2026, 10, 5, 8),
            _ms(2026, 10, 5, 8, 30),
            archived=_ms(2026, 10, 6, 8),
        )
        writer.message(
            SESSION_ARCHIVED,
            _ms(2026, 10, 5, 8),
            _human(PROMPT_ARCHIVED),
            [_text(PROMPT_ARCHIVED)],
        )
        writer.message(
            SESSION_ARCHIVED,
            _ms(2026, 10, 5, 8, 10),
            _assistant(),
            [_text("Old parser plan captured. " + NEEDLE_ARCHIVED)],
        )

        writer.session(
            SESSION_CHILD,
            PROJECT_ALPHA,
            "Explore the handoff module",
            _ms(2026, 10, 20, 9, 11),
            _ms(2026, 10, 20, 9, 13),
            parent_id=SESSION_MAIN,
        )
        writer.message(
            SESSION_CHILD,
            _ms(2026, 10, 20, 9, 11),
            _human(agent="explore"),
            [_text("Explore the parser entry points. " + NEEDLE_SUBAGENT)],
        )
        writer.message(
            SESSION_CHILD,
            _ms(2026, 10, 20, 9, 12),
            _assistant(agent="explore"),
            [_text("Entry points mapped.")],
        )

        writer.session(
            SESSION_V2ONLY,
            PROJECT_ALPHA,
            TITLE_V2ONLY,
            _ms(2026, 10, 27, 18),
            _ms(2026, 10, 27, 18, 5),
            model=json.dumps({"id": MODEL_MAIN, "providerID": "synthetic"}),
            in_v1=False,
            usage={"cost": 0.08, "tokens_input": 300, "tokens_output": 150},
        )
        writer.message(
            SESSION_V2ONLY,
            _ms(2026, 10, 27, 18),
            _human(PROMPT_V2ONLY),
            [_text(PROMPT_V2ONLY)],
        )

        writer.session(
            SESSION_NOTITLE,
            PROJECT_GAMMA,
            "",
            _ms(2026, 10, 22, 11),
            _ms(2026, 10, 22, 11, 10),
        )
        writer.message(
            SESSION_NOTITLE,
            _ms(2026, 10, 22, 11),
            _human(PROMPT_NOTITLE),
            [_text(PROMPT_NOTITLE)],
        )

        connection.commit()
    finally:
        connection.close()
    return home
