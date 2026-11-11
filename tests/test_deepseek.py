from __future__ import annotations

import json
import re

from cli_support import FixtureTestCase
from deepseek_fixture import (
    COMPACT_SUMMARY as DEEPSEEK_COMPACT_SUMMARY,
    MODEL_ALT as DEEPSEEK_MODEL_ALT,
    NEEDLE_ARCHIVED as DEEPSEEK_ARCHIVED_NEEDLE,
    NEEDLE_DEEP_ONLY as DEEPSEEK_DEEP_ONLY_NEEDLE,
    NEEDLE_SUBAGENT as DEEPSEEK_SUBAGENT_NEEDLE,
    NEEDLE_TOOL_OUTPUT as DEEPSEEK_TOOL_OUTPUT_NEEDLE,
    PROJECT_ALPHA as DEEPSEEK_PROJECT_ALPHA,
    PROJECT_BETA as DEEPSEEK_PROJECT_BETA,
    PROMPTS_MAIN as DEEPSEEK_PROMPTS,
    PROMPT_ARCHIVED as DEEPSEEK_ARCHIVED_PROMPT,
    PROMPT_IMAGE_ONLY as DEEPSEEK_IMAGE_ONLY_PROMPT,
    PROMPT_MULTI as DEEPSEEK_MULTI_PROMPT,
    PROMPT_MULTI_ABANDONED as DEEPSEEK_ABANDONED_PROMPT,
    PROMPT_PLAIN as DEEPSEEK_PLAIN_PROMPT,
    PROMPT_SUBAGENT as DEEPSEEK_SUBAGENT_PROMPT,
    SESSION_ARCHIVED as DEEPSEEK_ARCHIVED,
    SESSION_EMPTY as DEEPSEEK_EMPTY,
    SESSION_MAIN as DEEPSEEK_MAIN,
    SESSION_MULTI as DEEPSEEK_MULTI,
    SESSION_PLAIN as DEEPSEEK_PLAIN,
    SESSION_SUBAGENT as DEEPSEEK_SUBAGENT,
    TITLE_ARCHIVED as DEEPSEEK_TITLE_ARCHIVED,
    TITLE_MULTI as DEEPSEEK_TITLE_MULTI,
    TODOS_LATEST as DEEPSEEK_TODOS,
    decompress as deepseek_decompress,
)


class DeepSeekTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli("show", *args, "--format", "json", **kwargs)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_harness_row(self) -> None:
        rows = self.run_json("harnesses")
        rows = [row for row in rows if row["name"] == "deepseek"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "ready")
        self.assertEqual(rows[0]["variants"], "desktop")
        self.assertEqual(rows[0]["store"], "~/.dsh")
        self.assertEqual(
            rows[0]["aliases"], "deepseek, deepseek-harness, dsh"
        )

    def test_lists_active_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "deepseek")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("deepseek:d5ee0003"))
        self.assertTrue(lines[1].startswith("deepseek:d5ee0006"))
        self.assertTrue(lines[2].startswith("deepseek:d5ee0004"))
        self.assertTrue(lines[3].startswith("deepseek:d5ee0001"))
        self.assertNotIn("d5ee0002", out)
        self.assertNotIn("d5ee0005", out)

    def test_aliases(self) -> None:
        for alias in ("deepseek", "deepseek-harness", "dsh"):
            sessions = self.run_json(
                "search", "--harness", alias, "--limit", "0"
            )
            self.assertEqual(len(sessions), 4)
            self.assertTrue(
                all(session["ref"].startswith("deepseek:") for session in sessions)
            )

    def test_keyword_id_cwd_since_limit_and_no_match(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "deepseek", "handoff")
        self.assertEqual(code, 0, err)
        self.assertIn("deepseek:d5ee0001", out)
        self.assertNotIn("d5ee0003", out)

        sessions = self.run_json("search", "--harness", "deepseek", "d5ee0003")
        self.assertEqual(
            [session["ref"] for session in sessions], ["deepseek:d5ee0003"]
        )

        code, out, err = self.run_cli(
            "search", "--harness", "deepseek", "--cwd", DEEPSEEK_PROJECT_ALPHA
        )
        self.assertEqual(code, 0, err)
        self.assertIn("deepseek:d5ee0001", out)
        self.assertIn("deepseek:d5ee0006", out)
        self.assertNotIn("d5ee0003", out)

        code, out, err = self.run_cli(
            "search", "--harness", "deepseek", "--cwd", "/Users/example"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("deepseek:d5ee0004", out)
        self.assertIn("deepseek:d5ee0006", out)

        code, out, err = self.run_cli(
            "search", "--harness", "deepseek", "--since", "2026-10-25"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("deepseek:d5ee0003", out)
        self.assertIn("deepseek:d5ee0006", out)
        self.assertIn("deepseek:d5ee0004", out)
        self.assertNotIn("d5ee0001", out)

        code, out, err = self.run_cli(
            "search", "--harness", "deepseek", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

        code, out, err = self.run_cli(
            "search", "--harness", "deepseek", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_latest_and_query_filter(self) -> None:
        sessions = self.run_json("latest", "--harness", "deepseek")
        self.assertEqual(
            [session["ref"] for session in sessions], ["deepseek:d5ee0003"]
        )
        self.assertEqual(sessions[0]["title"], DEEPSEEK_PLAIN_PROMPT)
        self.assertEqual(sessions[0]["first_prompt"], DEEPSEEK_PLAIN_PROMPT)
        self.assertEqual(sessions[0]["last_prompt"], DEEPSEEK_PLAIN_PROMPT)
        self.assertEqual(sessions[0]["entrypoint"], "desktop")
        self.assertEqual(sessions[0]["variants"], "desktop")

        sessions = self.run_json("latest", "--harness", "deepseek", "bounded")
        self.assertEqual(
            [session["ref"] for session in sessions], ["deepseek:d5ee0004"]
        )
        self.assertEqual(sessions[0]["title"], DEEPSEEK_TITLE_MULTI)

        code, out, err = self.run_cli(
            "latest", "--harness", "deepseek", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_archived_is_hidden_by_default(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "deepseek", "--include-archived", "--limit", "0"
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        marks = {
            parts[0]: parts[-1] for parts in (line.split("\t") for line in lines)
        }
        self.assertEqual(
            marks,
            {
                "deepseek:d5ee0003": "-",
                "deepseek:d5ee0006": "-",
                "deepseek:d5ee0004": "-",
                "deepseek:d5ee0002": "yes",
                "deepseek:d5ee0001": "-",
            },
        )

    def test_deep_search_scans_content(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "deepseek", DEEPSEEK_DEEP_ONLY_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "deepseek", "--deep", DEEPSEEK_DEEP_ONLY_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("deepseek:d5ee0003", out)
        self.assertNotIn("d5ee0001", out)

        code, out, err = self.run_cli(
            "search", "--harness", "deepseek", "--deep", DEEPSEEK_TOOL_OUTPUT_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("deepseek:d5ee0001", out)
        self.assertNotIn("d5ee0003", out)

        code, out, err = self.run_cli(
            "search", "--harness", "deepseek", "--deep", DEEPSEEK_ABANDONED_PROMPT
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "deepseek", "--deep", "Drafted the plan."
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_deep_search_respects_archive_and_subagent(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "deepseek", "--deep", DEEPSEEK_ARCHIVED_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "deepseek",
            "--include-archived",
            "--deep",
            DEEPSEEK_ARCHIVED_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("deepseek:d5ee0002", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "deepseek",
            "--include-archived",
            "--deep",
            DEEPSEEK_SUBAGENT_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_v4_transcript_is_authoritative(self) -> None:
        data = self.show_json("deepseek:d5ee0004", "--messages", "0")
        self.assertEqual(data["title"], DEEPSEEK_TITLE_MULTI)
        self.assertEqual(data["cwd"], DEEPSEEK_PROJECT_BETA)
        self.assertEqual(data["model"], DEEPSEEK_MODEL_ALT)
        self.assertEqual(data["first_prompt"], DEEPSEEK_MULTI_PROMPT)
        self.assertEqual(data["turn_count"], 1)
        self.assertTrue(data["path"].endswith("session.v4.jsonl.zstd"))
        self.assertIn(
            "session-%s" % DEEPSEEK_MULTI, data["path"]
        )

        prompts = self.run_json("prompts", "deepseek:d5ee0004", "--limit", "0")
        self.assertEqual(
            [prompt["text"] for prompt in prompts["prompts"]],
            [DEEPSEEK_MULTI_PROMPT],
        )

    def test_legacy_unversioned_transcript(self) -> None:
        code, out, err = self.run_cli(
            "show", "deepseek:d5ee0003", "--messages", "3", "--chars", "200"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("## Task", out)
        self.assertIn(DEEPSEEK_PLAIN_PROMPT, out)
        self.assertIn("API error: quota exceeded.", out)
        self.assertNotIn("## Compact summary", out)

        data = self.show_json("deepseek:d5ee0003", "--messages", "0")
        self.assertTrue(data["path"].endswith("session.jsonl.zstd"))
        self.assertEqual(data["model"], "example-deepseek-model-3")
        self.assertEqual(data["turn_count"], 1)

    def test_metadata_only_session(self) -> None:
        code, out, err = self.run_cli("show", "deepseek:d5ee0006")
        self.assertEqual(code, 0, err)
        self.assertIn("# deepseek:d5ee0006", out)
        self.assertIn("- turns: 0", out)
        self.assertNotIn("## Task", out)
        self.assertNotIn("## Recent turns", out)

        data = self.show_json("deepseek:d5ee0006", "--messages", "0")
        self.assertEqual(data["title"], DEEPSEEK_EMPTY)
        self.assertEqual(data["turn_count"], 0)
        self.assertEqual(data["todos"], [])
        self.assertEqual(data["edited_files"], [])

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli(
            "show", "deepseek:d5ee0001", "--messages", "2", "--chars", "200"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("# deepseek:d5ee0001", out)
        self.assertIn("- harness: deepseek (desktop)", out)
        self.assertIn("- cwd: `%s`" % (DEEPSEEK_PROJECT_ALPHA + "/packages"), out)
        self.assertIn("- turns: 4", out)
        self.assertIn("- model: `%s`" % DEEPSEEK_MODEL_ALT, out)
        self.assertIn("## Task", out)
        self.assertIn(DEEPSEEK_PROMPTS[0], out)
        self.assertIn("## Latest request", out)
        self.assertIn(DEEPSEEK_PROMPTS[-1], out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn(DEEPSEEK_COMPACT_SUMMARY, out)
        self.assertIn("## Todos (1 open / 3 total)", out)
        self.assertIn("- [pending] Update the handoff docs", out)
        self.assertNotIn("- [completed] Refactor the digest", out)
        self.assertIn("## Edited files", out)
        self.assertIn("src/digest.py` (x2)", out)
        self.assertIn("docs/handoff.md`", out)
        self.assertIn("## Recent tools", out)
        self.assertIn("bash: sed -n", out)
        self.assertIn("edit: src/digest.py", out)
        self.assertIn("write: docs/handoff.md", out)
        self.assertNotIn("Injected agent instructions", out)
        self.assertNotIn("Injected runtime context", out)
        self.assertNotIn("Injected tool-job context", out)
        self.assertNotIn("Synthetic system note.", out)
        self.assertNotIn("Synthetic developer note.", out)
        self.assertNotIn(DEEPSEEK_IMAGE_ONLY_PROMPT, out)
        self.assertNotIn(DEEPSEEK_SUBAGENT_PROMPT, out)

    def test_show_json_fields(self) -> None:
        data = self.show_json("deepseek:d5ee0001", "--messages", "0")
        self.assertEqual(data["ref"], "deepseek:d5ee0001")
        self.assertEqual(data["harness"], "deepseek")
        self.assertEqual(data["session_id"], DEEPSEEK_MAIN)
        self.assertEqual(data["cwd"], DEEPSEEK_PROJECT_ALPHA + "/packages")
        self.assertEqual(data["entrypoint"], "desktop")
        self.assertEqual(data["variants"], "desktop")
        self.assertEqual(data["branch"], "")
        self.assertEqual(data["version"], "")
        self.assertEqual(data["model"], DEEPSEEK_MODEL_ALT)
        self.assertEqual(data["started"], "2026-10-20T09:00:00Z")
        self.assertEqual(data["updated"], "2026-10-20T10:10:00Z")
        self.assertGreater(data["size_bytes"], 0)
        self.assertFalse(data["archived"])
        self.assertEqual(data["compact_summary"], DEEPSEEK_COMPACT_SUMMARY)
        self.assertEqual(data["first_prompt"], DEEPSEEK_PROMPTS[0])
        self.assertEqual(data["last_prompt"], DEEPSEEK_PROMPTS[-1])
        self.assertEqual(data["turn_count"], 4)
        self.assertEqual(
            data["todos"],
            [
                {"subject": subject, "status": status}
                for subject, status in DEEPSEEK_TODOS
            ],
        )
        self.assertEqual(
            data["edited_files"],
            [
                {
                    "path": DEEPSEEK_PROJECT_ALPHA + "/src/digest.py",
                    "count": 2,
                },
                {
                    "path": DEEPSEEK_PROJECT_ALPHA + "/docs/handoff.md",
                    "count": 1,
                },
            ],
        )
        self.assertEqual(
            data["tool_counts"], {"edit": 2, "bash": 1, "write": 1}
        )
        self.assertEqual(
            [(tool["name"], tool["detail"]) for tool in data["recent_tools"]],
            [
                ("bash", "sed -n '1,40p' src/digest.py"),
                ("edit", "src/digest.py"),
                ("edit", "src/digest.py"),
                ("write", "docs/handoff.md"),
            ],
        )
        self.assertEqual(
            data["path"],
            str(
                self.deepseek_home
                / "sessions"
                / "--Users-example-project-alpha--"
                / ("session-" + DEEPSEEK_MAIN)
                / "session.v3.jsonl.zstd"
            ),
        )

    def test_show_by_source_path(self) -> None:
        data = self.show_json("deepseek:d5ee0001", "--messages", "0")
        source = data["path"]

        code, out, err = self.run_cli("show", source)
        self.assertEqual(code, 0, err)
        self.assertIn("# deepseek:d5ee0001", out)

        code, out, err = self.run_cli("prompts", source, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "4")

    def test_show_archived_session(self) -> None:
        code, out, err = self.run_cli("show", "deepseek:d5ee0002")
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)
        self.assertIn("- cwd: `%s`" % DEEPSEEK_PROJECT_BETA, out)

        data = self.show_json("deepseek:d5ee0002")
        self.assertTrue(data["archived"])
        self.assertEqual(data["title"], DEEPSEEK_TITLE_ARCHIVED)
        self.assertEqual(data["first_prompt"], DEEPSEEK_ARCHIVED_PROMPT)

        code, out, err = self.run_cli("show", data["path"])
        self.assertEqual(code, 0, err)
        self.assertIn("# deepseek:d5ee0002", out)

    def test_show_missing_ambiguous_and_too_short_refs(self) -> None:
        code, out, err = self.run_cli("show", "deepseek:d5ee000f")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "deepseek:d5ee000")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", err)

        code, out, err = self.run_cli("show", "deepseek:d5e")
        self.assertEqual(code, 2)
        self.assertIn("too short", err)

    def test_subagent_session_is_excluded(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "deepseek",
            "--include-archived",
            "--limit",
            "0",
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn("d5ee0005", out)

        code, out, err = self.run_cli("show", "deepseek:d5ee0005")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli("prompts", "deepseek:d5ee0001", "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "4")

        code, out, err = self.run_cli("prompts", "deepseek:d5ee0001")
        self.assertEqual(code, 0, err)
        for index, prompt in enumerate(DEEPSEEK_PROMPTS, 1):
            self.assertIn("## %d" % index, out)
            self.assertIn(prompt, out)

        code, out, err = self.run_cli(
            "prompts", "deepseek:d5ee0001", "--offset", "1", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("## 2", out)
        self.assertNotIn(DEEPSEEK_PROMPTS[0], out)
        self.assertIn("next: --offset 2 --limit 1", out)

        code, out, err = self.run_cli(
            "prompts", "deepseek:d5ee0001", "--order", "newest", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("## 4"), out.index("## 3"))
        self.assertNotIn("## 1", out)

        code, out, err = self.run_cli(
            "prompts", "deepseek:d5ee0001", "--offset", "9"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts", "deepseek:d5ee0001", "--limit", "1", "--chars", "10"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Please re…", out)
        self.assertNotIn(DEEPSEEK_PROMPTS[0], out)

    def test_prompts_json_and_archived(self) -> None:
        data = self.run_json("prompts", "deepseek:d5ee0001", "--limit", "2")
        self.assertEqual(data["ref"], "deepseek:d5ee0001")
        self.assertEqual(data["session_id"], DEEPSEEK_MAIN)
        self.assertEqual(data["cwd"], DEEPSEEK_PROJECT_ALPHA + "/packages")
        self.assertFalse(data["archived"])
        self.assertEqual(data["total"], 4)
        self.assertEqual(data["returned"], 2)
        self.assertTrue(data["has_more"])
        self.assertEqual(
            [prompt["index"] for prompt in data["prompts"]], [1, 2]
        )
        self.assertEqual(data["prompts"][0]["text"], DEEPSEEK_PROMPTS[0])
        self.assertEqual(data["prompts"][0]["timestamp"], '2026-10-20T09:10:00Z')

        data = self.run_json("prompts", "deepseek:d5ee0002", "--count")
        self.assertTrue(data["archived"])
        self.assertEqual(data["total"], 1)

    def test_non_human_records_never_become_prompts(self) -> None:
        prompts = self.run_json(
            "prompts", "deepseek:d5ee0001", "--limit", "0"
        )
        texts = [prompt["text"] for prompt in prompts["prompts"]]
        self.assertEqual(texts, list(DEEPSEEK_PROMPTS))
        self.assertEqual(texts.count(DEEPSEEK_PROMPTS[0]), 1)
        for text in texts:
            self.assertNotIn("Injected ", text)
            self.assertNotIn("Synthetic ", text)
        self.assertNotIn(DEEPSEEK_IMAGE_ONLY_PROMPT, texts)
        self.assertNotIn(DEEPSEEK_SUBAGENT_PROMPT, texts)
        self.assertNotIn(DEEPSEEK_ABANDONED_PROMPT, texts)

    def test_empty_session_prompts(self) -> None:
        code, out, err = self.run_cli("prompts", "deepseek:d5ee0006", "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "0")

        code, out, err = self.run_cli("prompts", "deepseek:d5ee0006", "--limit", "0")
        self.assertEqual(code, 0, err)
        self.assertIn("no user prompts", out)

    def test_missing_workspace_json_degrades_to_all_active(self) -> None:
        sessions = self.run_json(
            "search",
            "--harness",
            "deepseek",
            "--limit",
            "0",
            deepseek_home=self.deepseek_no_workspace_home,
        )
        self.assertEqual(len(sessions), 5)
        archived = {
            session["ref"]: session["archived"] for session in sessions
        }
        self.assertFalse(archived["deepseek:d5ee0002"])

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "deepseek",
            "--deep",
            DEEPSEEK_ARCHIVED_NEEDLE,
            deepseek_home=self.deepseek_no_workspace_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("deepseek:d5ee0002", out)

    def test_empty_store_is_safe(self) -> None:
        for command in ("search", "latest"):
            code, out, err = self.run_cli(
                command,
                "--harness",
                "deepseek",
                deepseek_home=self.empty_deepseek_home,
            )
            self.assertEqual(code, 0, err)
            self.assertIn("no sessions matched", out)

    def test_commands_do_not_modify_deepseek_store(self) -> None:
        def snapshot() -> dict:
            files = {}
            for path in self.deepseek_home.rglob("*"):
                if path.is_file():
                    files[str(path)] = (
                        path.read_bytes(),
                        path.stat().st_mtime_ns,
                    )
            return files

        before = snapshot()
        self.run_cli_checked("search", "--harness", "deepseek")
        self.run_cli_checked("search", "--harness", "deepseek", "--include-archived")
        self.run_cli_checked(
            "search", "--harness", "deepseek", "--deep", DEEPSEEK_DEEP_ONLY_NEEDLE
        )
        self.run_cli_checked("latest", "--harness", "deepseek")
        self.run_cli_checked("show", "deepseek:d5ee0001")
        self.run_cli_checked("show", "deepseek:d5ee0003")
        self.run_cli_checked("show", "deepseek:d5ee0002", "--format", "json")
        self.run_cli_checked("prompts", "deepseek:d5ee0001")
        self.run_cli_checked("prompts", "deepseek:d5ee0001", "--count")
        self.assertEqual(snapshot(), before)
        self.assertFalse(
            any(
                path.name.endswith(("-wal", "-shm", "-journal"))
                for path in self.deepseek_home.rglob("*")
            )
        )

    def test_fixture_data_is_synthetic(self) -> None:
        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        for path in self.deepseek_home.rglob("*"):
            if not path.is_file():
                continue
            raw = (
                deepseek_decompress(path)
                if path.name.endswith(".zstd")
                else path.read_bytes()
            )
            text = raw.decode("utf-8", "ignore")
            self.assertNotIn("/Volumes/", text, str(path))
            self.assertNotIn("/home/", text, str(path))
            self.assertNotIn("C:\\Users\\", text, str(path))
            self.assertNotIn(
                "/Users/", text.replace("/Users/example/", ""), str(path)
            )
            self.assertIsNone(email.search(text), str(path))
        for session_id in (
            DEEPSEEK_MAIN,
            DEEPSEEK_ARCHIVED,
            DEEPSEEK_PLAIN,
            DEEPSEEK_MULTI,
            DEEPSEEK_SUBAGENT,
            DEEPSEEK_EMPTY,
        ):
            self.assertTrue(session_id.startswith("d5ee00"), session_id)
        for path in (self.deepseek_home / "sessions").rglob("session-*"):
            if path.is_dir():
                self.assertTrue(
                    path.name[len("session-") :].startswith("d5ee00"), path.name
                )
