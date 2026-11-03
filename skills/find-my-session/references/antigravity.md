# Antigravity

## Status

| Item | Value |
| --- | --- |
| Status | Ready |
| Adapter | `scripts/fms_lib/harnesses/antigravity.py`, shared parser `antigravity_family.py` |
| Harness name | `antigravity` |
| Aliases | `antigravity`, `antigravity-desktop`, `antigravity-ide` |
| Variants | `desktop, ide` |
| Store | `~/.gemini/antigravity` |
| Legacy transcript root | `~/.gemini/antigravity-ide` |
| Home overrides | `FMS_ANTIGRAVITY_HOME`, `FMS_ANTIGRAVITY_IDE_HOME` |
| Verified | macOS arm64, Antigravity 2.28.0 and Antigravity IDE 2.6.0, 2026-10-29 |

The desktop app and the retired IDE edition share one conversation store.
Every IDE conversation was migrated into the desktop store byte for byte, and
the IDE has not written a session since 2026-07-29. The adapter therefore
exposes one harness and one ref namespace. The IDE store is read only as a
legacy companion for the brain transcripts of migrated sessions.

The Antigravity CLI (`agy`) keeps a separate store and is the separate
`antigravity-cli` harness, documented in `references/antigravity-cli.md`.

## Store layout

```text
~/.gemini/antigravity/
├── conversation_summaries.db            # metadata + archive index
├── conversations/
│   └── <conversation uuid>.db           # one SQLite database per session
└── brain/
    └── <conversation uuid>/
        └── .system_generated/
            └── logs/
                ├── transcript_full.jsonl    # authoritative readable transcript
                └── transcript.jsonl         # truncated variant

~/.gemini/antigravity-ide/
└── brain/
    └── <conversation uuid>/.system_generated/logs/...
```

`session_id` is the `conversations/<uuid>.db` stem, so
`antigravity:a17e5a01` is the usual short ref. The source path printed by
`show` is the per-conversation database; brain transcripts are not session
roots and cannot be passed to `show` directly. `size_bytes` is the
per-conversation database size.

### Metadata database

`conversation_summaries.db` has one `conversation_summaries` row per
conversation. The adapter reads:

| Column | Use |
| --- | --- |
| `conversation_id` | Session id. |
| `title` | Preferred title. |
| `preview` | Title fallback. |
| `last_modified_time` | `updated`, as `YYYY-MM-DD HH:MM:SS+00:00`. |
| `workspace_uris` | JSON list of `file://` URIs; the first path is `cwd`. |
| `nesting_depth`, `parent_conversation_id` | Nested-session exclusion. |
| `project_id` | Empty means the row came from the IDE migration. |

Missing columns degrade to empty values; a missing or unreadable database
degrades to transcript-only metadata.

The desktop database also carries an FTS5 table, `conversations_fts`, with one
row per transcript chunk and an `archived` column. A conversation is archived
when `MAX(CAST(archived AS INTEGER))` over its chunks is greater than zero.
The adapter reads that aggregate and nothing else from the FTS table. The
Antigravity CLI summaries database has no FTS table, which is why the CLI
harness reports every session as active.

## Session selection

A row is listed only when `conversations/<uuid>.db` exists. The metadata
database is indexed by the desktop app and can contain rows without a local
database, notably CLI conversations and stale summaries; those rows are
skipped. A database without a summary row is still listed from its transcript
metadata.

Nested conversations are excluded when `nesting_depth > 0` or
`parent_conversation_id` is non-empty. These are teamwork and subagent child
conversations and never become sessions. Brain directories without a matching
database, including orphaned directories, are never listed.

Listing order is the database file name; the shared CLI re-sorts results by
`updated`, so `search` shows the newest conversation first.

## Transcript records

Each line of `transcript_full.jsonl` is one JSON object with `type`,
`source`, `created_at`, and usually `content`. Timestamps are ISO 8601.

| `type` | Read as |
| --- | --- |
| `USER_INPUT` with `source` empty or `USER_EXPLICIT` | Human prompt. The content wraps the typed text in one `<USER_REQUEST>...</USER_REQUEST>` block. |
| `PLANNER_RESPONSE` | Assistant `content`, optional `thinking`, and `tool_calls`. |
| `GENERIC` | Executor or tool text. Not a prompt and not rendered. |
| `CHECKPOINT` | Markdown plan; `- [x]` and `- [ ]` lines become todos. |
| `SYSTEM_MESSAGE`, `ERROR_MESSAGE` | Bookkeeping. Ignored. |

`<ADDITIONAL_METADATA>`, `<USER_SETTINGS_CHANGE>`, and `<SKILL>` blocks are
injected context outside the request wrapper and are removed before a prompt
is stored. A `USER_INPUT` with any other `source` value is not a human prompt.

Tool calls are `{"name": "...", "args": {...}}`. The human-readable detail
comes from `toolSummary` or `toolAction`, with command, query, and path fields
as fallbacks. Edit tools are `write_to_file`, `write_file`,
`replace_file_content`, and `edit_file`; their `TargetFile`, `Path`, or
`AbsolutePath` argument becomes an edited file. Relative paths are resolved
against the session cwd.

## Prompt extraction

`iter_prompts` streams the full transcript in order and yields every
`USER_INPUT` record whose source is empty or `USER_EXPLICIT`. Nothing is capped,
paged, or deduplicated; the shared CLI owns counting, ordering, paging, and
`--chars`. When both `transcript_full.jsonl` and `transcript.jsonl` exist, only
the full file is read, so the truncated variant can never add prompts.

## Titles

The title is the first non-generic of:

1. `conversation_summaries.title`.
2. The latest non-generic prompt, then the first non-generic prompt.
3. `conversation_summaries.preview`.
4. The latest prompt, then the session id.

Empty prompts, single characters, punctuation or digits only, and generic
continuations such as `continue`, `next`, `ok`, or `继续` are non-titles.

## Digest

`summarize()` reads a 400 KB / 600-record head and a 400 KB tail of the
transcript for the first and last prompts, the first record timestamp, and the
title fallback. `started` is the first record time; `updated` is
`last_modified_time` with a transcript and file-mtime fallback. Model, branch,
and version are empty because neither store records them.

`load()` streams the full transcript once:

- Up to 50 recent exchanges, one per human prompt.
- Up to three assistant text blocks per exchange, 5,000 characters each.
- Up to eight tools per exchange and 20 recent tools overall.
- Edited files keyed by absolute path with a count, capped at 30.
- Tool counts by tool name.
- Todos from the last `CHECKPOINT` record that contains checkbox lines.

There is no verified Antigravity compaction record, so `compact_summary` stays
empty. A checkpoint plan is rendered as todos, never as a prompt or summary.

## Search and deep search

Keyword search uses the metadata title, cwd, and the first and last prompts.
The first `workspace_uris` path becomes `cwd`, and `--cwd` matches that path.

`--deep` scans, per session:

1. `transcript_full.jsonl` when present.
2. `transcript.jsonl` otherwise.
3. The raw per-conversation database bytes when no transcript exists.

All query tokens must appear in one session. Subagent transcript files,
`history.jsonl`, `jetbox_summaries_proto.pb`, orphan brain directories, and
IDE-only conversations are never scanned. A session with a transcript is never
deep-scanned through its database, so internal database payloads cannot create
false matches for normal sessions.

## Archive state

The desktop store records archived conversations in `conversations_fts`. The
adapter sets `SessionSummary.archived` from that aggregate; the shared CLI
excludes archived sessions from search, latest, and deep search unless
`--include-archived` is passed. An explicit `show` or `prompts` by ref still
opens an archived session and marks it. There is no deleted-session flag; a
conversation leaves the listing only when its per-conversation database is
removed.

## Known gaps

- IDE-only conversations are not listed; the IDE is retired and only migrated
  sessions whose databases live in the desktop store are visible.
- Migrated IDE sessions use the desktop database as their source path while
  their transcript is read from the legacy IDE home.
- Metadata-only sessions have no prompts, no turns, and no transcript digest.
- Nested teamwork conversations are excluded from listing and reference
  lookup, but an explicit path to their database still summarizes the session.
- Model, branch, and version are not available.
- No compaction metadata is parsed, so `compact_summary` is always empty.
- `CHECKPOINT` plans are the only todo source; older checkpoints are replaced
  by the newest one that contains checkboxes.
- The WAL-mode metadata database sometimes has no `-shm` file. The adapter
  retries the connection with `immutable=1`, which is read-only and creates
  no store files.

## Verification

Fixtures are built at runtime by `tests/antigravity_fixture.py`.

```bash
python3 - <<'PY'
from pathlib import Path
import tempfile
from tests.antigravity_fixture import (
    build_antigravity_home,
    build_antigravity_ide_home,
)
root = Path(tempfile.mkdtemp(prefix="antigravity-fixture-"))
build_antigravity_home(root / "home")
build_antigravity_ide_home(root / "ide")
print(root)
PY
```

```bash
export FMS_ANTIGRAVITY_HOME="/path/from/above/home"
export FMS_ANTIGRAVITY_IDE_HOME="/path/from/above/ide"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness antigravity --limit 0
skills/find-my-session/scripts/fms search --harness antigravity --include-archived --limit 0
skills/find-my-session/scripts/fms show antigravity:a17e5a01
skills/find-my-session/scripts/fms show antigravity:a17e5a04 --format json
skills/find-my-session/scripts/fms prompts antigravity:a17e5a01 --count
skills/find-my-session/scripts/fms prompts antigravity:a17e5a01 --order newest --limit 2
skills/find-my-session/scripts/fms search --harness antigravity --deep antigravity-deep-only-needle
```

Expected: four active sessions, newest first; `a17e5a02` appears only with
`--include-archived` and is marked `yes`; `a17e5a01` shows four prompts, two
open todos, edited files, and tool counts; `a17e5a04` reports the `ide`
entrypoint and reads its transcript from the legacy home; `a17e5a06` has
metadata and a source path but no prompts; the deep-only needle matches only
`a17e5a07`; and the nested, orphan-summary, IDE-only, subagent, and database
decoy needles never match.
