# Grok Build

## Status

| Item | Value |
| --- | --- |
| Status | Ready |
| Adapter | `scripts/fms_lib/harnesses/grok_build.py` |
| Harness name | `grok-build` |
| Aliases | `grok`, `grok-build`, `grok-cli` |
| Variants | `tui, headless, acp` |
| Store | `~/.grok` |
| Home override | `FMS_GROK_HOME` |
| Verified | macOS arm64, Grok Build 1.0.70 (`f50904eaee6c`), 2026-10-29 |

The TUI, headless mode, and ACP integrations are separate entrypoints into the
same product, `GROK_HOME` defaulting to `~/.grok`, and they share one session
store and one session-id namespace, so they are a single harness. The live
store was verified through sessions created by the TUI/CLI. Headless and ACP
runs are expected to write the same layout but were not exercised separately
during verification.

## Store layout

```text
~/.grok/
├── sessions/
│   ├── <url-encoded-cwd>/
│   │   ├── <session uuid>/
│   │   │   ├── updates.jsonl            # authoritative ACP event stream
│   │   │   ├── summary.json             # index entry: title, cwd, times
│   │   │   ├── chat_history.jsonl       # rendered history, deep search only
│   │   │   ├── compaction_checkpoints/*.json
│   │   │   ├── compaction/INDEX.md, segment_NNN.md
│   │   │   ├── plan.json                # observed empty; plans live in updates
│   │   │   ├── system_prompt.txt, prompt_context.json
│   │   │   ├── tool_definitions.json, rewind_points.jsonl
│   │   │   ├── signals.json, feedback.jsonl
│   │   │   └── subagents/<child session id>/   # child session marker
│   │   └── notes.json                   # group-level file, never a session
│   └── <slug>-<hash>/
│       ├── .cwd                         # original cwd when the group name is too long
│       └── <session uuid>/...
├── bin/grok
└── docs/, README.md
```

The group directory is the absolute working directory URL-encoded. When the
encoded name would exceed 255 bytes, Grok uses a shortened slug plus a hash and
writes the original path into the group's `.cwd` file. The adapter prefers
`summary.json`'s `info.cwd`, then `.cwd`, then the URL-decoded group name, and
only accepts a decoded group name that looks like an absolute path.

`session_id` is `summary.json`'s `info.id`, falling back to the directory name.
`grok-build:9a0b1c01` is therefore the usual short ref. `size_bytes` is the
`updates.jsonl` size; the other files are not counted.

`summary.json` also records `created_at`, `updated_at`, `last_active_at`,
`current_model_id`, `num_messages`, `session_kind`, `parent_session_id`,
`fork_context_source`, `forked_at`, `agent_name`, `agent_id`, `attempt_id`,
`head_branch`, `head_commit`, `git_root_dir`, `git_remotes`, `grok_home`,
`reasoning_effort`, `sandbox_profile`, `last_turn_summary`, `last_recap`,
`next_trace_turn`, and `chat_format_version`. The adapter reads the cwd, id,
timestamps, title, model, branch, and `session_kind`; the rest is ignored.

## Session selection

A directory under `sessions/<group>/<session>/` is listed only when both
`summary.json` and a non-empty `updates.jsonl` exist. This skips empty
placeholder sessions that were created but never used.

Subagent child sessions are excluded in two independent ways:

1. Their `summary.json` has `session_kind` `subagent` or `subagent_resume`.
2. A sibling session directory contains `subagents/<child id>/`.

Each check alone is enough; both are applied so a partly written child is still
hidden. A fork (`parent_session_id` set without a subagent kind) is a normal
top-level session and stays listed.

Listing order is `updates.jsonl` modification time, newest first. Session refs
stay stable because they come from `info.id`.

## `updates.jsonl` records

Every line is one JSON object:

```json
{"timestamp": 1760951400, "method": "session/update",
 "params": {"sessionId": "...", "update": {"sessionUpdate": "..."}, "_meta": {}}}
```

`method` is normally `session/update`; `_x.ai/session/update` also appears. The
adapter reads `params.update` regardless of method. Timestamps are epoch
seconds. A partially written final line is skipped.

| `sessionUpdate` | Read as |
| --- | --- |
| `user_message_chunk` | Candidate human prompt. `content` is a text or image block. `_meta` carries `modelId`, `promptIndex`, and optional `hideFromScrollback` or `syntheticPrompt`. |
| `agent_message_chunk` | Assistant text. Each chunk is its own assistant message, not a delta. |
| `agent_thought_chunk` | Thinking. Ignored. |
| `tool_call` | Tool name in `title`, arguments in `rawInput`, id in `toolCallId`. |
| `tool_call_update` | Status and output for a tool call. Ignored for counts and edits. |
| `plan` | Todo entries in `entries`, each with `content`, `priority`, and `status`. |
| `turn_completed` | Turn boundary with `stop_reason` and usage. Ignored. |
| `session_recap`, `compaction_checkpoint`, `auto_compact_started/completed` | Context bookkeeping. Ignored. |
| `subagent_spawned/finished`, background, memory, workflow, scheduled-task events | Ignored. |

## Prompt extraction

A prompt comes only from `user_message_chunk` with a `text` content block.
Image blocks are ignored, so a prompt made only of images is not listed.

Records with `_meta.hideFromScrollback` or `_meta.syntheticPrompt` are skipped.
Consecutive text chunks with the same `promptIndex` are joined with a newline;
a new `promptIndex` or any non-user update ends the prompt. The resulting text
is then cleaned:

| Shape | Treatment |
| --- | --- |
| `<system-reminder>...</system-reminder>` | Stripped; surrounding text is kept. |
| `<user-prompt-submit-hook>...</user-prompt-submit-hook>` | Stripped. |
| `<task-notification>`, `<command-name>`, `<local-command-*>`, `<bash-*>` | Record excluded. |
| `Caveat:` continuation text | Excluded. |
| `This session is being continued from a previous conversation...` | Excluded. |
| `[Request interrupted by user ...]` | Excluded when the whole prompt is the marker. |
| `/review`, `/clear`, and other bare slash commands | Excluded. |

`iter_prompts` streams the full `updates.jsonl` in order with no cap. The shared
CLI owns counting, paging, ordering, and `--chars`. Tiny real prompts such as
`1`, `3`, `做`, or `继续` are kept; the generic-prompt filter applies only when
choosing a title.

## Titles

The title is the first non-generic of:

1. `summary.json`'s `generated_title`.
2. `summary.json`'s `session_summary`.
3. The latest non-generic prompt, then the first non-generic prompt.

Empty prompts, a single character, punctuation or digits only, and generic
continuations such as `continue`, `next`, `ok`, or `继续` are treated as
non-titles. If a session has prompts but all of them are generic, the latest
prompt is still used rather than the id.

## Compaction

Grok writes a checkpoint JSON under `compaction_checkpoints/` for each
compaction. Each contains `prompt_index_at_compaction`, `compacted_history`,
`created_at`, and `schema_version`. The continuation message is a `user` entry
in `compacted_history` whose text starts with
`This session is being continued from a previous conversation`.

The adapter inspects the five newest checkpoint files by mtime, picks the
highest `(prompt_index_at_compaction, mtime_ns)`, and stores its first
continuation message as `compact_summary`. `compaction/segment_NNN.md` files are
historical records and are not used as the summary. `show` renders the summary
under `Compact summary (latest compaction)`; `--summary-chars 0` omits it.

## Todos

The latest `plan` event replaces the todo list. Each entry maps `content` to
`subject` and keeps `status` (`pending`, `in_progress`, `completed`). A
`todo_write` tool call is a fallback if no plan event exists. `plan.json` was
empty in every verified session, so it is ignored.

## Digest

`load()` streams `updates.jsonl` once and retains bounded state:

- Up to 50 recent exchanges, grouped by `promptIndex`.
- Up to three assistant text blocks per exchange, 5,000 characters each.
- Up to eight tools per exchange and 20 recent tools overall.
- Edited files from `search_replace` and `write` tool input, keyed by absolute
  path with a count, capped at 30. Relative paths are resolved against the
  session cwd.
- Tool counts from `tool_call` records only; `tool_call_update` does not create
  a second count.

Assistant API error text is kept because it usually explains quota or
authentication failures. Thinking chunks, tool results, images, attachments,
and system prompts are not rendered. `turn_count` counts retained human
prompts.

## Search and deep search

`summarize()` reads a 2 MB / 400-record head for the first prompt and a 1.5 MB
tail for the latest prompt. If the tail holds no prompt, it expands up to 16 MB;
live sessions with very large pasted images needed the expansion. Title, cwd,
timestamps, model, branch, and size come from `summary.json`.

`--deep` scans, per session:

- `updates.jsonl`
- `chat_history.jsonl`
- `compaction/*.md`
- `compaction_checkpoints/*.json`

All query tokens must be found within one session; tokens may be spread across
those files, but never across sessions. The scan uses the shared normalized
UTF-8 matcher, so case and non-ASCII tokens work without escaping.
`system_prompt.txt`, `tool_definitions.json`, `prompt_context.json`, images, and
subagent traffic are not scanned.

## Archive state

Grok Build has no archive flag. `/delete` removes the session directory
permanently, so a deleted session simply disappears. Every listed session is
reported as active (`archived: false`); `--include-archived` changes nothing.
An explicit `show` by ref or path still opens any session that exists.

## Known gaps

- No archive or deleted-session metadata; only a missing directory signals
  deletion.
- Image-only prompts are not listed because the adapter reads text blocks only.
- `plan.json` is ignored because it was empty in every verified session.
- `tool_call_update` output is not rendered in the digest.
- `entrypoint` and `version` are empty: `summary.json` carries neither.
- Headless and ACP entrypoints were not exercised separately; only the shared
  store layout is verified.
- Compaction segment markdown is used by `--deep` but not as the summary.
- Sessions whose only prompt sits beyond the 16 MB tail window can miss a
  latest-prompt title.

## Verification

Fixtures are built at runtime by `tests/grok_fixture.py`.

```bash
python3 - <<'PY'
from pathlib import Path
import tempfile
from tests.grok_fixture import build_grok_home
root = Path(tempfile.mkdtemp(prefix="grok-fixture-"))
build_grok_home(root / "home")
print(root)
PY
```

```bash
export FMS_GROK_HOME="/path/from/above/home"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness grok-build --limit 0
skills/find-my-session/scripts/fms search --harness grok-build --include-archived --limit 0
skills/find-my-session/scripts/fms show grok-build:9a0b1c01
skills/find-my-session/scripts/fms show grok-build:9a0b1c04 --format json
skills/find-my-session/scripts/fms prompts grok-build:9a0b1c01 --count
skills/find-my-session/scripts/fms prompts grok-build:9a0b1c01 --order newest --limit 2
skills/find-my-session/scripts/fms search --harness grok-build --deep grok-deep-only-needle
```

Expected: four active sessions, newest first; archive columns all `-`;
`9a0b1c01` shows five prompts, two open todos, edited files, and the latest
compaction summary; `9a0b1c02` falls back to its first prompt
as the title; `9a0b1c03` uses the `.cwd` group path; `9a0b1c04` shows the newer
checkpoint summary; the deep-only needle matches only `grok-build:9a0b1c03`;
and subagent, empty-session, and group-decoy needles never match.
