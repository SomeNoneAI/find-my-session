# 0.1 promotion plan

A short, factual announcement aimed at people who switch between coding
agents and lose sessions when a harness runs out of quota. Nothing here gets
posted until the release gate below passes.

## Release gate (do not post before this)

- [ ] PyPI serving: `https://pypi.org/project/find-my-session/` resolves and
      `pipx install find-my-session` works (#10).
- [ ] The README PyPI badge renders.
- [ ] `pipx` / `uvx` install instructions verified once end-to-end
      (per `RELEASING.md` post-release checks).
- [ ] Latest CI green on `main`.

## Core message

One sentence: **find-my-session finds the session you remember starting — in
any of your installed coding agents — and prints a low-token handoff digest,
so switching harnesses mid-task costs one command instead of an hour of
grep.**

Facts to keep in every post:

- Read-only and local: never writes to session stores; standard-library
  Python; no telemetry.
- 16 ready harnesses (Claude Code, Codex, Cursor, Kimi, Qoder, DeepSeek,
  Antigravity, ZCode, and more) — the compatibility matrix has the verified
  list.
- Ships as an agent skill (`fms` CLI) and a local browser panel
  (`fms-ui`), sharing one core.
- `fms doctor --fingerprint` reports store *shape* without content, so drift
  can be reported upstream safely.
- Link: <https://github.com/SomeNoneAI/find-my-session> (README demo at the
  top of the page shows `search` → `show` → `prompts` paging).

## Show HN

Title: `Show HN: Find-my-session – search every coding agent's local sessions`

Body (keep to ~10 lines, first person, no marketing adjectives):

> I switch between Claude Code, Codex, and Cursor, and whenever one hits its
> quota I could remember what I was doing but not which tool had the
> session. So I built find-my-session: one read-only CLI that indexes the
> local stores of the coding agents already on your machine and prints a
> compact handoff digest (task, todos, recent tools, prompts) you can paste
> into the next harness.
>
> - `fms search "oauth token refresh" --harness claude-code`
> - `fms show <ref>` — the digest; `fms prompts <ref>` — every human prompt,
>   paged
> - `fms doctor` — per-store health; `--fingerprint` reports store shape
>   without any session content, for reporting format drift
>
> Standard-library Python, strictly read-only, no telemetry; also ships as a
> local browser panel. `pipx install find-my-session`. Supported harnesses
> and the verified matrix: <https://github.com/SomeNoneAI/find-my-session>.
>
> Happy to answer questions about the store formats — each one is
> reverse-engineered and pinned by synthetic fixtures.

## Reddit

Post in this order; stop if mods object. Link the repo, use the demo GIF/SVG
from the README, and lead with the quota-handoff story, not the tool list.

| Subreddit | Angle | Caveat |
| --- | --- | --- |
| r/ClaudeAI | "Switching away from Claude Code mid-task?" — Claude Code is one of the stores fms reads and the skill installs into it | Check self-promo rules; flair if required |
| r/ChatGPTCoding | Codex-centric: find the old Codex session when the new tool takes over | Same |
| r/LocalLLaMA | Only if framed around locally-stored CLI agents (Kimi CLI, Qwen Code); otherwise skip — off-topic risk | Lowest priority |

Draft (r/ClaudeAI, adjust the harness names per sub):

> Title: I kept losing threads when switching coding agents, so I made a CLI that searches all of their local sessions
>
> Body: When Claude Code runs out of quota mid-task, the session still
> exists on disk — it just becomes unfindable from the next tool. I built a
> read-only CLI that walks the local stores of Claude Code, Codex, Cursor,
> and ~13 other coding agents, finds the session by keyword/cwd/time, and
> prints a handoff digest: task, todos, recent edits, and every human
> prompt. Paste that into the new harness and continue.
>
> It never writes to the stores, is stdlib-only Python, and ships as an
> agent skill plus a small local web panel. Repo with demo:
> https://github.com/SomeNoneAI/find-my-session — feedback welcome,
> especially which harness store to support next.

## Chinese channels

| Channel | Where | Note |
| --- | --- | --- |
| V2EX | `/go/create`（分享创造节点） | 用中文稿；标题避免标题党，正文贴 demo |
| 即刻 (Jike) | 「一起做产品」「AI探索站」圈子 | 短帖 + demo 图 |
| 少数派 sspai | Matrix 投稿 | 可稍长，强调"只读、本地、隐私"三点 |

Draft (V2EX / Jike,~200 字):

> 标题：find-my-session：跨编码 Agent 检索本地会话的只读 CLI / 技能
>
> 换工具时（Claude Code → Codex → Cursor…）额度用完，之前的会话还在磁盘
> 上，只是换了个工具就找不到了。写了个开源小工具：一条命令跨 16 个
> harness 搜索本地会话，输出低 token 的接力摘要（任务、todo、最近改动、
> 用户提示词），贴给下一个 Agent 就能继续。严格只读、纯标准库、无遥测；
> 附带本地浏览器面板。GitHub：https://github.com/SomeNoneAI/find-my-session
> （README 顶部有演示图，pipx install find-my-session 即装）

## Awesome-list submissions

Submit one PR per list, each following that list's CONTRIBUTING format.
Verify each repo is active before opening the PR.

| List | Fit | Entry angle |
| --- | --- | --- |
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | Strong | Tools section: cross-harness session finder that reads Claude Code stores |
| [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | Strong | Skills section: the `find-my-session-skill.zip` skill |
| [RoggeOhta/awesome-codex-cli](https://github.com/RoggeOhta/awesome-codex-cli) | Good | Tools: Codex store support + handoff out of Codex |
| [e2b-dev/awesome-ai-agents](https://github.com/e2b-dev/awesome-ai-agents) | Broad | Agents/tools section, one line |
| GitHub topics | Self-serve | Add `agent-skills`, `claude-code`, `codex`, `cursor`, `ai-cli` topics on the repo itself |

## Order and follow-up

1. Land #10 (PyPI), verify the gate above.
2. Show HN on a weekday morning US time; monitor the thread for store-format
   questions (they convert into issue reports).
3. Reddit r/ClaudeAI 1–2 days later (avoid same-day collision with HN).
4. V2EX / Jike / sspai the same week; sspai article can reuse the ZH draft
   expanded with the privacy design from `references/diagnostics.md`.
5. Awesome-list PRs last, once the README badge and install commands are
   final, so no list links a broken install.
