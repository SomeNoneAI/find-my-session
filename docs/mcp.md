# MCP server

`fms mcp` runs a [Model Context Protocol](https://modelcontextprotocol.io/)
server on stdio, exposing the read-only fms surface as tools. Any
MCP-native host — Claude Desktop, IDE extensions, agent frameworks — can
then search, inspect, and hand off coding-agent sessions without shelling
out or leaving its protocol.

The server implements the MCP stdio transport: one JSON-RPC 2.0 message
per line on stdin/stdout. Schema revisions `2025-06-18` and `2024-11-05`
are supported; a client proposing another revision is answered with the
newest one this build speaks.

## Host configuration

Claude Desktop (and other hosts with the same shape):

```json
{
  "mcpServers": {
    "find-my-session": {
      "command": "fms",
      "args": ["mcp"]
    }
  }
}
```

Any harness `FMS_<NAME>_HOME` overrides already in the host's environment
apply as usual. The server is strictly read-only and makes no network
requests.

## Tools

| Tool | Maps to | Notes |
| --- | --- | --- |
| `harnesses` | `fms harnesses` | Ready and planned harnesses with stores and aliases. |
| `search_sessions` | `fms search` | Fuzzy keywords plus cwd/since/harness filters; metadata only. |
| `latest_session` | `fms latest` | Newest matching session summary. |
| `show_session` | `fms show` | The low-token handoff digest as JSON. |
| `session_prompts` | `fms prompts` | Human prompts with count and paging. |
| `usage_stats` | `fms stats` | Recorded token/cost totals per harness. |
| `doctor` | `fms doctor` | Store health, optionally with the `--fingerprint` shape summary. |

There is no write tool and no resume tool: reopening a session launches an
interactive app, which does not belong inside a tool call. Hosts that want
it can surface the `fms resume <ref>` command themselves.

## Errors

Tool failures (unknown ref, unreadable store) come back as tool results
with `isError: true` and a sanitized message — the same text the CLI
prints — so a host can show them to the user without a stack trace.
Protocol-level failures (unknown method, bad arguments to the protocol
itself) are JSON-RPC errors per the spec.

## Testing

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | fms mcp
```
`tests/test_mcp.py` for the full in-process suite.

To list this server in the MCP Registry, see
[docs/mcp-publishing.md](mcp-publishing.md).
