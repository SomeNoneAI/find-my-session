# Qwen Code

## Status

- Implemented (`core/fms_lib/harnesses/qwen.py`), harness name `qwen`.
- Aliases: `qwen`.
- Variants: `cli`.
- Store: `~/.qwen`, override with `FMS_QWEN_HOME`.

## Verified against

- macOS arm64, Qwen Code 1.0.0-preview (flat store layout), 2026-11-11: one
  live session log at `projects/<encoded-cwd>/<session-uuid>.jsonl` listed,
  shown, and prompt-counted; `ai-title`, `tasks/` todos, `tool_use` calls,
  and `errorFallbackMessage` API-error records all surfaced; files unchanged
  afterwards.
- macOS arm64, Qwen Code (`0.8.2` record envelopes), 2026-11-04. Nine session
  logs across four project directories listed, all readable, 0 skipped;
  `search`, `latest`, `show`, prompt count, and `doctor` verified; files
  unchanged afterwards. The live store holds a handful of short real
  sessions, so wide schema coverage rests on the synthetic fixture.
- Linux is expected to work but was not verified; Windows unverified.

## Layout

Two layouts are read, newest first:

- 0.x: `~/.qwen/projects/<encoded-cwd>/chats/<session-uuid>.jsonl` — one JSONL
  session log per chat.
- 1.0 (preview): `~/.qwen/projects/<encoded-cwd>/<session-uuid>.jsonl` —
  the log sits directly in the project directory, next to a
  `<session-uuid>/` directory (`state.json`, `compression-v2/`) that holds
  opaque product state and is not read.

`<encoded-cwd>` replaces path separators with `-` (Claude Code style); it is
ambiguous for hyphenated directory names and is not used — the cwd comes from
each record's `cwd` field.

Todos:

- 0.x: `~/.qwen/todos/<session-id>.json`
  (`{"todos": [{"content", "id", "status"}], "sessionId"}`).
- 1.0: `~/.qwen/tasks/<session-id>/<n>.json` — one file per task, ordered by
  the numeric file name, with `subject` and `businessInfo.stage`
  (`processing` → in progress, `done` → completed). The tasks directory wins
  when both exist.

`settings.json`, `skills/`, `oauth_creds.json`, `logs/`, and the per-session
`state.json` are ignored.

## Session log format

Every line is one record with the envelope `{"uuid", "parentUuid",
"sessionId", "timestamp", "type", "cwd", "gitBranch", "version", ...}`.
Metadata records may use epoch-millis timestamps instead of ISO strings.

### 0.x records

- `message`: `{"role", "parts": [...]}` with Gemini-style parts.
- `user` — `text` parts are the human turns. No injected preamble was
  observed in user records; `<session_context>`-style guards exist anyway.
- `assistant` — `model` + `usageMetadata` on the record; `text` parts are
  visible replies, `functionCall` parts (`{id, name, args}`) are tool
  invocations.
- `tool_result` — `toolCallResult: {callId, resultDisplay, status}` plus a
  `functionResponse` part; redundant with the call, skipped for the digest
  but visible to deep search.
- `system` — every observed record was `subtype: "ui_telemetry"`; skipped.

### 1.0 records

- `message.content` is Anthropic-style: a plain string for human turns, or a
  list of blocks (`{"type": "text"}`, `{"type": "tool_use", "id", "name",
  "input"}`, `{"type": "tool_result", "tool_use_id", "content"}`).
- `user` — human turns carry `origin: {"kind": "human"}` and
  `humanInput: {"text", "mode"}`; tool results arrive as separate `user`
  records whose content is a `tool_result` block list. Local-command output
  is wrapped in `<local-command-caveat>` and never becomes a prompt.
- `assistant` — `message.model` names the model; `text` blocks are visible
  replies; `tool_use` blocks are tool invocations. Failed requests keep
  `isApiErrorMessage: true` with `errorFallbackMessage` and
  `displayErrorCode` (`network_failure`, `406`, `provider_error` were
  observed live); the fallback text is shown in the digest.
- Metadata-only record types never become prompts: `active-leaf` (message-tree
  position, epoch-millis timestamp), `attachment` (context documents),
  `workspace-directories`, `runtime-config` (model), `ai-title` (the app
  title, preferred for the session title), `last-prompt`, `worktree-state`.
- Records with `isSidechain: true` are skipped.

## Human prompts

`user` records that are real human turns: 1.0 requires
`origin.kind == "human"` (or `humanInput.text`), 0.x requires non-empty `text`
parts. Both layouts filter injected-context prefixes (`<session_context>`,
`<environment_context>`, `<memory>`, `<local-command-caveat>`). Generic
`继续`/`ok`-style prompts stay in the listing but never become the title;
1.0 sessions use the `ai-title` record first. Sessions whose only prompt is
generic fall back to the session-id-based title.

## Digest

`fms show` extracts cwd, branch (`gitBranch`), version, started/updated, the
latest `model` (record-level or `message.model`), turns, tool calls with
details from `functionCall` args or `tool_use` input, and per-session todos
from `tasks/` (1.0) or `todos/` (0.x). API-error fallback text surfaces as
the assistant reply for failed turns. Compaction summaries and edited files
are not present in the observed format and stay empty. `size` is the JSONL
file size. There is no archive state; deleted sessions disappear from disk.

## Deep search

`--deep` streams the chat file, so text inside `toolCallResult`,
`functionResponse`, `tool_result`, and `attachment` payloads counts even
though head/tail prompt metadata never sees it.

## Usage totals

`fms stats` sums the `usageMetadata` block each 0.x assistant record carries
(`promptTokenCount` → input, `candidatesTokenCount` → output,
`cachedContentTokenCount` → cache read). 1.0 records did not carry usage
totals live, so those sessions report `-`. Cost is not recorded.

## Resume

Verified: qwen --resume <sessionId> reopens a session (qwen --continue reopens the most recent in this directory). fms resume prints qwen --resume <id>.

## Known gaps and risks

- 1.0 usage totals are not recorded in the log; `fms stats` reports `-` for
  1.0 sessions.
- No compaction/summary record was observed in either layout.
- Qwen Code evolves quickly as a fork; record types beyond those listed above
  may need adapter updates.
- Windows paths unverified.

## Verification recipe

```bash
export FMS_QWEN_HOME="$PWD/tests/fixtures/qwen-home"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness qwen
skills/find-my-session/scripts/fms search --harness qwen --deep qwen-deep-only-needle
skills/find-my-session/scripts/fms show qwen:aaaaaaaa
skills/find-my-session/scripts/fms show qwen:dddddddd
skills/find-my-session/scripts/fms prompts qwen:aaaaaaaa --count
skills/find-my-session/scripts/fms prompts qwen:aaaaaaaa --order newest --limit 2
skills/find-my-session/scripts/fms prompts qwen:dddddddd --count
skills/find-my-session/scripts/fms doctor --harness qwen
```

Then repeat against the live store with `FMS_QWEN_HOME` unset and record
the version, platform, and date in the compatibility matrix.
