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
- There is no telemetry, no network access, and no update check. The CLI
  makes no outbound requests; the UI panel binds to `127.0.0.1` and serves
  only same-origin static assets plus local JSON APIs.
- Fixtures in this repository must be synthetic. Never commit real
  transcripts, paths, emails, tokens, or other session data — see
  `CONTRIBUTING.md`.

## Response expectations

- We acknowledge private advisories within 3 business days and aim to ship
  a fix or mitigation within 14 days for issues that expose session content
  beyond the requested command, write to a store, or read outside a
  documented store root.
- Low-severity hardening (error-message wording, fixture hygiene) is
  scheduled like any other bug and credited in `CHANGELOG.md`.
