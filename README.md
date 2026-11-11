# find-my-session
> 🌐 [中文说明](README.zh-CN.md)

[![CI](https://github.com/SomeNoneAI/find-my-session/actions/workflows/ci.yml/badge.svg)](https://github.com/SomeNoneAI/find-my-session/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/SomeNoneAI/find-my-session/badge)](https://scorecard.dev/viewer.html?url=github.com/SomeNoneAI/find-my-session)
[![PyPI](https://img.shields.io/pypi/v/find-my-session.svg)](https://pypi.org/project/find-my-session/)
[![Python 3.9–3.14](https://img.shields.io/badge/python-3.9%E2%80%933.14-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A local, read-only session finder and handoff tool for coding agents, shipped in two forms that share one `fms_lib` core:

- **find-my-session-skill** — an agent skill (`fms` CLI) that finds the right session across harnesses and prints a low-token handoff digest instead of the whole transcript.
- **find-my-session-ui** — a human-friendly browser panel for the same stores.

When a harness runs out of quota, you usually remember *what* you were doing but not *where* the session lives. `fms` answers that with one compact command.

![fms search and fms show in a terminal](docs/assets/demo.svg)

![Counting and paging the human prompts of one session](docs/assets/prompts-paging.svg)

![The find-my-session browser panel reading a synthetic session store](docs/assets/ui.png)

Screenshots use synthetic fixture data.

## Ask your agent

If the skill is installed, just talk to your agent in plain language — no `fms` flags needed:

- `/find-my-session 找到 claude-code 最近的一个会话，继续那个任务`
- `/find-my-session find the most recent claude-code session and continue that task`
- `/find-my-session 额度用完了，在 claude-code 里找昨天关于鉴权的那次会话并接力`
- `/find-my-session search my claude-code sessions about token refresh and show the handoff digest`
- `/find-my-session 列出这个项目最近一次 claude-code 会话里我提过的所有需求`

The agent resolves the harness, runs `search` / `latest` / `show` / `prompts`, and continues the work.

## Supported harnesses

Twenty-two adapters are ready; one more is planned. Verified versions, surfaces, and caveats live in the [compatibility matrix](docs/compatibility.md); per-harness store details live in [references/](skills/find-my-session/references/).

| Harness | Ref prefix | Store |
| --- | --- | --- |
| Qoder CN | `qoder-cn` | `~/.qoder-cn` |
| Qoder (international) | `qoder` | `~/.qoder` |
| Kimi Code | `kimi-code` | `~/.kimi-code` |
| ZCode | `zcode` | `~/.zcode` |
| CodeArts Agent | `codearts-agent` | `~/.codeartsdoer` |
| ChatGPT Codex | `codex` | `~/.codex` |
| DeepSeek Harness | `deepseek` | `~/.dsh` |
| Claude Code | `claude-code` | `~/.claude` |
| Cline | `cline` | `~/.cline` |
| Grok Build | `grok-build` | `~/.grok` |
| WorkBuddy AI | `workbuddy` | `~/.workbuddy-ai` |
| WorkBuddy (domestic) | `workbuddy-cn` | `~/.workbuddy` |
| Antigravity | `antigravity` | `~/.gemini/antigravity` |
| Antigravity CLI | `antigravity-cli` | `~/.gemini/antigravity-cli` |
| MiniMax Code | `minimax-code` | `~/.minimax/v2` |
| Cursor | `cursor` | `~/.cursor/projects` |
| OpenCode | `opencode` | `~/.local/share/opencode` |
| Gemini CLI | `gemini-cli` | `~/.gemini` |
| Qwen Code | `qwen` | `~/.qwen` |
| Pi | `pi` | `~/.pi/agent/sessions` |
| Oh My Pi | `omp` | `~/.omp/agent/sessions` |
| CodeBuddy CN | `codebuddy-cn` | `CodeBuddy CN/codebuddy-sessions.vscdb` |
| Cline (VS Code extension) | `cline-vscode` (planned) | VS Code globalStorage |

## Requirements

- Python 3.9 or newer; macOS or Linux. Python 3.9 is end-of-life upstream and 0.2 is planned to require 3.10+ (see [ROADMAP.md](ROADMAP.md)).
- No third-party Python packages
- Compressed stores (`codex` `.jsonl.zst`, `deepseek` `.zstd`) need a zstd decoder: Python 3.14+ or the `zstd` CLI; otherwise those sessions are skipped
- Windows is exercised by an experimental, non-blocking CI job but is not supported yet; see [ROADMAP.md](ROADMAP.md)

## Install

### CLI and UI commands

`pipx install find-my-session` installs the `fms` and `fms-ui` commands from PyPI. To run an unreleased commit, install from Git instead: `pipx install git+https://github.com/SomeNoneAI/find-my-session.git`. Use `pipx upgrade find-my-session` to upgrade or `pipx uninstall find-my-session` to remove them. With `uv`, `uvx --from find-my-session fms ...` runs the PyPI release without a permanent install.

### For agents: the skill

1. **Release ZIP.** Each GitHub Release publishes `find-my-session-skill.zip`. Download it from the [latest release](https://github.com/SomeNoneAI/find-my-session/releases/latest), then install it into your harness (for example, unzip it into `~/.claude/skills` for Claude Code, or link the directory into your harness's skills folder).
2. **Source checkout.**

   ```bash
   git clone https://github.com/SomeNoneAI/find-my-session.git
   cd find-my-session
   ln -s "$PWD/skills/find-my-session" ~/.claude/skills/find-my-session   # Claude Code; adapt the path for your harness
   ```

   From a checkout you can also run the CLI directly as `python3 skills/find-my-session/scripts/fms`, or run `python3 tools/build_artifacts.py` to build `dist/find-my-session-skill.zip` yourself. To remove a linked skill, delete its symlink from the harness's skills folder.

### For humans: the UI panel

1. **Release ZIP.** Download `find-my-session-ui.zip` from the [latest release](https://github.com/SomeNoneAI/find-my-session/releases/latest), extract it, and run `python3 fms-ui` from the extracted directory (or `./fms-ui` when your extractor preserves executable bits). Replace that directory to upgrade or delete it to uninstall.
2. **pipx.** The same pipx install above provides the `fms-ui` command.
3. **Source checkout.** Run `fms_ui/fms-ui` (use `--no-browser --port 8765` to pick a port without opening a browser).

The panel starts a read-only server on `127.0.0.1` with keyword and metadata filters, session overviews, paged user prompts, recent turns, and copyable refs. The static frontend uses only same-origin JSON APIs — no Node.js, no external assets. Language follows the local system, with an explicit zh/en switch. The interface also follows the system light/dark preference, with a manual toggle and a non-black dark palette. The frontend is built with Vue 3 + TypeScript + Vite; Node.js is needed only when developing it from `fms_ui/frontend/`, never to run the panel.

## Quick start

```bash
fms harnesses                                     # list ready and planned harnesses
fms search "quota handoff" --harness claude-code  # find sessions by keywords
fms latest --harness claude-code --cwd .          # most recent session in this repo
fms show claude-code:c1a0de01                     # low-token handoff digest
fms prompts claude-code:c1a0de01 --count          # count human prompts, then page with --limit/--offset
fms resume claude-code:e1a2b3c4 --exec            # jump straight back into a session
fms stats --since 7d                              # token/cost totals across harnesses
```

Search prefers an explicit `--harness`; omit the query to list recent sessions. Archived sessions are excluded from `search`/`latest` unless `--include-archived` is passed. `show` stays read-only and prints the raw source path so an agent can grep the original file when the digest is not enough.

## Commands

| Command | Purpose |
| --- | --- |
| `fms harnesses` | List ready and planned harnesses, variants, and stores. |
| `fms search [query ...]` | Search session metadata by keywords; omit the query to list recent sessions. |
| `fms latest` | Return the most recent matching session. |
| `fms show <ref>` | Print a handoff digest for one session. |
| `fms prompts <ref>` | List every human prompt in one session; count, page, and order them. |
| `fms mcp` | Run the Model Context Protocol server on stdio: exposes harnesses/search/latest/show/prompts/stats/doctor as read-only MCP tools for MCP-native hosts. See [docs/mcp.md](docs/mcp.md). |
| `fms stats [--harness] [--since] [--json]` | Aggregate the token/cost usage that harnesses themselves record; harnesses without recorded usage show `-`. |
| `fms resume <ref> [--exec]` | Print (or run) the harness command that reopens the session; falls back to the handoff digest when no resume command is verified. |
| `fms doctor [--harness] [--json] [--fingerprint]` | Check the local environment and stores (decoder availability, readable roots, per-harness health); `--fingerprint` adds a content-free shape summary for drift reports. |

## Useful options

| Option | Applies to | Meaning |
| --- | --- | --- |
| `--harness NAME[,NAME]` | search, latest, stats, resume, show, prompts, doctor | Restrict lookup to a harness. Recommended for speed and precision. |
| `--cwd PATH` | search, latest | Match a session whose working directory contains, or is contained by, `PATH`. |
| `--since 7d` / `--since 2026-10-01` | search, latest | Filter by last update time. |
| `--limit N` | search, latest, prompts | Limit results or prompts; `0` means unlimited. |
| `--offset N` | prompts | Skip the first N prompts. |
| `--order oldest/newest` | prompts | Page order; original indices are preserved. |
| `--count` | prompts | Print only the total prompt count. |
| `--deep` | search, latest | Also scan full transcripts. Slower; still prints metadata only. |
| `--explain` | search, latest | Print per-token scoring breakdowns to stderr. |
| `--timeout SECONDS` | search, latest | Stop deep scanning after N seconds and show partial results; `0` means no limit. |
| `--include-archived` | search, latest | Include archived sessions. Off by default. |
| `--verbose` | search, latest | Warn about skipped sessions on stderr without changing stdout. |
| `--messages N` / `--chars N` / `--summary-chars N` | show | Cap turns, per-message characters, and summary characters. |
| `--json` | harnesses, search, latest, stats, resume, prompts, doctor | Machine-readable output; use `--format json` for `show`. See [docs/json-output.md](docs/json-output.md) for the field contract. |

Session references use `harness:session-prefix` (for example `claude-code:c1a0de01`); a raw transcript path from a supported store works too.

### Picking with fzf

Every listing is plain TSV, so interactive picking is a pipe away:

```bash
fms search --limit 0 | fzf | cut -f1 | xargs -I{} fms show {}
fms search --limit 0 --include-archived | fzf --with-nth=2,4 | cut -f1 | xargs -I{} fms resume {}
```

The second recipe resumes the picked session in its own harness when the
harness has a verified resume command (see `fms resume --help`). Desktop/CLI surfaces that share one store share one ref space — see the [compatibility matrix](docs/compatibility.md) for which surfaces are verified.

## Privacy and safety

- Everything runs locally; the CLI makes no network requests.
- The CLI only reads session files and databases, opening SQLite stores read-only; it never edits or deletes session content.
- Search output is metadata-only; `show` and `prompts` can print conversation content, so treat their output like the original transcript.

## Development and documentation

- [CONTRIBUTING.md](CONTRIBUTING.md) — setup, tests, and how to add or verify a harness.
- [docs/compatibility.md](docs/compatibility.md) — the detailed, per-harness compatibility matrix.
- [docs/json-output.md](docs/json-output.md) — the `--json` field contract and pre-1.0 stability policy.
- [docs/faq.md](docs/faq.md) — 5-minute tutorial and answers to the most common "where is my session" questions.
- [ROADMAP.md](ROADMAP.md) — near-term plans.
- [SECURITY.md](SECURITY.md) — supported versions and private vulnerability reporting.
- [skills/find-my-session/references/](skills/find-my-session/references/) — per-harness store schemas and verification recipes; start with [extending.md](skills/find-my-session/references/extending.md) to add a harness.

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q core fms_ui skills/find-my-session/scripts tools tests
python3 tools/build_artifacts.py   # rebuild dist/find-my-session-skill(.zip) and dist/find-my-session-ui(.zip)
```

## License

MIT. See [LICENSE](LICENSE).

<!-- mcp-name: io.github.SomeNoneAI/find-my-session -->
