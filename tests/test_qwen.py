"""Tests for the Qwen Code adapter.

The fixture is a committed synthetic store: three project directories with
``chats/<uuid>.jsonl`` logs (0.x layout) plus a flat ``<uuid>.jsonl`` log
(1.0-preview layout) with per-session task files, exercising prompt
extraction, tool calls, telemetry skipping, deep search, todos, API-error
surfacing, and a partially written trailing record. Every identifier and
prompt is invented.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from cli_support import FixtureTestCase  # noqa: E402

REF_MAIN = "qwen:aaaaaaaa"
REF_MINI = "qwen:bbbbbbbb"
REF_BETA = "qwen:cccccccc"
REF_GAMMA = "qwen:dddddddd"

PROJECT_ALPHA = "/Users/example/project-alpha"
PROJECT_BETA = "/Users/example/project-beta"
PROJECT_GAMMA = "/Users/example/project-gamma"

PROMPTS_MAIN = (
    "Refactor the handoff digest so the CLI stays bounded.",
    "Also cover the compaction fallback path.",
    "Run the parser tests and fix the failures.",
)
MODEL_MAIN = "synthetic-qwen-1"
PROMPTS_GAMMA = (
    "Review the gamma rollout plan.",
    "Ship the gamma rollout.",
)
MODEL_GAMMA = "synthetic-qwen-2"
GAMMA_TITLE = "Gamma rollout review"
GAMMA_FILE = "dddddddd-4444-4d4e-8f4a-444444444444.jsonl"
PROMPT_BETA = "Draft the migration notes for the digest."
NEEDLE_DEEP_ONLY = "qwen-deep-only-needle"
MAIN_FILE = "aaaaaaaa-1111-4a1b-8c1d-111111111111.jsonl"


class QwenTests(FixtureTestCase):
    def test_harness_row(self) -> None:
        payload = self.run_json("harnesses")
        row = next(row for row in payload if row["name"] == "qwen")
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["variants"], "cli")
        self.assertEqual(row["store"], "~/.qwen")

    def test_lists_sessions_newest_first_across_projects(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qwen")
        self.assertEqual(code, 0, err)
        refs = [line.split("\t")[0] for line in out.strip().splitlines()[1:]]
        self.assertEqual(refs, [REF_GAMMA, REF_BETA, REF_MINI, REF_MAIN])
        self.assertIn(PROJECT_BETA, out)
        self.assertIn(PROJECT_ALPHA, out)
        self.assertIn(PROJECT_GAMMA, out)

    def test_keyword_cwd_and_no_match(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qwen", "migration notes")
        self.assertEqual(code, 0, err)
        self.assertIn(REF_BETA, out)

        code, out, err = self.run_cli(
            "search", "--harness", "qwen", "--cwd", PROJECT_ALPHA
        )
        self.assertEqual(code, 0, err)
        self.assertIn(REF_MAIN, out)
        self.assertNotIn(REF_BETA, out)

        code, out, err = self.run_cli(
            "search", "--harness", "qwen", "no-such-keyword-anywhere"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_latest_and_branch_metadata(self) -> None:
        payload = self.run_json("search", "--harness", "qwen", "--json")
        by_ref = {session["ref"]: session for session in payload}
        self.assertEqual(by_ref[REF_BETA]["branch"], "feature/migration")
        self.assertEqual(by_ref[REF_MAIN]["branch"], "main")
        self.assertEqual(by_ref[REF_MAIN]["version"], "0.8.2")
        self.assertEqual(by_ref[REF_MAIN]["model"], MODEL_MAIN)
        self.assertGreater(by_ref[REF_MAIN]["size_bytes"], 0)
        self.assertEqual(by_ref[REF_GAMMA]["title"], GAMMA_TITLE)
        self.assertEqual(by_ref[REF_GAMMA]["version"], "1.0.0-preview")
        self.assertEqual(by_ref[REF_GAMMA]["model"], MODEL_GAMMA)

        code, out, err = self.run_cli("latest", "--harness", "qwen")
        self.assertEqual(code, 0, err)
        self.assertIn(REF_GAMMA, out)

    def test_generic_prompt_session_falls_back_to_id_title(self) -> None:
        code, out, err = self.run_cli("show", REF_MINI)
        self.assertEqual(code, 0, err)
        self.assertIn("# qwen:bbbbbbbb", out)
        self.assertIn("- turns: 1", out)

    def test_deep_search_finds_tool_result_text(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "qwen", NEEDLE_DEEP_ONLY
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "qwen", "--deep", NEEDLE_DEEP_ONLY
        )
        self.assertEqual(code, 0, err)
        self.assertIn(REF_MAIN, out)
        self.assertNotIn(REF_BETA, out)
        self.assertNotIn(REF_MINI, out)
        self.assertNotIn(REF_GAMMA, out)

    def test_v1_layout_digest_prefers_ai_title(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qwen")
        self.assertEqual(code, 0, err)
        gamma_row = next(
            line for line in out.strip().splitlines() if line.startswith(REF_GAMMA)
        )
        self.assertIn(GAMMA_TITLE, gamma_row)

        code, out, err = self.run_cli("show", REF_GAMMA)
        self.assertEqual(code, 0, err)
        self.assertIn("# qwen:dddddddd", out)
        self.assertIn("- cwd: `%s`" % PROJECT_GAMMA, out)
        self.assertIn("- branch: `main`", out)
        self.assertIn("- version: `1.0.0-preview`", out)
        self.assertIn("- model: `%s`" % MODEL_GAMMA, out)
        self.assertIn("- turns: 2", out)
        self.assertIn("## Todos (1 open / 2 total)", out)
        self.assertIn("[in_progress] Audit the gamma rollout plan", out)
        self.assertIn("Bash: ls gamma/", out)
        self.assertIn("Synthetic provider error: socket closed", out)
        self.assertNotIn("gamma plan files listed", out)
        self.assertNotIn("synthetic skill reference", out)
        self.assertIn(GAMMA_FILE, out)

    def test_v1_prompts_exclude_tool_results_meta_and_attachments(self) -> None:
        code, out, err = self.run_cli("prompts", REF_GAMMA, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "2")

        code, out, err = self.run_cli("prompts", REF_GAMMA)
        self.assertEqual(code, 0, err)
        for prompt in PROMPTS_GAMMA:
            self.assertIn(prompt, out)
        self.assertNotIn("gamma plan files listed", out)
        self.assertNotIn("synthetic local command output", out)
        self.assertNotIn("synthetic skill reference", out)
        self.assertNotIn("/status", out)

    def test_v1_todos_and_tools_in_json_digest(self) -> None:
        code, out, err = self.run_cli("show", REF_GAMMA, "--format", "json")
        self.assertEqual(code, 0, err)
        detail = json.loads(out)
        self.assertEqual(detail["session_id"], "dddddddd-4444-4d4e-8f4a-444444444444")
        self.assertEqual(detail["cwd"], PROJECT_GAMMA)
        self.assertEqual(detail["model"], MODEL_GAMMA)
        self.assertEqual(detail["turn_count"], 2)
        self.assertEqual(
            [todo["status"] for todo in detail["todos"]],
            ["in_progress", "completed"],
        )
        self.assertEqual(detail["tool_counts"], {"Bash": 1})

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli("show", REF_MAIN)
        self.assertEqual(code, 0, err)
        self.assertIn("# qwen:aaaaaaaa", out)
        self.assertIn("- harness: qwen (cli)", out)
        self.assertIn("- cwd: `%s`" % PROJECT_ALPHA, out)
        self.assertIn("- branch: `main`", out)
        self.assertIn("- version: `0.8.2`", out)
        self.assertIn("- turns: 3", out)
        self.assertIn("- model: `%s`" % MODEL_MAIN, out)
        self.assertIn("- source: `", out)
        self.assertIn("## Task", out)
        self.assertIn(PROMPTS_MAIN[0], out)
        self.assertIn("## Todos (2 open / 3 total)", out)
        self.assertIn("[in_progress] Add prompt paging", out)
        self.assertIn("## Recent tools", out)
        self.assertIn("read_file: /Users/example/project-alpha/src/handoff.py", out)
        self.assertNotIn("ui_telemetry", out)
        self.assertNotIn("qwen-deep-only-needle", out)

    def test_show_json_fields(self) -> None:
        code, out, err = self.run_cli("show", REF_MAIN, "--format", "json")
        self.assertEqual(code, 0, err)
        detail = json.loads(out)
        self.assertEqual(detail["harness"], "qwen")
        self.assertEqual(detail["session_id"], "aaaaaaaa-1111-4a1b-8c1d-111111111111")
        self.assertEqual(detail["cwd"], PROJECT_ALPHA)
        self.assertEqual(detail["model"], MODEL_MAIN)
        self.assertEqual(detail["turn_count"], 3)
        self.assertEqual(detail["compact_summary"], "")
        self.assertEqual(
            [todo["status"] for todo in detail["todos"]],
            ["completed", "in_progress", "pending"],
        )
        self.assertEqual(detail["tool_counts"], {"read_file": 1})
        self.assertEqual(detail["archived"], False)
        self.assertTrue(detail["path"].endswith(MAIN_FILE))

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli("prompts", REF_MAIN, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "3")

        code, out, err = self.run_cli("prompts", REF_MAIN, "--limit", "2")
        self.assertEqual(code, 0, err)
        self.assertIn("total: 3, returned: 2, order: oldest", out)
        self.assertIn(PROMPTS_MAIN[0], out)
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

        code, out, err = self.run_cli("prompts", REF_MAIN, "--offset", "9")
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

    def test_prompts_exclude_tool_results_and_telemetry(self) -> None:
        code, out, err = self.run_cli("prompts", REF_MAIN)
        self.assertEqual(code, 0, err)
        for prompt in PROMPTS_MAIN:
            self.assertIn(prompt, out)
        self.assertNotIn("parser module contents", out)
        self.assertNotIn("functionResponse", out)
        self.assertNotIn(NEEDLE_DEEP_ONLY, out)

        code, out, err = self.run_cli("prompts", REF_BETA, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "1")

    def test_prompts_json(self) -> None:
        code, out, err = self.run_cli(
            "prompts", REF_MAIN, "--json", "--limit", "1", "--chars", "30"
        )
        self.assertEqual(code, 0, err)
        listing = json.loads(out)
        self.assertEqual(listing["total"], 3)
        prompt = listing["prompts"][0]
        self.assertEqual(prompt["index"], 1)
        self.assertTrue(prompt["text"].endswith("…"))

    def test_doctor_reports_the_store(self) -> None:
        payload = self.run_json("doctor", "--harness", "qwen", "--fingerprint")
        store = next(
            item for item in payload["stores"] if item["harness"] == "qwen"
        )
        self.assertTrue(store["present"])
        self.assertEqual(store["candidates"], 4)
        self.assertEqual(store["readable"], 4)
        self.assertEqual(store["skipped"], 0)
        self.assertEqual(store["home"], "<custom>")
        kinds = store["fingerprint"]["kinds"]
        self.assertEqual(kinds["jsonl"]["files"], 4)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(PROJECT_ALPHA, serialized)
        self.assertNotIn("/Users/example", serialized)

    def test_empty_store_is_safe(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "qwen", qwen_home=self.empty_qwen_home
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_commands_do_not_modify_qwen_store(self) -> None:
        root = self.qwen_home
        before = {
            str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }
        self.run_cli_checked("search", "--harness", "qwen")
        self.run_cli_checked("latest", "--harness", "qwen")
        self.run_cli_checked("show", REF_MAIN)
        self.run_cli_checked("prompts", REF_MAIN, "--count")
        self.run_cli_checked("show", REF_GAMMA)
        self.run_cli_checked("prompts", REF_GAMMA, "--count")
        self.run_cli_checked("search", "--harness", "qwen", "--deep", NEEDLE_DEEP_ONLY)
        self.run_cli_checked("doctor", "--harness", "qwen")
        after = {
            str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }
        self.assertEqual(before, after)

    def test_fixture_data_is_synthetic(self) -> None:
        fixture_root = Path(__file__).resolve().parent / "fixtures" / "qwen-home"
        for path in fixture_root.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("calvin", text.casefold(), path.name)
            if "/Users/" in text:
                self.assertIn("/Users/example/", text, path.name)


if __name__ == "__main__":
    unittest.main()
