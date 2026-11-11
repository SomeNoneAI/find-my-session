# Compatibility matrix

This is the single detailed compatibility matrix for find-my-session. The READMEs link here instead of repeating per-version detail.

## Legend（图例）

- **Implemented** — adapter code exists, is registered in `fms harnesses`, and is covered by synthetic-fixture tests.
- **Verified** — additionally checked against a real store on a real machine; the version, surface, and date are recorded below.
- **Partial** — implemented, but only some surfaces/versions were verified; the rest are listed as expected or unverified.
- **Expected** — inferred from a sibling surface or shared store, **not** confirmed on a real install.
- **Planned** — researched or reserved, no adapter yet.
- **Not supported** — researched and found unreadable or otherwise impossible to support; the verdict and probe date are recorded below.

Synthetic fixtures prove the parser logic, not ongoing compatibility: a harness app can change its schema in any release, and a fixture that passes today says nothing about next month's build. "Verified" is always a point-in-time statement about the recorded version and date.

## Platform support

| Platform | Status | Details |
| --- | --- | --- |
| macOS | Supported | Primary development and live-verification platform; CI runs on `macos-latest`. |
| Linux | Supported | Pure standard-library Python with POSIX paths; CI runs on `ubuntu-latest`. |
| Windows | Experimental | Exercised by a non-blocking `windows-latest` CI job, green as of 2026-11-04 (synthetic fixtures only). No harness store has been verified against a real Windows install and failures are not release blockers; the verification path for volunteers is [references/windows-verification.md](../skills/find-my-session/references/windows-verification.md). |

## Ready harnesses

| Harness | Status | Verified against | Expected / unverified | Reference |
| --- | --- | --- | --- | --- |
| Qoder CN (`qoder-cn`) | Implemented · Verified | macOS live store re-verified 2026-11-04 (agent `1.1.79-hotfix.7`, 473 sessions readable); desktop app + `qoderclicn` CLI share `~/.qoder-cn` | Linux/Windows app-database paths implemented but unverified | [qoder-cn.md](../skills/find-my-session/references/qoder-cn.md) |
| Qoder international (`qoder`) | Implemented · Partial | macOS, re-verified 2026-11-04 (agent `1.1.79-hotfix.7`, 17 sessions readable) | CLI storage: expected to share `~/.qoder`, no international CLI was available to confirm | [qoder.md](../skills/find-my-session/references/qoder.md) |
| Kimi Code (`kimi-code`) | Implemented · Verified | macOS, re-verified 2026-11-04 (229 sessions all readable; app version not recorded locally); desktop + CLI share one store | — | [kimi-code.md](../skills/find-my-session/references/kimi-code.md) |
| ZCode (`zcode`) | Implemented · Verified | macOS, ZCode 0.17.1 desktop + CLI, re-verified 2026-11-04 (44 sessions readable) | — | [zcode.md](../skills/find-my-session/references/zcode.md) |
| CodeArts Agent (`codearts-agent`) | Implemented · Verified | macOS, CodeArts Agent 26.10.100 (`com.huawei.codearts.agent`), 2026-10-29; desktop only; store re-checked 2026-11-04: present but empty | A future CLI edition is unknown: same database would share the harness, separate store would need a new one | [codearts-agent.md](../skills/find-my-session/references/codearts-agent.md) |
| ChatGPT Codex (`codex`) | Implemented · Partial | macOS, re-verified 2026-11-04 against Codex `0.166.0-alpha.5.1`: 1,210 rollouts listed, 1,137 readable, 73 subagent sessions correctly skipped; desktop, IDE, and CLI share one store | Live `codex` CLI behavior beyond what its rollouts record is unverified (the binary was not executed) | [codex.md](../skills/find-my-session/references/codex.md) |
| DeepSeek Harness (`deepseek`) | Implemented · Verified | Live store on the research machine, re-verified 2026-11-04 (70 compressed logs readable); desktop app is the only shipped surface | App version not recorded; Windows paths untested | [deepseek.md](../skills/find-my-session/references/deepseek.md) |
| Claude Code (`claude-code`) | Implemented · Partial | macOS, Claude Code 2.1.312, re-verified 2026-11-04 (5 sessions readable) | Only the CLI entrypoint was observed; IDE-side metadata is unverified | [claude-code.md](../skills/find-my-session/references/claude-code.md) |
| Cline (`cline`) | Implemented · Partial | macOS, Cline CLI 3.0.74, re-verified 2026-11-04 (106 sessions readable) | Desktop-app metadata beyond the shared transcript shape is unverified; the VS Code extension store is the separate planned `cline-vscode` harness | [cline.md](../skills/find-my-session/references/cline.md) |
| Grok Build (`grok-build`) | Implemented · Partial | macOS arm64, Grok Build 1.0.70, re-verified 2026-11-04 (51 sessions readable), via TUI/CLI sessions | Headless and ACP modes: expected to write the same layout, not exercised separately | [grok-build.md](../skills/find-my-session/references/grok-build.md) |
| WorkBuddy AI (`workbuddy`) | Implemented · Verified | macOS, WorkBuddy AI 5.9.3 (`com.workbuddy.workbuddy-ai`), 2026-10-29; desktop only; store re-checked 2026-11-04: present but empty | — | [workbuddy.md](../skills/find-my-session/references/workbuddy.md) |
| WorkBuddy domestic (`workbuddy-cn`) | Implemented · Verified | macOS, WorkBuddy 5.5.4 (`com.tencent.workbuddy.mac`), 2026-10-29; desktop only; re-verified 2026-11-04: 43/44 sessions readable, 1 legacy transcript with a parse error | — | [workbuddy-cn.md](../skills/find-my-session/references/workbuddy-cn.md) |
| Antigravity (`antigravity`) | Implemented · Verified | macOS arm64, Antigravity 2.28.0 desktop + Antigravity IDE 2.6.0, re-verified 2026-11-04 (405 sessions readable); both editions share one migrated store | No compaction record observed, so `compact_summary` stays empty | [antigravity.md](../skills/find-my-session/references/antigravity.md) |
| Antigravity CLI (`antigravity-cli`) | Implemented · Verified | macOS arm64, `agy` 1.4.9, re-verified 2026-11-04 (484 sessions readable) | — | [antigravity-cli.md](../skills/find-my-session/references/antigravity-cli.md) |
| MiniMax Code (`minimax-code`) | Implemented · Verified | macOS arm64, `mcode` 0.7.1 CLI, re-verified 2026-11-04; 20 top-level conversations listed from the live runtime database; read-only behavior confirmed on a frozen copy of the real store | MiniMax Code 3.1.10 desktop app was observed using the same runtime database but was not confirmed as a session producer; no archived row existed live, so archive filtering is verified by synthetic fixture only | [minimax-code.md](../skills/find-my-session/references/minimax-code.md) |
| Cursor (`cursor`) | Implemented · Partial | macOS arm64, Cursor 3.23.23 desktop app, re-verified 2026-11-04; 4 transcripts listed from the live store, 2 archived rows excluded by default; read-only behavior confirmed against the live store | The `cursor-agent` CLI is expected to share `~/.cursor/projects` but no CLI-originated transcript was observed; the cwd is empty when the editor's `workspaceStorage` manifest for that folder is gone or the session ran without a folder; `model` and `version` are not recorded locally; the older Composer chat store in `state.vscdb` is a different format and is not read | [cursor.md](../skills/find-my-session/references/cursor.md) |
| OpenCode (`opencode`) | Implemented · Verified | macOS arm64, OpenCode 2.2.5, 2026-11-04; 48 top-level sessions listed from the live database, all readable, 0 skipped; `show`, prompt count, prompt paging (oldest/newest), and `doctor` verified; database bytes and mtime unchanged afterwards | No live row had `time_archived` set, so archive filtering is verified by synthetic fixture only; the legacy pre-database `storage/` directory is not read; Linux expected to share the XDG layout but unverified; Windows store location unverified | [opencode.md](../skills/find-my-session/references/opencode.md) |
| Gemini CLI (`gemini-cli`) | Implemented · Verified | macOS arm64, Gemini CLI 0.46.0 (log mentions 0.46.0 → 0.49.0 updates), 2026-11-04; six chat logs across one project directory listed, all readable; `search`, `latest`, `show`, prompt count/paging, and `doctor` verified, chat files unchanged afterwards; the store holds a handful of short real sessions, so wide schema coverage rests on the synthetic fixture | No archive, todo, or compaction records exist in the observed format; Linux expected to share `~/.gemini` but unverified; Windows store location unverified | [gemini-cli.md](../skills/find-my-session/references/gemini-cli.md) |
| Qwen Code (`qwen`) | Implemented · Verified | macOS arm64, Qwen Code 1.0.0-preview, 2026-11-11: one flat-layout session log listed from the live store, `show`/`prompts` verified, `ai-title`, `tasks/` todos, `tool_use` calls, and `errorFallbackMessage` error records all surfaced; files unchanged afterwards. macOS arm64, Qwen Code (`0.8.2` record envelopes), 2026-11-04: nine session logs across four project directories listed, all readable, 0 skipped; `search`, `latest`, `show`, prompt count, and `doctor` verified, files unchanged afterwards | 1.0 records carry no usage totals, so `fms stats` reports `-` for them; no archive state exists, so `--include-archived` is a no-op; Linux expected to share `~/.qwen` but unverified; Windows unverified | [qwen.md](../skills/find-my-session/references/qwen.md) |
| Pi (`pi`) | Implemented · Verified | macOS arm64, Pi `1.5.0` (`@earendil-works/pi-coding-agent`), 2026-11-04; one live session listed, shown, prompt-counted, and `doctor`-checked; transcript bytes and mtimes unchanged afterwards | Only one short live session was observed; tool calls, compaction, and explicit titles rest on the official format docs plus synthetic fixture. Pi has no archive state, so `--include-archived` is a no-op | [pi.md](../skills/find-my-session/references/pi.md) |
| Oh My Pi (`omp`) | Implemented · Verified | macOS arm64, omp `18.16.0` (`@oh-my-pi/pi-coding-agent`), 2026-11-04; one live session listed, shown, prompt-counted, and `doctor`-checked; subagent transcript correctly excluded; transcript bytes and mtimes unchanged afterwards | Only one short live session was observed; compaction is fixture-only, and title changes rest on third-party schema documentation. No archive state exists, so `--include-archived` is a no-op. `history.db` titles are not read | [omp.md](../skills/find-my-session/references/omp.md) |
| CodeBuddy CN (`codebuddy-cn`) | Implemented · Verified | macOS arm64, live store on 2026-11-06: 8 sessions listed, 2 archived via `genie-archived-session-ids` in Local Storage leveldb; default search hides them, `--include-archived` brings them back; `show`, `prompts`, and `doctor` exercised against the real store; database bytes and mtimes unchanged afterwards | 5 of 8 live sessions had no message-queue file, so their digests carry metadata only. Only user turns (`status: sent`) were observed with content; assistant shapes, tool calls, compaction, and usage totals are unimplemented. `cwd` mixes absolute and `~/`-prefixed forms as recorded. Archived ids live in `Local Storage/leveldb/*.log`, not in the session index; a missing log means no archive metadata. Linux/Windows locations unverified. International `codebuddy` is a different product and is not read | [codebuddy-cn.md](../skills/find-my-session/references/codebuddy-cn.md) |

## Planned harnesses

| Harness | Status | Store | Notes | Reference |
| --- | --- | --- | --- | --- |
| Cline VS Code extension (`cline-vscode`) | Planned | VS Code `globalStorage/saoudrizwan.claude-dev` | Different transcript format from the Cline desktop/CLI store; not implemented | [cline.md](../skills/find-my-session/references/cline.md) |
| Windsurf / Devin Desktop | Research | `~/.windsurf`, `~/.codeium/windsurf` | IDE not installed on the research machine; store unknown; [issue #28](https://github.com/SomeNoneAI/find-my-session/issues/28) | — |
| Continue | Research | `~/.continue` | Skills only at home level; sessions believed editor-side; [issue #29](https://github.com/SomeNoneAI/find-my-session/issues/29) | — |

## Not supported harnesses

| Harness | Status | Store | Notes | Reference |
| --- | --- | --- | --- | --- |
| Trae (`trae`) | Not supported | `~/.trae` + `~/Library/Application Support/Trae/ModularData/ai-agent` | macOS arm64, Trae 3.6.13 (`com.trae.app`), probed 2026-11-04: `database.db` is encrypted (no `SQLite format 3` header; ~8.0 entropy over the first 64 KB), `~/.trae` contains no `.jsonl` transcript, and the app has no CLI. No adapter was written | — |
| Trae CN (`trae-cn`) | Not supported | `~/.trae-cn` + `~/Library/Application Support/Trae CN/ModularData/ai-agent` | macOS arm64, Trae CN 3.4.14 (`cn.trae.app`), probed 2026-11-04: same encrypted `database.db`; `state.vscdb` exposes only session ids, working directories, titles, and `messageIds`; no `.jsonl` transcript exists; no CLI. No adapter was written | — |
| Trae 宝 (`trae-bao`) | Not supported · not a separate harness | Shares the Trae CN store | Floating-assistant surface inside Trae CN (`trae.floatingChat.buttonIcon = traebao`, `iCubeFloatingChat` assets), not an independent app, store, or schema; it must not get its own adapter or ref namespace. If Trae CN later exposes a readable transcript, Trae 宝 should be an alias rather than a third harness. Probed 2026-11-04 | — |

**Reproduce the verdict.** Check whether `ModularData/ai-agent/database.db` begins with `SQLite format 3` (it does not in either edition), and whether `~/.trae` or `~/.trae-cn` contains any `*.jsonl` transcript (they do not). A "Not supported" verdict is point-in-time: if a future build writes a readable local transcript, re-run these checks and update this matrix.

## Interpreting this matrix

- "Verified" covers exactly the surfaces listed in that row. If a row says a surface is expected or unverified, treat results there as best-effort until someone records a real check.
- Verification dates are when the check ran, not an expiry; they tell you how stale the claim may be.
- Cross-edition isolation is deliberate: Qoder CN vs international Qoder, WorkBuddy AI vs domestic WorkBuddy, and Antigravity desktop vs its CLI never share refs or stores, even when they share one parser.

## Reporting drift（反馈漂移）

If a harness, edition, or version is unsupported, or a real store no longer matches what its reference documents, ask your agent to draft a report using [references/contribution.md](../skills/find-my-session/references/contribution.md): it defines the consent-first flow, the redacted evidence to collect, and the issue format for the [issue tracker](https://github.com/SomeNoneAI/find-my-session/issues). The [drift report template](https://github.com/SomeNoneAI/find-my-session/issues/new?template=drift_report.yml) collects the same evidence as a structured form. Never attach real session files, credentials, or private paths.

If you verified a harness against a newer real version, update the "Verified against" cell with the version and date, and mention the platform you used.
