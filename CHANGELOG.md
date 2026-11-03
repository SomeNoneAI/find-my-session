# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
