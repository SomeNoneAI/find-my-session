"""Build a synthetic Grok Build store for tests.

The layout mirrors ``~/.grok/sessions``: sessions are grouped by the
URL-encoded working directory, and each session directory holds the
authoritative ``updates.jsonl`` ACP stream, a ``summary.json`` index entry,
compaction checkpoints, and optional compaction history. Every identifier,
path, prompt, and title is invented.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

SESSION_MAIN = "9a0b1c01-1111-4a1b-8c1d-111111111111"
SESSION_AUX = "9a0b1c02-2222-4b2c-9d2e-222222222222"
SESSION_PLAIN = "9a0b1c03-3333-4c3d-9e4f-333333333333"
SESSION_COMPACT = "9a0b1c04-4444-4d4e-8f5a-444444444444"
SESSION_SUBAGENT = "9a0b1c05-5555-4e5f-9a6b-555555555555"
SESSION_EMPTY = "9a0b1c06-6666-4f6a-8b7c-666666666666"
SESSION_ORPHAN_SUBAGENT = "9a0b1c07-7777-4a7b-9c8d-777777777777"

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_AUX = "/Users/example/project-aux"
PROJECT_DELTA = "/Users/example/project-delta"
PROJECT_BETA = "/Users/example/project-beta"

GROUP_ALPHA = quote(PROJECT_ALPHA, safe="")
GROUP_AUX = quote(PROJECT_AUX, safe="")
GROUP_BETA = quote(PROJECT_BETA, safe="")
GROUP_DELTA_SLUG = "project-delta-9f2c"

TITLE_MAIN = "Refactor the handoff digest for the CLI"
TITLE_COMPACT = "Plan the migration and resume."
GENERIC_TITLE = "继续"

PROMPTS_MAIN = (
    "Please refactor the handoff digest so the CLI stays bounded. grok-main-needle",
    "继续",
    "Tighten the digest tests.",
    "[Image #1] Inspect the preview screenshot.",
    "Please summarize the handoff digest and keep the output short enough for the CLI.",
)
PROMPTS_AUX = (
    "Draft the migration notes.",
    "继续",
)
PROMPT_PLAIN = "Investigate the migration drift in project delta. grok-plain-needle"
PROMPT_COMPACT_EARLY = "Plan the migration."
PROMPT_COMPACT_RESUME = "Continue after compaction."
PROMPT_SUBAGENT = "Subagent scratch work. grok-subagent-needle."
PROMPT_DECOY = "Decoy session that must never be listed. grok-decoy-needle."
PROMPT_HIDDEN = "Hidden reminder that must not count. grok-hidden-needle."
PROMPT_SYNTHETIC = "Synthetic sweep prompt that must not count."
PROMPT_SLASH = "/review"
PROMPT_INTERRUPT = "[Request interrupted by user]"

NEEDLE_MAIN = "grok-main-needle"
NEEDLE_TOOL_OUTPUT = "grok-tool-output-needle"
NEEDLE_DEEP_ONLY = "grok-deep-only-needle"
NEEDLE_COMPACTION_ONLY = "grok-compaction-needle"
NEEDLE_CHAT_ONLY = "grok-chat-history-needle"
NEEDLE_SUBAGENT = "grok-subagent-needle"
NEEDLE_DECOY = "grok-decoy-needle"

COMPACT_SUMMARY = (
    "This session is being continued from a previous conversation.\n"
    "Summary of the handoff digest refactor."
)
COMPACT_SUMMARY_OLD = (
    "This session is being continued from a previous conversation.\n"
    "An older summary that must lose to the newer checkpoint."
)
COMPACT_SESSION_SUMMARY = (
    "This session is being continued from a previous conversation.\n"
    "Summary of the migration plan and its resume point."
)

MODEL_MAIN = "synthetic-grok-1"
MODEL_AUX = "synthetic-grok-2"
MODEL_PLAIN = "synthetic-grok-3"
MODEL_COMPACT = "synthetic-grok-4"

BRANCH_MAIN = "feature/handoff"
BRANCH_AUX = "main"
BRANCH_PLAIN = "main"
BRANCH_COMPACT = "release/2.0"


def _epoch(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0
) -> int:
    return int(
        datetime(
            year, month, day, hour, minute, tzinfo=timezone.utc
        ).timestamp()
    )


def _summary_stamp(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0
) -> str:
    return (
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S.000000Z")
    )


def _record(
    session_id: str,
    update: Dict[str, Any],
    timestamp: int,
    method: str = "session/update",
) -> Dict[str, Any]:
    return {
        "timestamp": timestamp,
        "method": method,
        "params": {
            "sessionId": session_id,
            "update": update,
            "_meta": {},
        },
    }


def _user_chunk(
    session_id: str,
    text: str,
    prompt_index: int,
    timestamp: int,
    *,
    hidden: bool = False,
    synthetic: bool = False,
    model: str = MODEL_MAIN,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "modelId": model,
        "promptIndex": prompt_index,
    }
    if hidden:
        meta["hideFromScrollback"] = True
    if synthetic:
        meta["syntheticPrompt"] = True
    return _record(
        session_id,
        {
            "sessionUpdate": "user_message_chunk",
            "content": {"type": "text", "text": text},
            "_meta": meta,
        },
        timestamp,
    )


def _image_chunk(
    session_id: str,
    prompt_index: int,
    timestamp: int,
    *,
    model: str = MODEL_MAIN,
) -> Dict[str, Any]:
    return _record(
        session_id,
        {
            "sessionUpdate": "user_message_chunk",
            "content": {
                "type": "image",
                "mimeType": "image/png",
                "data": "AAAA",
            },
            "_meta": {"modelId": model, "promptIndex": prompt_index},
        },
        timestamp,
    )


def _agent_chunk(
    session_id: str, text: str, timestamp: int
) -> Dict[str, Any]:
    return _record(
        session_id,
        {
            "sessionUpdate": "agent_message_chunk",
            "content": {"type": "text", "text": text},
        },
        timestamp,
    )


def _thought_chunk(
    session_id: str, text: str, timestamp: int
) -> Dict[str, Any]:
    return _record(
        session_id,
        {
            "sessionUpdate": "agent_thought_chunk",
            "content": {"type": "text", "text": text},
        },
        timestamp,
    )


def _tool_call(
    session_id: str,
    name: str,
    arguments: Dict[str, Any],
    call_id: str,
    timestamp: int,
) -> Dict[str, Any]:
    return _record(
        session_id,
        {
            "sessionUpdate": "tool_call",
            "toolCallId": call_id,
            "title": name,
            "rawInput": arguments,
            "_meta": {},
        },
        timestamp,
    )


def _tool_update(
    session_id: str,
    call_id: str,
    timestamp: int,
    *,
    status: str = "completed",
    output: Optional[str] = None,
) -> Dict[str, Any]:
    update: Dict[str, Any] = {
        "sessionUpdate": "tool_call_update",
        "toolCallId": call_id,
        "status": status,
        "kind": "other",
        "locations": [],
    }
    if output is not None:
        update["rawOutput"] = output
    return _record(session_id, update, timestamp)


def _plan(
    session_id: str, entries: List[Dict[str, Any]], timestamp: int
) -> Dict[str, Any]:
    return _record(
        session_id,
        {"sessionUpdate": "plan", "entries": entries},
        timestamp,
    )


def _turn_done(
    session_id: str, timestamp: int, *, stop_reason: str = "end_turn"
) -> Dict[str, Any]:
    return _record(
        session_id,
        {
            "sessionUpdate": "turn_completed",
            "prompt_id": "prompt-%s" % timestamp,
            "stop_reason": stop_reason,
            "usage": {},
            "elapsed_ms": 1000,
        },
        timestamp,
    )


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


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _set_mtime(path: Path, stamp: str) -> None:
    seconds = (
        datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.000000Z")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    os.utime(path, (seconds, seconds))


def _summary(
    session_id: str,
    cwd: Optional[str],
    created: str,
    updated: str,
    *,
    title: str = "",
    summary_text: str = "",
    model: str = MODEL_MAIN,
    branch: str = "",
    **extra: Any,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "info": {"id": session_id},
        "generated_title": title,
        "session_summary": summary_text,
        "created_at": created,
        "updated_at": updated,
        "last_active_at": updated,
        "current_model_id": model,
        "num_messages": 0,
        "chat_format_version": 1,
        "grok_home": "/Users/example/.grok",
        "sandbox_profile": "",
        "reasoning_effort": "medium",
        "next_trace_turn": 0,
        "agent_name": "",
        "head_branch": branch,
    }
    if cwd is not None:
        data["info"]["cwd"] = cwd
    data.update(extra)
    return data


def _checkpoint(
    index: int,
    summary_text: str,
    created: str,
) -> Dict[str, Any]:
    return {
        "checkpoint_id": "checkpoint-%02d" % index,
        "prompt_index_at_compaction": index,
        "compacted_history": [
            {
                "type": "system",
                "content": "Synthetic system context for the compaction.",
            },
            {
                "type": "user",
                "content": summary_text,
                "synthetic_reason": "compaction",
            },
            {
                "type": "user",
                "content": [{"type": "text", "text": "A later synthetic turn."}],
                "synthetic_reason": "compaction",
            },
        ],
        "schema_version": 1,
        "created_at": created,
        "original_user_info": "",
        "reread_file_paths": [],
    }


def _main_records() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    records.append(
        _user_chunk(
            SESSION_MAIN,
            PROMPTS_MAIN[0],
            0,
            _epoch(2026, 10, 20, 9, 10),
        )
    )
    records.append(
        _thought_chunk(
            SESSION_MAIN,
            "The parser is probably in src.",
            _epoch(2026, 10, 20, 9, 11),
        )
    )
    records.append(
        _agent_chunk(
            SESSION_MAIN,
            "I'll inspect the parser first.",
            _epoch(2026, 10, 20, 9, 11),
        )
    )
    records.append(
        _tool_call(
            SESSION_MAIN,
            "read_file",
            {"target_file": PROJECT_ALPHA + "/src/handoff.ts"},
            "call-0001",
            _epoch(2026, 10, 20, 9, 11),
        )
    )
    records.append(
        _tool_update(
            SESSION_MAIN,
            "call-0001",
            _epoch(2026, 10, 20, 9, 12),
            output="Parsed the handoff module. %s" % NEEDLE_TOOL_OUTPUT,
        )
    )
    records.append(_turn_done(SESSION_MAIN, _epoch(2026, 10, 20, 9, 12)))
    records.append(
        _user_chunk(
            SESSION_MAIN, PROMPTS_MAIN[1], 1, _epoch(2026, 10, 20, 9, 30)
        )
    )
    records.append(
        _agent_chunk(
            SESSION_MAIN,
            "Continuing with the bounded digest.",
            _epoch(2026, 10, 20, 9, 31),
        )
    )
    records.append(_turn_done(SESSION_MAIN, _epoch(2026, 10, 20, 9, 31)))
    records.append(
        _user_chunk(
            SESSION_MAIN,
            "<system-reminder>\nThe user opened src/handoff.ts.\n</system-reminder>\n"
            + PROMPTS_MAIN[2],
            2,
            _epoch(2026, 10, 20, 9, 50),
        )
    )
    records.append(
        _tool_call(
            SESSION_MAIN,
            "search_replace",
            {"file_path": PROJECT_ALPHA + "/src/handoff.ts"},
            "call-0002",
            _epoch(2026, 10, 20, 9, 52),
        )
    )
    records.append(
        _tool_update(
            SESSION_MAIN,
            "call-0002",
            _epoch(2026, 10, 20, 9, 52),
            output="Updated the digest limit.",
        )
    )
    records.append(
        _agent_chunk(
            SESSION_MAIN, "Edits applied.", _epoch(2026, 10, 20, 9, 53)
        )
    )
    records.append(
        _tool_call(
            SESSION_MAIN,
            "search_replace",
            {"file_path": PROJECT_ALPHA + "/src/handoff.ts"},
            "call-0003",
            _epoch(2026, 10, 20, 9, 54),
        )
    )
    records.append(
        _tool_update(
            SESSION_MAIN, "call-0003", _epoch(2026, 10, 20, 9, 54)
        )
    )
    records.append(
        _tool_call(
            SESSION_MAIN,
            "write",
            {"file_path": PROJECT_ALPHA + "/docs/handoff.md"},
            "call-0004",
            _epoch(2026, 10, 20, 9, 54),
        )
    )
    records.append(
        _tool_update(
            SESSION_MAIN, "call-0004", _epoch(2026, 10, 20, 9, 54)
        )
    )
    records.append(
        _tool_call(
            SESSION_MAIN,
            "run_terminal_command",
            {"command": "python3 -m pytest -q"},
            "call-0005",
            _epoch(2026, 10, 20, 9, 54),
        )
    )
    records.append(
        _tool_update(
            SESSION_MAIN,
            "call-0005",
            _epoch(2026, 10, 20, 9, 54),
            output="All tests pass.",
        )
    )
    records.append(
        _plan(
            SESSION_MAIN,
            [
                {
                    "content": "Refactor the digest",
                    "priority": "medium",
                    "status": "completed",
                },
                {
                    "content": "Add prompt paging",
                    "priority": "medium",
                    "status": "in_progress",
                },
                {
                    "content": "Update docs",
                    "priority": "medium",
                    "status": "pending",
                },
            ],
            _epoch(2026, 10, 20, 9, 55),
        )
    )
    records.append(_turn_done(SESSION_MAIN, _epoch(2026, 10, 20, 9, 55)))
    records.append(
        _user_chunk(
            SESSION_MAIN,
            PROMPT_HIDDEN,
            3,
            _epoch(2026, 10, 20, 9, 55),
            hidden=True,
        )
    )
    records.append(
        _user_chunk(
            SESSION_MAIN,
            PROMPT_SYNTHETIC,
            4,
            _epoch(2026, 10, 20, 9, 56),
            synthetic=True,
        )
    )
    records.append(
        _user_chunk(
            SESSION_MAIN, PROMPT_SLASH, 5, _epoch(2026, 10, 20, 9, 57)
        )
    )
    records.append(
        _user_chunk(
            SESSION_MAIN, PROMPT_INTERRUPT, 6, _epoch(2026, 10, 20, 9, 57)
        )
    )
    records.append(
        _image_chunk(SESSION_MAIN, 7, _epoch(2026, 10, 20, 10, 0))
    )
    records.append(
        _user_chunk(
            SESSION_MAIN, PROMPTS_MAIN[3], 7, _epoch(2026, 10, 20, 10, 0)
        )
    )
    records.append(
        _agent_chunk(
            SESSION_MAIN,
            "The screenshot shows a clipped hover card.",
            _epoch(2026, 10, 20, 10, 2),
        )
    )
    records.append(
        _user_chunk(
            SESSION_MAIN, PROMPTS_MAIN[4], 8, _epoch(2026, 10, 20, 10, 5)
        )
    )
    records.append(
        _agent_chunk(
            SESSION_MAIN, "All bounded and ready.", _epoch(2026, 10, 20, 10, 7)
        )
    )
    records.append(_turn_done(SESSION_MAIN, _epoch(2026, 10, 20, 10, 7)))
    return records


def _chat_history() -> List[Dict[str, Any]]:
    return [
        {
            "type": "system",
            "content": "Synthetic system prompt for the Grok Build fixture.",
        },
        {
            "type": "user",
            "content": [{"type": "text", "text": NEEDLE_CHAT_ONLY}],
            "synthetic_reason": "background",
        },
        {
            "type": "user",
            "content": [{"type": "text", "text": PROMPTS_MAIN[0]}],
            "prompt_index": 0,
        },
        {
            "type": "assistant",
            "content": [{"type": "text", "text": "I'll inspect the parser."}],
            "model_id": MODEL_MAIN,
            "reasoning_effort": "medium",
        },
    ]


def build_grok_home(home: Path) -> Path:
    """Create a synthetic ``~/.grok`` store under ``home``."""

    home.mkdir(parents=True, exist_ok=True)
    sessions = home / "sessions"

    # --- main session: tools, todos, compaction, image prompt, hidden noise --
    main_dir = sessions / GROUP_ALPHA / SESSION_MAIN
    _write_jsonl(main_dir / "updates.jsonl", _main_records())
    _write_jsonl(main_dir / "chat_history.jsonl", _chat_history())
    _write_json(
        main_dir / "summary.json",
        _summary(
            SESSION_MAIN,
            PROJECT_ALPHA,
            _summary_stamp(2026, 10, 20, 9, 10),
            _summary_stamp(2026, 10, 20, 10, 8),
            title=TITLE_MAIN,
            model=MODEL_MAIN,
            branch=BRANCH_MAIN,
            num_messages=5,
        ),
    )
    _write_text(
        main_dir / "compaction" / "INDEX.md",
        "# Compaction Segment Index\n\n| Segment | Turn |\n| --- | --- |\n",
    )
    _write_text(
        main_dir / "compaction" / "segment_001.md",
        "# HISTORICAL -- DO NOT EDIT\n"
        "# Record of a compacted turn\n\n"
        "%s\n" % NEEDLE_COMPACTION_ONLY,
    )
    _write_json(
        main_dir / "compaction_checkpoints" / "checkpoint-old.json",
        _checkpoint(2, COMPACT_SUMMARY_OLD, _summary_stamp(2026, 10, 20, 9, 55)),
    )
    _write_json(
        main_dir / "compaction_checkpoints" / "checkpoint-new.json",
        _checkpoint(8, COMPACT_SUMMARY, _summary_stamp(2026, 10, 20, 10, 8)),
    )
    _set_mtime(
        main_dir / "compaction_checkpoints" / "checkpoint-old.json",
        _summary_stamp(2026, 10, 20, 9, 55),
    )
    _set_mtime(
        main_dir / "compaction_checkpoints" / "checkpoint-new.json",
        _summary_stamp(2026, 10, 20, 10, 8),
    )
    (main_dir / "subagents" / SESSION_SUBAGENT).mkdir(parents=True)
    (main_dir / "subagents" / SESSION_ORPHAN_SUBAGENT).mkdir(parents=True)
    _set_mtime(
        main_dir / "updates.jsonl", _summary_stamp(2026, 10, 20, 10, 8)
    )

    # --- fork: a generic generated title, two prompts, separate top-level ----
    aux_dir = sessions / GROUP_ALPHA / SESSION_AUX
    _write_jsonl(
        aux_dir / "updates.jsonl",
        [
            _user_chunk(
                SESSION_AUX,
                PROMPTS_AUX[0],
                0,
                _epoch(2026, 10, 26, 14, 0),
                model=MODEL_AUX,
            ),
            _agent_chunk(
                SESSION_AUX,
                "Drafted the migration notes.",
                _epoch(2026, 10, 26, 14, 1),
            ),
            _user_chunk(
                SESSION_AUX,
                PROMPTS_AUX[1],
                1,
                _epoch(2026, 10, 26, 14, 3),
                model=MODEL_AUX,
            ),
            _agent_chunk(
                SESSION_AUX,
                "Notes are ready.",
                _epoch(2026, 10, 26, 14, 4),
            ),
            _turn_done(SESSION_AUX, _epoch(2026, 10, 26, 14, 4)),
        ],
    )
    _write_json(
        aux_dir / "summary.json",
        _summary(
            SESSION_AUX,
            PROJECT_ALPHA,
            _summary_stamp(2026, 10, 26, 14, 0),
            _summary_stamp(2026, 10, 26, 14, 5),
            title=GENERIC_TITLE,
            model=MODEL_AUX,
            branch=BRANCH_AUX,
            parent_session_id=SESSION_MAIN,
            forked_at=_summary_stamp(2026, 10, 26, 14, 0),
            num_messages=2,
        ),
    )
    _set_mtime(
        aux_dir / "updates.jsonl", _summary_stamp(2026, 10, 26, 14, 5)
    )

    # --- plain session: slug group, .cwd fallback, deep-only needle ---------
    plain_dir = sessions / GROUP_DELTA_SLUG / SESSION_PLAIN
    _write_jsonl(
        plain_dir / "updates.jsonl",
        [
            _user_chunk(
                SESSION_PLAIN,
                PROMPT_PLAIN,
                0,
                _epoch(2026, 10, 27, 15, 0),
                model=MODEL_PLAIN,
            ),
            _agent_chunk(
                SESSION_PLAIN,
                "Checking the migration ledger. %s found here."
                % NEEDLE_DEEP_ONLY,
                _epoch(2026, 10, 27, 15, 20),
            ),
            _agent_chunk(
                SESSION_PLAIN,
                "API error: synthetic quota exceeded.",
                _epoch(2026, 10, 27, 15, 30),
            ),
            _turn_done(
                SESSION_PLAIN,
                _epoch(2026, 10, 27, 15, 30),
                stop_reason="error",
            ),
        ],
    )
    _write_text(plain_dir.parent / ".cwd", PROJECT_DELTA + "\n")
    _write_json(
        plain_dir / "summary.json",
        _summary(
            SESSION_PLAIN,
            None,
            _summary_stamp(2026, 10, 27, 15, 0),
            _summary_stamp(2026, 10, 27, 15, 30),
            model=MODEL_PLAIN,
            branch=BRANCH_PLAIN,
            num_messages=1,
        ),
    )
    _set_mtime(
        plain_dir / "updates.jsonl", _summary_stamp(2026, 10, 27, 15, 30)
    )

    # --- compacted session: latest checkpoint wins ---------------------------
    compact_dir = sessions / GROUP_BETA / SESSION_COMPACT
    _write_jsonl(
        compact_dir / "updates.jsonl",
        [
            _user_chunk(
                SESSION_COMPACT,
                PROMPT_COMPACT_EARLY,
                0,
                _epoch(2026, 10, 24, 11, 0),
                model=MODEL_COMPACT,
            ),
            _agent_chunk(
                SESSION_COMPACT,
                "The migration plan is drafted.",
                _epoch(2026, 10, 24, 11, 1),
            ),
            _user_chunk(
                SESSION_COMPACT,
                PROMPT_COMPACT_RESUME,
                1,
                _epoch(2026, 10, 24, 11, 5),
                model=MODEL_COMPACT,
            ),
            _agent_chunk(
                SESSION_COMPACT,
                "Resumed from the compaction summary.",
                _epoch(2026, 10, 24, 11, 10),
            ),
            _turn_done(
                SESSION_COMPACT, _epoch(2026, 10, 24, 11, 10)
            ),
        ],
    )
    _write_json(
        compact_dir / "summary.json",
        _summary(
            SESSION_COMPACT,
            PROJECT_BETA,
            _summary_stamp(2026, 10, 24, 11, 0),
            _summary_stamp(2026, 10, 24, 11, 10),
            title=TITLE_COMPACT,
            model=MODEL_COMPACT,
            branch=BRANCH_COMPACT,
            num_messages=2,
        ),
    )
    _write_json(
        compact_dir / "compaction_checkpoints" / "checkpoint-early.json",
        _checkpoint(
            1,
            "This session is being continued from a previous conversation.\n"
            "An earlier migration summary.",
            _summary_stamp(2026, 10, 24, 11, 2),
        ),
    )
    _write_json(
        compact_dir / "compaction_checkpoints" / "checkpoint-late.json",
        _checkpoint(
            2,
            COMPACT_SESSION_SUMMARY,
            _summary_stamp(2026, 10, 24, 11, 8),
        ),
    )
    _set_mtime(
        compact_dir / "compaction_checkpoints" / "checkpoint-early.json",
        _summary_stamp(2026, 10, 24, 11, 2),
    )
    _set_mtime(
        compact_dir / "compaction_checkpoints" / "checkpoint-late.json",
        _summary_stamp(2026, 10, 24, 11, 8),
    )
    _set_mtime(
        compact_dir / "updates.jsonl", _summary_stamp(2026, 10, 24, 11, 10)
    )

    # --- subagent child session: must never be listed -----------------------
    subagent_dir = sessions / GROUP_ALPHA / SESSION_SUBAGENT
    _write_jsonl(
        subagent_dir / "updates.jsonl",
        [
            _user_chunk(
                SESSION_SUBAGENT,
                PROMPT_SUBAGENT,
                0,
                _epoch(2026, 10, 20, 9, 20),
                model=MODEL_MAIN,
            ),
            _agent_chunk(
                SESSION_SUBAGENT,
                "Subagent output.",
                _epoch(2026, 10, 20, 9, 21),
            ),
        ],
    )
    _write_json(
        subagent_dir / "summary.json",
        _summary(
            SESSION_SUBAGENT,
            PROJECT_ALPHA,
            _summary_stamp(2026, 10, 20, 9, 20),
            _summary_stamp(2026, 10, 20, 9, 21),
            model=MODEL_MAIN,
            branch=BRANCH_MAIN,
            session_kind="subagent",
            parent_session_id=SESSION_MAIN,
            num_messages=1,
        ),
    )
    _set_mtime(
        subagent_dir / "updates.jsonl",
        _summary_stamp(2026, 10, 20, 9, 21),
    )

    # --- empty session: no transcript, must not be listed -------------------
    empty_dir = sessions / GROUP_ALPHA / SESSION_EMPTY
    _write_json(
        empty_dir / "summary.json",
        _summary(
            SESSION_EMPTY,
            PROJECT_ALPHA,
            _summary_stamp(2026, 10, 28, 8, 0),
            _summary_stamp(2026, 10, 28, 8, 0),
            num_messages=0,
        ),
    )

    # --- group-level decoy file: never a session ----------------------------
    _write_json(
        sessions / GROUP_ALPHA / "notes.json",
        {"note": PROMPT_DECOY},
    )

    return home
