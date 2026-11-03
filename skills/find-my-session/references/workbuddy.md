# WorkBuddy AI

## Status

| Item | Value |
| --- | --- |
| Status | Ready |
| Adapter | `scripts/fms_lib/harnesses/workbuddy.py` |
| Shared parser | `scripts/fms_lib/harnesses/workbuddy_family.py` |
| Harness name | `workbuddy` |
| Aliases | `workbuddy`, `workbuddy-ai`, `wb` |
| Variants | `desktop` |
| Store | `~/.workbuddy-ai` |
| Home override | `FMS_WORKBUDDY_HOME` |
| Database override | `FMS_WORKBUDDY_APP_DB` |
| Verified | macOS, WorkBuddy AI 5.9.3 (`com.workbuddy.workbuddy-ai`), 2026-10-29 |

WorkBuddy AI is the international edition of WorkBuddy. Its runtime still uses
CodeBuddy identifiers internally (`codebuddy.session_id` in trace baggage,
`__codebuddyLocal` on records, a `/tmp/codebuddy-prewarm-*.sock` socket), but the
store and the product are WorkBuddy AI's own.

The domestic WorkBuddy edition shares this JSONL and database schema but uses
its own store at `~/.workbuddy` and its own harness, `workbuddy-cn`. Both
adapters are thin subclasses of `WorkBuddyBaseAdapter`, and neither reads the
other edition's database. See `references/workbuddy-cn.md`.

The domestic CodeBuddy edition is a different product with a different store.
It is reserved as the planned `codebuddy` harness and is not implemented; a
`workbuddy` ref never resolves to a CodeBuddy session, and `~/.codebuddy` is not
read by this adapter.

Only the desktop app was observed. There is no `workbuddy` binary on `PATH`, and
the per-session registry in `sessions/<pid>.json` records `kind: interactive`
with a local URL for the desktop runtime, so `variants` is `desktop` alone.

## Store layout

```text
~/.workbuddy-ai/
├── workbuddy.db                          # sessions table: title, status, archive
├── projects/
│   └── <slugified cwd>/
│       ├── <session id>.jsonl            # transcript, one JSON record per line
│       ├── <session id>.file-rollback.ndjson   # ignored
│       ├── <session id>.meta.json        # ignored
│       └── <session id>/tool-results/    # large tool output, ignored
├── tasks/
│   └── <session id>/<n>.json             # todo list for one session
├── sessions/<pid>.json                   # live process registry, ignored
├── traces/                               # OpenTelemetry traces, ignored
└── logs/, cache/, plugins/, skills/      # not read
```

`projects/<slug>/<session id>.jsonl` is the only transcript. The slug is the
working directory with `/` replaced by `-` and spaces kept, for example
`Users-example-project-alpha`; the adapter never parses it and reads `cwd` from
the database or from the records instead.

`workbuddy.db` is opened read-only through a SQLite URI (`file:...?mode=ro`).
The adapter creates no cache, WAL, SHM, or journal file. In a live check with the
app running, the database and every transcript were unchanged after listing,
search, deep search, `show`, and `prompts`.

### `workbuddy.db`

| Table | Columns read | Purpose |
| --- | --- | --- |
| `sessions` | `id`, `cwd`, `title`, `custom_title`, `status`, `model`, `created_at`, `updated_at`, `deleted_at`, `visibility` | One row per session; also carries the archive flag. |

Timestamps are epoch milliseconds. Other tables (`session_usage`, `automations`,
`automation_runs`, `workspaces`, `buddy_snapshots`, `workspace_trust_decisions`)
are ignored. `session_usage.used` and `.size` are context-window accounting, not
session content.

A transcript with no `sessions` row is still listed. CLI-only or orphaned
transcripts are normal, and the adapter falls back to the `cwd` recorded in the
transcript and to prompt-derived titles.

## Record types

Every line is one JSON object with `type`, `sessionId`, `timestamp`, and usually
`id`, `cwd`, and `_meta`. `timestamp` is epoch milliseconds.

| `type` | Read as |
| --- | --- |
| `message` (`role: user`) | User turn. `content` is a list of `input_text` parts. |
| `message` (`role: user`, `providerData.isMeta: true`) | Injected meta content. Excluded. |
| `message` (`role: user`, compaction flags) | Compaction summary when present. Parsed into `compact_summary`, never a prompt. |
| `message` (`role: assistant`) | Assistant turn. `content` is a list of `output_text` parts. |
| `function_call` | Tool call. `name` is the tool, `arguments` is a JSON **string**. |
| `function_call_result` | Tool result. Ignored by the digest; `output` may be a dict or a list. |
| `reasoning` | Thinking text in `rawContent`. Ignored. |
| `summary` (`providerData.source: initial-user-message`) | Denormalized initial prompt. First-prompt fallback only. |
| `ai-title` | Generated title in `aiTitle`. Used only when the database has none. |
| `session-meta` | Host metadata. Ignored. |
| `file-history-snapshot` | File backup bookkeeping. Ignored. |

Observed tool names include `Bash`, `Read`, `Edit`, `Write`, `Grep`, `WebSearch`,
`WebFetch`, `TaskCreate`, `TaskUpdate`, `TaskOutput`, `AskUserQuestion`, `Skill`,
`present_files`, `show_widget`, and `automation_update`. Names are matched
case-insensitively for the edited-file list.

## Prompt extraction

A user record is a human prompt only when the text carries one of these markers.
Everything else is agent traffic and is dropped.

| Record shape | Treatment |
| --- | --- |
| `<user_query>...</user_query>` present | Human prompt; the inner text is used. |
| `providerData.startsNewUserRequest: true` with no `user_query` | Fallback for older builds: system reminders are stripped and the remainder must be non-empty. |
| `<system-reminder data-role="user-context">` block only | Excluded. |
| `<task-notification>...</task-notification>` | Excluded; these are background-task results delivered as user turns. |
| `providerData.isMeta: true` | Excluded. |
| `providerData.compactType` / `isCompacted` / `isSummary`, or `<cb_summary>` | Excluded; this is a compaction record. |
| `summary` record (`source: initial-user-message`) | Excluded; it is a denormalized copy used only as a first-prompt fallback. |
| `role: assistant`, `reasoning`, `function_call`, `function_call_result` | Excluded. |

The `<system-reminder>` block in front of a prompt contains the environment,
identity files, and memory context; it is stripped rather than truncated, so a
prompt never starts with injected context. A record with several `user_query`
blocks yields one prompt with the blocks joined, and one prompt per record is
yielded overall.

`__codebuddyLocal` is a desktop UI marker, not a meta flag. Records carrying it
are real human prompts and are included.

`startsNewUserRequest` is not reliable on its own: one observed follow-up had it
`false` while still carrying a `user_query`, and older builds omit it entirely.
The marker order above handles both.

## Digest

`load()` streams the transcript once, in file order, and retains bounded state:

- Up to 50 recent user/assistant exchanges.
- Up to three assistant text blocks per exchange, 5,000 characters each.
- Up to eight tools per exchange and 20 recent tools overall.
- Edited files from `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and
  `apply_patch` calls, keyed by absolute path with a count, capped at 30.
  Relative paths are resolved against the session cwd.
- Todos from `tasks/<session id>/*.json`, ordered by file modification time, up
  to 400; `done` is normalized to `completed`.

No compaction record was observed in the international format, so
`compact_summary` is normally empty and `show` omits that section. The shared
parser still recognizes the domestic `<cb_summary>` compaction records and the
`compactType` / `isCompacted` / `isSummary` flags, so a future international
build that emits them is captured as a summary rather than a turn. When there is
no compaction, long sessions are summarized by the prompt-derived title, the
task, the latest request, and the todo list instead.

Tool results are never printed; only the tool name and a short argument excerpt
are kept. `output` payloads, `tool-results/*.txt`, and file snapshots are not
read.

## Listing and search

`iter_session_paths()` globs `projects/*/*.jsonl`, skips
`*.file-rollback.ndjson`, and sorts by modification time, newest first. Every
other file in the project directory is ignored, so a rollback log is never
mistaken for a session.

`summarize()` reads a bounded head (2 MB or 800 records) and tail (512 KB):

- Head: first human prompt, `cwd`, `requestModelId`, first `ai-title`, start time.
- Tail: last human prompt and the newest record timestamp.
- Database row: `custom_title`, `title`, `status`, `model`, `created_at`,
  `updated_at`.

When the head contains no human prompt, the denormalized initial prompt in a
`summary` record is used as the first-prompt fallback. It is never exposed as a
prompt and never replaces `last_prompt`.

It never parses assistant text or tool output. `session_id` is the transcript
file stem, which is already the session id, so `workbuddy:c0de2001` is a useful
eight-character ref. `size_bytes` is the transcript size, which is real for this
harness.

`title` prefers `custom_title`, then `title`, then the first `ai-title` record,
then the latest meaningful prompt.

## Archive state

A session is hidden when either condition holds:

- `sessions.status` is `archived`. The app's `archiveSession` handler sets that
  status, so it is the authoritative archive flag.
- `sessions.deleted_at` is a positive timestamp. A `deleted_at` of `-1` is the
  cloud-transport "never deleted" sentinel and stays active.

`visibility` is also treated as `archived` when it holds that value, but no row
on the verified machine used it — treat that path as **expected, unverified**.
A missing, unreadable, or older-schema database degrades to "no archive
metadata", so every session is active.

`SessionSummary.archived` is the only cross-harness signal. The shared CLI
filters archived sessions before search, including `--deep`, and `show` still
opens an archived session by explicit ref or path.

## Deep search

`--deep` uses the default per-file scan. It reads the transcript in 4 MB chunks,
normalizes the text once, and requires every query token to appear, so a match in
one session never leaks into another. Because the shared CLI filters archived
sessions first, an archived transcript is not scanned unless
`--include-archived` is passed.

## Known gaps

- No compaction summary was observed in the international format;
  `compact_summary` is usually empty. The shared parser handles the domestic
  `<cb_summary>` shape if a future build emits it.
- `branch` and `version` are empty: the database has no such columns and the
  transcript records do not carry them.
- Tool results, `tool-results/*.txt`, and file snapshots are not rendered.
- Zero-byte placeholder transcripts cannot be summarized and are skipped until
  the first record is written.
- `traces/` holds OpenTelemetry spans that repeat prompt text; they are ignored
  so prompts are not counted twice.
- `sessions/*.json` is a live process registry, not a session list; prewarm
  entries are not sessions.
- Playground sessions (`is_playground = 1`) are listed like any other session.
- Schema drift is the main risk: new record types are ignored rather than
  guessed, and a transcript whose prompts lose the `user_query` wrapper falls
  back to `startsNewUserRequest`.

## Verification

Fixtures are built at runtime by `tests/workbuddy_fixture.py` because the home
mixes JSONL transcripts with a SQLite database. To inspect one manually:

```bash
python3 - <<'PY'
from pathlib import Path
import tempfile
from tests.workbuddy_fixture import build_workbuddy_home
root = Path(tempfile.mkdtemp(prefix="workbuddy-fixture-"))
build_workbuddy_home(root / "home")
print(root / "home")
PY
```

Then point the CLI at that directory:

```bash
export FMS_WORKBUDDY_HOME="/path/from/above"
export FMS_WORKBUDDY_APP_DB="$FMS_WORKBUDDY_HOME/workbuddy.db"
scripts/fms harnesses
scripts/fms search --harness workbuddy --limit 0
scripts/fms search --harness workbuddy --include-archived --limit 0
scripts/fms show workbuddy:c0de2001
scripts/fms show workbuddy:c0de2001 --format json
scripts/fms prompts workbuddy:c0de2001 --count
scripts/fms prompts workbuddy:c0de2001 --limit 2 --offset 1
scripts/fms prompts workbuddy:c0de2001 --order newest --limit 2
scripts/fms search --harness workbuddy --deep deep-only-needle
```

Expected: four active sessions by default, six with `--include-archived`, three
prompts for `workbuddy:c0de2001`, and a deep hit only for `workbuddy:c0de2002`.
