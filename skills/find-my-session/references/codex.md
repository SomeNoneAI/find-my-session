# ChatGPT Codex

## Status

| Item | Value |
| --- | --- |
| Status | Ready |
| Adapter | `scripts/fms_lib/harnesses/codex.py` |
| Harness name | `codex` |
| Aliases | `codex`, `chatgpt-codex` |
| Variants | `desktop, ide, cli` |
| Store | `~/.codex` |
| Home override | `FMS_CODEX_HOME` |
| Verified | macOS, session metadata from Codex 0.163.0–0.165.0-alpha.1.2, 2026-10-29 |

Codex Desktop, the Codex IDE extension, and the Codex CLI share one `~/.codex`
store and one session-id namespace, so they are a single harness. Threads
written by all three surfaces were observed: `originator` is `Codex Desktop`,
`codex-tui`, `codex-web-gui`, or `codex-web-vue`, and `source` is `desktop`,
`cli`, `vscode`, or an object such as `{"subagent": {...}}`.

The sessions were verified through their recorded metadata and transcripts. The
local `codex` binary was not executed during verification, so CLI behavior
beyond what its rollouts record is **unverified**.

## Store layout

```text
~/.codex/
├── sessions/<YYYY>/<MM>/<DD>/
│   ├── rollout-<date>T<time>-<thread id>.jsonl[.zst]
│   └── rollout-<date>T<time>-<thread id>_<segment id>.jsonl[.zst]
├── archived_sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl[.zst]
├── session_index.jsonl          # id, thread_name, updated_at
├── history.jsonl                # legacy prompt history, ignored
├── version.json, config.toml    # ignored
└── log/, cache/, tmp/           # ignored
```

The adapter only globs `rollout-*.jsonl` and `rollout-*.jsonl.zst` under
`sessions/` and `archived_sessions/`. A `.zst` rollout is decompressed in
memory; nothing is rewritten and no cache file is created.

`session_index.jsonl` is read for thread titles. `session_id` comes from the
file name, which is also `session_meta.payload.id`, so `codex:c0de0001` is a
useful eight-character ref. `size_bytes` is the rollout file size, which is the
compressed size for `.zst` files.

## Rollout records

Every line is one JSON object with `timestamp` (ISO 8601 UTC), `type`, and,
since early 2025 builds, a monotonic `ordinal`.

| `type` | Read as |
| --- | --- |
| `session_meta` | First record. `payload` carries `id`, `session_id`, `timestamp`, `cwd`, `originator`, `source`, `cli_version`, `git.branch`, `thread_source`, and `history_base` on resumed segments. |
| `turn_context` | `payload.cwd` and `payload.model` for the turn. The last one wins. |
| `response_item` / `message` (`role: user`) | Candidate human prompt. |
| `response_item` / `message` (`role: assistant`) | Assistant text. API error text is kept. |
| `response_item` / `reasoning` | Thinking blocks. Ignored. |
| `response_item` / `function_call` | Tool call. `arguments` is a JSON string. |
| `response_item` / `custom_tool_call` | Free-form tool call; `apply_patch` carries a patch body. |
| `response_item` / `*_output` | Tool result. Never a prompt. |
| `compacted` | `payload.message` is the compaction summary. |
| `event_msg` | Duplicate UI events, including a second copy of user text. Ignored. |
| `world_state`, `token_usage_record` | Bookkeeping. Ignored. |

A partially written final line is tolerated: invalid JSON is skipped.

## Resumed threads

Resuming a thread does not append to the old rollout. Codex opens a new segment
named `rollout-...-<thread id>_<segment id>.jsonl` whose `session_meta` carries:

```json
"history_base": {
  "thread_id": "<previous segment id>",
  "end_ordinal_exclusive": 2318,
  "end_byte_offset": 26935
}
```

`thread_id` points at the **immediately previous segment**, not the root, so the
adapter walks the chain segment by segment. Each segment inherits the caps from
its child and contributes only records below them; the tip contributes
everything. `iter_prompts`, `load`, and `--deep` concatenate the chain oldest
first and deduplicate by `ordinal`, so the full thread is visible exactly once
and abandoned tail records are not counted twice.

Listing and ref resolution report one session per thread. The newest segment
wins, preferring an active segment over an archived one when timestamps tie.
`started` comes from the oldest segment; `cwd`, `branch`, `version`, and
`model` from the tip unless an older record is the only source.

## Prompt extraction

A record becomes a human prompt only when all of these hold:

1. `type` is `response_item` and `payload.type` is `message`.
2. `payload.role` is `user`.
3. When
   `payload.internal_chat_message_metadata_passthrough.content_item_kinds`
   exists, every kind starts with `user.`. Older builds omit the field.
4. After cleaning, the text is not an injected wrapper or a bare slash command.

Injected context is removed before the check:

| Shape | Treatment |
| --- | --- |
| `# AGENTS.md instructions ...` | Excluded. |
| `<environment_context>...</environment_context>` | Stripped; an empty result is excluded. |
| `<skill>`, `<turn_aborted>`, `<recommended_plugins>`, `<user_instructions>` | Excluded. |
| `<system-reminder>`, `<user-prompt-submit-hook>` | Stripped. |
| `<task-notification>...</task-notification>` | Excluded. |
| `<in-app-browser-context>...</in-app-browser-context>` | Block removed; any text after it is kept. |
| `# Files mentioned by the user: ... ## My request for Codex: <text>` | The section after the marker is the prompt. |
| `# Browser comments: ... Comment: <text>` | The text after `Comment:` is the prompt. |
| `## Referenced ChatGPT conversation:` | Excluded. |
| `/review` and other bare slash commands | Excluded. |

`event_msg` copies of user text, `*_output` records, reasoning blocks, and
assistant messages never become prompts. `iter_prompts` returns every human
prompt in thread order without applying generic-prompt filters; only title
selection skips prompts such as `continue`, `继续`, `ok`, or a single character.

## Compaction

`compacted` records carry the latest summary in `payload.message`. `load()`
stores it as `compact_summary` and never treats it as a turn. `summarize()` does
not read compaction; titles come from prompts or the index. `show` renders the
summary under `Compact summary (latest compaction)`; `--summary-chars 0` omits
it.

## Titles

`title` prefers a non-empty `thread_name` in `session_index.jsonl`, then the
latest meaningful prompt, then the first prompt. A generic `thread_name` such as
`继续` is ignored. An index entry without a rollout is never listed.

## Listing and search

`summarize()` makes one streaming pass per rollout: a bounded head (120 records
or 512 KB) for `session_meta`, the first prompt, and the model, plus a bounded
tail (1 MB) for the last prompt, the newest timestamp, and the model. Only lines
that can contain a user message or a `turn_context` are parsed in the tail;
everything else is matched with byte-level prefilters. On a store with about
1,200 rollouts (485 MB compressed) a full listing took about 5–6 seconds.

`--deep` scans the whole chain of each non-archived session. Tokens are matched
against decompressed UTF-8 text, so a match in one session never leaks into
another, and bytes beyond a segment's `end_byte_offset` are not scanned. A
missing zstd decoder makes compressed sessions unreadable rather than partially
misread; they are skipped from listing and deep search.

## Archive state

A rollout is archived when its file lives under `archived_sessions/`. There is
no deleted flag in the rollout or index files, so a removed rollout simply
disappears. Archive state never crosses into another harness.

`show` opens an archived session by ref or path and prints `- archived: yes`;
JSON exposes `archived`; TSV has the trailing `archived` column. Subagent
threads (`thread_source: subagent` or a `source.subagent` object) are not
resumable, so they are never listed, searched, or resolved by ref.

## Digest

`load()` streams the chain once and retains bounded state:

- Up to 50 recent exchanges.
- Up to three assistant text blocks per exchange, 5,000 characters each.
- Up to eight tools per exchange and 20 recent tools overall.
- Edited files from `apply_patch` (`*** Update/Add/Delete File:`), keyed by
  absolute path with a count, capped at 30. Relative paths are resolved against
  the turn cwd.
- No todos: Codex has no per-session todo store, so `show` prints no todo
  section and JSON returns `[]`.

Tool results are not rendered. `turn_count` counts human prompts only.

## zstd

`.jsonl.zst` rollouts are decompressed with `compression.zstd` on Python 3.14+,
falling back to the `zstd` CLI (`zstd -dc --quiet --`). Without either, the
adapter raises a decode error for compressed files and they are skipped. No
pure-Python decompressor is bundled, so Python 3.9–3.13 need the `zstd` binary
for compressed stores.

## Known gaps

- No todo extraction; Codex sessions have no todo files.
- No deleted-session metadata; only the archived directory is authoritative.
- Subagent threads and automation child threads are excluded from listing.
- Attachments, images, and `world_state` are ignored.
- The CLI binary was not executed during verification.
- The 512 KB / 120-record head can miss a first prompt only in pathological
  sessions whose first user message follows very large tool output.
- zstd scanning is chunked, so a token split across a 4 MB chunk boundary could
  in theory be missed; the 512-byte overlap makes this practically impossible.

## Verification

Fixtures are built at runtime by `tests/codex_fixture.py`; the zstd fixture is
only produced when a zstd backend is available.

```bash
python3 - <<'PY'
from pathlib import Path
import tempfile
from tests.codex_fixture import build_codex_home, build_codex_zstd_home
root = Path(tempfile.mkdtemp(prefix="codex-fixture-"))
build_codex_home(root / "home")
build_codex_zstd_home(root / "zstd-home")
print(root)
PY
```

```bash
export FMS_CODEX_HOME="/path/from/above/home"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness codex --limit 0
skills/find-my-session/scripts/fms search --harness codex --include-archived --limit 0
skills/find-my-session/scripts/fms show codex:c0de0001
skills/find-my-session/scripts/fms show codex:c0de0002 --format json
skills/find-my-session/scripts/fms prompts codex:c0de0001 --count
skills/find-my-session/scripts/fms prompts codex:c0de0001 --order newest --limit 2
skills/find-my-session/scripts/fms search --harness codex --deep deep-only-needle
FMS_CODEX_HOME="/path/from/above/zstd-home" \
  skills/find-my-session/scripts/fms search --harness codex --deep zstd-only-needle
```

Expected: three active sessions by default and four with `--include-archived`;
`codex:c0de0002` shows three prompts assembled from two segments; `继续` is
found only with `--deep`; the abandoned base prompt is never reported; and the
compressed session is listed only when a zstd decoder exists.

## Live verification

Checked read-only on macOS against a live store on 2026-10-29: listing,
`--include-archived`, `latest`, `show`, and `prompts` left every rollout file and
`session_index.jsonl` unchanged, and created no WAL, SHM, journal, or cache file.
The only file that changed during the session was the running desktop app's own
`logs_2.sqlite-wal`; the adapter never opens it.
