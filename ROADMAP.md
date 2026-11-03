# Roadmap

Public direction for find-my-session. No dates are promised; order is roughly priority.

## Near term: release and diagnostics

- **Packaging and releases.** pip/pipx install from the Git repository (`pipx install git+https://github.com/SomeNoneAI/find-my-session.git`), exposing `fms` and `fms-ui`, plus automated GitHub Releases that publish both ZIPs (`find-my-session-skill.zip`, `find-my-session-ui.zip`) with a `SHA256SUMS.txt`.
- **Diagnostics.** `fms doctor [--harness] [--json]` to check decoder availability, readable stores, and per-harness health, and a `--verbose` mode for `search`/`latest`, so a broken or drifted store is obvious before it wastes a handoff.

## Ongoing: schema compatibility

- Keep adapters current as harness apps change their stores, guided by the [compatibility matrix](docs/compatibility.md).
- Recruit real-environment checks: most "Verified" rows reflect one machine on one day. Volunteers who confirm a harness against their own current app version — and report back via the drift flow in [references/contribution.md](skills/find-my-session/references/contribution.md) — keep the matrix honest.

## Performance

- Large transcripts: keep search metadata-only with bounded memory, and keep `--deep` and prompt listing streaming, so multi-hundred-megabyte sessions stay usable. Profile against big real stores before adding cleverness.

## Windows policy

- Windows is **not tested** today and nothing is promised. Community-verified reports are welcome, but there is no committed timeline for first-class Windows support.

## Community maintenance

- Reviews and adapters for planned harnesses ([compatibility matrix](docs/compatibility.md)) follow [CONTRIBUTING.md](CONTRIBUTING.md); new adapters land with a reference doc, synthetic fixtures, and matrix updates, or they do not land.
