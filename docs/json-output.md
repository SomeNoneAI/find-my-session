# JSON output contract

`fms` prints machine-readable JSON when a command is given `--json`; `fms show`
uses `--format json`. Output is one compact document on stdout, with no
pretty-printing, banners, or progress text.

The examples below use synthetic fixture data. Paths and refs are illustrative.

## General rules

- Exit code `0` means the command succeeded. No matches is success: `search`
  and `latest` print `[]`, and `prompts` reports `total: 0` with an empty
  `prompts` array.
- Usage, lookup, and store errors exit `2` and write a plain-text message to
  stderr. Errors are never JSON. `--verbose` warnings also go to stderr and do
  not change stdout.
- Timestamps are UTC ISO 8601 with a `Z` suffix, or `null` when the harness did
  not record one. `updated` is always present.
- Metadata a harness does not provide is an empty string, not a missing field.
  `archived` is always a boolean.
- `path` is the absolute source path on this machine. `size_bytes` is the
  on-disk size of that source when the adapter can determine it, otherwise `0`.
- `ref` is the stable short reference accepted by `show`, `prompts`, and the UI.
  Treat it as opaque; the text after the colon is a session-id prefix.
- Fields that mirror harness data (`title`, `model`, `todos`, ...) are
  best-effort and vary by adapter. The [compatibility matrix](compatibility.md)
  records what is verified per harness.

## Stability

Before 1.0, the JSON shape can grow but should not silently break:

- New fields may be added in any release. Consumers must ignore unknown fields.
- Existing fields are not removed or renamed without a changelog entry and a
  minor version bump.
- Array order is documented per command. Do not infer identity or persistence
  from an array position.
- Truncation changes content (text length), not the set of fields.

## `fms harnesses --json`

An array with one object per adapter, in registry order:

```json
[
  {
    "name": "qoder-cn",
    "status": "ready",
    "variants": "desktop, cli",
    "store": "~/.qoder-cn",
    "aliases": "qoder-cn, qodercn, qoder_cn, qcn"
  }
]
```

| field | type | meaning |
| --- | --- | --- |
| `name` | string | Canonical harness name used by `--harness`. |
| `status` | string | `ready` or `planned`. |
| `variants` | string | Comma-separated surfaces that share the store. |
| `store` | string | Advisory default store path; may contain `~`. |
| `aliases` | string | Comma-separated accepted names. |

All values are strings, including display-oriented lists.

## Session summaries: `search` and `latest`

`fms search --json` and `fms latest --json` print an array of session summary
objects. `search` returns up to 10 by default; `latest` returns at most 1,
sorted by `updated` descending. `--limit 0` removes the limit. Filters
(`--cwd`, `--since`, `--include-archived`, `--deep`) change which objects are
present, not their shape.

```json
[
  {
    "ref": "qoder-cn:b2c3d4e5",
    "harness": "qoder-cn",
    "session_id": "b2c3d4e5-2222-4b2c-9d2e-222222222222",
    "path": "/Users/example/.qoder-cn/projects/-Users-example-project-beta/b2c3d4e5-2222-4b2c-9d2e-222222222222.jsonl",
    "cwd": "/Users/example/project-beta",
    "title": "Add a dark mode toggle to settings",
    "first_prompt": "Add a dark mode toggle to settings",
    "last_prompt": "Add a dark mode toggle to settings",
    "started": "2026-10-27T14:00:00Z",
    "updated": "2026-10-27T15:30:00Z",
    "branch": "main",
    "model": "qoder-lite",
    "entrypoint": "cli",
    "version": "1.2.3",
    "size_bytes": 4623,
    "variants": "desktop, cli",
    "archived": false
  }
]
```

| field | type | meaning |
| --- | --- | --- |
| `ref` | string | Stable `harness:prefix` reference. |
| `harness` | string | Canonical harness name. |
| `session_id` | string | Full session identifier in the source store. |
| `path` | string | Absolute transcript or source path. |
| `cwd` | string | Working directory recorded by the harness; may be empty. |
| `title` | string | Adapter-chosen summary; usually the latest substantive prompt. |
| `first_prompt` | string | First human prompt when one was found; may be empty. |
| `last_prompt` | string | Latest human prompt when one was found; may be empty. |
| `started` | string or null | Session start, UTC. |
| `updated` | string | Last update, UTC. Always present. |
| `branch` | string | Git branch when the harness recorded one. |
| `model` | string | Model name when recorded. |
| `entrypoint` | string | Surface the adapter inferred (for example `cli`). |
| `version` | string | Harness/app version recorded in the session. |
| `size_bytes` | integer | Source size in bytes, or `0` when unknown. |
| `variants` | string | Comma-separated surfaces for this harness. |
| `archived` | boolean | Archive state exposed by the adapter. |

## `fms show --format json`

One session detail object. Defaults match the Markdown digest: the last 2
exchanges, 600 characters per message block, and a 1000-character compact
summary. The same flags apply in JSON mode:

- `--messages 0` empties `exchanges`; a positive value keeps that many recent
  exchanges. `turn_count` still reports the full count.
- `--chars 0` disables per-message truncation; the default is 600.
- `--summary-chars 0` sets `compact_summary` to `""` (the summary is disabled);
  a positive value truncates it.
- `--no-todos` sets `todos` to `[]`.
- `--no-tools` sets `tool_counts` to `{}`, `recent_tools` to `[]`, and each
  exchange's `tools` to `[]`. Keys are not removed.

The object starts with every [session summary](#session-summaries-search-and-latest)
field, then adds:

| field | type | meaning |
| --- | --- | --- |
| `compact_summary` | string | Latest compaction summary, or `""`. |
| `todos` | array | Objects with adapter-defined `id`, `subject`, `description`, `status`. |
| `turn_count` | integer | Total user/assistant exchanges, before truncation. |
| `exchanges` | array | Recent turns, oldest first within the returned slice. |
| `edited_files` | array | Objects with `path` (string) and `count` (integer), most edited first. |
| `tool_counts` | object | Tool name to call count across the session. |
| `recent_tools` | array | Up to 5 tools, oldest first. |

An exchange has:

| field | type | meaning |
| --- | --- | --- |
| `user` | string | User prompt text. |
| `timestamp` | string or null | Time of the user turn, UTC. |
| `assistant` | array of strings | Assistant text blocks for the turn. |
| `tools` | array | Tool calls during the turn. |

A tool call has `name` (string), `detail` (string, often a path or command),
and `timestamp` (string or null). Todo `status` values are adapter-defined;
`pending`, `in_progress`, and `completed` are common but not guaranteed.

```json
{
  "ref": "qoder-cn:b2c3d4e5",
  "harness": "qoder-cn",
  "session_id": "b2c3d4e5-2222-4b2c-9d2e-222222222222",
  "path": "/Users/example/.qoder-cn/projects/-Users-example-project-beta/b2c3d4e5-2222-4b2c-9d2e-222222222222.jsonl",
  "cwd": "/Users/example/project-beta",
  "title": "Add a dark mode toggle to settings",
  "first_prompt": "Add a dark mode toggle to settings",
  "last_prompt": "Add a dark mode toggle to settings",
  "started": "2026-10-27T14:00:00Z",
  "updated": "2026-10-27T15:30:00Z",
  "branch": "main",
  "model": "qoder-lite",
  "entrypoint": "cli",
  "version": "1.2.3",
  "size_bytes": 4623,
  "variants": "desktop, cli",
  "archived": false,
  "compact_summary": "Earlier work added a theme provider and the ThemeToggle component. Remaining work: verify contrast in light and dark themes.",
  "todos": [
    {
      "id": "2",
      "subject": "Verify contrast in light and dark themes",
      "description": "Check the toggle and surrounding settings text against both themes.",
      "status": "pending"
    }
  ],
  "turn_count": 1,
  "exchanges": [
    {
      "user": "Add a dark mode toggle to settings",
      "timestamp": "2026-10-27T14:00:05Z",
      "assistant": [
        "The toggle component is in place. The remaining work is checking contrast in both themes."
      ],
      "tools": [
        {
          "name": "Edit",
          "detail": "/Users/example/project-beta/src/settings/ThemeToggle.tsx",
          "timestamp": "2026-10-27T15:00:10Z"
        }
      ]
    }
  ],
  "edited_files": [
    {
      "path": "/Users/example/project-beta/src/settings/ThemeToggle.tsx",
      "count": 2
    }
  ],
  "tool_counts": {
    "Write": 1,
    "Edit": 1
  },
  "recent_tools": [
    {
      "name": "Edit",
      "detail": "/Users/example/project-beta/src/settings/ThemeToggle.tsx",
      "timestamp": "2026-10-27T15:00:10Z"
    }
  ]
}
```

## `fms prompts --json`

The object always starts with the session identity and prompt count:

```json
{
  "ref": "qoder-cn:a1b2c3d4",
  "harness": "qoder-cn",
  "session_id": "a1b2c3d4-1111-4a1b-8c1d-111111111111",
  "path": "/Users/example/.qoder-cn/projects/-Users-example-project-alpha/a1b2c3d4-1111-4a1b-8c1d-111111111111.jsonl",
  "cwd": "/Users/example/project-alpha",
  "archived": false,
  "total": 2,
  "offset": 0,
  "limit": 0,
  "order": "oldest",
  "returned": 2,
  "has_more": false,
  "prompts": [
    {
      "index": 1,
      "timestamp": "2026-10-20T09:00:05Z",
      "text": "Add OAuth token refresh to the CLI"
    },
    {
      "index": 2,
      "timestamp": "2026-10-20T09:10:00Z",
      "text": "Also handle PKCE for the desktop login flow"
    }
  ]
}
```

| field | type | meaning |
| --- | --- | --- |
| `total` | integer | Total human prompts in the session, ignoring paging. |
| `offset` | integer | Number of prompts skipped. |
| `limit` | integer | Requested page size; `0` means no limit. |
| `order` | string | `oldest` or `newest`. |
| `returned` | integer | Length of `prompts` in this response. |
| `has_more` | boolean | Whether more prompts exist after this page. |
| `prompts` | array | Page of prompt objects. |

`index` is the 1-based position in the original oldest-first prompt stream, so
it stays stable when `--order newest` or paging is used. `timestamp` may be
`null`. `--chars` truncates `text`; the default `0` returns full text.

With `--count`, the object stops after `total`:

```json
{
  "ref": "qoder-cn:a1b2c3d4",
  "harness": "qoder-cn",
  "session_id": "a1b2c3d4-1111-4a1b-8c1d-111111111111",
  "path": "/Users/example/.qoder-cn/projects/-Users-example-project-alpha/a1b2c3d4-1111-4a1b-8c1d-111111111111.jsonl",
  "cwd": "/Users/example/project-alpha",
  "archived": false,
  "total": 2
}
```

## `fms resume --json`

```json
{
  "ref": "claude-code:c1a0de03",
  "harness": "claude-code",
  "resume_argv": ["claude", "--resume", "c1a0de03-3333-4c3d-9e4f-333333333333"],
  "executed": false
}
```

| field | type | meaning |
| --- | --- | --- |
| `ref` | string | Resolved session reference. |
| `harness` | string | Harness that owns the session. |
| `resume_argv` | array or null | The command to reopen the session, as an argv list; `null` when no resume command is verified for the harness. |
| `executed` | boolean | Whether `--exec` ran the command. |

`resume_argv` is an argv list, never a shell string. The mapping is
deliberately small: only commands verified against the real app are
included.

## `fms doctor --json`

Environment details plus one store entry per selected harness. `doctor` never
reads session content, and it redacts locations outside the home directory.

```json
{
  "fms": "0.1.0",
  "python": "3.13.6",
  "platform": "Darwin 25.6.0 arm64",
  "zstd": {
    "available": true,
    "python_compression": false,
    "cli": true,
    "hint": ""
  },
  "stores": [
    {
      "harness": "qoder-cn",
      "variants": "desktop, cli",
      "store": "~/.qoder-cn",
      "home": "<custom>",
      "present": true,
      "candidates": 2,
      "readable": 2,
      "skipped": 0,
      "issues": []
    }
  ]
}
```

| field | type | meaning |
| --- | --- | --- |
| `fms` | string | CLI version. |
| `python` | string | Interpreter version. |
| `platform` | string | System, release, and machine. |
| `zstd` | object | `available`, `python_compression`, `cli`, and a `hint` when missing. |
| `stores` | array | One entry per selected harness. |

A store entry reports `present` (boolean), `candidates`, `readable`, and
`skipped` counts, and `issues` grouped by reason. `home` is `~/...` when the
store is under the home directory and `<custom>` otherwise, so an overridden or
unusual location is not echoed. An issue has `reason`, `count`, `detail`, and an
optional `hint`; the detail is sanitized and does not include session content.

### `fms doctor --json --fingerprint`

Passing the opt-in `--fingerprint` flag adds one `fingerprint` object per
present store entry. Without the flag the key is never emitted, in text or
JSON. A fingerprint describes store *shape* only — layout kinds, top-level
field names with value types and occurrence counts, sqlite tables, columns,
and row counts. Values, prompts, paths, session ids, timestamps, emails, and
tokens are never included, so the object is safe to paste into a public issue.

```json
"fingerprint": {
  "bounds": {
    "head_bytes": 2000000,
    "records_per_file": 200,
    "fields_per_kind": 64
  },
  "kinds": {
    "jsonl": {
      "files": 2,
      "records": 27,
      "records_unparsed": 0,
      "fields": {
        "cwd": {"str": 19},
        "sessionId": {"str": 27},
        "type": {"str": 27},
        "version": {"str": 19}
      }
    },
    "sqlite": {
      "files": 1,
      "records": 12,
      "tables": [
        {
          "name": "chat_sessions",
          "rows": 12,
          "columns": [
            {"name": "session_id", "type": "TEXT"},
            {"name": "archived", "type": "INTEGER"}
          ]
        }
      ]
    }
  }
}
```

| field | type | meaning |
| --- | --- | --- |
| `bounds` | object | Sampling limits: bytes inspected per file, records per file, and field names per kind. |
| `kinds` | object | One entry per layout kind, keyed by kind name. |
| `kinds.<kind>.files` | number | Candidate files of this kind. |
| `kinds.<kind>.records` | number | Top-level records (or sqlite rows) observed in the sample. |
| `kinds.<kind>.records_unparsed` | number | Lines or elements that did not parse as JSON objects. |
| `kinds.<kind>.fields` | object | Top-level field name → JSON value type → count. Sorted by field name. |
| `kinds.<kind>.truncated_fields` | boolean | Present when more than 64 distinct field names were seen. |
| `kinds.<kind>.tables` | array | sqlite only: table names, column names with declared types, and row counts. |
| `kinds.<kind>.truncated_tables` | boolean | Present when more than 32 tables were seen. |

Kind names: `jsonl` and `json` for record-shaped stores, `sqlite` for
databases, `text` for decodable non-JSON content, `empty`, `binary` (NUL
bytes), `unreadable` (OS-level read failure), and `zstd-undecodable` (a
compressed file with no decoder on the machine). Layout kinds without
record structure (`text`, `empty`, `binary`, `unreadable`,
`zstd-undecodable`) report only `files`. Sampling is deterministic — the
first 2 MB per file (decompressed when needed), 8 MB for single-document
JSON, up to 200 records per file — and field names are sorted, so two runs
over the same store produce the same output.
