# Antigravity CLI

## Status

| Item | Value |
| --- | --- |
| Status | Ready |
| Adapter | `scripts/fms_lib/harnesses/antigravity_cli.py`, shared parser `antigravity_family.py` |
| Harness name | `antigravity-cli` |
| Aliases | `antigravity-cli`, `agy` |
| Variants | `cli` |
| Store | `~/.gemini/antigravity-cli` |
| Home override | `FMS_ANTIGRAVITY_CLI_HOME` |
| Verified | macOS arm64, `agy` 1.4.9, 2026-10-29 |

The Antigravity CLI keeps its own conversation store. It is not a variant of
the desktop harness: refs, archive state, and session ids never resolve across
the two stores. The record format, metadata schema, and brain transcript layout
are the same, so both harnesses share `antigravity_family.py`.

## Store layout

```text
~/.gemini/antigravity-cli/
├── conversation_summaries.db            # metadata; no archive index
├── conversations/
│   └── <conversation uuid>.db           # one SQLite database per session
├── brain/
│   └── <conversation uuid>/.system_generated/logs/
│       ├── transcript_full.jsonl
│       └── transcript.jsonl
├── history.jsonl                        # command history, not a session
└── jetbox_summaries_proto.pb            # protobuf cache, not a session
```

`session_id` is the `conversations/<uuid>.db` stem, so
`antigravity-cli:c11a2b01` is the usual short ref. The source path printed by
`show` is the per-conversation database. `size_bytes` is its size.

## Differences from the desktop harness

| Area | Desktop | CLI |
| --- | --- | --- |
| Archive state | `conversations_fts.archived` aggregate | none; every session active |
| Legacy transcript root | `~/.gemini/antigravity-ide` for migrated sessions | none |
| Entrypoint | `desktop`, or `ide` for migrated sessions | `cli` |
| Variants | `desktop, ide` | `cli` |

Because the CLI summaries database has no `conversations_fts` table, the
adapter never sets `archived`; `--include-archived` changes nothing. The CLI
store also has no migrated-IDE sessions, so every listed session reads its
transcript from the CLI brain root and reports the `cli` entrypoint.

## Session selection

A row is listed only when `conversations/<uuid>.db` exists. Summary rows
without a local database, such as stale or imported rows, are skipped. Nested
conversations (`nesting_depth > 0` or a non-empty `parent_conversation_id`) are
excluded. Brain directories without a database are never listed.

`history.jsonl` and `jetbox_summaries_proto.pb` are supporting caches. They are
never sessions and are never scanned by `--deep`.

## Records, prompts, titles, and digest

The transcript and metadata formats match the desktop harness:

- `USER_INPUT` records with an explicit user source become prompts; the text
  inside `<USER_REQUEST>` is kept and injected context blocks are removed.
- `PLANNER_RESPONSE` supplies assistant text and tool calls.
- `CHECKPOINT` checkbox plans become todos.
- Titles prefer the metadata title, then non-generic prompts, then the
  preview, then the id.
- `summarize()` reads a bounded head and tail; `load()` streams the transcript
  once and keeps bounded exchanges, assistant text, tools, and edited files.
- `iter_prompts()` streams the full transcript, so the truncated
  `transcript.jsonl` never adds prompts when the full file exists.
- `compact_summary` is always empty.

See `references/antigravity.md` for the full record and digest description.

## Search and deep search

Keyword search uses the metadata title, cwd, and the first and last prompts.
`--deep` scans `transcript_full.jsonl`, then `transcript.jsonl`, then the raw
per-conversation database bytes when no transcript exists. All tokens must
appear in one session. The CLI orphan brain directories, `history.jsonl`, and
the protobuf cache are never scanned.

## Known gaps

- No archive or delete metadata; a removed database simply disappears.
- Metadata-only sessions have no prompts or turns.
- Model, branch, and version are not available.
- No compaction metadata is parsed.
- The CLI summaries database carries no FTS index, so there is no full-text
  metadata to reuse; deep search reads transcripts directly.

## Verification

Fixtures are built at runtime by `tests/antigravity_fixture.py`.

```bash
python3 - <<'PY'
from pathlib import Path
import tempfile
from tests.antigravity_fixture import build_antigravity_cli_home
root = Path(tempfile.mkdtemp(prefix="antigravity-cli-fixture-"))
build_antigravity_cli_home(root / "home")
print(root)
PY
```

```bash
export FMS_ANTIGRAVITY_CLI_HOME="/path/from/above/home"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness antigravity-cli --limit 0
skills/find-my-session/scripts/fms show antigravity-cli:c11a2b01
skills/find-my-session/scripts/fms prompts antigravity-cli:c11a2b01 --count
skills/find-my-session/scripts/fms search --harness antigravity-cli --deep cli-deep-only-needle
```

Expected: four active sessions, newest first; the archive column is always `-`;
`c11a2b01` shows three prompts, its edited `docs/rollout.md`, and
`run_command`/`write_to_file` tool counts; `c11a2b02` falls back to its prompt
as the title; `c11a2b04` has metadata but no prompts; the deep needle matches
only `c11a2b01`; and the short-transcript, history, protobuf, and orphan-brain
decoys never match.
