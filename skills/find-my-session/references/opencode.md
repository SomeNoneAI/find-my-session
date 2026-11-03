# OpenCode

## Status

- Implemented (`core/fms_lib/harnesses/opencode.py`), harness name `opencode`.
- Aliases: `opencode`.
- Variants: `cli, tui, ide` — all surfaces share one store and one ref namespace.
- Store: `~/.local/share/opencode` (honors `XDG_DATA_HOME`), override with
  `FMS_OPENCODE_HOME`. No separate app-database override: the database is the
  store.

## Verified against

- macOS arm64, OpenCode 2.2.5, 2026-11-04. 48 top-level sessions listed from
  the live database, all readable, 0 skipped. `show`, prompt count, prompt
  paging (oldest/newest), and `doctor` verified against the live store, and
  the database bytes and mtime were unchanged afterwards.
- No live row had `time_archived` set, so archive filtering is verified by
  the synthetic fixture only.
- Linux is expected to work (same XDG layout) but was not verified.
- Windows store location is unverified; the adapter falls back to the XDG
  path and reports the store as not found.

## Layout

One SQLite database, WAL mode:

- `~/.local/share/opencode/opencode.db` — sessions, messages, parts, todos.
- A legacy pre-database `storage/` directory may exist with older JSON-file
  stores; it is **not** read and those sessions are invisible to `fms`.
- `auth.json`, `log/`, `bin/`, `snapshot/` are ignored.

The schema is the one CodeArts Agent builds on (`session`, `message`,
`part`, `todo`), but 2.2.5 is mid-migration and the adapter follows it:

- `session_v2` is authoritative when present and strictly newer than the
  `session` mirror; the adapter reads `session_v2` and falls back to
  `session` on older stores. One live session existed only in `session_v2`.
- `message` and `part` remain authoritative for content; the extra
  `session_message` mirror may lag the newest message, so it is not read.
- Timestamps are epoch milliseconds.

## Sessions

- Rows in `session_v2`/`session`. `parent_id` set means a subagent run
  (for example the `explore` agent); those rows are never listed, searched,
  or shown as sessions.
- `directory` is the session cwd; `path` is usually empty and is ignored.
- `title` is the stored title; when missing or generic the adapter derives
  the title from the latest meaningful prompt, then the first.
- `model` is a JSON blob `{"id", "providerID", "variant"}`; the adapter uses
  `id`, falling back to the newest assistant message's `modelID`.
- `version` is the OpenCode version string. `cost` and `tokens_*` are not
  surfaced. `size` is always `0` because sessions are rows, not files.
- Archive state is `time_archived IS NOT NULL`; deleted sessions are removed
  from the database and simply disappear.
- `slug` is a random codename (`nimble-wolf`) and is not used.

## Messages and parts

`message.data` is JSON: `role` (`user`/`assistant`), `agent`
(`build`, `plan`, `explore`, `compaction`), `summary`, `error`,
`modelID`, `providerID`, `tokens`. `part.data` is JSON with `type`:

- `text` — visible text; `synthetic: true` marks injected context and is
  always skipped.
- `tool` — `{tool, callID, state:{status, input, output, metadata, title}}`;
  observed tools: `bash`, `edit`, `glob`, `grep`, `read`, `task`,
  `todowrite`. Tool output feeds deep search; `task` spawns subagents whose
  transcripts are the child sessions.
- `patch` — `{files: [...]}`; every path is recorded as an edited file.
- `file` — user attachments; rendered files are ignored.
- `reasoning` — thinking; ignored.
- `step-start`/`step-finish` — ignored.
- `compaction` — `{auto, overflow, tail_start_id}` marker; ignored as
  content.

## Human prompts

A prompt is a `user` message whose non-synthetic `text` parts, joined in
order, survive these filters:

- synthetic parts and synthetic messages are skipped;
- wrapped `<system-reminder>`/`<task-notification>` blocks are stripped;
- pure slash-command wrappers (`/agents`) are rejected;
- known injected markers (`the todowrite tool hasn't been used recently`,
  compaction-continuation preambles) are rejected.

`继续`/`ok`-style generic prompts stay in the prompt listing (they are
human-authored) but never become the title. Ordering is `message.time_created`,
then `part.time_created`, then ids.

## Compaction

A compaction summary is an assistant message with `summary: true` or
`agent`/`mode` `compaction`; its text parts become `compact_summary`. The
`compaction` *part* is only a marker.

## Deep search

`--deep` scans the `message` and `part` rows of that one session only
(`WHERE session_id = ?`), so a match never leaks across sessions. A match
inside tool output — which the head/tail prompt metadata never sees — is a
deep-search hit. The largest observed top-level session carried ~12 MB of
part data; the scan is a bounded per-session pass.

## Digest

`fms show` extracts cwd, started/updated, model, version, the compaction
summary, todos from the `todo` table (`done` is normalized to `completed`),
edited files from `patch` parts and `edit`/`write` tool inputs, tool names
with short details, the last 20 tool calls, and assistant API error text
(quota/auth failures survive). Attachments and reasoning are ignored.

## Known gaps and risks

- The legacy `storage/` JSON store is not read.
- Windows paths are unverified.
- The 2.x schema migration is ongoing upstream; if `session_v2` disappears
  or parts move to `session_part`, the adapter needs an update.
- No archive row was ever observed live, so the `time_archived` semantics
  (set on archive) rest on the column name plus fixture tests.
- Custom command templates that expand into user text without the synthetic
  flag (for example a pasted instruction preamble) appear as prompts.

## Verification recipe

```bash
python3 -c 'import sys; sys.path.insert(0, "tests"); from pathlib import Path; from opencode_fixture import build_opencode_home; build_opencode_home(Path("tmp/opencode-home"))'
export FMS_OPENCODE_HOME="$PWD/tmp/opencode-home"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness opencode
skills/find-my-session/scripts/fms search --harness opencode --deep oc-deep-only-needle
skills/find-my-session/scripts/fms show opencode:0adc0001
skills/find-my-session/scripts/fms prompts opencode:0adc0001 --count
skills/find-my-session/scripts/fms prompts opencode:0adc0001 --order newest --limit 2
skills/find-my-session/scripts/fms doctor --harness opencode
```

Then repeat against the live store with `FMS_OPENCODE_HOME` unset and record
the version, platform, and date in the compatibility matrix.
