"""Tests for the Gemini CLI adapter.

The fixture is a committed synthetic store: two project directories with
``chats/session-*.jsonl`` logs exercising snapshot replacement, bare-message
appends, dedupe, injected context, tool responses, API errors, and a
partially written trailing record. Every identifier and prompt is invented.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from cli_support import FixtureTestCase  # noqa: E402

REF_MAIN = "gemini-cli:11111111"
REF_EMPTY = "gemini-cli:22222222"
REF_BETA = "gemini-cli:33333333"

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_BETA = "/Users/example/project-beta"

PROMPTS_MAIN = (
    "Refactor the handoff digest so the CLI stays bounded.\nKeep it under two pages.",
    "Summarize the handoff digest limits for the README.",
    "Pin the parser tests.",
)
MODEL_MAIN = "synthetic-gemini-1"
PROMPT_BETA = "Draft the migration notes for the digest."
NEEDLE_DEEP_ONLY = "gemini-deep-only-needle"
MAIN_FILE = "session-2026-10-20T09-10-11111111.jsonl"


class GeminiCLITests(FixtureTestCase):
    def test_harness_row(self) -> None:
        payload = self.run_json("harnesses")
        row = next(row for row in payload if row["name"] == "gemini-cli")
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["variants"], "cli")
        self.assertEqual(row["store"], "~/.gemini")
        self.assertIn("gemini", row["aliases"].split(", "))

    def test_lists_sessions_newest_first_across_projects(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "gemini-cli")
        self.assertEqual(code, 0, err)
        refs = [line.split("\t")[0] for line in out.strip().splitlines()[1:]]
        self.assertEqual(refs, [REF_BETA, REF_EMPTY, REF_MAIN])
        self.assertIn(PROJECT_BETA, out)
        self.assertIn(PROJECT_ALPHA, out)

    def test_keyword_title_and_no_match(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "gemini-cli", "migration notes"
        )
        self.assertEqual(code, 0, err)
        self.assertIn(REF_BETA, out)
        self.assertIn(PROMPT_BETA, out)

        code, out, err = self.run_cli(
            "search", "--harness", "gemini-cli", "33333333"
        )
        self.assertEqual(code, 0, err)
        self.assertIn(REF_BETA, out)

        code, out, err = self.run_cli(
            "search", "--harness", "gemini-cli", "no-such-keyword-anywhere"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_cwd_and_latest(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "gemini-cli", "--cwd", PROJECT_ALPHA
        )
        self.assertEqual(code, 0, err)
        self.assertIn(REF_MAIN, out)
        self.assertNotIn(REF_BETA, out)

        code, out, err = self.run_cli("latest", "--harness", "gemini-cli")
        self.assertEqual(code, 0, err)
        self.assertIn(REF_BETA, out)

    def test_long_id_prefix_resolves_via_header(self) -> None:
        code, out, err = self.run_cli(
            "show", "gemini-cli:11111111-2222-4a1b-8c1d-111111111111"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("## Task", out)

    def test_deep_search_finds_tool_response_text(self) -> None:
        with_main = self.gemini_home / "tmp/project-alpha/chats" / MAIN_FILE
        self.assertIn("parser module contents", with_main.read_text())

        code, out, err = self.run_cli(
            "search", "--harness", "gemini-cli", "parser module contents"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "gemini-cli", "--deep", "parser module contents"
        )
        self.assertEqual(code, 0, err)
        self.assertIn(REF_MAIN, out)
        self.assertNotIn(REF_BETA, out)

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli("show", REF_MAIN)
        self.assertEqual(code, 0, err)
        self.assertIn("# gemini-cli:11111111", out)
        self.assertIn("- harness: gemini-cli (cli)", out)
        self.assertIn("- cwd: `%s`" % PROJECT_ALPHA, out)
        self.assertIn("- turns: 3", out)
        self.assertIn("- model: `%s`" % MODEL_MAIN, out)
        self.assertIn("- source: `", out)
        self.assertIn("## Task", out)
        self.assertIn(PROMPTS_MAIN[0], out)
        self.assertIn("[API Error:", out)
        self.assertIn("rate limit reached", out)
        self.assertIn("read_file", out)
        self.assertNotIn("session_context", out)
        self.assertNotIn("Gemini CLI update available", out)

    def test_show_json_fields(self) -> None:
        code, out, err = self.run_cli("show", REF_MAIN, "--format", "json")
        self.assertEqual(code, 0, err)
        detail = json.loads(out)
        self.assertEqual(detail["harness"], "gemini-cli")
        self.assertEqual(detail["session_id"], "11111111")
        self.assertEqual(detail["cwd"], PROJECT_ALPHA)
        self.assertEqual(detail["model"], MODEL_MAIN)
        self.assertEqual(detail["turn_count"], 3)
        self.assertEqual(detail["compact_summary"], "")
        self.assertEqual(detail["todos"], [])
        self.assertEqual(detail["tool_counts"], {"read_file": 1})
        self.assertEqual(detail["archived"], False)
        self.assertGreater(detail["size_bytes"], 0)

    def test_show_empty_session_falls_back_to_id_title(self) -> None:
        code, out, err = self.run_cli("show", REF_EMPTY)
        self.assertEqual(code, 0, err)
        self.assertIn("# gemini-cli:22222222", out)
        self.assertIn("- turns: 0", out)

    def test_bare_prefix_and_missing_refs(self) -> None:
        code, out, err = self.run_cli("show", "33333333")
        self.assertEqual(code, 0, err)
        self.assertIn(PROMPT_BETA, out)

        code, out, err = self.run_cli("show", "gemini-cli:zzzz")
        self.assertEqual(code, 2, err)
        self.assertIn("no session matched", err)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli("prompts", REF_MAIN, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "3")

        code, out, err = self.run_cli("prompts", REF_MAIN, "--limit", "2")
        self.assertEqual(code, 0, err)
        self.assertIn("total: 3, returned: 2, order: oldest", out)
        self.assertIn(PROMPTS_MAIN[0], out)
        self.assertIn(PROMPTS_MAIN[1], out)
        self.assertNotIn(PROMPTS_MAIN[2], out)
        self.assertIn("next: --offset 2 --limit 2", out)

        code, out, err = self.run_cli(
            "prompts", REF_MAIN, "--offset", "2", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertIn(PROMPTS_MAIN[2], out)
        self.assertNotIn(PROMPTS_MAIN[0], out)

        code, out, err = self.run_cli(
            "prompts", REF_MAIN, "--order", "newest", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertIn(PROMPTS_MAIN[2], out)
        self.assertNotIn(PROMPTS_MAIN[0], out)

        code, out, err = self.run_cli("prompts", REF_MAIN, "--offset", "9")
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

    def test_prompts_exclude_injected_context_and_tool_results(self) -> None:
        code, out, err = self.run_cli("prompts", REF_MAIN)
        self.assertEqual(code, 0, err)
        self.assertIn(PROMPTS_MAIN[0], out)
        self.assertNotIn("session_context", out)
        self.assertNotIn("parser module contents", out)
        self.assertNotIn("read_file", out)
        # The context message appears exactly once despite the re-emit.
        self.assertEqual(out.count("This is the Gemini CLI"), 0)

    def test_prompts_json(self) -> None:
        code, out, err = self.run_cli(
            "prompts", REF_MAIN, "--json", "--limit", "1", "--chars", "30"
        )
        self.assertEqual(code, 0, err)
        listing = json.loads(out)
        self.assertEqual(listing["total"], 3)
        self.assertEqual(listing["returned"], 1)
        prompt = listing["prompts"][0]
        self.assertEqual(prompt["index"], 1)
        self.assertTrue(prompt["text"].endswith("…"))
        self.assertTrue(prompt["timestamp"].startswith("2026-10-20T"))

    def test_doctor_reports_the_store(self) -> None:
        payload = self.run_json("doctor", "--harness", "gemini-cli", "--fingerprint")
        store = next(
            item for item in payload["stores"] if item["harness"] == "gemini-cli"
        )
        self.assertTrue(store["present"])
        self.assertEqual(store["candidates"], 3)
        self.assertEqual(store["readable"], 3)
        self.assertEqual(store["skipped"], 0)
        self.assertEqual(store["home"], "<custom>")
        kinds = store["fingerprint"]["kinds"]
        self.assertEqual(kinds["jsonl"]["files"], 3)
        self.assertGreater(kinds["jsonl"]["records"], 0)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(PROJECT_ALPHA, serialized)
        self.assertNotIn("/Users/example", serialized)

    def test_empty_store_is_safe(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "gemini-cli", gemini_home=self.empty_gemini_home
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "doctor", "--harness", "gemini-cli", gemini_home=self.empty_gemini_home
        )
        self.assertEqual(code, 0, err)
        self.assertIn("candidates: 0, readable: 0, skipped: 0", out)

    def test_commands_do_not_modify_gemini_store(self) -> None:
        root = self.gemini_home
        before = {
            str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }
        self.run_cli("search", "--harness", "gemini-cli")
        self.run_cli("latest", "--harness", "gemini-cli")
        self.run_cli("show", REF_MAIN)
        self.run_cli("prompts", REF_MAIN, "--count")
        self.run_cli("search", "--harness", "gemini-cli", "--deep", "parser module")
        self.run_cli("doctor", "--harness", "gemini-cli")
        after = {
            str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }
        self.assertEqual(before, after)

    def test_fixture_data_is_synthetic(self) -> None:
        fixture_root = Path(__file__).resolve().parent / "fixtures" / "gemini-cli-home"
        for path in fixture_root.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("/Users/calvinchen", text, path.name)
            self.assertNotIn("calvin", text.casefold(), path.name)
            if "/Users/" in text:
                self.assertIn("/Users/example/", text, path.name)


if __name__ == "__main__":
    unittest.main()
