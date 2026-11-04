# Publishing to the MCP Registry

The registry hosts metadata only; the artifact stays on PyPI.
`server.json` at the repo root is the single source of that metadata.

## Prerequisites

- The version in `server.json` matches the release tag and
  `core/fms_lib/__init__.py` (see `RELEASING.md`; registry versions are
  immutable — a fix means a new version).
- PyPI release for that version is live (`pipx install` / `uvx` resolves
  it), and the PyPI description contains
  `mcp-name: io.github.SomeNoneAI/find-my-session` (in `README.md`).
- `mcp-publisher` installed (`brew install mcp-publisher` or the
  [release binary](https://github.com/modelcontextprotocol/registry/releases)).

## Publish a release

```bash
# 1. Sanity-check the manifest against the release
python3 -c "import json; d=json.load(open('server.json')); print(d['name'], d['version'])"
pipx install "find-my-session==$(python3 -c "import json; print(json.load(open('server.json'))['version'])")"

# 2. Log in (GitHub device flow; namespace io.github.SomeNoneAI requires it)
mcp-publisher login github

# 3. Publish
mcp-publisher publish

# 4. Verify
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.SomeNoneAI/find-my-session"
```

## After bumping the version

1. Update `version` in `server.json` (both top-level and the package
   entry) to the new release.
2. Re-run the steps above — the registry keeps every version; old ones
   stay listed.

## Client configuration

Registry clients run the PyPI package without installing it:

```json
{
  "mcpServers": {
    "find-my-session": {
      "command": "uvx",
      "args": ["--from", "find-my-session", "fms", "mcp"]
    }
  }
}
```

Local checkouts keep using `"command": "fms", "args": ["mcp"]`
(see `docs/mcp.md`).
