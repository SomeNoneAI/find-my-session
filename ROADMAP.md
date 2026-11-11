# Roadmap

Public direction for find-my-session. No dates are promised; order is roughly priority.

## Near term: release and distribution

- **PyPI.** Shipped with the first tagged release: the release workflow builds the wheel and sdist and publishes them through Trusted Publishing, so `pipx install find-my-session` and `uvx --from find-my-session fms` work.
- **Releases.** Shipped: automated GitHub Releases publish both ZIPs (`find-my-session-skill.zip`, `find-my-session-ui.zip`), the Python distributions, and a `SHA256SUMS.txt`, with build provenance attestations.
- **Diagnostics.** `fms doctor [--harness] [--json]` checks decoder availability, readable stores, and per-harness health; `--verbose` on `search`/`latest` reports skipped sessions, so a broken or drifted store is obvious before it wastes a handoff.
- **JSON contract.** Keep `--json` additive before 1.0 and document every field in [docs/json-output.md](docs/json-output.md).
- **Supply-chain checks.** CodeQL analyzes Python on every change; the OpenSSF Scorecard evaluation and adoption plan is documented in [docs/scorecard.md](docs/scorecard.md). Ongoing: keep the release workflow's tag-only publishing gate and pinned, checksum-verified publisher tooling intact.

## Python support

- 0.1.x supports Python 3.9–3.14. Python 3.9 is end-of-life upstream; 0.2 is planned to require 3.10+ once CI capacity for 3.9 becomes a burden. Any change will be called out in the changelog and both READMEs.
- Python 3.14 provides native zstd support; older interpreters can use the `zstd` CLI for compressed stores.

## Ongoing: schema compatibility

- Keep adapters current as harness apps change their stores, guided by the [compatibility matrix](docs/compatibility.md).
- Recruit real-environment checks: most "Verified" rows reflect one machine on one day. Volunteers who confirm a harness against their own current app version — and report back via the drift flow in [references/contribution.md](skills/find-my-session/references/contribution.md) — keep the matrix honest.

## Performance

- Large transcripts: keep search metadata-only with bounded memory, and keep `--deep` and prompt listing streaming, so multi-hundred-megabyte sessions stay usable. Profile against big real stores before adding cleverness.

## Windows policy

- Windows runs in an **experimental, non-blocking** CI job with synthetic fixtures, which is green as of 2026-11-04 (path fidelity, CRLF parsing, and platform-aware launcher tests fixed). Nothing is promised yet: there is no committed timeline for first-class Windows support.
- Community fixes and verification reports are welcome. First-class support needs a maintainer with a Windows environment running the documented verification path: [references/windows-verification.md](skills/find-my-session/references/windows-verification.md).

## Community maintenance

- Reviews and adapters for planned harnesses ([compatibility matrix](docs/compatibility.md)) follow [CONTRIBUTING.md](CONTRIBUTING.md); new adapters land with a reference doc, synthetic fixtures, and matrix updates, or they do not land.
- Planned harnesses and larger features should be tracked as issues, with `good first issue` or `help wanted` where appropriate.
- GitHub Discussions can carry store-format change reports and harness requests once the volume justifies it.
- `.github/CODEOWNERS` routes reviews to the maintainer; branch protection should require CI and review before merge.
