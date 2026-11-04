# Competitive analysis

What other tools in the "find my agent session" space do, and where
find-my-session's CLI and UI can grow. Researched 2026-11-04.

## Landscape

| Tool | Form | What it does | What it lacks |
| --- | --- | --- | --- |
| `claude --resume` / `--continue` | built-in | Pickers and id-based resume inside Claude Code | One harness only |
| [`claude-history`](https://github.com/raine/claude-history) | CLI/TUI | Fuzzy-search Claude Code history, open transcript | One harness; browse only |
| [`clauhist`](https://dev.to/lef237/clauhist-browse-full-claude-code-history-and-resume-sessions-across-projects-1c1o) | CLI (fzf) | Full history across working directories, resume | One harness |
| [`ccrider`](https://news.ycombinator.com/item?id=46512501) | TUI/CLI/MCP | Search and resume sessions; MCP interface | One harness |
| [`cli-continues`](https://github.com/yigitkonur/cli-continues) | CLI | Resume a session in another tool (cross-tool handoff) | Narrow store coverage |
| [`claude-code-history-viewer`](https://github.com/jhlee0409/claude-code-history-viewer) | Desktop app | Unified browse/search/analyze across Claude/Gemini/Codex/Cline | Heavier install; no handoff digests |
| Claude History Viewer (VS Code) | IDE extension | Browse/search/diff, usage and cost tracking | IDE-bound |
| `ccusage`-style trackers | CLI | Token/cost analytics from local stores | No session retrieval |

find-my-session's moat is the combination: **19 harnesses, one read-only
core, low-token handoff digests, an agent skill, and a local web panel**.
The gaps competitors expose:

1. **Resume execution.** Competitors resume sessions (`claude --resume
   <id>`, `codex resume <id>`); fms only prints a digest. A
   `fms resume <ref>` that prints — and with `--exec`, runs — the right
   harness's resume command closes the loop from "found it" to "back in
   it".
2. **Interactive picking.** TUI pickers (fzf-style) are the default
   interaction elsewhere. fms is print-only; the cheap path is explicit
   fzf/rofi interop plus a plain-line output mode, and optionally a
   stdlib `curses` picker later.
3. **Usage and cost analytics.** Stores already carry token/cost data
   (Codex messages, OpenCode `cost`/`tokens_*` columns, Qwen
   `usageMetadata`). A `fms stats` aggregator is unclaimed territory in
   cross-harness form.
4. **MCP interface.** ccrider exposes search over MCP so any agent can
   query sessions. fms reaches agents as a skill; an MCP server would
   widen that to MCP-native hosts.
5. **Diff views.** The VS Code viewer diffs edited files; fms lists them.
   Deeper store parsing; lower priority.

## Priority for this project

1. `fms resume` (CLI) — **shipped** for Claude Code and Codex, with the
   digest fallback for harnesses whose resume command is not verified yet;
   the mapping grows one verified command at a time.
2. `fms stats` — **shipped** for Claude Code, Qwen Code, and OpenCode
   (authoritative session columns and per-message usage); the
   `usage_summary` hook grows the coverage one verified store at a time.
3. fzf/rofi interop recipes in the README (zero code).
4. MCP server — **shipped** (`fms mcp`): seven read-only tools over the
   MCP stdio transport, so MCP-native hosts get the same surface the
   skill provides.
5. UI: surface the resume command and stats in the panel once the CLI
   owns them.
