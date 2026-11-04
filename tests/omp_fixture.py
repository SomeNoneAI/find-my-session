"""Synthetic Oh My Pi (omp) session store for tests. All content is invented."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_MAIN = "/Users/example/projects/omp-demo"
PROJECT_PLAIN = "/Users/example/projects/omp-notes"

SESSION_MAIN = "a1b2c3d4-1111-4a1b-8c1d-111111111111"
SESSION_PLAIN = "b2c3d4e5-2222-4b2c-9d2e-222222222222"
SESSION_SUBAGENT = "d4e5f6a7-4444-4d4e-8f5a-444444444444"

TITLE_AUTO = "Initial omp title"
TITLE_MANUAL = "omp adapter handoff"
PROMPTS_MAIN = [
    "Wire the omp adapter",
    "继续",
    "Check the title fallback",
]
PROMPTS_PLAIN = ["Sketch the notes layout", "Tighten the wording"]

COMPACT_SUMMARY = "The omp schema was mapped before the adapter was written."
DEEP_ONLY_NEEDLE = "OMP_DEEP_SENTINEL"
TOOL_OUTPUT_NEEDLE = "OMP_TOOL_SENTINEL"
INJECTED_NEEDLE = "OMP_INJECTED_SENTINEL"
SUBAGENT_PROMPT = "Investigate the failing fixture"
EDIT_PATH = "/Users/example/projects/omp-demo/src/adapter.py"
MODEL_MAIN = "anthropic/claude-opus-4-8"
VERSION_MAIN = "3"
TODO_SUBJECT = "Verify omp prompt paging"

MAIN_STEM = "2026-10-27T16-30-00-000Z_%s" % SESSION_MAIN
PLAIN_STEM = "2026-10-20T10-10-00-000Z_%s" % SESSION_PLAIN
SUBAGENT_STEM = "2026-10-27T16-31-00-000Z_%s" % SESSION_SUBAGENT


def _entry(
    entry_id: str,
    parent: str,
    timestamp: str,
    **payload: Any,
) -> Dict[str, Any]:
    return {
        "id": entry_id,
        "parentId": parent,
        "timestamp": timestamp,
        **payload,
    }


def _message(
    entry_id: str,
    parent: str,
    timestamp: str,
    role: str,
    content: Any,
    **extra: Any,
) -> Dict[str, Any]:
    return _entry(
        entry_id,
        parent,
        timestamp,
        type="message",
        message={"role": role, "content": content, "timestamp": 0, **extra},
    )


def _main_records() -> List[Dict[str, Any]]:
    return [
        {
            "type": "title",
            "title": TITLE_AUTO,
            "source": "auto",
            "updatedAt": "2026-10-27T16:30:01.000Z",
            "pad": 0,
        },
        {
            "type": "session",
            "version": 3,
            "id": SESSION_MAIN,
            "timestamp": "2026-10-27T16:30:00.000Z",
            "cwd": PROJECT_MAIN,
        },
        _entry(
            "m1",
            None,
            "2026-10-27T16:30:01.000Z",
            type="model_change",
            model=MODEL_MAIN,
            runtime={"version": "18.16.0"},
        ),
        _entry(
            "cwd1",
            "m1",
            "2026-10-27T16:30:02.000Z",
            type="custom",
            customType="date-cwd-reminder",
            data={"cwd": PROJECT_MAIN, "date": "2026-10-27"},
        ),
        _message(
            "u1",
            "cwd1",
            "2026-10-27T16:30:03.000Z",
            "user",
            [{"type": "text", "text": PROMPTS_MAIN[0]}],
            attribution="user",
        ),
        _message(
            "a1",
            "u1",
            "2026-10-27T16:30:04.000Z",
            "assistant",
            [
                {"type": "thinking", "thinking": "plan", "thinkingSignature": "sig"},
                {"type": "text", "text": "I will write the parser."},
                {
                    "type": "toolCall",
                    "id": "tc1",
                    "name": "write",
                    "arguments": {"path": EDIT_PATH, "content": "pass"},
                },
            ],
            model="claude-opus-4-8",
            provider="anthropic",
            usage={
                "input": 150,
                "output": 30,
                "cacheRead": 20,
                "cacheWrite": 0,
                "totalTokens": 200,
                "cost": {"total": 0.0025},
            },
            stopReason="toolUse",
        ),
        _message(
            "r1",
            "a1",
            "2026-10-27T16:30:05.000Z",
            "toolResult",
            [{"type": "text", "text": "output %s" % TOOL_OUTPUT_NEEDLE}],
            toolCallId="tc1",
            toolName="write",
            isError=False,
        ),
        _entry(
            "c1",
            "r1",
            "2026-10-27T16:30:06.000Z",
            type="compaction",
            summary=COMPACT_SUMMARY,
            tokensBefore=60000,
        ),
        _entry(
            "sp1",
            "c1",
            "2026-10-27T16:30:07.000Z",
            type="custom",
            customType="system-prompt-digest",
            data={"tokens": 10},
        ),
        _message(
            "u2",
            "sp1",
            "2026-10-27T16:30:08.000Z",
            "user",
            [{"type": "text", "text": PROMPTS_MAIN[1]}],
            attribution="user",
        ),
        _message(
            "meta1",
            "u2",
            "2026-10-27T16:30:09.000Z",
            "user",
            [{"type": "text", "text": INJECTED_NEEDLE}],
            attribution="system",
        ),
        _message(
            "a2",
            "meta1",
            "2026-10-27T16:30:10.000Z",
            "assistant",
            [{"type": "text", "text": "Continuing the adapter work."}],
            model="claude-opus-4-8",
            provider="anthropic",
            usage={
                "input": 90,
                "output": 20,
                "cacheRead": 0,
                "cacheWrite": 0,
                "totalTokens": 110,
                "cost": {"total": 0.0013},
            },
            stopReason="stop",
        ),
        _message(
            "u3",
            "a2",
            "2026-10-27T16:30:11.000Z",
            "user",
            [{"type": "text", "text": PROMPTS_MAIN[2]}],
            attribution="user",
        ),
        _message(
            "a3",
            "u3",
            "2026-10-27T16:30:12.000Z",
            "assistant",
            [
                {
                    "type": "toolCall",
                    "id": "tc2",
                    "name": "todo",
                    "arguments": {
                        "todos": [
                            {"content": TODO_SUBJECT, "status": "in_progress"},
                            {"content": "Run the suite", "status": "pending"},
                        ]
                    },
                },
            ],
            model="claude-opus-4-8",
            provider="anthropic",
            stopReason="toolUse",
        ),
        {
            "type": "title_change",
            "title": TITLE_MANUAL,
            "source": "manual",
            "updatedAt": "2026-10-27T16:30:13.000Z",
            "timestamp": "2026-10-27T16:30:13.000Z",
        },
        _message(
            "a4",
            "a3",
            "2026-10-27T16:30:14.000Z",
            "assistant",
            [{"type": "text", "text": "Rate limited."}],
            model="claude-opus-4-8",
            provider="anthropic",
            errorMessage="provider rate limit exceeded",
            stopReason="error",
        ),
    ]


def _plain_records() -> List[Dict[str, Any]]:
    return [
        {
            "type": "session",
            "version": 3,
            "id": SESSION_PLAIN,
            "timestamp": "2026-10-20T10:10:00.000Z",
            "cwd": PROJECT_PLAIN,
        },
        _message(
            "p1",
            None,
            "2026-10-20T10:10:02.000Z",
            "user",
            [{"type": "text", "text": PROMPTS_PLAIN[0]}],
            attribution="user",
        ),
        _message(
            "p2",
            "p1",
            "2026-10-20T10:10:03.000Z",
            "assistant",
            [{"type": "text", "text": "Here is a layout."}],
            model="claude-opus-4-8",
            provider="anthropic",
            stopReason="stop",
        ),
        _message(
            "p3",
            "p2",
            "2026-10-20T10:10:04.000Z",
            "user",
            [{"type": "text", "text": PROMPTS_PLAIN[1]}],
            attribution="user",
        ),
        _message(
            "p4",
            "p3",
            "2026-10-20T10:10:05.000Z",
            "assistant",
            [{"type": "text", "text": "Shortened the copy."}],
            model="claude-opus-4-8",
            provider="anthropic",
            stopReason="stop",
        ),
    ]


def _subagent_records() -> List[Dict[str, Any]]:
    return [
        {
            "type": "session",
            "version": 3,
            "id": SESSION_SUBAGENT,
            "timestamp": "2026-10-27T16:31:00.000Z",
            "cwd": PROJECT_MAIN,
        },
        _message(
            "s1",
            None,
            "2026-10-27T16:31:01.000Z",
            "user",
            [{"type": "text", "text": SUBAGENT_PROMPT}],
            attribution="user",
        ),
        _message(
            "s2",
            "s1",
            "2026-10-27T16:31:02.000Z",
            "assistant",
            [{"type": "text", "text": "Fixture reviewed."}],
            model="claude-opus-4-8",
            provider="anthropic",
            stopReason="stop",
        ),
    ]


def _write(path: Path, records: List[Dict[str, Any]], partial: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(
        json.dumps(record, separators=(",", ":")) for record in records
    ) + "\n"
    if partial:
        text += '{"type":"message","id":"trunc","message":{"role":"user","content":[{"type":"text","text":"par'
    path.write_text(text, encoding="utf-8")


def _stamp(path: Path, iso: str) -> None:
    seconds = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(
        timezone.utc
    ).timestamp()
    os.utime(path, (seconds, seconds))


def build_omp_home(root: Path) -> Path:
    home = root
    workspace = home / "sessions" / "--Users-example-projects-omp-demo--"
    main_path = workspace / (MAIN_STEM + ".jsonl")
    _write(main_path, _main_records())
    _stamp(main_path, "2026-10-27T16:30:00.000Z")

    subagent_path = workspace / MAIN_STEM / "reviewer.jsonl"
    _write(subagent_path, _subagent_records())
    _stamp(subagent_path, "2026-10-27T16:31:00.000Z")

    lock_path = workspace / (MAIN_STEM + ".jsonl.lock.os")
    lock_path.write_text("", encoding="utf-8")

    plain_path = (
        home
        / "sessions"
        / "--Users-example-projects-omp-notes--"
        / (PLAIN_STEM + ".jsonl")
    )
    _write(plain_path, _plain_records(), partial=True)
    _stamp(plain_path, "2026-10-20T10:10:00.000Z")
    return home
