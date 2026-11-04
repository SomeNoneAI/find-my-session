"""Tests for ``fms resume``.

The resume command prints (or with --exec, runs) the harness command
that reopens a session. Verified mappings exist for Claude Code, Codex,
Pi, OMP, Cursor, Cline, OpenCode, Qwen, Kimi, and ZCode; harnesses
without a verified command fall back to the handoff hint. The --exec
path is exercised against a stubbed subprocess so no test ever launches
a real harness, and every ref is resolved from the synthetic fixtures —
never from a live store.
"""

from __future__ import annotations

import json
from unittest import mock

from cli_support import FixtureTestCase  # noqa: E402


class ResumeTests(FixtureTestCase):
    def _newest_session(self, harness: str) -> dict:
        sessions = self.run_json("latest", "--harness", harness)
        self.assertEqual(len(sessions), 1, sessions)
        return sessions[0]

    def test_claude_resume_command(self) -> None:
        session = self._newest_session("claude-code")
        code, out, err = self.run_cli("resume", session["ref"])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "claude --resume %s" % session["session_id"])

    def test_codex_resume_command(self) -> None:
        session = self._newest_session("codex")
        code, out, err = self.run_cli("resume", session["ref"])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "codex resume %s" % session["session_id"])

    def test_new_resume_commands(self) -> None:
        expected = {
            "cursor": ["cursor-agent", "--resume"],
            "cline": ["cline", "--id"],
            "qwen": ["qwen", "--resume"],
            "kimi-code": ["kimi", "--session"],
        }
        for harness, prefix in expected.items():
            with self.subTest(harness=harness):
                session = self._newest_session(harness)
                code, out, err = self.run_cli("resume", session["ref"])
                self.assertEqual(code, 0, err)
                self.assertEqual(
                    out.strip(),
                    "%s %s" % (" ".join(prefix), session["session_id"]),
                )

    def test_opencode_resume_uses_raw_session_id(self) -> None:
        session = self._newest_session("opencode")
        code, out, err = self.run_cli("resume", session["ref"])
        self.assertEqual(code, 0, err)
        raw_id = session["path"].split("#", 1)[1]
        self.assertEqual(out.strip(), "opencode --session %s" % raw_id)

    def test_zcode_resume_uses_raw_session_id(self) -> None:
        session = self._newest_session("zcode")
        code, out, err = self.run_cli("resume", session["ref"])
        self.assertEqual(code, 0, err)
        raw_id = session["path"].split("#", 1)[1]
        self.assertEqual(out.strip(), "zcode --resume %s" % raw_id)

    def test_json_output(self) -> None:
        session = self._newest_session("claude-code")
        code, out, err = self.run_cli("resume", session["ref"], "--json")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["ref"], session["ref"])
        self.assertEqual(payload["harness"], "claude-code")
        self.assertEqual(
            payload["resume_argv"],
            ["claude", "--resume", session["session_id"]],
        )
        self.assertFalse(payload["executed"])

    def test_harness_without_known_resume_command(self) -> None:
        session = self._newest_session("workbuddy")
        code, out, err = self.run_cli("resume", session["ref"])
        self.assertEqual(code, 0, err)
        self.assertIn(
            "no verified resume command for harness 'workbuddy'", out
        )
        self.assertIn("fms show %s" % session["ref"], out)

        payload = self.run_json("resume", session["ref"])
        self.assertIsNone(payload["resume_argv"])
        self.assertFalse(payload["executed"])

    def test_exec_runs_the_command(self) -> None:
        session = self._newest_session("claude-code")
        completed = mock.Mock(returncode=7)
        with mock.patch(
            "fms_lib.cli.subprocess.run", return_value=completed
        ) as run_mock:
            code, out, err = self.run_cli("resume", session["ref"], "--exec")
        self.assertEqual(code, 7)
        self.assertIn("claude --resume", out)
        self.assertIn("fms: launching", err)
        run_mock.assert_called_once_with(
            ["claude", "--resume", session["session_id"]]
        )

    def test_exec_json_reports_execution(self) -> None:
        session = self._newest_session("claude-code")
        completed = mock.Mock(returncode=0)
        with mock.patch("fms_lib.cli.subprocess.run", return_value=completed):
            payload = self.run_json("resume", session["ref"], "--exec")
        self.assertTrue(payload["executed"])

    def test_missing_ref_errors_cleanly(self) -> None:
        code, out, err = self.run_cli("resume", "claude-code:zzzz")
        self.assertEqual(code, 2, err)
        self.assertIn("no session matched", err)
