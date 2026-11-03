"""Build synthetic Antigravity stores for tests.

The desktop edition keeps ``conversations/<id>.db`` per session, metadata and
archive state in ``conversation_summaries.db``, and readable transcripts in
``brain/<id>/.system_generated/logs``. Migrated IDE sessions keep their
transcripts under the retired ``~/.gemini/antigravity-ide`` companion store.
The Antigravity CLI mirrors the same layout under its own home. Every
identifier, path, prompt, and title is invented.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SESSION_MAIN = "a17e5a01-1111-4a1b-8c1d-111111111111"
SESSION_ARCHIVED = "a17e5a02-2222-4b2c-9d2e-222222222222"
SESSION_NESTED = "a17e5a03-3333-4c3d-9e4f-333333333333"
SESSION_MIGRATED = "a17e5a04-4444-4d4e-8f5a-444444444444"
SESSION_ORPHAN = "a17e5a05-5555-4e5f-9a6b-555555555555"
SESSION_METADATA = "a17e5a06-6666-4f6a-8b7c-666666666666"
SESSION_DEEP = "a17e5a07-7777-4a7b-9c8d-777777777777"
SESSION_IDE_ONLY = "a17e5a08-8888-4b8c-8d9e-888888888888"
SESSION_ORPHAN_BRAIN = "a17e5a09-9999-4c9d-9eaf-999999999999"

CLI_SESSION_MAIN = "c11a2b01-1111-4a1b-8c1d-111111111111"
CLI_SESSION_FALLBACK = "c11a2b02-2222-4b2c-9d2e-222222222222"
CLI_SESSION_ORPHAN = "c11a2b03-3333-4c3d-9e4f-333333333333"
CLI_SESSION_METADATA = "c11a2b04-4444-4d4e-8f5a-444444444444"
CLI_SESSION_DEEP = "c11a2b05-5555-4e5f-9a6b-555555555555"
CLI_ORPHAN_BRAIN = "c11a2b99-9999-4c9d-9eaf-999999999999"

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_LEGACY = "/Users/example/project-legacy"
PROJECT_DEEP = "/Users/example/project-deep"
PROJECT_ARCHIVE = "/Users/example/project-archive"
PROJECT_CLI = "/Users/example/project-cli"

TITLE_MAIN = "Antigravity handoff digest"
TITLE_ARCHIVED = "Archived migration notes"
TITLE_MIGRATED = "Legacy IDE migration"
TITLE_METADATA = "Metadata only session"
TITLE_DEEP = "Deep search session"
TITLE_CLI_MAIN = "Command line rollout"
TITLE_CLI_METADATA = "CLI metadata session"

PROMPTS_MAIN = (
    "Please refactor the Antigravity digest so the CLI stays bounded. "
    "antigravity-main-needle",
    "继续",
    "Tighten the digest tests.",
    "Please summarize the handoff digest and keep the output short enough "
    "for the CLI.",
)
PROMPT_ARCHIVED = "Archive the migration notes."
PROMPT_MIGRATED = "Review the legacy IDE migration."
PROMPT_NESTED = "Nested worker task. antigravity-nested-needle."
PROMPT_DEEP = "Locate the deep Antigravity marker."
PROMPT_SYSTEM = (
    "<USER_REQUEST>Synthetic system reminder that must not count. "
    "antigravity-hidden-needle</USER_REQUEST>"
)
PROMPT_SUBAGENT = "Subagent scratch prompt. antigravity-subagent-needle."
PROMPT_SHORT = "short-transcript-only-prompt"
PROMPT_IDE_ONLY = "IDE-only conversation that must not be listed."

CLI_PROMPTS = (
    "Plan the command line rollout. cli-main-needle",
    "继续",
    "Verify the rollout checklist.",
)
CLI_PROMPT_FALLBACK = "Trace the scheduler retry loop."
CLI_PROMPT_DEEP = "Review the CLI deep marker."

NEEDLE_MAIN = "antigravity-main-needle"
NEEDLE_TOOL_OUTPUT = "antigravity-tool-output-needle"
NEEDLE_ARCHIVED = "antigravity-archived-needle"
NEEDLE_NESTED = "antigravity-nested-needle"
NEEDLE_MIGRATED = "antigravity-migrated-needle"
NEEDLE_DEEP = "antigravity-deep-only-needle"
NEEDLE_DB_ONLY = "antigravity-db-only-needle"
NEEDLE_DB_DECOY = "antigravity-db-decoy-needle"
NEEDLE_SUBAGENT = "antigravity-subagent-needle"
NEEDLE_ORPHAN_BRAIN = "antigravity-orphan-brain-needle"
NEEDLE_IDE_ONLY = "antigravity-ide-only-needle"

CLI_NEEDLE_MAIN = "cli-main-needle"
CLI_NEEDLE_DEEP = "cli-deep-only-needle"
CLI_NEEDLE_DB_ONLY = "cli-db-only-needle"
CLI_NEEDLE_HISTORY = "cli-history-decoy-needle"
CLI_NEEDLE_PROTO = "cli-proto-decoy-needle"
CLI_PROMPT_SHORT = "short-transcript-decoy-needle"


def _utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _stamp(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0
) -> str:
    # The store writes ``YYYY-MM-DD HH:MM:SS+00:00`` timestamps.
    return _utc(year, month, day, hour, minute).strftime(
        "%Y-%m-%d %H:%M:%S+00:00"
    )


def _user(
    text: str,
    stamp: str,
    *,
    source: str = "USER_EXPLICIT",
    extra: str = "",
) -> Dict[str, Any]:
    content = "<USER_REQUEST>%s</USER_REQUEST>\n%s" % (text, extra)
    return {
        "type": "USER_INPUT",
        "source": source,
        "created_at": stamp,
        "content": content,
    }


def _planner(
    content: str,
    stamp: str,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "type": "PLANNER_RESPONSE",
        "source": "MODEL",
        "created_at": stamp,
        "content": content,
        "thinking": "",
    }
    if tool_calls:
        record["tool_calls"] = tool_calls
    return record


def _tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return {"name": name, "args": arguments}


def _generic(content: str, stamp: str) -> Dict[str, Any]:
    return {"type": "GENERIC", "created_at": stamp, "content": content}


def _checkpoint(content: str, stamp: str) -> Dict[str, Any]:
    return {"type": "CHECKPOINT", "created_at": stamp, "content": content}


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _transcript(
    home: Path, session_id: str, records: Iterable[Dict[str, Any]]
) -> Path:
    path = (
        home
        / "brain"
        / session_id
        / ".system_generated"
        / "logs"
        / "transcript_full.jsonl"
    )
    _write_jsonl(path, records)
    return path


def _conversation_db(path: Path, raw: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.execute(
            "CREATE TABLE steps ("
            "idx INTEGER PRIMARY KEY, "
            "step_format INTEGER NOT NULL DEFAULT 0, "
            "step_payload BLOB)"
        )
        connection.execute(
            "CREATE TABLE trajectory_meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        connection.execute(
            "INSERT INTO steps (idx, step_format, step_payload) VALUES (0, 0, ?)",
            (raw,),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _summary_db(path: Path, rows: List[Dict[str, Any]], fts_rows: List[Dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.execute(
            "CREATE TABLE conversation_summaries ("
            "conversation_id TEXT PRIMARY KEY, "
            "title TEXT, "
            "preview TEXT, "
            "step_count INTEGER, "
            "last_modified_time TEXT, "
            "workspace_uris TEXT, "
            "status TEXT, "
            "source TEXT, "
            "project_id TEXT, "
            "agent_name TEXT, "
            "parent_conversation_id TEXT, "
            "nesting_depth INTEGER DEFAULT 0, "
            "battle_id TEXT, "
            "winning_conversation_id TEXT, "
            "not_fully_idle INTEGER DEFAULT 0, "
            "killed INTEGER DEFAULT 0, "
            "last_user_input_time TEXT, "
            "last_user_input_step_index INTEGER, "
            "app_data_dir TEXT, "
            "raw_summary TEXT, "
            "group_id TEXT)"
        )
        columns = [
            "conversation_id",
            "title",
            "preview",
            "step_count",
            "last_modified_time",
            "workspace_uris",
            "status",
            "source",
            "project_id",
            "agent_name",
            "parent_conversation_id",
            "nesting_depth",
        ]
        connection.executemany(
            "INSERT INTO conversation_summaries (%s) VALUES (%s)"
            % (", ".join(columns), ", ".join("?" for _ in columns)),
            [tuple(row.get(column) for column in columns) for row in rows],
        )
        if fts_rows:
            _create_fts(connection)
            fts_columns = [
                "conversation_id",
                "chunk_index",
                "chunk_first_step",
                "chunk_last_step",
                "last_modified_time",
                "step_count",
                "last_step_created_at",
                "archived",
                "user_step_byte_offsets",
                "agent_step_byte_offsets",
                "title",
                "workspace",
                "project",
                "user_body",
                "agent_body",
            ]
            connection.executemany(
                "INSERT INTO conversations_fts (%s) VALUES (%s)"
                % (", ".join(fts_columns), ", ".join("?" for _ in fts_columns)),
                [tuple(row.get(column) for column in fts_columns) for row in fts_rows],
            )
        connection.commit()
    finally:
        connection.close()
    return path


def _create_fts(connection: sqlite3.Connection) -> None:
    columns = (
        "conversation_id UNINDEXED, "
        "chunk_index UNINDEXED, "
        "chunk_first_step UNINDEXED, "
        "chunk_last_step UNINDEXED, "
        "last_modified_time UNINDEXED, "
        "step_count UNINDEXED, "
        "last_step_created_at UNINDEXED, "
        "archived UNINDEXED, "
        "user_step_byte_offsets UNINDEXED, "
        "agent_step_byte_offsets UNINDEXED, "
        "title, "
        "workspace, "
        "project, "
        "user_body, "
        "agent_body"
    )
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE conversations_fts USING fts5("
            "%s, tokenize = 'unicode61 remove_diacritics 2', "
            "prefix = '1 2 3')" % columns
        )
    except sqlite3.OperationalError:
        connection.execute(
            "CREATE TABLE conversations_fts (%s)" % columns.replace(" UNINDEXED", "")
        )


def _row(
    session_id: str,
    title: str,
    updated: str,
    *,
    cwd: str = "",
    project_id: str = "synthetic-project",
    nesting_depth: int = 0,
    parent: str = "",
    agent_name: str = "",
) -> Dict[str, Any]:
    return {
        "conversation_id": session_id,
        "title": title,
        "preview": title,
        "step_count": 12,
        "last_modified_time": updated,
        "workspace_uris": json.dumps(["file://" + cwd]) if cwd else "[]",
        "status": "idle",
        "source": "desktop",
        "project_id": project_id,
        "agent_name": agent_name,
        "parent_conversation_id": parent,
        "nesting_depth": nesting_depth,
    }


def _fts_row(
    session_id: str,
    title: str,
    updated: str,
    *,
    chunk: int = 0,
    archived: int = 0,
    cwd: str = "",
) -> Dict[str, Any]:
    return {
        "conversation_id": session_id,
        "chunk_index": chunk,
        "chunk_first_step": 0,
        "chunk_last_step": 12,
        "last_modified_time": updated,
        "step_count": 12,
        "last_step_created_at": updated,
        "archived": str(archived),
        "user_step_byte_offsets": "",
        "agent_step_byte_offsets": "",
        "title": title,
        "workspace": cwd,
        "project": "",
        "user_body": "",
        "agent_body": "",
    }


def _main_records() -> List[Dict[str, Any]]:
    return [
        _user(PROMPTS_MAIN[0], _stamp(2026, 9, 1, 10, 5)),
        _planner(
            "I'll inspect the handoff module first.",
            _stamp(2026, 9, 1, 10, 6),
            [
                _tool(
                    "view_file",
                    {
                        "AbsolutePath": PROJECT_ALPHA + "/src/handoff.py",
                        "toolSummary": "Viewed the handoff module",
                    },
                )
            ],
        ),
        _generic(
            "Step output: %s" % NEEDLE_TOOL_OUTPUT,
            _stamp(2026, 9, 1, 10, 7),
        ),
        _planner(
            "",
            _stamp(2026, 9, 1, 10, 8),
            [
                _tool(
                    "write_to_file",
                    {
                        "TargetFile": PROJECT_ALPHA + "/src/handoff.py",
                        "toolSummary": "Wrote the handoff module",
                    },
                ),
                _tool(
                    "replace_file_content",
                    {
                        "TargetFile": PROJECT_ALPHA + "/src/handoff.py",
                        "toolSummary": "Updated the digest limit",
                    },
                ),
            ],
        ),
        _user(PROMPTS_MAIN[1], _stamp(2026, 9, 1, 10, 12)),
        _planner(
            "继续完善摘要。",
            _stamp(2026, 9, 1, 10, 13),
            [
                _tool(
                    "run_command",
                    {
                        "CommandLine": "python3 -m unittest",
                        "toolSummary": "Ran the unit tests",
                    },
                )
            ],
        ),
        _user(
            PROMPTS_MAIN[2],
            _stamp(2026, 9, 1, 10, 20),
            extra="<ADDITIONAL_METADATA>Opened src/handoff.py."
            "</ADDITIONAL_METADATA>\n",
        ),
        _planner(
            "Adding regression coverage.",
            _stamp(2026, 9, 1, 10, 21),
            [
                _tool(
                    "write_file",
                    {
                        "Path": PROJECT_ALPHA + "/docs/handoff.md",
                        "toolSummary": "Wrote the handoff notes",
                    },
                )
            ],
        ),
        _user(
            PROMPTS_MAIN[3],
            _stamp(2026, 9, 1, 10, 40),
            extra="<USER_SETTINGS_CHANGE>{\"theme\": \"dark\"}"
            "</USER_SETTINGS_CHANGE>\n",
        ),
        _planner(
            "The digest is bounded and ready.",
            _stamp(2026, 9, 1, 10, 41),
            [
                _tool(
                    "edit_file",
                    {
                        "Path": "src/digest.py",
                        "toolSummary": "Tightened the digest tests",
                    },
                ),
                _tool(
                    "grep_search",
                    {
                        "Query": "handoff digest",
                        "toolSummary": "Searched the digest references",
                    },
                ),
                _tool(
                    "view_file",
                    {
                        "AbsolutePath": PROJECT_ALPHA + "/docs/handoff.md",
                        "toolSummary": "Viewed the handoff notes",
                    },
                ),
            ],
        ),
        _checkpoint(
            "## Plan\n"
            "- [x] Refactor the digest\n"
            "- [ ] Add prompt paging\n"
            "- [ ] Update docs\n",
            _stamp(2026, 9, 1, 10, 44),
        ),
        _user(
            PROMPT_SYSTEM,
            _stamp(2026, 9, 1, 10, 44),
            source="SYSTEM",
        ),
        {
            "type": "ERROR_MESSAGE",
            "created_at": _stamp(2026, 9, 1, 10, 44),
            "content": "Synthetic warning that must not count.",
        },
    ]


def _archived_records() -> List[Dict[str, Any]]:
    return [
        _user(PROMPT_ARCHIVED, _stamp(2026, 8, 20, 8, 55)),
        _planner(
            "Archived the migration notes. %s" % NEEDLE_ARCHIVED,
            _stamp(2026, 8, 20, 9, 0),
        ),
    ]


def _nested_records() -> List[Dict[str, Any]]:
    return [
        _user(PROMPT_NESTED, _stamp(2026, 9, 2, 7, 55)),
        _planner("Worker done.", _stamp(2026, 9, 2, 8, 0)),
    ]


def _migrated_records() -> List[Dict[str, Any]]:
    return [
        _user(PROMPT_MIGRATED, _stamp(2026, 8, 28, 11, 55)),
        _planner(
            "The migration is complete. %s" % NEEDLE_MIGRATED,
            _stamp(2026, 8, 28, 12, 0),
        ),
    ]


def _deep_records() -> List[Dict[str, Any]]:
    return [
        _user(PROMPT_DEEP, _stamp(2026, 8, 25, 10, 55)),
        _planner("Checking markers.", _stamp(2026, 8, 25, 10, 56)),
        _generic(
            "Search index cache: %s" % NEEDLE_DEEP,
            _stamp(2026, 8, 25, 11, 0),
        ),
    ]


def _cli_main_records() -> List[Dict[str, Any]]:
    return [
        _user(CLI_PROMPTS[0], _stamp(2026, 9, 3, 8, 55)),
        _planner(
            "Planning the rollout.",
            _stamp(2026, 9, 3, 8, 56),
            [
                _tool(
                    "run_command",
                    {
                        "CommandLine": "agy --version",
                        "toolSummary": "Checked the CLI version",
                    },
                )
            ],
        ),
        _user(CLI_PROMPTS[1], _stamp(2026, 9, 3, 9, 0)),
        _planner("继续执行。", _stamp(2026, 9, 3, 9, 1)),
        _user(CLI_PROMPTS[2], _stamp(2026, 9, 3, 9, 5)),
        _planner(
            "Checklist verified.",
            _stamp(2026, 9, 3, 9, 6),
            [
                _tool(
                    "write_to_file",
                    {
                        "TargetFile": PROJECT_CLI + "/docs/rollout.md",
                        "toolSummary": "Wrote the rollout checklist",
                    },
                )
            ],
        ),
        _generic(
            "Rollout trace: %s" % CLI_NEEDLE_DEEP,
            _stamp(2026, 9, 3, 9, 9),
        ),
    ]


def build_antigravity_home(home: Path) -> Path:
    """Create a synthetic ``~/.gemini/antigravity`` desktop store."""

    home.mkdir(parents=True, exist_ok=True)
    summaries = [
        _row(
            SESSION_MAIN,
            TITLE_MAIN,
            _stamp(2026, 9, 1, 10, 45),
            cwd=PROJECT_ALPHA,
        ),
        _row(
            SESSION_ARCHIVED,
            TITLE_ARCHIVED,
            _stamp(2026, 8, 20, 9, 0),
            cwd=PROJECT_LEGACY,
        ),
        _row(
            SESSION_NESTED,
            "Teamwork worker",
            _stamp(2026, 9, 2, 8, 0),
            cwd=PROJECT_ALPHA,
            nesting_depth=1,
            parent=SESSION_MAIN,
            agent_name="teamwork_preview_worker",
        ),
        _row(
            SESSION_MIGRATED,
            TITLE_MIGRATED,
            _stamp(2026, 8, 28, 12, 0),
            cwd=PROJECT_LEGACY,
            project_id="",
        ),
        _row(
            SESSION_ORPHAN,
            "Orphan summary session",
            _stamp(2026, 9, 5, 9, 0),
            cwd=PROJECT_ALPHA,
        ),
        _row(
            SESSION_METADATA,
            TITLE_METADATA,
            _stamp(2026, 8, 15, 7, 0),
            cwd=PROJECT_ARCHIVE,
        ),
        _row(
            SESSION_DEEP,
            TITLE_DEEP,
            _stamp(2026, 8, 25, 11, 0),
            cwd=PROJECT_DEEP,
        ),
        # The desktop summaries database also indexes CLI conversations, but
        # only rows with a desktop conversation database are listed.
        _row(
            CLI_SESSION_MAIN,
            TITLE_CLI_MAIN,
            _stamp(2026, 9, 3, 9, 10),
            cwd=PROJECT_CLI,
        ),
    ]
    fts_rows = [
        _fts_row(
            SESSION_MAIN,
            TITLE_MAIN,
            _stamp(2026, 9, 1, 10, 45),
            cwd=PROJECT_ALPHA,
        ),
        _fts_row(
            SESSION_ARCHIVED,
            TITLE_ARCHIVED,
            _stamp(2026, 8, 20, 9, 0),
            chunk=0,
            cwd=PROJECT_LEGACY,
        ),
        _fts_row(
            SESSION_ARCHIVED,
            TITLE_ARCHIVED,
            _stamp(2026, 8, 20, 9, 0),
            chunk=1,
            archived=1,
            cwd=PROJECT_LEGACY,
        ),
        _fts_row(
            SESSION_NESTED,
            "Teamwork worker",
            _stamp(2026, 9, 2, 8, 0),
            cwd=PROJECT_ALPHA,
        ),
        _fts_row(
            SESSION_MIGRATED,
            TITLE_MIGRATED,
            _stamp(2026, 8, 28, 12, 0),
            cwd=PROJECT_LEGACY,
        ),
        _fts_row(
            SESSION_METADATA,
            TITLE_METADATA,
            _stamp(2026, 8, 15, 7, 0),
            cwd=PROJECT_ARCHIVE,
        ),
        _fts_row(
            SESSION_DEEP,
            TITLE_DEEP,
            _stamp(2026, 8, 25, 11, 0),
            cwd=PROJECT_DEEP,
        ),
    ]
    _summary_db(home / "conversation_summaries.db", summaries, fts_rows)

    conversations = home / "conversations"
    _conversation_db(
        conversations / (SESSION_MAIN + ".db"),
        ("steps containing %s" % NEEDLE_DB_DECOY).encode("utf-8"),
    )
    for session_id in (
        SESSION_ARCHIVED,
        SESSION_NESTED,
        SESSION_MIGRATED,
        SESSION_DEEP,
    ):
        _conversation_db(
            conversations / (session_id + ".db"),
            ("synthetic conversation %s" % session_id).encode("utf-8"),
        )
    _conversation_db(
        conversations / (SESSION_METADATA + ".db"),
        ("metadata fallback %s" % NEEDLE_DB_ONLY).encode("utf-8"),
    )

    _transcript(home, SESSION_MAIN, _main_records())
    _transcript(home, SESSION_ARCHIVED, _archived_records())
    _transcript(home, SESSION_NESTED, _nested_records())
    _transcript(home, SESSION_DEEP, _deep_records())

    logs = home / "brain" / SESSION_MAIN / ".system_generated" / "logs"
    _write_jsonl(logs / "transcript.jsonl", [_user(PROMPT_SHORT, _stamp(2026, 9, 1, 11, 0))])
    _write_jsonl(
        logs / "subagent_transcript.jsonl",
        [
            _user(PROMPT_SUBAGENT, _stamp(2026, 9, 1, 10, 30)),
            _planner("Subagent output.", _stamp(2026, 9, 1, 10, 31)),
        ],
    )

    _transcript(
        home,
        SESSION_ORPHAN_BRAIN,
        [
            _user(
                "Orphan brain conversation. %s" % NEEDLE_ORPHAN_BRAIN,
                _stamp(2026, 9, 4, 9, 0),
            )
        ],
    )
    return home


def build_antigravity_ide_home(home: Path) -> Path:
    """Create the retired IDE companion store with transcripts only."""

    home.mkdir(parents=True, exist_ok=True)
    _transcript(home, SESSION_MIGRATED, _migrated_records())
    _transcript(
        home,
        SESSION_IDE_ONLY,
        [
            _user(PROMPT_IDE_ONLY, _stamp(2026, 9, 6, 9, 0)),
            _planner("IDE-only output.", _stamp(2026, 9, 6, 9, 1)),
        ],
    )
    _conversation_db(
        home / "conversations" / (SESSION_IDE_ONLY + ".db"),
        ("IDE-only conversation %s" % NEEDLE_IDE_ONLY).encode("utf-8"),
    )
    return home


def build_antigravity_cli_home(home: Path) -> Path:
    """Create a synthetic ``~/.gemini/antigravity-cli`` store."""

    home.mkdir(parents=True, exist_ok=True)
    summaries = [
        _row(
            CLI_SESSION_MAIN,
            TITLE_CLI_MAIN,
            _stamp(2026, 9, 3, 9, 10),
            cwd=PROJECT_CLI,
        ),
        _row(
            CLI_SESSION_FALLBACK,
            "",
            _stamp(2026, 9, 2, 9, 0),
            cwd=PROJECT_CLI,
        ),
        _row(
            CLI_SESSION_ORPHAN,
            "CLI orphan summary",
            _stamp(2026, 9, 4, 9, 0),
            cwd=PROJECT_CLI,
        ),
        _row(
            CLI_SESSION_METADATA,
            TITLE_CLI_METADATA,
            _stamp(2026, 8, 29, 9, 0),
            cwd=PROJECT_CLI,
        ),
        _row(
            CLI_SESSION_DEEP,
            "CLI deep session",
            _stamp(2026, 8, 30, 9, 0),
            cwd=PROJECT_CLI,
        ),
    ]
    _summary_db(home / "conversation_summaries.db", summaries, [])

    conversations = home / "conversations"
    for session_id in (
        CLI_SESSION_MAIN,
        CLI_SESSION_FALLBACK,
        CLI_SESSION_DEEP,
    ):
        _conversation_db(
            conversations / (session_id + ".db"),
            ("synthetic CLI conversation %s" % session_id).encode("utf-8"),
        )
    _conversation_db(
        conversations / (CLI_SESSION_METADATA + ".db"),
        ("CLI fallback %s" % CLI_NEEDLE_DB_ONLY).encode("utf-8"),
    )

    _transcript(home, CLI_SESSION_MAIN, _cli_main_records())
    _transcript(
        home,
        CLI_SESSION_FALLBACK,
        [
            _user(CLI_PROMPT_FALLBACK, _stamp(2026, 9, 2, 8, 55)),
            _planner("Retry loop traced.", _stamp(2026, 9, 2, 9, 0)),
        ],
    )
    _transcript(
        home,
        CLI_SESSION_DEEP,
        [
            _user(CLI_PROMPT_DEEP, _stamp(2026, 8, 30, 8, 55)),
            _planner("Deep marker found.", _stamp(2026, 8, 30, 9, 0)),
        ],
    )

    logs = home / "brain" / CLI_SESSION_MAIN / ".system_generated" / "logs"
    _write_jsonl(
        logs / "transcript.jsonl",
        [_user(CLI_PROMPT_SHORT, _stamp(2026, 9, 3, 9, 7))],
    )

    _transcript(
        home,
        CLI_ORPHAN_BRAIN,
        [
            _user(
                "CLI orphan brain conversation.",
                _stamp(2026, 9, 4, 10, 0),
            )
        ],
    )
    (home / "history.jsonl").write_text(
        json.dumps(
            {"session": CLI_ORPHAN_BRAIN, "note": CLI_NEEDLE_HISTORY},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (home / "jetbox_summaries_proto.pb").write_bytes(
        ("synthetic proto %s" % CLI_NEEDLE_PROTO).encode("utf-8")
    )
    return home
