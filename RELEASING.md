# Releasing

Releases are tag-driven. Pushing a `v*` tag runs
`.github/workflows/release.yml`, which tests the code, rebuilds the tracked
frontend, builds both standalone artifacts and the Python distributions,
checksums every asset, attests build provenance, creates the GitHub Release,
and publishes the wheel and sdist to PyPI with Trusted Publishing.

Do not create or push a tag without explicit maintainer approval.

## One-time PyPI setup

The first release needs a trusted publisher on PyPI. No API token or repository
secret is stored.

1. Sign in to PyPI and open **Publishing** → **Add a pending publisher**.
2. Fill in:
   - PyPI project name: `find-my-session`
   - Owner: `SomeNoneAI`
   - Repository: `find-my-session`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. In the GitHub repository, create an environment named `pypi`
   (**Settings** → **Environments**). Requiring reviewers is recommended so a
   tag build pauses before it uploads.
4. Confirm the project name is still available. The publish job fails if an
   existing PyPI project uses the name.

The pending publisher becomes a normal trusted publisher after the first
successful upload. If the workflow filename, repository, or environment name
changes later, update the publisher on PyPI before tagging.

## Version bump

`core/fms_lib/__init__.py` is the single version source. `pyproject.toml` reads
it dynamically, and the release workflow refuses a tag that does not match it.

1. Update `__version__` in `core/fms_lib/__init__.py`.
2. Move the changelog entries from `[Unreleased]` into a dated release section.
3. Update `docs/compatibility.md`, both READMEs, and `SKILL.md` if behavior or
   verification status changed.
4. Rebuild `fms_ui/static/` if the frontend changed
   (`cd fms_ui/frontend && npm ci && npm run typecheck && npm test && npm run build`).
5. Run the checks in `AGENTS.md`.
6. Commit, then create and push the tag:

   ```bash
   git tag -a v0.2.0 -m "v0.2.0"
   git push origin v0.2.0
   ```

## What the workflow publishes

- GitHub Release assets: `find-my-session-skill.zip`,
  `find-my-session-ui.zip`, the wheel, the sdist, and `SHA256SUMS.txt`.
  Re-running a tag build refreshes existing assets with `--clobber`.
- PyPI: the wheel and sdist, uploaded with `pypa/gh-action-pypi-publish`
  through OIDC. `skip-existing` makes a re-run safe when the version was
  already published.
- Build provenance attestations for every release asset.

After the first successful upload, users can install with:

```bash
pipx install find-my-session
uvx --from find-my-session fms latest
```

## Post-release checks

- `pipx install find-my-session` and `uvx --from find-my-session fms --version`
  resolve the new version.
- The PyPI page lists the wheel and sdist, and the README badges resolve. The
  PyPI badge reads "not found" until the first publish.
- The GitHub Release contains both ZIPs, both Python distributions, and
  `SHA256SUMS.txt`; the provenance attestation is visible on each asset.
- `fms harnesses` still matches the README tables and
  `docs/compatibility.md`.

## Repository settings

These are one-time GitHub settings, not release steps:

- Upload `docs/assets/social-preview.png` under **Settings** → **General** →
  **Social preview**.
- Protect `main`: require the CI jobs (tests, Ruff, Mypy, frontend, packaging)
  and a review before merge.
- Confirm `.github/CODEOWNERS` lists the maintainers with write access.
- Enable Discussions if store-format reports and harness requests need a
  public home; see [ROADMAP.md](ROADMAP.md).

## Recovering a failed release

- Failure before the release is created: fix the problem, then re-run the
  workflow. Delete and re-push the tag only if the tag itself is wrong.
- Failure in `publish-pypi` after the GitHub Release exists: open the failed
  run and choose **Re-run failed jobs**. The wheel and sdist artifact is kept
  for the run, and `skip-existing` tolerates a partially completed upload.
- A PyPI version can never be replaced, only yanked. Bump the version instead
  of trying to overwrite it.
