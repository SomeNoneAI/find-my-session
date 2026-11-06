"""Build a synthetic CodeBuddy CN store for tests.

Layout mirrors the real desktop app: a ``codebuddy-sessions.vscdb``
SQLite ``ItemTable`` with one ``session:<id>`` row per conversation,
per-queue JSON message files under
``User/globalStorage/tencent-cloud.coding-copilot/message-queue/``,
per-session todos in ``todos/<id>.json``, and edited-file snapshots in
``file-changes/<id>/``.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List

SESSION_MAIN = "c0de9001-aaaa-bbbb-cccc-111111111111"
SESSION_PLAIN = "c0de9002-aaaa-bbbb-cccc-222222222222"
SESSION_NO_QUEUE = "c0de9003-aaaa-bbbb-cccc-333333333333"
SESSION_IMAGE = "c0de9004-aaaa-bbbb-cccc-444444444444"
SESSION_ARCHIVED = "c0de9005-aaaa-bbbb-cccc-555555555555"

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_BETA = "/Users/example/project-beta"
PROJECT_GAMMA = "/Users/example/project-gamma"

PROMPTS_MAIN = (
    "Please refactor the handoff digest so the CLI stays bounded. codebuddy-main-needle",
    "Ship the compact summary fallback.",
    "Tighten the digest tests.",
)
PROMPT_PLAIN = "Investigate the migration drift in project gamma."
PROMPT_IMAGE = "图片是这样的"
PROMPT_ARCHIVED = "Archived session prompt. codebuddy-archived-needle"

TITLE_MAIN = "Refactor the handoff digest for the CLI"

EXTENSION_DIR = "tencent-cloud.coding-copilot"


def _ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    from datetime import datetime, timezone

    return int(
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp()
        * 1000
    )


def _encode_project(path: str) -> str:
    return base64.urlsafe_b64encode(path.encode()).decode().rstrip("=")


def _text_block(text: str, counter: List[int]) -> Dict[str, Any]:
    counter[0] += 1
    return {
        "type": "text",
        "text": text,
        "_meta": {"blockId": "block-synthetic-%d" % counter[0]},
    }


def _user_item(
    session_id: str,
    order: int,
    when: int,
    prompt: str,
    counter: List[int],
    model: str = "hy4-synthetic",
) -> Dict[str, Any]:
    return {
        "id": "mq-%d-user-%d" % (when, order),
        "conversationId": session_id,
        "contentBlocks": [_text_block(prompt, counter)],
        "previewText": prompt[:60],
        "status": "sent",
        "order": order,
        "createdAt": when,
        "updatedAt": when + 1000,
        "modeId": "craft",
        "modelId": model,
        "lastAttemptAt": when + 500,
    }


def _assistant_item(
    session_id: str, order: int, when: int, model: str = "hy4-synthetic"
) -> Dict[str, Any]:
    return {
        "id": "mq-%d-asst-%d" % (when, order),
        "conversationId": session_id,
        "contentBlocks": [
            {"type": "assistant", "text": "synthetic reply", "_meta": {}}
        ],
        "previewText": "synthetic reply",
        "status": "completed",
        "order": order,
        "createdAt": when,
        "updatedAt": when + 1000,
        "modeId": "craft",
        "modelId": model,
        "lastAttemptAt": when + 500,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_archive_log(home: Path, session_ids: List[str]) -> None:
    # Minimal leveldb-log-shaped file: the adapter scans for the
    # genie-archived-session-ids key with a one-byte length prefix and
    # a 0x01 separator before the JSON array; the last record wins.
    payload = json.dumps(session_ids, ensure_ascii=False).encode("utf-8")
    record = (
        b"genie-archived-session-ids"
        + bytes([len(payload) + 1])
        + b"\x01"
        + payload
    )
    leveldb = home / "Local Storage" / "leveldb"
    leveldb.mkdir(parents=True, exist_ok=True)
    (leveldb / "000003.log").write_bytes(record)


def _write_index(home: Path, rows: Iterable[Dict[str, Any]]) -> None:
    home.mkdir(parents=True, exist_ok=True)
    db_path = home / "codebuddy-sessions.vscdb"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute(
            "CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)"
        )
        for row in rows:
            connection.execute(
                "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
                (
                    "session:%s" % row["conversationId"],
                    json.dumps(row, ensure_ascii=False),
                ),
            )
        connection.commit()
    finally:
        connection.close()


def _index_row(
    session_id: str,
    cwd: str,
    title: str,
    status: str,
    created: int,
    updated: int,
) -> Dict[str, Any]:
    return {
        "conversationId": session_id,
        "cwd": cwd,
        "userId": "00000000-0000-4000-8000-000000000000",
        "title": title,
        "status": status,
        "createdAt": created,
        "updatedAt": updated,
    }


def build_codebuddy_cn_home(home: Path) -> Path:
    """Create a synthetic CodeBuddy CN store under ``home``."""
    counter = [0]
    created_main = _ms(2026, 10, 20, 17, 0)
    rows = [
        _index_row(
            SESSION_MAIN,
            PROJECT_ALPHA,
            TITLE_MAIN,
            "Working",
            created_main,
            _ms(2026, 10, 20, 18, 8),
        ),
        _index_row(
            SESSION_PLAIN,
            PROJECT_GAMMA,
            "",
            "Completed",
            _ms(2026, 10, 21, 9, 0),
            _ms(2026, 10, 21, 9, 30),
        ),
        _index_row(
            SESSION_NO_QUEUE,
            PROJECT_BETA,
            "Session without a message queue",
            "Completed",
            _ms(2026, 10, 22, 9, 0),
            _ms(2026, 10, 22, 9, 30),
        ),
        _index_row(
            SESSION_IMAGE,
            PROJECT_BETA,
            "",
            "Completed",
            _ms(2026, 10, 23, 9, 0),
            _ms(2026, 10, 23, 9, 30),
        ),
        _index_row(
            SESSION_ARCHIVED,
            PROJECT_GAMMA,
            "",
            "Completed",
            _ms(2026, 10, 19, 9, 0),
            _ms(2026, 10, 19, 9, 30),
        ),
    ]
    _write_index(home, rows)

    extension = home / "User" / "globalStorage" / EXTENSION_DIR
    queue_dir = extension / "message-queue"

    main_items: List[Dict[str, Any]] = []
    for order, prompt in enumerate(PROMPTS_MAIN):
        when = created_main + order * 900_000
        main_items.append(
            _user_item(SESSION_MAIN, order, when, prompt, counter)
        )
        main_items.append(
            _assistant_item(SESSION_MAIN, order, when + 60_000)
        )
    # A system-reminder wrapper must not become part of the prompt.
    main_items.append(
        _user_item(
            SESSION_MAIN,
            len(PROMPTS_MAIN),
            created_main + 4_000_000,
            "<system-reminder>stale context</system-reminder>Check the preview layout.",
            counter,
        )
    )
    _write_json(
        queue_dir / "main-queue.json",
        {
            "version": 2,
            "lastUpdated": created_main + 5_000_000,
            "conversations": {
                SESSION_MAIN: {
                    "version": 2,
                    "conversationId": SESSION_MAIN,
                    "updatedAt": created_main + 5_000_000,
                    "runtime": {"activated": True},
                    "items": main_items,
                }
            },
        },
    )

    plain_items = [
        _user_item(
            SESSION_PLAIN, 0, _ms(2026, 10, 21, 9, 5), PROMPT_PLAIN, counter
        )
    ]
    _write_json(
        queue_dir / "plain-queue.json",
        {
            "version": 2,
            "lastUpdated": _ms(2026, 10, 21, 9, 30),
            "conversations": {
                SESSION_PLAIN: {
                    "version": 2,
                    "conversationId": SESSION_PLAIN,
                    "updatedAt": _ms(2026, 10, 21, 9, 30),
                    "runtime": {"activated": True},
                    "items": plain_items,
                }
            },
        },
    )

    # Image blocks are context, never prompts; the text sibling is.
    _write_json(
        queue_dir / "image-queue.json",
        {
            "version": 2,
            "lastUpdated": _ms(2026, 10, 23, 9, 30),
            "conversations": {
                SESSION_IMAGE: {
                    "version": 2,
                    "conversationId": SESSION_IMAGE,
                    "updatedAt": _ms(2026, 10, 23, 9, 30),
                    "runtime": {"activated": True},
                    "items": [
                        {
                            "id": "mq-image-1",
                            "conversationId": SESSION_IMAGE,
                            "contentBlocks": [
                                {
                                    "type": "image",
                                    "data": "aVBORw0KGgo=",
                                    "mimeType": "image/png",
                                    "uri": "image.png",
                                    "_meta": {},
                                },
                                {"type": "text", "text": PROMPT_IMAGE, "_meta": {}},
                            ],
                            "previewText": "image.png " + PROMPT_IMAGE,
                            "status": "sent",
                            "order": 0,
                            "createdAt": _ms(2026, 10, 23, 9, 5),
                            "updatedAt": _ms(2026, 10, 23, 9, 6),
                            "modeId": "craft",
                            "modelId": "hy4-synthetic",
                            "lastAttemptAt": _ms(2026, 10, 23, 9, 6),
                        }
                    ],
                }
            },
        },
    )
    # SESSION_NO_QUEUE deliberately has no queue file.

    _write_json(
        queue_dir / "archived-queue.json",
        {
            "version": 2,
            "lastUpdated": _ms(2026, 10, 19, 9, 30),
            "conversations": {
                SESSION_ARCHIVED: {
                    "version": 2,
                    "conversationId": SESSION_ARCHIVED,
                    "updatedAt": _ms(2026, 10, 19, 9, 30),
                    "runtime": {"activated": True},
                    "items": [
                        _user_item(
                            SESSION_ARCHIVED,
                            0,
                            _ms(2026, 10, 19, 9, 5),
                            PROMPT_ARCHIVED,
                            counter,
                        )
                    ],
                }
            },
        },
    )

    # Archive state: Electron Local Storage leveldb log with the
    # genie-archived-session-ids key holding a JSON id array.
    _write_archive_log(home, [SESSION_ARCHIVED])
    _write_json(
        extension / "todos" / (SESSION_MAIN + ".json"),
        {
            "conversationId": SESSION_MAIN,
            "todos": [
                {
                    "id": "1",
                    "status": "in_progress",
                    "content": "Add prompt paging",
                },
                {
                    "id": "2",
                    "status": "pending",
                    "content": "Update docs",
                },
            ],
            "updatedAt": _ms(2026, 10, 20, 18, 0),
        },
    )

    changes = extension / "file-changes" / SESSION_MAIN
    for name in (
        "handoff.ts_1e5e6d47.json",
        "handoff.md_85e37a49.json",
    ):
        _write_json(changes / name, {"changes": []})

    # Empty genie-history conversation dirs exist in the real store but
    # carry no messages; include one to prove the adapter ignores them.
    (extension / "genie-history" / _encode_project(PROJECT_ALPHA)
     / "conversations" / SESSION_MAIN).mkdir(parents=True, exist_ok=True)

    return home
