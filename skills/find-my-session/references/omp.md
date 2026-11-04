# Oh My Pi (`omp`)

| | |
| --- | --- |
| Status | Implemented · Verified |
| Adapter | `core/fms_lib/harnesses/omp.py` |
| Harness | `omp` |
| Aliases | `omp`, `oh-my-pi` |
| Variant | `cli` |
| Store | `~/.omp/agent/sessions` |
| Home override | `FMS_OMP_HOME` |
| Session-dir override | `PI_CODING_AGENT_SESSION_DIR`, else `<home>/sessions` |
| Verified | omp `18.16.0`, macOS arm64, 2026-11-04: one live session listed, shown, counted and paged; transcript bytes and mtimes unchanged |

Oh My Pi is a separate fork of Pi with its own npm package (`@oh-my-pi/pi-coding-agent`), command (`omp`), store, and schema. It is not an alias of `pi`, and the unrelated npm package `oh-my-pi` is a Pi extension, not this CLI. Both harnesses are implemented independently; their formats must not be merged.

## Layout

```text
~/.omp/agent/
  sessions/
    --<sanitized-cwd>--/
      <local-time>_<session-id>.jsonl
      <stem>/
        <agent-id>.jsonl      # subagent transcript, never listed
      <stem>.jsonl.lock.os    # lock file, ignored
  history.db                  # session title index, not read by fms
```

Only top-level `.jsonl` files two levels below `sessions/` are sessions. A file whose parent directory matches a sibling `<stem>.jsonl` (or lives under `subagents/`) is a subagent transcript and is skipped, including when addressed by raw path. The session id comes from the filename suffix after the first `_`, with the `session` header as a fallback.

## Schema

| Entry `type` | Fields used |
| --- | --- |
| `session` | `id`, `cwd`, `version` (number) |
| `title`, `title_change` | `title`, `source` (`auto`/`manual`); the last value wins |
| `model_change` | `model` (provider-prefixed) |
| `message` (`user`) | `content` text blocks, `attribution` |
| `message` (`assistant`) | `content` `text`/`thinking`/`toolCall`, `model`, `provider`, `usage`, `errorMessage` |
| `message` (`toolResult`) | flat `toolName`/`toolCallId`/`content`/`isError`; never a prompt |
| `custom` | e.g. `date-cwd-reminder`, `system-prompt-digest`; injected, never a prompt |
| `compaction` | `summary` (expected to match Pi; fixture-only) |

`message.timestamp` is Unix milliseconds; entry timestamps are ISO 8601. `model_change.model` already includes the provider prefix, so the digest prefers it over the bare assistant `model`. Usage totals come from assistant `usage`, including `cost.total`.

## Prompts

A user message is human-authored only when `message.role == "user"` and its `attribution` is absent or `user`; any other non-empty attribution is skipped. Injected reminders are separate `custom` records and are never prompts. System reminders inside prompt text are stripped. `iter_prompts` yields every accepted prompt once, in file order, uncapped, and without paging or deduplication by text. Titles are taken from `title`/`title_change` when present; generic titles fall back to the latest meaningful prompt.

## Digest

Same bounded shape as Pi: 50 exchanges, last compaction summary, todos from `todo` tool calls, tool counts, recent tools, edited files from edit/write-family tools, and assistant error text. Thinking blocks, `thinkingSignature`, images, and `history.db` titles are ignored.

## Archive and deletion

No archive flag or archive directory exists in the store or CLI; deleting a session removes its file. `SessionSummary.archived` is always `False`, so `--include-archived` changes nothing. `history.db` (`session_titles`) is deliberately not read; it carries titles, not archive state.

## Resume

Verified against `omp --help`: `omp --resume <id prefix|path>` reopens a session. `fms resume` prints `omp --resume <id>`.

## Gaps and drift risks

- Only omp `18.16.0` was observed live, with one short session; tool calls, compaction, and title-change coverage rest on the synthetic fixture and third-party schema documentation.
- Compaction entry shape is expected, not observed live.
- `history.db` may carry titles for sessions whose transcript title record is missing; fms intentionally ignores it.
- OMP honors `PI_CODING_AGENT_SESSION_DIR` (confirmed in the 18.16.0 binary strings), but this is not documented in its CLI help.

## Verification recipe

```bash
python3 -c 'import sys; sys.path.insert(0,"tests"); from pathlib import Path; from omp_fixture import build_omp_home; build_omp_home(Path("tmp/omp-home"))'
export FMS_OMP_HOME="$PWD/tmp/omp-home"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness omp --limit 0
skills/find-my-session/scripts/fms show omp:a1b2c3d4 --messages 5
skills/find-my-session/scripts/fms prompts omp:a1b2c3d4 --count
```
