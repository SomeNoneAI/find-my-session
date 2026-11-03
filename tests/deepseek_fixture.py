"""Build a synthetic DeepSeek Harness (``dsh``) store for tests.

The layout mirrors ``~/.dsh``: one zstd-compressed JSONL event log per session
under ``sessions/<encoded-cwd>/session-<uuid>/session[.vN].jsonl.zstd`` and
archive state in ``storages/workspace.json``. The fixture covers an active
session with tools, todos, and a compaction; an archived session; a legacy
unversioned transcript; a directory with two schema versions; a metadata-only
session; and a delegated child session that must never be listed. Every
identifier, path, and prompt is invented.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # Python 3.14+
    from compression import zstd as _zstd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised on older interpreters
    _zstd = None

HAS_ZSTD = _zstd is not None or shutil.which("zstd") is not None

SESSION_MAIN = "d5ee0001-1111-4a1b-8c1d-111111111111"
SESSION_ARCHIVED = "d5ee0002-2222-4b2c-9d2e-222222222222"
SESSION_PLAIN = "d5ee0003-3333-4c3d-9e3f-333333333333"
SESSION_MULTI = "d5ee0004-4444-4d4e-8f4a-444444444444"
SESSION_SUBAGENT = "d5ee0005-5555-4e5f-9a5b-555555555555"
SESSION_EMPTY = "d5ee0006-6666-4f6a-8b6c-666666666666"

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_BETA = "/Users/example/project-beta"
PROJECT_GAMMA = "/Users/example/project-gamma"
PROJECT_ALPHA_PACKAGES = PROJECT_ALPHA + "/packages"

GROUP_ALPHA = "--Users-example-project-alpha--"
GROUP_BETA = "--Users-example-project-beta--"
GROUP_GAMMA = "--Users-example-project-gamma--"

MODEL_MAIN = "example-deepseek-model-1"
MODEL_ALT = "example-deepseek-model-2"
MODEL_PLAIN = "example-deepseek-model-3"

TITLE_MAIN = "Bounded handoff digest refactor"
TITLE_ARCHIVED = "Archived rollout notes"
TITLE_MULTI = "Resume the bounded digest."

PROMPTS_MAIN = (
    "Please refactor the handoff digest so the CLI stays bounded. main-only-needle",
    "继续",
    "Ship the compact summary fallback.",
    "Tighten the digest tests.",
)
PROMPT_ARCHIVED = "The archived-needle lives here."
PROMPT_PLAIN = "Investigate the migration drift in project gamma."
PROMPT_MULTI_ABANDONED = "Abandoned rewrite attempt."
PROMPT_MULTI = "Resume the bounded digest."
PROMPT_SUBAGENT = "Subagent scratch work. subagent-only-needle."
PROMPT_IMAGE_ONLY = "This image-only message must not become a prompt."

COMPACT_SUMMARY = (
    "Summary of the conversation so far:\n"
    "The digest was bounded and prompt paging was verified."
)

TODOS_EARLY = (
    ("Refactor the digest", "completed"),
    ("Add prompt paging", "pending"),
    ("Update docs", "in_progress"),
)
TODOS_LATEST = (
    ("Refactor the digest", "completed"),
    ("Add prompt paging", "completed"),
    ("Update the handoff docs", "pending"),
)

NEEDLE_MAIN = "main-only-needle"
NEEDLE_TOOL_OUTPUT = "tool-output-needle"
NEEDLE_DEEP_ONLY = "deep-only-needle"
NEEDLE_ARCHIVED = "archived-needle"
NEEDLE_SUBAGENT = "subagent-only-needle"


def _ms(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> int:
    return int(
        datetime(
            year, month, day, hour, minute, second, tzinfo=timezone.utc
        ).timestamp()
        * 1000
    )


def _record(
    record_type: str, seq: int, timestamp: int, data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    return {
        "type": record_type,
        "seq": seq,
        "time": timestamp,
        "data": data or {},
    }


def _header(
    session_id: str,
    cwd: str,
    timestamp: int,
    version: int = 4,
    depth: int = 0,
) -> Dict[str, Any]:
    prefix = "session-" if depth == 0 else ""
    return {
        "type": "session",
        "version": version,
        "id": prefix + session_id,
        "createdAt": timestamp,
        "cwd": cwd,
        "isSeeded": False,
        "delegationDepth": depth,
        "agentPreset": "standard",
    }


def _request_header(seq: int, timestamp: int, model: str) -> Dict[str, Any]:
    return _record(
        "request/header",
        seq,
        timestamp,
        {
            "header": {
                "config": {
                    "provider": "example",
                    "model": model,
                    "reasoningEffort": "medium",
                },
                "tools": [],
            },
            "reason": "turn",
        },
    )


def _user(
    seq: int,
    timestamp: int,
    text: str,
    source: str = "user",
    message_id: Optional[str] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "source": {"kind": source},
        "role": "user",
        "id": message_id or "msg-%d" % seq,
    }
    if source == "user":
        data["source"].update(
            {"rpcId": "rpc-%d" % seq, "clientTimeZone": "UTC"}
        )
    return _record("user/message", seq, timestamp, data)


def _image_user(seq: int, timestamp: int) -> Dict[str, Any]:
    return _record(
        "user/message",
        seq,
        timestamp,
        {
            "content": [
                {"type": "image", "attachment": "synthetic-attachment.png"}
            ],
            "source": {"kind": "user", "rpcId": "rpc-%d" % seq},
            "role": "user",
            "id": "msg-image-%d" % seq,
        },
    )


def _inbox(seq: int, timestamp: int, text: str, message_id: str) -> Dict[str, Any]:
    return _record(
        "agent/inbox/spliced",
        seq,
        timestamp,
        {
            "target": "next-turn",
            "start": 0,
            "inserted": [
                {
                    "content": [{"type": "text", "text": text}],
                    "source": {"kind": "user", "rpcId": "rpc-%d" % seq},
                    "role": "user",
                    "id": message_id,
                }
            ],
        },
    )


def _assistant(
    seq: int,
    timestamp: int,
    turn: int,
    step: int,
    texts: Iterable[str] = (),
    reasoning: Iterable[str] = (),
) -> Dict[str, Any]:
    content: List[Dict[str, Any]] = []
    for text in reasoning:
        content.append({"type": "reasoning", "text": text})
    for text in texts:
        content.append({"type": "text", "text": text})
    return _record(
        "assistant/message",
        seq,
        timestamp,
        {
            "turn": turn,
            "step": step,
            "message": {
                "role": "assistant",
                "content": content,
                "source": {
                    "kind": "provider",
                    "provider": "example",
                    "model": MODEL_MAIN,
                },
                "id": "asst-%d" % seq,
            },
            "usage": {
                "inputTokens": 10,
                "outputTokens": 5,
                "totalTokens": 15,
                "cacheReadTokens": 0,
            },
        },
    )


def _tool_call(
    seq: int,
    timestamp: int,
    turn: int,
    step: int,
    name: str,
    arguments: Dict[str, Any],
    call_id: str,
) -> Dict[str, Any]:
    return _record(
        "tool/call",
        seq,
        timestamp,
        {
            "turn": turn,
            "step": step,
            "callId": call_id,
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    )


def _tool_result(
    seq: int,
    timestamp: int,
    turn: int,
    step: int,
    call_id: str,
    text: str,
) -> Dict[str, Any]:
    return _record(
        "tool/result",
        seq,
        timestamp,
        {
            "turn": turn,
            "step": step,
            "message": {
                "role": "tool",
                "source": {"kind": "tool", "callId": call_id},
                "toolCallId": call_id,
                "content": [{"type": "text", "text": text}],
                "isError": False,
                "id": "result-%d" % seq,
            },
            "meta": {"cwd": PROJECT_ALPHA},
        },
    )


def _title(
    seq: int, timestamp: int, title: str, source: str = "provider"
) -> Dict[str, Any]:
    return _record(
        "session/title",
        seq,
        timestamp,
        {
            "title": title,
            "messageSeqs": [1],
            "source": {"kind": source},
        },
    )


def _todo_write(
    seq: int, timestamp: int, todos: Iterable[Tuple[str, str]]
) -> Dict[str, Any]:
    return _record(
        "todo/write",
        seq,
        timestamp,
        {
            "todos": [
                {"content": content, "status": status}
                for content, status in todos
            ]
        },
    )


def _compaction(seq: int, timestamp: int, text: str) -> Dict[str, Any]:
    return _record(
        "compaction/summary",
        seq,
        timestamp,
        {
            "compactionId": "compaction-1",
            "sourceCommandId": "command-1",
            "summary": [{"type": "text", "text": text}],
            "rawOutput": [{"type": "text", "text": text}],
            "llmStreamCall": False,
            "shadowedRange": {"start": 1, "end": seq - 1},
            "shadowedSeqs": [],
            "shadowedTokenCount": 10,
            "provider": "example",
            "model": MODEL_MAIN,
            "maxTokens": 100,
            "usage": {
                "inputTokens": 0,
                "outputTokens": 0,
                "totalTokens": 0,
                "cacheReadTokens": 0,
            },
        },
    )


def _compress(path: Path) -> Optional[Path]:
    target = path.with_name(path.name + ".zstd")
    data = path.read_bytes()
    if _zstd is not None:
        with _zstd.ZstdFile(target, "wb") as handle:
            handle.write(data)
        path.unlink()
        return target
    executable = shutil.which("zstd")
    if not executable:
        return None
    with target.open("wb") as handle:
        subprocess.run(
            [executable, "-q", "-c", "--", str(path)],
            check=True,
            stdout=handle,
            stderr=subprocess.DEVNULL,
        )
    path.unlink()
    return target


def decompress(path: Path) -> bytes:
    if _zstd is not None:
        with _zstd.ZstdFile(path, "rb") as handle:
            return handle.read()
    executable = shutil.which("zstd")
    if not executable:
        raise RuntimeError("zstd decoder unavailable")
    return subprocess.run(
        [executable, "-dc", "--quiet", "--", str(path)],
        check=True,
        capture_output=True,
    ).stdout


def _write_transcript(
    session_dir: Path,
    name: str,
    records: Iterable[Dict[str, Any]],
    mtime_ms: int,
) -> Path:
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / name
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    target = _compress(path) or path
    stamp = mtime_ms / 1000.0
    os.utime(target, (stamp, stamp))
    return target


def _main_records() -> List[Dict[str, Any]]:
    return [
        _header(SESSION_MAIN, PROJECT_ALPHA, _ms(2026, 10, 20, 9, 0), version=3),
        _record("permission/preset", 2, _ms(2026, 10, 20, 9, 0), {"preset": "workspace-write"}),
        _record("sandbox/mode", 3, _ms(2026, 10, 20, 9, 0), {"mode": "workspace-write"}),
        _record("approval/policy", 4, _ms(2026, 10, 20, 9, 0), {"policy": "ask"}),
        _request_header(5, _ms(2026, 10, 20, 9, 0), MODEL_MAIN),
        _user(
            6,
            _ms(2026, 10, 20, 9, 1),
            "Injected agent instructions that are not a prompt.",
            source="agent-instructions",
        ),
        _user(
            7,
            _ms(2026, 10, 20, 9, 1),
            "Injected runtime context that is not a prompt.",
            source="runtime-context",
        ),
        _user(8, _ms(2026, 10, 20, 9, 10), PROMPTS_MAIN[0], message_id="msg-main-1"),
        _title(9, _ms(2026, 10, 20, 9, 10), "Refactor the handoff digest", "fallback"),
        _record("turn/start", 10, _ms(2026, 10, 20, 9, 10), {"turn": 1}),
        _record("step/start", 11, _ms(2026, 10, 20, 9, 10), {"turn": 1, "step": 1}),
        _assistant(12, _ms(2026, 10, 20, 9, 11), 1, 1, texts=["I'll inspect the digest."]),
        _record(
            "request/context",
            13,
            _ms(2026, 10, 20, 9, 11),
            {"provider": "example", "model": MODEL_MAIN, "contextWindow": 100000},
        ),
        _tool_call(
            14,
            _ms(2026, 10, 20, 9, 12),
            1,
            1,
            "bash",
            {"command": "sed -n '1,40p' src/digest.py", "description": "Read the digest"},
            "call-bash-1",
        ),
        _record(
            "job/registered",
            15,
            _ms(2026, 10, 20, 9, 12),
            {"jobId": "job-1", "owner": "bash", "kind": "command", "label": "sed"},
        ),
        _record(
            "job/settled",
            16,
            _ms(2026, 10, 20, 9, 12),
            {"jobId": "job-1", "owner": "bash", "kind": "command", "label": "sed", "status": "done"},
        ),
        _tool_result(
            17,
            _ms(2026, 10, 20, 9, 13),
            1,
            1,
            "call-bash-1",
            "%s\nDigest module loaded." % NEEDLE_TOOL_OUTPUT,
        ),
        _assistant(
            18,
            _ms(2026, 10, 20, 9, 14),
            1,
            2,
            texts=["The digest is bounded; I'll split the edit."],
        ),
        _tool_call(
            19,
            _ms(2026, 10, 20, 9, 14),
            1,
            2,
            "edit",
            {
                "file_path": "src/digest.py",
                "old_string": "limit = 100",
                "new_string": "limit = 200",
            },
            "call-edit-1",
        ),
        _tool_result(20, _ms(2026, 10, 20, 9, 14), 1, 2, "call-edit-1", "edit applied"),
        _tool_call(
            21,
            _ms(2026, 10, 20, 9, 15),
            1,
            3,
            "edit",
            {
                "file_path": "src/digest.py",
                "old_string": "limit = 200",
                "new_string": "limit = 250",
            },
            "call-edit-2",
        ),
        _tool_result(22, _ms(2026, 10, 20, 9, 15), 1, 3, "call-edit-2", "edit applied"),
        _todo_write(23, _ms(2026, 10, 20, 9, 16), TODOS_EARLY),
        _assistant(24, _ms(2026, 10, 20, 9, 16), 1, 3, texts=["Digest bounded."]),
        _record("step/end", 25, _ms(2026, 10, 20, 9, 16), {"turn": 1, "step": 3}),
        _record("turn/end", 26, _ms(2026, 10, 20, 9, 17), {"turn": 1, "reason": {"kind": "stop"}}),
        _title(27, _ms(2026, 10, 20, 9, 20), TITLE_MAIN, "provider"),
        _user(28, _ms(2026, 10, 20, 9, 30), PROMPTS_MAIN[1], message_id="msg-main-2"),
        _assistant(29, _ms(2026, 10, 20, 9, 31), 2, 1, texts=["Continuing with paging."]),
        _user(
            30,
            _ms(2026, 10, 20, 9, 39),
            "Injected tool-job context that is not a prompt.",
            source="tool-jobs",
        ),
        _inbox(31, _ms(2026, 10, 20, 9, 40), PROMPTS_MAIN[2], "msg-main-3"),
        _user(32, _ms(2026, 10, 20, 9, 40), PROMPTS_MAIN[2], message_id="msg-main-3"),
        _compaction(33, _ms(2026, 10, 20, 9, 45), COMPACT_SUMMARY),
        _record(
            "compaction/prune",
            34,
            _ms(2026, 10, 20, 9, 45),
            {"shadowedRange": {"start": 1, "end": 32}, "shadowedSeqs": [], "shadowedTokenCount": 10},
        ),
        _image_user(35, _ms(2026, 10, 20, 9, 46)),
        _record(
            "system/message",
            36,
            _ms(2026, 10, 20, 9, 47),
            {
                "turn": 3,
                "step": 1,
                "message": {
                    "role": "system",
                    "content": [{"type": "text", "text": "Synthetic system note."}],
                    "source": {"kind": "system"},
                    "id": "sys-1",
                },
            },
        ),
        _record(
            "developer/message",
            37,
            _ms(2026, 10, 20, 9, 48),
            {
                "turn": 3,
                "step": 1,
                "message": {
                    "role": "developer",
                    "content": [{"type": "text", "text": "Synthetic developer note."}],
                    "source": {"kind": "developer"},
                    "id": "dev-1",
                },
                "headerSeq": 5,
            },
        ),
        _record(
            "subagent/descriptor",
            38,
            _ms(2026, 10, 20, 9, 49),
            {
                "version": 1,
                "mode": "sync",
                "provider": "example",
                "label": "Research",
                "agentProvider": "example",
                "agentModel": MODEL_MAIN,
                "agentReasoningEffort": "medium",
            },
        ),
        _user(39, _ms(2026, 10, 20, 9, 50), PROMPTS_MAIN[3], message_id="msg-main-4"),
        _assistant(40, _ms(2026, 10, 20, 9, 51), 3, 1, texts=["Tests tightened."]),
        _tool_call(
            41,
            _ms(2026, 10, 20, 9, 52),
            3,
            1,
            "write",
            {"file_path": "docs/handoff.md", "content": "# Handoff"},
            "call-write-1",
        ),
        _tool_result(42, _ms(2026, 10, 20, 9, 52), 3, 1, "call-write-1", "written"),
        _todo_write(43, _ms(2026, 10, 20, 9, 53), TODOS_LATEST),
        _record(
            "working-directory/change",
            44,
            _ms(2026, 10, 20, 10, 5),
            {"cwd": PROJECT_ALPHA_PACKAGES},
        ),
        _record(
            "model/selection",
            45,
            _ms(2026, 10, 20, 10, 6),
            {"provider": "example", "model": MODEL_ALT},
        ),
        _title(46, _ms(2026, 10, 20, 10, 8), TITLE_MAIN, "provider"),
        _record("turn/end", 47, _ms(2026, 10, 20, 10, 10), {"turn": 3, "reason": {"kind": "stop"}}),
    ]


def build_deepseek_home(home: Path) -> Path:
    """Create ``sessions/`` and ``storages/workspace.json`` under ``home``."""

    home.mkdir(parents=True, exist_ok=True)
    sessions = home / "sessions"

    main_dir = sessions / GROUP_ALPHA / ("session-" + SESSION_MAIN)
    _write_transcript(
        main_dir,
        "session.v3.jsonl",
        _main_records(),
        _ms(2026, 10, 20, 10, 10),
    )
    (main_dir / "session.lock").write_bytes(b"")

    _write_transcript(
        sessions / GROUP_BETA / ("session-" + SESSION_ARCHIVED),
        "session.v4.jsonl",
        [
            _header(SESSION_ARCHIVED, PROJECT_BETA, _ms(2026, 10, 21, 9, 30)),
            _request_header(2, _ms(2026, 10, 21, 9, 30), MODEL_MAIN),
            _title(3, _ms(2026, 10, 21, 9, 30), TITLE_ARCHIVED, "fallback"),
            _user(4, _ms(2026, 10, 21, 9, 35), PROMPT_ARCHIVED),
            _assistant(5, _ms(2026, 10, 21, 10, 5), 1, 1, texts=["Archived work."]),
            _record("turn/end", 6, _ms(2026, 10, 21, 10, 5), {"turn": 1, "reason": {"kind": "stop"}}),
        ],
        _ms(2026, 10, 21, 10, 5),
    )

    _write_transcript(
        sessions / GROUP_GAMMA / ("session-" + SESSION_PLAIN),
        "session.jsonl",
        [
            _header(SESSION_PLAIN, PROJECT_GAMMA, _ms(2026, 10, 27, 15, 0), version=1),
            _request_header(2, _ms(2026, 10, 27, 15, 0), MODEL_PLAIN),
            _user(3, _ms(2026, 10, 27, 15, 5), PROMPT_PLAIN),
            _assistant(
                4,
                _ms(2026, 10, 27, 15, 20),
                1,
                1,
                texts=["Checking the migration ledger. %s found here." % NEEDLE_DEEP_ONLY],
            ),
            _assistant(5, _ms(2026, 10, 27, 15, 30), 1, 2, texts=["API error: quota exceeded."]),
            _record("turn/end", 6, _ms(2026, 10, 27, 15, 30), {"turn": 1, "reason": {"kind": "error"}}),
        ],
        _ms(2026, 10, 27, 15, 30),
    )

    multi_dir = sessions / GROUP_ALPHA / ("session-" + SESSION_MULTI)
    _write_transcript(
        multi_dir,
        "session.v2.jsonl",
        [
            _header(SESSION_MULTI, PROJECT_BETA, _ms(2026, 10, 24, 9, 0), version=2),
            _request_header(2, _ms(2026, 10, 24, 9, 0), MODEL_MAIN),
            _user(3, _ms(2026, 10, 24, 9, 5), PROMPT_MULTI_ABANDONED),
            _assistant(4, _ms(2026, 10, 24, 9, 6), 1, 1, texts=["Abandoned response."]),
        ],
        _ms(2026, 10, 24, 9, 6),
    )
    _write_transcript(
        multi_dir,
        "session.v4.jsonl",
        [
            _header(SESSION_MULTI, PROJECT_BETA, _ms(2026, 10, 25, 11, 0), version=4),
            _request_header(2, _ms(2026, 10, 25, 11, 0), MODEL_ALT),
            _title(3, _ms(2026, 10, 25, 11, 1), TITLE_MULTI, "fallback"),
            _user(4, _ms(2026, 10, 25, 11, 5), PROMPT_MULTI),
            _assistant(5, _ms(2026, 10, 25, 11, 12), 1, 1, texts=["Resumed from the bounded digest."]),
            _record("turn/end", 6, _ms(2026, 10, 25, 11, 12), {"turn": 1, "reason": {"kind": "stop"}}),
        ],
        _ms(2026, 10, 25, 11, 12),
    )

    _write_transcript(
        sessions / GROUP_ALPHA / ("session-" + SESSION_EMPTY),
        "session.v4.jsonl",
        [_header(SESSION_EMPTY, PROJECT_ALPHA, _ms(2026, 10, 26, 9, 0))],
        _ms(2026, 10, 26, 9, 0),
    )

    _write_transcript(
        sessions / GROUP_BETA / SESSION_SUBAGENT,
        "session.v4.jsonl",
        [
            _header(
                SESSION_SUBAGENT,
                PROJECT_BETA,
                _ms(2026, 10, 24, 8, 0),
                depth=1,
            ),
            _request_header(2, _ms(2026, 10, 24, 8, 0), MODEL_MAIN),
            _user(3, _ms(2026, 10, 24, 8, 1), PROMPT_SUBAGENT),
            _assistant(4, _ms(2026, 10, 24, 8, 2), 1, 1, texts=["Subagent output."]),
        ],
        _ms(2026, 10, 24, 8, 2),
    )

    storages = home / "storages"
    storages.mkdir(parents=True, exist_ok=True)
    workspace_id = "b47a7cf7-d5ff-42c2-933f-2d89ce51e0b6"
    workspace = {
        "unit": {"name": "workspace", "version": 2},
        "global": {
            "initialized": True,
            "workspaceIds": [workspace_id],
            "archivedSessionIds": ["session-" + SESSION_ARCHIVED],
            "pinnedSessionIds": [],
        },
        "tables": {
            "workspaces": {
                workspace_id: {
                    "path": PROJECT_ALPHA,
                    "title": "project-alpha",
                    "sessionIds": [
                        "session-" + SESSION_MAIN,
                        "session-" + SESSION_ARCHIVED,
                        "session-" + SESSION_PLAIN,
                        "session-" + SESSION_MULTI,
                        "session-" + SESSION_EMPTY,
                    ],
                    "createdAt": "2026-10-01T00:00:00.000Z",
                    "updatedAt": "2026-10-27T15:30:00.000Z",
                }
            }
        },
    }
    with (storages / "workspace.json").open("w", encoding="utf-8") as handle:
        json.dump(workspace, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return home
