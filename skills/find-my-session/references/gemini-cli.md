# Gemini CLI

## Status

- Implemented (`core/fms_lib/harnesses/gemini_cli.py`), harness name
  `gemini-cli`.
- Aliases: `gemini-cli`, `gemini`.
- Variants: `cli`.
- Store: `~/.gemini`, override with `FMS_GEMINI_CLI_HOME`.

## Verified against

- macOS arm64, Gemini CLI 0.46.0 (logs reference 0.46.0 → 0.49.0 updates),
  2026-11-04. Six chat logs across one project directory listed, all
  readable; `search`, `latest`, `show`, prompt count/paging, and `doctor`
  verified; chat files unchanged afterwards. The store holds a handful of
  short real sessions, so wide schema coverage rests on the synthetic
  fixture.
- Linux is expected to work (same `~/.gemini` layout) but was not verified.
- Windows store location is unverified.

## Layout

- `~/.gemini/tmp/<project>/chats/session-<timestamp>-<uuid>.jsonl` — one
  replayable chat log per session. `<project>` is a slug derived from the
  working directory, not a reliable identity.
- `~/.gemini/tmp/<project>/.project_root` — the absolute working directory
  of the project; this is the authoritative cwd.
- `~/.gemini/history/<project>/` was observed empty and is ignored.
- `GEMINI.md`, `settings.json`, `google_accounts.json`, `bin/`, `config/`
  are ignored.

## Chat log format

JSONL mixing three record shapes, replayed top to bottom:

1. header: `{"sessionId", "projectHash", "startTime", "lastUpdated",
   "kind": "main"}`;
2. `{"$set": {"messages": [...], "lastUpdated": ...}}` — full-array
   snapshot that *replaces* the message list;
3. `{"$set": {"lastUpdated": ...}}` — metadata-only update;
4. bare message records `{"id", "timestamp", "type", "content", "model",
   "thoughts", "tokens"}` — appended in order.

Replay keeps a message list: a `$set` with `messages` replaces it (and the
seen-id set), bare records append unless their `id` was already seen. A
partially written trailing line is skipped. Only `kind: "main"` was
observed; all logs are treated as sessions.

Message types:

- `user` — `content` blocks are `{"text": ...}` (human turns; the first
  message repeats an injected `<session_context>` preamble) or
  `{"functionResponse": {"id", "name", "response"}}` (tool results).
- `gemini` — assistant turns with `model`, `thoughts`
  (`[{subject, description, timestamp}]`, treated as thinking and ignored),
  and `tokens`; visible text lives in `text` content blocks and is often
  absent in these logs.
- `info` — CLI notices with a plain-string `content` (for example update
  banners); ignored.
- `error` — API failures with a plain-string `content`
  (`[API Error: ...]`); kept in the digest so quota/auth failures survive.

## Human prompts

A prompt is a `user` message whose `text` blocks, joined in order, do not
start with `<session_context>` / `<environment_context>`. Tool results
(`functionResponse`) are never prompts. Generic `继续`/`ok`-style prompts
stay in the listing but never become the title. When a snapshot replaces
the list, prompts recorded only before the snapshot disappear with it —
that is the format's semantics, not a filter.

## Digest

`fms show` extracts cwd (from `.project_root`), started/updated (header
times, then the newest message or `$set` timestamp), the latest `model`,
turns, tool calls with names from `functionResponse`, and API error text.
Todos, compaction summaries, and edited files are not present in this
format; `compact_summary` and `edited_files` stay empty. `size` is the
JSONL file size. There is no archive state; deleted chats are removed from
disk.

## Deep search

`--deep` streams the chat file, so matches inside tool responses and
`$set` payloads count even though head/tail prompt metadata never sees
them.

## Known gaps and risks

- Observed logs predate richer assistant text; if newer versions append
  more content block kinds, prompt/turn extraction may need an update.
- Sessions whose only content is the injected `<session_context>` preamble
  have no prompts and fall back to the id-based title.
- The tmp directory name is a project slug, not a stable id; refs use the
  session uuid prefix (the trailing segment of the file name, which matches
  the header `sessionId` prefix).
- No archive, no todos, no compaction in the observed format.

## Verification recipe

```bash
export FMS_GEMINI_CLI_HOME="$PWD/tests/fixtures/gemini-cli-home"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness gemini-cli
skills/find-my-session/scripts/fms search --harness gemini-cli --deep "parser module contents"
skills/find-my-session/scripts/fms show gemini-cli:11111111
skills/find-my-session/scripts/fms prompts gemini-cli:11111111 --count
skills/find-my-session/scripts/fms prompts gemini-cli:11111111 --order newest --limit 2
skills/find-my-session/scripts/fms doctor --harness gemini-cli
```

Then repeat against the live store with `FMS_GEMINI_CLI_HOME` unset and
record the version, platform, and date in the compatibility matrix.
