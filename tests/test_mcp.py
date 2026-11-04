"""Tests for the MCP server (``fms mcp``).

The server speaks newline-delimited JSON-RPC 2.0 on stdio and exposes the
read-only fms surface as MCP tools. Tests exercise the protocol handler
in-process (initialize handshake, tools/list, tools/call against the
synthetic fixtures, error paths) plus one end-to-end stdio round trip.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from unittest import mock

from cli_support import FMS, FixtureTestCase  # noqa: E402


class McpProtocolTests(FixtureTestCase):
    def handle(self, message: dict) -> dict:
        from fms_lib import mcp

        env = {
            "FMS_OPENCODE_HOME": str(self.opencode_home),
            "FMS_QWEN_HOME": str(self.qwen_home),
            "FMS_QODER_CN_HOME": str(self.home),
        }
        with mock.patch.dict(os.environ, env):
            response = mcp.handle_message(message)
        assert response is not None
        return response

    def test_initialize_negotiates_supported_version(self) -> None:
        response = self.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            }
        )
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(response["result"]["serverInfo"]["name"], "find-my-session")

    def test_initialize_falls_back_to_latest_for_unknown_version(self) -> None:
        response = self.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": {"protocolVersion": "1999-01-01"},
            }
        )
        self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")

    def test_tools_list_exposes_readonly_surface(self) -> None:
        response = self.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(
            names,
            [
                "harnesses",
                "search_sessions",
                "latest_session",
                "show_session",
                "session_prompts",
                "usage_stats",
                "doctor",
            ],
        )
        for tool in response["result"]["tools"]:
            self.assertEqual(tool["inputSchema"]["type"], "object")

    def test_notifications_get_no_response(self) -> None:
        from fms_lib import mcp

        self.assertIsNone(
            mcp.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )

    def test_unknown_method_returns_method_not_found(self) -> None:
        response = self.handle(
            {"jsonrpc": "2.0", "id": 4, "method": "resources/list"}
        )
        self.assertEqual(response["error"]["code"], -32601)

    def test_unknown_tool_returns_invalid_params(self) -> None:
        response = self.handle(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "nope", "arguments": {}},
            }
        )
        self.assertEqual(response["error"]["code"], -32602)

    def test_harnesses_tool(self) -> None:
        response = self.handle(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "harnesses", "arguments": {}},
            }
        )
        rows = json.loads(response["result"]["content"][0]["text"])
        names = {row["name"] for row in rows}
        self.assertIn("opencode", names)
        self.assertIn("gemini-cli", names)
        self.assertIn("qwen", names)

    def test_search_session_tool_respects_fixture_harness(self) -> None:
        response = self.handle(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "search_sessions",
                    "arguments": {"harness": "opencode", "limit": 1},
                },
            }
        )
        sessions = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["harness"], "opencode")

    def test_show_session_tool(self) -> None:
        session = self.run_json("latest", "--harness", "qwen")[0]
        response = self.handle(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "show_session",
                    "arguments": {"ref": session["ref"], "messages": 1},
                },
            }
        )
        detail = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(detail["harness"], "qwen")
        self.assertIn("turn_count", detail)

    def test_session_prompts_tool(self) -> None:
        session = self.run_json("latest", "--harness", "qwen")[0]
        response = self.handle(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {
                    "name": "session_prompts",
                    "arguments": {"ref": session["ref"]},
                },
            }
        )
        listing = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(listing["total"], 1)

    def test_usage_stats_tool(self) -> None:
        response = self.handle(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "usage_stats",
                    "arguments": {"harness": "opencode"},
                },
            }
        )
        rows = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(rows[0]["harness"], "opencode")
        self.assertEqual(rows[0]["sessions_with_usage"], 2)

    def test_user_error_becomes_tool_error_result(self) -> None:
        response = self.handle(
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "show_session",
                    "arguments": {"ref": "qwen:zzzz"},
                },
            }
        )
        self.assertTrue(response["result"]["isError"])
        self.assertIn("no session matched", response["result"]["content"][0]["text"])

    def test_parse_error_line(self) -> None:
        from fms_lib import mcp

        out = io.StringIO()
        mcp.serve(io.StringIO("{not json\n"), out)
        response = json.loads(out.getvalue())
        self.assertEqual(response["error"]["code"], -32700)


class McpStdioRoundTripTests(FixtureTestCase):
    def test_stdio_round_trip(self) -> None:
        import os

        env = dict(os.environ)
        env.update(
            {
                "FMS_OPENCODE_HOME": str(self.opencode_home),
                "FMS_QWEN_HOME": str(self.qwen_home),
                "FMS_QODER_CN_HOME": str(self.home),
            }
        )
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "ping"},
        ]
        stdin_payload = "\n".join(json.dumps(m) for m in messages) + "\n"
        result = subprocess.run(
            [sys.executable, str(FMS), "mcp"],
            input=stdin_payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        # Three responses: the notification must produce none.
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0]["result"]["serverInfo"]["name"], "find-my-session")
        self.assertEqual(len(lines[1]["result"]["tools"]), 7)
        self.assertEqual(lines[2]["result"], {})
