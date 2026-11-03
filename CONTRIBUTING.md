# Contributing

Thanks for helping make session handoff work across more harnesses.

## Ground rules

- Keep the tool read-only. It must never modify, move, or delete a session.
- Keep the runtime dependency-free. Use the Python standard library.
- Do not commit real session data, usernames, tokens, repository paths, or
  conversation excerpts. Fixtures must be synthetic or thoroughly redacted.
- Prefer compact output. Token efficiency is a product requirement, not a
  cosmetic detail.
- One adapter should not change the behavior of another adapter.

## Development setup

Requirements: Python 3.9 or newer. The Python runtime and test suite need no
third-party packages; CI installs coverage tooling only for the optional
report. Tests use isolated fixture homes and environment overrides; they never
read the developer's real sessions.

The browser panel frontend lives in `ui/frontend/` (Vue 3 + TypeScript +
Vite). Node.js is needed only for frontend development — building the tracked
static output in `ui/static/`, type-checking, and running the Vitest suite:

```bash
cd ui/frontend
npm ci
npm run typecheck
npm test
npm run build   # rewrites ../static (index.html, app.js, styles.css, ...)
```

Commit the rebuilt `ui/static/` together with the source change so the Python
server and release artifacts stay runnable without Node.js.

```bash
git clone https://github.com/SomeNoneAI/find-my-session.git
cd find-my-session
python3 -m unittest discover -s tests -v
python3 -m compileall -q core ui skills/find-my-session/scripts tools tests
```

## Repository layout

- `core/fms_lib/` — shared CLI, query service, models, and harness adapters.
- `skills/find-my-session/` — skill entrypoint, `SKILL.md`, and adapter references.
- `ui/` — local browser panel server and the tracked static frontend build.
- `ui/frontend/` — Vue 3 + TypeScript + Vite source; `npm run build` emits into `ui/static/`.
- `tools/build_artifacts.py` — builds both release artifacts.
- `tests/` — standard-library unittest suite and synthetic fixtures.

## Building the artifacts

The project ships two artifacts from one core:

```bash
python3 tools/build_artifacts.py
```

This produces `dist/find-my-session-skill/` and `dist/find-my-session-ui/`
(with matching `.zip` files) — the agent skill and the human UI panel,
respectively.

## Adding a harness

1. **Research the store.** Identify every relevant variant (desktop, CLI, IDE
   extension, international, regional), the exact paths on each platform, and
   the transcript schema. Record what you verified and what you inferred.
2. **Define the low-token surface.** Determine how to derive the first prompt,
   latest prompt, working directory, timestamps, compact summaries, todos,
   edited files, and the complete human-prompt stream without reading the whole
   transcript for every search.
3. **Implement the adapter.** Add a module under
   `core/fms_lib/harnesses/` and register it in
   `registry.py`. Follow the contract in
   `skills/find-my-session/references/extending.md`.
4. **Write the reference document.** Add
   `skills/find-my-session/references/<harness>.md` with verified paths,
   variants, schema notes, field-selection rules, caveats, and privacy notes.
5. **Add fixtures and tests.** Use synthetic transcripts. Cover search, latest,
   show, prompt listing with count and paging, JSON output, missing stores, and
   malformed records.
6. **Update the matrix.** Change the status in `fms harnesses` and both
   `README` files, and record verified versions, surfaces, and dates in
   `docs/compatibility.md`.

A harness is not "ready" until its reference document, tests, and support
matrix all agree.

## Adapter quality bar

- Search must not require a full transcript read.
- `show` must cap every user-visible field and stay under a few thousand tokens
  by default.
- `prompts` must stream the transcript, return only human-authored inputs, and
  retain only the requested page. Count and paging belong in the shared service,
  not in the adapter.
- Missing roots, unreadable files, truncated JSON lines, and partially written
  sessions must degrade gracefully.
- The adapter must never execute commands or interpret tool-call content.
- Environment overrides must exist for tests and nonstandard installs, and must
  be documented in the adapter reference.

## Verifying against real stores

Synthetic fixtures keep CI fast and private, but they do not prove a real app
still writes the same schema. When you check an adapter against a live store:

- Use a consent-first flow: report what you will read, read only what the
  adapter reads, and never commit transcripts, paths, usernames, or tokens.
  Follow `skills/find-my-session/references/contribution.md`.
- Record the harness version, surfaces (desktop/CLI/IDE), operating system,
  and date in the adapter's reference document, and update the matching row of
  `docs/compatibility.md`, including anything you could not verify.

## Pull requests

- Keep changes focused.
- Include tests for new behavior and bug fixes.
- Run the full test suite before opening a pull request.
- Describe the harness version and platform you tested against.
- Sanitize all command output and screenshots. Remove tokens, usernames, private
  repository paths, and conversation content.
- Update the changelog for user-visible changes.
- If your change alters what is verified or planned, update
  `docs/compatibility.md` and both README tables in the same PR.

## Commit messages

Use short, imperative messages. Conventional Commits prefixes such as `feat:`,
`fix:`, `docs:`, and `test:` are welcome but not required.

## Licensing

By contributing, you agree that your contribution is licensed under the MIT
License in this repository.
