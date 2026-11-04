# Cursor

## Status

| Item | Value |
| --- | --- |
| Status | Ready |
| Adapter | `core/fms_lib/harnesses/cursor.py` |
| Harness name | `cursor` |
| Aliases | `cursor`, `cursor-agent`, `cursor-ide` |
| Variants | `desktop, cli` |
| Store | `~/.cursor/projects` |
| Home override | `FMS_CURSOR_HOME` |
| Index database override | `FMS_CURSOR_APP_DB` |
| Workspace manifests override | `FMS_CURSOR_WORKSPACE_STORAGE` |
| Verified | macOS arm64, Cursor 3.23.23 desktop app, 2026-11-03 |

Cursor 3.x keeps one JSONL transcript per agent conversation under
`~/.cursor/projects/<project>/agent-transcripts/<session-id>/<session-id>.jsonl`.
The desktop app also maintains a conversation index at
`User/globalStorage/conversation-search.db` that carries the title, the
last-update timestamp, the git branch, and the archive flag.

The desktop app is the verified surface. The `cursor-agent` CLI shares the same
`~/.cursor` runtime directory and the same transcript layout, so it is listed
under the same harness, but no CLI-originated transcript was observed on the
verification machine.

## Store layout

```text
~/.cursor/
└── projects/
    └── <project-dir>/
        ├── agent-transcripts/
        │   └── <session-id>/
        │       ├── <session-id>.jsonl      # the conversation transcript
        │       └── subagents/<child-id>.jsonl   # delegated child transcripts
        ├── canvases/, mcps/, terminals/     # not read
        └── agent-notes/, agent-tools/       # not read
```

The desktop app's metadata lives beside the store:

```text
~/Library/Application Support/Cursor/User/
├── globalStorage/
│   ├── conversation-search.db              # conversation index (titles, archive)
│   └── state.vscdb                         # not read
└── workspaceStorage/
    └── <hash>/workspace.json               # {"folder": "file:///path"}
```

### The project directory name

`<project-dir>` is a lossy encoding of the workspace folder:

```text
non-alphanumeric characters -> "-"
runs of "-"                -> "-"
leading/trailing "-"       -> removed
```

So `/Volumes/SomeNone/git/mine/find-my-session` becomes
`Volumes-SomeNone-git-mine-find-my-session`. The encoding cannot be inverted:
`a-b/c` and `a/b-c` both encode to `a-b-c`.

Two other names appear in practice and carry no folder:

- `empty-window` — the app was used without any folder open.
- A bare millisecond timestamp — a transient window that has no stable folder.

### Recovering the real cwd

Because the project directory name is lossy, the adapter resolves the cwd from
the desktop app's `workspaceStorage/<hash>/workspace.json` manifests: it
encodes every known `folder` URI with the same function and matches the
result against the project directory name. A match yields the exact folder
path; without a match the session has an empty cwd, and `--cwd` will not match
it. `empty-window` and timestamp-named projects therefore have no cwd, which
is correct: those sessions really did not run in a folder.

`workspaceStorage` is pruned by the editor over time, so an old workspace may
no longer be listed and its sessions lose their cwd.

## Conversation index

`conversation-search.db` is opened read-only through a SQLite URI
(`file:...?mode=ro`). The `conversations` table holds one row per conversation:

| Column | Use |
| --- | --- |
| `id` | Session id; matches the transcript directory name. |
| `title` | Stored title. `General chat` and `General chat conversation` are Cursor's placeholder titles and are treated as no title. |
| `branches` | JSON array of branch names; the first one becomes `branch`. |
| `updated_at` | Epoch milliseconds; becomes `updated`. |
| `is_archived` | Non-zero means the conversation is archived. |
| `source`, `scope`, `root_fingerprint`, `cache_fingerprint` | Not used. |

The database is a live WAL store while the app runs. It is read, never
written; the app itself may advance the WAL independently.

A missing, locked, unreadable, or older-schema database degrades to "no index
metadata": every session stays active, the title falls back to the transcript,
and `updated` falls back to the transcript's modification time.

## Transcript format

Each line of the JSONL transcript is one record.

### Message records

```json
{"role": "user", "message": {"content": [{"type": "text", "text": "..."}]}}
{"role": "assistant", "message": {"content": [
  {"type": "text", "text": "..."},
  {"type": "tool_use", "name": "read_file", "input": {"file_path": "..."}}
]}}
```

Only `text` and `tool_use` parts are written to the transcript. Tool results,
images, files, reasoning, and redacted reasoning are dropped by Cursor before
the transcript is written, so they are never rendered.

### Turn records

```json
{"type": "turn_ended", "status": "success"}
{"type": "turn_ended", "status": "error", "error": "Named models unavailable ..."}
```

The `error` text explains quota and plan failures, so it is kept and appended
to the digest as `Turn ended: error: ...`.

### Metadata records

```json
{"type": "metadata", "metadata": {"overview": "Summary of the conversation so far: ..."}}
```

The overview is Cursor's own compaction summary and becomes `compact_summary`.

### JSON transcripts

Cursor can also write a pretty-printed `<session-id>.json` next to the JSONL
file, with a `messages` array of `{role, text, toolCalls, toolResult}` objects
and a `turnEnded` object. The adapter reads both shapes; the JSONL file wins
when both exist.

## Prompt extraction

Cursor wraps a typed request in `<user_query>` and keeps injected context in
sibling tags:

```text
<timestamp>Tuesday, Nov 3, 2026, 2:57 PM (UTC+8)</timestamp>
<user_query>
hi
</user_query>
```

A human prompt is the content of a `<user_query>` block in a `role: "user"`
message. Everything else is excluded:

- Messages with no `<user_query>` block, which carry injected context such as
  `<system_reminder>`, `<git_status>`, `<mcp_instructions>`, or
  `<agent_notification>`.
- `<summary_request>` blocks, which are Cursor's compaction requests.
- `role: "assistant"` messages and `role: "system"` messages, which Cursor
  never writes to the transcript.
- Tool results, which are not written to the transcript at all.

The `<timestamp>` wrapper carries the moment the request was sent. The adapter
parses the observed `Weekday, Month D, YYYY, H:MM AM/PM (UTC±H)` form, plus
plain ISO 8601, and normalizes to UTC. The wrapper is removed from the prompt
text.

`iter_prompts()` yields each human prompt once, in transcript order. The
shared CLI owns counting, paging, ordering, and character caps.

## Digest

`load()` streams the transcript once and retains bounded state:

- Up to 50 recent exchanges.
- Up to three assistant text blocks per exchange, 5,000 characters each.
- Up to eight tools per exchange and 20 recent tools overall.
- Edited files from tool calls whose name contains `edit`, `write`, `create`,
  or `delete`, with relative paths resolved against the session cwd, capped at
  30.
- Todos from a `todo_write` tool call whose input carries a `todos` array;
  `done` is normalized to `completed`.
- The compaction summary from the `metadata` record.
- The turn error text.

`<think>` and `<thinking>` blocks are stripped from assistant text.

## Listing and search

`iter_session_paths()` walks `projects/*/agent-transcripts/*/*.jsonl` and
`*.json`, newest first by modification time. Two paths are never listed:

- Anything under a `subagents/` directory. Cursor stores a delegated child
  conversation at `agent-transcripts/<parent-id>/subagents/<child-id>.jsonl`,
  and that child is part of its parent's turn, not a resumable session.
- Anything outside `agent-transcripts/`, such as `canvases/`, `mcps/`, and
  `terminals/`.

`summarize()` merges the index row with the transcript. The title prefers the
stored title, then the latest meaningful prompt, then the first; generic
prompts such as `继续`, `ok`, and `?` never become titles. `model` and
`version` stay empty: the local store records neither.

## Archive state

`conversations.is_archived` is authoritative. Archived conversations are
excluded from `search` and `latest` by the shared CLI, and `--deep` never
scans them unless `--include-archived` is passed. `show` and `prompts` still
open an archived session by explicit ref or path and print `- archived: yes`.

Cursor has no separate deleted flag: a deleted conversation leaves the index.

## Resume

Verified: cursor-agent --resume [chatId] reopens a session (--continue resumes the most recent). fms resume prints cursor-agent --resume <id>.

## Deep search

`--deep` scans the session's own transcript file. Because the scan is keyed by
the session's file, a match in one session never leaks into another, and
subagent or stray files are never scanned because they are not sessions.

## Known gaps

- `model` and `version` are empty; the local store records neither. The
  Cursor app version is not read from `state.vscdb`.
- The cwd is empty when the workspace manifest is gone or the session ran
  without a folder. The project directory name alone cannot be inverted.
- The `cursor-agent` CLI is expected to share this store and ref space, but no
  CLI-originated transcript was observed during verification.
- Cursor's `.txt` human-readable transcript and the `.json` transcript were
  not observed in the live store. The `.json` shape is read when present; the
  `.txt` shape is not.
- Attachments, images, and tool-result payloads are ignored.
- The index is a live WAL store. `fms` never writes to it, but the app may
  advance the WAL on its own.
- Schema drift is the main risk: unknown record types and content parts are
  ignored rather than guessed.
- Cursor's older Composer chat store (`composer.composerData` in
  `state.vscdb`) is a different format and is not read by this adapter. It was
  not present in the verified 3.23.23 store.

## Verification

Fixtures are generated at runtime by `tests/cursor_fixture.py` because the store
mixes JSONL transcripts with a SQLite index.

```bash
python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "tests")
from cursor_fixture import build_cursor_home
root = Path("/tmp/cursor-fixture")
build_cursor_home(root)
print(root)
PY

export FMS_CURSOR_HOME="/tmp/cursor-fixture"
export FMS_CURSOR_APP_DB="$FMS_CURSOR_HOME/User/globalStorage/conversation-search.db"
scripts/fms harnesses
scripts/fms search --harness cursor --limit 0
scripts/fms search --harness cursor --include-archived --limit 0
scripts/fms search --harness cursor --deep cursor-deep-only-needle
scripts/fms show cursor:f1c00001
scripts/fms show cursor:f1c00001 --format json
scripts/fms prompts cursor:f1c00001 --count
scripts/fms prompts cursor:f1c00001 --limit 2 --offset 1
scripts/fms prompts cursor:f1c00001 --order newest --limit 2
scripts/fms doctor --harness cursor
```

Expected: four active sessions by default, six with `--include-archived` (the
two extra rows are marked `yes`), four prompts for `cursor:f1c00001`, and a
deep hit only for `cursor:f1c00002` for the synthetic deep needle. Removing
the index database makes every session active.
