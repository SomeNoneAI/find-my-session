from __future__ import annotations

import json
import re

from cli_support import FixtureTestCase
from antigravity_fixture import (
    CLI_NEEDLE_DB_ONLY as ANTIGRAVITY_CLI_DB_ONLY_NEEDLE,
    CLI_NEEDLE_DEEP as ANTIGRAVITY_CLI_DEEP_NEEDLE,
    CLI_NEEDLE_HISTORY as ANTIGRAVITY_CLI_HISTORY_NEEDLE,
    CLI_NEEDLE_PROTO as ANTIGRAVITY_CLI_PROTO_NEEDLE,
    CLI_PROMPT_FALLBACK as ANTIGRAVITY_CLI_FALLBACK_PROMPT,
    CLI_PROMPT_SHORT as ANTIGRAVITY_CLI_SHORT_PROMPT,
    CLI_PROMPTS as ANTIGRAVITY_CLI_PROMPTS,
    CLI_SESSION_DEEP as ANTIGRAVITY_CLI_DEEP,
    CLI_SESSION_FALLBACK as ANTIGRAVITY_CLI_FALLBACK,
    CLI_SESSION_MAIN as ANTIGRAVITY_CLI_MAIN,
    CLI_SESSION_METADATA as ANTIGRAVITY_CLI_METADATA,
    CLI_SESSION_ORPHAN as ANTIGRAVITY_CLI_ORPHAN,
    CLI_ORPHAN_BRAIN as ANTIGRAVITY_CLI_ORPHAN_BRAIN,
    NEEDLE_ARCHIVED as ANTIGRAVITY_ARCHIVED_NEEDLE,
    NEEDLE_DB_DECOY as ANTIGRAVITY_DB_DECOY_NEEDLE,
    NEEDLE_DB_ONLY as ANTIGRAVITY_DB_ONLY_NEEDLE,
    NEEDLE_DEEP as ANTIGRAVITY_DEEP_NEEDLE,
    NEEDLE_IDE_ONLY as ANTIGRAVITY_IDE_ONLY_NEEDLE,
    NEEDLE_MAIN as ANTIGRAVITY_MAIN_NEEDLE,
    NEEDLE_NESTED as ANTIGRAVITY_NESTED_NEEDLE,
    NEEDLE_ORPHAN_BRAIN as ANTIGRAVITY_ORPHAN_BRAIN_NEEDLE,
    NEEDLE_SUBAGENT as ANTIGRAVITY_SUBAGENT_NEEDLE,
    NEEDLE_TOOL_OUTPUT as ANTIGRAVITY_TOOL_OUTPUT_NEEDLE,
    PROJECT_ALPHA as ANTIGRAVITY_PROJECT_ALPHA,
    PROJECT_ARCHIVE as ANTIGRAVITY_PROJECT_ARCHIVE,
    PROJECT_CLI as ANTIGRAVITY_PROJECT_CLI,
    PROJECT_LEGACY as ANTIGRAVITY_PROJECT_LEGACY,
    PROMPT_MIGRATED as ANTIGRAVITY_MIGRATED_PROMPT,
    PROMPT_SHORT as ANTIGRAVITY_SHORT_PROMPT,
    PROMPT_SUBAGENT as ANTIGRAVITY_SUBAGENT_PROMPT,
    PROMPTS_MAIN as ANTIGRAVITY_PROMPTS,
    SESSION_ARCHIVED as ANTIGRAVITY_ARCHIVED,
    SESSION_DEEP as ANTIGRAVITY_DEEP,
    SESSION_IDE_ONLY as ANTIGRAVITY_IDE_ONLY,
    SESSION_MAIN as ANTIGRAVITY_MAIN,
    SESSION_METADATA as ANTIGRAVITY_METADATA,
    SESSION_MIGRATED as ANTIGRAVITY_MIGRATED,
    SESSION_NESTED as ANTIGRAVITY_NESTED,
    SESSION_ORPHAN as ANTIGRAVITY_ORPHAN,
    SESSION_ORPHAN_BRAIN as ANTIGRAVITY_ORPHAN_BRAIN,
    TITLE_ARCHIVED as ANTIGRAVITY_TITLE_ARCHIVED,
    TITLE_CLI_MAIN as ANTIGRAVITY_CLI_TITLE_MAIN,
    TITLE_CLI_METADATA as ANTIGRAVITY_CLI_TITLE_METADATA,
    TITLE_MAIN as ANTIGRAVITY_TITLE_MAIN,
    TITLE_METADATA as ANTIGRAVITY_TITLE_METADATA,
    TITLE_MIGRATED as ANTIGRAVITY_TITLE_MIGRATED,
)


class AntigravityTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli(
            "show", *args, "--format", "json", **kwargs
        )
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_harness_row(self) -> None:
        rows = [
            row
            for row in self.run_json("harnesses")
            if row["name"] == "antigravity"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "ready")
        self.assertEqual(rows[0]["variants"], "desktop, ide")
        self.assertEqual(rows[0]["store"], "~/.gemini/antigravity")
        self.assertEqual(
            rows[0]["aliases"],
            "antigravity, antigravity-desktop, antigravity-ide",
        )

    def test_lists_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "antigravity")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("antigravity:a17e5a01"))
        self.assertTrue(lines[1].startswith("antigravity:a17e5a04"))
        self.assertTrue(lines[2].startswith("antigravity:a17e5a07"))
        self.assertTrue(lines[3].startswith("antigravity:a17e5a06"))
        self.assertNotIn("a17e5a02", out)
        self.assertNotIn("a17e5a03", out)
        self.assertNotIn("a17e5a05", out)
        self.assertNotIn("a17e5a08", out)
        self.assertNotIn("a17e5a09", out)
        self.assertNotIn("c11a2b01", out)

    def test_aliases(self) -> None:
        for alias in (
            "antigravity",
            "antigravity-desktop",
            "antigravity-ide",
        ):
            sessions = self.run_json(
                "search", "--harness", alias, "--limit", "0"
            )
            self.assertEqual(len(sessions), 4)
            self.assertTrue(
                all(
                    session["ref"].startswith("antigravity:")
                    for session in sessions
                )
            )

    def test_keyword_id_cwd_since_limit_and_no_match(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "antigravity", "handoff"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("antigravity:a17e5a01", out)
        self.assertNotIn("a17e5a04", out)

        sessions = self.run_json(
            "search", "--harness", "antigravity", "a17e5a07"
        )
        self.assertEqual(
            [session["ref"] for session in sessions],
            ["antigravity:a17e5a07"],
        )

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "antigravity",
            "--cwd",
            ANTIGRAVITY_PROJECT_ALPHA,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("antigravity:a17e5a01", out)
        self.assertNotIn("a17e5a04", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "antigravity",
            "--cwd",
            ANTIGRAVITY_PROJECT_LEGACY,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("antigravity:a17e5a04", out)
        self.assertNotIn("a17e5a02", out)

        code, out, err = self.run_cli(
            "search", "--harness", "antigravity", "--cwd", "/Users/example"
        )
        self.assertEqual(code, 0, err)
        for ref in ("a17e5a01", "a17e5a04", "a17e5a06", "a17e5a07"):
            self.assertIn(ref, out)

        code, out, err = self.run_cli(
            "search", "--harness", "antigravity", "--since", "2026-08-27"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("a17e5a01", out)
        self.assertIn("a17e5a04", out)
        self.assertNotIn("a17e5a06", out)
        self.assertNotIn("a17e5a07", out)

        code, out, err = self.run_cli(
            "search", "--harness", "antigravity", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

        code, out, err = self.run_cli(
            "search", "--harness", "antigravity", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_archive_filtering(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "antigravity", "--include-archived"
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], "ref\tupdated\tcwd\ttitle\tarchived")
        self.assertEqual(len(lines[1:]), 5)
        marks = {
            parts[0]: parts[-1]
            for parts in (line.split("\t") for line in lines[1:])
        }
        self.assertEqual(marks["antigravity:a17e5a02"], "yes")
        self.assertEqual(marks["antigravity:a17e5a01"], "-")

        code, out, err = self.run_cli(
            "latest", "--harness", "antigravity", "archived"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)
        self.assertIn("--include-archived", out)

        code, out, err = self.run_cli(
            "latest",
            "--harness",
            "antigravity",
            "archived",
            "--include-archived",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("antigravity:a17e5a02", out)

        data = self.show_json("antigravity:a17e5a02", "--messages", "0")
        self.assertTrue(data["archived"])
        self.assertEqual(data["title"], ANTIGRAVITY_TITLE_ARCHIVED)
        self.assertEqual(data["updated"], "2026-08-20T09:00:00Z")

        code, out, err = self.run_cli("show", "antigravity:a17e5a02")
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)

        code, out, err = self.run_cli(
            "prompts", "antigravity:a17e5a02", "--count"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "1")

        data = self.run_json("prompts", "antigravity:a17e5a02")
        self.assertTrue(data["archived"])

    def test_latest_and_query_filter(self) -> None:
        sessions = self.run_json("latest", "--harness", "antigravity")
        self.assertEqual(
            [session["ref"] for session in sessions],
            ["antigravity:a17e5a01"],
        )
        self.assertEqual(sessions[0]["title"], ANTIGRAVITY_TITLE_MAIN)
        self.assertEqual(
            sessions[0]["first_prompt"], ANTIGRAVITY_PROMPTS[0]
        )
        self.assertEqual(
            sessions[0]["last_prompt"], ANTIGRAVITY_PROMPTS[-1]
        )
        self.assertEqual(sessions[0]["cwd"], ANTIGRAVITY_PROJECT_ALPHA)
        self.assertEqual(sessions[0]["entrypoint"], "desktop")
        self.assertEqual(sessions[0]["variants"], "desktop")

        sessions = self.run_json(
            "latest", "--harness", "antigravity", "migration"
        )
        self.assertEqual(
            [session["ref"] for session in sessions],
            ["antigravity:a17e5a04"],
        )
        self.assertEqual(sessions[0]["title"], ANTIGRAVITY_TITLE_MIGRATED)

        code, out, err = self.run_cli(
            "latest", "--harness", "antigravity", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_deep_search_scans_transcripts_and_db_fallback(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "antigravity", ANTIGRAVITY_DEEP_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "antigravity",
            "--deep",
            ANTIGRAVITY_DEEP_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("antigravity:a17e5a07", out)
        self.assertNotIn("a17e5a01", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "antigravity",
            "--deep",
            ANTIGRAVITY_TOOL_OUTPUT_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("antigravity:a17e5a01", out)
        self.assertNotIn("a17e5a07", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "antigravity",
            "--deep",
            ANTIGRAVITY_DB_ONLY_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("antigravity:a17e5a06", out)
        self.assertNotIn("a17e5a01", out)

        for needle in (
            ANTIGRAVITY_DB_DECOY_NEEDLE,
            ANTIGRAVITY_SUBAGENT_NEEDLE,
            ANTIGRAVITY_ORPHAN_BRAIN_NEEDLE,
            ANTIGRAVITY_IDE_ONLY_NEEDLE,
            ANTIGRAVITY_NESTED_NEEDLE,
            ANTIGRAVITY_SHORT_PROMPT,
        ):
            code, out, err = self.run_cli(
                "search", "--harness", "antigravity", "--deep", needle
            )
            self.assertEqual(code, 0, err)
            self.assertIn("no sessions matched", out, needle)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "antigravity",
            "--deep",
            ANTIGRAVITY_ARCHIVED_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "antigravity",
            "--include-archived",
            "--deep",
            ANTIGRAVITY_ARCHIVED_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("antigravity:a17e5a02", out)

    def test_deep_search_tokens_do_not_leak_across_sessions(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "antigravity",
            "--deep",
            ANTIGRAVITY_MAIN_NEEDLE,
            ANTIGRAVITY_DEEP_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "antigravity",
            "--include-archived",
            "--deep",
            ANTIGRAVITY_TOOL_OUTPUT_NEEDLE,
            ANTIGRAVITY_ARCHIVED_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_nested_orphan_and_ide_only_sessions_are_excluded(self) -> None:
        for ref in (
            "antigravity:a17e5a03",
            "antigravity:a17e5a05",
            "antigravity:a17e5a08",
            "antigravity:a17e5a09",
        ):
            code, out, err = self.run_cli("show", ref)
            self.assertEqual(code, 2, ref)
            self.assertIn("no session matched", err)

        orphan_path = (
            self.antigravity_home
            / "brain"
            / ANTIGRAVITY_ORPHAN_BRAIN
            / ".system_generated"
            / "logs"
            / "transcript_full.jsonl"
        )
        code, out, err = self.run_cli("show", str(orphan_path))
        self.assertEqual(code, 2)
        self.assertIn("not inside a known harness session store", err)

        ide_only_db = (
            self.antigravity_ide_home
            / "conversations"
            / (ANTIGRAVITY_IDE_ONLY + ".db")
        )
        code, out, err = self.run_cli("show", str(ide_only_db))
        self.assertEqual(code, 2)
        self.assertIn("not inside a known harness session store", err)

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli(
            "show", "antigravity:a17e5a01", "--messages", "6", "--chars", "120"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("# antigravity:a17e5a01", out)
        self.assertIn("- harness: antigravity (desktop)", out)
        self.assertIn("- cwd: `%s`" % ANTIGRAVITY_PROJECT_ALPHA, out)
        self.assertIn("- turns: 4", out)
        self.assertNotIn("- branch:", out)
        self.assertNotIn("- model:", out)
        self.assertNotIn("- version:", out)
        self.assertIn("## Task", out)
        self.assertIn(ANTIGRAVITY_PROMPTS[0], out)
        self.assertIn("## Latest request", out)
        self.assertIn(ANTIGRAVITY_PROMPTS[-1], out)
        self.assertIn("## Todos (2 open / 3 total)", out)
        self.assertIn("[pending] Add prompt paging", out)
        self.assertIn("[pending] Update docs", out)
        self.assertNotIn("[completed] Refactor the digest", out)
        self.assertIn("## Edited files", out)
        self.assertIn("src/handoff.py` (x2)", out)
        self.assertIn("docs/handoff.md`", out)
        self.assertIn("src/digest.py`", out)
        self.assertIn("## Recent tools", out)
        self.assertIn("view_file", out)
        self.assertIn("run_command", out)
        self.assertIn("edit_file", out)
        self.assertIn("## Recent turns", out)
        self.assertNotIn("- archived: yes", out)
        self.assertNotIn(ANTIGRAVITY_TOOL_OUTPUT_NEEDLE, out)
        self.assertNotIn("Subagent scratch prompt", out)
        self.assertNotIn(ANTIGRAVITY_SHORT_PROMPT, out)
        self.assertNotIn("Synthetic system reminder", out)
        self.assertNotIn("Opened src/handoff.py", out)
        self.assertNotIn("<USER_REQUEST>", out)
        self.assertNotIn("<USER_SETTINGS_CHANGE>", out)

    def test_show_json_fields(self) -> None:
        data = self.show_json("antigravity:a17e5a01", "--messages", "0")
        self.assertEqual(data["ref"], "antigravity:a17e5a01")
        self.assertEqual(data["session_id"], ANTIGRAVITY_MAIN)
        self.assertEqual(data["cwd"], ANTIGRAVITY_PROJECT_ALPHA)
        self.assertEqual(data["entrypoint"], "desktop")
        self.assertEqual(data["variants"], "desktop")
        self.assertEqual(data["branch"], "")
        self.assertEqual(data["version"], "")
        self.assertEqual(data["model"], "")
        self.assertGreater(data["size_bytes"], 0)
        self.assertFalse(data["archived"])
        self.assertEqual(data["started"], "2026-09-01T10:05:00Z")
        self.assertEqual(data["updated"], "2026-09-01T10:45:00Z")
        self.assertEqual(data["title"], ANTIGRAVITY_TITLE_MAIN)
        self.assertEqual(data["compact_summary"], "")
        self.assertEqual(data["first_prompt"], ANTIGRAVITY_PROMPTS[0])
        self.assertEqual(data["last_prompt"], ANTIGRAVITY_PROMPTS[-1])
        self.assertEqual(data["turn_count"], 4)
        self.assertEqual(
            data["todos"],
            [
                {"subject": "Refactor the digest", "status": "completed"},
                {"subject": "Add prompt paging", "status": "pending"},
                {"subject": "Update docs", "status": "pending"},
            ],
        )
        self.assertEqual(
            data["edited_files"],
            [
                {
                    "path": ANTIGRAVITY_PROJECT_ALPHA + "/src/handoff.py",
                    "count": 2,
                },
                {
                    "path": ANTIGRAVITY_PROJECT_ALPHA + "/docs/handoff.md",
                    "count": 1,
                },
                {
                    "path": ANTIGRAVITY_PROJECT_ALPHA + "/src/digest.py",
                    "count": 1,
                },
            ],
        )
        self.assertEqual(
            data["tool_counts"],
            {
                "view_file": 2,
                "write_to_file": 1,
                "replace_file_content": 1,
                "run_command": 1,
                "write_file": 1,
                "edit_file": 1,
                "grep_search": 1,
            },
        )
        self.assertEqual(
            data["path"],
            str(
                self.antigravity_home
                / "conversations"
                / (ANTIGRAVITY_MAIN + ".db")
            ),
        )

    def test_show_migrated_ide_session(self) -> None:
        data = self.show_json("antigravity:a17e5a04", "--messages", "0")
        self.assertEqual(data["session_id"], ANTIGRAVITY_MIGRATED)
        self.assertEqual(data["entrypoint"], "ide")
        self.assertEqual(data["variants"], "ide")
        self.assertEqual(data["cwd"], ANTIGRAVITY_PROJECT_LEGACY)
        self.assertEqual(data["title"], ANTIGRAVITY_TITLE_MIGRATED)
        self.assertEqual(data["first_prompt"], ANTIGRAVITY_MIGRATED_PROMPT)
        self.assertEqual(data["last_prompt"], ANTIGRAVITY_MIGRATED_PROMPT)
        self.assertEqual(data["turn_count"], 1)

        code, out, err = self.run_cli("show", "antigravity:a17e5a04")
        self.assertEqual(code, 0, err)
        self.assertIn("- harness: antigravity (ide)", out)
        self.assertIn(ANTIGRAVITY_MIGRATED_PROMPT, out)

    def test_show_metadata_only_session(self) -> None:
        data = self.show_json("antigravity:a17e5a06", "--messages", "0")
        self.assertEqual(data["title"], ANTIGRAVITY_TITLE_METADATA)
        self.assertEqual(data["cwd"], ANTIGRAVITY_PROJECT_ARCHIVE)
        self.assertEqual(data["entrypoint"], "desktop")
        self.assertEqual(data["first_prompt"], "")
        self.assertEqual(data["last_prompt"], "")
        self.assertEqual(data["turn_count"], 0)
        self.assertEqual(data["todos"], [])
        self.assertEqual(data["exchanges"], [])

        code, out, err = self.run_cli("show", "antigravity:a17e5a06")
        self.assertEqual(code, 0, err)
        self.assertIn("# antigravity:a17e5a06", out)
        self.assertNotIn("## Task", out)
        self.assertNotIn("## Recent turns", out)

        code, out, err = self.run_cli(
            "prompts", "antigravity:a17e5a06", "--count"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "0")

        code, out, err = self.run_cli("prompts", "antigravity:a17e5a06")
        self.assertEqual(code, 0, err)
        self.assertIn("no user prompts", out)

    def test_show_by_source_path(self) -> None:
        data = self.show_json("antigravity:a17e5a01", "--messages", "0")
        source = data["path"]

        code, out, err = self.run_cli("show", source)
        self.assertEqual(code, 0, err)
        self.assertIn("# antigravity:a17e5a01", out)

        code, out, err = self.run_cli("prompts", source, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "4")

        transcript = (
            self.antigravity_home
            / "brain"
            / ANTIGRAVITY_MAIN
            / ".system_generated"
            / "logs"
            / "transcript_full.jsonl"
        )
        code, out, err = self.run_cli("show", str(transcript))
        self.assertEqual(code, 2)
        self.assertIn("not inside a known harness session store", err)

    def test_show_missing_ambiguous_and_too_short_refs(self) -> None:
        code, out, err = self.run_cli("show", "antigravity:a17e5aff")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "antigravity:a17e5a0")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", err)

        code, out, err = self.run_cli("show", "antigravity:a17")
        self.assertEqual(code, 2)
        self.assertIn("too short", err)

        code, out, err = self.run_cli("show", "a17e5a01")
        self.assertEqual(code, 0, err)
        self.assertIn("# antigravity:a17e5a01", out)

        code, out, err = self.run_cli("show", "antigravity-cli:a17e5a01")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli(
            "prompts", "antigravity:a17e5a01", "--count"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "4")

        code, out, err = self.run_cli("prompts", "antigravity:a17e5a01")
        self.assertEqual(code, 0, err)
        for index, prompt in enumerate(ANTIGRAVITY_PROMPTS, 1):
            self.assertIn("## %d" % index, out)
            self.assertIn(prompt, out)

        code, out, err = self.run_cli(
            "prompts",
            "antigravity:a17e5a01",
            "--offset",
            "1",
            "--limit",
            "1",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("## 2", out)
        self.assertNotIn(ANTIGRAVITY_PROMPTS[0], out)
        self.assertIn("next: --offset 2 --limit 1", out)

        code, out, err = self.run_cli(
            "prompts",
            "antigravity:a17e5a01",
            "--order",
            "newest",
            "--limit",
            "2",
        )
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("## 4"), out.index("## 3"))
        self.assertNotIn("## 1", out)

        code, out, err = self.run_cli(
            "prompts", "antigravity:a17e5a01", "--offset", "9"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts",
            "antigravity:a17e5a01",
            "--limit",
            "1",
            "--chars",
            "10",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Please re…", out)
        self.assertNotIn(ANTIGRAVITY_PROMPTS[0], out)

    def test_prompts_json(self) -> None:
        data = self.run_json(
            "prompts", "antigravity:a17e5a01", "--limit", "2"
        )
        self.assertEqual(data["ref"], "antigravity:a17e5a01")
        self.assertEqual(data["session_id"], ANTIGRAVITY_MAIN)
        self.assertEqual(data["cwd"], ANTIGRAVITY_PROJECT_ALPHA)
        self.assertFalse(data["archived"])
        self.assertEqual(data["total"], 4)
        self.assertEqual(data["returned"], 2)
        self.assertTrue(data["has_more"])
        self.assertEqual(
            [prompt["index"] for prompt in data["prompts"]], [1, 2]
        )
        self.assertEqual(data["prompts"][0]["text"], ANTIGRAVITY_PROMPTS[0])
        self.assertIsNotNone(data["prompts"][0]["timestamp"])

    def test_non_human_records_never_become_prompts(self) -> None:
        prompts = self.run_json(
            "prompts", "antigravity:a17e5a01", "--limit", "0"
        )
        texts = [prompt["text"] for prompt in prompts["prompts"]]
        self.assertEqual(texts, list(ANTIGRAVITY_PROMPTS))
        self.assertEqual(texts[2], "Tighten the digest tests.")
        for text in texts:
            self.assertNotIn("<USER_REQUEST>", text)
            self.assertNotIn("<ADDITIONAL_METADATA>", text)
            self.assertNotIn("<USER_SETTINGS_CHANGE>", text)
        for excluded in (
            "Synthetic system reminder",
            ANTIGRAVITY_SUBAGENT_PROMPT,
            ANTIGRAVITY_SHORT_PROMPT,
            ANTIGRAVITY_TOOL_OUTPUT_NEEDLE,
            "Synthetic warning that must not count.",
        ):
            self.assertFalse(
                any(excluded in text for text in texts), excluded
            )

    def test_cross_harness_isolation(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "antigravity-cli", ANTIGRAVITY_MAIN_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "antigravity", "cli-main-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "show", "antigravity-cli:%s" % ANTIGRAVITY_MAIN[:8]
        )
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli(
            "show", "antigravity:%s" % ANTIGRAVITY_CLI_MAIN[:8]
        )
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        sessions = self.run_json(
            "search", ANTIGRAVITY_MAIN_NEEDLE, "--limit", "0"
        )
        self.assertEqual(
            {session["ref"] for session in sessions},
            {"antigravity:a17e5a01"},
        )

    def test_empty_store_is_safe(self) -> None:
        for command in ("search", "latest"):
            code, out, err = self.run_cli(
                command,
                "--harness",
                "antigravity",
                antigravity_home=self.empty_antigravity_home,
                antigravity_ide_home=self.empty_antigravity_ide_home,
            )
            self.assertEqual(code, 0, err)
            self.assertIn("no sessions matched", out)

    def test_commands_do_not_modify_antigravity_store(self) -> None:
        homes = (
            self.antigravity_home,
            self.antigravity_ide_home,
            self.antigravity_cli_home,
        )

        def snapshot() -> dict:
            files = {}
            for home in homes:
                for path in home.rglob("*"):
                    if path.is_file():
                        files[str(path)] = (
                            path.read_bytes(),
                            path.stat().st_mtime_ns,
                        )
            return files

        before = snapshot()
        self.run_cli("search", "--harness", "antigravity")
        self.run_cli(
            "search", "--harness", "antigravity", "--include-archived"
        )
        self.run_cli(
            "search",
            "--harness",
            "antigravity",
            "--deep",
            ANTIGRAVITY_DEEP_NEEDLE,
        )
        self.run_cli("latest", "--harness", "antigravity")
        self.run_cli("show", "antigravity:a17e5a01")
        self.run_cli("show", "antigravity:a17e5a04", "--format", "json")
        self.run_cli("show", "antigravity:a17e5a06")
        self.run_cli("prompts", "antigravity:a17e5a01")
        self.run_cli("prompts", "antigravity:a17e5a01", "--count")
        self.run_cli("search", "--harness", "antigravity-cli")
        self.run_cli(
            "search",
            "--harness",
            "antigravity-cli",
            "--deep",
            ANTIGRAVITY_CLI_DEEP_NEEDLE,
        )
        self.run_cli("show", "antigravity-cli:%s" % ANTIGRAVITY_CLI_MAIN[:8])
        self.run_cli(
            "prompts", "antigravity-cli:%s" % ANTIGRAVITY_CLI_MAIN[:8]
        )
        self.assertEqual(snapshot(), before)
        self.assertFalse(
            any(
                path.name.endswith(("-wal", "-shm", "-journal"))
                for home in homes
                for path in home.rglob("*")
            )
        )

    def test_fixture_data_is_synthetic(self) -> None:
        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        for home in (
            self.antigravity_home,
            self.antigravity_ide_home,
            self.antigravity_cli_home,
        ):
            for path in home.rglob("*"):
                if not path.is_file():
                    continue
                text = path.read_bytes().decode("utf-8", "ignore")
                self.assertNotIn("/Volumes/", text)
                self.assertNotIn("/home/", text)
                self.assertNotIn(
                    "/Users/", text.replace("/Users/example/", "")
                )
                self.assertIsNone(email.search(text), str(path))
        for session_id in (
            ANTIGRAVITY_MAIN,
            ANTIGRAVITY_ARCHIVED,
            ANTIGRAVITY_NESTED,
            ANTIGRAVITY_MIGRATED,
            ANTIGRAVITY_ORPHAN,
            ANTIGRAVITY_METADATA,
            ANTIGRAVITY_DEEP,
            ANTIGRAVITY_IDE_ONLY,
            ANTIGRAVITY_ORPHAN_BRAIN,
        ):
            self.assertTrue(session_id.startswith("a17e5a"), session_id)
        for session_id in (
            ANTIGRAVITY_CLI_MAIN,
            ANTIGRAVITY_CLI_FALLBACK,
            ANTIGRAVITY_CLI_ORPHAN,
            ANTIGRAVITY_CLI_METADATA,
            ANTIGRAVITY_CLI_DEEP,
            ANTIGRAVITY_CLI_ORPHAN_BRAIN,
        ):
            self.assertTrue(session_id.startswith("c11a2b"), session_id)


class AntigravityCLITests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli(
            "show", *args, "--format", "json", **kwargs
        )
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_harness_row(self) -> None:
        rows = [
            row
            for row in self.run_json("harnesses")
            if row["name"] == "antigravity-cli"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "ready")
        self.assertEqual(rows[0]["variants"], "cli")
        self.assertEqual(rows[0]["store"], "~/.gemini/antigravity-cli")
        self.assertEqual(rows[0]["aliases"], "antigravity-cli, agy")

    def test_lists_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "antigravity-cli"
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("antigravity-cli:c11a2b01"))
        self.assertTrue(lines[1].startswith("antigravity-cli:c11a2b02"))
        self.assertTrue(lines[2].startswith("antigravity-cli:c11a2b05"))
        self.assertTrue(lines[3].startswith("antigravity-cli:c11a2b04"))
        self.assertNotIn("c11a2b03", out)
        self.assertNotIn("c11a2b99", out)

        sessions = self.run_json(
            "search", "--harness", "antigravity-cli", "c11a2b02"
        )
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["title"], ANTIGRAVITY_CLI_FALLBACK_PROMPT)

    def test_aliases_and_cwd(self) -> None:
        for alias in ("antigravity-cli", "agy"):
            sessions = self.run_json(
                "search", "--harness", alias, "--limit", "0"
            )
            self.assertEqual(len(sessions), 4)
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "agy",
            "--cwd",
            ANTIGRAVITY_PROJECT_CLI,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 5)

    def test_no_archive_state(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "antigravity-cli", "--include-archived"
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        for line in lines:
            self.assertEqual(line.split("\t")[-1], "-")

        data = self.show_json(
            "antigravity-cli:c11a2b01", "--messages", "0"
        )
        self.assertFalse(data["archived"])

        code, out, err = self.run_cli(
            "show", "antigravity-cli:c11a2b01"
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn("- archived: yes", out)

    def test_full_transcript_preference_and_deep_search(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "antigravity-cli",
            "--deep",
            ANTIGRAVITY_CLI_DEEP_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("antigravity-cli:c11a2b01", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "antigravity-cli",
            "--deep",
            ANTIGRAVITY_CLI_DB_ONLY_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("antigravity-cli:c11a2b04", out)
        self.assertNotIn("c11a2b01", out)

        for needle in (
            ANTIGRAVITY_CLI_SHORT_PROMPT,
            ANTIGRAVITY_CLI_HISTORY_NEEDLE,
            ANTIGRAVITY_CLI_PROTO_NEEDLE,
            "CLI orphan brain conversation",
        ):
            code, out, err = self.run_cli(
                "search",
                "--harness",
                "antigravity-cli",
                "--deep",
                needle,
            )
            self.assertEqual(code, 0, err)
            self.assertIn("no sessions matched", out, needle)

    def test_show_and_prompts(self) -> None:
        data = self.show_json(
            "antigravity-cli:c11a2b01", "--messages", "0"
        )
        self.assertEqual(data["session_id"], ANTIGRAVITY_CLI_MAIN)
        self.assertEqual(data["entrypoint"], "cli")
        self.assertEqual(data["variants"], "cli")
        self.assertEqual(data["title"], ANTIGRAVITY_CLI_TITLE_MAIN)
        self.assertEqual(data["cwd"], ANTIGRAVITY_PROJECT_CLI)
        self.assertEqual(data["first_prompt"], ANTIGRAVITY_CLI_PROMPTS[0])
        self.assertEqual(data["last_prompt"], ANTIGRAVITY_CLI_PROMPTS[-1])
        self.assertEqual(data["turn_count"], 3)
        self.assertEqual(data["started"], "2026-09-03T08:55:00Z")
        self.assertEqual(data["updated"], "2026-09-03T09:10:00Z")
        self.assertEqual(
            data["edited_files"],
            [
                {
                    "path": ANTIGRAVITY_PROJECT_CLI + "/docs/rollout.md",
                    "count": 1,
                }
            ],
        )
        self.assertEqual(
            data["tool_counts"], {"run_command": 1, "write_to_file": 1}
        )

        code, out, err = self.run_cli(
            "show", "antigravity-cli:c11a2b01", "--messages", "6"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("- harness: antigravity-cli (cli)", out)
        self.assertIn("- turns: 3", out)
        self.assertIn("## Edited files", out)
        self.assertIn("docs/rollout.md", out)
        self.assertIn("## Recent tools", out)
        self.assertIn("run_command", out)

        code, out, err = self.run_cli(
            "prompts", "antigravity-cli:c11a2b01", "--count"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "3")

        prompts = self.run_json(
            "prompts", "antigravity-cli:c11a2b01", "--limit", "0"
        )
        self.assertEqual(
            [prompt["text"] for prompt in prompts["prompts"]],
            list(ANTIGRAVITY_CLI_PROMPTS),
        )

        page = self.run_json(
            "prompts",
            "antigravity-cli:c11a2b01",
            "--order",
            "newest",
            "--limit",
            "1",
        )
        self.assertEqual([prompt["index"] for prompt in page["prompts"]], [3])
        self.assertTrue(page["has_more"])

    def test_metadata_only_and_orphans(self) -> None:
        data = self.show_json(
            "antigravity-cli:c11a2b04", "--messages", "0"
        )
        self.assertEqual(data["title"], ANTIGRAVITY_CLI_TITLE_METADATA)
        self.assertEqual(data["turn_count"], 0)
        self.assertEqual(data["first_prompt"], "")
        self.assertEqual(data["cwd"], ANTIGRAVITY_PROJECT_CLI)

        code, out, err = self.run_cli(
            "prompts", "antigravity-cli:c11a2b04", "--count"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "0")

        code, out, err = self.run_cli("show", "antigravity-cli:c11a2b03")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "antigravity-cli:c11a2b99")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_cross_store_isolation(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "antigravity", "cli-main-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "antigravity-cli", ANTIGRAVITY_MAIN_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "show", "antigravity:%s" % ANTIGRAVITY_CLI_MAIN[:8]
        )
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli(
            "show", "antigravity-cli:%s" % ANTIGRAVITY_MAIN[:8]
        )
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)
