# Diagnosing unreadable sessions

`fms search` and `fms latest` silently skip sessions whose transcripts cannot
be read: a missing zstd decoder, permission problems, corrupt files, or
format drift all look identical to "no sessions here". Two tools tell those
cases apart without printing any session content.

## `fms doctor`

```
fms doctor [--harness NAME ...] [--json]
```

Scans every selected harness store (all ready harnesses by default) and
reports, per store:

- whether the store directory exists (`present` / `not found`; a missing or
  empty store is informational, never an error);
- `candidates` — transcript files the adapter considered;
- `readable` — transcripts that summarized successfully;
- `skipped` — transcripts that failed, grouped into category rows with a
  count, a path-stripped detail line, and an actionable hint when one exists.

Categories:

| Reason | Meaning | Typical fix |
| --- | --- | --- |
| `decoder-missing` | no zstd decoder on this machine | install the `zstd` CLI or use Python 3.14+ |
| `unreadable` | OS-level read failure (permissions, vanished file, undecodable stream) | check file permissions / disk |
| `parse-error` | decoded content is not a recognized transcript (corrupt file, format drift, non-resumable subagent transcript) | upgrade fms; report format drift |
| `unknown` | anything else | report with `fms doctor --json` output |

JSON output schema:

```json
{
  "fms": "0.1.0",
  "python": "3.9.6",
  "platform": "Darwin 25.6.0 arm64",
  "zstd": {"available": true, "python_compression": false, "cli": true, "hint": ""},
  "stores": [
    {
      "harness": "deepseek",
      "variants": "desktop",
      "store": "~/.dsh",
      "home": "~/.dsh",
      "present": true,
      "candidates": 5,
      "readable": 4,
      "skipped": 1,
      "issues": [
        {
          "reason": "parse-error",
          "count": 1,
          "detail": "cannot read DeepSeek session header: <session>",
          "hint": "..."
        }
      ]
    }
  ]
}
```

Reading the result:

- `present: true`, `candidates: 0` — the harness genuinely has no sessions;
- `skipped > 0` — sessions exist but some could not be read; the issue rows
  say why;
- `present: false` — the harness is not installed or uses a different store
  location; `home` shows a redacted form of the directory fms looked in. Check
  any `FMS_<NAME>_HOME` override when the location is unexpected.

## `fms search --verbose` / `fms latest --verbose`

Adds `--verbose` to both listing commands. When any session is skipped during
the scan, a compact warning is written to stderr:

```
fms: warning: 2 session(s) skipped while scanning
fms:   deepseek: 2x decoder-missing: zstd decoder unavailable; install the zstd CLI or use Python 3.14+
fms:     /home/user/.dsh/sessions/.../session.v3.jsonl.zstd
```

- stdout stays clean: TSV or JSON results are exactly what a non-verbose run
  would print, so pipes and scripts are unaffected; exit codes do not change.
- Without `--verbose` nothing is written to stderr, as before.
- Skipped transcript paths are listed only under `--verbose`; the
  count/reason/harness summary lines never contain paths, session ids,
  titles, prompts, or working directories.

## Privacy and read-only guarantees

- Diagnostics never build `fms show`-style exchanges or run `--deep` content
  scans; they only repeat the summarize pass that `search` already performs.
  They do not retain a whole transcript in memory.
- Output contains counts, error categories, and detail lines with session
  paths replaced by `<session>` placeholders. Home-relative store roots use
  `~`; custom roots outside the home directory appear as `<custom>`. Raw paths
  are shown only for skipped transcripts under an explicit `--verbose`.
- Everything is strictly read-only: no command creates, modifies, or locks
  store files (no SQLite WAL/journal files are produced).

## Performance boundaries

`doctor` summarizes every session in the selected stores, so its cost is the
same order as `fms search --limit 0` over the same stores. Adapters with
head/tail summaries keep those bounds; DeepSeek must stream each complete
compressed log, with bounded memory. Prefer `--harness` on hosts with many
stores. `--verbose` adds no extra I/O: it reuses the report that the scan
already collected, and is safe to leave on in scripts that separate stderr.
