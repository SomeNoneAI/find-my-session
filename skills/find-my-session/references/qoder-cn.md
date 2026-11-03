# Qoder CN session store

Status: ready. Adapter: `scripts/fms_lib/harnesses/qoder_cn.py`. Harness name: `qoder-cn`. Aliases: `qodercn`, `qoder_cn`, `qcn`.

This document describes Qoder CN. International Qoder is a separate product with a separate store (`~/.qoder`) and a separate adapter; see `qoder.md`. Both adapters share one parser class, but their stores, refs, and environment overrides are distinct.

## Variants

Qoder CN ships as a desktop application and as the `qoderclicn` CLI. Both write the same store at `~/.qoder-cn`, so one adapter covers both.

`entrypoint` is present on most transcript records, but it has been observed as `cli` even for desktop-originated sessions. Do not use it to identify the surface. Treat desktop and CLI as one storage variant and state that both are supported.

The store location can be overridden for tests or non-standard installs:

```bash
export FMS_QODER_CN_HOME=/path/to/qoder-cn-home
```

The override points at the directory that contains `projects/` and `tasks/`.

## Layout

```text
~/.qoder-cn/
├── projects/
│   └── <encoded-cwd>/
│       └── <session-uuid>.jsonl
└── tasks/
    └── <session-uuid>/
        ├── 1.json
        ├── 2.json
        └── ...
```

- `projects/<encoded-cwd>/<session-uuid>.jsonl` is the transcript. The adapter globs `projects/*/*.jsonl`.
- `<encoded-cwd>` replaces path separators with `-`; for example `/Users/example/project` becomes `-Users-example-project`. Hidden path components can produce consecutive dashes. Do not reverse this encoding; read `cwd` from the transcript instead.
- `tasks/<session-uuid>/<n>.json` stores todos for that session. The directory is often empty.
- Session ids are UUIDs. `fms` refs use the first eight characters, for example `qoder-cn:3f2a9c1d`.

## Archive metadata

Qoder CN does not record archive state in the transcript or under `~/.qoder-cn`. The desktop app keeps the session list and archive state in an Electron SQLite database outside the agent store:

```text
~/Library/Application Support/com.qodercn.app.stable/main.sqlite   # macOS, current app
```

The adapter opens the database read-only (`file:...?mode=ro`) and reads:

```sql
SELECT session_id FROM chat_sessions WHERE archived = 1 OR deleted_at IS NOT NULL
```

- `archived = 1` and any non-null `deleted_at` are treated as archived. `search` and `latest` hide both unless `--include-archived` is passed; `show` still opens them by explicit ref or path.
- A transcript that has no row in the database is treated as active. CLI-only sessions can be absent from the app database.
- A missing, locked, or older-schema database degrades to "no archive metadata": every session is active. The adapter never writes to the database.
- The archive set is cached per process by database path, modification time, and size.

Override the database path for tests or non-standard installs:

```bash
export FMS_QODER_CN_APP_DB=/path/to/main.sqlite
```

This override is separate from `FMS_QODER_CN_HOME`, which only changes the transcript store. The legacy `QoderCN` app-support directory is used as a fallback on macOS. Linux (`<XDG_CONFIG_HOME or ~/.config>/com.qodercn.app.stable/main.sqlite`) and Windows (`%APPDATA%\com.qodercn.app.stable\main.sqlite`) candidates are implemented but unverified.

## Transcript format

One JSON object per line, UTF-8. Records are append-only during a session, but compaction can rewrite the effective conversation. Lines can be very large.

Common record types:

| `type` | Purpose |
| --- | --- |
| `workspace-directories` | Session workspace roots in `directories`; also appears near EOF. |
| `runtime-config` | Model, reasoning effort, context window, generation settings. Timestamps may be epoch milliseconds. |
| `user` | Human prompt, tool result, sidechain prompt, or compaction summary. |
| `assistant` | Assistant content blocks. |
| `attachment` | Attached files or images. Not parsed by the digest. |
| `system` | System events, including `subtype: compact_boundary`. |
| `last-prompt` | Denormalized latest prompt for fast listing; usually near EOF. |
| `active-leaf` | Conversation tree pointer. Not user-visible content. |
| `file-history-snapshot` | File edit history metadata. Not used by the digest. |
| `worktree-state` | Worktree bookkeeping. Not used by the digest. |

### User records

Important fields:

- `humanInput.text`: the actual human prompt when present.
- `message.content`: a string or a list of content blocks. For prompts it usually contains a `text` block. For tool results it contains `tool_result` blocks.
- `cwd`, `gitBranch`, `entrypoint`, `version`, `sessionId`, `timestamp`.
- `isSidechain`: true for subagent/sidechain traffic. The adapter ignores these for the main task.
- `isMeta`: true for injected content such as an expanded skill body. Never treat it as a human prompt.
- `isCompactSummary`: true for the continuation summary created by compaction.
- `isVisibleInTranscriptOnly`: often set on compaction summaries.
- `toolUseResult`: present on tool-result user records.

### Assistant records

`message.content` is a list of blocks:

- `thinking`: internal reasoning. The digest ignores it.
- `text`: assistant-visible text.
- `tool_use`: `name` plus `input`. The adapter extracts a short detail and tracks edits.

### Tool results

Tool results are stored as `user` records. They can have `toolUseResult` and `message.content` blocks of type `tool_result`. They are not human prompts and must not create turns. The adapter skips them.

### Compaction

Qoder CN compaction produces two related records:

```json
{"type":"user","isCompactSummary":true,"message":{"role":"user","content":[{"type":"text","text":"This session is being continued from a previous conversation..."}]}}
{"type":"system","subtype":"compact_boundary","content":"Conversation compacted","isCompactSummary":true,"compactMetadata":{"trigger":"auto","preTokens":167275}}
```

The `user` record contains the useful summary. The `system` record only marks the boundary; its `content` is the literal string `Conversation compacted`. Use the latest user compaction record as the `Compact summary` section, and never treat either record as a human prompt.

The continuation text is not authored by the user. Prompts beginning with `This session is being continued from a previous conversation` are rejected by the adapter even when the flag is missing.

### Latest prompt

`last-prompt` records look like:

```json
{"type":"last-prompt","sessionId":"...","lastPrompt":"..."}
```

They have no timestamp and are usually within the last 512 KB, but about 1% of sessions omit them. The adapter falls back to the last meaningful human prompt in a larger tail window, then to the first prompt.

## What the adapter extracts

Summary (head/tail reads only):

- `cwd`, branch, model, version, entrypoint, started time, updated time, size.
- First meaningful human prompt and latest meaningful human prompt.
- Title: latest prompt unless it is generic (`continue`, `继续`, `ok`, etc.), otherwise the first prompt.
- Archived flag, read read-only from the desktop app database (see [Archive metadata](#archive-metadata)).

Digest (`show`, full streaming read):

- Latest compaction summary.
- Recent exchanges and tool calls, capped in memory.
- Tool counts, recent tools, and edited files from `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, `apply_patch`, and `StrReplace`.
- Todos from `tasks/<session-id>/*.json`, sorted by numeric filename, last 400 files.
- Turn count based on human prompts only.

Prompts (`prompts`, full streaming read):

- Every human prompt in transcript order, with its timestamp, after removing system reminders and command wrappers.
- Skips tool-result records, `isMeta`, `isSidechain`, `isCompactSummary`, `last-prompt`, `active-leaf`, and empty editor-state records.
- Prompt text is returned in full; the CLI applies `--chars`, `--limit`, and `--offset` without retaining other prompts in memory.

## Todo schema

```json
{
  "id": "2",
  "subject": "Refresh tokens before expiry",
  "description": "Add refreshIfExpired and wire it into getAccessToken.",
  "activeForm": "Adding the refresh path",
  "status": "in_progress",
  "blocks": [],
  "blockedBy": [],
  "businessInfo": {"stage": "processing"}
}
```

Observed statuses: `pending`, `in_progress`, `processing`, `completed`. The renderer treats `pending`, `in_progress`, `processing`, and `blocked` as open. `activeForm`, `blocks`, `blockedBy`, and `businessInfo` are ignored.

## Caveats

- There is no stored session title (no `ai-title` equivalent). Titles are derived and can look like a truncated prompt.
- Context before a compaction may exist only in the compaction summary. The digest shows the summary; do not assume the raw earlier turns are still present.
- Tool results can be much larger than prompts. `show` never prints them wholesale.
- `attachment` records may reference images or files. The digest does not render attachments.
- Timestamp formats vary: ISO 8601 strings on most records, epoch milliseconds on some config records. The CLI normalizes both to UTC.
- New Qoder CN releases can add record types. Unknown types are ignored; add a synthetic fixture before teaching the adapter about a new shape.
- Session data can contain secrets and personal information. Keep the CLI read-only and never commit real transcripts.

## Performance notes

The adapter deliberately splits work:

- `search` and `latest` read up to 2 MB / 200 records from the head and 512 KB from the tail per session. If `last-prompt` is absent, the tail read expands to 4 MB.
- Archive lookup adds one read-only SQLite query per process, typically a few milliseconds even on a multi-hundred-MB app database.
- `show` streams the selected transcript once. Large sessions can exceed 100 MB.
- `prompts --count` streams the selected transcript once; a listing streams it twice. Only the selected page is retained.
- `--deep` streams every candidate transcript in chunks, so it is orders of magnitude slower. Use it only when metadata search fails.

## Verification

From the repository root, run against the synthetic fixture:

```bash
export FMS_QODER_CN_HOME="$PWD/tests/fixtures/qoder-cn-home"
skills/find-my-session/scripts/fms search --harness qcn
skills/find-my-session/scripts/fms show qcn:a1b2c3d4
skills/find-my-session/scripts/fms show qcn:b2c3d4e5
skills/find-my-session/scripts/fms prompts qcn:a1b2c3d4 --count
skills/find-my-session/scripts/fms prompts qcn:a1b2c3d4
```

Expected: two sessions, the alpha fixture with two open todos, the beta fixture with a compaction summary, and exactly two alpha prompts (the OAuth request and the PKCE follow-up) with no system reminder or sidechain text.

Archive behavior is covered by tests that generate synthetic app databases at runtime rather than committing one. To verify manually against a real app database, archive a session in Qoder CN, then compare:

```bash
fms search --harness qcn <prefix>
fms search --harness qcn <prefix> --include-archived
fms show qcn:<prefix>
```

Expected: the default search misses, `--include-archived` finds it, and `show` prints `- archived: yes`.
