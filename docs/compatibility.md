# Compatibility matrix

This is the single detailed compatibility matrix for find-my-session. The READMEs link here instead of repeating per-version detail.

## Legend（图例）

- **Implemented** — adapter code exists, is registered in `fms harnesses`, and is covered by synthetic-fixture tests.
- **Verified** — additionally checked against a real store on a real machine; the version, surface, and date are recorded below.
- **Partial** — implemented, but only some surfaces/versions were verified; the rest are listed as expected or unverified.
- **Expected** — inferred from a sibling surface or shared store, **not** confirmed on a real install.
- **Planned** — researched or reserved, no adapter yet.

Synthetic fixtures prove the parser logic, not ongoing compatibility: a harness app can change its schema in any release, and a fixture that passes today says nothing about next month's build. "Verified" is always a point-in-time statement about the recorded version and date.

## Platform support

| Platform | Status | Details |
| --- | --- | --- |
| macOS | Supported | Primary development and live-verification platform; CI runs on `macos-latest`. |
| Linux | Supported | Pure standard-library Python with POSIX paths; CI runs on `ubuntu-latest`. |
| Windows | Experimental | Exercised by a non-blocking `windows-latest` CI job. Path handling is expected to work, but no harness store has been verified on Windows and failures are not release blockers. |

## Ready harnesses

| Harness | Status | Verified against | Expected / unverified | Reference |
| --- | --- | --- | --- | --- |
| Qoder CN (`qoder-cn`) | Implemented · Verified | macOS live store; desktop app + `qoderclicn` CLI share `~/.qoder-cn`; app version not recorded | Linux/Windows app-database paths implemented but unverified | [qoder-cn.md](../skills/find-my-session/references/qoder-cn.md) |
| Qoder international (`qoder`) | Implemented · Partial | macOS, desktop/IDE `0.4.11` (agent `1.1.75-hotfix.1`) | CLI storage: expected to share `~/.qoder`, no international CLI was available to confirm | [qoder.md](../skills/find-my-session/references/qoder.md) |
| Kimi Code (`kimi-code`) | Implemented · Verified | macOS, Kimi Code 0.43.0, 2026-10-28 (222 sessions: 149 active / 73 archived); desktop + CLI share one store | — | [kimi-code.md](../skills/find-my-session/references/kimi-code.md) |
| ZCode (`zcode`) | Implemented · Verified | macOS, ZCode 0.17.0 desktop + CLI, 2026-10-28 | — | [zcode.md](../skills/find-my-session/references/zcode.md) |
| CodeArts Agent (`codearts-agent`) | Implemented · Verified | macOS, CodeArts Agent 26.10.100 (`com.huawei.codearts.agent`), 2026-10-29; desktop only | A future CLI edition is unknown: same database would share the harness, separate store would need a new one | [codearts-agent.md](../skills/find-my-session/references/codearts-agent.md) |
| ChatGPT Codex (`codex`) | Implemented · Partial | macOS, session metadata and transcripts from Codex 0.163.0–0.165.0-alpha.1.2, 2026-10-29; desktop, IDE, and CLI share one store | Live `codex` CLI behavior beyond what its rollouts record is unverified (the binary was not executed) | [codex.md](../skills/find-my-session/references/codex.md) |
| DeepSeek Harness (`deepseek`) | Implemented · Verified | Live store on the research machine (72 compressed logs listed in ~0.5 s); desktop app is the only shipped surface | App version not recorded; Windows paths untested | [deepseek.md](../skills/find-my-session/references/deepseek.md) |
| Claude Code (`claude-code`) | Implemented · Partial | macOS, session metadata from Claude Code 2.1.305–2.1.312, 2026-10-29 | Only the CLI entrypoint was observed; IDE-side metadata is unverified | [claude-code.md](../skills/find-my-session/references/claude-code.md) |
| Cline (`cline`) | Implemented · Partial | macOS, Cline CLI 3.0.74 (88 sessions), 2026-10-29 | Desktop-app metadata beyond the shared transcript shape is unverified; the VS Code extension store is the separate planned `cline-vscode` harness | [cline.md](../skills/find-my-session/references/cline.md) |
| Grok Build (`grok-build`) | Implemented · Partial | macOS arm64, Grok Build 1.0.70, 2026-10-29, via TUI/CLI sessions | Headless and ACP modes: expected to write the same layout, not exercised separately | [grok-build.md](../skills/find-my-session/references/grok-build.md) |
| WorkBuddy AI (`workbuddy`) | Implemented · Verified | macOS, WorkBuddy AI 5.9.3 (`com.workbuddy.workbuddy-ai`), 2026-10-29; desktop only | — | [workbuddy.md](../skills/find-my-session/references/workbuddy.md) |
| WorkBuddy domestic (`workbuddy-cn`) | Implemented · Verified | macOS, WorkBuddy 5.5.4 (`com.tencent.workbuddy.mac`), 2026-10-29; desktop only | — | [workbuddy-cn.md](../skills/find-my-session/references/workbuddy-cn.md) |
| Antigravity (`antigravity`) | Implemented · Verified | macOS arm64, Antigravity 2.28.0 desktop + Antigravity IDE 2.6.0, 2026-10-29; both editions share one migrated store | No compaction record observed, so `compact_summary` stays empty | [antigravity.md](../skills/find-my-session/references/antigravity.md) |
| Antigravity CLI (`antigravity-cli`) | Implemented · Verified | macOS arm64, `agy` 1.4.9, 2026-10-29 | — | [antigravity-cli.md](../skills/find-my-session/references/antigravity-cli.md) |
| MiniMax Code (`minimax-code`) | Implemented · Verified | macOS arm64, `mcode` 0.7.1 CLI, 2026-11-03; 19 top-level conversations listed from the live runtime database (2 internal task sessions filtered); read-only behavior confirmed on a frozen copy of the real store | MiniMax Code 3.1.10 desktop app was observed using the same runtime database but was not confirmed as a session producer; no archived row existed live, so archive filtering is verified by synthetic fixture only | [minimax-code.md](../skills/find-my-session/references/minimax-code.md) |
| Cursor (`cursor`) | Implemented · Partial | macOS arm64, Cursor 3.23.23 desktop app, 2026-11-03; 4 transcripts listed from the live store, 2 archived rows excluded by default; read-only behavior confirmed against the live store | The `cursor-agent` CLI is expected to share `~/.cursor/projects` but no CLI-originated transcript was observed; the cwd is empty when the editor's `workspaceStorage` manifest for that folder is gone or the session ran without a folder; `model` and `version` are not recorded locally; the older Composer chat store in `state.vscdb` is a different format and is not read | [cursor.md](../skills/find-my-session/references/cursor.md) |
| OpenCode (`opencode`) | Implemented · Verified | macOS arm64, OpenCode 2.2.5, 2026-11-04; 48 top-level sessions listed from the live database, all readable, 0 skipped; `show`, prompt count, prompt paging (oldest/newest), and `doctor` verified; database bytes and mtime unchanged afterwards | No live row had `time_archived` set, so archive filtering is verified by synthetic fixture only; the legacy pre-database `storage/` directory is not read; Linux expected to share the XDG layout but unverified; Windows store location unverified | [opencode.md](../skills/find-my-session/references/opencode.md) |

## Planned harnesses

| Harness | Status | Store | Notes | Reference |
| --- | --- | --- | --- | --- |
| CodeBuddy (`codebuddy`) | Planned | `~/.codebuddy` | Domestic CodeBuddy desktop/IDE is a different product with its own store; reserved, not researched or implemented | — |
| Cline VS Code extension (`cline-vscode`) | Planned | VS Code `globalStorage/saoudrizwan.claude-dev` | Different transcript format from the Cline desktop/CLI store; not implemented | [cline.md](../skills/find-my-session/references/cline.md) |

## Interpreting this matrix

- "Verified" covers exactly the surfaces listed in that row. If a row says a surface is expected or unverified, treat results there as best-effort until someone records a real check.
- Verification dates are when the check ran, not an expiry; they tell you how stale the claim may be.
- Cross-edition isolation is deliberate: Qoder CN vs international Qoder, WorkBuddy AI vs domestic WorkBuddy, and Antigravity desktop vs its CLI never share refs or stores, even when they share one parser.

## Reporting drift（反馈漂移）

If a harness, edition, or version is unsupported, or a real store no longer matches what its reference documents, ask your agent to draft a report using [references/contribution.md](../skills/find-my-session/references/contribution.md): it defines the consent-first flow, the redacted evidence to collect, and the issue format for the [issue tracker](https://github.com/SomeNoneAI/find-my-session/issues). Never attach real session files, credentials, or private paths.

If you verified a harness against a newer real version, update the "Verified against" cell with the version and date, and mention the platform you used.
