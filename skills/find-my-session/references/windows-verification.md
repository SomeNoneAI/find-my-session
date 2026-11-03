# Verifying a harness on Windows

First-class Windows support (issue #13) needs real-store verification from
someone running Windows. This is that verification path. The synthetic
Windows CI job is already green; what it cannot prove is how the harness
apps behave on a real Windows install.

## Before you start

- Read the privacy gate in [contribution.md](contribution.md): everything
  below is read-only, and nothing that leaves your machine may contain
  session content, real paths, or ids.
- Python 3.9+ installed (`python --version`). No third-party packages.

## 1. Point fms at your store

Every harness honors a `FMS_<NAME>_HOME` override (see the harness's
reference for the exact name). Point it at the store the app actually uses,
for example:

```powershell
$env:FMS_CLAUDE_HOME = "$env:USERPROFILE\.claude"
```

Run `fms harnesses` and confirm the harness row shows the store you expect.

## 2. Read-only smoke battery

Run this for each harness you use and keep the output:

```powershell
fms doctor --harness <name> --json
fms doctor --harness <name> --fingerprint --json
fms search --harness <name> --limit 0
fms latest --harness <name>
fms show <ref-from-latest> --format json
fms prompts <ref-from-latest> --count
fms prompts <ref-from-latest> --limit 2
```

Record per harness: the doctor counts (`candidates`/`readable`/`skipped`),
the issue rows if any, whether the newest session's digest renders, and the
prompt count.

## 3. Read-only guarantee check

Before the battery, snapshot bytes and mtimes; after it, compare:

```powershell
Get-ChildItem -Recurse <store> -File | Get-FileHash -Algorithm SHA256 | Set-Content before.txt
# ... run the battery ...
Get-ChildItem -Recurse <store> -File | Get-FileHash -Algorithm SHA256 | Set-Content after.txt
fc.exe before.txt after.txt
```

Also confirm no `-wal`/`-shm` files appeared next to any SQLite store that
did not have them before.

## 4. What we care about on Windows specifically

- **Path separators.** Digests must echo recorded paths as the harness
  wrote them (no `\` ↔ `/` rewriting). Eyeball the edited-file lists and
  `source:` lines.
- **CRLF stores.** Pretty-printed transcripts written by a Windows app may
  use CRLF (this already bit Cline's parser once). If `prompts --count`
  looks too low, say so — that is a finding.
- **Home resolution.** Confirm `FMS_<NAME>_HOME` overrides and default
  locations (`%USERPROFILE%`, `%LOCALAPPDATA%`, `%APPDATA%`) resolve where
  the app actually stores data. The references document the macOS/Linux
  paths; Windows paths are exactly what we need recorded.
- **SQLite access.** Read-only mode must not create `-wal`/`-shm` side
  files for databases that did not have them.

## 5. Reporting

File the [drift report](https://github.com/SomeNoneAI/find-my-session/issues/new?template=drift_report.yml)
(or a harness support request for stores that do not parse at all) with:

- Windows edition and version, Python version, `fms --version`;
- per-harness doctor counts and issue rows (redacted);
- which paths resolved and which did not;
- the read-only check result.

Maintainers will turn a clean report into matrix rows. A harness is
"Windows-verified" only after its real store parses and the read-only
guarantee holds on your machine.
