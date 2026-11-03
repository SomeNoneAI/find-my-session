# WorkBuddy domestic

## Status

| Item | Value |
| --- | --- |
| Status | Ready |
| Adapter | `scripts/fms_lib/harnesses/workbuddy_cn.py` |
| Shared parser | `scripts/fms_lib/harnesses/workbuddy_family.py` |
| Harness name | `workbuddy-cn` |
| Aliases | `workbuddy-cn`, `workbuddycn`, `workbuddy_cn`, `wb-cn` |
| Variants | `desktop` |
| Store | `~/.workbuddy` |
| Home override | `FMS_WORKBUDDY_CN_HOME` |
| Database override | `FMS_WORKBUDDY_CN_APP_DB` |
| Verified | macOS, WorkBuddy 5.5.4 (`com.tencent.workbuddy.mac`), 2026-10-29 |

WorkBuddy domestic is Tencent WorkBuddy for the mainland China edition. It
shares the JSONL transcript, todo directory, and application database schema of
WorkBuddy AI, so both adapters are thin subclasses of `WorkBuddyBaseAdapter`.
They remain separate harnesses because they use separate stores and ref
namespaces:

| Harness | Edition | Store | Bundle |
| --- | --- | --- | --- |
| `workbuddy` | International WorkBuddy AI | `~/.workbuddy-ai` | `com.workbuddy.workbuddy-ai` |
| `workbuddy-cn` | Domestic WorkBuddy | `~/.workbuddy` | `com.tencent.workbuddy.mac` |

The unqualified `workbuddy` alias stays with the international edition so
existing refs keep resolving. Use `workbuddy-cn` or `wb-cn` for the domestic
store. Neither adapter reads the other edition's database, and a
`workbuddy-cn:` ref never resolves to an international session. The domestic
CodeBuddy product is unrelated and remains the planned `codebuddy` harness.

Only the desktop app was observed. There is no WorkBuddy binary on `PATH`, and
the per-session registry in `sessions/<pid>.json` records an interactive desktop
runtime, so `variants` is `desktop` alone.

## Store layout

```text
~/.workbuddy/
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
├── file-history/, blobs/, changes-index/, artifact-index/   # not read
└── logs/, cache/, plugins/, skills/      # not read
```

`projects/<slug>/<session id>.jsonl` is the only transcript. The slug is the
working directory with `/` replaced by `-` and spaces kept; the adapter never
parses it and reads `cwd` from the database or from the records instead.

`workbuddy.db` is opened read-only through a SQLite URI (`file:...?mode=ro`).
The adapter creates no cache, WAL, SHM, or journal file. A live snapshot of the
store was unchanged after listing, search, deep search, `show`, and `prompts`.

### `workbuddy.db`

| Table | Columns read | Purpose |
| --- | --- | --- |
| `sessions` | `id`, `cwd`, `title`, `custom_title`, `status`, `model`, `created_at`, `updated_at`, `deleted_at` | One row per session; also carries the archive flag. |

The domestic schema has no `visibility` column. The adapter introspects
`PRAGMA table_info(sessions)` and selects only columns that exist, so the same
base class works with both editions. Domestic rows also carry `last_activity_at`,
`source_mode`, `is_playground`, `mode`, `expert_*`, `project_id`, and
`session_settings`; none of these change the digest, so they are ignored.

Timestamps are epoch milliseconds. Other tables (`session_usage`, `automations`,
`automation_runs`, `workspaces`, `buddy_snapshots`,
`automation_delivery_outbox`, `automation_runtime_state`) are ignored.
`session_usage.used` and `.size` are context-window accounting, not session
content.

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
| `message` (`role: user`, compaction flags) | Compaction summary. Parsed into `compact_summary`, never a prompt. |
| `message` (`role: assistant`) | Assistant turn. `content` is a list of `output_text` parts. |
| `function_call` | Tool call. `name` is the tool, `arguments` is a JSON **string**. |
| `function_call_result` | Tool result. Ignored by the digest; `output` may be a dict or a list. |
| `reasoning` | Thinking text in `rawContent`. Ignored. |
| `summary` (`providerData.source: initial-user-message`) | Denormalized initial prompt. First-prompt fallback only. |
| `ai-title` | Generated title in `aiTitle`. Used only when the database has none. |
| `session-meta` | Host metadata. Ignored. |
| `file-history-snapshot` | File backup bookkeeping. Ignored. |

Domestic user records may carry `__codebuddyLocal` (for example
`sensitiveUserInputReviewed: true`). It is a local UI marker, not a meta flag:
those records are real human prompts and are included. The domestic build does
not emit `providerData.startsNewUserRequest`; the fallback is kept for older
builds but was not observed.

Observed tool names match the international build: `Bash`, `Read`, `Edit`,
`Write`, `Grep`, `WebSearch`, `WebFetch`, `TaskCreate`, `TaskUpdate`,
`TaskOutput`, `AskUserQuestion`, `Skill`, `present_files`, `show_widget`, and
`automation_update`. Names are matched case-insensitively for the edited-file
list.

## Prompt extraction

A user record is a human prompt only when all of these hold:

1. `type` is `message` and `role` is `user`.
2. `providerData.isMeta` is not `true`.
3. The record is not a compaction (see below).
4. The text carries a `<user_query>...</user_query>` block, or, for older
   builds, `providerData.startsNewUserRequest: true` with non-empty text after
   system reminders are stripped.

Everything else is agent traffic and is dropped:

| Record shape | Treatment |
| --- | --- |
| `<user_query>...</user_query>` present | Human prompt; the inner text is used. |
| `<system-reminder data-role="user-context">` block only | Excluded. |
| `<task-notification>...</task-notification>` | Excluded; background-task results delivered as user turns. |
| `providerData.isMeta: true` | Excluded. |
| `providerData.compactType` / `isCompacted` / `isSummary` | Excluded; compaction. |
| `<cb_summary>...</cb_summary>` content | Excluded; compaction. |
| `role: assistant`, `reasoning`, `function_call`, `function_call_result` | Excluded. |

The `<system-reminder>` block in front of a prompt contains the environment,
identity files, and memory context; it is stripped rather than truncated, so a
prompt never starts with injected context. A record with several `user_query`
blocks yields one prompt with the blocks joined, and one prompt per record is
yielded overall.

`__codebuddyLocal` records are included. They are ordinary user turns written by
the desktop client, and excluding them would drop real requests; one verified
session had 21 of them.

## Compaction

Domestic transcripts add compaction records that the international build does
not emit. They appear as `message` records whose `providerData` carries
`compactType` (for example `pre-message-auto`), `isCompacted: true`, and
`isCompactInternal: true`, with the summary text wrapped in
`<cb_summary>...</cb_summary>`. That body embeds the previous
`<previous_user_message>` / `<user_query>` blocks.

- `load()` captures the stripped body as `compact_summary`; it does not create a
  turn and does not touch `first_prompt` or `last_prompt`.
- `summarize()` and `iter_prompts()` drop the record entirely, so the embedded
  prior prompts are not counted twice.
- `show` renders the text under `Compact summary (latest compaction)` once the
  wrapper is removed; `--summary-chars 0` omits it.

On a verified compacted domestic session the adapter reports 23 human prompts,
matching the records the user typed, and a non-empty compact summary.

## Initial-prompt summary record

Near the end of a domestic transcript there is a `summary` record with
`providerData.source == "initial-user-message"` and the first user prompt in its
`summary` field. It is a denormalized copy, not a new turn.

The adapter uses it only as a first-prompt fallback when the head slice contains
no human prompt, which happens on long sessions or after compaction. It never
appears in `iter_prompts`, never replaces `last_prompt`, and is not rendered as
a compaction.

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

`turn_count` counts human prompts only. Tool results are never printed; only the
tool name and a short argument excerpt are kept. `output` payloads,
`tool-results/*.txt`, and file snapshots are not read.

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

It never parses assistant text or tool output. `session_id` is the transcript
file stem, which is already the session id, so `workbuddy-cn:d0d0c001` is a
useful eight-character ref. `size_bytes` is the transcript size, which is real
for this harness.

`title` prefers `custom_title`, then `title`, then the first `ai-title` record,
then the latest meaningful prompt.

A zero-byte transcript cannot be summarized and is skipped by listing, search,
and ref resolution. The app creates such placeholders before the first record is
written; they are not sessions yet.

## Archive state

A session is hidden when either condition holds:

- `sessions.status` is `archived`.
- `sessions.deleted_at` is a positive timestamp. A `deleted_at` of `-1` is the
  cloud-transport "never deleted" sentinel and stays active.

The base class also treats `visibility = 'archived'` as hidden when that column
exists, but the domestic schema has no `visibility` column, so that path is
**expected, unverified** for this edition. A missing, unreadable, or
older-schema database degrades to "no archive metadata", so every session is
active. A transcript with no database row stays active.

`SessionSummary.archived` is the only cross-harness signal. The shared CLI
filters archived sessions before search, including `--deep`, and `show` still
opens an archived session by explicit ref or path. Archive state never crosses
into `workbuddy`, `codebuddy`, or any other harness.

## Deep search

`--deep` uses the default per-file scan. It reads the transcript in 4 MB chunks,
normalizes the text once, and requires every query token to appear, so a match in
one session never leaks into another. Because the shared CLI filters archived
sessions first, an archived transcript is not scanned unless
`--include-archived` is passed.

## Known gaps

- `branch` and `version` are empty: the database has no such columns and the
  transcript records do not carry them.
- Tool results, `tool-results/*.txt`, file snapshots, and attachments are not
  rendered.
- The compaction body keeps its own structured markup
  (`<previous_user_message>`, `<user_query>`, `<previous_tool_call>`). Only the
  outer `<cb_summary>` wrapper is removed; the digest renders the body as the
  harness wrote it, bounded by `--summary-chars`.
- Zero-byte placeholder transcripts are skipped rather than listed.
- `traces/` holds OpenTelemetry spans that repeat prompt text; they are ignored
  so prompts are not counted twice.
- `sessions/*.json` is a live process registry, not a session list.
- Playground, background automation, and expert sessions are listed like any
  other session; `source_mode`, `is_playground`, and `expert_*` are ignored.
- No CLI surface was observed; `variants` stays `desktop`.
- Schema drift is the main risk: new record types are ignored rather than
  guessed. If a future build changes the compaction wrapper or drops
  `<user_query>`, prompt extraction degrades to the `startsNewUserRequest`
  fallback or to no prompts.

## Verification

Fixtures are built at runtime by `tests/workbuddy_cn_fixture.py` because the home
mixes JSONL transcripts with a SQLite database. To inspect one manually:

```bash
python3 - <<'PY'
from pathlib import Path
import tempfile
from tests.workbuddy_cn_fixture import build_workbuddy_cn_home
root = Path(tempfile.mkdtemp(prefix="workbuddy-cn-fixture-"))
build_workbuddy_cn_home(root / "home")
print(root / "home")
PY
```

Then point the CLI at that directory:

```bash
export FMS_WORKBUDDY_CN_HOME="/path/from/above"
export FMS_WORKBUDDY_CN_APP_DB="$FMS_WORKBUDDY_CN_HOME/workbuddy.db"
scripts/fms harnesses
scripts/fms search --harness workbuddy-cn --limit 0
scripts/fms search --harness workbuddy-cn --include-archived --limit 0
scripts/fms show workbuddy-cn:d0d0c001
scripts/fms show workbuddy-cn:d0d0c001 --format json
scripts/fms prompts workbuddy-cn:d0d0c001 --count
scripts/fms prompts workbuddy-cn:d0d0c001 --limit 2 --offset 1
scripts/fms prompts workbuddy-cn:d0d0c001 --order newest --limit 2
scripts/fms search --harness workbuddy-cn --deep deep-only-needle
```

Expected: four active sessions by default, six with `--include-archived` (the
zero-byte placeholder and the rollback log are never listed), three prompts for
`workbuddy-cn:d0d0c001`, a rendered compact summary without the `<cb_summary>`
wrapper, and a deep hit only for `workbuddy-cn:d0d0c002`.
