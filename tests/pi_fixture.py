"""Synthetic Pi session store for tests. All content is invented."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_MAIN = "/Users/example/projects/pi-demo"
PROJECT_PLAIN = "/Users/example/projects/pi-notes"

SESSION_MAIN = "a1b2c3d4-1111-4a1b-8c1d-111111111111"
SESSION_PLAIN = "b2c3d4e5-2222-4b2c-9d2e-222222222222"

TITLE_MAIN = "Pi loader handoff"
PROMPTS_MAIN = [
    "Refactor the session loader",
    "继续",
    "Add synthetic paging tests",
]
PROMPTS_PLAIN = ["Draft a small note", "Polish the opening line"]

COMPACT_SUMMARY = "Earlier work moved the loader into the adapter layer."
DEEP_ONLY_NEEDLE = "PI_DEEP_SENTINEL"
TOOL_OUTPUT_NEEDLE = "PI_TOOL_SENTINEL"
INJECTED_NEEDLE = "PI_INJECTED_SENTINEL"
EDIT_PATH = "/Users/example/projects/pi-demo/src/loader.py"
MODEL_MAIN = "openrouter/free"
VERSION_MAIN = "3"
TODO_SUBJECT = "Verify prompt paging"

MAIN_STEM = "2026-10-27T15-30-00-000Z_%s" % SESSION_MAIN
PLAIN_STEM = "2026-10-20T09-10-00-000Z_%s" % SESSION_PLAIN


def _entry(
    entry_id: str,
    parent: str,
    timestamp: str,
    **payload: Any,
) -> Dict[str, Any]:
    record = {
        "id": entry_id,
        "parentId": parent,
        "timestamp": timestamp,
        **payload,
    }
    return record


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
    records: List[Dict[str, Any]] = [
        {
            "type": "session",
            "version": 3,
            "id": SESSION_MAIN,
            "timestamp": "2026-10-27T15:30:00.000Z",
            "cwd": PROJECT_MAIN,
        },
        _entry(
            "m1",
            None,
            "2026-10-27T15:30:01.000Z",
            type="model_change",
            provider="openrouter",
            modelId="free",
        ),
        _message(
            "u1",
            "m1",
            "2026-10-27T15:30:02.000Z",
            "user",
            [{"type": "text", "text": PROMPTS_MAIN[0]}],
        ),
        _message(
            "a1",
            "u1",
            "2026-10-27T15:30:03.000Z",
            "assistant",
            [
                {"type": "thinking", "thinking": "internal reasoning"},
                {"type": "text", "text": "I will inspect the loader first."},
                {
                    "type": "toolCall",
                    "id": "tc1",
                    "name": "bash",
                    "arguments": {"command": "rg session_loader src"},
                },
            ],
            model=MODEL_MAIN,
            provider="openrouter",
            usage={
                "input": 120,
                "output": 40,
                "cacheRead": 10,
                "cacheWrite": 0,
                "totalTokens": 170,
                "cost": {"total": 0.0012},
            },
            stopReason="toolUse",
        ),
        _message(
            "r1",
            "a1",
            "2026-10-27T15:30:04.000Z",
            "toolResult",
            [{"type": "text", "text": "output %s" % TOOL_OUTPUT_NEEDLE}],
            toolCallId="tc1",
            toolName="bash",
            isError=False,
        ),
        _message(
            "a2",
            "r1",
            "2026-10-27T15:30:05.000Z",
            "assistant",
            [
                {
                    "type": "toolCall",
                    "id": "tc2",
                    "name": "edit",
                    "arguments": {"path": EDIT_PATH, "oldText": "a", "newText": "b"},
                },
            ],
            model=MODEL_MAIN,
            provider="openrouter",
            stopReason="toolUse",
        ),
        _entry(
            "c1",
            "a2",
            "2026-10-27T15:30:06.000Z",
            type="compaction",
            summary=COMPACT_SUMMARY,
            firstKeptEntryId="a2",
            tokensBefore=50000,
        ),
        _entry(
            "cm1",
            "c1",
            "2026-10-27T15:30:07.000Z",
            type="custom_message",
            customType="demo-extension",
            content="Injected %s" % INJECTED_NEEDLE,
            display=True,
        ),
        _message(
            "u2",
            "cm1",
            "2026-10-27T15:30:08.000Z",
            "user",
            [
                {"type": "text", "text": PROMPTS_MAIN[1]},
                {
                    "type": "text",
                    "text": "<system-reminder>hidden reminder</system-reminder>",
                },
            ],
        ),
        _message(
            "a3",
            "u2",
            "2026-10-27T15:30:09.000Z",
            "assistant",
            [{"type": "text", "text": "Continuing the refactor."}],
            model=MODEL_MAIN,
            provider="openrouter",
            usage={
                "input": 80,
                "output": 20,
                "cacheRead": 0,
                "cacheWrite": 0,
                "totalTokens": 100,
                "cost": {"total": 0.0008},
            },
            stopReason="stop",
        ),
        _message(
            "u3",
            "a3",
            "2026-10-27T15:30:10.000Z",
            "user",
            [{"type": "text", "text": PROMPTS_MAIN[2]}],
        ),
        _message(
            "a4",
            "u3",
            "2026-10-27T15:30:11.000Z",
            "assistant",
            [
                {
                    "type": "toolCall",
                    "id": "tc3",
                    "name": "todo",
                    "arguments": {
                        "todos": [
                            {"content": TODO_SUBJECT, "status": "in_progress"},
                            {"content": "Run the suite", "status": "pending"},
                        ]
                    },
                },
            ],
            model=MODEL_MAIN,
            provider="openrouter",
            stopReason="toolUse",
        ),
        _entry(
            "info1",
            "a4",
            "2026-10-27T15:30:12.000Z",
            type="session_info",
            name=TITLE_MAIN,
        ),
        _message(
            "a5",
            "info1",
            "2026-10-27T15:30:14.000Z",
            "assistant",
            [{"type": "text", "text": "Rate limited."}],
            model=MODEL_MAIN,
            provider="openrouter",
            errorMessage="provider rate limit exceeded",
            stopReason="error",
        ),
    ]
    return records


def _plain_records() -> List[Dict[str, Any]]:
    return [
        {
            "type": "session",
            "version": 3,
            "id": SESSION_PLAIN,
            "timestamp": "2026-10-20T09:10:00.000Z",
            "cwd": PROJECT_PLAIN,
        },
        _message(
            "p1",
            None,
            "2026-10-20T09:10:02.000Z",
            "user",
            [{"type": "text", "text": PROMPTS_PLAIN[0]}],
        ),
        _message(
            "p2",
            "p1",
            "2026-10-20T09:10:03.000Z",
            "assistant",
            [{"type": "text", "text": "Here is a draft."}],
            model=MODEL_MAIN,
            provider="openrouter",
            stopReason="stop",
        ),
        _message(
            "p3",
            "p2",
            "2026-10-20T09:10:04.000Z",
            "user",
            [{"type": "text", "text": PROMPTS_PLAIN[1]}],
        ),
        _message(
            "p4",
            "p3",
            "2026-10-20T09:10:05.000Z",
            "assistant",
            [{"type": "text", "text": "Tightened the opening."}],
            model=MODEL_MAIN,
            provider="openrouter",
            stopReason="stop",
        ),
    ]


def _write(path: Path, records: List[Dict[str, Any]], partial: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, separators=(",", ":")) for record in records]
    text = "\n".join(lines) + "\n"
    if partial:
        text += '{"type":"message","id":"trunc","message":{"role":"user","content":[{"type":"text","text":"par'
    path.write_text(text, encoding="utf-8")


def _stamp(path: Path, iso: str) -> None:
    seconds = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(
        timezone.utc
    ).timestamp()
    os.utime(path, (seconds, seconds))


def build_pi_home(root: Path) -> Path:
    home = root
    sessions = home / "sessions" / "--Users-example-projects-pi-demo--"
    main_path = sessions / (MAIN_STEM + ".jsonl")
    _write(main_path, _main_records())
    _stamp(main_path, "2026-10-27T15:30:00.000Z")

    plain_path = home / "sessions" / "--Users-example-projects-pi-notes--" / (
        PLAIN_STEM + ".jsonl"
    )
    _write(plain_path, _plain_records(), partial=True)
    _stamp(plain_path, "2026-10-20T09:10:00.000Z")
    return home
