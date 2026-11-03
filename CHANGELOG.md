# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- MiniMax Code (`minimax-code`, aliases `minimax` and `mcode`) over
  `~/.minimax/v2`: dated `messages.jsonl` transcripts plus one runtime SQLite
  database, database-authoritative listing and prompts, todo events, archive
  and internal-session filtering, compaction fallback, deep search, synthetic
  fixture tests, and a per-harness reference.

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
