# CodeArts Agent

## Status

| Item | Value |
| --- | --- |
| Status | Ready |
| Adapter | `scripts/fms_lib/harnesses/codearts_agent.py` |
| Harness name | `codearts-agent` |
| Aliases | `codearts-agent`, `codearts`, `codeartsdoer`, `codearts-doer` |
| Variants | `desktop` |
| Store | `~/.codeartsdoer` |
| Home override | `FMS_CODEARTS_HOME` |
| Database override | `FMS_CODEARTS_DB` |
| Verified | macOS, CodeArts Agent 26.10.100 (`com.huawei.codearts.agent`), 2026-10-29 |

CodeArts Agent is Huawei's desktop coding agent. It is built on the opencode
runtime and keeps every session in one SQLite database, so the adapter is
database-backed like ZCode: sessions are rows, not files.

Only the desktop app was observed on this machine. There is no `codearts` or
`codeartsdoer` binary on `PATH`, so `variants` is `desktop` alone. If a CLI
edition later writes the same database, it can share this harness; if it writes
its own store, it needs a separate harness name.

Sessions have no per-session transcript path. Refs are the primary handle, and
the digest's `source:` value is a virtual path:
`<db path>#<raw session id>`. `show` and `prompts` accept that virtual path as
`REF|PATH`. Passing the bare database path is rejected.

## Store layout

```text
~/.codeartsdoer/
├── codearts-data/
│   ├── opencode.db             # sessions, messages, parts, todos, workspace
│   ├── opencode.db-wal         # present while the app is running
│   ├── opencode.db-shm
│   ├── storage/                # sandbox, permission, and session-diff files
│   └── log/                    # kernel logs, not read
├── CodeArts_Agent/             # downloaded agent kernel builds, not read
├── agent-team/session/         # team contact metadata, not read
└── memory/                     # long-term memory notes, not read
```

Only `codearts-data/opencode.db` is opened, read-only through a SQLite URI
(`file:...?mode=ro`). The adapter creates no cache, WAL, SHM, or journal file and
never migrates, repairs, or rewrites the schema. The database file and the WAL
bytes are unchanged by listing, search, deep search, `show`, and `prompts`; the
WAL grows only when CodeArts Agent itself writes. SQLite may still update the
shared-memory index (`-shm`) of a WAL that the app already left in place, exactly
as with ZCode. In a live check with CodeArts Agent running, the database bytes
and mtime were unchanged after every command.

`~/.codearts-doer-for-coding` and `~/Library/Application Support/CodeArts Agent`
are the VS Code shell and Electron profile. They hold extensions and window
state, not sessions.

### `opencode.db`

| Table | Columns read | Purpose |
| --- | --- | --- |
| `session` | `id`, `parent_id`, `directory`, `title`, `version`, `time_created`, `time_updated`, `time_archived`, `workspace_id` | One row per session. |
| `message` | `id`, `session_id`, `time_created`, `data` | Message envelope; `data` is JSON with `role`, `agent`, `modelID`, `error`. |
| `part` | `id`, `message_id`, `session_id`, `time_created`, `data` | Ordered content chunks; `data.type` selects text, tool, reasoning, step, and compaction. |
| `todo` | `session_id`, `content`, `status`, `position` | Current todo list per session. |
| `workspace` | `id`, `branch` | Branch for sessions that record a `workspace_id`. |

Columns are introspected with `PRAGMA table_info`, so an older or newer schema
degrades instead of failing. Timestamps are epoch milliseconds. The verified
build has no `sequence` column on `part`; the adapter orders parts by
`time_created` then `id`, and prefers `sequence` when a build provides it.

Ignored tables:

- `cag_session_extra`: CodeArts extension row holding token usage and the signed-in
  account name. It is not needed for a handoff and contains identity data.
- `cag_message_extra`, `cag_file_diff`: per-message provenance and per-file diff
  records. Tool parts already carry the edited paths in a format-neutral way.
- `project`, `permission`, `session_share`, `account*`, `event*`, `preference`:
  app state, sharing, and accounting.

## Message data

`message.data` is JSON. The adapter reads:

- `role`: `user` or `assistant`.
- `agent`, `mode`: `build`, `compaction`, or another agent name.
- `modelID`, `providerID`: assistant model, used for the digest's `model:` line.
- `model.modelID`: user-side model selection, used only as a fallback.
- `path.cwd` / `path.root`: recorded per assistant message; the `session.directory`
  column is authoritative for cwd.
- `error.data.message`, then `error.message`, then `error.name`: API failures.
- `summary: true`: marks the assistant message that carries a compaction summary.
- `synthetic: true` on a user message: a runtime-injected row, never a prompt.

## Parts

| `part.data.type` | Read as |
| --- | --- |
| `text` | User or assistant text. Skipped when `synthetic: true`. |
| `tool` | Tool call: `tool` is the name, `state.input` the arguments, `state.status` the outcome. |
| `compaction` | Compaction boundary marker; carries no text. |
| `reasoning`, `step-start`, `step-finish` | Ignored. |

Human prompt text is identified by `metadata.isUserInput: true` on the part, and
injected text by `synthetic: true`. The adapter keys off `synthetic` because it is
the flag the runtime sets for every injected part; a part without it is treated
as authored text and then re-checked against the reminder prefixes.

Tool outputs are never printed in the digest; only the name and a short argument
excerpt are kept. Attachments are not rendered.

## Listing and search

`iter_session_paths()` selects top-level sessions only:

```sql
SELECT id FROM session
WHERE parent_id IS NULL
ORDER BY time_updated DESC
```

Child sessions are background work such as `Auto-Memory Extraction`, whose
`parent_id` is a synthetic value like `ses_silent` rather than a real session id.
They are never listed, searched, or opened by prefix.

`summarize()` opens the database and reads a bounded slice:

- Session row: cwd, title, version, timestamps, archive marker, branch.
- Head prompts: up to 200 human text rows, oldest first.
- Tail prompts: up to 200 human text rows, newest first.
- Latest assistant `modelID`, falling back to the first user `model.modelID`.

It never reads assistant text, tool output, or the whole session. On the live
store at verification time (2 sessions, 98 messages, 398 parts, 1.6 MB),
`fms latest --harness codearts-agent` completed in about 0.4 seconds.

`session_id` is the raw id with the `ses_` prefix removed, so
`codearts-agent:e7a73ed6` is a useful eight-character ref. `find()` accepts a
prefix with or without `ses_`.

`entrypoint` and `variants` are `desktop`. `size_bytes` is always `0`: a session
has no file size of its own and the shared database size would be misleading.

`title` uses the app's stored session title. When it is empty or generic, the
adapter falls back to the latest meaningful human prompt, then the first.

## Archive state

A session is hidden when `session.time_archived` is set. There is no separate
task index and no soft-delete column in the verified schema; deleted sessions are
removed from `session` by cascade. A missing or unreadable database degrades to
"no archive metadata", so every session is active.

`SessionSummary.archived` is the only cross-harness signal. The shared CLI
filters archived sessions before search, including `--deep`, and `show` still
opens an archived session by explicit ref.

## Digest

`load()` streams the session's messages once, ordered by `time_created`, message
`id`, then part order, and retains bounded state:

- Up to 50 recent user/assistant exchanges.
- Up to three assistant text blocks per exchange, 5,000 characters each.
- Up to eight tools per exchange and 20 recent tools overall.
- Edited files from `edit`, `write`, `multiedit`, `patch`, `apply_patch`, and
  `notebookedit` tool parts, keyed by absolute path with a count, capped at 30.
  Ordering follows the most recent edit.
- Todos in `position` order, up to 400; `done` is normalized to `completed`.

The compact summary comes from the assistant message marked
`summary: true` (or `agent`/`mode` = `compaction`), capped at 20,000 characters.
In the verified build a compaction is written as a user message carrying a
`compaction` part followed by that assistant message, so the marker itself never
becomes a prompt.

API error details are appended to the assistant text as `[API error] ...`,
because quota and authentication failures are often the reason a handoff is
needed.

`turn_count` counts human prompts, not messages.

## Prompt listing

`iter_prompts()` streams every message in the session and yields one `UserPrompt`
per human-authored message, in transcript order. It applies no paging or
character caps; the CLI owns those.

Included:

- `role = user` messages whose text parts are not `synthetic`.
- Slash commands with arguments.
- Repeated and short prompts such as `继续`.

Excluded:

- Parts with `synthetic: true`, including the injected language reminder that
  CodeArts appends to almost every turn.
- User messages that contain only synthetic parts or only a `compaction` marker.
- Assistant messages, including the compaction summary message.
- Reasoning, step, and tool parts.

## Deep search

`--deep` is implemented per session, not per file. `contains()` scans only the
`message.data` and `part.data` rows of the selected session, normalizes the text
once, and requires every query token to appear. Because the shared CLI filters
archived sessions first, an archived session is not scanned unless
`--include-archived` is passed.

## Known gaps

- `size_bytes` is `0`.
- Attachments and reasoning are ignored.
- Child and background sessions (`parent_id` set) are excluded even with
  `--include-archived`.
- `cag_file_diff` is not read, so a file changed only through a shell command is
  not listed under edited files.
- The verified build has no `time_deleted` column; deletion is a hard cascade.
- A raw database path without `#<session id>` is rejected; use a ref or the
  printed virtual source path.
- Schema drift is the main risk: the adapter relies on opencode's `session`,
  `message`, `part`, and `todo` tables. New part types are ignored rather than
  guessed, and a missing table degrades to an empty section.

## Verification

Fixtures are built at runtime by `tests/codearts_fixture.py` because SQLite
databases are binary. To inspect one manually:

```bash
python3 - <<'PY'
from pathlib import Path
import tempfile
from tests.codearts_fixture import build_codearts_home
root = Path(tempfile.mkdtemp(prefix="codearts-fixture-"))
build_codearts_home(root / "home")
print(root / "home")
PY
```

Then point the CLI at that directory:

```bash
export FMS_CODEARTS_HOME="/path/from/above"
scripts/fms harnesses
scripts/fms search --harness codearts-agent
scripts/fms search --harness codearts-agent --include-archived --limit 0
scripts/fms show codearts-agent:c0de1001
scripts/fms show codearts-agent:c0de1001 --format json
scripts/fms prompts codearts-agent:c0de1001 --count
scripts/fms prompts codearts-agent:c0de1001 --limit 2 --offset 1
scripts/fms prompts codearts-agent:c0de1001 --order newest --limit 2
scripts/fms search --harness codearts-agent --deep deep-only-needle
```

Expected: two active sessions by default, three with `--include-archived`, no
child session, five prompts for `codearts-agent:c0de1001`, and a deep hit only
for `codearts-agent:c0de1002`.

`CodeArtsAgentTests.test_wal_mode_store_is_not_written` also converts a copy of
the fixture to WAL mode while holding a writer connection, then asserts that the
database and WAL bytes and the database mtime are unchanged after `search`,
`latest`, `show`, `prompts`, and `--deep`.
