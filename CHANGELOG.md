# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- UI panel authentication: `fms-ui` generates a random token at startup,
  passes it through the launch URL, and checks it on every API request,
  together with `Origin`/`Sec-Fetch-Site` validation and exact Host
  matching; write and metadata methods answer 405. Documented in
  `fms_ui/README.md` and `SECURITY.md`.
- Release workflow hardening: every publishing job now requires a `v*` tag
  ref (manual dispatch removed), releases never overwrite existing assets,
  a concurrency group serializes publishes, Python distribution checksums
  are verified before PyPI upload, and the MCP publisher binary is
  downloaded and checksum-verified in a credential-free job.
- Shared presentation defaults in `fms_lib.limits`: CLI and MCP surfaces
  read their `show`/`search`/`prompts` defaults from one module, and the
  MCP `show_session` tool honors its documented `messages`/`chars`
  arguments instead of ignoring them.
- Shared zstd support (`fms_lib.harnesses.zstd_support`): the zstd CLI is
  looked up once per process, and bounded metadata scans of compressed
  Codex/DeepSeek transcripts are memoized by file identity (path, mtime,
  size) in a bounded LRU cache, so long-lived hosts re-query without
  re-decompressing.
- `fms search`/`latest` now truncate with a bounded heap while scoring, so
  a small `--limit` no longer sorts the whole candidate set.

### Changed

- Qwen Code adapter now reads the 1.0-preview store alongside the 0.x one:
  session logs sit flat at
  `~/.qwen/projects/<encoded-cwd>/<session-uuid>.jsonl` (0.x kept them under
  `chats/`), human turns carry Anthropic-style `message.content` blocks with
  `origin.kind: "human"` instead of Gemini-style parts, tool invocations are
  `content[].tool_use` blocks, titles come from `ai-title` records, API
  failures surface via `errorFallbackMessage`, and per-session todos live in
  `~/.qwen/tasks/<session-id>/<n>.json` (`businessInfo.stage`). The 0.x
  layout, record shapes, and `~/.qwen/todos/` files keep working unchanged.
- Documentation consistency pass: `SKILL.md` gains an `fms mcp` section and
  a Qwen troubleshooting entry, both READMEs list all seven MCP tools plus
  the `--explain`/`--timeout` options and the full `--harness`/`--json`
  coverage, `references/extending.md` describes the single-pass prompt
  listing and the ten verified resume commands, the capability checklist in
  `.agents/skills/add-harness/SKILL.md` gains an MCP row, `ROADMAP.md` marks
  the shipped release/distribution items, and the changelog is ordered
  Unreleased-first with versions descending.
- Frontend supply chain: `package-lock.json` is rebuilt from the official
  npm registry (no more npmmirror URLs), `package.json` pins
  `engines.node >= 22` and `packageManager`, a `.nvmrc` pins Node 22,
  `@types/node` matches the runtime, and CI/release install with
  `npm ci --engine-strict` via `node-version-file`.
- Tests run in a clean-room environment (`clear=True` with a sentinel
  HOME/XDG/APPDATA), read-only store tests assert every command exits 0
  with output before comparing byte snapshots, prompt timestamp assertions
  compare exact instants, and a decoy-store test proves no adapter falls
  back to the real home directory.

### Housekeeping

- `code-review-report.md` moved into `docs/`; `.gitignore` now covers
  scratch session exports (`*.jsonl`/`*.db`/`*.sqlite*`) with a
  `tests/fixtures` exception, plus the project-local `.qwen/` settings.

## [0.1.4] - 2026-11-06

### Added

- CodeBuddy CN (`codebuddy-cn`) adapter. The desktop app keeps a session
  index in `CodeBuddy CN/codebuddy-sessions.vscdb` (SQLite `ItemTable`
  with one `session:<id>` row per conversation), message bodies in
  `message-queue/*.json` (`status: sent` items with text blocks),
  per-session todos in `todos/<id>.json`, edited-file snapshots in
  `file-changes/<id>/`, and archive state in Electron Local Storage
  (`genie-archived-session-ids` in `Local Storage/leveldb/*.log`).
  Sessions without a queue file still list and show from index metadata.
  No verified resume command, no usage totals. Documented in
  `skills/find-my-session/references/codebuddy-cn.md`.

- Pi (`pi`) and Oh My Pi (`omp`) adapters. Pi reads the JSONL session tree
  under `~/.pi/agent/sessions`; OMP is a separate fork with its own store
  at `~/.omp/agent/sessions`, `title`/`title_change` records, per-message
  `attribution`, and subagent transcripts that are never listed. Neither
  harness has archive state. Both support prompt listing, handoff digests,
  usage totals, and a verified `resume` command (`pi --session`,
  `omp --resume`).
- `fms mcp`: a Model Context Protocol server on stdio (schema revisions
  2025-06-18 and 2024-11-05) exposing the read-only surface — session
  search, handoff digests, prompt listing, usage stats, and doctor — as
  seven MCP tools for MCP-native hosts. Documented in `docs/mcp.md`.
- `fms stats [--harness] [--cwd] [--since] [--include-archived] [--json]`:
  per-harness token/cost totals from the usage data harness apps
  themselves record (Claude Code and Qwen transcripts, OpenCode's session
  columns), with an optional `usage_summary` adapter hook so more
  harnesses join as their stores are verified — never estimated.
- `fms resume <ref> [--exec] [--json]`: print (or run) the harness command
  that reopens a session — `claude --resume <id>` and `codex resume <id>`
  today, with a handoff-digest fallback for harnesses whose resume command
  is not verified yet. Adapters opt in via the new optional `resume_argv`
  hook.
- `docs/faq.md`: 5-minute tutorial plus answers to the most common
  search/resume/archive questions, linked from both READMEs.
- Session-scale regression budgets: 1k sessions under 5s and 10k under
  30s end-to-end for keyword search (measured ~0.2s/~2s locally).
- `tests/test_json_contract.py`: frozen required-key assertions for
  `harnesses`/`search`/`latest`/`show`/`prompts`/`stats`, matching
  `docs/json-output.md` (additive changes pass, removals fail).
- `SECURITY.md`: read-only/telemetry statement, response-time expectations
  (acknowledge in 3 business days, fix critical exposure in 14).
- `search`/`latest --explain`: per-token scoring breakdowns on stderr.
- `search`/`latest --deep --timeout SECONDS`: stop deep scanning after N
- `fms resume` now covers Cursor (`cursor-agent --resume`), Cline
  (`cline --id`), OpenCode (`opencode --session`), Qwen (`qwen --resume`),
  Kimi (`kimi --session`), and ZCode (`zcode --resume`).
- MCP Registry ready: `server.json` manifest plus `docs/mcp-publishing.md`
  publish guide; `README.md` carries the registry ownership token.

### Fixed

- The `find-my-session` wheel now ships `fms_ui/static/harness-logos/*`,
  so `pip`/`pipx` installs serve harness logos instead of 404ing.
- `skills/find-my-session/SKILL.md` references now link all 21 ready
  harnesses (`opencode`, `gemini-cli`, `qwen`, `pi`, `omp` were missing),
  and the Cursor troubleshooting entry lives under Troubleshooting again.
- CI `packaging` now waits for `test`, `frontend`, and `build`, so broken
  tests or artifacts block wheel/sdist builds.
- `fms prompts` counts and pages in a single `iter_prompts` pass: the
  newest-first path keeps a bounded trailing window instead of replaying
  large transcripts twice, with identical paging semantics.

## [0.1.3] - 2026-11-05

### Changed

- README examples (including `docs/assets/demo.svg` and
  `docs/assets/prompts-paging.svg`) now use Claude Code (`claude-code`)
  instead of Qoder CN, and both READMEs lead with the language-switch link
  plus copy-paste agent prompts such as
  `/find-my-session 找到 claude-code 最近的一个会话，继续那个任务`.

## [0.1.2] - 2026-11-04

### Added

- OpenCode (`opencode`) over `~/.local/share/opencode/opencode.db`: one
  SQLite row store for the CLI, TUI, and IDE extension, with `session_v2`
  preferred over the legacy `session` mirror during the upstream 2.x schema
  migration, subagent child-session exclusion, `time_archived` archive
  state, todo table capture, `patch`-part edited files, compaction
  summaries, prompt extraction with synthetic and slash-command filtering,
  per-session deep search over virtual `opencode.db#<id>` source paths,
  synthetic runtime fixtures, and a per-harness reference.
- Gemini CLI (`gemini-cli`, alias `gemini`) over `~/.gemini/tmp/<project>/chats/`:
  one replayable JSONL chat log per session combining full-array `$set`
  snapshots with appended bare message records, cwd recovery from the
  project's `.project_root`, prompt extraction that skips injected
  `<session_context>` turns and `functionResponse` tool results, tool names
  and API error text in the digest, streaming deep search, synthetic
  fixture tests, and a per-harness reference.
- Qwen Code (`qwen`) over `~/.qwen/projects/<encoded-cwd>/chats/`: one JSONL
  log per chat with Claude Code-style record envelopes and Gemini-style
  message parts, cwd/branch/version from the record envelope, per-session
  todos from `~/.qwen/todos/`, `ui_telemetry` system records skipped,
  `functionCall` tool details in the digest, streaming deep search,
  synthetic fixture tests, and a per-harness reference.

## [0.1.1] - 2026-11-03

### Added

- Cursor (`cursor`, aliases `cursor-agent` and `cursor-ide`) over
  `~/.cursor/projects`: one JSONL transcript per agent conversation under
  `agent-transcripts/<session-id>/`, the desktop conversation index for titles,
  update times, branches, and archive state, `workspaceStorage` manifests to
  recover the real cwd, subagent transcript filtering, `<user_query>` prompt
  extraction, compaction summaries, todo capture, turn error text, deep search,
  synthetic fixture tests, and a per-harness reference.
- MiniMax Code (`minimax-code`, aliases `minimax` and `mcode`) over
  `~/.minimax/v2`: dated `messages.jsonl` transcripts plus one runtime SQLite
  database, database-authoritative listing and prompts, todo events, archive
  and internal-session filtering, compaction fallback, deep search, synthetic
  fixture tests, and a per-harness reference.
- PyPI Trusted Publishing in the release workflow, alongside the existing
  GitHub Release assets and build provenance attestations.
- `fms doctor --fingerprint`, an opt-in redacted shape summary per store:
  layout kinds, top-level field names with value types and counts, sqlite
  tables, columns, and row counts. No values, paths, ids, or timestamps are
  emitted, so output is safe to paste into a public issue when reporting
  format drift. Documented in `references/diagnostics.md` and
  `docs/json-output.md`.
- A CodeQL workflow analyzing Python on `main` and pull requests, plus
  `docs/scorecard.md`, the OpenSSF Scorecard evaluation and adoption plan.
- A README demo of `fms prompts` count and paging
  (`docs/assets/prompts-paging.svg`, synthetic data), linked from both
  READMEs.
- `docs/promotion-plan-0.1.md`, the 0.1 announcement draft and awesome-list
  submission plan.
- Ruff and mypy checks in CI, with the initial mypy findings fixed.
- Dependabot updates for GitHub Actions, Python development dependencies, and
  the frontend.
- An experimental, non-blocking Windows CI job (synthetic fixtures only).
- `docs/json-output.md`, a field-level contract for `--json` output and its
  pre-1.0 stability policy.
- README demo assets for the CLI digest and the browser panel, generated from
  synthetic fixture data.

### Changed

- The top-level `ui` package is now `fms_ui`, avoiding a generic package name
  in installed environments. Both READMEs, build artifacts, tests, and the
  frontend paths were updated.
- Package metadata is single-sourced: the version comes from
  `fms_lib.__version__`, with classifiers, keywords, authors, project URLs, and
  an SPDX license expression.
- The release workflow now checks the tag against the package version, rebuilds
  the frontend, smoke-tests standalone launchers, checksums every asset, and
  publishes Python distributions to PyPI through OIDC.
- Shared adapter helpers (`is_generic`, `choose_title`, `file_path`,
  `tool_detail`) moved to `harnesses/common.py`; harness-specific parsing stays
  in each adapter.
- The skill description is shorter and no longer enumerates every harness; the
  authoritative list stays in the skill body and `fms harnesses`.

### Fixed

- Mypy findings in the Codex, MiniMax Code, Qoder, Kimi Code, and UI server
  code paths.
- Release tests now check the actual source layout of the sdist and the SPDX
  license metadata.

## [0.1.0] - 2026-11-03

First public release.

### Added

- Read-only `fms` CLI with `harnesses`, `search`, `latest`, `show`, `prompts`,
  and `doctor`; keyword and metadata filters, archived-session handling, JSON
  output, and low-token handoff digests.
- Fourteen ready harness adapters and two planned harnesses, documented in
  `docs/compatibility.md` with per-harness reference notes.
- Agent skill packaging and a local browser panel for the same session stores,
  with search filters, paged prompts, recent turns, i18n, and light/dark themes.
- pip/pipx packaging for the `fms` and `fms-ui` commands, plus tag-driven
  GitHub Releases with both standalone ZIPs and SHA-256 checksums.
- Standard-library test suite with synthetic fixtures and CI across Python
  3.9–3.14, frontend type-checking and tests, and release-artifact checks.

### Security

- Local-only operation with no network requests; the UI binds to `127.0.0.1`,
  validates the Host header, and serves a strict CSP.
- Session stores are read-only; SQLite databases are opened read-only.
