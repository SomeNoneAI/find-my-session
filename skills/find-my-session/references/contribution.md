# Reporting drift, missing support, and unclear docs

Use this after a run showed that the skill does not match the harness on disk, and the user agreed to report it. The deliverable is a GitHub issue the user can submit without editing: one title, one body, no session content.

## What is worth reporting

Report only what you observed in this session:

- A harness, edition, or variant the skill does not support: a planned harness such as CodeBuddy or `cline-vscode`, a new agent product, or a regional or international build with its own store.
- A supported harness whose new version changed behavior: moved paths, a newer schema, renamed records, a new compression or database format, or sessions that are now skipped or only partly parsed.
- Documentation drift: `SKILL.md` or a `references/<harness>.md` describes paths, variants, store sharing, archive state, prompt filtering, or environment overrides that no longer match the install.
- A failure that Troubleshooting in `SKILL.md` does not explain and that is not missing data, missing permissions, or a session the user archived or deleted.

Do not report a session that is merely archived, deleted, empty, or unreadable because the app is mid-write. Do not report a guess: if you did not observe the store or the output, stop and say what is missing. If the user mentions an existing issue, offer to add this evidence there instead of opening a duplicate.

## Ask first

Explain in one short block:

- what the user wanted and what the skill expected,
- what you observed instead,
- why it looks like missing support, a version change, or stale documentation,
- that you can draft an issue for the user to review and submit.

Never open, upload, or post anything yourself, and never create a draft issue on the user's behalf. If the user declines, keep the finding in the conversation and move on.

## Privacy gate

Session stores are private. The issue must be useful without exposing them. Never include:

- prompt, assistant, or tool text, diffs, file contents, or any `show` digest output;
- usernames, home directories, repository, project, or customer names, hostnames, emails, conversation titles, or session ids;
- tokens, API keys, cookies, or URLs with credentials.

Prefer shape over content: file and directory names, record `type` values, column names, counts, and exit codes. Replace anything identifying with a placeholder such as `<project>`, `<encoded-cwd>`, `<session-id>`, or `~/`, and say that you did. When a value's shape matters, use a synthetic example.

## Evidence to collect

Collect only what applies, and keep every command read-only.

| Item | How to get it | Redact |
| --- | --- | --- |
| Skill version | `python3 <skill-dir>/scripts/fms --version`, or `fms --version` when it is on `PATH` | nothing |
| Platform | `uname -sm` and the macOS or Linux version | nothing |
| Python | `python3 --version` | nothing |
| Harness | product, edition or variant, and app or CLI version | nothing |
| Harness row | `fms harnesses` | nothing |
| Diagnostics | `fms doctor --json`, optionally with `--harness <name>` | review the output and remove any local paths before sharing |
| Command | the exact `fms` invocation and its exit code | replace `--cwd` with `.`; drop query words that name private work |
| Expected | the sentence from `SKILL.md` or `references/<harness>.md`, plus the file name | nothing |
| Observed | the differing output, stderr, or error | replace paths and ids |
| Store shape | top-level `ls` of the store, one or two levels deep | names only, never file contents; rename anything that encodes a person or project |

For SQLite stores, `sqlite3 <db> '.tables'` and `PRAGMA table_info(<table>)` usually explain the drift; never attach the database. For compressed logs, the decoder used (`zstd` CLI or Python 3.14 `compression.zstd`) matters more than the bytes. If the store cannot be decoded at all, that is itself the finding.

## Pick the template

Submit at [the project issue page](https://github.com/SomeNoneAI/find-my-session/issues/new/choose); if the skill was installed from a fork, use the upstream repository instead.

- **Harness support request** (`[harness] `) for a missing harness, edition, or variant.
- **Bug report** (`[bug] `) for a supported harness that now behaves differently, or for documentation that no longer matches.

A missing harness that blocks a real workflow is still a harness request; note the impact in its caveats field.

## Title

Use `[harness] <product> <edition or variant>` or `[bug] <harness>: <symptom>`. Name the harness and the observable symptom, not a suspected cause; stay under about 70 characters; include a version only when the version is the trigger; never include paths, titles, repositories, or names.

Examples:

- `[harness] CodeBuddy desktop session store`
- `[harness] Cline VS Code extension transcripts`
- `[bug] deepseek: sessions missing after dsh 2.1`
- `[bug] workbuddy-cn: prompts duplicated after <cb_summary>`
- `[bug] docs: antigravity-cli now records archive state`

## Body

Match the issue form so the report is complete without follow-up questions.

````markdown
## Summary

<2-4 sentences: what the user wanted, what the skill expected, and what happened.>

## Environment

- find-my-session: <output of fms --version>
- Skill docs: `SKILL.md` or `references/<harness>.md`, with the section that no longer matches
- Harness: <product, edition or variant, version>
- Platform: <macOS or Linux version, arch>
- Python: <python3 --version>

## Expected

<Quote or paraphrase the documented behavior.>

## Actual

<What happened instead. No session content.>

## Steps to reproduce

1. `<exact fms command, cwd redacted>`
2. <observed result>

## Evidence

```text
<sanitized output or store shape>
```

## Privacy check

- [ ] No session content, prompts, credentials, identifiers, or private paths.
- [ ] Paths, ids, and project names are replaced with placeholders.
- [ ] I am willing to test a fix on this installation. (optional)
````

## Example

A supported harness moved its store after an app update. The agent observed the new path but not the cause.

Title: `[bug] deepseek: sessions missing after dsh 2.1`

````markdown
## Summary

After updating DeepSeek Harness to 2.1, `fms latest --harness deepseek` finds no sessions even though the app lists several recent conversations. The store now lives at `~/.dsh/conversations` instead of `~/.dsh/sessions`, which is the path documented in `references/deepseek.md`.

## Environment

- find-my-session: fms 0.1.0
- Skill docs: `references/deepseek.md`, "Store layout"
- Harness: DeepSeek Harness desktop 2.1
- Platform: macOS 26.1 arm64
- Python: Python 3.14.0

## Expected

`fms latest --harness deepseek` lists recent sessions from `~/.dsh/sessions`.

## Actual

It prints `no sessions matched`. `fms harnesses` still reports `deepseek` as ready.

## Steps to reproduce

1. `fms latest --harness deepseek --cwd .`
2. Output: `no sessions matched`

## Evidence

```text
~/.dsh/
├── conversations/        # new; same per-session layout
│   └── <encoded-cwd>/session-<id>/session.v8.jsonl.zstd
└── storages/workspace.json
```

## Privacy check

- [x] No session content, prompts, credentials, identifiers, or private paths.
- [x] Paths, ids, and project names are replaced with placeholders.
````

## Present it

1. Re-read the draft once against the privacy gate.
2. Give one line of context, then a single fenced block with the title on its own `Title:` line and the body below it, so the user can copy both without editing.
3. Name the submission URL and the template to choose.
4. Offer to shorten, soften, or add evidence, and remind the user that submitting is their call. Do not submit it yourself.

Keep the tone friendly, factual, and short. Assume the maintainer wants the mismatch fixed; describe the impact instead of judging the product ("sessions are not listed", not "the tool is broken"). If the cause is unknown, say so.
