from __future__ import annotations

import json
import re
from pathlib import Path

from cli_support import FixtureTestCase
from claude_code_fixture import (
    COMPACT_SESSION_SUMMARY as CLAUDE_COMPACT_SESSION_SUMMARY,
    COMPACT_SUMMARY as CLAUDE_COMPACT_SUMMARY,
    HISTORY_PROMPT as CLAUDE_HISTORY_PROMPT,
    NEEDLE_DEEP_ONLY as CLAUDE_DEEP_ONLY_NEEDLE,
    NEEDLE_SUBAGENT as CLAUDE_SUBAGENT_NEEDLE,
    NEEDLE_TOOL_OUTPUT as CLAUDE_TOOL_OUTPUT_NEEDLE,
    PROMPTS_AUX as CLAUDE_PROMPTS_AUX,
    PROMPTS_MAIN as CLAUDE_PROMPTS,
    PROMPT_COMPACT_RESUME as CLAUDE_COMPACT_RESUME_PROMPT,
    PROMPT_PLAIN as CLAUDE_PLAIN_PROMPT,
    SESSION_AUX as CLAUDE_AUX,
    SESSION_COMPACT as CLAUDE_COMPACT,
    SESSION_MAIN as CLAUDE_MAIN,
    SESSION_PLAIN as CLAUDE_PLAIN,
    TITLE_MAIN as CLAUDE_TITLE_MAIN,
    VERSION_MAIN as CLAUDE_VERSION,
)


class ClaudeCodeTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli("show", *args, "--format", "json", **kwargs)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_harness_row(self) -> None:
        rows = self.run_json("harnesses")
        rows = [row for row in rows if row["name"] == "claude-code"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "ready")
        self.assertEqual(rows[0]["variants"], "cli, ide")
        self.assertEqual(rows[0]["store"], "~/.claude")
        self.assertEqual(rows[0]["aliases"], "claude, claude-code")

    def test_lists_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "claude-code")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("claude-code:c1a0de03"))
        self.assertTrue(lines[1].startswith("claude-code:c1a0de02"))
        self.assertTrue(lines[2].startswith("claude-code:c1a0de04"))
        self.assertTrue(lines[3].startswith("claude-code:c1a0de01"))
        self.assertNotIn("c1a0de05", out)
        self.assertNotIn("c1a0de06", out)
        self.assertNotIn("c1a0deff", out)

    def test_aliases(self) -> None:
        for alias in ("claude", "claude-code"):
            sessions = self.run_json("search", "--harness", alias, "--limit", "0")
            self.assertEqual(len(sessions), 4)
            self.assertTrue(
                all(session["ref"].startswith("claude-code:") for session in sessions)
            )

    def test_keyword_id_cwd_since_limit_and_no_match(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "claude-code", "handoff")
        self.assertEqual(code, 0, err)
        self.assertIn("claude-code:c1a0de01", out)
        self.assertNotIn("c1a0de03", out)

        sessions = self.run_json("search", "--harness", "claude-code", "c1a0de03")
        self.assertEqual(
            [session["ref"] for session in sessions], ["claude-code:c1a0de03"]
        )

        code, out, err = self.run_cli(
            "search", "--harness", "claude-code", "--cwd", "/Users/example/project-alpha"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("claude-code:c1a0de01", out)
        self.assertNotIn("c1a0de02", out)

        code, out, err = self.run_cli(
            "search", "--harness", "claude-code", "--cwd", "/Users/example"
        )
        self.assertEqual(code, 0, err)
        for ref in ("c1a0de01", "c1a0de02", "c1a0de03", "c1a0de04"):
            self.assertIn(ref, out)

        code, out, err = self.run_cli(
            "search", "--harness", "claude-code", "--since", "2026-10-24"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("c1a0de03", out)
        self.assertIn("c1a0de02", out)
        self.assertIn("c1a0de04", out)
        self.assertNotIn("c1a0de01", out)

        code, out, err = self.run_cli(
            "search", "--harness", "claude-code", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

        code, out, err = self.run_cli(
            "search", "--harness", "claude-code", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_latest_and_query_filter(self) -> None:
        sessions = self.run_json("latest", "--harness", "claude-code")
        self.assertEqual(
            [session["ref"] for session in sessions], ["claude-code:c1a0de03"]
        )
        self.assertEqual(sessions[0]["title"], CLAUDE_PLAIN_PROMPT)
        self.assertEqual(sessions[0]["first_prompt"], CLAUDE_PLAIN_PROMPT)
        self.assertEqual(sessions[0]["last_prompt"], CLAUDE_PLAIN_PROMPT)
        self.assertEqual(sessions[0]["entrypoint"], "cli")
        self.assertEqual(sessions[0]["variants"], "cli, ide")

        sessions = self.run_json("latest", "--harness", "claude-code", "handoff")
        self.assertEqual(
            [session["ref"] for session in sessions], ["claude-code:c1a0de01"]
        )
        self.assertEqual(sessions[0]["title"], CLAUDE_TITLE_MAIN)
        self.assertEqual(sessions[0]["first_prompt"], CLAUDE_PROMPTS[0])
        self.assertEqual(sessions[0]["last_prompt"], CLAUDE_PROMPTS[-1])

        code, out, err = self.run_cli(
            "latest", "--harness", "claude-code", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_archive_flag_is_always_inactive(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "claude-code",
            "--include-archived",
            "--limit",
            "0",
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        for line in lines:
            self.assertEqual(line.split("\t")[-1], "-")

        data = self.show_json("claude-code:c1a0de01", "--messages", "0")
        self.assertFalse(data["archived"])

        code, out, err = self.run_cli("show", "claude-code:c1a0de01")
        self.assertEqual(code, 0, err)
        self.assertNotIn("- archived: yes", out)

    def test_deep_search_scans_content(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "claude-code", CLAUDE_DEEP_ONLY_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "claude-code", "--deep", CLAUDE_DEEP_ONLY_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("claude-code:c1a0de03", out)
        self.assertNotIn("c1a0de01", out)

        code, out, err = self.run_cli(
            "search", "--harness", "claude-code", "--deep", CLAUDE_TOOL_OUTPUT_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("claude-code:c1a0de01", out)
        self.assertNotIn("c1a0de03", out)

        for needle in ("Stale index entry", CLAUDE_HISTORY_PROMPT):
            code, out, err = self.run_cli(
                "search", "--harness", "claude-code", "--deep", needle
            )
            self.assertEqual(code, 0, err)
            self.assertIn("no sessions matched", out)

    def test_subagent_and_decoy_transcripts_are_excluded(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "claude-code",
            "--include-archived",
            "--deep",
            CLAUDE_SUBAGENT_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "claude-code",
            "--include-archived",
            "--deep",
            "claude-decoy-needle",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli("show", "claude-code:c1a0de05")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        subagent_path = (
            self.claude_home
            / "projects"
            / "-Users-example-project-alpha"
            / CLAUDE_MAIN
            / "subagents"
            / "agent-c1a0de05.jsonl"
        )
        code, out, err = self.run_cli("show", str(subagent_path))
        self.assertEqual(code, 2)
        self.assertIn("not a resumable session", err)

        decoy_path = (
            self.claude_home
            / "projects"
            / "-Users-example-project-alpha"
            / "agent-c1a0deff.jsonl"
        )
        code, out, err = self.run_cli("show", str(decoy_path))
        self.assertEqual(code, 2)
        self.assertIn("not a resumable session", err)

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli(
            "show", "claude-code:c1a0de01", "--messages", "6", "--chars", "120"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("# claude-code:c1a0de01", out)
        self.assertIn("- harness: claude-code (cli, ide)", out)
        self.assertIn("- cwd: `/Users/example/project-alpha`", out)
        self.assertIn("- branch: `feature/handoff`", out)
        self.assertIn("- turns: 6", out)
        self.assertIn("- model: `synthetic-claude-1`", out)
        self.assertIn("- version: `%s`" % CLAUDE_VERSION, out)
        self.assertIn("## Task", out)
        self.assertIn(CLAUDE_PROMPTS[0], out)
        self.assertIn("## Latest request", out)
        self.assertIn(CLAUDE_PROMPTS[-1], out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn("A previous turn asked to bound the handoff digest.", out)
        self.assertIn("## Todos (2 open / 3 total)", out)
        self.assertIn("[in_progress] Add prompt paging", out)
        self.assertIn("[pending] Update docs", out)
        self.assertIn("## Edited files", out)
        self.assertIn("src/handoff.ts` (x2)", out)
        self.assertIn("docs/handoff.md`", out)
        self.assertIn("notebooks/demo.ipynb`", out)
        self.assertIn("Edit x2", out)
        self.assertNotIn("- archived: yes", out)
        self.assertNotIn("<system-reminder>", out)
        self.assertNotIn("<task-notification>", out)
        self.assertNotIn("<local-command", out)
        self.assertNotIn("Caveat:", out)
        self.assertNotIn("/review", out)
        self.assertNotIn("[Request interrupted", out)
        self.assertNotIn("sidechain prompt", out)
        self.assertNotIn(CLAUDE_TOOL_OUTPUT_NEEDLE, out)
        self.assertNotIn("Old todo from transcript", out)
        self.assertNotIn(CLAUDE_HISTORY_PROMPT, out)
        self.assertNotIn("Stale index", out)

    def test_show_json_fields(self) -> None:
        data = self.show_json("claude-code:c1a0de01", "--messages", "0")
        self.assertEqual(data["ref"], "claude-code:c1a0de01")
        self.assertEqual(data["session_id"], CLAUDE_MAIN)
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertEqual(data["entrypoint"], "cli")
        self.assertEqual(data["variants"], "cli, ide")
        self.assertEqual(data["branch"], "feature/handoff")
        self.assertEqual(data["version"], CLAUDE_VERSION)
        self.assertEqual(data["model"], "synthetic-claude-1")
        self.assertGreater(data["size_bytes"], 0)
        self.assertFalse(data["archived"])
        self.assertEqual(data["started"], "2026-10-20T09:10:00Z")
        self.assertEqual(data["updated"], "2026-10-20T10:08:00Z")
        self.assertEqual(data["title"], CLAUDE_TITLE_MAIN)
        self.assertEqual(data["compact_summary"], CLAUDE_COMPACT_SUMMARY)
        self.assertEqual(data["first_prompt"], CLAUDE_PROMPTS[0])
        self.assertEqual(data["last_prompt"], CLAUDE_PROMPTS[-1])
        self.assertEqual(data["turn_count"], 6)
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
                    "path": "/Users/example/project-alpha/src/handoff.ts",
                    "count": 2,
                },
                {
                    "path": "/Users/example/project-alpha/docs/handoff.md",
                    "count": 1,
                },
                {
                    "path": "/Users/example/project-alpha/notebooks/demo.ipynb",
                    "count": 1,
                },
            ],
        )
        self.assertEqual(
            data["tool_counts"],
            {
                "Edit": 2,
                "Read": 1,
                "Write": 1,
                "NotebookEdit": 1,
                "Bash": 1,
                "TodoWrite": 1,
            },
        )
        self.assertEqual(
            data["path"],
            str(
                self.claude_home
                / "projects"
                / "-Users-example-project-alpha"
                / (CLAUDE_MAIN + ".jsonl")
            ),
        )

    def test_show_aux_session_title_and_todos_fallback(self) -> None:
        data = self.show_json("claude-code:c1a0de02", "--messages", "0")
        self.assertEqual(data["session_id"], CLAUDE_AUX)
        self.assertEqual(data["entrypoint"], "claude-vscode")
        self.assertEqual(data["title"], CLAUDE_PROMPTS_AUX[0])
        self.assertEqual(data["first_prompt"], CLAUDE_PROMPTS_AUX[0])
        self.assertEqual(data["last_prompt"], CLAUDE_PROMPTS_AUX[1])
        self.assertEqual(data["turn_count"], 2)
        self.assertFalse(data["archived"])
        self.assertEqual(
            data["todos"],
            [
                {"subject": "Draft migration notes", "status": "completed"},
                {"subject": "Verify notes", "status": "in_progress"},
            ],
        )

        code, out, err = self.run_cli("show", "claude-code:c1a0de02")
        self.assertEqual(code, 0, err)
        self.assertIn("## Todos (1 open / 2 total)", out)
        self.assertIn("[in_progress] Verify notes", out)

    def test_show_compacted_session(self) -> None:
        code, out, err = self.run_cli("show", "claude-code:c1a0de04")
        self.assertEqual(code, 0, err)
        self.assertIn("- turns: 2", out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn(CLAUDE_COMPACT_SESSION_SUMMARY, out)
        self.assertNotIn("An earlier compact summary", out)

        data = self.show_json("claude-code:c1a0de04", "--messages", "0")
        self.assertEqual(data["compact_summary"], CLAUDE_COMPACT_SESSION_SUMMARY)
        self.assertEqual(data["first_prompt"], "Plan the migration.")
        self.assertEqual(data["last_prompt"], CLAUDE_COMPACT_RESUME_PROMPT)
        self.assertEqual(data["turn_count"], 2)

        prompts = self.run_json("prompts", "claude-code:c1a0de04", "--limit", "0")
        self.assertEqual(prompts["total"], 2)
        self.assertEqual(
            [prompt["text"] for prompt in prompts["prompts"]],
            ["Plan the migration.", CLAUDE_COMPACT_RESUME_PROMPT],
        )

    def test_show_by_source_path(self) -> None:
        data = self.show_json("claude-code:c1a0de01", "--messages", "0")
        source = data["path"]

        code, out, err = self.run_cli("show", source)
        self.assertEqual(code, 0, err)
        self.assertIn("# claude-code:c1a0de01", out)

        code, out, err = self.run_cli("prompts", source, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "6")

    def test_show_missing_ambiguous_and_too_short_refs(self) -> None:
        code, out, err = self.run_cli("show", "claude-code:c1a0deff")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "claude-code:c1a0de0")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", err)

        code, out, err = self.run_cli("show", "claude-code:c1a")
        self.assertEqual(code, 2)
        self.assertIn("too short", err)

        code, out, err = self.run_cli("show", "c1a0de03")
        self.assertEqual(code, 0, err)
        self.assertIn("# claude-code:c1a0de03", out)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli("prompts", "claude-code:c1a0de01", "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "6")

        code, out, err = self.run_cli("prompts", "claude-code:c1a0de01")
        self.assertEqual(code, 0, err)
        for index, prompt in enumerate(CLAUDE_PROMPTS, 1):
            self.assertIn("## %d" % index, out)
            self.assertIn(prompt, out)

        code, out, err = self.run_cli(
            "prompts", "claude-code:c1a0de01", "--offset", "1", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("## 2", out)
        self.assertNotIn(CLAUDE_PROMPTS[0], out)
        self.assertIn("next: --offset 2 --limit 1", out)

        code, out, err = self.run_cli(
            "prompts", "claude-code:c1a0de01", "--order", "newest", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("## 6"), out.index("## 5"))
        self.assertNotIn("## 1", out)

        code, out, err = self.run_cli(
            "prompts", "claude-code:c1a0de01", "--offset", "9"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts", "claude-code:c1a0de01", "--limit", "1", "--chars", "10"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Please re…", out)
        self.assertNotIn(CLAUDE_PROMPTS[0], out)

    def test_prompts_json(self) -> None:
        data = self.run_json("prompts", "claude-code:c1a0de01", "--limit", "2")
        self.assertEqual(data["ref"], "claude-code:c1a0de01")
        self.assertEqual(data["session_id"], CLAUDE_MAIN)
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertFalse(data["archived"])
        self.assertEqual(data["total"], 6)
        self.assertEqual(data["returned"], 2)
        self.assertTrue(data["has_more"])
        self.assertEqual([prompt["index"] for prompt in data["prompts"]], [1, 2])
        self.assertEqual(data["prompts"][0]["text"], CLAUDE_PROMPTS[0])
        self.assertIsNotNone(data["prompts"][0]["timestamp"])

    def test_non_human_records_never_become_prompts(self) -> None:
        prompts = self.run_json("prompts", "claude-code:c1a0de01", "--limit", "0")
        texts = [prompt["text"] for prompt in prompts["prompts"]]
        self.assertEqual(texts, list(CLAUDE_PROMPTS))
        self.assertEqual(texts.count(CLAUDE_PROMPTS[0]), 1)
        self.assertEqual(texts[3], "Tighten the digest tests.")
        for text in texts:
            self.assertNotIn("<system-reminder>", text)
            self.assertNotIn("<task-notification>", text)
            self.assertNotIn("<local-command", text)
            self.assertNotIn("Caveat:", text)
        for excluded in (
            "sidechain prompt must not count",
            "[Request interrupted",
            "/review",
            "# AGENTS.md",
            "<bash-input>",
            "Old todo from transcript",
        ):
            self.assertFalse(
                any(excluded in text for text in texts), excluded
            )
        self.assertNotIn(CLAUDE_TOOL_OUTPUT_NEEDLE, texts)

    def test_cross_harness_isolation(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "codex", "claude-main-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "claude-code", "main-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        sessions = self.run_json("search", "claude-main-needle", "--limit", "0")
        self.assertEqual(
            {session["ref"] for session in sessions}, {"claude-code:c1a0de01"}
        )

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "claude-code",
            "--include-archived",
            "--deep",
            CLAUDE_SUBAGENT_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_empty_store_is_safe(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "claude-code",
            claude_home=self.empty_claude_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "latest",
            "--harness",
            "claude-code",
            claude_home=self.empty_claude_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_commands_do_not_modify_claude_store(self) -> None:
        def snapshot() -> dict:
            files = {}
            for path in self.claude_home.rglob("*"):
                if path.is_file():
                    files[str(path)] = (
                        path.read_bytes(),
                        path.stat().st_mtime_ns,
                    )
            return files

        before = snapshot()
        self.run_cli("search", "--harness", "claude-code")
        self.run_cli("search", "--harness", "claude-code", "--include-archived")
        self.run_cli(
            "search", "--harness", "claude-code", "--deep", CLAUDE_DEEP_ONLY_NEEDLE
        )
        self.run_cli("latest", "--harness", "claude-code")
        self.run_cli("show", "claude-code:c1a0de01")
        self.run_cli("show", "claude-code:c1a0de02")
        self.run_cli("show", "claude-code:c1a0de04", "--format", "json")
        self.run_cli("prompts", "claude-code:c1a0de01")
        self.run_cli("prompts", "claude-code:c1a0de01", "--count")
        self.assertEqual(snapshot(), before)
        self.assertFalse(
            any(
                path.name.endswith(("-wal", "-shm", "-journal"))
                for path in self.claude_home.rglob("*")
            )
        )

    def test_fixture_data_is_synthetic(self) -> None:
        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        for path in self.claude_home.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8", "ignore")
            self.assertNotIn(str(Path.home()), text)
            self.assertNotIn("/Volumes/", text)
            self.assertNotIn("/home/", text)
            self.assertNotIn("/Users/", text.replace("/Users/example/", ""))
            self.assertIsNone(email.search(text), str(path))
            self.assertNotIn("01a1", text)
        for session_id in (
            CLAUDE_MAIN,
            CLAUDE_AUX,
            CLAUDE_PLAIN,
            CLAUDE_COMPACT,
        ):
            self.assertTrue(session_id.startswith("c1a0de"), session_id)
