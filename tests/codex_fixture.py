"""Build a synthetic ChatGPT Codex store for tests.

The layout mirrors ``~/.codex``: rollout JSONL segments under
``sessions/<YYYY>/<MM>/<DD>/``, archived rollouts under
``archived_sessions/``, and thread titles in ``session_index.jsonl``. A
resumed thread is split into an older root segment and a newer segment whose
``session_meta.history_base`` points back at the root with an exclusive
ordinal cap, so the fixture can prove that abandoned tail records are not
counted twice. Compressed rollouts are only produced when a zstd backend is
available. Every identifier, path, and prompt is invented.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:  # Python 3.14+
    from compression import zstd as _zstd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised on older interpreters
    _zstd = None

HAS_ZSTD = _zstd is not None or shutil.which("zstd") is not None

SESSION_MAIN = "c0de0001-1111-4a1b-8c1d-111111111111"
SESSION_RESUMED = "c0de0002-2222-4b2c-9d2e-222222222222"
SEGMENT_RESUMED = "c0de0003-3333-4c3d-9e3f-333333333333"
SESSION_PLAIN = "c0de0004-4444-4d4e-8f4a-444444444444"
SESSION_SUBAGENT = "c0de0005-5555-4e5f-9a5b-555555555555"
SESSION_ARCHIVED = "c0de0006-6666-4f6a-8b6c-666666666666"
SESSION_ZSTD = "c0de0007-7777-4a7b-9c7d-777777777777"

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_RESUME = "/Users/example/project-resume"
PROJECT_GAMMA = "/Users/example/project-gamma"
PROJECT_BETA = "/Users/example/project-beta"

INDEX_TITLE_MAIN = "Refactor the handoff digest for the CLI"
INDEX_TITLE_ARCHIVED = "Archived rollout notes"

COMPACT_SUMMARY = (
    "Summary of the conversation so far:\n"
    "The conversation is between an AI agent and a user.\n"
    "A previous turn asked to bound the handoff digest."
)
RESUMED_COMPACT_SUMMARY = "Summary of the earlier rollout: keep the digest bounded."

PROMPTS_MAIN = (
    "Please refactor the handoff digest so the CLI stays bounded. main-only-needle",
    "继续",
    "Ship the compact summary fallback.",
    "Tighten the digest tests.",
    "Fix the hover state in the preview.",
    "Check the preview layout.",
)
PROMPT_PLAIN = "Investigate the migration drift in project gamma."
PROMPT_ARCHIVED = "The archived-needle lives here."
PROMPT_SUBAGENT = "Subagent scratch work. subagent-only-needle."
PROMPT_ZSTD = "Compressed rollout survives decompression."

PROMPTS_RESUMED = (
    "Draft the rollout resume plan.",
    "继续",
    "Resume from the compacted state.",
)
PROMPT_ABANDONED = "Abandoned rewrite attempt."
PROMPT_ABANDONED_RESPONSE = "Abandoned response."
PROMPT_RESUMED_RESPONSE = "Resumed with the compacted summary."

NEEDLE_TOOL_OUTPUT = "tool-output-needle"
NEEDLE_DEEP_ONLY = "deep-only-needle"
NEEDLE_ARCHIVED = "archived-needle"
NEEDLE_SUBAGENT = "subagent-only-needle"
NEEDLE_ZSTD = "zstd-only-needle"
NEEDLE_MAIN = "main-only-needle"

MODEL_MAIN = "synthetic-model-1"
MODEL_RESUMED = "synthetic-model-2"
VERSION_MAIN = "0.0.1-synthetic"
VERSION_PLAIN = "0.0.2-synthetic"


def _ts(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> str:
    return (
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _epoch_ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp()
        * 1000
    )


def _record(record_type: str, timestamp: str, ordinal: int, **fields: Any) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "timestamp": timestamp,
        "type": record_type,
        "ordinal": ordinal,
    }
    record.update(fields)
    return record


def _meta(
    session_id: str,
    timestamp: str,
    ordinal: int,
    cwd: str,
    originator: str,
    source: Any,
    version: str,
    branch: Optional[str] = None,
    history_base: Optional[Dict[str, Any]] = None,
    thread_source: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": session_id,
        "session_id": session_id,
        "timestamp": timestamp,
        "cwd": cwd,
        "originator": originator,
        "cli_version": version,
        "source": source,
    }
    if branch is not None:
        payload["git"] = {
            "branch": branch,
            "commit_hash": "0000000000000000000000000000000000000000",
            "repository_url": "https://example.invalid/example/repo",
        }
    if history_base is not None:
        payload["history_base"] = history_base
    if thread_source is not None:
        payload["thread_source"] = thread_source
    return _record("session_meta", timestamp, ordinal, payload=payload)


def _turn_context(
    timestamp: str, ordinal: int, cwd: str, model: str
) -> Dict[str, Any]:
    return _record(
        "turn_context",
        timestamp,
        ordinal,
        payload={"cwd": cwd, "model": model, "effort": "medium"},
    )


def _user(
    timestamp: str,
    ordinal: int,
    text: str,
    kinds: Optional[List[str]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": text}],
    }
    if kinds is not None:
        payload["internal_chat_message_metadata_passthrough"] = {
            "content_item_kinds": kinds
        }
    return _record("response_item", timestamp, ordinal, payload=payload)


def _assistant(timestamp: str, ordinal: int, text: str) -> Dict[str, Any]:
    return _record(
        "response_item",
        timestamp,
        ordinal,
        payload={
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        },
    )


def _reasoning(timestamp: str, ordinal: int) -> Dict[str, Any]:
    return _record(
        "response_item",
        timestamp,
        ordinal,
        payload={
            "type": "reasoning",
            "summary": [],
            "content": [{"type": "reasoning_text", "text": "Synthetic reasoning."}],
        },
    )


def _function_call(
    timestamp: str, ordinal: int, name: str, arguments: Dict[str, Any]
) -> Dict[str, Any]:
    return _record(
        "response_item",
        timestamp,
        ordinal,
        payload={
            "type": "function_call",
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
            "call_id": "call_%d" % ordinal,
        },
    )


def _function_output(
    timestamp: str, ordinal: int, text: str
) -> Dict[str, Any]:
    return _record(
        "response_item",
        timestamp,
        ordinal,
        payload={
            "type": "function_call_output",
            "call_id": "call_%d" % (ordinal - 1),
            "output": text,
        },
    )


def _custom_tool_call(
    timestamp: str, ordinal: int, name: str, input_text: str
) -> Dict[str, Any]:
    return _record(
        "response_item",
        timestamp,
        ordinal,
        payload={
            "type": "custom_tool_call",
            "name": name,
            "input": input_text,
            "call_id": "call_%d" % ordinal,
        },
    )


def _custom_tool_output(timestamp: str, ordinal: int) -> Dict[str, Any]:
    return _record(
        "response_item",
        timestamp,
        ordinal,
        payload={
            "type": "custom_tool_call_output",
            "call_id": "call_%d" % (ordinal - 1),
            "output": "synthetic patch applied",
        },
    )


def _event_msg(timestamp: str, ordinal: int, kind: str, **fields: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"type": kind}
    payload.update(fields)
    return _record("event_msg", timestamp, ordinal, payload=payload)


def _compacted(timestamp: str, ordinal: int, message: str) -> Dict[str, Any]:
    return _record("compacted", timestamp, ordinal, payload={"message": message})


def _token_usage(timestamp: str, ordinal: int) -> Dict[str, Any]:
    return _record(
        "token_usage_record",
        timestamp,
        ordinal,
        payload={"input_tokens": 10, "output_tokens": 5},
    )


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _append_raw(path: Path, raw: bytes) -> None:
    with path.open("ab") as handle:
        handle.write(raw)


def _base_record(
    session_id: str,
    timestamp: str,
    ordinal: int,
    cwd: str,
    originator: str,
    source: Any,
    version: str,
    branch: Optional[str] = None,
    history_base: Optional[Dict[str, Any]] = None,
    thread_source: Optional[str] = None,
) -> Dict[str, Any]:
    return _meta(
        session_id,
        timestamp,
        ordinal,
        cwd,
        originator,
        source,
        version,
        branch=branch,
        history_base=history_base,
        thread_source=thread_source,
    )


def _compress(path: Path) -> bool:
    target = path.with_suffix(".jsonl.zst")
    if _zstd is not None:
        data = path.read_bytes()
        with _zstd.ZstdFile(target, "wb") as handle:
            handle.write(data)
        path.unlink()
        return True
    executable = shutil.which("zstd")
    if not executable:
        return False
    subprocess.run(
        [executable, "-q", "-f", "--rm", "--", str(path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return target.is_file()


def _rollout_path(root: Path, stamp: tuple, name: str) -> Path:
    year, month, day, hour, minute, second = stamp
    return (
        root
        / ("%04d" % year)
        / ("%02d" % month)
        / ("%02d" % day)
        / (
            "rollout-%04d-%02d-%02dT%02d-%02d-%02d-%s.jsonl"
            % (year, month, day, hour, minute, second, name)
        )
    )


def build_codex_home(home: Path) -> Path:
    """Create ``sessions/``, ``archived_sessions/``, and the index under ``home``."""

    home.mkdir(parents=True, exist_ok=True)
    sessions = home / "sessions"
    archived = home / "archived_sessions"

    # --- main session: prompts, tools, patches, compaction, injected wrappers ---
    main_path = _rollout_path(
        sessions, (2026, 10, 20, 9, 10, 5), SESSION_MAIN
    )
    main_records = [
        _base_record(
            SESSION_MAIN,
            _ts(2026, 10, 20, 9, 10),
            0,
            PROJECT_ALPHA,
            "Codex Desktop",
            "desktop",
            VERSION_MAIN,
            branch="feature/handoff",
        ),
        _turn_context(_ts(2026, 10, 20, 9, 10), 1, PROJECT_ALPHA, MODEL_MAIN),
        _user(
            _ts(2026, 10, 20, 9, 10),
            2,
            "# AGENTS.md instructions for /Users/example/project-alpha\n\n"
            "<INSTRUCTIONS>\nPrefer small diffs.\n</INSTRUCTIONS>",
        ),
        _user(
            _ts(2026, 10, 20, 9, 10),
            3,
            "<environment_context>\n  <cwd>%s</cwd>\n</environment_context>"
            % PROJECT_ALPHA,
        ),
        _user(
            _ts(2026, 10, 20, 9, 11),
            4,
            PROMPTS_MAIN[0],
            kinds=["user.text"],
        ),
        _event_msg(
            _ts(2026, 10, 20, 9, 11),
            5,
            "user_message",
            message=PROMPTS_MAIN[0],
        ),
        _assistant(_ts(2026, 10, 20, 9, 12), 6, "I'll read the parser first."),
        _function_call(
            _ts(2026, 10, 20, 9, 12),
            7,
            "shell",
            {"cmd": "sed -n '1,120p' src/handoff.ts", "workdir": PROJECT_ALPHA},
        ),
        _function_output(
            _ts(2026, 10, 20, 9, 13),
            8,
            "Parsed the handoff module. %s" % NEEDLE_TOOL_OUTPUT,
        ),
        _custom_tool_call(
            _ts(2026, 10, 20, 9, 14),
            9,
            "apply_patch",
            "*** Begin Patch\n"
            "*** Update File: src/handoff.ts\n"
            "@@\n"
            "-const limit = 100;\n"
            "+const limit = 200;\n"
            "*** Add File: docs/handoff.md\n"
            "+# Handoff\n"
            "*** End Patch\n",
        ),
        _custom_tool_output(_ts(2026, 10, 20, 9, 14), 10),
        _user(_ts(2026, 10, 20, 9, 30), 11, PROMPTS_MAIN[1]),
        _turn_context(_ts(2026, 10, 20, 9, 31), 12, PROJECT_ALPHA, MODEL_MAIN),
        _user(_ts(2026, 10, 20, 9, 45), 13, PROMPTS_MAIN[2]),
        _compacted(_ts(2026, 10, 20, 10, 0), 14, COMPACT_SUMMARY),
        _user(
            _ts(2026, 10, 20, 10, 2),
            15,
            "# Files mentioned by the user:\n\n"
            "## src/handoff.ts:1-40\n\n"
            "```ts\nconst limit = 200;\n```\n\n"
            "## My request for Codex:\n%s" % PROMPTS_MAIN[3],
        ),
        _custom_tool_call(
            _ts(2026, 10, 20, 10, 3),
            16,
            "apply_patch",
            "*** Begin Patch\n"
            "*** Update File: src/handoff.ts\n"
            "@@\n"
            "-const limit = 200;\n"
            "+const limit = 250;\n"
            "*** End Patch\n",
        ),
        _custom_tool_output(_ts(2026, 10, 20, 10, 3), 17),
        _user(
            _ts(2026, 10, 20, 10, 4),
            18,
            "# Browser comments:\n\n"
            "## localhost:3000/preview\n"
            "Comment:\n%s" % PROMPTS_MAIN[4],
        ),
        _user(
            _ts(2026, 10, 20, 10, 5),
            19,
            '<in-app-browser-context url="http://localhost:3000/preview">\n'
            "Visible text only.\n"
            "</in-app-browser-context>\n%s" % PROMPTS_MAIN[5],
        ),
        _user(
            _ts(2026, 10, 20, 10, 5),
            20,
            "<task-notification>\n<task-id>AB12CD</task-id>\n"
            "<status>completed</status>\n</task-notification>",
        ),
        _user(
            _ts(2026, 10, 20, 10, 6),
            21,
            "This must not become a prompt.",
            kinds=["context.environment"],
        ),
        _user(_ts(2026, 10, 20, 10, 6), 22, "/review"),
        _assistant(_ts(2026, 10, 20, 10, 7), 23, "All bounded and ready."),
        _reasoning(_ts(2026, 10, 20, 10, 7), 24),
        _token_usage(_ts(2026, 10, 20, 10, 8), 25),
    ]
    _write_jsonl(main_path, main_records)
    _append_raw(
        main_path,
        b'{"timestamp": "2026-10-20T10:09:00Z", "type": "response_item", '
        b'"ordinal": 26, "payload": {"type": "message", "role": "user", '
        b'"content": [{"type": "input_text", "text": "truncated prompt',
    )

    # --- resumed thread: older root segment plus newer segment --------------
    resumed_root = _rollout_path(
        sessions, (2026, 9, 28, 17, 36, 10), SESSION_RESUMED
    )
    resumed_base_records = [
        _base_record(
            SESSION_RESUMED,
            _ts(2026, 9, 28, 17, 36),
            0,
            PROJECT_RESUME,
            "codex-tui",
            "cli",
            VERSION_MAIN,
            branch="main",
        ),
        _turn_context(
            _ts(2026, 9, 28, 17, 36), 1, PROJECT_RESUME, MODEL_MAIN
        ),
        _user(_ts(2026, 9, 28, 17, 40), 2, PROMPTS_RESUMED[0]),
        _user(_ts(2026, 9, 28, 17, 41), 3, PROMPTS_RESUMED[1]),
        _assistant(_ts(2026, 9, 28, 17, 42), 4, "Drafted the plan."),
        _user(_ts(2026, 9, 28, 17, 50), 5, PROMPT_ABANDONED),
        _assistant(_ts(2026, 9, 28, 17, 51), 6, PROMPT_ABANDONED_RESPONSE),
    ]
    _write_jsonl(resumed_root, resumed_base_records)
    resumed_byte_cap = sum(
        len((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
        for record in resumed_base_records
        if record["ordinal"] < 4
    )
    _write_jsonl(
        _rollout_path(
            sessions,
            (2026, 10, 25, 11, 0, 0),
            "%s_%s" % (SESSION_RESUMED, SEGMENT_RESUMED),
        ),
        [
            _base_record(
                SESSION_RESUMED,
                _ts(2026, 10, 25, 11, 0),
                4,
                PROJECT_RESUME,
                "codex-web-gui",
                "vscode",
                VERSION_MAIN,
                branch="dev",
                history_base={
                    "thread_id": SESSION_RESUMED,
                    "end_ordinal_exclusive": 4,
                    "end_byte_offset": resumed_byte_cap,
                },
            ),
            _turn_context(
                _ts(2026, 10, 25, 11, 0), 5, PROJECT_RESUME, MODEL_RESUMED
            ),
            _user(_ts(2026, 10, 25, 11, 5), 6, PROMPTS_RESUMED[2]),
            _compacted(_ts(2026, 10, 25, 11, 8), 7, RESUMED_COMPACT_SUMMARY),
            _assistant(_ts(2026, 10, 25, 11, 12), 8, PROMPT_RESUMED_RESPONSE),
        ],
    )

    # --- plain session: no tools, no compaction, deep-only needle -----------
    _write_jsonl(
        _rollout_path(sessions, (2026, 10, 27, 15, 0, 0), SESSION_PLAIN),
        [
            _base_record(
                SESSION_PLAIN,
                _ts(2026, 10, 27, 15, 0),
                0,
                PROJECT_GAMMA,
                "codex-tui",
                "cli",
                VERSION_PLAIN,
            ),
            _turn_context(_ts(2026, 10, 27, 15, 0), 1, PROJECT_GAMMA, MODEL_MAIN),
            _user(_ts(2026, 10, 27, 15, 5), 2, PROMPT_PLAIN),
            _assistant(
                _ts(2026, 10, 27, 15, 20),
                3,
                "Checking the migration ledger. %s found here." % NEEDLE_DEEP_ONLY,
            ),
            _assistant(_ts(2026, 10, 27, 15, 30), 4, "API error: quota exceeded."),
        ],
    )

    # --- subagent thread: must never be listed ------------------------------
    _write_jsonl(
        _rollout_path(sessions, (2026, 10, 24, 8, 0, 0), SESSION_SUBAGENT),
        [
            _base_record(
                SESSION_SUBAGENT,
                _ts(2026, 10, 24, 8, 0),
                0,
                PROJECT_BETA,
                "codex-tui",
                {"subagent": {"parent_thread_id": SESSION_MAIN}},
                VERSION_PLAIN,
                thread_source="subagent",
            ),
            _turn_context(_ts(2026, 10, 24, 8, 0), 1, PROJECT_BETA, MODEL_MAIN),
            _user(_ts(2026, 10, 24, 8, 1), 2, PROMPT_SUBAGENT),
            _assistant(_ts(2026, 10, 24, 8, 2), 3, "Subagent output."),
        ],
    )

    # --- archived thread ----------------------------------------------------
    _write_jsonl(
        _rollout_path(archived, (2026, 10, 21, 9, 30, 0), SESSION_ARCHIVED),
        [
            _base_record(
                SESSION_ARCHIVED,
                _ts(2026, 10, 21, 9, 30),
                0,
                PROJECT_BETA,
                "codex-tui",
                "cli",
                VERSION_MAIN,
                branch="release/1.0",
            ),
            _turn_context(_ts(2026, 10, 21, 9, 30), 1, PROJECT_BETA, MODEL_MAIN),
            _user(_ts(2026, 10, 21, 9, 35), 2, PROMPT_ARCHIVED),
            _assistant(_ts(2026, 10, 21, 10, 5), 3, "Archived work."),
        ],
    )

    # --- thread titles ------------------------------------------------------
    index_lines = [
        {
            "id": SESSION_MAIN,
            "thread_name": INDEX_TITLE_MAIN,
            "updated_at": _epoch_ms(2026, 10, 20, 10, 8),
        },
        {
            "id": SESSION_ARCHIVED,
            "thread_name": INDEX_TITLE_ARCHIVED,
            "updated_at": _epoch_ms(2026, 10, 21, 10, 5),
        },
        {
            "id": SESSION_SUBAGENT,
            "thread_name": "Subagent task",
            "updated_at": _epoch_ms(2026, 10, 24, 8, 2),
        },
        {
            "id": SESSION_PLAIN,
            "thread_name": "",
            "updated_at": _epoch_ms(2026, 10, 27, 15, 30),
        },
        {
            "id": "c0de00ff-ffff-4fff-8fff-ffffffffffff",
            "thread_name": "Stale index entry that has no rollout",
            "updated_at": _epoch_ms(2026, 10, 1, 0, 0),
        },
    ]
    with (home / "session_index.jsonl").open("w", encoding="utf-8") as handle:
        for line in index_lines:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    # --- legacy history file: never a session -------------------------------
    with (home / "history.jsonl").open("w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "session_id": SESSION_MAIN,
                    "ts": _epoch_ms(2026, 10, 20, 9, 11),
                    "text": "Legacy history entry that must never be listed.",
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    stamps = {
        main_path: _ts(2026, 10, 20, 10, 9),
        resumed_root: _ts(2026, 9, 28, 17, 51),
        _rollout_path(
            sessions,
            (2026, 10, 25, 11, 0, 0),
            "%s_%s" % (SESSION_RESUMED, SEGMENT_RESUMED),
        ): _ts(2026, 10, 25, 11, 12),
        _rollout_path(sessions, (2026, 10, 27, 15, 0, 0), SESSION_PLAIN): _ts(
            2026, 10, 27, 15, 30
        ),
        _rollout_path(sessions, (2026, 10, 24, 8, 0, 0), SESSION_SUBAGENT): _ts(
            2026, 10, 24, 8, 2
        ),
        _rollout_path(archived, (2026, 10, 21, 9, 30, 0), SESSION_ARCHIVED): _ts(
            2026, 10, 21, 10, 5
        ),
    }
    for path, stamp in stamps.items():
        seconds = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        ).timestamp()
        os.utime(path, (seconds, seconds))
    return home


def build_codex_zstd_home(home: Path) -> Path:
    """Create a one-session store whose rollout is zstd-compressed when possible."""

    home.mkdir(parents=True, exist_ok=True)
    path = _rollout_path(
        home / "sessions", (2026, 10, 23, 9, 0, 0), SESSION_ZSTD
    )
    _write_jsonl(
        path,
        [
            _base_record(
                SESSION_ZSTD,
                _ts(2026, 10, 23, 9, 0),
                0,
                PROJECT_BETA,
                "Codex Desktop",
                "desktop",
                VERSION_MAIN,
                branch="dev",
            ),
            _turn_context(_ts(2026, 10, 23, 9, 0), 1, PROJECT_BETA, MODEL_MAIN),
            _user(_ts(2026, 10, 23, 9, 1), 2, PROMPT_ZSTD),
            _assistant(
                _ts(2026, 10, 23, 9, 5),
                3,
                "Decompressed without writing. %s" % NEEDLE_ZSTD,
            ),
        ],
    )
    _compress(path)
    stamp = datetime(2026, 10, 23, 9, 5, tzinfo=timezone.utc).timestamp()
    for candidate in (path, path.with_suffix(".jsonl.zst")):
        if candidate.is_file():
            os.utime(candidate, (stamp, stamp))
    return home
