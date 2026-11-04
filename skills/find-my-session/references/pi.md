# Pi (`pi`)

| | |
| --- | --- |
| Status | Implemented · Verified |
| Adapter | `core/fms_lib/harnesses/pi.py` |
| Harness | `pi` |
| Aliases | `pi`, `pi-cli` |
| Variant | `cli` |
| Store | `~/.pi/agent/sessions` |
| Home override | `FMS_PI_HOME` |
| Session-dir override | `PI_CODING_AGENT_SESSION_DIR`, else `<home>/sessions` |
| Verified | Pi `1.5.0`, macOS arm64, 2026-11-04: one live session listed, shown, counted and paged; transcript bytes and mtimes unchanged |

Pi is distributed as `@earendil-works/pi-coding-agent` and exposes the `pi` command. The legacy `@mariozechner/*` packages use the same store layout and are deprecated, not rehomed.

## Layout

```text
~/.pi/agent/
  sessions/
    --<sanitized-cwd>--/
      <local-time>_<session-id>.jsonl
```

One JSONL file per session. Entries form a tree through `id`/`parentId`; branching stays in one file. Subagent or extension transcripts are not a documented Pi feature, so only files directly under a workspace directory are listed. The adapter derives the session id from the filename suffix after the first `_`, and falls back to the `session` header when the filename is unusual.

## Schema

| Entry `type` | Fields used |
| --- | --- |
| `session` | `id`, `cwd`, `version`, `timestamp` |
| `model_change` | `provider`, `modelId` |
| `message` (`user`) | `content` text blocks; human-authored only |
| `message` (`assistant`) | `content` `text`/`thinking`/`toolCall`, `model`, `errorMessage`, `usage` |
| `message` (`toolResult`) | `toolName`, `content`, `isError`; never a prompt |
| `message` (`system`, `bashExecution`, `custom`, `branchSummary`, `compactionSummary`) | ignored for prompts |
| `compaction` | `summary`, `tokensBefore` |
| `session_info` | `name` (explicit title) |

Timestamps are ISO 8601 on entries and Unix milliseconds on message objects. Both normalize to UTC. Message `usage` carries `input`, `output`, `cacheRead`, `cacheWrite`, `totalTokens`, and `cost.total`; `fms stats` sums those per session and never estimates.

## Prompts

`iter_prompts` accepts only `message.role == "user"` text blocks, strips `<system-reminder>…</system-reminder>` blocks, and yields every human prompt in file order without caps. Tool results, compaction summaries, branch summaries, `custom_message` injection, `bashExecution`, and session metadata never become prompts. Generic prompts such as `继续` are kept in prompt listing but ignored when choosing a derived title. An explicit `session_info.name` wins; otherwise the title comes from the latest meaningful prompt, then the first.

## Digest

`load` keeps the last 50 user/assistant exchanges, the last compaction summary, open todos from `todo` tool calls, tool counts, recent tools, edited files from `edit`/`write`/`multi_edit`/`apply_patch`/`ast_edit`, and assistant `errorMessage` text. Thinking blocks and images are ignored. Tool-call arguments are never executed.

## Archive and deletion

Pi has no archive flag or archive directory; deleting a session removes its file. `SessionSummary.archived` is always `False`, so `--include-archived` changes nothing. Do not infer archive state from transcript content.

## Resume

Verified against `pi --help`: `pi --session <id>` reopens a saved session by id or path. `fms resume` prints that command.

## Gaps and drift risks

- Only Pi `1.5.0` was observed live, with one short session; tool calls, compaction, and `session_info` coverage rest on the synthetic fixture and the official session-format documentation.
- Message `timestamp` values (Unix milliseconds) are not used for ordering; entry timestamps are.
- No native subagent transcript convention is documented, so none is filtered.

## Verification recipe

```bash
python3 -c 'import sys; sys.path.insert(0,"tests"); from pathlib import Path; from pi_fixture import build_pi_home; build_pi_home(Path("tmp/pi-home"))'
export FMS_PI_HOME="$PWD/tmp/pi-home"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness pi --limit 0
skills/find-my-session/scripts/fms show pi:a1b2c3d4 --messages 5
skills/find-my-session/scripts/fms prompts pi:a1b2c3d4 --count
```
