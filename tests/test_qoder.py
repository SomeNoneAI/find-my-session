from __future__ import annotations

from cli_support import (
    FixtureTestCase,
    SESSION_C,
)


class QoderInternationalTests(FixtureTestCase):
    def test_lists_only_international_sessions(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qoder")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("qoder:d4e5f6a7"))
        self.assertTrue(lines[1].startswith("qoder:c3d4e5f6"))
        self.assertNotIn("qoder-cn:", out)

    def test_alias_and_cwd_filter(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "qoder-intl",
            "--cwd",
            "/Users/example/project-gamma",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder:c3d4e5f6", out)
        self.assertNotIn("qoder:d4e5f6a7", out)

    def test_does_not_mix_with_qoder_cn(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qoder-cn")
        self.assertEqual(code, 0, err)
        self.assertNotIn("c3d4e5f6", out)
        self.assertNotIn("d4e5f6a7", out)

        code, out, err = self.run_cli("search", "--harness", "qoder")
        self.assertEqual(code, 0, err)
        self.assertNotIn("a1b2c3d4", out)
        self.assertNotIn("b2c3d4e5", out)

    def test_default_scan_covers_both_products(self) -> None:
        sessions = self.run_json("search", "--limit", "0")
        harnesses = {session["harness"] for session in sessions}
        self.assertLessEqual({"qoder-cn", "qoder"}, harnesses)

    def test_refs_do_not_cross_stores(self) -> None:
        code, out, err = self.run_cli("show", "qoder:a1b2c3d4")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "qoder-cn:c3d4e5f6")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_show_digest(self) -> None:
        code, out, err = self.run_cli("show", "qoder:c3d4e5f6")
        self.assertEqual(code, 0, err)
        self.assertIn("# qoder:c3d4e5f6", out)
        self.assertIn("## Task\nAdd billing webhook retries", out)
        self.assertIn("## Latest request\nUse exponential backoff", out)
        self.assertIn("## Todos (1 open / 2 total)", out)
        self.assertIn("[pending] Add replay protection for webhook deliveries", out)
        self.assertIn("`/Users/example/project-gamma/src/billing/webhook.ts`", out)

    def test_show_compact_summary(self) -> None:
        code, out, err = self.run_cli("show", "qoder:d4e5f6a7")
        self.assertEqual(code, 0, err)
        self.assertIn("## Task\nExport invoices as CSV", out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn("invoice export pipeline", out)
        self.assertIn("[in_progress] Verify CSV escaping", out)
        self.assertNotIn("Expanded skill body", out)

    def test_show_by_path_resolves_international_harness(self) -> None:
        path = (
            self.qoder_home
            / "projects"
            / "-Users-example-project-gamma"
            / (SESSION_C + ".jsonl")
        )
        code, out, err = self.run_cli("show", str(path))
        self.assertEqual(code, 0, err)
        self.assertIn("# qoder:c3d4e5f6", out)

    def test_task_transcripts_are_not_sessions(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qoder")
        self.assertEqual(code, 0, err)
        self.assertNotIn("task-", out)

        code, out, err = self.run_cli(
            "search", "--harness", "qoder", "--deep", "subagent-only-marker"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_json_fields_use_international_ref(self) -> None:
        sessions = self.run_json("search", "--harness", "qoder", "billing")
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["ref"], "qoder:c3d4e5f6")
        self.assertEqual(sessions[0]["harness"], "qoder")
        self.assertEqual(sessions[0]["session_id"], SESSION_C)
        self.assertEqual(sessions[0]["cwd"], "/Users/example/project-gamma")
