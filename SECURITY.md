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

## Scope

`find-my-session` is a local, read-only CLI. It performs no network requests and
does not execute anything found in a transcript. Security-relevant areas include:

- Path handling and harness root restrictions
- Accidental reads outside a documented session store
- Output that exposes more data than the requested command implies
- Parsing behavior that could be influenced by a malicious transcript file

## Safe operation

- Run the CLI as the same user that owns the session files.
- Treat `show`, `--deep`, and JSON output as sensitive, because they can print
  conversation content or local paths.
- Review fixture data before contributing it.
