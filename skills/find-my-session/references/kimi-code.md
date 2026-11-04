# Kimi Code session store

Status: ready. Adapter: `scripts/fms_lib/harnesses/kimi_code.py`. Harness name: `kimi-code`. Aliases: `kimi`, `kimi-code-cli`, `kimi-code-desktop`.

Kimi Code desktop and the `kimi` CLI write the same store at `~/.kimi-code` and the same session namespace, so one adapter covers both. `kimi-code-cli` and `kimi-code-desktop` are convenience aliases, not separate harnesses; refs resolve to the same session.

## Variants

Verified surfaces: Kimi Code desktop and the Kimi Code CLI. Both create `sessions/<workspace-id>/<session-id>/` trees and `server/events/<session-id>.jsonl` journals in one home directory.

The adapter infers the surface from prompt client metadata. A `clientMetadata` list containing a `kimi_code_composer` object is treated as desktop; anything else is treated as CLI. This is an inference, not a guaranteed field. `SessionSummary.entrypoint` carries the result and `show` prints it as `variants`; treat a surprising value as cosmetic.

The store location can be overridden for tests or non-standard installs:

```bash
export FMS_KIMI_CODE_HOME=/path/to/kimi-code-home
```

The override points at the directory that contains `sessions/`, `server/`, and `session_index.jsonl`.

## Layout

```text
~/.kimi-code/
├── sessions/
│   └── <workspace-id>/
│       └── session_<session-uuid>/
│           ├── state.json
│           └── agents/
│               ├── main/
│               │   └── wire.jsonl
│               └── <other-agent>/
│                   └── wire.jsonl
├── server/
│   └── events/
│       └── session_<session-uuid>.jsonl
├── session_index.jsonl
└── workspaces.json
```

- `sessions/<workspace-id>/session_<uuid>/` is the session directory. The workspace id encodes the project, for example `wd_example-project_0123456789ab`. Do not reverse it; read `cwd` from `state.json` or the session index.
- `state.json` is the small session metadata file. It is the only authority for archive state.
- `agents/main/wire.jsonl` is the main transcript. `agents/<other>/wire.jsonl` belongs to subagents; the adapter ignores those files entirely.
- `server/events/session_<uuid>.jsonl` is an event journal written by the app server. It records the same session as an ordered event stream.
- `session_index.jsonl` maps `sessionId` to `workDir`. It is a fallback for older sessions whose `state.json` has no `cwd`.
- `workspaces.json` and `bin/` are not used by the adapter.
- Session ids look like `session_<uuid>`. `fms` refs use the first eight characters after the prefix, for example `kimi-code:e5f6a7b8`. A leading `session_` in a ref is accepted by `show`; the adapter's `find()` strips it before matching.

Only top-level session directories are listed. `wire.jsonl` files under subagent agents are never treated as sessions.

## Session state

`state.json` is a single JSON object. Observed fields:

| Field | Purpose |
| --- | --- |
| `id` | Full session id, normally `session_<uuid>`. Older files can omit it; the directory name is used. |
| `title` | Stored title. The adapter falls back to prompts when it is missing or generic. |
| `titleKind`, `isCustomTitle` | Title provenance. Not used for extraction. |
| `archived` | Boolean archive flag. `true` hides the session from `search` and `latest`. |
| `archivedAt` | Archive timestamp. Informational. |
| `cwd` | Working directory in newer files. |
| `workDir` | Working directory in older files. Used when `cwd` is absent. |
| `createdAt`, `updatedAt` | ISO 8601 timestamps. |
| `lastPrompt` | Denormalized latest prompt for fast listing. |
| `lastTurnReason` | Last turn outcome. Not used by the digest. |
| `version` | Kimi Code version that wrote the session. Informational. |
| `agents` | Per-agent status. Not used for extraction. |

No deleted-session tombstone has been observed. Deleting a session removes its directory and event journal; there is nothing left to hide. Treat missing state as "not archived".

## Archive metadata

Archive state is read directly from `state.json.archived`. A session is hidden from `search` and `latest` when the value is `true`; `--include-archived` opts it back in. `show` and `prompts` still open an archived session by explicit ref or path and print `- archived: yes`.

This differs from the Qoder adapters, which query a desktop SQLite database. The Kimi adapter never opens a database and never writes to the store.

A session whose `state.json` is missing, unreadable, or has no `archived` field is treated as active. Sessions created and archived entirely by the CLI follow the same rule: the flag is in the shared state file.

## Event journal

The journal starts with a header record and is followed by wrapper records:

```json
{"version":1,"kind":"journal_header","created_at":"..."}
{"kind":"event","seq":1,"envelope":{"session_id":"session_...","timestamp":"...","type":"prompt.submitted","payload":{"agentId":"main","promptId":"...","content":[{"type":"text","text":"..."}]}}}
```

The adapter unwraps `envelope` and ignores `journal_header`. Important envelope types:

| `type` | Purpose |
| --- | --- |
| `event.session.created` | Session metadata, including `session.metadata.cwd`. |
| `prompt.submitted` | A human prompt. |
| `turn.steer` | A message injected during a running turn. Only `origin.kind == "user"` is human. |
| `prompt.steered` | An expanded skill or system body. Never a human prompt. |
| `context.spliced` | Context rewriting. Never a human prompt. |
| `compaction.completed` | Compaction result with `result.summary`. |
| `tool.call.started`, `tool.result` | Tool activity and output. Tool results are not prompts. |
| `session.meta.updated` | Title and metadata updates. Not content. |

Prompt records carry `agentId`. Only absent, `main`, or `agentId == "main"` records are human-facing; subagent prompts are excluded. `promptId` or `userMessageId` identifies a prompt, and the adapter deduplicates repeated submissions by that id.

## Wire transcript

`agents/main/wire.jsonl` is one JSON object per line. It is the primary file for search, `show`, and `--deep`. Important record types:

| `type` | Purpose |
| --- | --- |
| `metadata` | Protocol version and creation time. |
| `profile.bind` | Tool list and `modelAlias`. Used as a model fallback. |
| `turn.prompt` | A human prompt when `origin.kind == "user"`. |
| `turn.steer` | A human steering message when `origin.kind == "user"`. |
| `agent.message.appended` | Assistant or tool-result message. Assistant content blocks are `think` or `text`; tool calls are in `message.message.toolCalls`. |
| `tools.update_store` | Tool state. `key == "todo"` replaces the todo list. |
| `context.apply_compaction` | Compaction. `summary` is preferred over `contextSummary`. |
| `llm.request` | Model name for the request. Used as the primary model source. |
| `usage.record` | Token usage. Only inspected for a model fallback. |
| `file_history.tracked` | File change tracking. Not used; edits are derived from tool calls. |

`agent.message.appended` wraps the actual message in `message.message`. Records with `message.message.role == "user"` are tool results or injected context, never human prompts. `think` blocks are ignored by the digest.

## What the adapter extracts

Summary (bounded head/tail reads):

- `cwd` from `state.cwd`, then `state.workDir`, then session-created event metadata, then the cached `session_index.jsonl` lookup.
- `started`/`updated` from `state.createdAt` and `state.updatedAt`, falling back to event and wire timestamps, then file mtime.
- Title from `state.title` when it is meaningful; otherwise derived from the latest, then the first, meaningful prompt.
- First and latest meaningful human prompts.
- Model from `llm.request.model`, then `profile.bind.modelAlias`, then `usage.record.model`.
- Surface from prompt client metadata, marked inferred.
- Archive flag from `state.archived`.
- `path` is `agents/main/wire.jsonl` when it exists, otherwise the event journal. `--deep` therefore searches the main wire, not the event journal.

Digest (`show`, one streaming pass over the main wire):

- Latest compaction summary, capped at 20,000 characters.
- Recent exchanges, capped at 50, with up to three assistant text blocks of 5,000 characters each.
- Tool counts, up to 20 recent tools, and edited files from `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and `apply_patch`, capped at 30 paths.
- Todos from the latest `tools.update_store` record with `key == "todo"`. Item `title` (or `subject`) becomes the subject; `done` is normalized to `completed`. An empty update clears the list.
- Turn count based on human prompts only.
- Assistant API errors are not a distinct record type in this store; visible assistant text is retained as ordinary text.

Prompts (`prompts`, streaming):

- Every human prompt in transcript order, with its timestamp, after removing system reminders and command wrappers.
- Source preference: the event journal if it yields at least one human prompt; otherwise the wire transcript. The journal and wire are not merged, so a session cannot print the same prompt twice from both sources.
- Excluded: subagent records, `prompt.steered`, skill-activation and other non-user `turn.steer` origins, `context.spliced`, tool results, assistant messages, compaction, and reminder-only prompts.
- Duplicate submissions with the same prompt id are emitted once.
- Prompt text is returned uncapped; the CLI applies `--chars`, `--limit`, and `--offset` without retaining other prompts in memory.

## Todos

```json
{"key":"todo","value":[{"title":"Extract token budget helper","status":"in_progress"},{"title":"Add regression tests","status":"done"}]}
```

Observed statuses: `pending`, `in_progress`, `done`. The adapter normalizes `done` to `completed`. The renderer treats `pending`, `in_progress`, `processing`, and `blocked` as open and lists completed items only when nothing is open.

## Surface inference

Desktop prompts carry:

```json
"clientMetadata":[{"display_text":"...","kimi_code_composer":{"version":1}}]
```

A prompt with that object is marked `desktop`; otherwise it is marked `cli`. The field is observed on desktop-originated prompts and absent on older CLI records, but it is not documented as an API contract. A session can therefore show the wrong surface if Kimi changes the metadata shape. Do not use `entrypoint` for filtering; both surfaces share the store.

## Resume

Verified: kimi --session [id] reopens a session (kimi --continue reopens the most recent; -r/--resume is a hidden alias). fms resume prints kimi --session <id>.

## Caveats

- Desktop and CLI share one namespace. There is no separate desktop database and no separate archive store.
- Deep search scans `agents/main/wire.jsonl` only. Text that exists solely in `server/events/*.jsonl` (for example a spliced context block) is not found by `--deep`. Prompt listing still prefers the journal, so prompt counts can be correct when deep search misses.
- Subagent wires under `agents/<other>/wire.jsonl` are not listed, searched, shown, or counted.
- `session_index.jsonl` is read only as a `cwd` fallback and is cached per process by path, modification time, and size. A stale index can leave `cwd` empty for very old sessions.
- `state.lastPrompt` can lag the wire. The adapter prefers it for fast listing but recomputes the latest prompt during `show`.
- Timestamps are ISO 8601 in current files. The adapter normalizes strings and epoch seconds or milliseconds to UTC.
- Wire records can be large; assistant text is capped in the digest, but `prompts` returns full prompt text unless the CLI caps it.
- Attachments are not rendered. Files referenced by tool calls appear only through edited-file paths.
- New Kimi Code releases can add record types. Unknown types are ignored; add a synthetic fixture before teaching the adapter about a new shape.
- Session data can contain secrets and personal information. Keep the CLI read-only and never commit real transcripts.

## Performance notes

- `search` and `latest` read up to 1 MB / 300 records from the wire head and 256 KB from the tail per session. The session index is read once per process when a `cwd` fallback is needed.
- On a 222-session live store (149 active, 73 archived), a summary pass took about 0.45 seconds.
- `show` streams the main wire once.
- `prompts --count` streams the event journal once when it exists; a listing scans twice and retains only the selected page.
- `--deep` streams every candidate main wire in chunks and never scans archived sessions unless `--include-archived` is passed.

## Verification

From the repository root, run against the synthetic fixture:

```bash
export FMS_KIMI_CODE_HOME="$PWD/tests/fixtures/kimi-code-home"
skills/find-my-session/scripts/fms harnesses
skills/find-my-session/scripts/fms search --harness kimi-code
skills/find-my-session/scripts/fms latest --harness kimi
skills/find-my-session/scripts/fms search --harness kimi-code --include-archived
skills/find-my-session/scripts/fms show kimi-code:e5f6a7b8
skills/find-my-session/scripts/fms show kimi-code:f6a7b8c9
skills/find-my-session/scripts/fms prompts kimi-code:e5f6a7b8 --count
skills/find-my-session/scripts/fms prompts kimi-code:e5f6a7b8 --limit 2 --offset 1
skills/find-my-session/scripts/fms prompts kimi-code:e5f6a7b8 --order newest --limit 2
```

Expected:

- Default listing shows the active desktop fixture and the wire-only CLI fixture, not the archived one.
- `--include-archived` adds the archived fixture and marks it in TSV.
- The desktop digest reports five exchanges, the synthetic model, open and completed todos, a compaction summary, and edited files; it must not contain hidden reasoning, tool-result text, or subagent text.
- `prompts --count` reports 5. The page and newest listing must not contain the skill body, the spliced context, the reminder-only prompt, the subagent prompt, or a duplicate of the first prompt.

Live verification used Kimi Code 0.43.0 on macOS on 2026-10-28: 222 sessions were listed, 149 active and 73 archived, and a desktop session with the expected title was found by `search`, opened with `show`, and counted with `prompts --count` without modifying the store.
