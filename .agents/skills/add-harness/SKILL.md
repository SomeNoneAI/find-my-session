---
name: add-harness
description: Add or split harness support in find-my-session, including store research, adapter implementation, prompt listing, archive and deleted-session metadata, synthetic fixtures, tests, reference documentation, and support-matrix updates. Use when implementing a new agent tool or product edition such as Antigravity, DeepSeek Harness, Cline, CodeBuddy, or another database-backed or Qoder-family store.
---

# Add a harness

## Definition of done

A harness is ready only when all of these agree:

- An adapter module under `core/fms_lib/harnesses/`.
- An entry in `READY`, with the matching `PLANNED` entry removed.
- A reference document under `skills/find-my-session/references/`.
- A synthetic fixture, committed or generated at runtime, and tests covering listing, search, latest, show, prompt listing with count and paging, archive state, refs, diagnostics, and read-only behavior.
- The support matrix updated in `SKILL.md`, `README.md`, `README.zh-CN.md`, and `docs/compatibility.md`.
- A `CHANGELOG.md` entry.
- Compile, test, and manual smoke checks passing.

Mark unverified surfaces as "expected" or "unverified". Never claim support you did not observe.

## Capability checklist

Every ready adapter must cover all of these, even if the harness supplies the data in an unusual shape. The shared CLI owns formatting, filtering, counting, and paging; the adapter owns extraction.

| Capability | Adapter surface | Required evidence |
| --- | --- | --- |
| List sessions | `iter_session_paths`, `summarize` | Listing, newest-first ordering, aliases, stable refs. |
| Search and latest | `summarize` metadata | Keyword, id prefix, cwd, since, limit, and no-match behavior. |
| Deep search | Transcript or per-session stored content | `--deep` finds text absent from head/tail metadata and never matches content from another session. |
| Handoff digest | `load` | Markdown and JSON with todos, tools, edits, compaction, and bounded output. |
| Prompt listing | `iter_prompts` | `prompts` total, oldest/newest paging, offset past end, character cap, JSON, and non-human exclusions. |
| Archive and deleted | `SessionSummary.archived` | Default exclusion, `--include-archived`, explicit `show`/`prompts`, and no cross-edition leakage. |
| Ref resolution | `session_id_for`, `owns` | `harness:prefix`, bare prefix, raw path (or virtual source path), and ambiguity errors. |
| Diagnostics | `home`, `iter_session_paths`, `summarize` | `doctor --harness <name>` reports accurate candidate/readable/skipped counts; failures stay sanitized unless `--verbose` explicitly shows paths. |
| Store fingerprint | nothing (shared, derived from candidates) | `doctor --fingerprint` yields content-free shape summaries over the fixture (kinds, field names, counts) with no values, ids, or paths; no adapter code is involved. |
| Read-only operation | Every file and database path | Byte and mtime snapshot unchanged; no WAL or SHM side effects. |

If a capability genuinely does not exist for the harness, document the gap in the reference and keep the shared behavior safe. Never invent data to satisfy the checklist.

## 1. Research the harness

Define the harness boundary first. One harness equals one store and one ref namespace.

- List every surface: desktop, IDE, CLI, extension, and regional or international edition.
- Determine whether the surfaces share a store. If they do not, create separate harness names, as with `qoder-cn` and `qoder`.
- Find the exact store path on each platform and record the version and edition you verified.
- Choose an `FMS_<NAME>_HOME` override. If archive or other metadata lives in an application database, choose a separate `FMS_<NAME>_APP_DB` override.
- Map the layout: transcripts, todo/task files, subagent execution logs, attachments, state, indexes, and app databases.
- If sessions are rows in an application database, map the tables (session, message, part, todo) and the JSON fields that carry role, prompt kind, visibility, tool calls, compaction, and model. Note that there is no per-session file to print as a source path.
- Inspect real records before writing code: human prompts, assistant text, tool calls and results, sidechains, injected or meta content, compaction, timestamps, API errors, model/branch/version fields, and session ids.
- Identify archive and delete state and its authoritative source. Do not infer it from transcript content.
- Measure large-session sizes and decide what `summarize` can read from a bounded head/tail slice.

Keep verified facts separate from assumptions. Never copy real session content, paths, or identifiers into the repository.

## 2. Choose the adapter shape

- Create one adapter per store and edition. Do not merge separate stores behind one harness name.
- If editions share a schema but not a store, extract a shared parser base class and keep thin subclasses. Follow `qoder_family.py`, `qoder_cn.py`, and `qoder.py`.
- If each session is a per-session database plus a readable transcript, keep the transcript as the primary source and fall back to that database's bytes for deep search. Set the per-session database as the summary path and print it as the `source:`. Follow `antigravity_family.py`, `antigravity.py`, and `antigravity_cli.py`.
- If sessions are database rows, use one adapter for the store, set `session_roots()` to `[]`, override `owns()` for the database and its virtual `<db>#<id>` path, and implement `contains()` as a per-session row scan. Follow `zcode.py`.
- Keep all format knowledge in the adapter. The shared CLI, search, and renderer stay format-neutral unless the feature is genuinely cross-harness.
- Treat archive state as cross-harness: the shared CLI consumes `SessionSummary.archived`, so do not filter archived sessions inside the adapter.
- Reuse `fms_lib/util.py`, `models.py`, and existing helpers. Do not add a parallel data model.

## 3. Implement the adapter

Create `core/fms_lib/harnesses/<harness>.py`. Use `references/extending.md` for the minimal subclass skeleton and `qoder.py` for a concrete example.

Required members:

| Member | Requirement |
| --- | --- |
| `name` | Stable lowercase name used in refs. |
| `aliases` | Include the canonical name first; keep aliases unambiguous. |
| `variants` | Human-readable surfaces, for example `desktop, cli`. |
| `store_hint` | Short path shown by `fms harnesses`. |
| `home()` | Resolve the store root and honor `FMS_<NAME>_HOME`. |
| `session_roots()` | Directories used by `show <path>` ownership checks; `[]` for database-only stores. |
| `iter_session_paths()` | Yield only top-level resumable sessions, newest first when cheap. For a database store, yield virtual `<db>#<id>` paths. |
| `summarize(path)` | Return a `SessionSummary` using bounded reads, including `archived`. |
| `load(summary)` | Return a `SessionDetail` with one streaming pass and bounded retention. |
| `iter_prompts(summary)` | Yield every human prompt once, in transcript order, as `UserPrompt`. No paging or caps. |
| `contains(summary, tokens)` | Deep-search hook. Default scans the file; override for database stores to scan only that session's rows. |
| `session_id_for(path)` | Override when the id is not the filename stem. |
| `find(prefix)` | Use the base implementation unless the store needs an index. |
| `owns(path)` | Override only for multiple roots or virtual source paths. |

Extraction rules:

- Accept a human prompt only from human-authored records. Skip tool results, sidechains, injected or meta content, and compaction summaries.
- Expose every human prompt through `iter_prompts` in transcript order, cleaned but uncapped. The CLI owns count, paging, order, character caps, and JSON; do not reimplement them per adapter.
- Strip system reminders and command wrappers. Reject generic prompts such as `continue`, `继续`, or `ok` when choosing a title.
- Prefer a stored title when the harness provides one. Otherwise derive it from the latest meaningful prompt, then the first. Never invent a title from an id when prompts exist.
- Collect cwd, branch, model, version, entrypoint, started/updated time, size, and session id with graceful fallbacks. A database store has no file size; leave it at `0` and say so in the reference.
- Normalize ISO 8601 and epoch-second or epoch-millisecond timestamps to UTC.
- Parse compaction into `compact_summary`, never into `first_prompt` or `last_prompt`.
- Extract todos when the store provides them; otherwise return an empty list and document the gap.
- Track tool names, short tool details, tool counts, recent tools, and edited files with caps.
- Keep assistant API error text: it often explains quota or authentication failures. Ignore thinking and redacted-thinking blocks.
- Do not render attachments; document that they are ignored.
- Never execute, evaluate, or interpret tool-call content.

## 4. Support archive and deleted sessions

Archive state usually lives outside the transcript. Find the authoritative source before coding.

For the Qoder family, the desktop app stores it in Electron `main.sqlite`, table `chat_sessions`. The relevant columns are `session_id`, `archived`, `archived_at`, and `deleted_at`; query only the hidden ids:

```sql
SELECT session_id FROM chat_sessions
WHERE archived = 1 OR deleted_at IS NOT NULL;
```

Implement archive support as follows:

- Open the database read-only with a URI such as `file:/path/main.sqlite?mode=ro`.
- Query only hidden ids: `WHERE archived = 1 OR deleted_at IS NOT NULL`.
- Treat deleted sessions as archived. The shared CLI hides both unless `--include-archived` is passed.
- Treat a transcript with no database row as active. CLI-only sessions can be absent from the desktop database.
- Treat a missing, locked, unreadable, or older-schema database as "no archive metadata", so every session is active. Never create, migrate, repair, or write the database.
- Cache the archive id set per process by database path, modification time, and size.
- Keep the home override and app-database override separate. Never read another edition's database.
- Set `SessionSummary.archived` in `summarize()`. The shared CLI filters before search and before `--deep`, so archived transcripts are not scanned by default.
- Keep `show` able to open an archived session by explicit ref or path. It prints `- archived: yes`; JSON exposes `archived`; TSV has a trailing `archived` column.

Required archive tests:

- Default `search` and `latest` exclude archived sessions.
- `--include-archived` includes them and marks TSV rows.
- `--deep` does not read archived transcripts unless `--include-archived` is passed.
- `show` still opens an archived session by ref and by path.
- Deleted-only rows are hidden by default.
- Archive state does not cross editions.
- The archive database bytes are unchanged and no `-wal` or `-shm` files are created by commands.

If the harness has no archive concept, leave `archived` at its default `False` and say so in the reference document. A database-backed harness can carry the flag on the session row itself or in a separate index table, as ZCode does with `tasks.archived`, `tasks.deleted`, and `tasks.cli_deleted`; treat all three as hidden. Antigravity carries a per-chunk `archived` column in `conversations_fts` and aggregates it per conversation with `MAX(CAST(archived AS INTEGER)) > 0`; a missing FTS table means no archive metadata.

## 5. Register the harness

Edit `core/fms_lib/registry.py`:

1. Import the adapter.
2. Add an instance to `READY`.
3. Remove the matching `PlannedHarness` from `PLANNED`.
4. Verify aliases do not collide with existing or planned harnesses.
5. Run `fms harnesses` and confirm status, variants, store, and aliases.

`fms harnesses` is driven entirely by these tuples. Do not hand-edit its output elsewhere.

## 6. Build fixtures and tests

Create `tests/fixtures/<harness>-home/` with a store-shaped tree. Keep it small and synthetic. If the harness stores sessions in a database, generate the whole home at runtime with a helper such as `tests/zcode_fixture.py` and `PRAGMA journal_mode=DELETE`, so no binary database is committed and no WAL or SHM files appear during tests.

Cover these cases:

- A normal session with prompts, assistant text, tools, and edits.
- A session with missing optional records, such as no last-prompt or no todos.
- A compaction summary.
- Sidechain or subagent records that must not become turns.
- Tool-result records that must not become prompts.
- Task or subagent execution transcripts that must not be listed, searched, or shown as sessions.
- Todo files with multiple statuses.
- Records with API errors, timestamps in both formats, and partially written final lines.
- Real prompts interleaved with tool results, sidechains, meta records, compaction, and denormalized latest-prompt records, so prompt listing can prove its exclusions.

Fixture rules:

- Use `/Users/example/...` paths, invented UUIDs, and invented prompts.
- Never include real session data, usernames, email addresses, tokens, or private repository paths.
- Do not commit binary app databases. Generate a synthetic archive database in `setUpClass` or a helper, as `ArchiveTests` does, and generate database-backed session stores the same way.
- Add a privacy scan that rejects real paths, emails, and unexpected session ids.

Test checklist, in `tests/test_cli.py` or a new test module:

- Harness listing, status, aliases, and store hint.
- Default listing and newest-first ordering.
- Keyword, session-id prefix, cwd, since, limit, and no-match behavior.
- Deep search behavior and archive filtering before deep search. For a database store, prove that a match in one session does not leak into another.
- Latest ordering and query filtering.
- Show Markdown and JSON, including compaction, todos, edited files, and tool summaries.
- Prompt listing: total count, oldest and newest paging, offset past the end, `--chars`, JSON fields, archived sessions, and exclusion of all non-human records.
- Ref resolution by `harness:prefix`, bare prefix, and raw path, plus the virtual source path when the store has no per-session file; unknown and ambiguous refs.
- Cross-harness isolation: refs and archive state never resolve across stores.
- Read-only snapshot of fixture files, mtimes, app databases, and absence of WAL or SHM side effects.

Use environment overrides to point every command at temporary fixture copies. Never let a test read a developer's live store.

## 7. Document the harness

Add `skills/find-my-session/references/<harness>.md` with:

- Status, adapter file, harness name, aliases.
- Variants, whether they share a store, and which surfaces are verified.
- Exact layout and home override.
- File formats, record types, and field-selection rules.
- Prompt, tool-result, sidechain, compaction, todo, archive, and timestamp handling.
- What the digest extracts and what it ignores.
- How `iter_prompts` selects prompts and what it excludes.
- Known gaps, format drift risks, performance notes.
- A verification recipe against the synthetic fixture.

Update these files together:

- `skills/find-my-session/SKILL.md`: support matrix, variants, triggers, and any new user-facing flag.
- `README.md` and `README.zh-CN.md`: status matrix, quick-start example when useful.
- `docs/compatibility.md`: verified versions, surfaces, platforms, dates, and explicit unverified gaps.
- `CHANGELOG.md`: one `Unreleased` entry.
- `skills/find-my-session/references/extending.md`: only when the adapter contract itself changes.
- `AGENTS.md`: only when repository-wide rules or layout change.

## 8. Verify

Run from the repository root:

```bash
python3 -m compileall -q core ui skills/find-my-session/scripts tools tests
python3 -m unittest discover -s tests -v
python3 tools/build_artifacts.py
```

Then smoke-test manually against the synthetic fixture:

```bash
export FMS_<NAME>_HOME="$PWD/tests/fixtures/<harness>-home"
export FMS_<NAME>_APP_DB="$PWD/tmp/synthetic-main.sqlite"   # only if archive exists
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness <name>
skills/find-my-session/scripts/fms latest --harness <name>
skills/find-my-session/scripts/fms search --harness <name> --include-archived
skills/find-my-session/scripts/fms search --harness <name> --deep <needle>
skills/find-my-session/scripts/fms show <name>:<prefix>
skills/find-my-session/scripts/fms prompts <name>:<prefix> --count
skills/find-my-session/scripts/fms prompts <name>:<prefix> --limit 5
skills/find-my-session/scripts/fms prompts <name>:<prefix> --order newest --limit 5
```

If the fixture is generated rather than committed, build it first and point `FMS_<NAME>_HOME` at the generated tree, for example:

```bash
python3 -c 'import sys; sys.path.insert(0, "tests"); from pathlib import Path; from zcode_fixture import build_zcode_home; build_zcode_home(Path("tmp/zcode-home"))'
export FMS_ZCODE_HOME="$PWD/tmp/zcode-home"
```

Finally, repeat read-only checks against one real store: list sessions, search without and with `--include-archived`, show one session, count and page its prompts, compare archived counts, confirm the database is not modified, and record the harness version and platform you tested.

## Reference implementation

- Shared schema example: `core/fms_lib/harnesses/qoder_family.py`.
- Thin edition adapters: `qoder_cn.py` and `qoder.py`.
- Shared-store example: `kimi_code.py`, where desktop and CLI use one store and one harness with aliases.
- Database-backed store example: `zcode.py`, with per-session `contains()`, virtual source paths, and two SQLite databases. `codearts_agent.py` is a second example built on the opencode schema, with `synthetic`-part prompt filtering and a compaction message marker.
- Transcript-plus-app-database example: `workbuddy_family.py` with thin `workbuddy.py` and `workbuddy_cn.py` subclasses, where JSONL transcripts carry the turns, a per-session todo directory carries the todos, and one SQLite database carries the title and archive status. The two editions share a schema but not a store, so they are separate harnesses over one parser.
- Resume-chain example: `codex.py`, where one thread rotates into several rollout segments that are stitched through `history_base` (`thread_id`, `end_ordinal_exclusive`, `end_byte_offset`) for listing, digest, prompt listing, and byte-capped deep search, and compressed `.jsonl.zst` segments are streamed through `compression.zstd` or the `zstd` CLI.
- Single-transcript example: `claude_code.py`, where one JSONL file per session holds prompts, tool calls, compaction, and titles; subagent transcripts under `subagents/` and `agent-*.jsonl` are excluded, the per-project `sessions-index.json` is ignored as stale, and the harness has no archive state.
- Pretty-printed JSON-array example: `cline.py`, where each session is a directory holding `<id>.json` metadata, a pretty-printed `<id>.messages.json` with a top-level `messages` array, and an optional `<id>.compaction.json`. The adapter streams the array with an incremental UTF-8 decoder and `json.JSONDecoder.raw_decode`, widens the tail window until the latest prompt is found, uses a suffix `ref_id` because ids start with a timestamp, scans the compaction file as well as the transcript for deep search, excludes sibling `<agent>__<id>.messages.json` subagent/team transcripts, and has no archive state.
- Cwd-grouped ACP-stream example: `grok_build.py`, where sessions live under `sessions/<encoded-cwd>/<session-id>/` and one `updates.jsonl` event stream carries prompts, assistant chunks, tool calls, plans, and turn boundaries; compaction checkpoints and `chat_history.jsonl` are scanned only for the digest and deep search, subagent child sessions are excluded twice over (`session_kind` and parent `subagents/` directories), and there is no archive state.
- Per-session database example: `antigravity_family.py` with thin `antigravity.py` (desktop plus retired IDE, FTS archive aggregate, legacy transcript root) and `antigravity_cli.py` (separate store, no archive index). Sessions are `conversations/<uuid>.db` files, metadata is in `conversation_summaries.db`, and prompts and turns come from `brain/<uuid>/.system_generated/logs/transcript_full.jsonl`; deep search falls back to the per-session database bytes.
- Compressed versioned single-log example: `deepseek.py`, where each session directory holds `session[.vN].jsonl.zstd` snapshots and the highest `vN` wins, the decompressed log is streamed once with bounded summary state and again for the digest, human prompts require `source.kind == "user"` while injected context reuses `user/message`, archive ids come from `storages/workspace.json`, and `delegationDepth > 0` subagent sessions are excluded.
- Adapter contract: `skills/find-my-session/references/extending.md`.
- Prompt listing tests: `tests/test_cli.py`, class `PromptsTests`.
- Archive and cross-edition tests: `tests/test_cli.py`, class `ArchiveTests`.
- Kimi listing, digest, prompts, and read-only tests: `tests/test_kimi.py`, class `KimiCodeTests`.
- ZCode listing, digest, prompts, deep search, and read-only tests: `tests/test_zcode.py`, class `ZCodeTests`; synthetic store builder `tests/zcode_fixture.py`.
- CodeArts Agent listing, digest, prompts, deep search, archive, and read-only tests: `tests/test_codearts.py`, class `CodeArtsAgentTests`; synthetic store builder `tests/codearts_fixture.py`.
- WorkBuddy listing, digest, prompts, deep search, archive, and read-only tests: `tests/test_workbuddy.py`, class `WorkBuddyTests`; synthetic store builder `tests/workbuddy_fixture.py`.
- WorkBuddy domestic listing, compaction, initial-prompt fallback, archive, cross-harness isolation, and read-only tests: `tests/test_workbuddy.py`, class `WorkBuddyCNTests`; synthetic store builder `tests/workbuddy_cn_fixture.py`.
- Codex listing, resumed-segment chain, compressed rollouts, digest, prompts, deep search, archive, and read-only tests: `tests/test_codex.py`, class `CodexTests`; synthetic store builder `tests/codex_fixture.py`.
- Claude Code listing, wrapper filtering, compaction, todos, subagent exclusion, digest, prompts, deep search, and read-only tests: `tests/test_claude.py`, class `ClaudeCodeTests`; synthetic store builder `tests/claude_code_fixture.py`.
- Cline listing, suffix refs, injected-context filtering, compaction snapshots and compaction-only deep search, subagent exclusion, digest, prompts, and read-only tests: `tests/test_cline.py`, class `ClineTests`; synthetic store builder `tests/cline_fixture.py`.
- Grok Build listing, generated-title fallback, subagent and empty-session exclusion, checkpoint compaction, plan todos, digest, prompts, cross-file deep search, and read-only tests: `tests/test_grok.py`, class `GrokBuildTests`; synthetic store builder `tests/grok_fixture.py`.
- Antigravity listing, archive filtering, migrated IDE transcripts, checkpoint todos, metadata-only sessions, digest, prompts, database-fallback deep search, and read-only tests: `tests/test_antigravity.py`, classes `AntigravityTests` and `AntigravityCLITests`; synthetic store builder `tests/antigravity_fixture.py`.
- DeepSeek listing, version selection, legacy transcript, archive filtering, subagent exclusion, digest, prompts, deep search, metadata-only session, and read-only tests: `tests/test_deepseek.py`, class `DeepSeekTests`; synthetic store builder `tests/deepseek_fixture.py`.
- MiniMax Code listing, digest, prompts, deep search, archive, and read-only tests: `tests/test_minimax_code.py`, class `MiniMaxCodeTests`; synthetic store builder `tests/minimax_code_fixture.py`. The store is a dated `messages.jsonl` transcript plus one `runtime-state.sqlite`; the database is authoritative for listing, messages, todos, archive state, and deep search, while the transcript carries the compaction summary and is the fallback when the database is unavailable.
- Cursor listing, cwd recovery, digest, prompts, deep search, archive, subagent filtering, and read-only tests: `tests/test_cursor.py`, class `CursorTests`; synthetic store builder `tests/cursor_fixture.py`.
- Per-harness docs: `skills/find-my-session/references/qoder-cn.md`, `qoder.md`, `kimi-code.md`, `zcode.md`, `codearts-agent.md`, `codex.md`, `deepseek.md`, `claude-code.md`, `cline.md`, `grok-build.md`, `antigravity.md`, `antigravity-cli.md`, `workbuddy.md`, `workbuddy-cn.md`, and `minimax-code.md`, `cursor.md`.
