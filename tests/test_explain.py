from __future__ import annotations

import unittest

from cli_support import FixtureTestCase  # noqa: E402


class ExplainTests(FixtureTestCase):
    def test_explain_prints_breakdown_to_stderr(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "qcn", "dark", "--explain"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:b2c3d4e5", out)
        self.assertIn("qoder-cn:b2c3d4e5: score 60", err)
        self.assertIn("dark=title/last_prompt+60", err)

    def test_explain_marks_deep_only_matches(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "qcn", "--deep", "verifier-secret",
            "--explain",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:a1b2c3d4", out)
        self.assertIn("deep-only match", err)

    def test_explain_does_not_pollute_json(self) -> None:
        data = self.run_json(
            "search", "--harness", "qcn", "dark", "--explain"
        )
        self.assertEqual([s["ref"] for s in data], ["qoder-cn:b2c3d4e5"])


class DeepTimeoutTests(FixtureTestCase):
    def test_zero_timeout_means_no_limit(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "qcn", "--deep", "verifier-secret",
            "--timeout", "0",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:a1b2c3d4", out)
        self.assertNotIn("timed out", err)

    def test_expired_timeout_returns_partial_results(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "qcn", "--deep", "verifier-secret",
            "--timeout", "0.000001",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("timed out", err)


if __name__ == "__main__":
    unittest.main()
