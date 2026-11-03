from __future__ import annotations

import json
import re
from pathlib import Path

from cli_support import FixtureTestCase
from grok_fixture import (
    BRANCH_MAIN as GROK_BRANCH_MAIN,
    COMPACT_SESSION_SUMMARY as GROK_COMPACT_SESSION_SUMMARY,
    COMPACT_SUMMARY as GROK_COMPACT_SUMMARY,
    GROUP_ALPHA as GROK_GROUP_ALPHA,
    MODEL_MAIN as GROK_MODEL_MAIN,
    NEEDLE_CHAT_ONLY as GROK_CHAT_ONLY_NEEDLE,
    NEEDLE_COMPACTION_ONLY as GROK_COMPACTION_ONLY_NEEDLE,
    NEEDLE_DECOY as GROK_DECOY_NEEDLE,
    NEEDLE_DEEP_ONLY as GROK_DEEP_ONLY_NEEDLE,
    NEEDLE_SUBAGENT as GROK_SUBAGENT_NEEDLE,
    NEEDLE_TOOL_OUTPUT as GROK_TOOL_OUTPUT_NEEDLE,
    PROMPTS_AUX as GROK_PROMPTS_AUX,
    PROMPTS_MAIN as GROK_PROMPTS,
    PROMPT_COMPACT_EARLY as GROK_COMPACT_EARLY_PROMPT,
    PROMPT_COMPACT_RESUME as GROK_COMPACT_RESUME_PROMPT,
    PROMPT_DECOY as GROK_DECOY_PROMPT,
    PROMPT_HIDDEN as GROK_HIDDEN_PROMPT,
    PROMPT_INTERRUPT as GROK_INTERRUPT_PROMPT,
    PROMPT_PLAIN as GROK_PLAIN_PROMPT,
    PROMPT_SLASH as GROK_SLASH_PROMPT,
    PROMPT_SYNTHETIC as GROK_SYNTHETIC_PROMPT,
    PROJECT_ALPHA as GROK_PROJECT_ALPHA,
    PROJECT_DELTA as GROK_PROJECT_DELTA,
    SESSION_AUX as GROK_AUX,
    SESSION_COMPACT as GROK_COMPACT,
    SESSION_EMPTY as GROK_EMPTY,
    SESSION_MAIN as GROK_MAIN,
    SESSION_PLAIN as GROK_PLAIN,
    SESSION_SUBAGENT as GROK_SUBAGENT,
    TITLE_MAIN as GROK_TITLE_MAIN,
)


class GrokBuildTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli("show", *args, "--format", "json", **kwargs)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_harness_row(self) -> None:
        rows = self.run_json("harnesses")
        rows = [row for row in rows if row["name"] == "grok-build"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "ready")
        self.assertEqual(rows[0]["variants"], "tui, headless, acp")
        self.assertEqual(rows[0]["store"], "~/.grok")
        self.assertEqual(rows[0]["aliases"], "grok-build, grok, grok-cli")

    def test_lists_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "grok-build")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("grok-build:9a0b1c03"))
        self.assertTrue(lines[1].startswith("grok-build:9a0b1c02"))
        self.assertTrue(lines[2].startswith("grok-build:9a0b1c04"))
        self.assertTrue(lines[3].startswith("grok-build:9a0b1c01"))
        self.assertNotIn("9a0b1c05", out)
        self.assertNotIn("9a0b1c06", out)
        self.assertNotIn("9a0b1c07", out)
        self.assertNotIn(GROK_DECOY_PROMPT, out)

    def test_aliases(self) -> None:
        for alias in ("grok-build", "grok", "grok-cli"):
            sessions = self.run_json("search", "--harness", alias, "--limit", "0")
            self.assertEqual(len(sessions), 4)
            self.assertTrue(
                all(session["ref"].startswith("grok-build:") for session in sessions)
            )

    def test_keyword_id_cwd_since_limit_and_no_match(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "grok-build", "handoff")
        self.assertEqual(code, 0, err)
        self.assertIn("grok-build:9a0b1c01", out)
        self.assertNotIn("9a0b1c03", out)

        sessions = self.run_json("search", "--harness", "grok-build", "9a0b1c03")
        self.assertEqual(
            [session["ref"] for session in sessions], ["grok-build:9a0b1c03"]
        )

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "grok-build",
            "--cwd",
            GROK_PROJECT_ALPHA,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("grok-build:9a0b1c01", out)
        self.assertIn("grok-build:9a0b1c02", out)
        self.assertNotIn("9a0b1c03", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "grok-build",
            "--cwd",
            GROK_PROJECT_DELTA,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("grok-build:9a0b1c03", out)
        self.assertNotIn("9a0b1c01", out)

        code, out, err = self.run_cli(
            "search", "--harness", "grok-build", "--cwd", "/Users/example"
        )
        self.assertEqual(code, 0, err)
        for ref in ("9a0b1c01", "9a0b1c02", "9a0b1c03", "9a0b1c04"):
            self.assertIn(ref, out)

        code, out, err = self.run_cli(
            "search", "--harness", "grok-build", "--since", "2026-10-24"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("9a0b1c03", out)
        self.assertIn("9a0b1c02", out)
        self.assertIn("9a0b1c04", out)
        self.assertNotIn("9a0b1c01", out)

        code, out, err = self.run_cli(
            "search", "--harness", "grok-build", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

        code, out, err = self.run_cli(
            "search", "--harness", "grok-build", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_latest_and_query_filter(self) -> None:
        sessions = self.run_json("latest", "--harness", "grok-build")
        self.assertEqual(
            [session["ref"] for session in sessions], ["grok-build:9a0b1c03"]
        )
        self.assertEqual(sessions[0]["title"], GROK_PLAIN_PROMPT)
        self.assertEqual(sessions[0]["first_prompt"], GROK_PLAIN_PROMPT)
        self.assertEqual(sessions[0]["last_prompt"], GROK_PLAIN_PROMPT)
        self.assertEqual(sessions[0]["cwd"], GROK_PROJECT_DELTA)
        self.assertEqual(sessions[0]["variants"], "tui, headless, acp")

        sessions = self.run_json("latest", "--harness", "grok-build", "handoff")
        self.assertEqual(
            [session["ref"] for session in sessions], ["grok-build:9a0b1c01"]
        )
        self.assertEqual(sessions[0]["title"], GROK_TITLE_MAIN)
        self.assertEqual(sessions[0]["first_prompt"], GROK_PROMPTS[0])
        self.assertEqual(sessions[0]["last_prompt"], GROK_PROMPTS[-1])

        code, out, err = self.run_cli(
            "latest", "--harness", "grok-build", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_archive_flag_is_always_inactive(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "grok-build",
            "--include-archived",
            "--limit",
            "0",
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        for line in lines:
            self.assertEqual(line.split("\t")[-1], "-")

        data = self.show_json("grok-build:9a0b1c01", "--messages", "0")
        self.assertFalse(data["archived"])

        code, out, err = self.run_cli("show", "grok-build:9a0b1c01")
        self.assertEqual(code, 0, err)
        self.assertNotIn("- archived: yes", out)

    def test_deep_search_scans_content(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "grok-build", GROK_DEEP_ONLY_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "grok-build", "--deep", GROK_DEEP_ONLY_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("grok-build:9a0b1c03", out)
        self.assertNotIn("9a0b1c01", out)

        code, out, err = self.run_cli(
            "search", "--harness", "grok-build", "--deep", GROK_TOOL_OUTPUT_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("grok-build:9a0b1c01", out)
        self.assertNotIn("9a0b1c03", out)

        for needle in (GROK_COMPACTION_ONLY_NEEDLE, GROK_CHAT_ONLY_NEEDLE):
            code, out, err = self.run_cli(
                "search", "--harness", "grok-build", "--deep", needle
            )
            self.assertEqual(code, 0, err)
            self.assertIn("grok-build:9a0b1c01", out)
            self.assertNotIn("9a0b1c03", out)

    def test_deep_search_tokens_do_not_leak_across_sessions(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "grok-build",
            "--deep",
            "grok-main-needle",
            GROK_DEEP_ONLY_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "grok-build",
            "--deep",
            GROK_COMPACTION_ONLY_NEEDLE,
            GROK_CHAT_ONLY_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("grok-build:9a0b1c01", out)
        self.assertNotIn("9a0b1c03", out)

    def test_subagent_and_decoy_records_are_excluded(self) -> None:
        for needle in (GROK_SUBAGENT_NEEDLE, GROK_DECOY_NEEDLE):
            code, out, err = self.run_cli(
                "search", "--harness", "grok-build", "--deep", needle
            )
            self.assertEqual(code, 0, err)
            self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli("show", "grok-build:9a0b1c05")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        subagent_path = (
            self.grok_home
            / "sessions"
            / GROK_GROUP_ALPHA
            / GROK_SUBAGENT
            / "updates.jsonl"
        )
        code, out, err = self.run_cli("show", str(subagent_path))
        self.assertEqual(code, 2)
        self.assertIn("not resumable", err)

        empty_path = (
            self.grok_home
            / "sessions"
            / GROK_GROUP_ALPHA
            / GROK_EMPTY
            / "summary.json"
        )
        code, out, err = self.run_cli("show", str(empty_path))
        self.assertEqual(code, 2)
        self.assertIn("cannot read Grok Build transcript", err)

        decoy_path = (
            self.grok_home / "sessions" / GROK_GROUP_ALPHA / "notes.json"
        )
        code, out, err = self.run_cli("show", str(decoy_path))
        self.assertEqual(code, 2)
        self.assertIn("not inside a known harness session store", err)

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli(
            "show", "grok-build:9a0b1c01", "--messages", "6", "--chars", "120"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("# grok-build:9a0b1c01", out)
        self.assertIn("- harness: grok-build (tui, headless, acp)", out)
        self.assertIn("- cwd: `%s`" % GROK_PROJECT_ALPHA, out)
        self.assertIn("- branch: `%s`" % GROK_BRANCH_MAIN, out)
        self.assertIn("- turns: 5", out)
        self.assertIn("- model: `%s`" % GROK_MODEL_MAIN, out)
        self.assertNotIn("- version:", out)
        self.assertIn("## Task", out)
        self.assertIn(GROK_PROMPTS[0], out)
        self.assertIn("## Latest request", out)
        self.assertIn(GROK_PROMPTS[-1], out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn("Summary of the handoff digest refactor.", out)
        self.assertIn("## Todos (2 open / 3 total)", out)
        self.assertIn("[in_progress] Add prompt paging", out)
        self.assertIn("[pending] Update docs", out)
        self.assertNotIn("[completed] Refactor the digest", out)
        self.assertIn("## Edited files", out)
        self.assertIn("src/handoff.ts` (x2)", out)
        self.assertIn("docs/handoff.md`", out)
        self.assertIn("## Recent tools", out)
        self.assertIn("search_replace", out)
        self.assertIn("run_terminal_command", out)
        self.assertIn("## Recent turns", out)
        self.assertNotIn("- archived: yes", out)
        self.assertNotIn("<system-reminder>", out)
        self.assertNotIn(GROK_HIDDEN_PROMPT, out)
        self.assertNotIn(GROK_SYNTHETIC_PROMPT, out)
        self.assertNotIn(GROK_SLASH_PROMPT, out)
        self.assertNotIn(GROK_INTERRUPT_PROMPT, out)
        self.assertNotIn(GROK_TOOL_OUTPUT_NEEDLE, out)
        self.assertNotIn(GROK_CHAT_ONLY_NEEDLE, out)
        self.assertNotIn("An older summary that must lose", out)
        self.assertNotIn(GROK_DECOY_PROMPT, out)

    def test_show_json_fields(self) -> None:
        data = self.show_json("grok-build:9a0b1c01", "--messages", "0")
        self.assertEqual(data["ref"], "grok-build:9a0b1c01")
        self.assertEqual(data["session_id"], GROK_MAIN)
        self.assertEqual(data["cwd"], GROK_PROJECT_ALPHA)
        self.assertEqual(data["entrypoint"], "")
        self.assertEqual(data["variants"], "tui, headless, acp")
        self.assertEqual(data["branch"], GROK_BRANCH_MAIN)
        self.assertEqual(data["version"], "")
        self.assertEqual(data["model"], GROK_MODEL_MAIN)
        self.assertGreater(data["size_bytes"], 0)
        self.assertFalse(data["archived"])
        self.assertEqual(data["started"], "2026-10-20T09:10:00Z")
        self.assertEqual(data["updated"], "2026-10-20T10:08:00Z")
        self.assertEqual(data["title"], GROK_TITLE_MAIN)
        self.assertEqual(data["compact_summary"], GROK_COMPACT_SUMMARY)
        self.assertEqual(data["first_prompt"], GROK_PROMPTS[0])
        self.assertEqual(data["last_prompt"], GROK_PROMPTS[-1])
        self.assertEqual(data["turn_count"], 5)
        self.assertEqual(
            data["todos"],
            [
                {"subject": "Refactor the digest", "status": "completed"},
                {"subject": "Add prompt paging", "status": "in_progress"},
                {"subject": "Update docs", "status": "pending"},
            ],
        )
        self.assertEqual(
            data["edited_files"],
            [
                {
                    "path": GROK_PROJECT_ALPHA + "/src/handoff.ts",
                    "count": 2,
                },
                {
                    "path": GROK_PROJECT_ALPHA + "/docs/handoff.md",
                    "count": 1,
                },
            ],
        )
        self.assertEqual(
            data["tool_counts"],
            {
                "search_replace": 2,
                "read_file": 1,
                "write": 1,
                "run_terminal_command": 1,
            },
        )
        self.assertEqual(
            data["path"],
            str(
                self.grok_home
                / "sessions"
                / GROK_GROUP_ALPHA
                / GROK_MAIN
                / "updates.jsonl"
            ),
        )

    def test_show_aux_title_fallback(self) -> None:
        data = self.show_json("grok-build:9a0b1c02", "--messages", "0")
        self.assertEqual(data["session_id"], GROK_AUX)
        self.assertEqual(data["title"], GROK_PROMPTS_AUX[0])
        self.assertEqual(data["first_prompt"], GROK_PROMPTS_AUX[0])
        self.assertEqual(data["last_prompt"], GROK_PROMPTS_AUX[1])
        self.assertEqual(data["turn_count"], 2)
        self.assertEqual(data["todos"], [])
        self.assertFalse(data["archived"])

        code, out, err = self.run_cli("show", "grok-build:9a0b1c02")
        self.assertEqual(code, 0, err)
        self.assertIn("- turns: 2", out)
        self.assertIn("## Latest request", out)
        self.assertIn(GROK_PROMPTS_AUX[1], out)
        self.assertNotIn("## Todos", out)

    def test_show_plain_session_uses_group_cwd(self) -> None:
        data = self.show_json("grok-build:9a0b1c03", "--messages", "5")
        self.assertEqual(data["cwd"], GROK_PROJECT_DELTA)
        self.assertEqual(data["title"], GROK_PLAIN_PROMPT)
        self.assertEqual(data["first_prompt"], GROK_PLAIN_PROMPT)
        self.assertEqual(data["last_prompt"], GROK_PLAIN_PROMPT)
        self.assertEqual(data["turn_count"], 1)
        self.assertEqual(data["todos"], [])
        self.assertEqual(data["edited_files"], [])
        self.assertIn(
            "API error: synthetic quota exceeded.", json.dumps(data)
        )

    def test_show_compacted_session(self) -> None:
        code, out, err = self.run_cli("show", "grok-build:9a0b1c04")
        self.assertEqual(code, 0, err)
        self.assertIn("- turns: 2", out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn(GROK_COMPACT_SESSION_SUMMARY, out)
        self.assertNotIn("An earlier migration summary.", out)

        data = self.show_json("grok-build:9a0b1c04", "--messages", "0")
        self.assertEqual(data["compact_summary"], GROK_COMPACT_SESSION_SUMMARY)
        self.assertEqual(data["first_prompt"], GROK_COMPACT_EARLY_PROMPT)
        self.assertEqual(data["last_prompt"], GROK_COMPACT_RESUME_PROMPT)
        self.assertEqual(data["turn_count"], 2)

        prompts = self.run_json("prompts", "grok-build:9a0b1c04", "--limit", "0")
        self.assertEqual(prompts["total"], 2)
        self.assertEqual(
            [prompt["text"] for prompt in prompts["prompts"]],
            [GROK_COMPACT_EARLY_PROMPT, GROK_COMPACT_RESUME_PROMPT],
        )

    def test_show_by_source_path(self) -> None:
        data = self.show_json("grok-build:9a0b1c01", "--messages", "0")
        source = data["path"]

        code, out, err = self.run_cli("show", source)
        self.assertEqual(code, 0, err)
        self.assertIn("# grok-build:9a0b1c01", out)

        code, out, err = self.run_cli("prompts", source, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "5")

    def test_show_missing_ambiguous_and_too_short_refs(self) -> None:
        code, out, err = self.run_cli("show", "grok-build:9a0b1cff")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "grok-build:9a0b1c0")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", err)

        code, out, err = self.run_cli("show", "grok-build:9a0")
        self.assertEqual(code, 2)
        self.assertIn("too short", err)

        code, out, err = self.run_cli("show", "9a0b1c03")
        self.assertEqual(code, 0, err)
        self.assertIn("# grok-build:9a0b1c03", out)

        code, out, err = self.run_cli("show", "grok-build:9a0b1c06")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli("prompts", "grok-build:9a0b1c01", "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "5")

        code, out, err = self.run_cli("prompts", "grok-build:9a0b1c01")
        self.assertEqual(code, 0, err)
        for index, prompt in enumerate(GROK_PROMPTS, 1):
            self.assertIn("## %d" % index, out)
            self.assertIn(prompt, out)

        code, out, err = self.run_cli(
            "prompts", "grok-build:9a0b1c01", "--offset", "1", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("## 2", out)
        self.assertNotIn(GROK_PROMPTS[0], out)
        self.assertIn("next: --offset 2 --limit 1", out)

        code, out, err = self.run_cli(
            "prompts", "grok-build:9a0b1c01", "--order", "newest", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("## 5"), out.index("## 4"))
        self.assertNotIn("## 1", out)

        code, out, err = self.run_cli(
            "prompts", "grok-build:9a0b1c01", "--offset", "9"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts", "grok-build:9a0b1c01", "--limit", "1", "--chars", "10"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Please re…", out)
        self.assertNotIn(GROK_PROMPTS[0], out)

    def test_prompts_json(self) -> None:
        data = self.run_json("prompts", "grok-build:9a0b1c01", "--limit", "2")
        self.assertEqual(data["ref"], "grok-build:9a0b1c01")
        self.assertEqual(data["session_id"], GROK_MAIN)
        self.assertEqual(data["cwd"], GROK_PROJECT_ALPHA)
        self.assertFalse(data["archived"])
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["returned"], 2)
        self.assertTrue(data["has_more"])
        self.assertEqual([prompt["index"] for prompt in data["prompts"]], [1, 2])
        self.assertEqual(data["prompts"][0]["text"], GROK_PROMPTS[0])
        self.assertIsNotNone(data["prompts"][0]["timestamp"])

    def test_non_human_records_never_become_prompts(self) -> None:
        prompts = self.run_json("prompts", "grok-build:9a0b1c01", "--limit", "0")
        texts = [prompt["text"] for prompt in prompts["prompts"]]
        self.assertEqual(texts, list(GROK_PROMPTS))
        self.assertEqual(texts.count(GROK_PROMPTS[0]), 1)
        self.assertEqual(texts[2], "Tighten the digest tests.")
        for text in texts:
            self.assertNotIn("<system-reminder>", text)
            self.assertNotIn("<task-notification>", text)
            self.assertNotIn("<local-command", text)
        for excluded in (
            GROK_HIDDEN_PROMPT,
            GROK_SYNTHETIC_PROMPT,
            GROK_SLASH_PROMPT,
            GROK_INTERRUPT_PROMPT,
            GROK_TOOL_OUTPUT_NEEDLE,
            "Subagent scratch work",
            GROK_DECOY_PROMPT,
            "This session is being continued",
        ):
            self.assertFalse(
                any(excluded in text for text in texts), excluded
            )

    def test_cross_harness_isolation(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "claude-code", "grok-main-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "grok-build", "claude-main-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli("show", "claude-code:9a0b1c01")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "grok-build:c1a0de01")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        sessions = self.run_json("search", "grok-main-needle", "--limit", "0")
        self.assertEqual(
            {session["ref"] for session in sessions}, {"grok-build:9a0b1c01"}
        )

    def test_empty_store_is_safe(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "grok-build",
            grok_home=self.empty_grok_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "latest",
            "--harness",
            "grok-build",
            grok_home=self.empty_grok_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_commands_do_not_modify_grok_store(self) -> None:
        def snapshot() -> dict:
            files = {}
            for path in self.grok_home.rglob("*"):
                if path.is_file():
                    files[str(path)] = (
                        path.read_bytes(),
                        path.stat().st_mtime_ns,
                    )
            return files

        before = snapshot()
        self.run_cli("search", "--harness", "grok-build")
        self.run_cli("search", "--harness", "grok-build", "--include-archived")
        self.run_cli(
            "search", "--harness", "grok-build", "--deep", GROK_DEEP_ONLY_NEEDLE
        )
        self.run_cli("latest", "--harness", "grok-build")
        self.run_cli("show", "grok-build:9a0b1c01")
        self.run_cli("show", "grok-build:9a0b1c02")
        self.run_cli("show", "grok-build:9a0b1c04", "--format", "json")
        self.run_cli("prompts", "grok-build:9a0b1c01")
        self.run_cli("prompts", "grok-build:9a0b1c01", "--count")
        self.assertEqual(snapshot(), before)
        self.assertFalse(
            any(
                path.name.endswith(("-wal", "-shm", "-journal"))
                for path in self.grok_home.rglob("*")
            )
        )

    def test_fixture_data_is_synthetic(self) -> None:
        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        for path in self.grok_home.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8", "ignore")
            self.assertNotIn(str(Path.home()), text)
            self.assertNotIn("/Volumes/", text)
            self.assertNotIn("/home/", text)
            self.assertNotIn("/Users/", text.replace("/Users/example/", ""))
            self.assertNotIn("lcdp-ai-chat", text)
            self.assertNotIn("fuse-console", text)
            self.assertIsNone(email.search(text), str(path))
        for session_id in (
            GROK_MAIN,
            GROK_AUX,
            GROK_PLAIN,
            GROK_COMPACT,
            GROK_SUBAGENT,
            GROK_EMPTY,
        ):
            self.assertTrue(session_id.startswith("9a0b1c"), session_id)
