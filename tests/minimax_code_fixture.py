"""Build a synthetic MiniMax Code store for tests.

MiniMax Code keeps one ``messages.jsonl`` per dated session directory plus a
single ``runtime-state.sqlite`` that carries metadata, the full message
history, todo events, and archive state. Binary databases are generated at
runtime, never committed. All identifiers, paths, and prompts are synthetic.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SESSION_MAIN = "mvs_c0de4001-1111-4a1b-8c1d-111111111111"
SESSION_PLAIN = "mvs_c0de4002-2222-4b2c-9d2e-222222222222"
SESSION_ARCHIVED = "mvs_c0de4003-3333-4c3d-9e4f-333333333333"
SESSION_HIDDEN = "mvs_c0de4004-4444-4d4e-8f5a-444444444444"
SESSION_CHILD = "mvs_c0de4005-5555-4e5f-9a6b-555555555555"
SESSION_PEEK = "mvs_c0de4006-6666-4f6a-8b7c-666666666666"
SESSION_CRON = "mvs_c0de4007-7777-4a7b-9c8d-777777777777"
SESSION_EMPTY = "mvs_c0de4008-8888-4b8c-ad9e-888888888888"

DISPLAY_MAIN = SESSION_MAIN[len("mvs_") :]
DISPLAY_PLAIN = SESSION_PLAIN[len("mvs_") :]
DISPLAY_ARCHIVED = SESSION_ARCHIVED[len("mvs_") :]
DISPLAY_EMPTY = SESSION_EMPTY[len("mvs_") :]

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_BETA = "/Users/example/project-beta"
PROJECT_GAMMA = "/Users/example/project-gamma"
PROJECT_EMPTY = "/Users/example/project-empty"

TITLE_MAIN = "Refactor handoff parser for the CLI"
TITLE_PLAIN = "Investigate migration drift"
TITLE_EMPTY = "Empty synthetic session"

PROMPTS_MAIN = (
    "Please refactor the handoff parser so the CLI digest stays bounded.",
    "继续",
    "Also add a compaction fallback when the summary record is present.",
    "Run the parser tests and fix the two failures.",
    "别再改了，先记下欠账。",
)
PROMPT_PLAIN = "Investigate the migration drift in project gamma."
PROMPT_ARCHIVED = "The archived-needle lives here."
PROMPT_HIDDEN = "This hidden row must not appear."
PROMPT_CHILD = "Subagent should not be listed."
PROMPT_PEEK = "Peek session must not be listed."
PROMPT_CRON_SESSION = "Cron session must not be listed."
PROMPT_CRON_MESSAGE = "@worker scheduled follow-up; run the nightly task."
PROMPT_QUESTIONNAIRE = (
    "<questionnaire-response>\n"
    "  <answers><answer><stepId>scope</stepId></answer></answers>\n"
    "</questionnaire-response>"
)
COMPACT_SUMMARY_MAIN = (
    "Handoff parser work summarized. compaction-only-needle"
)
DEEP_NEEDLE = "deep-only-needle found in the transcript."

SESSIONS_SCHEMA = """
CREATE TABLE local_runtime_sessions (
    session_id TEXT PRIMARY KEY,
    record_json TEXT NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    columnar_version INTEGER NOT NULL DEFAULT 3,
    agent_name TEXT,
    runtime TEXT,
    session_type TEXT,
    status TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    visibility TEXT NOT NULL DEFAULT 'visible',
    session_kind TEXT NOT NULL DEFAULT 'conversation',
    purpose TEXT,
    purpose_kind TEXT NOT NULL DEFAULT '',
    origin_cron_id TEXT,
    parent_session_id TEXT,
    workspace_dir TEXT,
    project_workspace_dir TEXT,
    is_default_workspace INTEGER NOT NULL DEFAULT 0,
    title TEXT,
    created_at_ms INTEGER,
    error_message TEXT,
    error_code INTEGER,
    extra_data_json TEXT NOT NULL DEFAULT '{}',
    project_id INTEGER,
    history_relative_dir TEXT
);
CREATE TABLE local_runtime_message_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    msg_id TEXT NOT NULL,
    role TEXT,
    turn_id TEXT,
    created_at_ms INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    source TEXT,
    source_context_json TEXT,
    UNIQUE(session_id, msg_id)
);
CREATE INDEX idx_local_runtime_message_rows_session_id
    ON local_runtime_message_rows(session_id, id);
"""


def _ms(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> int:
    return int(
        datetime(
            year, month, day, hour, minute, second, tzinfo=timezone.utc
        ).timestamp()
        * 1000
    )


def _folder_suffix(raw_id: str) -> str:
    return base64.urlsafe_b64encode(raw_id.encode("utf-8")).decode("ascii").rstrip("=")


def _session_dir(
    home: Path,
    year: int,
    month: int,
    day: int,
    clock: str,
    raw_id: str,
) -> Path:
    folder = "%s-session_%s" % (clock, _folder_suffix(raw_id))
    return (
        home
        / "sessions"
        / ("%04d" % year)
        / ("%02d" % month)
        / ("%02d" % day)
        / folder
    )


def _write_manifest(
    directory: Path, raw_id: str, created_ms: int, updated_ms: Optional[int] = None
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    data = {
        "schemaVersion": 1,
        "sessionId": raw_id,
        "createdAtMs": created_ms,
        "updatedAtMs": created_ms if updated_ms is None else updated_ms,
        "source": "local-runtime",
        "layout": "v2-final-dated-session",
    }
    (directory / "manifest.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _jsonl_record(
    message_id: str, turn_id: str, message: Dict[str, Any]
) -> str:
    return json.dumps(
        {"message_id": message_id, "turn_id": turn_id, "message": message},
        ensure_ascii=False,
    )


def _user_message(
    prompt: str, timestamp_ms: int, reminder: str = "Use `tool_search` for tools."
) -> Dict[str, Any]:
    wrapper = "<system-reminder>\n%s\n</system-reminder>\n\n" % reminder
    text = wrapper + prompt
    return {
        "role": "user",
        "content": [{"type": "text", "text": text}],
        "canonicalTextRange": {
            "startOffset": len(wrapper),
            "endOffset": len(text),
        },
        "timestamp": timestamp_ms,
    }


def _assistant_message(
    blocks: List[Dict[str, Any]],
    timestamp_ms: int,
    model: str = "minimax/MiniMax-M3.1-Flash",
) -> Dict[str, Any]:
    return {
        "role": "assistant",
        "content": blocks,
        "api": "anthropic-messages",
        "provider": "minimax",
        "model": model,
        "stopReason": "toolUse",
        "responseId": "resp_synthetic",
        "timestamp": timestamp_ms,
        "usage": {},
    }


def _text_block(text: str) -> Dict[str, Any]:
    return {"type": "text", "text": text}


def _thinking_block(text: str) -> Dict[str, Any]:
    return {"type": "thinking", "thinking": text, "thinkingSignature": "sig"}


def _tool_block(name: str, arguments: Dict[str, Any], call_id: str) -> Dict[str, Any]:
    return {
        "type": "toolCall",
        "id": call_id,
        "name": name,
        "arguments": arguments,
    }


def _tool_result(name: str, call_id: str, timestamp_ms: int) -> Dict[str, Any]:
    return {
        "role": "toolResult",
        "toolName": name,
        "toolCallId": call_id,
        "content": [{"type": "text", "text": "ok"}],
        "details": {},
        "isError": False,
        "timestamp": timestamp_ms,
    }


def _write_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        _jsonl_record("msg_synthetic_%03d" % index, "turn_synthetic", record)
        for index, record in enumerate(records)
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _tool_call(
    name: str,
    call_id: str,
    arguments: Dict[str, Any],
    status: int = 2,
) -> Dict[str, Any]:
    return {
        "tool_name": name,
        "tool_call_id": call_id,
        "tool_call_status": status,
        "tool_call_args": json.dumps(arguments, ensure_ascii=False),
        "tool_call_result_data": json.dumps(
            {"content": [{"type": "text", "text": "ok"}]},
            ensure_ascii=False,
        ),
    }


class _Writer:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.sequence = 0

    def session(
        self,
        raw_id: str,
        relative: str,
        title: str,
        cwd: str,
        created: int,
        updated: int,
        *,
        kind: str = "conversation",
        archived: int = 0,
        visibility: str = "visible",
        parent_id: Optional[str] = None,
        model: str = "minimax/MiniMax-M3.1-Flash",
        error_message: Optional[str] = None,
        error_code: Optional[int] = None,
    ) -> None:
        record = {
            "agentName": "mavis",
            "archived": bool(archived),
            "createdAtMs": created,
            "runtime": "pi-agent",
            "sessionId": raw_id,
            "sessionType": "branch",
            "status": "started",
            "updatedAtMs": updated,
            "visibility": "hidden",
            "workspaceDir": cwd,
        }
        extra = {
            "appMode": "coding",
            "effectiveModel": model,
            "titleSource": "auto",
        }
        self.connection.execute(
            "INSERT INTO local_runtime_sessions ("
            "session_id, record_json, updated_at_ms, columnar_version, "
            "agent_name, runtime, session_type, status, archived, visibility, "
            "session_kind, parent_session_id, workspace_dir, "
            "project_workspace_dir, title, created_at_ms, error_message, "
            "error_code, extra_data_json, history_relative_dir"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                raw_id,
                json.dumps(record, ensure_ascii=False),
                updated,
                3,
                "mavis",
                "pi-agent",
                "branch",
                "started",
                archived,
                visibility,
                kind,
                parent_id,
                cwd,
                cwd,
                title,
                created,
                error_message,
                error_code,
                json.dumps(extra, ensure_ascii=False),
                relative,
            ),
        )

    def user(
        self,
        raw_id: str,
        text: str,
        when: int,
        source: str = "api",
    ) -> None:
        self.sequence += 1
        message = {
            "msg_id": "msg_user_%03d" % self.sequence,
            "msg_type": 1,
            "role": "user",
            "source": source,
            "msg_content": text,
            "timestamp": when,
            "turnId": "turn_%03d" % self.sequence,
        }
        self._insert(raw_id, "user", when, message, source)

    def assistant(
        self,
        raw_id: str,
        text: str,
        when: int,
        tools: Optional[List[Dict[str, Any]]] = None,
        *,
        msg_type: int = 2,
        thinking: str = "",
        finish_reason: str = "toolUse",
    ) -> None:
        self.sequence += 1
        message = {
            "msg_id": "msg_assistant_%03d" % self.sequence,
            "msg_type": msg_type,
            "role": "assistant",
            "source": "api",
            "msg_content": text,
            "thinking_content": thinking,
            "thinking_duration_ms": 25 if thinking else 0,
            "finish_reason": finish_reason,
            "tool_calls": tools or [],
            "timestamp": when,
            "turnId": "turn_%03d" % self.sequence,
        }
        self._insert(raw_id, "assistant", when, message, "api")

    def operation(self, raw_id: str, when: int) -> None:
        self.sequence += 1
        message = {
            "msg_id": "msg_operation_%03d" % self.sequence,
            "kind": "message_snapshot",
            "role": "assistant",
            "committedRevision": self.sequence,
            "operationId": "op_%03d" % self.sequence,
            "metadata": {},
            "timestamp": when,
            "turnId": "turn_%03d" % self.sequence,
        }
        self._insert(raw_id, "assistant", when, message, "api")

    def todo(
        self,
        raw_id: str,
        todos: List[Dict[str, str]],
        when: int,
    ) -> None:
        self.sequence += 1
        event = {"eventType": "todo_updated", "todos": todos}
        message = {
            "msg_id": "msg_todo_%03d" % self.sequence,
            "msg_type": 3,
            "msg_content": json.dumps(event, ensure_ascii=False),
            "source": "api",
            "timestamp": when,
            "turnId": "turn_%03d" % self.sequence,
        }
        self._insert(raw_id, None, when, message, "api")

    def _insert(
        self,
        raw_id: str,
        role: Optional[str],
        when: int,
        message: Dict[str, Any],
        source: str,
    ) -> None:
        self.connection.execute(
            "INSERT INTO local_runtime_message_rows "
            "(session_id, msg_id, role, turn_id, created_at_ms, data_json, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                raw_id,
                message["msg_id"],
                role,
                message.get("turnId"),
                when,
                json.dumps(message, ensure_ascii=False),
                source,
            ),
        )


def build_minimax_code_home(home: Path) -> Path:
    """Create a synthetic session tree plus ``sqlite/runtime-state.sqlite``."""

    home.mkdir(parents=True, exist_ok=True)
    sessions_root = home / "sessions"

    main_dir = _session_dir(
        home, 2026, 10, 27, "14-00-00-000", SESSION_MAIN
    )
    main_created = _ms(2026, 10, 27, 14, 0)
    _write_manifest(main_dir, SESSION_MAIN, main_created)
    _write_jsonl(
        main_dir / "messages.jsonl",
        [
            {
                "role": "compactionSummary",
                "summary": COMPACT_SUMMARY_MAIN,
                "tokensBefore": 1234,
                "timestamp": _ms(2026, 10, 27, 15, 20),
            },
            {
                "role": "custom",
                "customType": "session_identity_reminder",
                "display": False,
                "content": "<system-reminder>\nYOUR SESSION ID: %s\n"
                "</system-reminder>" % SESSION_MAIN,
                "timestamp": _ms(2026, 10, 27, 15, 20),
            },
            _assistant_message(
                [
                    _thinking_block("Resuming after compaction."),
                    _text_block("Resuming after compaction."),
                    _tool_block(
                        "read",
                        {"path": "/Users/example/project-alpha/src/handoff.ts"},
                        "call_read",
                    ),
                ],
                _ms(2026, 10, 27, 15, 21),
            ),
            _tool_result("read", "call_read", _ms(2026, 10, 27, 15, 22)),
            _user_message(PROMPTS_MAIN[3], _ms(2026, 10, 27, 15, 30)),
            _assistant_message(
                [
                    _text_block(DEEP_NEEDLE),
                    _tool_block(
                        "edit",
                        {
                            "file_path": "/Users/example/project-alpha/src/handoff.ts",
                            "old_string": "a",
                            "new_string": "b",
                        },
                        "call_edit",
                    ),
                ],
                _ms(2026, 10, 27, 15, 31),
            ),
            _tool_result("edit", "call_edit", _ms(2026, 10, 27, 15, 32)),
            _user_message(PROMPTS_MAIN[4], _ms(2026, 10, 27, 16, 0)),
            _assistant_message(
                [
                    _text_block("Recorded the remaining work."),
                    _tool_block(
                        "todowrite",
                        {
                            "todos": [
                                {"content": "Trim digest output", "status": "pending"}
                            ]
                        },
                        "call_todo",
                    ),
                ],
                _ms(2026, 10, 27, 16, 0, 30),
            ),
        ],
    )

    plain_dir = _session_dir(
        home, 2026, 10, 27, "15-00-00-000", SESSION_PLAIN
    )
    plain_created = _ms(2026, 10, 27, 15, 0)
    _write_manifest(plain_dir, SESSION_PLAIN, plain_created)
    _write_jsonl(
        plain_dir / "messages.jsonl",
        [
            _user_message(PROMPT_PLAIN, _ms(2026, 10, 27, 15, 0)),
            _assistant_message(
                [_text_block("Checking the migration ledger.")],
                _ms(2026, 10, 27, 15, 30),
            ),
        ],
    )

    archived_dir = _session_dir(
        home, 2026, 10, 21, "09-30-00-000", SESSION_ARCHIVED
    )
    archived_created = _ms(2026, 10, 21, 9, 30)
    _write_manifest(archived_dir, SESSION_ARCHIVED, archived_created)
    _write_jsonl(
        archived_dir / "messages.jsonl",
        [
            _user_message(PROMPT_ARCHIVED, _ms(2026, 10, 21, 9, 30)),
            _assistant_message(
                [_text_block("Archived work.")], _ms(2026, 10, 21, 10, 5)
            ),
        ],
    )

    hidden_dir = _session_dir(
        home, 2026, 10, 24, "10-00-00-000", SESSION_HIDDEN
    )
    hidden_created = _ms(2026, 10, 24, 10, 0)
    _write_manifest(hidden_dir, SESSION_HIDDEN, hidden_created)
    _write_jsonl(
        hidden_dir / "messages.jsonl",
        [
            _user_message(PROMPT_HIDDEN, hidden_created),
            _assistant_message(
                [_text_block("Hidden work.")], _ms(2026, 10, 24, 10, 5)
            ),
        ],
    )

    child_dir = _session_dir(
        home, 2026, 10, 26, "11-00-00-000", SESSION_CHILD
    )
    child_created = _ms(2026, 10, 26, 11, 0)
    _write_manifest(child_dir, SESSION_CHILD, child_created)
    _write_jsonl(
        child_dir / "messages.jsonl",
        [
            _user_message(PROMPT_CHILD, child_created),
            _assistant_message(
                [_text_block("Child work.")], _ms(2026, 10, 26, 11, 5)
            ),
        ],
    )

    peek_dir = _session_dir(
        home, 2026, 10, 23, "12-00-00-000", SESSION_PEEK
    )
    peek_created = _ms(2026, 10, 23, 12, 0)
    _write_manifest(peek_dir, SESSION_PEEK, peek_created)
    _write_jsonl(
        peek_dir / "messages.jsonl",
        [
            _user_message(PROMPT_PEEK, peek_created),
            _assistant_message(
                [_text_block("Peek work.")], _ms(2026, 10, 23, 12, 5)
            ),
        ],
    )

    cron_dir = _session_dir(
        home, 2026, 10, 22, "13-00-00-000", SESSION_CRON
    )
    cron_created = _ms(2026, 10, 22, 13, 0)
    _write_manifest(cron_dir, SESSION_CRON, cron_created)
    _write_jsonl(
        cron_dir / "messages.jsonl",
        [
            _user_message(PROMPT_CRON_SESSION, cron_created),
            _assistant_message(
                [_text_block("Cron work.")], _ms(2026, 10, 22, 13, 5)
            ),
        ],
    )

    empty_dir = _session_dir(
        home, 2026, 10, 22, "08-00-00-000", SESSION_EMPTY
    )
    empty_created = _ms(2026, 10, 22, 8, 0)
    _write_manifest(empty_dir, SESSION_EMPTY, empty_created)
    (empty_dir / "messages.jsonl").write_bytes(b"")

    db_path = home / "sqlite" / "runtime-state.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.executescript(SESSIONS_SCHEMA)
        writer = _Writer(connection)

        writer.session(
            SESSION_MAIN,
            str(main_dir.relative_to(sessions_root)),
            TITLE_MAIN,
            PROJECT_ALPHA,
            main_created,
            _ms(2026, 10, 27, 14, 15),
        )
        writer.user(SESSION_MAIN, PROMPTS_MAIN[0], _ms(2026, 10, 27, 14, 0))
        writer.assistant(
            SESSION_MAIN,
            "I'll start by reading the parser and its tests.",
            _ms(2026, 10, 27, 14, 1),
            [
                _tool_call(
                    "read", "call_read", {"path": "src/handoff.ts"}
                )
            ],
        )
        writer.todo(
            SESSION_MAIN,
            [
                {"content": "Refactor handoff parser", "status": "pending"},
                {
                    "content": "Document compaction fallback",
                    "status": "in_progress",
                },
            ],
            _ms(2026, 10, 27, 14, 2),
        )
        writer.user(SESSION_MAIN, PROMPTS_MAIN[1], _ms(2026, 10, 27, 14, 3))
        writer.assistant(
            SESSION_MAIN,
            "Editing the parser.",
            _ms(2026, 10, 27, 14, 4),
            [
                _tool_call(
                    "edit",
                    "call_edit_1",
                    {
                        "file_path": "src/handoff.ts",
                        "old_string": "a",
                        "new_string": "b",
                    },
                )
            ],
        )
        writer.user(
            SESSION_MAIN,
            PROMPT_CRON_MESSAGE,
            _ms(2026, 10, 27, 14, 5),
            source="cron",
        )
        writer.assistant(
            SESSION_MAIN,
            "Adding docs.",
            _ms(2026, 10, 27, 14, 6),
            [
                _tool_call(
                    "edit",
                    "call_edit_2",
                    {
                        "file_path": "/Users/example/project-alpha/src/handoff.ts",
                        "old_string": "c",
                        "new_string": "d",
                    },
                ),
                _tool_call(
                    "write",
                    "call_write",
                    {
                        "path": "docs/handoff.md",
                        "content": "synthetic",
                    },
                ),
            ],
        )
        writer.user(
            SESSION_MAIN,
            PROMPT_QUESTIONNAIRE,
            _ms(2026, 10, 27, 14, 7),
            source="questionnaire",
        )
        writer.user(SESSION_MAIN, PROMPTS_MAIN[2], _ms(2026, 10, 27, 14, 8))
        writer.assistant(
            SESSION_MAIN,
            "Running tests.",
            _ms(2026, 10, 27, 14, 9),
            [
                _tool_call(
                    "bash",
                    "call_bash_failed",
                    {
                        "command": "python3 -m unittest tests.test_handoff",
                        "description": "Run parser tests",
                    },
                    status=3,
                )
            ],
        )
        writer.todo(
            SESSION_MAIN,
            [
                {"content": "Refactor handoff parser", "status": "completed"},
                {
                    "content": "Document compaction fallback",
                    "status": "in_progress",
                },
                {"content": "Trim digest output", "status": "pending"},
            ],
            _ms(2026, 10, 27, 14, 10),
        )
        writer.operation(SESSION_MAIN, _ms(2026, 10, 27, 14, 11))
        writer.user(SESSION_MAIN, PROMPTS_MAIN[3], _ms(2026, 10, 27, 15, 30))
        writer.assistant(
            SESSION_MAIN,
            DEEP_NEEDLE,
            _ms(2026, 10, 27, 15, 31),
            [
                _tool_call(
                    "bash",
                    "call_bash_ok",
                    {"command": "git status --short"},
                )
            ],
        )
        writer.user(SESSION_MAIN, PROMPTS_MAIN[4], _ms(2026, 10, 27, 16, 0))
        writer.assistant(
            SESSION_MAIN,
            "Recorded the remaining work.",
            _ms(2026, 10, 27, 16, 0, 30),
            msg_type=1,
            finish_reason="stop",
        )

        writer.session(
            SESSION_PLAIN,
            str(plain_dir.relative_to(sessions_root)),
            TITLE_PLAIN,
            PROJECT_GAMMA,
            plain_created,
            _ms(2026, 10, 27, 15, 30),
            model="minimax/MiniMax-M2",
            error_message="exceed quota limit",
            error_code=429,
        )
        writer.user(SESSION_PLAIN, PROMPT_PLAIN, _ms(2026, 10, 27, 15, 0))
        writer.assistant(
            SESSION_PLAIN,
            "Checking the migration ledger.",
            _ms(2026, 10, 27, 15, 30),
            finish_reason="stop",
        )

        writer.session(
            SESSION_ARCHIVED,
            str(archived_dir.relative_to(sessions_root)),
            "Quota recovery notes",
            PROJECT_BETA,
            archived_created,
            _ms(2026, 10, 21, 10, 5),
            archived=1,
        )
        writer.user(
            SESSION_ARCHIVED, PROMPT_ARCHIVED, _ms(2026, 10, 21, 9, 30)
        )
        writer.assistant(
            SESSION_ARCHIVED,
            "Archived work.",
            _ms(2026, 10, 21, 10, 5),
            finish_reason="stop",
        )

        writer.session(
            SESSION_HIDDEN,
            str(hidden_dir.relative_to(sessions_root)),
            "Hidden scratch session",
            PROJECT_ALPHA,
            hidden_created,
            _ms(2026, 10, 24, 10, 5),
            visibility="hidden",
        )
        writer.user(SESSION_HIDDEN, PROMPT_HIDDEN, hidden_created)
        writer.assistant(
            SESSION_HIDDEN,
            "Hidden work.",
            _ms(2026, 10, 24, 10, 5),
            finish_reason="stop",
        )

        writer.session(
            SESSION_CHILD,
            str(child_dir.relative_to(sessions_root)),
            "Subagent child work",
            PROJECT_ALPHA,
            child_created,
            _ms(2026, 10, 26, 11, 5),
            kind="task",
            parent_id=SESSION_MAIN,
        )
        writer.user(SESSION_CHILD, PROMPT_CHILD, child_created)
        writer.assistant(
            SESSION_CHILD,
            "Child work.",
            _ms(2026, 10, 26, 11, 5),
            finish_reason="stop",
        )

        writer.session(
            SESSION_PEEK,
            str(peek_dir.relative_to(sessions_root)),
            "Peek session",
            PROJECT_ALPHA,
            peek_created,
            _ms(2026, 10, 23, 12, 5),
            kind="peek",
        )
        writer.user(SESSION_PEEK, PROMPT_PEEK, peek_created)
        writer.assistant(
            SESSION_PEEK,
            "Peek work.",
            _ms(2026, 10, 23, 12, 5),
            finish_reason="stop",
        )

        writer.session(
            SESSION_CRON,
            str(cron_dir.relative_to(sessions_root)),
            "Cron session",
            PROJECT_ALPHA,
            cron_created,
            _ms(2026, 10, 22, 13, 5),
            kind="cron",
        )
        writer.user(SESSION_CRON, PROMPT_CRON_SESSION, cron_created)
        writer.assistant(
            SESSION_CRON,
            "Cron work.",
            _ms(2026, 10, 22, 13, 5),
            finish_reason="stop",
        )

        writer.session(
            SESSION_EMPTY,
            str(empty_dir.relative_to(sessions_root)),
            TITLE_EMPTY,
            PROJECT_EMPTY,
            empty_created,
            empty_created,
        )

        connection.commit()
    finally:
        connection.close()
    return home
