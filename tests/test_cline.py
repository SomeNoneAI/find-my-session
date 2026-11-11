from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

from cli_support import FixtureTestCase
from cline_fixture import (
    BRANCH_MAIN as CLINE_BRANCH_MAIN,
    COMPACT_SUMMARY as CLINE_COMPACT_SUMMARY,
    EDITOR_ABS as CLINE_EDITOR_ABS,
    MODEL_MAIN as CLINE_MODEL_MAIN,
    NEEDLE_COMPACTION_ONLY as CLINE_COMPACTION_ONLY_NEEDLE,
    NEEDLE_DEEP_ONLY as CLINE_DEEP_ONLY_NEEDLE,
    NEEDLE_INJECTED as CLINE_INJECTED_NEEDLE,
    NEEDLE_SUBAGENT as CLINE_SUBAGENT_NEEDLE,
    NEEDLE_TOOL_OUTPUT as CLINE_TOOL_OUTPUT_NEEDLE,
    PROJECT_ALPHA as CLINE_PROJECT_ALPHA,
    PROMPTS_AUX as CLINE_PROMPTS_AUX,
    PROMPTS_MAIN as CLINE_PROMPTS,
    PROMPT_COMPACT_RESUME as CLINE_COMPACT_RESUME_PROMPT,
    PROMPT_PLAIN as CLINE_PLAIN_PROMPT,
    SESSION_AUX as CLINE_AUX,
    SESSION_COMPACT as CLINE_COMPACT,
    SESSION_MAIN as CLINE_MAIN,
    SESSION_PLAIN as CLINE_PLAIN,
    SUBAGENT_STEM as CLINE_SUBAGENT_STEM,
    TITLE_COMPACT as CLINE_TITLE_COMPACT,
    TITLE_MAIN as CLINE_TITLE_MAIN,
    VERSION_MAIN as CLINE_VERSION,
)


class ClineTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli("show", *args, "--format", "json", **kwargs)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_harness_row(self) -> None:
        rows = self.run_json("harnesses")
        rows = [row for row in rows if row["name"] == "cline"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "ready")
        self.assertEqual(rows[0]["variants"], "desktop, cli")
        self.assertEqual(rows[0]["store"], "~/.cline/data/sessions")
        self.assertEqual(rows[0]["aliases"], "cline")

    def test_vscode_extension_remains_planned(self) -> None:
        rows = self.run_json("harnesses")
        rows = [row for row in rows if row["name"] == "cline-vscode"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "planned")
        self.assertEqual(rows[0]["variants"], "vscode")

        code, out, err = self.run_cli("search", "--harness", "cline-vscode")
        self.assertEqual(code, 2)
        self.assertIn("planned but not implemented", err)

    def test_lists_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "cline")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("cline:c1a0e"))
        self.assertTrue(lines[1].startswith("cline:c1a0d"))
        self.assertTrue(lines[2].startswith("cline:c1a0g"))
        self.assertTrue(lines[3].startswith("cline:c1a0f"))
        self.assertNotIn("c1a0z", out)
        self.assertNotIn(CLINE_SUBAGENT_NEEDLE, out)

    def test_keyword_id_cwd_since_limit_and_no_match(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "cline", "handoff")
        self.assertEqual(code, 0, err)
        self.assertIn("cline:c1a0d", out)
        self.assertNotIn("cline:c1a0e", out)

        for needle, expected in (
            ("c1a0e", "cline:c1a0e"),
            ("1793000000000", "cline:c1a0f"),
            ("session_1793000000300", "cline:c1a0g"),
        ):
            sessions = self.run_json("search", "--harness", "cline", needle)
            self.assertEqual(
                [session["ref"] for session in sessions],
                [expected],
                needle,
            )

        sessions = self.run_json("search", "--harness", "cline", "c1a0")
        self.assertEqual(len(sessions), 4)

        code, out, err = self.run_cli(
            "search", "--harness", "cline", "--cwd", CLINE_PROJECT_ALPHA
        )
        self.assertEqual(code, 0, err)
        self.assertIn("cline:c1a0d", out)
        self.assertNotIn("cline:c1a0e", out)

        code, out, err = self.run_cli(
            "search", "--harness", "cline", "--cwd", "/Users/example"
        )
        self.assertEqual(code, 0, err)
        for ref in ("cline:c1a0d", "cline:c1a0e", "cline:c1a0g"):
            self.assertIn(ref, out)
        self.assertNotIn("cline:c1a0f", out)

        code, out, err = self.run_cli(
            "search", "--harness", "cline", "--since", "2026-10-24"
        )
        self.assertEqual(code, 0, err)
        for ref in ("cline:c1a0d", "cline:c1a0e", "cline:c1a0g"):
            self.assertIn(ref, out)
        self.assertNotIn("cline:c1a0f", out)

        code, out, err = self.run_cli(
            "search", "--harness", "cline", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

        code, out, err = self.run_cli(
            "search", "--harness", "cline", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_latest_and_query_filter(self) -> None:
        sessions = self.run_json("latest", "--harness", "cline")
        self.assertEqual([session["ref"] for session in sessions], ["cline:c1a0e"])
        self.assertEqual(sessions[0]["title"], CLINE_PROMPTS_AUX[0])
        self.assertEqual(sessions[0]["first_prompt"], CLINE_PROMPTS_AUX[0])
        self.assertEqual(sessions[0]["last_prompt"], CLINE_PROMPTS_AUX[1])
        self.assertEqual(sessions[0]["entrypoint"], "desktop")
        self.assertEqual(sessions[0]["variants"], "desktop, cli")

        sessions = self.run_json("latest", "--harness", "cline", "handoff")
        self.assertEqual([session["ref"] for session in sessions], ["cline:c1a0d"])
        self.assertEqual(sessions[0]["title"], CLINE_TITLE_MAIN)
        self.assertEqual(sessions[0]["first_prompt"], CLINE_PROMPTS[0])
        self.assertEqual(sessions[0]["last_prompt"], CLINE_PROMPTS[-1])
        self.assertEqual(sessions[0]["cwd"], CLINE_PROJECT_ALPHA)
        self.assertEqual(sessions[0]["branch"], CLINE_BRANCH_MAIN)
        self.assertEqual(sessions[0]["model"], CLINE_MODEL_MAIN)
        self.assertEqual(sessions[0]["version"], CLINE_VERSION)
        self.assertEqual(sessions[0]["entrypoint"], "cli")

        code, out, err = self.run_cli(
            "latest", "--harness", "cline", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_archive_flag_is_always_inactive(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "cline",
            "--include-archived",
            "--limit",
            "0",
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        for line in lines:
            self.assertEqual(line.split("\t")[-1], "-")

        data = self.show_json("cline:c1a0d", "--messages", "0")
        self.assertFalse(data["archived"])

        code, out, err = self.run_cli("show", "cline:c1a0d")
        self.assertEqual(code, 0, err)
        self.assertNotIn("- archived: yes", out)

    def test_deep_search_scans_content(self) -> None:
        for needle in (CLINE_TOOL_OUTPUT_NEEDLE, CLINE_COMPACTION_ONLY_NEEDLE):
            code, out, err = self.run_cli(
                "search", "--harness", "cline", needle
            )
            self.assertEqual(code, 0, err)
            self.assertIn("no sessions matched", out)

        for needle, expected, absent in (
            (CLINE_TOOL_OUTPUT_NEEDLE, "cline:c1a0d", "cline:c1a0g"),
            (CLINE_DEEP_ONLY_NEEDLE, "cline:c1a0d", "cline:c1a0e"),
            (CLINE_COMPACTION_ONLY_NEEDLE, "cline:c1a0g", "cline:c1a0d"),
            (CLINE_INJECTED_NEEDLE, "cline:c1a0d", "cline:c1a0e"),
        ):
            code, out, err = self.run_cli(
                "search", "--harness", "cline", "--deep", needle
            )
            self.assertEqual(code, 0, err)
            self.assertIn(expected, out, needle)
            self.assertNotIn(absent, out, needle)

        code, out, err = self.run_cli(
            "search", "--harness", "cline", "--deep", CLINE_SUBAGENT_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_subagent_transcript_is_not_a_session(self) -> None:
        path = (
            self.cline_home
            / "data"
            / "sessions"
            / CLINE_MAIN
            / (CLINE_SUBAGENT_STEM + ".messages.json")
        )
        self.assertTrue(path.is_file())

        code, out, err = self.run_cli("show", str(path))
        self.assertEqual(code, 2)
        self.assertIn("subagent transcript", err)

        code, out, err = self.run_cli("prompts", str(path), "--count")
        self.assertEqual(code, 2)
        self.assertIn("subagent transcript", err)

    def test_show_digest(self) -> None:
        code, out, err = self.run_cli("show", "cline:c1a0d")
        self.assertEqual(code, 0, err)
        self.assertIn("# cline:c1a0d", out)
        self.assertIn("- harness: cline (desktop, cli)", out)
        self.assertIn("- cwd: `%s`" % CLINE_PROJECT_ALPHA, out)
        self.assertIn("- branch: `%s`" % CLINE_BRANCH_MAIN, out)
        self.assertIn("- model: `%s`" % CLINE_MODEL_MAIN, out)
        self.assertIn("- version: `%s`" % CLINE_VERSION, out)
        self.assertIn("- turns: 4", out)
        self.assertIn("## Task\n%s" % CLINE_PROMPTS[0], out)
        self.assertIn("## Latest request\n%s" % CLINE_PROMPTS[-1], out)
        self.assertNotIn("## Todos", out)
        self.assertIn("## Edited files", out)
        self.assertIn(
            "- `%s/%s` (x2)" % (CLINE_PROJECT_ALPHA, "src/digest.py"), out
        )
        self.assertIn("- `%s`" % CLINE_EDITOR_ABS, out)
        self.assertIn("## Recent tools", out)
        self.assertIn("read_files", out)
        self.assertIn("editor", out)

    def test_show_json(self) -> None:
        data = self.show_json("cline:c1a0d", "--messages", "0")
        self.assertEqual(data["ref"], "cline:c1a0d")
        self.assertEqual(data["session_id"], CLINE_MAIN)
        self.assertEqual(data["cwd"], CLINE_PROJECT_ALPHA)
        self.assertEqual(data["title"], CLINE_TITLE_MAIN)
        self.assertEqual(data["first_prompt"], CLINE_PROMPTS[0])
        self.assertEqual(data["last_prompt"], CLINE_PROMPTS[-1])
        self.assertEqual(data["turn_count"], 4)
        self.assertEqual(data["todos"], [])
        self.assertEqual(data["compact_summary"], "")
        self.assertFalse(data["archived"])
        self.assertEqual(data["entrypoint"], "cli")
        self.assertEqual(data["exchanges"], [])
        self.assertEqual(
            data["edited_files"],
            [
                {
                    "path": CLINE_PROJECT_ALPHA + "/src/digest.py",
                    "count": 2,
                },
                {"path": CLINE_EDITOR_ABS, "count": 1},
            ],
        )
        self.assertEqual(data["tool_counts"], {"editor": 3, "read_files": 1})
        self.assertEqual(
            data["path"],
            str(
                self.cline_home
                / "data"
                / "sessions"
                / CLINE_MAIN
                / (CLINE_MAIN + ".messages.json")
            ),
        )

        recent = self.show_json("cline:c1a0d")
        self.assertEqual(len(recent["exchanges"]), 2)
        self.assertEqual(recent["exchanges"][-1]["user"], CLINE_PROMPTS[-1])
        self.assertEqual(
            recent["exchanges"][-1]["assistant"], ["Done."]
        )
        self.assertEqual(
            [tool["name"] for tool in recent["exchanges"][-1]["tools"]],
            ["editor"],
        )

    def test_show_plain_session_without_metadata(self) -> None:
        data = self.show_json("cline:c1a0f", "--messages", "0")
        self.assertEqual(data["session_id"], CLINE_PLAIN)
        self.assertEqual(data["title"], CLINE_PLAIN_PROMPT)
        self.assertEqual(data["first_prompt"], CLINE_PLAIN_PROMPT)
        self.assertEqual(data["last_prompt"], CLINE_PLAIN_PROMPT)
        self.assertEqual(data["cwd"], "")
        self.assertEqual(data["model"], "")
        self.assertEqual(data["entrypoint"], "")
        self.assertEqual(data["version"], "")
        self.assertEqual(data["turn_count"], 1)
        self.assertEqual(data["updated"], "2026-10-23T10:00:00Z")

    def test_show_compacted_session(self) -> None:
        code, out, err = self.run_cli("show", "cline:c1a0g")
        self.assertEqual(code, 0, err)
        self.assertIn("- turns: 2", out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn("Bound the Cline digest.", out)
        self.assertIn(CLINE_COMPACTION_ONLY_NEEDLE, out)
        self.assertNotIn("Earlier synthetic context summary", out)

        data = self.show_json("cline:c1a0g", "--messages", "0")
        self.assertEqual(data["compact_summary"], CLINE_COMPACT_SUMMARY)
        self.assertEqual(data["title"], CLINE_TITLE_COMPACT)
        self.assertEqual(data["first_prompt"], "Plan the migration.")
        self.assertEqual(data["last_prompt"], CLINE_COMPACT_RESUME_PROMPT)
        self.assertEqual(data["turn_count"], 2)

        prompts = self.run_json("prompts", "cline:c1a0g", "--limit", "0")
        self.assertEqual(prompts["total"], 2)
        self.assertEqual(
            [prompt["text"] for prompt in prompts["prompts"]],
            ["Plan the migration.", CLINE_COMPACT_RESUME_PROMPT],
        )

    def test_show_by_source_path(self) -> None:
        data = self.show_json("cline:c1a0d", "--messages", "0")
        source = data["path"]

        code, out, err = self.run_cli("show", source)
        self.assertEqual(code, 0, err)
        self.assertIn("# cline:c1a0d", out)

        code, out, err = self.run_cli("prompts", source, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "4")

    def test_show_missing_ambiguous_and_too_short_refs(self) -> None:
        code, out, err = self.run_cli("show", "cline:c1a0z")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "cline:c1a0")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", err)

        code, out, err = self.run_cli("show", "cline:c1a")
        self.assertEqual(code, 2)
        self.assertIn("too short", err)

        code, out, err = self.run_cli("show", "c1a0f")
        self.assertEqual(code, 0, err)
        self.assertIn("# cline:c1a0f", out)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli("prompts", "cline:c1a0d", "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "4")

        code, out, err = self.run_cli("prompts", "cline:c1a0d")
        self.assertEqual(code, 0, err)
        for index, prompt in enumerate(CLINE_PROMPTS, 1):
            self.assertIn("## %d" % index, out)
            self.assertIn(prompt, out)
        self.assertNotIn(CLINE_INJECTED_NEEDLE, out)
        self.assertNotIn("System-delivered", out)
        self.assertNotIn("was cut off", out)

        code, out, err = self.run_cli(
            "prompts", "cline:c1a0d", "--offset", "1", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("## 2", out)
        self.assertNotIn(CLINE_PROMPTS[0], out)
        self.assertIn("next: --offset 2 --limit 1", out)

        code, out, err = self.run_cli(
            "prompts", "cline:c1a0d", "--order", "newest", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("## 4"), out.index("## 3"))
        self.assertNotIn("## 1", out)

        code, out, err = self.run_cli(
            "prompts", "cline:c1a0d", "--offset", "9"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts", "cline:c1a0d", "--limit", "1", "--chars", "10"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Please re…", out)
        self.assertNotIn(CLINE_PROMPTS[0], out)

    def test_prompts_json(self) -> None:
        data = self.run_json("prompts", "cline:c1a0d", "--limit", "2")
        self.assertEqual(data["ref"], "cline:c1a0d")
        self.assertEqual(data["session_id"], CLINE_MAIN)
        self.assertEqual(data["cwd"], CLINE_PROJECT_ALPHA)
        self.assertFalse(data["archived"])
        self.assertEqual(data["total"], 4)
        self.assertEqual(data["returned"], 2)
        self.assertTrue(data["has_more"])
        self.assertEqual([prompt["index"] for prompt in data["prompts"]], [1, 2])
        self.assertEqual(data["prompts"][0]["text"], CLINE_PROMPTS[0])
        self.assertEqual(data["prompts"][0]["timestamp"], '2026-10-25T09:00:05Z')

    def test_non_human_records_never_become_prompts(self) -> None:
        prompts = self.run_json("prompts", "cline:c1a0d", "--limit", "0")
        texts = [prompt["text"] for prompt in prompts["prompts"]]
        self.assertEqual(texts, list(CLINE_PROMPTS))
        for text in texts:
            self.assertNotIn("[SYSTEM]", text)
            self.assertNotIn("<user_input", text)
            self.assertNotIn("</user_input>", text)
            self.assertNotIn("System-delivered", text)
            self.assertNotIn("was cut off", text)
            self.assertNotIn("tool_result", text)

        aux = self.run_json("prompts", "cline:c1a0e", "--limit", "0")
        self.assertEqual(
            [prompt["text"] for prompt in aux["prompts"]],
            list(CLINE_PROMPTS_AUX),
        )

    def test_commands_do_not_modify_store(self) -> None:
        def snapshot() -> dict:
            files = {}
            for path in self.cline_home.rglob("*"):
                if path.is_file():
                    files[str(path)] = (
                        path.read_bytes(),
                        path.stat().st_mtime_ns,
                    )
            return files

        before = snapshot()
        self.run_cli_checked("search", "--harness", "cline")
        self.run_cli_checked("search", "--harness", "cline", "--deep", CLINE_DEEP_ONLY_NEEDLE)
        self.run_cli_checked("latest", "--harness", "cline")
        self.run_cli_checked("show", "cline:c1a0d")
        self.run_cli_checked("show", "cline:c1a0d", "--format", "json")
        self.run_cli_checked("show", "cline:c1a0g")
        self.run_cli_checked("prompts", "cline:c1a0d", "--count")
        self.run_cli_checked("prompts", "cline:c1a0d", "--order", "newest", "--limit", "2")
        self.run_cli_checked(
            "search", "--harness", "cline", "--include-archived", "--limit", "0"
        )
        self.assertEqual(snapshot(), before)

    def test_crlf_transcript_parses_identically(self) -> None:
        # A real Windows Cline install can store the pretty-printed
        # transcript with CRLF line endings; prompts must survive.
        with tempfile.TemporaryDirectory(prefix="fms-cline-crlf-") as raw:
            home = Path(raw)
            shutil.copytree(self.cline_home, home / "cline-home")
            for messages in (home / "cline-home").rglob("*.messages.json"):
                data = messages.read_bytes().replace(b"\n", b"\r\n")
                messages.write_bytes(data)
            code, out, err = self.run_cli(
                "prompts", "cline:c1a0e", "--count", cline_home=home / "cline-home"
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(out.strip(), "2")
            code, out, err = self.run_cli(
                "show", "cline:c1a0e", cline_home=home / "cline-home"
            )
            self.assertEqual(code, 0, err)
            self.assertIn(CLINE_PROMPTS_AUX[1], out)

    def test_fixture_data_is_synthetic(self) -> None:
        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        for path in self.cline_home.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8", "ignore")
            self.assertNotIn(str(Path.home()), text)
            self.assertNotIn("/Volumes/", text)
            self.assertNotIn("/home/", text)
            self.assertNotIn("/Users/", text.replace("/Users/example/", ""))
            self.assertIsNone(email.search(text), str(path))
        for session_id in (
            CLINE_MAIN,
            CLINE_AUX,
            CLINE_COMPACT,
            CLINE_PLAIN,
        ):
            self.assertTrue(
                session_id.startswith(("session_1793000000", "1793000000")),
                session_id,
            )
