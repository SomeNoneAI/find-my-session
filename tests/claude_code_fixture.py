"""Build a synthetic Claude Code store for tests.

The layout mirrors ``~/.claude``: one JSONL transcript per session under
``projects/<encoded-cwd>/<session-uuid>.jsonl``, nested subagent transcripts
under ``projects/<encoded-cwd>/<session-uuid>/subagents/``, per-project
``sessions-index.json`` files, a global ``history.jsonl`` prompt history, and a
per-session todo directory. Every identifier, path, and prompt is invented.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any, Dict, Iterable, List

SESSION_MAIN = "c1a0de01-1111-4a1b-8c1d-111111111111"
SESSION_AUX = "c1a0de02-2222-4b2c-9d2e-222222222222"
SESSION_PLAIN = "c1a0de03-3333-4c3d-9e4f-333333333333"
SESSION_COMPACT = "c1a0de04-4444-4d4e-8f5a-444444444444"
SESSION_STALE = "c1a0de06-6666-4f6a-8b7c-666666666666"
SUBAGENT_ID = "c1a0de05-5555-4e5f-9a6b-555555555555"

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_AUX = "/Users/example/project-aux"
PROJECT_GAMMA = "/Users/example/project-gamma"
PROJECT_BETA = "/Users/example/project-beta"

SLUG_ALPHA = "-Users-example-project-alpha"
SLUG_AUX = "-Users-example-project-aux"
SLUG_GAMMA = "-Users-example-project-gamma"
SLUG_BETA = "-Users-example-project-beta"

TITLE_MAIN = "Refactor the handoff digest for the CLI"
STALE_TITLE = "Stale index entry that must not become a title"

COMPACT_SUMMARY = (
    "Summary of the conversation so far:\n"
    "The conversation is between an AI agent and a user.\n"
    "A previous turn asked to bound the handoff digest."
)
COMPACT_SESSION_SUMMARY = "The conversation summary for continuation."
COMPACT_SESSION_EARLY = "An earlier compact summary that the user message replaces."

PROMPTS_MAIN = (
    "Please refactor the handoff digest so the CLI stays bounded. claude-main-needle",
    "继续",
    "Ship the compact summary fallback.",
    "Tighten the digest tests.",
    "[Image #1] Inspect the preview screenshot.",
    "Check the preview layout.",
)
PROMPTS_AUX = (
    "Draft the migration notes.",
    "继续",
)
PROMPT_PLAIN = "Investigate the migration drift in project gamma."
PROMPT_COMPACT_EARLY = "Plan the migration."
PROMPT_COMPACT_RESUME = "Continue after compaction."
PROMPT_SUBAGENT = "Subagent scratch work. claude-subagent-needle."
PROMPT_DECOY = "Decoy transcript that must never be listed. claude-decoy-needle."

NEEDLE_TOOL_OUTPUT = "claude-tool-output-needle"
NEEDLE_DEEP_ONLY = "claude-deep-only-needle"
NEEDLE_SUBAGENT = "claude-subagent-needle"
NEEDLE_DECOY = "claude-decoy-needle"
NEEDLE_MAIN = "claude-main-needle"

SIDE_CHAIN_PROMPT = "sidechain prompt must not count"
HISTORY_PROMPT = "Legacy history entry that must never be listed."
LOCAL_COMMAND_TEXT = "Caveat: local command output must not become a prompt."
TASK_NOTIFICATION_TEXT = (
    "<task-notification>\n<task-id>AB12CD</task-id>\n"
    "<status>completed</status>\n</task-notification>"
)
INTERRUPT_TEXT = "[Request interrupted by user for tool use]"

MODEL_MAIN = "synthetic-claude-1"
MODEL_AUX = "synthetic-claude-2"
VERSION_MAIN = "0.0.1-synthetic"
VERSION_AUX = "0.0.3-synthetic"
VERSION_PLAIN = "0.0.2-synthetic"
VERSION_COMPACT = "0.0.4-synthetic"


def _ts(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> str:
    return (
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S.000Z")
    )


def _text_block(text: str) -> Dict[str, Any]:
    return {"type": "text", "text": text}


def _tool_use(name: str, arguments: Dict[str, Any], block_id: str) -> Dict[str, Any]:
    return {
        "type": "tool_use",
        "id": block_id,
        "name": name,
        "input": arguments,
    }


def _user(
    session_id: str,
    timestamp: str,
    content: Any,
    cwd: str,
    version: str,
    branch: str,
    uuid: str,
    entrypoint: str = "cli",
    is_meta: bool = False,
    is_sidechain: bool = False,
    is_compact_summary: bool = False,
    tool_use_result: Any = None,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "parentUuid": None,
        "isSidechain": is_sidechain,
        "userType": "external",
        "cwd": cwd,
        "sessionId": session_id,
        "version": version,
        "gitBranch": branch,
        "type": "user",
        "uuid": uuid,
        "timestamp": timestamp,
        "entrypoint": entrypoint,
        "message": {"role": "user", "content": content},
    }
    if is_meta:
        record["isMeta"] = True
    if is_compact_summary:
        record["isCompactSummary"] = True
    if tool_use_result is not None:
        record["toolUseResult"] = tool_use_result
    return record


def _assistant(
    session_id: str,
    timestamp: str,
    content: List[Dict[str, Any]],
    cwd: str,
    version: str,
    branch: str,
    uuid: str,
    model: str,
    entrypoint: str = "cli",
    usage: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "parentUuid": None,
        "isSidechain": False,
        "userType": "external",
        "cwd": cwd,
        "sessionId": session_id,
        "version": version,
        "gitBranch": branch,
        "type": "assistant",
        "uuid": uuid,
        "timestamp": timestamp,
        "entrypoint": entrypoint,
        "message": {
            "id": "msg_%s" % uuid,
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content,
            **({"usage": usage} if usage else {}),
        },
    }


def _attachment(
    session_id: str,
    timestamp: str,
    cwd: str,
    version: str,
    branch: str,
    uuid: str,
) -> Dict[str, Any]:
    return {
        "type": "attachment",
        "sessionId": session_id,
        "uuid": uuid,
        "timestamp": timestamp,
        "cwd": cwd,
        "version": version,
        "gitBranch": branch,
        "attachment": {"type": "file", "path": "README.md"},
    }


def _system(
    session_id: str,
    timestamp: str,
    subtype: str,
    **fields: Any,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "type": "system",
        "subtype": subtype,
        "sessionId": session_id,
        "timestamp": timestamp,
    }
    record.update(fields)
    return record


def _title(session_id: str, timestamp: str, title: str) -> Dict[str, Any]:
    return {
        "type": "ai-title",
        "sessionId": session_id,
        "timestamp": timestamp,
        "aiTitle": title,
    }


def _last_prompt(session_id: str, prompt: str) -> Dict[str, Any]:
    return {
        "type": "last-prompt",
        "sessionId": session_id,
        "lastPrompt": prompt,
        "leafUuid": "leaf-%s" % session_id[:8],
    }


def _summary(summary: str) -> Dict[str, Any]:
    return {
        "type": "summary",
        "summary": summary,
        "leafUuid": "leaf-summary",
    }


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _set_mtime(path: Path, stamp: str) -> None:
    seconds = (
        datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.000Z")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    os.utime(path, (seconds, seconds))


def _main_records() -> List[Dict[str, Any]]:
    branch = "feature/handoff"
    return [
        _attachment(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 10),
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0000",
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 10),
            PROMPTS_MAIN[0],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0001",
        ),
        _assistant(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 12),
            [
                _text_block("I'll read the parser first."),
                _tool_use(
                    "Read",
                    {"file_path": PROJECT_ALPHA + "/src/handoff.ts"},
                    "toolu-0002",
                ),
            ],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "a-main-0002",
            MODEL_MAIN,
            usage={
                "input_tokens": 1200,
                "output_tokens": 300,
                "cache_read_input_tokens": 400,
            },
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 13),
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu-0002",
                    "content": "Parsed the handoff module. %s" % NEEDLE_TOOL_OUTPUT,
                }
            ],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0003",
            tool_use_result={"stdout": "Parsed the handoff module."},
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 30),
            PROMPTS_MAIN[1],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0004",
        ),
        _assistant(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 31),
            [_text_block("Continuing with the bounded digest.")],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "a-main-0005",
            MODEL_MAIN,
            usage={
                "input_tokens": 900,
                "output_tokens": 150,
                "cache_read_input_tokens": 100,
            },
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 45),
            [_text_block(PROMPTS_MAIN[2])],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0006",
        ),
        _assistant(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 46),
            [_text_block("Compaction fallback is in place.")],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "a-main-0007",
            MODEL_MAIN,
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 50),
            "<system-reminder>\nThe user opened src/handoff.ts.\n</system-reminder>\n"
            + PROMPTS_MAIN[3],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0008",
        ),
        _assistant(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 52),
            [
                _tool_use(
                    "Edit",
                    {
                        "file_path": PROJECT_ALPHA + "/src/handoff.ts",
                        "old_string": "const limit = 100;",
                        "new_string": "const limit = 200;",
                    },
                    "toolu-0009",
                ),
            ],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "a-main-0009",
            MODEL_MAIN,
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 53),
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu-0009",
                    "content": "Edited src/handoff.ts",
                }
            ],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0010",
            tool_use_result={"filePath": PROJECT_ALPHA + "/src/handoff.ts"},
        ),
        _assistant(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 54),
            [
                _tool_use(
                    "Edit",
                    {
                        "file_path": PROJECT_ALPHA + "/src/handoff.ts",
                        "old_string": "const limit = 200;",
                        "new_string": "const limit = 250;",
                    },
                    "toolu-0011",
                ),
                _tool_use(
                    "Write",
                    {
                        "file_path": PROJECT_ALPHA + "/docs/handoff.md",
                        "content": "# Handoff\n",
                    },
                    "toolu-0012",
                ),
                _tool_use(
                    "NotebookEdit",
                    {
                        "notebook_path": PROJECT_ALPHA + "/notebooks/demo.ipynb",
                        "new_source": "print('handoff')",
                    },
                    "toolu-0013",
                ),
                _tool_use(
                    "Bash",
                    {"command": "python3 -m pytest -q"},
                    "toolu-0014",
                ),
                _tool_use(
                    "TodoWrite",
                    {
                        "todos": [
                            {
                                "content": "Old todo from transcript",
                                "status": "pending",
                                "activeForm": "Working on the old todo",
                            }
                        ]
                    },
                    "toolu-0015",
                ),
            ],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "a-main-0016",
            MODEL_MAIN,
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 55),
            "<local-command-caveat>" + LOCAL_COMMAND_TEXT + "</local-command-caveat>",
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0017",
            is_meta=True,
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 55),
            "<command-name>/clear</command-name>",
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0018",
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 56),
            TASK_NOTIFICATION_TEXT,
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0019",
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 56),
            "<bash-input>git status --short</bash-input>",
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0020",
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 57),
            INTERRUPT_TEXT,
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0021",
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 57),
            "/review",
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0022",
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 58),
            SIDE_CHAIN_PROMPT,
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0023",
            is_sidechain=True,
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 10, 0),
            [
                {"type": "image", "source": {"type": "base64", "data": "AAAA"}},
                _text_block(PROMPTS_MAIN[4]),
            ],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0024",
        ),
        _assistant(
            SESSION_MAIN,
            _ts(2026, 10, 20, 10, 2),
            [_text_block("The screenshot shows a clipped hover card.")],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "a-main-0025",
            MODEL_MAIN,
        ),
        _user(
            SESSION_MAIN,
            _ts(2026, 10, 20, 10, 5),
            PROMPTS_MAIN[5],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "u-main-0026",
        ),
        _assistant(
            SESSION_MAIN,
            _ts(2026, 10, 20, 10, 7),
            [_text_block("All bounded and ready.")],
            PROJECT_ALPHA,
            VERSION_MAIN,
            branch,
            "a-main-0027",
            MODEL_MAIN,
        ),
        _system(
            SESSION_MAIN,
            _ts(2026, 10, 20, 10, 7),
            "turn_duration",
            durationMs=1234,
        ),
        _title(SESSION_MAIN, _ts(2026, 10, 20, 9, 11), "hi"),
        _title(SESSION_MAIN, _ts(2026, 10, 20, 10, 8), TITLE_MAIN),
        _last_prompt(SESSION_MAIN, PROMPTS_MAIN[5]),
        _summary(COMPACT_SUMMARY),
        {
            "type": "queue-operation",
            "operation": "enqueue",
            "sessionId": SESSION_MAIN,
        },
        {
            "type": "file-history-snapshot",
            "sessionId": SESSION_MAIN,
            "snapshot": {"trackedFileBackups": {}},
        },
    ]


def build_claude_code_home(home: Path) -> Path:
    """Create a synthetic ``~/.claude`` store under ``home``."""

    home.mkdir(parents=True, exist_ok=True)
    projects = home / "projects"

    main_path = projects / SLUG_ALPHA / (SESSION_MAIN + ".jsonl")
    _write_jsonl(main_path, _main_records())
    _set_mtime(main_path, _ts(2026, 10, 20, 10, 9))

    # --- second session in the same project: titles and metadata fallbacks ---
    aux_branch = "main"
    aux_path = projects / SLUG_AUX / (SESSION_AUX + ".jsonl")
    _write_jsonl(
        aux_path,
        [
            _user(
                SESSION_AUX,
                _ts(2026, 10, 26, 14, 0),
                PROMPTS_AUX[0],
                PROJECT_AUX,
                VERSION_AUX,
                aux_branch,
                "u-aux-0001",
                entrypoint="claude-vscode",
            ),
            _assistant(
                SESSION_AUX,
                _ts(2026, 10, 26, 14, 1),
                [_text_block("Drafted the migration notes.")],
                PROJECT_AUX,
                VERSION_AUX,
                aux_branch,
                "a-aux-0002",
                MODEL_AUX,
                entrypoint="claude-vscode",
            ),
            _user(
                SESSION_AUX,
                _ts(2026, 10, 26, 14, 3),
                PROMPTS_AUX[1],
                PROJECT_AUX,
                VERSION_AUX,
                aux_branch,
                "u-aux-0003",
                entrypoint="claude-vscode",
            ),
            _assistant(
                SESSION_AUX,
                _ts(2026, 10, 26, 14, 4),
                [
                    _text_block("Notes are ready."),
                    _tool_use(
                        "TodoWrite",
                        {
                            "todos": [
                                {
                                    "content": "Draft migration notes",
                                    "status": "completed",
                                    "activeForm": "Drafting migration notes",
                                },
                                {
                                    "content": "Verify notes",
                                    "status": "in_progress",
                                    "activeForm": "Verifying notes",
                                },
                            ]
                        },
                        "toolu-aux-0005",
                    ),
                ],
                PROJECT_AUX,
                VERSION_AUX,
                aux_branch,
                "a-aux-0004",
                MODEL_AUX,
                entrypoint="claude-vscode",
            ),
            _title(SESSION_AUX, _ts(2026, 10, 26, 14, 2), "继续"),
            _last_prompt(SESSION_AUX, PROMPTS_AUX[1]),
        ],
    )
    _set_mtime(aux_path, _ts(2026, 10, 26, 14, 5))

    # --- plain session: deep-only needle, no tools, no title record ---------
    plain_path = projects / SLUG_GAMMA / (SESSION_PLAIN + ".jsonl")
    _write_jsonl(
        plain_path,
        [
            _user(
                SESSION_PLAIN,
                _ts(2026, 10, 27, 15, 0),
                PROMPT_PLAIN,
                PROJECT_GAMMA,
                VERSION_PLAIN,
                "main",
                "u-plain-0001",
            ),
            _assistant(
                SESSION_PLAIN,
                _ts(2026, 10, 27, 15, 20),
                [
                    _text_block(
                        "Checking the migration ledger. %s found here."
                        % NEEDLE_DEEP_ONLY
                    )
                ],
                PROJECT_GAMMA,
                VERSION_PLAIN,
                "main",
                "a-plain-0002",
                MODEL_MAIN,
            ),
            _assistant(
                SESSION_PLAIN,
                _ts(2026, 10, 27, 15, 30),
                [_text_block("API error: quota exceeded.")],
                PROJECT_GAMMA,
                VERSION_PLAIN,
                "main",
                "a-plain-0003",
                MODEL_MAIN,
            ),
        ],
    )
    _set_mtime(plain_path, _ts(2026, 10, 27, 15, 30))

    # --- compacted session: summary record plus an isCompactSummary message --
    compact_path = projects / SLUG_BETA / (SESSION_COMPACT + ".jsonl")
    _write_jsonl(
        compact_path,
        [
            _user(
                SESSION_COMPACT,
                _ts(2026, 10, 24, 11, 0),
                PROMPT_COMPACT_EARLY,
                PROJECT_BETA,
                VERSION_COMPACT,
                "release/2.0",
                "u-compact-0001",
            ),
            _assistant(
                SESSION_COMPACT,
                _ts(2026, 10, 24, 11, 1),
                [_text_block("The migration plan is drafted.")],
                PROJECT_BETA,
                VERSION_COMPACT,
                "release/2.0",
                "a-compact-0002",
                MODEL_AUX,
            ),
            _summary(COMPACT_SESSION_EARLY),
            _system(
                SESSION_COMPACT,
                _ts(2026, 10, 24, 11, 2),
                "compact_boundary",
                trigger="auto",
            ),
            _user(
                SESSION_COMPACT,
                _ts(2026, 10, 24, 11, 2),
                COMPACT_SESSION_SUMMARY,
                PROJECT_BETA,
                VERSION_COMPACT,
                "release/2.0",
                "u-compact-0003",
                is_compact_summary=True,
            ),
            _user(
                SESSION_COMPACT,
                _ts(2026, 10, 24, 11, 5),
                PROMPT_COMPACT_RESUME,
                PROJECT_BETA,
                VERSION_COMPACT,
                "release/2.0",
                "u-compact-0004",
            ),
            _assistant(
                SESSION_COMPACT,
                _ts(2026, 10, 24, 11, 10),
                [_text_block("Resumed from the compaction summary.")],
                PROJECT_BETA,
                VERSION_COMPACT,
                "release/2.0",
                "a-compact-0005",
                MODEL_AUX,
            ),
        ],
    )
    _set_mtime(compact_path, _ts(2026, 10, 24, 11, 10))

    # --- subagent transcript: must never be a session -----------------------
    subagent_path = (
        projects
        / SLUG_ALPHA
        / SESSION_MAIN
        / "subagents"
        / "agent-c1a0de05.jsonl"
    )
    _write_jsonl(
        subagent_path,
        [
            _user(
                SESSION_MAIN,
                _ts(2026, 10, 20, 9, 20),
                PROMPT_SUBAGENT,
                PROJECT_ALPHA,
                VERSION_MAIN,
                "feature/handoff",
                "u-subagent-0001",
                is_sidechain=True,
            ),
            _assistant(
                SESSION_MAIN,
                _ts(2026, 10, 20, 9, 21),
                [_text_block("Subagent output.")],
                PROJECT_ALPHA,
                VERSION_MAIN,
                "feature/handoff",
                "a-subagent-0002",
                MODEL_MAIN,
            ),
        ],
    )
    _set_mtime(subagent_path, _ts(2026, 10, 20, 9, 21))
    _write_json(
        subagent_path.with_suffix(".meta.json"),
        {"agentId": SUBAGENT_ID, "sessionId": SESSION_MAIN},
    )

    # --- decoy nested transcript directly under a project dir ---------------
    decoy_path = projects / SLUG_ALPHA / "agent-c1a0deff.jsonl"
    _write_jsonl(
        decoy_path,
        [
            _user(
                SESSION_MAIN,
                _ts(2026, 10, 20, 9, 25),
                PROMPT_DECOY,
                PROJECT_ALPHA,
                VERSION_MAIN,
                "feature/handoff",
                "u-decoy-0001",
            ),
        ],
    )
    _set_mtime(decoy_path, _ts(2026, 10, 20, 9, 25))

    # --- stale per-project index: never authoritative -----------------------
    _write_json(
        projects / SLUG_ALPHA / "sessions-index.json",
        {
            "version": 1,
            "entries": [
                {
                    "created": 1792000000000,
                    "fileMtime": 1792000000000,
                    "firstPrompt": STALE_TITLE,
                    "fullPath": str(projects / SLUG_ALPHA / (SESSION_STALE + ".jsonl")),
                    "gitBranch": "main",
                    "isSidechain": False,
                    "messageCount": 5,
                    "modified": 1792000000000,
                    "projectPath": PROJECT_ALPHA,
                    "sessionId": SESSION_STALE,
                },
                {
                    "created": 1792000000000,
                    "fileMtime": 1792000000000,
                    "firstPrompt": "An index first prompt that is stale",
                    "fullPath": str(main_path),
                    "gitBranch": "main",
                    "isSidechain": False,
                    "messageCount": 99,
                    "modified": 1792000000000,
                    "projectPath": PROJECT_ALPHA,
                    "sessionId": SESSION_MAIN,
                },
            ],
            "originalPath": PROJECT_ALPHA,
        },
    )
    _write_json(
        projects / "-" / "sessions-index.json",
        {"version": 1, "entries": [], "originalPath": "/"},
    )

    # --- todos: the store file wins over the transcript TodoWrite ------------
    _write_json(
        home / "todos" / (SESSION_MAIN + "-agent-agent01.json"),
        [
            {
                "content": "Refactor the digest",
                "status": "completed",
                "activeForm": "Refactoring the digest",
            },
            {
                "content": "Add prompt paging",
                "status": "in_progress",
                "activeForm": "Adding prompt paging",
            },
            {
                "content": "Update docs",
                "status": "pending",
                "activeForm": "Updating docs",
            },
        ],
    )
    _set_mtime(
        home / "todos" / (SESSION_MAIN + "-agent-agent01.json"),
        _ts(2026, 10, 20, 10, 9),
    )

    # --- legacy history file: never a session -------------------------------
    _write_jsonl(
        home / "history.jsonl",
        [
            {
                "display": HISTORY_PROMPT,
                "pastedContents": {},
                "timestamp": 1792000000000,
                "project": PROJECT_ALPHA,
                "sessionId": SESSION_MAIN,
            }
        ],
    )

    return home
