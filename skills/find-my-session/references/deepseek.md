# DeepSeek Harness sessions

## Status

- Harness name: `deepseek`
- Adapter: `scripts/fms_lib/harnesses/deepseek.py`
- Aliases: `deepseek`, `deepseek-harness`, `dsh`
- Variants: desktop (`dsh-desktop`)
- Default store: `~/.dsh`
- Override: `FMS_DEEPSEEK_HOME`

The desktop app is the only shipped surface. One store and one session namespace
serve every conversation, so desktop and any future CLI share the `deepseek` ref
space.

## Store layout

```text
~/.dsh/
  sessions/
    <encoded-cwd>/
      session-<session-id>/
        session.lock
        session.v3.jsonl.zstd
        session.v4.jsonl.zstd
  storages/
    workspace.json
```

- `sessions/<encoded-cwd>/` groups sessions by workspace. The adapter treats the
  group name as opaque and never decodes it; cwd comes from the transcript.
- Each `session-<uuid>/` directory holds one or more compressed JSONL transcripts:
  the legacy name `session.jsonl.zstd`, or a versioned `session.vN.jsonl.zstd`.
  Every `vN` file is a complete snapshot, not an append delta, so the highest
  `N` is authoritative; a tie falls back to the newest mtime. Empty files are
  skipped.
- `session.lock` and other non-transcript files are ignored.
- A delegated child session lives in a plain `<uuid>/` directory without the
  `session-` prefix and records `delegationDepth > 0`. It is never listed, so a
  subagent cannot be resumed as a top-level ref.
- `storages/workspace.json` carries the archive list under
  `global.archivedSessionIds`. The adapter reads only that list, read-only. A
  missing or unreadable file degrades to "everything active" instead of failing
  the listing.
- Transcripts are zstd-compressed. Decoding uses `compression.zstd` on Python
  3.14+ or the `zstd` CLI. Without either, the store cannot be read: sessions are
  skipped and the command reports no matches rather than writing anything.

## Transcript format

Each line is one JSON object with `type`, `seq`, `time` (epoch milliseconds),
and `data`. The first record is the header:

```json
{"type": "session", "version": 4, "id": "session-<uuid>",
 "createdAt": 1793000000000, "cwd": "/Users/example/project-alpha",
 "delegationDepth": 0, "isSeeded": false, "agentPreset": "standard"}
```

### Prompts

- A human prompt is `user/message` whose `data.source.kind` is `user`. The text
  lives in `data.content` blocks with `type: text`.
- Injected context reuses `user/message` with another source kind
  (`agent-instructions`, `runtime-context`, `tool-jobs`, and similar). Those
  records never become prompts or Task text.
- A message with only image blocks yields no text and is skipped.
- `agent/inbox/spliced` re-inserts a queued human message for the next turn. Its
  embedded message has the same id as the later `user/message`, so the adapter
  ignores spliced records entirely instead of deduplicating by id.

### Assistant, tools, and state

- `assistant/message` carries `data.message.content` with `text` and `reasoning`
  blocks. The digest keeps only text blocks and bounds them per exchange.
- `assistant/chunk` is ignored except for a `reason.kind == "error"` chunk, whose
  `failure.message` becomes assistant text so API failures stay visible.
- `tool/call` carries `name` and `arguments` as a JSON string. `tool/result` is
  never a prompt and is not listed as a tool call.
- `todo/write` carries the latest todo list; the newest record wins. A
  `todo_write` tool call is treated the same way.
- `compaction/summary` carries the compaction handoff in `data.summary` with
  `data.rawOutput` as a fallback. The latest summary wins; `compaction/prune`
  only describes shadowed ranges and is ignored.
- `working-directory/change` updates the current cwd.
- `session/title` carries the stored title; the latest record wins and can
  appear anywhere in the file.
- `request/header` (`header.config.model`) and `model/selection` carry the model;
  the latest valid value wins.
- Turn, step, request-context, job, permission, sandbox, approval, system,
  developer, subagent-descriptor, and usage records do not contribute to the
  digest.

## Listing

`summarize` decompresses the chosen transcript once and keeps bounded state: the
first and latest human prompt, the latest title, cwd, and model, and the last
event timestamp. zstd frames are not seekable and the title can be mid-file, so a
head/tail read would be wrong or incomplete.

- `updated` is the last record's `time`, falling back to the file mtime.
- `started` is the header `createdAt`.
- `title` prefers the latest `session/title`, then the latest meaningful prompt,
  then the first prompt, then the session id. Generic prompts such as `继续` are
  skipped when deriving a title but still count as prompts.
- `session_id` strips the `session-` prefix so 8-character refs stay meaningful.
- `archived` is membership in `global.archivedSessionIds`, normalized the same
  way and compared case-insensitively.
- `branch` and `version` are always empty; the transcript has no such fields.

## Digest

`load` streams the same transcript once:

- At most 50 exchanges, 3 assistant texts per exchange, 8 tools per exchange,
  and 20 recent tools.
- At most 30 edited files, counted from `edit` and `write` calls. Relative
  `file_path` values resolve against the latest recorded cwd.
- The latest todo list and the latest compaction summary, capped at 20,000
  characters.
- Prompt text is capped at 4,000 characters and assistant text at 5,000
  characters, following the shared renderer's limits.

## Prompt listing

`iter_prompts` yields `user/message` records whose source kind is `user`, in
transcript order, uncapped, once each. It excludes injected source kinds,
image-only messages, spliced inbox duplicates, assistant and tool records,
system and developer messages, and compaction summaries. Counting includes
short and generic prompts.

## Deep search

`contains` streams decompressed chunks with a small overlap, normalizes the text,
and requires every token in that one session. The shared CLI removes archived
sessions before calling it, so an archived session needs `--include-archived`
even for `--deep`.

## Gaps and risks

- No branch, version, or deleted flag. Removing a session directory is the only
  deletion signal; `--include-archived` does not reveal deleted sessions.
- `workspace.json` can be partially populated. It is authoritative only for
  archive ids; titles, models, and prompts come from the transcript. Sessions on
  disk without a workspace row are still listed.
- If a future build starts writing delta segments instead of full snapshots, the
  highest-version rule must be revisited.
- Decompression cost is proportional to total session size. Listing decompresses
  every candidate log; on the research machine 72 logs finished in about half a
  second. No cache is written into the store.
- Tool arguments that fail to parse degrade to a tool name with no detail and no
  edited-file entry.
- Unknown `assistant/chunk` error shapes degrade to no assistant text.
- Windows paths are untested.

## Verification

Build the synthetic store and point the adapter at it:

```bash
python3 -c 'import sys; sys.path.insert(0, "tests"); from pathlib import Path; from deepseek_fixture import build_deepseek_home; build_deepseek_home(Path("tmp/deepseek-home"))'
export FMS_DEEPSEEK_HOME="$PWD/tmp/deepseek-home"
python3 skills/find-my-session/scripts/fms search --harness deepseek
python3 skills/find-my-session/scripts/fms search --harness deepseek --include-archived --limit 0
python3 skills/find-my-session/scripts/fms show deepseek:d5ee0001
python3 skills/find-my-session/scripts/fms prompts deepseek:d5ee0001 --count
python3 skills/find-my-session/scripts/fms search --harness deepseek --deep tool-output-needle
```

The fixture covers an active session with tools, todos, and compaction, an
archived session, an unversioned transcript, a directory with two versions, a
metadata-only session, and a delegated child session. Tests live in
`tests/test_cli.py` (class `DeepSeekTests`) and are skipped when no zstd decoder
is available.

For a live check, never read `~/.dsh/.credentials.yaml` or print prompt text.
List sessions, compare archive counts with and without `--include-archived`,
show one known session, count its prompts, and snapshot file bytes and mtimes to
confirm the store is unchanged.
