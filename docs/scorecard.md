# OpenSSF Scorecard evaluation

[OpenSSF Scorecard](https://securityscorecards.dev/) scores a repository on
automated supply-chain checks. This evaluation decides whether the project
should adopt the Scorecard GitHub Action, and which checks are actionable for
a small, standard-library-only project. It was written before the first
public scan, so it maps each check against the repository as it is; the first
Action run will attach real scores to the same list.

## Recommendation

Adopt, as a **weekly, non-blocking** job. Scorecard is read-only, needs no
build, and finishes in well under a minute; a weekly schedule plus a badge in
the README costs almost nothing. It stays out of the PR path (no overlap with
the CI matrix, Ruff, mypy, or CodeQL, which is analysis rather than a policy
score). Suggested workflow, using the repo's SHA-pinned action convention:

```yaml
name: Scorecard

on:
  schedule:
    - cron: "43 5 * * 1"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  analysis:
    name: Scorecard analysis
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
      id-token: write
    steps:
      - name: Check out
        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
        with:
          persist-credentials: false

      - name: Run analysis
        uses: ossf/scorecard-action@<pin-to-current-v2-release> # v2
        with:
          results_file: results.sarif
          results_format: sarif
          publish_results: true
```

`publish_results: true` requires the repo to allow the Scorecard app and
publishes the public score used by the badge. Until that is switched on, the
badge and API show no data.

## Check-by-check status

Actionable items are grouped at the end.

| Check | Status here | Notes |
| --- | --- | --- |
| Token-Permissions | Pass | Every workflow declares least-privilege `permissions`; the release job scopes `id-token`/`attestations` to the publish path. |
| Pinned-Dependencies | Pass | All actions are SHA-pinned; Dependabot keeps the pins current, and CI pins Ruff/mypy versions. |
| Dangerous-Workflow | Pass | No `pull_request_target` checkouts of untrusted heads; the release workflow runs on tags with repository code only. |
| Binary-Artifacts | Pass | No committed binaries; release artifacts are built in CI from source and attested. |
| CI-Tests | Pass | CI covers 3.9–3.14, macOS, a frontend job, packaging, and an experimental Windows job. |
| Dependency-Update-Tool | Pass | Dependabot covers Actions, Python dev deps, and the frontend. |
| Maintained | Pass (young repo) | Recent, regular commits; re-checked automatically each week once adopted. |
| License | Pass | MIT with a `LICENSE` file. |
| Vulnerabilities | Pass | No open OSV advisories; the runtime is standard-library only, so there is no runtime dependency surface. |
| SAST | Pass (with CodeQL) | `codeql.yml` adds taint/dataflow analysis on Python; deliberately not duplicating Ruff (style) or mypy (types). |
| Code-Review | Partial | Solo-maintainer project; PRs are reviewed by the maintainer. Full enforcement arrives with branch protection (below). |
| Packaging | Partial | GitHub Releases publish ZIPs, wheels, sdist, checksums, and provenance; PyPI publishing is the remaining gap (#10). |
| Signed-Releases | Partial | `SHA256SUMS.txt` plus build-provenance attestations today; Scorecard's top marks want sigstore signatures, which PyPI Trusted Publishing provides on the package side. |
| Branch-Protection | **Missing — actionable** | Enable branch protection on `main`: require the CI checks and (when practical) review before merge. Owner action in repo settings. |
| Security-Policy | Pass | `SECURITY.md` at the root documents private advisory reporting, scope, and safe operation; private vulnerability reporting is enabled on the repository. |
| CII-Best-Practices | Optional | Registering for the CII badge is cheap and shows up as a Scorecard gain once in progress. |
| Fuzzing | Not applicable | No parser hot path that justifies a fuzzer for a stdlib CLI; revisit if a format becomes adversarial. |
| Webhooks / User-Updates | Not applicable | No webhooks or user content. |

## Actionable now

1. Enable branch protection on `main` (require CI, block force pushes).
2. If the score matters to you, add the Scorecard workflow above and the
   README badge; otherwise this document stands as the evaluation the issue
   asked for.

Updated after 0.1.1: the PyPI release landed via Trusted Publishing,
completing the Packaging check, and the Scorecard evaluation confirmed
`SECURITY.md` was already in place.
