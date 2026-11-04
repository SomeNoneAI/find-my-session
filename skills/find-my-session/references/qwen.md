# Qwen Code

## Status

- Implemented (`core/fms_lib/harnesses/qwen.py`), harness name `qwen`.
- Aliases: `qwen`.
- Variants: `cli`.
- Store: `~/.qwen`, override with `FMS_QWEN_HOME`.

## Verified against

- macOS arm64, Qwen Code (records carry version `0.8.2` envelopes),
  2026-11-04. Nine session logs across four project directories listed,
  all readable, 0 skipped; `search`, `latest`, `show`, prompt count, and
  `doctor` verified; files unchanged afterwards. The live store holds a
  handful of short real sessions, so wide schema coverage rests on the
  synthetic fixture.
- Linux is expected to work but was not verified; Windows unverified.

## Layout

- `~/.qwen/projects/<encoded-cwd>/chats/<session-uuid>.jsonl` — one JSONL
  session log per chat. `<encoded-cwd>` replaces path separators with `-`
  (Claude Code style); it is ambiguous for hyphenated directory names and
  is not used — the cwd comes from each record's `cwd` field.
- `~/.qwen/todos/<session-id>.json` — per-session todos
  (`{"todos": [{"content", "id", "status"}], "sessionId"}`).
- `settings.json`, `skills/`, `oauth_creds.json` are ignored.

## Session log format

Every line is one record:

- envelope: `uuid`, `parentUuid`, `sessionId`, `timestamp`, `type`, `cwd`,
  `gitBranch`, `version`;
- `message`: `{"role", "parts": [...]}` with Gemini-style parts.

Record types:

- `user` — `text` parts are the human turns. No injected preamble was
  observed in user records; `<session_context>`-style guards exist anyway.
- `assistant` — `model` + `usageMetadata` on the record; `text` parts are
  visible replies, `functionCall` parts (`{id, name, args}`) are tool
  invocations.
- `tool_result` — `toolCallResult: {callId, resultDisplay, status}` plus a
  `functionResponse` part; redundant with the call, skipped for the digest
  but visible to deep search.
- `system` — every observed record was `subtype: "ui_telemetry"`; skipped.

## Human prompts

`user` records whose `text` parts, joined in order, are non-empty and do
not start with an injected-context prefix. Generic `继续`/`ok`-style
prompts stay in the listing but never become the title. Sessions whose
only prompt is generic fall back to the session-id-based title.

## Digest

`fms show` extracts cwd, branch (`gitBranch`), version, started/updated,
the latest `model`, turns, tool calls with details from `functionCall`
args, and per-session todos from `~/.qwen/todos/` (`done` normalizes to
`completed`). Compaction summaries and edited files are not present in the
observed format and stay empty. `size` is the JSONL file size. There is no
archive state; deleted sessions disappear from disk.

## Deep search

`--deep` streams the chat file, so text inside `toolCallResult` and
`functionResponse` payloads counts even though head/tail prompt metadata
never sees it.

## Usage totals

`fms stats` sums the `usageMetadata` block each assistant record carries
(`promptTokenCount` → input, `candidatesTokenCount` → output,
`cachedContentTokenCount` → cache read). Cost is not recorded.

## Resume

Verified: qwen --resume <sessionId> reopens a session (qwen --continue reopens the most recent in this directory). fms resume prints qwen --resume <id>.

## Known gaps and risks

- No API-error record type was observed live; error text is not surfaced.
- No compaction/summary record in the observed format.
- Qwen Code evolves quickly as a fork; record types beyond
  user/assistant/tool_result/system may need adapter updates.
- Windows paths unverified.

## Verification recipe

```bash
export FMS_QWEN_HOME="$PWD/tests/fixtures/qwen-home"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness qwen
skills/find-my-session/scripts/fms search --harness qwen --deep qwen-deep-only-needle
skills/find-my-session/scripts/fms show qwen:aaaaaaaa
skills/find-my-session/scripts/fms prompts qwen:aaaaaaaa --count
skills/find-my-session/scripts/fms prompts qwen:aaaaaaaa --order newest --limit 2
skills/find-my-session/scripts/fms doctor --harness qwen
```

Then repeat against the live store with `FMS_QWEN_HOME` unset and record
the version, platform, and date in the compatibility matrix.
