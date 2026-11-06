# CodeBuddy CN

## Status

| Item | Value |
| --- | --- |
| Status | Ready |
| Adapter | `core/fms_lib/harnesses/codebuddy_cn.py` |
| Harness name | `codebuddy-cn` |
| Aliases | `codebuddy-cn`, `codebuddycn`, `cb-cn` |
| Variants | `desktop` |
| Store | `~/Library/Application Support/CodeBuddy CN` (macOS) |
| Home override | `FMS_CODEBUDDY_CN_HOME` |
| Verified | macOS arm64, live store on 2026-11-06 (8 sessions listed, all readable) |

`codebuddy` stays reserved for a future international edition. The planned
`codebuddy` harness (`~/.codebuddy`) is a different product with its own
store and must not resolve to this adapter.

## Store layout

```text
~/Library/Application Support/CodeBuddy CN/
├── codebuddy-sessions.vscdb          # session index (SQLite ItemTable)
├── last-session.json                 # launcher state, ignored
└── User/globalStorage/tencent-cloud.coding-copilot/
    ├── message-queue/*.json          # message bodies, one queue file each
    ├── todos/<session id>.json       # per-session todos
    ├── file-changes/<session id>/    # edited-file snapshots
    └── genie-history/<base64-cwd>/   # empty per-session dirs, ignored
```

`~/.codebuddy` (skills, plugins, settings) is **not** the session store.

## Session index

`codebuddy-sessions.vscdb` is a SQLite database with a single `ItemTable`:

| key | value |
| --- | --- |
| `session:<conversationId>` | JSON object |

The JSON value carries `conversationId`, `cwd`, `userId`, `title`,
`status` (`Working`, `Completed`), and millisecond-epoch `createdAt` /
`updatedAt`. The adapter opens the database read-only
(`file:...?mode=ro`) and reads all `session:%` rows. Listing order is
newest-first by `updatedAt`.

Observed `cwd` values are a mix of absolute macOS paths and `~/`-prefixed
paths (for example `~/git/bingo/fuse-console`); the adapter keeps them
as recorded. `--cwd` matching therefore works best with absolute paths.

## Message bodies

Each `message-queue/*.json` file holds `{"conversations": {<id>: {...}}}`
with an `items` array per conversation. Item shape:

```json
{
  "id": "mq-<epoch>-<rand>",
  "conversationId": "<uuid>",
  "contentBlocks": [{"type": "text", "text": "...", "_meta": {}}],
  "previewText": "first line",
  "status": "sent",
  "order": 0,
  "createdAt": "<epoch-ms string>",
  "updatedAt": "<epoch-ms string>",
  "modeId": "craft",
  "modelId": "hy4-preview",
  "lastAttemptAt": "<epoch-ms string>"
}
```

Prompt extraction: an item is a human prompt only when `status` is
`sent`. Assistant turns observed so far carry `completed` and their
assistant-shaped content blocks are skipped. `contentBlocks` with
`type: "text"` contribute text; `image` and other block types are
context and never prompts. `<system-reminder>` / `<task-notification>`
wrappers are stripped; generic prompts (`continue`, `继续`, `ok`) are
rejected for title selection only.

Sessions without a queue file (5 of 8 in the live store) still list,
search, and show from index metadata; prompts and the digest then carry
no turns. `genie-history/.../conversations/` directories exist but are
empty and are never read.

## Todos, edits, and files

- Todos come from `todos/<session id>.json` (`todos[].content` +
  `status`), mapped to `subject` + `status`.
- Edited files come from `file-changes/<session id>/` directory names:
  each `<file>_<hash>.json` snapshot counts once toward its file stem.
  Snapshot contents are never parsed.
- `file-changes` subdirectories of other sessions are ignored.

## Digest

`load()` streams the session queue once:

- Up to 50 recent user exchanges (prompt text capped at 4,000 chars).
- Todos from the todos file (capped at 400).
- Edited files from the file-changes directory (capped at 30).
- No compaction record exists in the observed store; `compact_summary`
  stays empty.
- `turn_count` counts human prompts only.

`show` prints the absolute virtual source path
`<home>/codebuddy-sessions.vscdb#<session-id>`; explicit `show` /
`prompts` by ref accept it because the shared `#` branch resolves the
base database file.

## Listing and search

`summarize()` reads the whole index (bounded: one row per session) plus
the session queue. Title prefers the stored index `title`, then the
latest meaningful prompt, then the first. Model comes from the first
item with a non-empty `modelId`. `size` is the sum of queue-file sizes
(a coarse figure, documented here rather than per-file precision).

`--deep` scans the session queue JSON (including non-text blocks) for
the tokens and never matches another session's queue. `contains()`
checks the prompt text, `previewText`, and the raw item JSON so that
model names and tool text inside a block can still match.

## Archive state

Archive state lives outside the session index, in Electron Local
Storage: `Local Storage/leveldb/*.log` carries a
`genie-archived-session-ids` key whose value is a JSON array of
archived conversation ids. The logs are append-only and rotate; the
newest record across all logs wins. The adapter scans for
`genie-archived-session-ids` + one-byte length + `0x01` + JSON and
takes the last match. There is no deleted flag; a removed index row
disappears from listings.

A missing or unreadable leveldb store means no archive metadata, so
every session stays active (same policy as a missing Qoder app
database). The default CLI hides archived sessions from
`search`/`latest` (including `--deep`, which never scans archived
queues); `--include-archived` brings them back; `show`/`prompts` open
them by explicit ref or virtual path.

## Resume

No verified resume command exists for CodeBuddy CN sessions, so `fms
resume` falls back to the handoff digest. Never invent a resume
command.

## Known gaps

- 5 of 8 live sessions had no message-queue file; their digests carry
  metadata only. The reason (expiry, eviction, or another queue
  location) is unknown.
- Only user turns (`status: sent`) were observed with real content;
  assistant-turn shapes, tool calls, compaction, and usage totals are
  fixture-only or unimplemented. `fms stats` reports nothing for this
  harness.
- `cwd` values mix absolute and `~/`-prefixed forms as recorded.
- Linux and Windows store locations are unverified; only the macOS
  Application Support path was observed.
- The `codebuddy` (international) store is a different product and is
  not read by this adapter.

## Verification

The fixture is built at runtime by `tests/codebuddy_cn_fixture.py`:

```bash
python3 - <<'PY'
from pathlib import Path
import tempfile
from tests.codebuddy_cn_fixture import build_codebuddy_cn_home
root = Path(tempfile.mkdtemp(prefix="codebuddy-cn-fixture-"))
build_codebuddy_cn_home(root / "home")
print(root)
PY
```

```bash
export FMS_CODEBUDDY_CN_HOME="/path/from/above/home"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness codebuddy-cn --limit 0
skills/find-my-session/scripts/fms show codebuddy-cn:c0de9001
skills/find-my-session/scripts/fms prompts codebuddy-cn:c0de9001 --count
skills/find-my-session/scripts/fms prompts codebuddy-cn:c0de9001 --limit 2
skills/find-my-session/scripts/fms prompts codebuddy-cn:c0de9001 --limit 2 --offset 2
```

Expected: four sessions newest-first (`c0de9004`, `c0de9003`,
`c0de9002`, `c0de9001`); `c0de9001` shows four prompts, two todos, and
edited files; `c0de9003` shows metadata only with zero turns; the
system-reminder wrapper is stripped; image blocks never become prompts.

Live verification (2026-11-06, macOS arm64): 8 sessions listed from the
real store, all readable, `show`/`prompts`/`doctor` exercised against
`271fead1` and `bec36e9e`; fixture and database bytes unchanged
afterwards.
