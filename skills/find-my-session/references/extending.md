# Adding a harness adapter

Each harness gets one adapter subclass, one reference document, one synthetic fixture home, and tests. Keep the shared CLI format-neutral; all format knowledge belongs in the adapter.

## Adapter contract

Create `core/fms_lib/harnesses/<harness>.py` with a subclass of `HarnessAdapter`:

```python
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from ..models import SessionDetail, SessionSummary, UserPrompt
from .base import HarnessAdapter


class ExampleAdapter(HarnessAdapter):
    name = "example"
    aliases = ("example", "ex")
    variants = "desktop, cli"
    store_hint = "~/.example"

    def home(self) -> Path:
        override = os.environ.get("FMS_EXAMPLE_HOME")
        if override:
            return Path(override).expanduser()
        return Path.home() / ".example"

    def session_roots(self) -> list[Path]:
        return [self.home() / "sessions"]

    def iter_session_paths(self) -> Iterator[Path]:
        root = self.home() / "sessions"
        if not root.is_dir():
            return
        paths = [path for path in root.glob("*/*.jsonl") if path.is_file()]
        paths.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        yield from paths

    def summarize(self, path: Path) -> SessionSummary:
        ...

    def load(self, summary: SessionSummary) -> SessionDetail:
        ...

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        ...
```

Required attributes and methods:

| Member | Requirement |
| --- | --- |
| `name` | Stable lowercase harness name used in refs, for example `claude-code`. |
| `aliases` | User-facing aliases; the first should equal `name` if reasonable. |
| `variants` | Human-readable surfaces, for example `desktop, cli`, `cli, ide`. |
| `store_hint` | Short store path shown by `fms harnesses`. |
| `home()` | Resolve the store root and honor an `FMS_<NAME>_HOME` override for tests. |
| `session_roots()` | Directories that contain session files; used by `show <path>` ownership checks. Defaults to `home()/projects`. |
| `iter_session_paths()` | Yield transcript paths, newest first when cheap. Do not summarize here. |
| `summarize(path)` | Return a `SessionSummary` using bounded reads. |
| `load(summary)` | Return a `SessionDetail` for one session. |
| `iter_prompts(summary)` | Yield every human prompt once, in transcript order, as `UserPrompt(text, timestamp)`. Apply no paging or character caps here. |
| `session_id_for(path)` | Override when the id is not the filename stem. |
| `find(needle)` | Prefix search. The base implementation is usually sufficient. |
| `owns(path)` | Path containment. Override only for multi-root stores, or for a database-backed store's virtual source path. |
| `contains(summary, tokens)` | Deep-search hook used by `--deep`. Defaults to scanning the source file; override for database-backed stores so only that session's rows are scanned. |

`SessionSummary` fields: `harness`, `session_id`, `path`, `cwd`, `updated`, `title`, `first_prompt`, `last_prompt`, `started`, `branch`, `model`, `entrypoint`, `version`, `size`, `variants`, `archived`, `ref_id`.

`ref_id` is optional. By default, `summary.ref` renders the first eight characters of `session_id`. When ids start with something meaningless such as a millisecond timestamp, set `ref_id` to a short unique suffix and override `find()` to match the raw id, the id without its product prefix, and the suffix, as `cline` does with `session_1793000000100_c1a0d` → `cline:c1a0d`.

`SessionDetail` fields: `summary`, `compact_summary`, `todos`, `exchanges`, `edited_files`, `tool_counts`, `recent_tools`, `turn_count`.

`UserPrompt` fields: `text`, `timestamp`. The CLI assigns 1-based chronological indices and owns counting, paging, ordering, character caps, and JSON output.

Use `ToolCall`, `Exchange`, and `UserPrompt` from `models.py`; do not invent parallel structures.

## Implementation rules

1. Read-only. Never write, rename, delete, lock, or repair a session file or an external metadata database. Do not create cache files inside the store.
2. Standard library only. The CLI supports Python 3.9+, so avoid newer syntax and third-party packages.
3. Bounded search. `summarize` must read only a head and tail slice, or index metadata if the harness provides one. Never parse a whole transcript just to list sessions.
4. Single full read for `show`. `load` may stream the selected transcript once. Keep deques and character caps; do not retain the whole file.
5. Missing data is normal. Handles absent titles, timestamps, branches, todos, compaction summaries, and partially written final lines without raising.
6. Tool results are not prompts. Exclude tool-result records, sidechains, injected/meta records, and system reminders from turns and titles.
7. Compaction summaries are not prompts. Parse them into `compact_summary`, not into `first_prompt` or `last_prompt`.
8. Multi-variant stores. If desktop and CLI share a store, use one adapter and list both variants. If they differ, create separate harness names such as `qoder` and `qoder-cn`.
9. Character caps. Truncate prompts, assistant text, summaries, and tool details so one pathological session cannot flood the context window.
10. Deterministic ordering. Sort by update time where possible; the CLI re-sorts results.
11. Archive state is metadata, not a separate store. If the harness records archive or delete state outside the transcript (for example in an app SQLite database), read it read-only and set `SessionSummary.archived`. Missing records mean active; missing or unreadable metadata must degrade to all-active. The CLI filters archived sessions before search, including `--deep`, so the adapter never needs its own flag.
12. Complete prompt listing is streaming. `iter_prompts` yields every human-authored prompt once, including duplicate and short prompts, in transcript order. Skip tool results, sidechains, injected/meta records, compaction summaries, and denormalized latest-prompt records. Return cleaned text without paging or caps; the CLI walks the iterator once, counting every prompt and retaining only the requested page.
13. Database-backed stores. If sessions are rows in an application SQLite database, open it read-only through a URI such as `file:/path/db.sqlite?mode=ro`, never copy it into the store, and never create a cache or journal file. There is no per-session file, so set `session_roots()` to `[]`, override `owns()` to accept the database path and its virtual `<db>#<session id>` form, and print that virtual path as the digest's `source:`. `show`/`prompts` accept it as a path. Implement `contains()` as a per-session row scan; the default file scan cannot work. Prefer the harness's own record semantics for prompts, and exclude subagent child rows from listing.
14. Deep search is per session. `contains()` must return true only when every token appears in that session's own content. The shared CLI filters archived sessions before calling it, so the adapter never needs its own archive check.

## Registration

In `core/fms_lib/registry.py`:

1. Import the adapter.
2. Add an instance to `READY`.
3. Remove the matching `PlannedHarness` entry from `PLANNED`.
4. Keep aliases unambiguous. If two products share a word, reserve the unqualified alias for the international or primary product and require a qualifier for the other.

`fms harnesses` is driven by these two tuples. No other registry edit is needed.

## Documentation

Add `references/<harness>.md` covering:

- Status, adapter file, harness name, aliases.
- Variants and whether they share a store.
- Exact directory layout and environment override.
- File format and record types.
- How prompts, tool results, sidechains, compaction, and todos are represented.
- What the digest extracts and what it ignores.
- How `iter_prompts` selects human prompts and what it excludes.
- Known gaps, format drift risks, and performance notes.
- A verification recipe against the synthetic fixture.

Update the support matrix in `SKILL.md` and both README files. Add a `CHANGELOG.md` entry.

## Fixtures and tests

Create `tests/fixtures/<harness>-home/` with a store-shaped tree. The fixture is the contract test for the adapter.

Fixture rules:

- Synthetic only. Use `/Users/example/...` paths, invented session ids, and invented prompts. Never copy a real transcript, even partially.
- Cover every supported variant to the extent the format differs.
- Include a normal session, a session with missing optional records, and any special case the adapter handles (compaction, sidechains, tool results, nested todos).
- Keep files small. Do not include binary attachments.
- If archive state lives in a binary application database, generate a synthetic database in `setUpClass` instead of committing one. Add a fixture-home override and a separate database-path override so tests cannot read a developer's live database.
- If the session store itself is a binary database, generate it at runtime too. `tests/zcode_fixture.py` builds a complete synthetic `db.sqlite` and tasks index; use `PRAGMA journal_mode=DELETE` so tests cannot leave WAL or SHM files behind.
- Add tests that scan the fixture for real user names, real project paths, and real session ids.

Add tests to `tests/test_cli.py` or a new `tests/test_<harness>.py`:

- Listing and aliases.
- Keyword, cwd, since, limit, and deep search.
- Deep search is scoped to one session: a token that exists only in another session must not match, and a database harness must not scan the whole database.
- Virtual source paths for database-backed stores resolve in `show` and `prompts`.
- Archive filtering when the harness supports it: default exclusion, `--include-archived`, deleted rows, and explicit `show` of an archived session.
- Latest ordering.
- Markdown and JSON show output.
- `prompts` count, oldest and newest paging, offset past the end, character caps, JSON fields, and exclusion of tool results, sidechains, meta records, and compaction.
- Missing and ambiguous refs.
- `doctor --harness <name>` candidate/readable/skipped counts and sanitized failure categories; `search --verbose` warns without polluting stdout.
- `doctor --fingerprint` works over the same candidates with no adapter work: fixture transcripts keep producing content-free shape summaries (no values, ids, or paths in the fingerprint).
- Optional `usage_summary(summary)`: return the recorded token/cost totals for one session as a flat dict (`tokens_input`, `tokens_output`, `tokens_cache_read`, `cost`), or inherit the `None` default so `fms stats` reports the harness as unrecorded. Only return numbers the store itself carries.
- Optional `resume_argv(summary)`: return the verified argv that reopens a session in the harness's own CLI (Claude Code, Codex, Pi, OMP, Cursor, Cline, OpenCode, Qwen, Kimi Code, and ZCode today), or inherit the `None` default so `fms resume` falls back to the handoff digest. Only implement it for commands verified against the real app.
- Read-only snapshot: file bytes and mtimes are unchanged after commands.
- Fixture validity and privacy markers.

Set the adapter's `FMS_<NAME>_HOME` override to a temporary copy of the fixture. Never run tests against a developer's live store.

## Quality gate

Before opening a pull request:

```bash
python3 -m compileall -q core fms_ui skills/find-my-session/scripts tools tests
python3 -m unittest discover -s tests -v
python3 tools/build_artifacts.py
```

Then verify manually with `--harness`, `--cwd`, `--since`, `--deep`, markdown, JSON, `doctor`, and `prompts --count` plus one paged listing. Confirm that the digest is useful for handoff without opening the transcript, and that prompt listing returns only human-authored prompts.

A harness is ready only when all of the following are true:

- Every advertised variant is covered or explicitly marked unsupported.
- Session listing works on a store with at least one very large transcript.
- `show` completes without loading the whole file into memory.
- `prompts` counts and pages without retaining the whole transcript, and excludes non-human records.
- Todos, edited files, and recent tools are either extracted or documented as unavailable.
- The reference document matches the fixture and the code.
- Tests pass on the CI matrix.
