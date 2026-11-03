# Qoder (international) session store

Status: ready. Adapter: `scripts/fms_lib/harnesses/qoder.py`. Harness name: `qoder`. Aliases: `qoder-intl`, `qoder-global`, `qoder-international`.

This document describes international Qoder. Qoder CN is a separate product with its own store (`~/.qoder-cn`) and its own adapter; see `qoder-cn.md`. The two share a transcript schema but never share session ids, refs, or environment overrides. Always pass the harness name when a user mentions one edition.

## Variants

Qoder international ships as a desktop/IDE application and as a CLI. The observed desktop build is `0.4.11` with agent version `1.1.75-hotfix.1`, writing `~/.qoder`.

There is no international `qoder` CLI installed on the verification machine, so CLI storage is unverified. The CN pair (`qoderclicn` plus desktop) shares one store, and the international CLI is expected to use `~/.qoder` as well. State desktop/IDE as verified and CLI as expected, not confirmed.

`entrypoint` is present on transcript records but has been observed as `cli` even for desktop-originated sessions. Do not use it to identify the surface.

The store location can be overridden for tests or non-standard installs:

```bash
export FMS_QODER_HOME=/path/to/qoder-home
```

The override points at the directory that contains `projects/` and `tasks/`. It is deliberately separate from `FMS_QODER_CN_HOME`, so a fixture or test cannot accidentally read the other edition.

## Layout

```text
~/.qoder/
├── projects/
│   ├── <encoded-cwd>/
│   │   ├── <session-uuid>.jsonl
│   │   ├── <session-uuid>/
│   │   │   ├── state.json
│   │   │   └── compression-v2/
│   │   └── transcript/
│   │       └── task-<task-id>.session.execution.jsonl
│   ├── canvases/
│   └── memory/
└── tasks/
    └── <session-uuid>/
        ├── 1.json
        ├── 2.json
        └── ...
```

- `projects/<encoded-cwd>/<session-uuid>.jsonl` is the transcript. The adapter globs `projects/*/*.jsonl`, which matches only top-level session files.
- `<encoded-cwd>` replaces path separators with `-`; read `cwd` from the transcript instead of reversing it. A project directory named `-` can exist and contains only task transcripts.
- `projects/<encoded-cwd>/<session-uuid>/` holds per-session state such as `state.json` and `compression-v2/`. Not used by the adapter.
- `projects/<encoded-cwd>/transcript/task-<task-id>.session.execution.jsonl` holds subagent/task execution logs. They use a different record schema (`session_meta`, `progress`, `user`, `assistant`) and are not resumable top-level sessions. The adapter excludes them, including from `--deep`.
- `tasks/<session-uuid>/<n>.json` stores todos, same schema as Qoder CN. The directory is often empty.
- Session ids are UUIDs. `fms` refs use the first eight characters, for example `qoder:3f2a9c1d`.

## Archive metadata

Archive state is not stored in the transcript or under `~/.qoder`. The desktop app keeps it in its own Electron SQLite database:

```text
~/Library/Application Support/com.qoder.app.stable/main.sqlite   # macOS, current app
```

The adapter reads `chat_sessions` read-only (`file:...?mode=ro`) and treats rows with `archived = 1` or a non-null `deleted_at` as archived. `search` and `latest` hide them unless `--include-archived` is passed; `show` still opens them. The rules match Qoder CN:

- Transcripts with no row in the database are active (CLI-only sessions can be missing).
- A missing, locked, or older-schema database degrades to all-active and is never written to.
- The archive set is cached per process by database path, modification time, and size.

Override the database path for tests or non-standard installs:

```bash
export FMS_QODER_APP_DB=/path/to/main.sqlite
```

This override is separate from `FMS_QODER_HOME` and from Qoder CN's `FMS_QODER_CN_APP_DB`. The two editions never share archive state. In the sampled international store the only archived row was also deleted and had no transcript, so enabling archived search did not change the visible session list.

## Transcript format

One JSON object per line, UTF-8. The record model is the same as Qoder CN; see `qoder-cn.md` for field-level details. Differences observed in the international store:

| Difference | Qoder international | Qoder CN |
| --- | --- | --- |
| Store root | `~/.qoder` | `~/.qoder-cn` |
| Harness ref | `qoder:<prefix>` | `qoder-cn:<prefix>` |
| Task execution transcripts | `projects/<cwd>/transcript/task-*.session.execution.jsonl` | Not observed |
| `worktree-state` records | Not observed in the sampled store | Present |
| `runtime-config` | Includes `reasoningEffort`, `contextWindow`, `generation` (often `null`) | Model-focused |

Common record types are identical: `workspace-directories`, `runtime-config`, `user`, `assistant`, `attachment`, `system`, `last-prompt`, `active-leaf`, and `file-history-snapshot`.

Resumed sessions can append another `workspace-directories`, `runtime-config`, and `last-prompt` block. The adapter reads the first usable metadata from the head and the latest values from the tail, so repeated blocks are safe.

### User records

Same fields as Qoder CN: `humanInput.text`, `message.content`, `cwd`, `gitBranch`, `entrypoint`, `version`, `isSidechain`, `isMeta`, `isCompactSummary`, and `toolUseResult`. Tool results are `user` records and never create turns.

The `humanInput.mode` field is present on prompts (for example `agent`). The adapter does not interpret it.

### Assistant records and tools

`message.content` contains `thinking`, `text`, and `tool_use` blocks. The digest ignores thinking, keeps a bounded amount of text, and records tool names, details, and edited files.

### Compaction

Same two-record pattern as Qoder CN:

```json
{"type":"user","isCompactSummary":true,"isVisibleInTranscriptOnly":true,"message":{"role":"user","content":[{"type":"text","text":"This session is being continued from a previous conversation..."}]}}
{"type":"system","subtype":"compact_boundary","content":"Conversation compacted","isCompactSummary":true,"compactMetadata":{"trigger":"auto","preTokens":167275}}
```

Only the user record holds the useful summary. The `system` record is a boundary marker. Neither is a human prompt.

### Latest prompt

`last-prompt` records have no timestamp and may be absent. The adapter falls back to the last meaningful human prompt in the tail, then to the first prompt. A missing `last-prompt` record is common after compaction.

## What the adapter extracts

Identical to Qoder CN:

- Summary: cwd, branch, model, version, entrypoint, started/updated time, size, first and latest meaningful prompts, derived title, archived flag.
- Digest: latest compaction summary, recent exchanges and tools, tool counts, edited files, todo list, human-prompt turn count.
- Prompts: every human prompt in transcript order, excluding tool results, sidechains, `isMeta` content, and compaction summaries. The delta fixture exercises an injected meta record that must not appear.

## Todo schema

Same as Qoder CN; see `qoder-cn.md`. Statuses observed here: `pending`, `in_progress`, `processing`, `completed`.

## Caveats

- Qoder international and Qoder CN are different products. A session found under `~/.qoder` must be reported as `qoder:<prefix>`, never as `qoder-cn:<prefix>`. Bare refs that match both stores are ambiguous and the CLI lists both candidates. Their archive databases are separate too; an archived CN session stays visible in the international store if it has no row there.
- Archive metadata comes from the desktop app database, not the transcript. If the app database is missing or unreadable, archived sessions will appear as active; mention this only if the user reports a mismatch.
- The adapter shares its parser with Qoder CN. A schema change in either product must be checked against both fixture stores before updating the shared class.
- Task transcripts under `transcript/` are excluded by design. They can be large and are not listed, searched, or shown as sessions.
- Assistant records can carry API error fields (`isApiErrorMessage`, `error`, `errorDetails`, `errorFallbackMessage`). The digest keeps their text as assistant output, which often explains a quota or authentication failure. `redacted_thinking` blocks are ignored.
- No stored title exists; titles are derived and can look like a truncated prompt.
- Context before compaction may exist only in the compaction summary.
- Attachments are not rendered.
- Timestamps are ISO 8601 on most records and epoch milliseconds on some config records; the CLI normalizes both to UTC.
- New releases can add record types. Unknown types are ignored; add a synthetic fixture before teaching the adapter a new shape.
- Session data can contain secrets and personal information. Keep the CLI read-only and never commit real transcripts.

## Performance notes

Same strategy as Qoder CN:

- `search` and `latest` read up to 2 MB / 200 records from the head and 512 KB from the tail per session, expanding to 4 MB when `last-prompt` is absent.
- Archive lookup adds one read-only SQLite query per process, typically a few milliseconds.
- `show` streams the selected transcript once. Large sessions can exceed 40 MB in the sampled store.
- `prompts --count` streams the selected transcript once; a listing streams it twice and retains only the requested page.
- `--deep` streams every candidate session transcript and remains much slower.

## Verification

From the repository root, run against the synthetic fixture:

```bash
export FMS_QODER_HOME="$PWD/tests/fixtures/qoder-home"
skills/find-my-session/scripts/fms search --harness qoder
skills/find-my-session/scripts/fms show qoder:c3d4e5f6
skills/find-my-session/scripts/fms show qoder:d4e5f6a7
skills/find-my-session/scripts/fms prompts qoder:d4e5f6a7
skills/find-my-session/scripts/fms search --harness qoder --deep subagent-only-marker
```

Expected: two sessions, the gamma fixture with one open todo and one completed todo, the delta fixture with a compaction summary and no `last-prompt`, exactly one delta prompt (`Export invoices as CSV`) with no compaction or injected meta text, and no match for the task-transcript marker. Also confirm `--harness qoder-cn` never returns these refs.

Archive behavior uses synthetic app databases generated by the test suite. To verify against the real app database, archive a session in international Qoder, then compare `search --harness qoder <prefix>` with and without `--include-archived`, and run `show qoder:<prefix>` to see `- archived: yes`.
