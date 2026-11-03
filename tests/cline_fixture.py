"""Build a synthetic Cline CLI/desktop store for tests.

The layout mirrors ``~/.cline``: each session is a directory under
``data/sessions/<session-id>/`` holding ``<session-id>.json`` (metadata),
``<session-id>.messages.json`` (pretty-printed transcript), and an optional
``<session-id>.compaction.json``. Subagent transcripts share the parent
session directory under a different file name. Every identifier, path, and
prompt is invented.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

SESSION_MAIN = "session_1793000000100_c1a0d"
SESSION_AUX = "session_1793000000200_c1a0e"
SESSION_COMPACT = "session_1793000000300_c1a0g"
SESSION_PLAIN = "1793000000000_c1a0f"
SUBAGENT_STEM = "lint-style__c1a0z"
SUBAGENT_ID = SESSION_MAIN + "__teamtask__" + SUBAGENT_STEM

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_AUX = "/Users/example/project-aux"
PROJECT_GAMMA = "/Users/example/project-gamma"

TITLE_MAIN = "Refactor the Cline digest"
TITLE_COMPACT = "Compact the Cline session context"

MODEL_MAIN = "synthetic-cline-1"
MODEL_AUX = "synthetic-cline-2"
PROVIDER = "synthetic-provider"
VERSION_MAIN = "0.0.1-synthetic"
VERSION_AUX = "0.0.2-synthetic"
VERSION_COMPACT = "0.0.3-synthetic"
BRANCH_MAIN = "feature/synthetic-digest"
BRANCH_AUX = "feature/synthetic-notes"

PROMPTS_MAIN = (
    "Please refactor the Cline handoff digest so the CLI stays bounded. "
    "cline-main-needle",
    "继续",
    "Ship the compact summary fallback.",
    "Tighten the digest tests.",
)
PROMPTS_AUX = (
    "Draft the migration notes.",
    "继续",
)
PROMPT_PLAIN = "Investigate the migration drift."
PROMPT_COMPACT_EARLY = "Plan the migration."
PROMPT_COMPACT_RESUME = "Continue after compaction."
PROMPT_SUBAGENT = "Subagent scratch work. cline-subagent-needle."

COMPACT_SUMMARY = (
    "Context summary:\n\n"
    "## Goal\n"
    "Bound the Cline digest.\n\n"
    "## State\n"
    "cline-compaction-only-needle"
)
COMPACT_EARLY_MESSAGE = "Context summary:\n\nEarlier synthetic context summary."

NEEDLE_MAIN = "cline-main-needle"
NEEDLE_TOOL_OUTPUT = "cline-tool-output-needle"
NEEDLE_DEEP_ONLY = "cline-deep-only-needle"
NEEDLE_COMPACTION_ONLY = "cline-compaction-only-needle"
NEEDLE_SUBAGENT = "cline-subagent-needle"
NEEDLE_INJECTED = "cline-injected-needle"

SYSTEM_TEXT = (
    "[SYSTEM] This run is not complete until you call submit_and_exit. "
    "cline-injected-needle"
)
CUTOFF_TEXT = (
    "Your previous response was cut off. Continue where you left off. "
    "cline-injected-needle"
)
TEAM_UPDATE_TEXT = (
    "System-delivered teammate async run updates: all tasks queued. "
    "cline-injected-needle"
)

EDITOR_REL = "src/digest.py"
EDITOR_ABS = PROJECT_ALPHA + "/src/render.py"


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


def _iso_ms(value: int) -> str:
    return (
        datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S.")
        + "%03dZ" % (value % 1000)
    )


def _text_block(text: str) -> Dict[str, Any]:
    return {"type": "text", "text": text}


def _user(
    identifier: str,
    ts: int,
    blocks: Any,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    message: Dict[str, Any] = {
        "id": identifier,
        "role": "user",
        "content": blocks if isinstance(blocks, list) else [_text_block(blocks)],
        "ts": ts,
    }
    if metadata:
        message["metadata"] = metadata
    return message


def _prompt(identifier: str, ts: int, text: str, mode: str = "yolo") -> Dict[str, Any]:
    return _user(
        identifier, ts, '<user_input mode="%s">%s</user_input>' % (mode, text)
    )


def _assistant(
    identifier: str,
    ts: int,
    blocks: Any,
    model: str = MODEL_MAIN,
) -> Dict[str, Any]:
    return {
        "id": identifier,
        "role": "assistant",
        "content": blocks if isinstance(blocks, list) else [_text_block(blocks)],
        "ts": ts,
        "modelInfo": {"id": model, "provider": PROVIDER},
    }


def _tool_use(name: str, arguments: Dict[str, Any], call_id: str) -> Dict[str, Any]:
    return {"type": "tool_use", "id": call_id, "name": name, "input": arguments}


def _tool_result(
    identifier: str, ts: int, call_id: str, name: str, result: str
) -> Dict[str, Any]:
    return _user(
        identifier,
        ts,
        [
            {
                "type": "tool_result",
                "tool_use_id": call_id,
                "name": name,
                "content": [{"query": "synthetic", "result": result}],
            }
        ],
    )


def _messages_document(
    messages: Any,
    session_id: str,
    updated_at: str,
    agent: str = "cline",
    origin: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    document: Dict[str, Any] = {
        "version": 1,
        "updated_at": updated_at,
        "agent": agent,
        "sessionId": session_id,
        "messages": messages,
        "system_prompt": "Synthetic system prompt for fixture sessions.",
    }
    if origin is not None:
        document["origin"] = origin
    return document


def _meta(
    session_id: str,
    *,
    source: str,
    started_at: str,
    ended_at: str,
    cwd: str,
    model: str,
    branch: str,
    version: str,
    prompt: str,
    title: str = "",
    messages_path: Path,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "sessionHistoryOrigin": {"mode": "user", "version": version},
        "git": {
            "url": "https://example.invalid/example/repo.git",
            "branch": branch,
        },
    }
    if title:
        metadata["title"] = title
    return {
        "version": 1,
        "session_id": session_id,
        "source": source,
        "pid": 4242,
        "started_at": started_at,
        "ended_at": ended_at,
        "exit_code": 0,
        "status": "completed",
        "interactive": False,
        "provider": PROVIDER,
        "model": model,
        "cwd": cwd,
        "workspace_root": cwd,
        "enable_tools": True,
        "enable_spawn": True,
        "enable_teams": True,
        "prompt": prompt,
        "metadata": metadata,
        "messages_path": str(messages_path),
    }


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _main_messages() -> Any:
    return [
        _prompt("m-main-01", _ms(2026, 10, 25, 9, 0, 5), PROMPTS_MAIN[0]),
        _user("m-main-02", _ms(2026, 10, 25, 9, 0, 6), SYSTEM_TEXT),
        _assistant(
            "m-main-03",
            _ms(2026, 10, 25, 9, 0, 30),
            [
                _text_block("I'll inspect the digest renderer."),
                _tool_use(
                    "read_files",
                    {"files": [{"path": PROJECT_ALPHA + "/src/render.py"}]},
                    "call-read-1",
                ),
            ],
        ),
        _tool_result(
            "m-main-04",
            _ms(2026, 10, 25, 9, 0, 31),
            "call-read-1",
            "read_files",
            "def render_digest():  # cline-tool-output-needle\n    pass",
        ),
        _assistant(
            "m-main-05",
            _ms(2026, 10, 25, 9, 1, 0),
            [
                _tool_use(
                    "editor",
                    {"command": "str_replace", "path": EDITOR_REL},
                    "call-edit-1",
                )
            ],
        ),
        _tool_result(
            "m-main-06",
            _ms(2026, 10, 25, 9, 1, 1),
            "call-edit-1",
            "editor",
            "Edited %s" % EDITOR_REL,
        ),
        _prompt(
            "m-main-07",
            _ms(2026, 10, 25, 9, 2, 0),
            PROMPTS_MAIN[1],
            mode="act",
        ),
        _assistant(
            "m-main-08",
            _ms(2026, 10, 25, 9, 2, 30),
            [
                _text_block("Continuing with the bounded digest."),
                _tool_use(
                    "editor",
                    {"command": "str_replace", "path": EDITOR_ABS},
                    "call-edit-2",
                ),
            ],
        ),
        _tool_result(
            "m-main-09",
            _ms(2026, 10, 25, 9, 2, 31),
            "call-edit-2",
            "editor",
            "Edited %s" % EDITOR_ABS,
        ),
        _user("m-main-10", _ms(2026, 10, 25, 9, 3, 0), CUTOFF_TEXT),
        _user("m-main-11", _ms(2026, 10, 25, 9, 3, 1), TEAM_UPDATE_TEXT),
        _prompt("m-main-12", _ms(2026, 10, 25, 9, 4, 0), PROMPTS_MAIN[2]),
        _assistant(
            "m-main-13",
            _ms(2026, 10, 25, 9, 4, 30),
            "The digest now stays bounded. cline-deep-only-needle",
        ),
        _prompt("m-main-14", _ms(2026, 10, 25, 9, 5, 0), PROMPTS_MAIN[3]),
        _assistant(
            "m-main-15",
            _ms(2026, 10, 25, 9, 5, 30),
            [
                _text_block("Done."),
                _tool_use(
                    "editor",
                    {"command": "str_replace", "path": EDITOR_REL},
                    "call-edit-3",
                ),
            ],
        ),
        _tool_result(
            "m-main-16",
            _ms(2026, 10, 25, 9, 5, 31),
            "call-edit-3",
            "editor",
            "Edited %s" % EDITOR_REL,
        ),
    ]


def _aux_messages() -> Any:
    return [
        _prompt("m-aux-01", _ms(2026, 10, 26, 8, 0, 0), PROMPTS_AUX[0]),
        _assistant(
            "m-aux-02",
            _ms(2026, 10, 26, 8, 0, 30),
            "Drafting the migration notes.",
            model=MODEL_AUX,
        ),
        _prompt("m-aux-03", _ms(2026, 10, 26, 8, 30, 0), PROMPTS_AUX[1]),
    ]


def _compact_messages() -> Any:
    return [
        _prompt("m-cmp-01", _ms(2026, 10, 24, 10, 0, 0), PROMPT_COMPACT_EARLY),
        _assistant(
            "m-cmp-02", _ms(2026, 10, 24, 10, 5, 0), "Planning the migration."
        ),
        _user(
            "m-cmp-03",
            _ms(2026, 10, 24, 10, 30, 0),
            COMPACT_EARLY_MESSAGE,
        ),
        _prompt(
            "m-cmp-04", _ms(2026, 10, 24, 11, 0, 0), PROMPT_COMPACT_RESUME
        ),
        _assistant("m-cmp-05", _ms(2026, 10, 24, 11, 5, 0), "Resuming."),
    ]


def _plain_messages() -> Any:
    return [
        _prompt("m-pln-01", _ms(2026, 10, 23, 8, 0, 0), PROMPT_PLAIN),
        _assistant(
            "m-pln-02", _ms(2026, 10, 23, 8, 5, 0), "Investigating the drift."
        ),
    ]


def _subagent_messages() -> Any:
    return [
        _prompt("m-sub-01", _ms(2026, 10, 25, 9, 6, 0), PROMPT_SUBAGENT),
        _assistant(
            "m-sub-02", _ms(2026, 10, 25, 9, 6, 30), "Lint pass complete."
        ),
    ]


def _write_session(
    root: Path,
    session_id: str,
    messages: Any,
    updated_at: str,
    meta: Optional[Dict[str, Any]] = None,
    compaction: Optional[Dict[str, Any]] = None,
) -> Path:
    session_dir = root / session_id
    messages_path = session_dir / (session_id + ".messages.json")
    _write_json(
        messages_path,
        _messages_document(messages, session_id, updated_at),
    )
    if meta is not None:
        _write_json(session_dir / (session_id + ".json"), meta)
    if compaction is not None:
        _write_json(
            session_dir / (session_id + ".compaction.json"), compaction
        )
    return messages_path


def build_cline_home(home: Path) -> Path:
    """Create a synthetic ``~/.cline`` store under ``home``."""

    home.mkdir(parents=True, exist_ok=True)
    root = home / "data" / "sessions"

    _write_session(
        root,
        SESSION_MAIN,
        _main_messages(),
        "2026-10-25T09:05:31.000Z",
        meta=_meta(
            SESSION_MAIN,
            source="cli",
            started_at="2026-10-25T09:00:05.000Z",
            ended_at="2026-10-25T10:30:00.000Z",
            cwd=PROJECT_ALPHA,
            model=MODEL_MAIN,
            branch=BRANCH_MAIN,
            version=VERSION_MAIN,
            prompt=PROMPTS_MAIN[0],
            title=TITLE_MAIN,
            messages_path=root
            / SESSION_MAIN
            / (SESSION_MAIN + ".messages.json"),
        ),
    )

    _write_session(
        root,
        SESSION_AUX,
        _aux_messages(),
        "2026-10-26T08:30:00.000Z",
        meta=_meta(
            SESSION_AUX,
            source="desktop",
            started_at="2026-10-26T08:00:00.000Z",
            ended_at="2026-10-26T09:00:00.000Z",
            cwd=PROJECT_AUX,
            model=MODEL_AUX,
            branch=BRANCH_AUX,
            version=VERSION_AUX,
            prompt=PROMPTS_AUX[0],
            messages_path=root
            / SESSION_AUX
            / (SESSION_AUX + ".messages.json"),
        ),
    )

    _write_session(
        root,
        SESSION_COMPACT,
        _compact_messages(),
        "2026-10-24T11:05:00.000Z",
        meta=_meta(
            SESSION_COMPACT,
            source="desktop",
            started_at="2026-10-24T10:00:00.000Z",
            ended_at="2026-10-24T12:00:00.000Z",
            cwd=PROJECT_GAMMA,
            model=MODEL_MAIN,
            branch="",
            version=VERSION_COMPACT,
            prompt=PROMPT_COMPACT_EARLY,
            title=TITLE_COMPACT,
            messages_path=root
            / SESSION_COMPACT
            / (SESSION_COMPACT + ".messages.json"),
        ),
        compaction={
            "version": 1,
            "updated_at": "2026-10-24T12:00:00.000Z",
            "conversation_id": SESSION_COMPACT,
            "source_message_count": 99,
            "source_prefix_hash": "sha256:synthetic",
            "source_last_message_key": "id:m-cmp-05",
            "messages": [
                _user(
                    "m-cmp-summary",
                    _ms(2026, 10, 24, 11, 30, 0),
                    COMPACT_SUMMARY,
                )
            ],
        },
    )

    # A session without metadata: everything falls back to the transcript.
    _write_session(
        root,
        SESSION_PLAIN,
        _plain_messages(),
        "2026-10-23T10:00:00.000Z",
    )

    # A subagent transcript in the parent session directory must never be
    # listed, searched, or shown as a session.
    subagent_path = root / SESSION_MAIN / (SUBAGENT_STEM + ".messages.json")
    _write_json(
        subagent_path,
        _messages_document(
            _subagent_messages(),
            SUBAGENT_ID,
            "2026-10-25T09:06:30.000Z",
            agent="teammate",
            origin={
                "source": "cli",
                "mode": "team",
                "sessionId": SUBAGENT_ID,
                "parentThreadId": SESSION_MAIN,
                "subagent": "lint-style",
                "version": VERSION_MAIN,
            },
        ),
    )

    return home
