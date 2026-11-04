---

> **New in this release:** `search`/`latest` accept `--explain` (per-token
> scoring breakdowns on stderr) and `--timeout SECONDS` (stop deep scanning
> after N seconds, show partial results). See "Why is this result ranked
> first?" and "Deep search is too slow" below.

```bash
fms doctor                                  # are my stores readable?
fms search "quota handoff" --harness kimi-code
fms latest --harness kimi-code --cwd .      # most recent session here
fms show kimi-code:e5f6a7b8                 # low-token handoff digest
fms prompts kimi-code:e5f6a7b8 --count      # how many prompts?
fms prompts kimi-code:e5f6a7b8 --limit 5    # page through them
fms resume claude-code:e1a2b3c4 --exec      # jump back into the session
```

Prefer the browser? Run `fms-ui` and use the same filters visually.

## Frequently asked questions

### Nothing matches my search. What now?

1. Drop one keyword — search is AND-only, every word must match.
2. Drop `--cwd` or `--since`; then try `latest --harness <name>`.
3. Retry once with `--include-archived` — archived sessions hide by
   default. Only the harnesses with real archive state are affected;
   the rest treat the flag as a no-op.
4. Still empty? Run `fms doctor --harness <name>`. Skipped counts with
   `decoder-missing` or `parse-error` mean the store exists but some
   sessions could not be parsed — that is different from "no sessions".

### Which `--harness` do I use for my app?

Desktop and CLI editions that share one store are one harness:
`qoder-cn` vs `qoder` (different products, refs never cross),
`kimi-code`, `zcode`, `codex`, `claude-code`, `grok-build` all cover
their desktop+CLI surfaces. The exceptions with separate stores are
`workbuddy` vs `workbuddy-cn` and `antigravity` vs `antigravity-cli`.
Run `fms harnesses` for the full list; the
[compatibility matrix](compatibility.md) records which surface was
verified for each row.

### Why does the same prefix resolve to the wrong session?

Refs are the first 8 characters of the session id. When two sessions
share a prefix, the CLI errors with an `ambiguous` message listing
candidates — use a longer prefix or the full `harness:id` ref shown
in the error.

### Why is this result ranked first?

Add `--explain`: each hit prints `token=field+points` to stderr, for
example `dark=title/last_prompt+60`. Prefix id matches score highest
(200/100), then cwd (80), title or latest prompt (60), first prompt
(50), and other metadata (10). Every query word must match somewhere
(AND-only). Deep-only matches report `deep-only match` and score 1, so
they rank below any metadata hit.

### Deep search is too slow. Can I stop it early?

Pass `--timeout SECONDS` with `--deep`: scanning stops after N seconds
and the CLI shows the partial results with a stderr warning telling
you how many sessions were scanned. `--timeout 0` (default) means no
limit. Narrow with `--harness` first — that is usually a bigger win
than any timeout.

### `prompts` says "no prompts in this range" — is that an error?

No. It means `--offset` is past the last prompt (`--count` tells you
the total first). `prompts` without `--limit` prints everything;
`--order newest --limit 5` prints the 5 most recent prompts.

### Compressed rollouts are skipped. How do I fix that?

Codex `.jsonl.zst` and DeepSeek `.jsonl.zstd` need a zstd decoder:
Python 3.14+ decodes them natively, otherwise install the `zstd` CLI.
Without either, those sessions are skipped and `doctor` reports
`decoder-missing`.

### The database looks locked. Will `fms` corrupt it?

No. SQLite stores open read-only (`mode=ro`), and the CLI never
writes to session files or app databases. A mid-write database may
degrade to an empty listing or missing archive flags — close or
restart the app and retry.

### Where did my archived session go?

`search` and `latest` exclude archived sessions unless you pass
`--include-archived`. Deleted sessions (Kimi, Grok `/delete`) are
removed from disk and cannot be recovered. Subagent and child
sessions are never listed by design.

### `show` output looks partial. What happened?

The session may use a newer record shape than the adapter knows.
Read the source file narrowly (the digest prints its path) and
report the drift following
[references/contribution.md](../skills/find-my-session/references/contribution.md)
— never paste session content into the report.

### Is my data sent anywhere?

No. Everything runs locally; the CLI makes no network requests and
the UI panel binds to `127.0.0.1`. Treat `show`/`prompts` output
like the original transcript when copying it elsewhere.
