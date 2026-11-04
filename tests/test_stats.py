"""Tests for ``fms stats``.

Only the OpenCode adapter has a verified usage source (cost and token
columns on the session row), so the fixtures exercise both the recorded
totals and the "not recorded" fallback for every other harness. All
identifiers and numbers are synthetic.
"""

from __future__ import annotations

import json

from cli_support import FixtureTestCase  # noqa: E402


class StatsTests(FixtureTestCase):
    def test_opencode_aggregates_recorded_usage(self) -> None:
        code, out, err = self.run_cli(
            "stats", "--harness", "opencode", "--json"
        )
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["harness"], "opencode")
        # Archived sessions are excluded by default.
        self.assertEqual(row["sessions"], 4)
        # MAIN and the session-v2-only session carry usage columns.
        self.assertEqual(row["sessions_with_usage"], 2)
        self.assertEqual(row["tokens_input"], 1800)
        self.assertEqual(row["tokens_output"], 950)
        self.assertEqual(row["tokens_cache_read"], 200)
        self.assertAlmostEqual(row["cost_usd"], 0.5)

    def test_claude_aggregates_transcript_usage(self) -> None:
        code, out, err = self.run_cli(
            "stats", "--harness", "claude-code", "--json"
        )
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        row = rows[0]
        self.assertEqual(row["harness"], "claude-code")
        self.assertEqual(row["sessions_with_usage"], 1)
        self.assertEqual(row["tokens_input"], 2100)
        self.assertEqual(row["tokens_output"], 450)
        self.assertEqual(row["tokens_cache_read"], 500)
        # Claude Code does not record cost.
        self.assertIsNone(row["cost_usd"])

    def test_qwen_aggregates_transcript_usage(self) -> None:
        code, out, err = self.run_cli("stats", "--harness", "qwen", "--json")
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        row = rows[0]
        self.assertEqual(row["harness"], "qwen")
        self.assertEqual(row["sessions_with_usage"], 1)
        self.assertEqual(row["tokens_input"], 1500)
        self.assertEqual(row["tokens_output"], 800)
        self.assertEqual(row["tokens_cache_read"], 200)
        self.assertIsNone(row["cost_usd"])

    def test_text_render_marks_unrecorded_harnesses(self) -> None:
        code, out, err = self.run_cli(
            "stats", "--harness", "opencode", "--harness", "kimi-code"
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()
        self.assertEqual(lines[0].split("\t")[0], "harness")
        by_harness = {line.split("\t")[0]: line for line in lines[1:]}
        self.assertIn("1800", by_harness["opencode"])
        self.assertIn("0.5000", by_harness["opencode"])
        self.assertEqual(by_harness["kimi-code"].split("\t")[-3:], ["-", "-", "-"])

    def test_filters_apply(self) -> None:
        code, out, err = self.run_cli(
            "stats",
            "--harness",
            "opencode",
            "--cwd",
            "/Users/example/project-alpha",
            "--json",
        )
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        self.assertEqual(rows[0]["sessions"], 2)
        self.assertEqual(rows[0]["sessions_with_usage"], 2)

        code, out, err = self.run_cli(
            "stats",
            "--harness",
            "opencode",
            "--cwd",
            "/Users/example/project-gamma",
            "--json",
        )
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        self.assertEqual(rows[0]["sessions"], 2)
        self.assertEqual(rows[0]["sessions_with_usage"], 0)

        code, out, err = self.run_cli(
            "stats", "--harness", "opencode", "--since", "2026-10-21", "--json"
        )
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        self.assertEqual(rows[0]["sessions"], 3)
        self.assertEqual(rows[0]["sessions_with_usage"], 1)

    def test_archived_sessions_excluded_by_default(self) -> None:
        # The archived fixture session carries no usage, so the totals are
        # identical either way; the session count is not.
        code, out, err = self.run_cli("stats", "--harness", "opencode", "--json")
        self.assertEqual(code, 0, err)
        default_rows = json.loads(out)
        code, out, err = self.run_cli(
            "stats", "--harness", "opencode", "--include-archived", "--json"
        )
        self.assertEqual(code, 0, err)
        included_rows = json.loads(out)
        self.assertEqual(default_rows[0]["sessions"], 4)
        self.assertEqual(included_rows[0]["sessions"], 5)
        self.assertEqual(
            default_rows[0]["sessions_with_usage"],
            included_rows[0]["sessions_with_usage"],
        )

    def test_unknown_harness_errors(self) -> None:
        code, out, err = self.run_cli("stats", "--harness", "nope")
        self.assertEqual(code, 2, err)
        self.assertIn("unknown harness", err)
