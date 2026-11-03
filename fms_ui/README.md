# Find My Session UI

A local, read-only browser panel for finding and handing off AI coding sessions.
The UI is the human-facing release; the separate skill release is for agents.

## Requirements

- Python 3.9 or newer
- macOS or Linux; Windows is exercised by a non-blocking CI job but is not supported
- No third-party Python packages and no Node.js at runtime
- Node.js 22+ only if you want to rebuild the frontend from `fms_ui/frontend/` sources
- Python 3.14+ or the `zstd` command for compressed Codex and DeepSeek stores

## Run

From this extracted directory:

```bash
python3 fms-ui
```

The panel opens at `http://127.0.0.1:8765`. To choose another port without
opening a browser:

```bash
python3 fms-ui --no-browser --port 8766
```

Stop the server with Ctrl+C. Check the release version with
`python3 fms-ui --version`. Standard unzip tools also preserve the launcher's
executable bit, so `./fms-ui` works; `python3 fms-ui` works with any extractor.

## Upgrade or remove

Upgrade by replacing this directory with the newer extracted release. Remove
the directory to uninstall. The UI does not install a background service.

## Privacy and safety

- The server listens only on `127.0.0.1` and uses same-origin local APIs.
- Session stores and application databases are opened read-only.
- Search results contain metadata; session details and prompts can contain
  sensitive conversation text and local paths.
- No session content is sent to the project maintainers.

## Snapshot cache and refresh

- The first request scans the session stores once and keeps an in-memory
  snapshot of session metadata (titles, paths, timestamps). The session list
  and the project directory picker share that snapshot, so loading, filtering,
  and paging do not rescan.
- Session details, user prompts, and full-text (deep) searches always read the
  stores live and are never cached. Nothing is written to the stores or disk.
- The "Rescan" button asks for a background rebuild and keeps showing the
  current list while it runs; the panel updates when the new snapshot lands.
  A long-running panel also refreshes the snapshot periodically.
- Restarting the server drops the cache.

For supported harnesses, diagnostics, and source code, see
https://github.com/SomeNoneAI/find-my-session .
