"""Contract tests for the shared presentation defaults.

``fms_lib.limits`` is the single source of truth for the CLI and MCP
surfaces. These tests fail if a surface drifts back to a local literal or
advertises a different default in its help text.
"""

from __future__ import annotations

import inspect
import unittest

from cli_support import FixtureTestCase  # noqa: E402


class LimitContractTests(FixtureTestCase):
    def test_render_defaults_match_limits_module(self) -> None:
        from fms_lib import limits, render

        for func in (render.render_show_markdown, render.render_show_json):
            signature = inspect.signature(func)
            self.assertEqual(
                signature.parameters["messages"].default,
                limits.SHOW_MESSAGES_DEFAULT,
            )
            self.assertEqual(
                signature.parameters["chars"].default,
                limits.SHOW_CHARS_DEFAULT,
            )
            self.assertEqual(
                signature.parameters["summary_chars"].default,
                limits.SHOW_SUMMARY_CHARS_DEFAULT,
            )

    def test_cli_parser_defaults_match_limits_module(self) -> None:
        from fms_lib import cli, limits

        parser = cli.build_parser()
        actions = {
            action.dest: action
            for action in parser._subparsers._group_actions[0].choices[  # noqa: SLF001
                "show"
            ]._actions
        }
        self.assertEqual(actions["messages"].default, limits.SHOW_MESSAGES_DEFAULT)
        self.assertEqual(actions["chars"].default, limits.SHOW_CHARS_DEFAULT)
        self.assertEqual(
            actions["summary_chars"].default, limits.SHOW_SUMMARY_CHARS_DEFAULT
        )

        search_actions = {
            action.dest: action
            for action in parser._subparsers._group_actions[0].choices[  # noqa: SLF001
                "search"
            ]._actions
        }
        self.assertEqual(search_actions["limit"].default, limits.SEARCH_LIMIT_DEFAULT)
        latest_actions = {
            action.dest: action
            for action in parser._subparsers._group_actions[0].choices[  # noqa: SLF001
                "latest"
            ]._actions
        }
        self.assertEqual(latest_actions["limit"].default, limits.LATEST_LIMIT_DEFAULT)

    def test_mcp_show_session_honors_messages_and_chars(self) -> None:
        import json
        import os
        from unittest import mock

        from fms_lib import mcp

        env = {
            "FMS_OPENCODE_HOME": str(self.opencode_home),
            "FMS_QWEN_HOME": str(self.qwen_home),
            "FMS_QODER_CN_HOME": str(self.home),
        }
        with mock.patch.dict(os.environ, env):
            response = mcp.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "show_session",
                        "arguments": {
                            "ref": "qwen:aaaaaaaa",
                            "messages": 1,
                            "chars": 10,
                        },
                    },
                }
            )
        detail = json.loads(response["result"]["content"][0]["text"])
        self.assertLessEqual(len(detail["exchanges"]), 1)
        for exchange in detail["exchanges"]:
            self.assertLessEqual(len(exchange["user"]), 11)


if __name__ == "__main__":
    unittest.main()
