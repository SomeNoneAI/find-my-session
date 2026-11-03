# AGENTS.md

find-my-session is a read-only, cross-harness agent-session finder and handoff tool, shipped as an agent skill and a local browser panel.

## Layout

- `core/fms_lib/` — shared CLI, query service, diagnostics, models, rendering, and harness adapters.
- `skills/find-my-session/` — skill-specific entrypoint and docs: `SKILL.md`, `scripts/fms`, `references/`.
- `fms_ui/` — standalone local UI server, `fms-ui` entrypoint, packaged usage guide, and language-neutral static frontend.
- `fms_ui/frontend/` — Vue 3 + TypeScript + Vite source for the static frontend; `npm run build` emits the tracked build products into `fms_ui/static/` (`index.html`, `app.js`, `styles.css`, plus `theme-init.js` and `favicon.svg` from `public/`). Node.js is a development-only dependency; the runtime server stays standard-library Python.
- `tools/build_artifacts.py` — builds self-contained skill and UI directories, ZIPs, and checksums.
- `pyproject.toml` — pip/pipx packaging for the `fms` and `fms-ui` commands.
- `docs/compatibility.md` — single detailed compatibility and live-verification matrix.
- `tests/` — standard-library unittest suite and synthetic fixtures; adapter tests are split by harness.
- `.agents/skills/add-harness/` — project skill for adding harness support.
- `.github/workflows/release.yml` — validates `v*` tags and publishes both ZIPs and checksums.

## Invariants

- Python 3.9+. Standard library only.
- Read-only. Never write to session stores, app databases, or caches inside them.
- Fixtures must be synthetic. Never commit real transcripts, paths, emails, tokens, or other session data.
- Keep harness-specific knowledge in adapters; the shared CLI, service, and UI stay format-neutral.
- `SessionSummary.archived` is the cross-harness archive flag. Search excludes archived sessions unless `--include-archived` is passed.
- Every adapter implements `iter_prompts` for `fms prompts`, yielding only human-authored prompts. The shared service owns counting, paging, and ordering; each frontend owns presentation limits.

## Workflow

- Adding or splitting a harness: follow `.agents/skills/add-harness/SKILL.md`.
- Only implement a harness when asked. `fms harnesses` reflects `registry.py`.
- Keep `SKILL.md`, `references/`, both READMEs, `docs/compatibility.md`, and `CHANGELOG.md` consistent with behavior and verification changes.
- When adding a CLI capability, update the capability checklist in `.agents/skills/add-harness/SKILL.md` and the adapter contract in `references/extending.md`.
- Keep `core/fms_lib/__init__.py`, `pyproject.toml`, and the current changelog release on the same version. A `v*` tag triggers the release workflow; do not create it without explicit approval.
- Run before finishing:

  ```bash
  python3 -m compileall -q core fms_ui skills/find-my-session/scripts tools tests
  python3 -m unittest discover -s tests
  python3 tools/build_artifacts.py
  ```

- After any `fms_ui/frontend/` change, also rebuild the tracked static output and keep it in the same commit:

  ```bash
  cd fms_ui/frontend && npm ci && npm run typecheck && npm test && npm run build
  ```

  The Python checks above never require Node.js.

- Do not commit or push unless the user explicitly asks.
