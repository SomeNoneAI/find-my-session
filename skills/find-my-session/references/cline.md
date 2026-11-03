# Cline

## Status

| Item | Value |
| --- | --- |
| Status | Ready |
| Adapter | `scripts/fms_lib/harnesses/cline.py` |
| Harness name | `cline` |
| Aliases | `cline` |
| Variants | `desktop, cli` |
| Store | `~/.cline/data/sessions` |
| Home override | `FMS_CLINE_HOME` |
| Verified | macOS, Cline CLI 3.0.74, 88 sessions, 2026-10-29 |

The Cline desktop app and the Cline CLI write the same store under `~/.cline`
and share one session-id namespace, so they are a single harness. Only the CLI
entrypoint (`source: "cli"`) was observed in the verified store; desktop
metadata beyond the shared transcript shape is **unverified**.

The Cline VS Code extension uses a completely separate store
(`globalStorage/saoudrizwan.claude-dev/tasks`) with a different transcript
format. It is a separate planned harness, `cline-vscode`, and is **not** read by
this adapter.

## Store layout

```text
~/.cline/
├── data/
│   ├── sessions/
│   │   └── <session id>/
│   │       ├── <session id>.json            # metadata (source, cwd, model, ended_at)
│   │       ├── <session id>.messages.json   # pretty-printed transcript
│   │       ├── <session id>.compaction.json # optional compaction snapshot
│   │       └── <agent>__<id>.messages.json  # subagent/team transcript, ignored
│   ├── db/                                  # app databases, never opened
│   ├── cache/, logs/, settings/, workspaces/
│   └── checkpoint-scratch/
├── apps/, skills/, tasks/, worktrees/       # ignored
└── cron/
```

The adapter lists only directories whose `<dir>/<dir>.messages.json` exists.
A `.messages.json` file whose stem differs from its directory name is a
subagent or team transcript and is never listed. Directories without a
canonical messages file are ignored. `data/db` is never opened, so no WAL or
SHM side effects can occur.

`session_id` is the directory name, for example
`session_1793000000100_c1a0d` or, for older CLI runs, `1789522544503_myk3h`.
The timestamp prefix is not stable across versions, so refs use the trailing
suffix instead: `cline:c1a0d`. Prefix lookups accept the raw id, the id without
`session_`, and the suffix.

`size_bytes` is the size of the `.messages.json` file. The metadata `.json` and
compaction `.json` sizes are not included.

## Messages file

The file is a single pretty-printed JSON object:

| Field | Read as |
| --- | --- |
| `updated_at` | Fallback timestamp when message `ts` values are missing. |
| `sessionId`, `agent`, `origin` | Identity and subagent markers. |
| `messages` | Ordered list of message objects. |
| `system_prompt` | Ignored. |

Each message has `id`, `role`, `content` (a list of blocks), `ts` (epoch
milliseconds), and usually `modelInfo` for assistant messages.

| Block / role | Read as |
| --- | --- |
| `user` + `text` with `<user_input mode="act\|yolo">…</user_input>` | Human prompt. |
| `user` + `tool_result` | Tool output. Never a prompt. |
| `user` + `[SYSTEM]`, `System-delivered …`, `Your previous response was cut off…` | Injected context. Never a prompt. |
| `user` + `Context summary:` | Injected compaction summary. Never a prompt. |
| `assistant` + `text` | Assistant text for the digest. |
| `assistant` + `tool_use` | Tool name and `input` for tool counts and edited files. |
| `assistant` + `thinking` | Ignored, but still scanned by `--deep`. |

## Prompt extraction

A message becomes a human prompt only when all of these hold:

1. `role` is `user`.
2. `content` contains no `tool_result` block.
3. At least one `text` block is non-empty after cleaning.
4. The text is not an injected prefix and does not start with `Context summary:`.

`iter_prompts` streams the whole file in transcript order, extracting the inner
text of every `<user_input>` wrapper and applying no generic-prompt filter.
Title selection alone skips generic prompts such as `继续`, `continue`, or `ok`.

## Compaction

When Cline compacts a session it writes `<session id>.compaction.json` next to
the transcript. Its `messages` array starts with a user message whose text
begins with `Context summary:`. The adapter reads the first such message as
`compact_summary` and renders it under `Compact summary (latest compaction)`.

The compaction snapshot may describe more source messages
(`source_message_count`) than the current messages file retains, because the
main transcript is trimmed after compaction. Deep search therefore scans both
the messages file and the compaction file, and a token found only in the
compaction snapshot still matches the session.

## Subagents and teams

Team runs write `<agent>__<id>.messages.json` into the **parent** session
directory, with `agent: "teammate"`, `taskType: "team"`, and
`origin.parentThreadId` pointing at the parent. In the verified store these
files coexist with the parent transcript. They are excluded from listing,
search, ref resolution, prompt counting, and deep search. Opening one by path
fails with `Cline subagent transcript is not a resumable session`.

## Titles

`title` prefers `metadata.title` from the session `.json`. When that is absent
or generic, it falls back to the latest meaningful prompt, then the first
prompt, then the session id.

## Listing and search

`summarize()` uses bounded reads:

- One streaming head pass of 1 MB or 400 messages for the first prompt and the
  first message timestamp.
- One tail pass of 1 MB for the latest prompt and timestamp. If no human prompt
  is found in that window, it retries at 4 MB and then 16 MB so the tail prompt
  is not lost when trailing messages carry large tool output.
- The metadata `.json` file (typically under 2 KB) for title, cwd, model,
  branch, version, `source`, and timestamps.

The parser locates the `"messages": [` line and decodes objects incrementally,
so pretty-printed JSON is never loaded whole. `started_at` and `ended_at` from
the metadata win; `updated_at` in the messages head and the last message `ts`
are fallbacks.

`--deep` scans the transcript bytes and the compaction bytes with the shared
UTF-8 matcher. Subagent files in the same directory are not scanned. Because
only one session directory is read per summary, a match cannot leak across
sessions.

## Archive state

The verified Cline store has no archive or deleted flag in session metadata,
and `data/db/sessions.db` has no archive or deleted columns either. Every
session is reported as active (`archived: false`). `--include-archived` changes
nothing, and a removed session directory disappears from listings.

## Digest

`load()` streams the messages file once and retains bounded state:

- Up to 50 recent exchanges.
- Up to three assistant text blocks per exchange, 5,000 characters each.
- Up to eight tools per exchange and 20 recent tools overall.
- Edited files from the `editor` tool input, keyed by normalized path with a
  count, capped at 30. Relative paths are resolved against the session cwd.
- The latest compaction summary when a `.compaction.json` file exists.

Tool results, thinking blocks, injected context, and subagent transcripts are
not rendered. Cline has no todo file for these sessions, so `todos` is always
empty; `show` prints no todos section. `turn_count` counts human prompts only.
`show` prints no archive line because the flag is never true.

## Known gaps

- No archive or deleted-session metadata; only missing directories signal
  deletion.
- Desktop-side metadata beyond the shared transcript and `.json` fields is
  unverified.
- The VS Code extension store is a different format and is not supported here;
  it stays planned as `cline-vscode`.
- Todos are not available for CLI/desktop sessions.
- `data/db` tables (schedules, subagent queue, status) are ignored on purpose;
  the adapter is file-based and read-only.
- The 1 MB / 400-message head can miss a first prompt only in pathological
  files whose first user message follows more than 1 MB of other messages.
- Attachments, images, and thinking blocks are ignored by the digest, though
  `--deep` still scans their bytes.

## Verification

Fixtures are built at runtime by `tests/cline_fixture.py`.

```bash
python3 - <<'PY'
from pathlib import Path
import tempfile
from tests.cline_fixture import build_cline_home
root = Path(tempfile.mkdtemp(prefix="cline-fixture-"))
build_cline_home(root / "home")
print(root)
PY
```

```bash
export FMS_CLINE_HOME="/path/from/above/home"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness cline --limit 0
skills/find-my-session/scripts/fms search --harness cline --include-archived --limit 0
skills/find-my-session/scripts/fms show cline:c1a0d
skills/find-my-session/scripts/fms show cline:c1a0g --format json
skills/find-my-session/scripts/fms prompts cline:c1a0d --count
skills/find-my-session/scripts/fms prompts cline:c1a0d --order newest --limit 2
skills/find-my-session/scripts/fms search --harness cline --deep cline-deep-only-needle
skills/find-my-session/scripts/fms search --harness cline --deep cline-compaction-only-needle
```

Expected: four active sessions; archive columns all `-`; `c1a0d` shows four
prompts, edited files, and tool counts; `c1a0g` shows the compaction summary;
the deep-only and compaction-only needles match only their sessions; and the
subagent needle never matches.
