# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## Reporting a vulnerability

Open a private security advisory through the repository's Security tab. Do not
open a public issue for a vulnerability.

Please include:

- The affected version and harness adapter
- Operating system and Python version
- A minimal reproduction using synthetic data
- The impact and any suggested mitigation

Do not attach real session files, credentials, tokens, or private repository
paths. If you must demonstrate a parsing issue, reduce it to a synthetic
transcript.

## Read-only and telemetry

- `find-my-session` is read-only by design: it never writes to session
  files, app databases, or anything inside the harness stores it reads.
  SQLite databases open with `mode=ro`; JSONL transcripts are read, never
  modified. `fms doctor` verifies readability without changing mtimes —
  see `tests/test_cli.py::SafetyTests` and the per-harness
  `do-not-modify` tests.
- There is no telemetry and no update check. The CLI itself makes no outbound
  requests; the UI panel binds to `127.0.0.1` and serves only same-origin static
  assets plus local JSON APIs. The one exception is `fms resume --exec`, which
  launches the harness's own CLI (see the threat model below).
- Fixtures in this repository must be synthetic. Never commit real
  transcripts, paths, emails, tokens, or other session data — see
  `CONTRIBUTING.md`.

## Threat model

- **Local, single-user boundary.** `fms` and the UI panel are meant to run as
  your own user on your own machine. They read session stores that other
  programs on the same machine may also be able to read; the tool does not
  encrypt or isolate that data from other local processes beyond the UI token.
- **UI access token.** Each `fms-ui` launch generates a random token delivered
  once via the opened URL. API requests must present it (`X-FMS-Token`); the
  server also checks the `Host` authority exactly and refuses cross-origin
  (`Origin` / `Sec-Fetch-Site`) and non-`GET` requests. This stops a stray local
  process or a malicious web page from reading session content through the
  panel. The static app shell is served without the token because it contains
  no session data.
- **`resume --exec` crosses the read-only boundary.** It starts the harness's
  own CLI, which may write data and make network requests. That launched
  application is outside this project's read-only guarantee; only run
  `--exec` for harnesses you trust. Without `--exec`, `fms resume` only prints
  the command.
- **Transcripts are untrusted input.** Session content comes from harness apps
  and may contain arbitrary text, including prompt-injection attempts aimed at
  an agent that reads a handoff digest. Treat digest and prompt output as data,
  not instructions.

## Response expectations

- We acknowledge private advisories within 3 business days and aim to ship
  a fix or mitigation within 14 days for issues that expose session content
  beyond the requested command, write to a store, or read outside a
  documented store root.
- Low-severity hardening (error-message wording, fixture hygiene) is
  scheduled like any other bug and credited in `CHANGELOG.md`.
