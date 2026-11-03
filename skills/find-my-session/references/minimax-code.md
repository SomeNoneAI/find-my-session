# MiniMax Code

## Status

| Item | Value |
| --- | --- |
| Status | Ready |
| Adapter | `scripts/fms_lib/harnesses/minimax_code.py` |
| Harness name | `minimax-code` |
| Aliases | `minimax-code`, `minimax`, `mcode` |
| Variants | `cli` |
| Store | `~/.minimax/v2` |
| Home override | `FMS_MINIMAX_CODE_HOME` |
| Database override | `FMS_MINIMAX_CODE_APP_DB` |
| Verified | macOS arm64, `mcode` 0.7.1 CLI against the MiniMax Code 3.1.10 runtime store, 2026-11-03 |

Every session has a dated `messages.jsonl` transcript, but
`sqlite/runtime-state.sqlite` is authoritative for listing metadata, the full
message history, tool calls, todo events, and archive state. The transcript is
the session anchor and is the only place that carries the compaction summary.

The `mcode` CLI is the verified surface. The MiniMax Code desktop app
(`/Applications/MiniMax Code.app`, app version 3.1.10) was running against the
same `runtime-state.sqlite` during verification — its WAL kept advancing while
the app was open — so the desktop UI is expected to share this store and ref
space. No desktop-originated session was confirmed, so `variants` stays `cli`
until one is.

## Store layout

```text
~/.minimax/v2/
├── sqlite/
│   ├── runtime-state.sqlite              # authoritative metadata + message rows
│   └── runtime-state.sqlite-wal/-shm     # live WAL; never written by fms
├── sessions/
│   └── <YYYY>/<MM>/<DD>/
│       └── <HH-MM-SS-mmm>-session_<base64url(session id)>/
│           ├── manifest.json             # sessionId, createdAtMs, updatedAtMs
│           └── messages.jsonl            # JSONL transcript and compaction
├── mcode/, assets/, observability/, ...  # not read
└── migration/, plugin-cache/, ...        # not read
```

The folder suffix is unpadded base64url of the raw `mvs_...` session id. The
adapter prefers `manifest.json.sessionId`, falls back to decoding the folder
suffix, and never guesses an id. Display refs strip the `mvs_` prefix, so a raw
`mvs_c0de...` id and `minimax-code:c0de...` resolve to the same session.

`runtime-state.sqlite` is opened read-only through a SQLite URI
(`file:...?mode=ro`): no cache, journal, WAL, or SHM file is created. Because the
app is normally running, the live WAL can still advance on its own; read-only
behavior was therefore confirmed against a frozen copy of a real store, where
listing, deep search, `show`, `prompts`, and `doctor` changed zero bytes.

### `local_runtime_sessions`

One row per session. Read columns: `session_id`, `record_json`,
`workspace_dir`, `project_workspace_dir`, `title`, `created_at_ms`,
`updated_at_ms`, `archived`, `visibility`, `status`, `session_kind`,
`parent_session_id`, `error_message`, `error_code`, `extra_data_json`, and
`history_relative_dir`.

- `extra_data_json.effectiveModel` is the session model.
- `error_message` and `error_code` are kept and rendered in the digest as
  `[API error] ...`, so quota and authentication failures stay visible.
- `record_json` is a denormalized copy whose `visibility` and `archived` may be
  stale; the columnar fields are authoritative.

### `local_runtime_message_rows`

One row per message: `session_id`, `msg_id`, `role`, `turn_id`,
`created_at_ms`, `data_json`, `source`. `data_json.msg_content` carries the
text and `tool_calls` carries the calls. Rows are ordered by `created_at_ms`,
then `id`.

The adapter reads only the rows for the session being shown; nothing from
another session is ever loaded.

### `messages.jsonl`

Each line is `{"message_id", "turn_id", "message"}`. The `message` object
carries `role`, `content` (a block list), and a `timestamp` in epoch
milliseconds or ISO 8601. Observed roles and blocks:

| Record | Treatment |
| --- | --- |
| `role: user`, text blocks | Human turn. `canonicalTextRange` trims the injected system-reminder prefix. |
| `role: assistant`, `text` blocks | Assistant text. |
| `role: assistant`, `thinking` blocks | Ignored, never rendered. |
| `role: assistant`, `toolCall` blocks | Tool name plus a short argument excerpt. |
| `role: toolResult` | Ignored by the digest. |
| `role: compactionSummary` | `summary` becomes `compact_summary`. |
| `role: custom` (identity reminder and similar) | Excluded. |

The database does not store the compaction summary, so `show` always checks the
transcript head for it after loading the message rows.

## Listing and search

`iter_session_paths()` reads the database first, newest `updated_at_ms` first),
and yields only top-level sessions:

- `parent_session_id IS NULL` — delegated task/subagent sessions are excluded.
- `session_kind IN ('conversation', 'task')` — peek, cron, and other internal
  kinds are excluded.
- `COALESCE(visibility, 'visible') != 'hidden'`.

A row whose `history_relative_dir` has no `messages.jsonl` is skipped. If the
database is missing, unreadable, or has no usable session table, the adapter
falls back to globbing `sessions/**/messages.jsonl` by modification time,
newest first; in that degraded mode every transcript is listed because archive
and internal-session metadata are unavailable.

`summarize()` merges the database row with the manifest and, only when the
database has no prompts, a bounded transcript head/tail read. `cwd` comes from
`workspace_dir`, then `project_workspace_dir`, then `record_json.workspaceDir`.
The title prefers the stored `title`, then the latest meaningful prompt, then
the first; generic prompts such as `继续`, `ok`, and `?` never become titles.

`size_bytes` is the transcript file size. `branch` and `version` stay empty:
neither the database nor the manifest carries them.

## Prompt extraction

A human prompt is a database row with `role = 'user'`, `msg_type = 1` when the
field is present, and a human `source` (`api` or `code_review`; an empty or
missing source is treated as human). The following are never prompts:

- `<system-reminder>`, `<task-notification>`, `<user-prompt-submit-hook>`, and
  `<local-command>` wrappers.
- `<questionnaire-response>` blocks and skill or slash-command invocations.
- Cron or worker deliveries (`source = 'cron'`), and injected meta content.
- Compaction summaries and tool results.

System reminders are stripped from the front of a prompt rather than truncated,
so a prompt never starts with injected context. On the transcript fallback the
`canonicalTextRange` offsets select the human substring directly.

`iter_prompts()` reads the database rows in `created_at_ms, id` order and yields
each human prompt once. When the database has no message rows for the session,
it streams the transcript instead. The shared CLI owns counting, paging,
ordering, and character caps.

## Digest

`load()` streams the session's message rows once and retains bounded state:

- Up to 50 recent exchanges.
- Up to three assistant text blocks per exchange, 5,000 characters each.
- Up to eight tools per exchange and 20 recent tools overall.
- Edited files from `edit`, `write`, `multiedit`, `notebookedit`, and
  `apply_patch`, with relative paths resolved against the session cwd, capped at
  30.
- Todos from `msg_type = 3` events whose payload has
  `eventType: "todo_updated"`; `done` is normalized to `completed`, capped at
  400. The latest event wins.
- The session-level API error text, when present.

Tool results are never printed; only the tool name and a short argument excerpt
are kept. Thinking blocks and custom records are ignored. The compaction
summary is read from the transcript head and rendered as
`compact_summary`, never as a turn.

## Archive state

A session is hidden when any of these holds:

- `local_runtime_sessions.archived` is non-zero.
- `visibility` is `hidden`, `archived`, or `deleted`.
- `status` is `hidden`, `archived`, or `deleted`.

The archive flag lives on the session row, so no separate index table is read.
A missing, unreadable, or older-schema database degrades to "no archive
metadata", so every transcript is active. The shared CLI applies the flag before
search and before deep search; `show` and `prompts` still open an archived
session by explicit ref or path and print `- archived: yes`.

## Deep search

`--deep` scans the session's own `local_runtime_message_rows.data_json` values
first and only then falls back to the transcript file. Because the scan is
keyed by the session id, a match in one session never leaks into another. The
transcript fallback is what finds compaction-only text, which has no database
row. Archived sessions are filtered by the shared CLI before this hook runs.

## Known gaps

- `branch` and `version` are empty; the store has no such fields.
- The MiniMax Code desktop app is expected to share this store but was not
  verified as a session producer; `variants` is `cli`.
- Attachments, images, and tool-result payloads are ignored.
- With a readable database, orphan transcripts that have no session row are
  not listed. Remove or rename the database to fall back to a pure transcript
  scan.
- A live app keeps the WAL open. Read-only commands do not write, but the WAL
  file itself may still change because of the app.
- Schema drift is the main risk: unknown message roles, block types, and
  session kinds are ignored rather than guessed.
- The store is versioned as `/v2`; an older `~/.minimax/sessions` layout is a
  different store and is not read.

## Verification

Fixtures are generated at runtime by `tests/minimax_code_fixture.py` because
the store mixes JSONL transcripts with a SQLite database.

```bash
python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "tests")
from minimax_code_fixture import build_minimax_code_home
root = Path("/tmp/minimax-code-fixture")
build_minimax_code_home(root)
print(root)
PY

export FMS_MINIMAX_CODE_HOME="/tmp/minimax-code-fixture"
export FMS_MINIMAX_CODE_APP_DB="$FMS_MINIMAX_CODE_HOME/sqlite/runtime-state.sqlite"
scripts/fms harnesses
scripts/fms search --harness minimax-code --limit 0
scripts/fms search --harness minimax-code --include-archived --limit 0
scripts/fms search --harness minimax-code --deep deep-only-needle
scripts/fms search --harness minimax-code --deep compaction-only-needle
scripts/fms show minimax-code:c0de4001
scripts/fms show minimax-code:c0de4001 --format json
scripts/fms prompts minimax-code:c0de4001 --count
scripts/fms prompts minimax-code:c0de4001 --limit 2 --offset 1
scripts/fms prompts minimax-code:c0de4001 --order newest --limit 2
scripts/fms doctor --harness minimax-code
```

Expected: three active sessions by default, four with `--include-archived`
(the extra row is marked `yes`), five prompts for `minimax-code:c0de4001`, and
deep hits only for that session for both synthetic needles. Removing the
database makes all eight transcripts active and fallback-only.
