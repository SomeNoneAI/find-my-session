# ZCode

## Status

| Item | Value |
| --- | --- |
| Status | Ready |
| Adapter | `scripts/fms_lib/harnesses/zcode.py` |
| Harness name | `zcode` |
| Aliases | `zcode`, `z-code`, `zai` |
| Variants | `desktop`, `cli` |
| Store | `~/.zcode` |
| Home override | `FMS_ZCODE_HOME` |
| Archive override | `FMS_ZCODE_APP_DB` |
| Verified | macOS, ZCode 0.17.0 desktop + CLI, 2026-10-28 |

ZCode desktop and its bundled `zcode` CLI share one SQLite store and one
session namespace, so they are one harness with two variants. A desktop session
id starts with `session_`; a CLI session id starts with `sess_`. Both appear in
the same tables and resolve to the same ref space.

Sessions are rows, not files. There is no per-session transcript path to print,
so refs are the primary handle and the digest's `source:` value is a virtual
path: `<db path>#<raw session id>`. `show` and `prompts` accept that virtual path
as `REF|PATH`. Passing the bare database path is rejected.

## Store layout

```text
~/.zcode/
├── cli/db/db.sqlite            # sessions, messages, parts, todos
├── v2/tasks-index.sqlite       # desktop task index; archive and delete flags
└── ...                         # app data not read by this adapter
```

Only two files are opened, both read-only through a SQLite URI
(`file:...?mode=ro`). The adapter creates no cache, WAL, or SHM file, and never
migrates, repairs, or rewrites a schema. SQLite may update the shared-memory
index of a WAL that the app already left in place; in a live check with ZCode
running, the database, WAL, SHM, and tasks-index bytes and mtimes were unchanged
after listing, search, deep search, `show`, and `prompts`.

### `cli/db/db.sqlite`

| Table | Columns read | Purpose |
| --- | --- | --- |
| `session` | `id`, `parent_id`, `directory`, `title`, `version`, `time_created`, `time_updated`, `time_archived`, `time_deleted`, `task_type` | One row per session. |
| `message` | `id`, `session_id`, `time_created`, `sequence`, `data` | Message envelope; `data` is JSON with `role` and `semantics`. |
| `part` | `id`, `message_id`, `session_id`, `sequence`, `data` | Ordered content chunks; `data.type` selects text, tool, reasoning, compaction, and others. |
| `todo` | `session_id`, `content`, `status`, `position` | Current todo list per session. |

Columns are introspected with `PRAGMA table_info`; older or newer schemas
degrade instead of failing. Timestamps are epoch milliseconds.

Other tables (`session_input`, `input_history`, `model_usage`, `tool_usage`,
`session_entry`, workflow tables, and `dwf_*`) are intentionally ignored. They
are useful for accounting but can duplicate prompts and tool traffic.

### `v2/tasks-index.sqlite`

The desktop app keeps a `tasks` table with `task_id`, `title`, `archived`,
`deleted`, and `cli_deleted`. A task id equals the raw session id and covers both
`session_` and `sess_` sessions. The adapter reads only ids where at least one
flag is set.

## Message semantics

`message.data` is JSON. The adapter reads:

- `role`: `user`, `assistant`, or another value.
- `semantics`: `origin`, `kind`, `uiVisibility`, `providerVisibility`,
  `transcriptVisibility`.
- `synthetic`: present and true for runtime-injected user rows.
- `modelId`, `modelSelection.modelId`, `error`.
- `contextSnapshot.envInfo.cwd` and `.gitBranch` for cwd/branch fallback.
- `time.created` is ignored; the `message.time_created` column is authoritative.

Observed `origin`/`kind` pairs:

| Role | origin | kind | Treatment |
| --- | --- | --- | --- |
| user | `real_user` | `user_prompt` | Human prompt. |
| user | `agent_runtime` | `system_reminder` | Excluded. |
| user | `agent_runtime` | `todo_reminder` | Excluded. |
| user | `agent_runtime` | `compact_summary` | Compact summary only. |
| user | `agent_runtime` | `background_notification` | Excluded. |
| user | `agent_runtime` | `subagent_notification` | Excluded. |
| assistant | `agent_runtime` | `assistant_response` | Assistant text and tools. |

Legacy rows without `semantics` are accepted as human prompts when they are not
`synthetic` and do not contain a runtime marker such as the TodoWrite reminder
or a continuation preamble. Rows with `transcriptVisibility: hidden` are never
prompts. A bare slash command such as `/clear` is not a prompt; a slash command
with arguments such as `/goal ...` is.

## Parts

| `part.data.type` | Read as |
| --- | --- |
| `text` | Assistant or user text. |
| `tool` | Tool call: `tool` is the name, `state.input` the arguments. |
| `compaction` | `summaryMessageId` points at the message holding the summary. |
| `reasoning`, `step-start`, `step-finish`, `timeline`, `file` | Ignored. |

Attachments (`file` parts) are not rendered or linked. Tool outputs are never
printed in the digest; only the name and a short argument excerpt are kept.

## Listing and search

`iter_session_paths()` selects top-level sessions only:

```sql
SELECT id FROM session
WHERE COALESCE(task_type, '') != 'subagent_child'
  AND parent_id IS NULL
ORDER BY time_updated DESC
```

Subagent child sessions are never listed, searched, or opened by prefix. A
direct virtual path can still summarize one, but `fms show` resolves refs
through `find()`, which lists only top-level sessions.

`summarize()` opens the database and reads a bounded slice:

- Session row: cwd, title, version, timestamps, archive markers.
- Head prompts: up to 200 human messages, oldest first.
- Tail prompts: up to 200 human messages, newest first.
- Latest assistant `modelId`, falling back to the first `modelSelection`.

It never reads assistant text, tool output, or the whole session. On a live
store with 41 top-level sessions and a 223 MB database, `fms latest --harness
zcode` completes in about 0.2 seconds.

`session_id` is the raw id with the `session_` or `sess_` prefix removed, so
`zcode:c0de0001` is a useful eight-character ref. `find()` accepts a prefix with
or without those raw prefixes.

`entrypoint` and `variants` are `desktop` for `session_...` ids and `cli` for
`sess_...` ids. `size_bytes` is always `0`: a session has no file size of its own
and the shared database size would be misleading.

`title` uses the app's stored session title. When it is empty or generic, the
adapter falls back to the latest meaningful human prompt, then the first.

## Archive and delete state

A session is hidden when any of these is true:

- `session.time_archived` is set.
- `session.time_deleted` is set.
- Its raw id appears in `tasks` with `archived = 1`, `deleted = 1`, or
  `cli_deleted = 1`.
- The tasks database is missing an id: active.

The hidden-id set is cached per process by database path, `mtime_ns`, and size.
A missing, unreadable, locked, or older-schema tasks database degrades to "no
archive metadata", so every session is active. The adapter never creates or
repairs that database. `SessionSummary.archived` is the only cross-harness
signal; the shared CLI filters archived sessions before search, including
`--deep`.

Deleted sessions may already be gone from `session`, leaving only a hidden task
row. That is harmless: listing reads `session`, so there is nothing to show.

## Digest

`load()` streams the session's messages once, ordered by `time_created` and
`message.sequence`, and retains bounded state:

- Up to 50 recent user/assistant exchanges.
- Up to three assistant text blocks per exchange, 5,000 characters each.
- Up to eight tools per exchange and 20 recent tools overall.
- Edited files from `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and
  `apply_patch`, keyed by absolute path with a count, capped at 30.
- Todos in `position` order, up to 400; `done` is normalized to `completed`.

The compact summary comes from a user message whose semantics kind is
`compact_summary`. If none exists, the adapter follows a `compaction` part's
`summaryMessageId` and joins that message's text parts. Both paths are capped at
20,000 characters.

API error details (`message.data.error.data.message`, then `error.message`, then
`error.name`) are appended to the assistant text as `[API error] ...`, because
quota and authentication failures are often the reason a handoff is needed.

`turn_count` counts human prompts, not messages.

## Prompt listing

`iter_prompts()` streams every message in the session and yields one
`UserPrompt` per human-authored message, in transcript order. It applies no
paging or character caps; the CLI owns those.

Included:

- `role = user`, `semantics.origin = real_user`, `semantics.kind =
  user_prompt`, visible transcript.
- Legacy user rows without semantics that pass the synthetic-marker checks.
- Slash commands with arguments.

Excluded:

- `synthetic` rows, hidden transcript rows, and every non-`user_prompt` kind.
- System, todo, background, and subagent notifications.
- Compact summaries, including the message referenced by a compaction part.
- Tool results, reasoning, step, timeline, and file parts.
- Bare slash commands, attachment-only messages, and runtime marker text.

## Deep search

`--deep` is implemented per session, not per file. `contains()` scans only the
`message.data` and `part.data` rows of the selected session, normalizes the text
once, and requires every query token to appear. Because the shared CLI filters
archived sessions first, an archived session is not scanned unless
`--include-archived` is passed. A live deep search over 41 sessions takes under
one second.

## Known gaps

- `size_bytes` is `0`.
- Attachments are ignored.
- Reasoning, step markers, and timeline events are ignored.
- `input_history` and `session_input` are not used; they may contain prompts that
  never became messages, or duplicates of them.
- Subagent child sessions are excluded even with `--include-archived`.
- A raw database path without `#<session id>` is rejected; use a ref or the
  printed virtual source path.
- The tasks database is a desktop artifact. A CLI-only installation may have no
  tasks index, in which case archive state falls back to the `session` columns.
- Schema drift is the main risk: new `semantics.kind` values are skipped rather
  than guessed, and new part types are ignored.

## Verification

Fixtures are built at runtime by `tests/zcode_fixture.py` because SQLite
databases are binary. To inspect one manually:

```bash
python3 - <<'PY'
from pathlib import Path
import tempfile
from tests.zcode_fixture import build_zcode_home
root = Path(tempfile.mkdtemp(prefix="zcode-fixture-"))
build_zcode_home(root / "home")
print(root / "home")
PY
```

Then point the CLI at that directory:

```bash
export FMS_ZCODE_HOME="/path/from/above"
export FMS_ZCODE_APP_DB="$FMS_ZCODE_HOME/v2/tasks-index.sqlite"
scripts/fms harnesses
scripts/fms search --harness zcode
scripts/fms search --harness zcode --include-archived --limit 0
scripts/fms show zcode:c0de0001
scripts/fms show zcode:c0de0001 --format json
scripts/fms prompts zcode:c0de0001 --count
scripts/fms prompts zcode:c0de0001 --limit 2 --offset 1
scripts/fms prompts zcode:c0de0001 --order newest --limit 2
scripts/fms search --harness zcode --deep deep-only-needle
```

Expected: two active sessions by default, five with `--include-archived`, no
subagent session, five prompts for `zcode:c0de0001`, and a deep hit only for
`zcode:c0de0002`.
