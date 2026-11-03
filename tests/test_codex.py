from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from cli_support import FixtureTestCase
from codex_fixture import (
    HAS_ZSTD as CODEX_HAS_ZSTD,
    INDEX_TITLE_MAIN as CODEX_INDEX_TITLE_MAIN,
    PROMPTS_MAIN as CODEX_PROMPTS,
    PROMPTS_RESUMED as CODEX_PROMPTS_RESUMED,
    PROMPT_ARCHIVED as CODEX_ARCHIVED_PROMPT,
    PROMPT_PLAIN as CODEX_PLAIN_PROMPT,
    PROMPT_ZSTD as CODEX_ZSTD_PROMPT,
    RESUMED_COMPACT_SUMMARY as CODEX_RESUMED_COMPACT,
    SESSION_ARCHIVED as CODEX_ARCHIVED,
    SESSION_MAIN as CODEX_MAIN,
    SESSION_PLAIN as CODEX_PLAIN,
    SESSION_RESUMED as CODEX_RESUMED,
    SESSION_SUBAGENT as CODEX_SUBAGENT,
    SESSION_ZSTD as CODEX_ZSTD,
    VERSION_MAIN as CODEX_VERSION,
)


class CodexTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli("show", *args, "--format", "json", **kwargs)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_harness_row(self) -> None:
        rows = self.run_json("harnesses")
        rows = [row for row in rows if row["name"] == "codex"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "ready")
        self.assertEqual(rows[0]["variants"], "desktop, ide, cli")
        self.assertEqual(rows[0]["store"], "~/.codex")
        self.assertEqual(rows[0]["aliases"], "codex, chatgpt-codex")

    def test_lists_active_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "codex")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("codex:c0de0004"))
        self.assertTrue(lines[1].startswith("codex:c0de0002"))
        self.assertTrue(lines[2].startswith("codex:c0de0001"))
        self.assertNotIn("c0de0005", out)
        self.assertNotIn("c0de0006", out)

    def test_aliases(self) -> None:
        for alias in ("codex", "chatgpt-codex"):
            sessions = self.run_json("search", "--harness", alias, "--limit", "0")
            self.assertEqual(len(sessions), 3)
            self.assertTrue(
                all(session["ref"].startswith("codex:") for session in sessions)
            )

    def test_keyword_id_cwd_since_limit_and_no_match(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "codex", "handoff")
        self.assertEqual(code, 0, err)
        self.assertIn("codex:c0de0001", out)
        self.assertNotIn("c0de0004", out)

        sessions = self.run_json("search", "--harness", "codex", "c0de0004")
        self.assertEqual(
            [session["ref"] for session in sessions], ["codex:c0de0004"]
        )

        sessions = self.run_json(
            "search",
            "--harness",
            "codex",
            "--deep",
            "继续",
            "--limit",
            "0",
        )
        self.assertEqual(
            {session["ref"] for session in sessions},
            {"codex:c0de0001", "codex:c0de0002"},
        )

        code, out, err = self.run_cli(
            "search", "--harness", "codex", "--cwd", "/Users/example/project-alpha"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codex:c0de0001", out)
        self.assertNotIn("c0de0002", out)

        code, out, err = self.run_cli(
            "search", "--harness", "codex", "--cwd", "/Users/example"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codex:c0de0001", out)
        self.assertIn("codex:c0de0002", out)
        self.assertIn("codex:c0de0004", out)

        code, out, err = self.run_cli(
            "search", "--harness", "codex", "--since", "2026-10-24"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codex:c0de0004", out)
        self.assertIn("codex:c0de0002", out)
        self.assertNotIn("c0de0001", out)

        code, out, err = self.run_cli(
            "search", "--harness", "codex", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

        code, out, err = self.run_cli(
            "search", "--harness", "codex", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_latest_and_query_filter(self) -> None:
        sessions = self.run_json("latest", "--harness", "codex")
        self.assertEqual(
            [session["ref"] for session in sessions], ["codex:c0de0004"]
        )
        self.assertEqual(sessions[0]["title"], CODEX_PLAIN_PROMPT)
        self.assertEqual(sessions[0]["first_prompt"], CODEX_PLAIN_PROMPT)
        self.assertEqual(sessions[0]["last_prompt"], CODEX_PLAIN_PROMPT)
        self.assertEqual(sessions[0]["entrypoint"], "cli")
        self.assertEqual(sessions[0]["variants"], "desktop, ide, cli")

        sessions = self.run_json("latest", "--harness", "codex", "handoff")
        self.assertEqual(
            [session["ref"] for session in sessions], ["codex:c0de0001"]
        )
        self.assertEqual(sessions[0]["title"], CODEX_INDEX_TITLE_MAIN)
        self.assertEqual(sessions[0]["first_prompt"], CODEX_PROMPTS[0])
        self.assertEqual(sessions[0]["last_prompt"], CODEX_PROMPTS[-1])

        code, out, err = self.run_cli(
            "latest", "--harness", "codex", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_archived_is_hidden_by_default(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "codex", "--include-archived", "--limit", "0"
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        marks = {
            parts[0]: parts[-1] for parts in (line.split("\t") for line in lines)
        }
        self.assertEqual(
            marks,
            {
                "codex:c0de0004": "-",
                "codex:c0de0002": "-",
                "codex:c0de0006": "yes",
                "codex:c0de0001": "-",
            },
        )

    def test_deep_search_scans_content(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "codex", "deep-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "codex", "--deep", "deep-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codex:c0de0004", out)
        self.assertNotIn("c0de0001", out)

        code, out, err = self.run_cli(
            "search", "--harness", "codex", "--deep", "tool-output-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codex:c0de0001", out)
        self.assertNotIn("c0de0004", out)

        code, out, err = self.run_cli(
            "search", "--harness", "codex", "--deep", "Legacy history entry"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "codex", "--deep", "Abandoned rewrite attempt."
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "codex", "--deep", "Drafted the plan."
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_deep_search_respects_archive_and_subagent(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "codex", "--deep", "archived-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "codex",
            "--include-archived",
            "--deep",
            "archived-needle",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codex:c0de0006", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "codex",
            "--include-archived",
            "--deep",
            "subagent-only-needle",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli(
            "show", "codex:c0de0001", "--messages", "6", "--chars", "120"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("# codex:c0de0001", out)
        self.assertIn("- harness: codex (desktop, ide, cli)", out)
        self.assertIn("- cwd: `/Users/example/project-alpha`", out)
        self.assertIn("- branch: `feature/handoff`", out)
        self.assertIn("- turns: 6", out)
        self.assertIn("- model: `synthetic-model-1`", out)
        self.assertIn("- version: `%s`" % CODEX_VERSION, out)
        self.assertIn("## Task", out)
        self.assertIn(CODEX_PROMPTS[0], out)
        self.assertIn("## Latest request", out)
        self.assertIn(CODEX_PROMPTS[-1], out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn(
            "A previous turn asked to bound the handoff digest.",
            out,
        )
        self.assertIn("## Edited files", out)
        self.assertIn("src/handoff.ts` (x2)", out)
        self.assertIn("docs/handoff.md`", out)
        self.assertIn("apply_patch", out)
        self.assertNotIn("## Todos", out)
        self.assertNotIn("# AGENTS.md instructions", out)
        self.assertNotIn("<environment_context>", out)
        self.assertNotIn("<in-app-browser-context", out)
        self.assertNotIn("<task-notification>", out)
        self.assertNotIn("## My request for Codex:", out)
        self.assertNotIn("This must not become a prompt.", out)
        self.assertNotIn("/review", out)
        self.assertNotIn("truncated prompt", out)

    def test_show_json_fields(self) -> None:
        data = self.show_json("codex:c0de0001", "--messages", "0")
        self.assertEqual(data["ref"], "codex:c0de0001")
        self.assertEqual(data["session_id"], CODEX_MAIN)
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertEqual(data["entrypoint"], "desktop")
        self.assertEqual(data["variants"], "desktop, ide, cli")
        self.assertEqual(data["branch"], "feature/handoff")
        self.assertEqual(data["version"], CODEX_VERSION)
        self.assertEqual(data["model"], "synthetic-model-1")
        self.assertGreater(data["size_bytes"], 0)
        self.assertFalse(data["archived"])
        self.assertIn(
            "A previous turn asked to bound the handoff digest.",
            data["compact_summary"],
        )
        self.assertEqual(data["first_prompt"], CODEX_PROMPTS[0])
        self.assertEqual(data["last_prompt"], CODEX_PROMPTS[-1])
        self.assertEqual(data["turn_count"], 6)
        self.assertEqual(data["todos"], [])
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
            ],
        )
        self.assertEqual(
            data["tool_counts"], {"apply_patch": 2, "shell": 1}
        )
        self.assertEqual(
            data["path"],
            str(
                self.codex_home
                / "sessions"
                / "2026"
                / "10"
                / "20"
                / (
                    "rollout-2026-10-20T09-10-05-%s.jsonl" % CODEX_MAIN
                )
            ),
        )

    def test_show_by_source_path(self) -> None:
        data = self.show_json("codex:c0de0001", "--messages", "0")
        source = data["path"]

        code, out, err = self.run_cli("show", source)
        self.assertEqual(code, 0, err)
        self.assertIn("# codex:c0de0001", out)

        code, out, err = self.run_cli("prompts", source, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "6")

    def test_show_archived_session(self) -> None:
        code, out, err = self.run_cli("show", "codex:c0de0006")
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)
        self.assertIn("- branch: `release/1.0`", out)

        data = self.show_json("codex:c0de0006")
        self.assertTrue(data["archived"])
        self.assertEqual(data["title"], "Archived rollout notes")

        code, out, err = self.run_cli("show", data["path"])
        self.assertEqual(code, 0, err)
        self.assertIn("# codex:c0de0006", out)

    def test_show_missing_ambiguous_and_too_short_refs(self) -> None:
        code, out, err = self.run_cli("show", "codex:c0de000f")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "codex:c0de000")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", err)

        code, out, err = self.run_cli("show", "codex:c0d")
        self.assertEqual(code, 2)
        self.assertIn("too short", err)

    def test_show_resumed_thread_chains_segments(self) -> None:
        code, out, err = self.run_cli("show", "codex:c0de0002")
        self.assertEqual(code, 0, err)
        self.assertIn("- turns: 3", out)
        self.assertIn("- cwd: `/Users/example/project-resume`", out)
        self.assertIn("- branch: `dev`", out)
        self.assertIn("- model: `synthetic-model-2`", out)
        self.assertIn("## Task", out)
        self.assertIn(CODEX_PROMPTS_RESUMED[0], out)
        self.assertIn("## Latest request", out)
        self.assertIn(CODEX_PROMPTS_RESUMED[-1], out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn(CODEX_RESUMED_COMPACT, out)
        self.assertNotIn("Abandoned", out)

        data = self.show_json("codex:c0de0002", "--messages", "0")
        self.assertTrue(data["started"].startswith("2026-09-28"))
        self.assertTrue(data["updated"].startswith("2026-10-25"))
        self.assertEqual(data["first_prompt"], CODEX_PROMPTS_RESUMED[0])
        self.assertEqual(data["last_prompt"], CODEX_PROMPTS_RESUMED[-1])

        prompts = self.run_json("prompts", "codex:c0de0002", "--limit", "0")
        self.assertEqual(
            [prompt["text"] for prompt in prompts["prompts"]],
            list(CODEX_PROMPTS_RESUMED),
        )

    def test_subagent_thread_is_excluded(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "codex", "--include-archived", "--limit", "0"
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn("c0de0005", out)

        code, out, err = self.run_cli("show", "codex:c0de0005")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli("prompts", "codex:c0de0001", "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "6")

        code, out, err = self.run_cli("prompts", "codex:c0de0001")
        self.assertEqual(code, 0, err)
        for index, prompt in enumerate(CODEX_PROMPTS, 1):
            self.assertIn("## %d" % index, out)
            self.assertIn(prompt, out)

        code, out, err = self.run_cli(
            "prompts", "codex:c0de0001", "--offset", "1", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("## 2", out)
        self.assertNotIn(CODEX_PROMPTS[0], out)
        self.assertIn("next: --offset 2 --limit 1", out)

        code, out, err = self.run_cli(
            "prompts", "codex:c0de0001", "--order", "newest", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("## 6"), out.index("## 5"))
        self.assertNotIn("## 1", out)

        code, out, err = self.run_cli(
            "prompts", "codex:c0de0001", "--offset", "9"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts", "codex:c0de0001", "--limit", "1", "--chars", "10"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Please re…", out)
        self.assertNotIn(CODEX_PROMPTS[0], out)

    def test_prompts_json_and_archived(self) -> None:
        data = self.run_json("prompts", "codex:c0de0001", "--limit", "2")
        self.assertEqual(data["ref"], "codex:c0de0001")
        self.assertEqual(data["session_id"], CODEX_MAIN)
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertFalse(data["archived"])
        self.assertEqual(data["total"], 6)
        self.assertEqual(data["returned"], 2)
        self.assertTrue(data["has_more"])
        self.assertEqual([prompt["index"] for prompt in data["prompts"]], [1, 2])
        self.assertEqual(data["prompts"][0]["text"], CODEX_PROMPTS[0])
        self.assertIsNotNone(data["prompts"][0]["timestamp"])

        data = self.run_json("prompts", "codex:c0de0006", "--count")
        self.assertTrue(data["archived"])
        self.assertEqual(data["total"], 1)

    def test_non_human_records_never_become_prompts(self) -> None:
        prompts = self.run_json(
            "prompts", "codex:c0de0001", "--limit", "0"
        )
        texts = [prompt["text"] for prompt in prompts["prompts"]]
        self.assertEqual(texts, list(CODEX_PROMPTS))
        self.assertEqual(texts.count(CODEX_PROMPTS[0]), 1)
        for text in texts:
            self.assertNotIn("<environment_context>", text)
            self.assertNotIn("<task-notification>", text)
            self.assertNotIn("<in-app-browser-context", text)
            self.assertNotIn("## My request for Codex:", text)
            self.assertNotIn("# Browser comments:", text)
        self.assertNotIn("This must not become a prompt.", texts)
        self.assertNotIn("/review", texts)
        self.assertNotIn("truncated prompt", texts)

    def test_archived_session_prompts(self) -> None:
        prompts = self.run_json("prompts", "codex:c0de0006", "--limit", "0")
        self.assertEqual(
            [prompt["text"] for prompt in prompts["prompts"]],
            [CODEX_ARCHIVED_PROMPT],
        )

    def test_empty_store_is_safe(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "codex",
            codex_home=self.empty_codex_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "latest",
            "--harness",
            "codex",
            codex_home=self.empty_codex_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_commands_do_not_modify_codex_store(self) -> None:
        def snapshot() -> dict:
            files = {}
            for path in self.codex_home.rglob("*"):
                if path.is_file():
                    files[str(path)] = (
                        path.read_bytes(),
                        path.stat().st_mtime_ns,
                    )
            return files

        before = snapshot()
        self.run_cli("search", "--harness", "codex")
        self.run_cli("search", "--harness", "codex", "--include-archived")
        self.run_cli("search", "--harness", "codex", "--deep", "deep-only-needle")
        self.run_cli("latest", "--harness", "codex")
        self.run_cli("show", "codex:c0de0001")
        self.run_cli("show", "codex:c0de0002")
        self.run_cli("show", "codex:c0de0006", "--format", "json")
        self.run_cli("prompts", "codex:c0de0001")
        self.run_cli("prompts", "codex:c0de0001", "--count")
        self.assertEqual(snapshot(), before)
        self.assertFalse(
            any(
                path.name.endswith(("-wal", "-shm", "-journal"))
                for path in self.codex_home.rglob("*")
            )
        )

    def test_fixture_data_is_synthetic(self) -> None:
        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        for path in self.codex_home.rglob("*"):
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
            CODEX_MAIN,
            CODEX_RESUMED,
            CODEX_PLAIN,
            CODEX_SUBAGENT,
            CODEX_ARCHIVED,
        ):
            self.assertTrue(session_id.startswith("c0de00"), session_id)

    @unittest.skipUnless(CODEX_HAS_ZSTD, "needs a zstd decoder")
    def test_zstd_rollout_is_readable(self) -> None:
        home = self.codex_zstd_home
        files = [path for path in home.rglob("*") if path.is_file()]
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].name.endswith(".jsonl.zst"))

        def snapshot() -> dict:
            return {
                str(path): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in home.rglob("*")
                if path.is_file()
            }

        before = snapshot()
        sessions = self.run_json(
            "search", "--harness", "codex", "--limit", "0", codex_home=home
        )
        self.assertEqual([session["ref"] for session in sessions], ["codex:c0de0007"])
        self.assertGreater(sessions[0]["size_bytes"], 0)
        self.assertEqual(sessions[0]["title"], CODEX_ZSTD_PROMPT)

        data = self.show_json("codex:c0de0007", "--messages", "0", codex_home=home)
        self.assertEqual(data["session_id"], CODEX_ZSTD)
        self.assertEqual(data["first_prompt"], CODEX_ZSTD_PROMPT)

        prompts = self.run_json(
            "prompts", "codex:c0de0007", "--limit", "0", codex_home=home
        )
        self.assertEqual(
            [prompt["text"] for prompt in prompts["prompts"]],
            [CODEX_ZSTD_PROMPT],
        )

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "codex",
            "--deep",
            "zstd-only-needle",
            codex_home=home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codex:c0de0007", out)

        self.assertEqual(snapshot(), before)
