# Claude Code

## Status

| Item | Value |
| --- | --- |
| Status | Ready |
| Adapter | `scripts/fms_lib/harnesses/claude_code.py` |
| Harness name | `claude-code` |
| Aliases | `claude`, `claude-code` |
| Variants | `cli, ide` |
| Store | `~/.claude` |
| Home override | `FMS_CLAUDE_HOME` |
| Verified | macOS, session metadata from Claude Code 2.1.305–2.1.312, 2026-10-29 |

The Claude Code CLI and the Claude Code IDE integration write the same store
and use the same session-id namespace, so they are a single harness. The live
store was verified through its transcripts. Only the CLI entrypoint (`cli`) was
observed; IDE-side metadata beyond that is **unverified**.

## Store layout

```text
~/.claude/
├── projects/
│   └── <encoded-cwd>/
│       ├── <session uuid>.jsonl
│       ├── sessions-index.json
│       └── <session uuid>/subagents/agent-<hash>.jsonl
├── todos/<session uuid>-agent-<agent id>.json   # expected, unverified
├── history.jsonl                                # global prompt history, ignored
├── sessions/<pid>.json                          # live process registry, ignored
├── session-env/, memory/, backups/              # ignored
└── shell-snapshots/, ide/, plugins/, telemetry/ # ignored
```

The adapter lists only `projects/*/*.jsonl`. Files whose name starts with
`agent-` and files under a `subagents/` directory are treated as subagent
transcripts and are never sessions. Archived or deleted transcripts are not
represented anywhere, so a removed session simply disappears.

`session_id` is the transcript file name, which equals the `sessionId` field in
the records, so `claude-code:c1a0de01` is a useful eight-character ref.
`size_bytes` is the transcript file size.

`projects/<encoded-cwd>/sessions-index.json` is **not** authoritative. In the
verified store it contained hundreds of entries for transcripts that no longer
existed and no entry for several existing transcripts. Titles come from the
transcripts instead; a stale index entry never creates a session.

## Transcript records

Every line is one JSON object with `type`, usually `sessionId`, `uuid`,
`timestamp`, `cwd`, `gitBranch`, `version`, and `entrypoint`.

| `type` | Read as |
| --- | --- |
| `user` | Candidate human prompt, tool result, or injected context. Carries `message.role == "user"`. |
| `assistant` | `message.content` blocks: `text`, `thinking`, and `tool_use`. `message.model` sets the model. |
| `summary` | Compaction summary in `summary`. Expected; no compaction was present in the verified store. |
| `system` | Bookkeeping (`turn_duration`, `compact_boundary`, `away_summary`, `local_command`, `informational`). Ignored except as a timestamp source. |
| `attachment` | Attached files and context. Never a prompt. |
| `ai-title` | UI title in `aiTitle`. The last non-empty, non-generic title wins. |
| `last-prompt` | `lastPrompt` is the newest prompt, used only as a fallback. |
| `queue-operation`, `mode`, `permission-mode`, `atis-latch` | UI state. Ignored. |
| `file-history-snapshot`, `cost-state`, `tools-used` | Bookkeeping. Ignored. |
| `api-request`, `api-request-blob`, `api-request-shape` | Request diagnostics. Ignored, but still scanned by `--deep`. |

## Resumed and subagent sessions

Resuming a session appends to the same transcript file, so there is no segment
chain to stitch. A separate transcript under
`projects/<slug>/<session>/subagents/agent-<hash>.jsonl` carries delegated
agent traffic. It is excluded from listing, search, ref resolution, and prompt
counting, and opening it by path fails with
`Claude Code subagent transcript is not a resumable session`. Records inside a
main transcript with `isSidechain: true` are skipped as prompts as well.

## Prompt extraction

A record becomes a human prompt only when all of these hold:

1. `type` is `user`.
2. `isMeta`, `isSidechain`, and `isCompactSummary` are absent or false.
3. The record has no `toolUseResult` field.
4. `message.role` is `user`.
5. `message.content` is a string or a list with at least one `text` block, and
   the list contains no `tool_result` block.

Injected content is removed or rejected before the prompt is kept:

| Shape | Treatment |
| --- | --- |
| `<system-reminder>...</system-reminder>` | Stripped; surrounding user text is kept. |
| `<user-prompt-submit-hook>...</user-prompt-submit-hook>` | Stripped. |
| `<task-notification>`, `<command-name>`, `<command-message>`, `<command-args>` | Record excluded. |
| `<local-command-caveat>`, `<local-command-stdout>`, `<local-command-stderr>` | Record excluded. |
| `<bash-input>`, `<bash-stdout>`, `<bash-stderr>` | Record excluded. |
| `Caveat:` continuation text | Excluded. |
| `This session is being continued from a previous conversation...` | Excluded. |
| `[Request interrupted by user ...]` markers | Excluded. |
| `/review`, `/clear`, and other bare slash commands | Excluded. |

`iter_prompts` streams the transcript in order and deduplicates by record
`uuid`. It applies no generic-prompt filter; only title selection skips prompts
such as `continue`, `继续`, `ok`, or a single character.

## Compaction

Claude Code compaction metadata was not present in the verified store. The
adapter handles three expected shapes defensively:

- `type: "summary"` uses its `summary` text.
- A `user` record with `isCompactSummary: true` stores its text as the summary
  and is never counted as a prompt.
- A `system` record with subtype `compact_boundary` only marks a boundary and
  is otherwise ignored.

The latest summary wins. `show` renders it under
`Compact summary (latest compaction)`; `--summary-chars 0` omits it.

## Titles

`title` uses the last non-empty, non-generic `aiTitle`, then the latest
meaningful prompt, then the first prompt. A generic title such as `继续` is
ignored. `sessions-index.json` is never consulted.

## Listing and search

`summarize()` makes one bounded streaming pass per transcript: a head of 400
records or 2 MB for metadata and the first prompt, plus a tail of 1.5 MB for the
latest prompt, title, model, and timestamp. The 2 MB head keeps the first prompt
visible even when earlier records carry large pasted images.

`--deep` scans transcript bytes with the shared UTF-8 matcher, so non-ASCII
tokens match without escaping. Only existing transcripts under
`projects/` are scanned; `history.jsonl`, `sessions-index.json`, subagent
transcripts, and live registries never produce matches.

## Archive state

Claude Code records no archive or deleted flag in its transcripts. Every session
is reported as active (`archived: false`). `--include-archived` changes nothing,
and a removed transcript disappears from listings.

## Digest

`load()` streams the transcript once and retains bounded state:

- Up to 50 recent exchanges.
- Up to three assistant text blocks per exchange, 5,000 characters each.
- Up to eight tools per exchange and 20 recent tools overall.
- Edited files from `Edit`, `Write`, `MultiEdit`, and `NotebookEdit` tool input,
  keyed by absolute path with a count, capped at 30. Relative paths are resolved
  against the turn cwd.
- Todos from `~/.claude/todos/<session-id>-agent-*.json` when present, else from
  the last `TodoWrite` tool input. Statuses such as `pending`, `in_progress`,
  and `completed` are preserved.

Tool results and request diagnostics are not rendered. `turn_count` counts
human prompts only. `show` prints no archive line because the flag is never
true.

## Known gaps

- No archive or deleted-session metadata; only missing files signal deletion.
- `sessions-index.json` is ignored because the live store was stale.
- Compaction and the todo directory are implemented from expected shapes but
  were not observed in the verified store.
- IDE-specific `entrypoint` values and metadata are unverified.
- Attachments, images, thinking blocks, and `api-request` bodies are ignored by
  the digest, though `--deep` still scans their bytes.
- The 400-record / 2 MB head can miss a first prompt only in pathological
  transcripts whose first user message follows more than 2 MB of other records.

## Verification

Fixtures are built at runtime by `tests/claude_code_fixture.py`.

```bash
python3 - <<'PY'
from pathlib import Path
import tempfile
from tests.claude_code_fixture import build_claude_code_home
root = Path(tempfile.mkdtemp(prefix="claude-fixture-"))
build_claude_code_home(root / "home")
print(root)
PY
```

```bash
export FMS_CLAUDE_HOME="/path/from/above/home"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness claude-code --limit 0
skills/find-my-session/scripts/fms search --harness claude-code --include-archived --limit 0
skills/find-my-session/scripts/fms show claude-code:c1a0de01
skills/find-my-session/scripts/fms show claude-code:c1a0de04 --format json
skills/find-my-session/scripts/fms prompts claude-code:c1a0de01 --count
skills/find-my-session/scripts/fms prompts claude-code:c1a0de01 --order newest --limit 2
skills/find-my-session/scripts/fms search --harness claude-code --deep claude-deep-only-needle
```

Expected: four active sessions in both searches; `codex`-style archive columns
all `-`; `c1a0de01` shows six prompts, two open todos, and edited files;
`c1a0de04` shows the compaction summary and two prompts; the deep-only needle
matches only `claude-code:c1a0de03`; and the subagent, decoy, history, and stale
index needles never match.
