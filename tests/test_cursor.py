from __future__ import annotations

import json
import re
from pathlib import Path

from cli_support import FixtureTestCase
from cursor_fixture import (
    NEEDLE_ARCHIVED as CURSOR_ARCHIVED_NEEDLE,
    NEEDLE_DECOY as CURSOR_DECOY_NEEDLE,
    NEEDLE_DEEP_ONLY as CURSOR_DEEP_ONLY_NEEDLE,
    NEEDLE_INJECTED as CURSOR_INJECTED_NEEDLE,
    NEEDLE_SUBAGENT as CURSOR_SUBAGENT_NEEDLE,
    OVERVIEW as CURSOR_OVERVIEW,
    PROJECT_ALPHA as CURSOR_PROJECT_ALPHA,
    PROMPTS_MAIN as CURSOR_PROMPTS,
    PROMPT_PLAIN as CURSOR_PLAIN_PROMPT,
    SESSION_ARCHIVED as CURSOR_ARCHIVED,
    SESSION_EMPTY as CURSOR_EMPTY,
    SESSION_MAIN as CURSOR_MAIN,
    TITLE_ARCHIVED as CURSOR_TITLE_ARCHIVED,
    TITLE_MAIN as CURSOR_TITLE_MAIN,
    build_cursor_home,
)


class CursorTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli("show", *args, "--format", "json", **kwargs)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_harness_row(self) -> None:
        rows = self.run_json("harnesses")
        rows = [row for row in rows if row["name"] == "cursor"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "ready")
        self.assertEqual(rows[0]["variants"], "desktop, cli")
        self.assertEqual(rows[0]["store"], "~/.cursor/projects")
        self.assertEqual(
            rows[0]["aliases"], "cursor, cursor-agent, cursor-ide"
        )

    def test_lists_active_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "cursor")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("cursor:f1c00002"))
        self.assertTrue(lines[1].startswith("cursor:f1c00006"))
        self.assertTrue(lines[2].startswith("cursor:f1c00001"))
        self.assertTrue(lines[3].startswith("cursor:f1c00004"))
        self.assertNotIn("f1c00003", out)
        self.assertNotIn("f1c00005", out)
        self.assertNotIn("f1c00007", out)
        self.assertNotIn("f1c00008", out)

    def test_aliases(self) -> None:
        for alias in ("cursor", "cursor-agent", "cursor-ide"):
            sessions = self.run_json(
                "search", "--harness", alias, "--limit", "0"
            )
            self.assertEqual(len(sessions), 4)
            self.assertTrue(
                all(session["ref"].startswith("cursor:") for session in sessions)
            )

    def test_keyword_id_cwd_since_limit_and_no_match(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "cursor", "handoff")
        self.assertEqual(code, 0, err)
        self.assertIn("cursor:f1c00001", out)
        self.assertNotIn("cursor:f1c00002", out)

        sessions = self.run_json("search", "--harness", "cursor", "f1c00002")
        self.assertEqual(
            [session["ref"] for session in sessions], ["cursor:f1c00002"]
        )

        code, out, err = self.run_cli(
            "search", "--harness", "cursor", "--cwd", CURSOR_PROJECT_ALPHA
        )
        self.assertEqual(code, 0, err)
        self.assertIn("cursor:f1c00001", out)
        self.assertNotIn("cursor:f1c00004", out)

        code, out, err = self.run_cli(
            "search", "--harness", "cursor", "--cwd", "/Users/example"
        )
        self.assertEqual(code, 0, err)
        for ref in ("cursor:f1c00001", "cursor:f1c00002", "cursor:f1c00004"):
            self.assertIn(ref, out)

        code, out, err = self.run_cli(
            "search", "--harness", "cursor", "--since", "2026-10-25"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("cursor:f1c00002", out)
        self.assertNotIn("cursor:f1c00001", out)

        code, out, err = self.run_cli(
            "search", "--harness", "cursor", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

        code, out, err = self.run_cli(
            "search", "--harness", "cursor", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_latest_and_query_filter(self) -> None:
        code, out, err = self.run_cli("latest", "--harness", "cursor")
        self.assertEqual(code, 0, err)
        self.assertTrue(
            out.strip().splitlines()[1].startswith("cursor:f1c00002")
        )

        code, out, err = self.run_cli("latest", "--harness", "cursor", "handoff")
        self.assertEqual(code, 0, err)
        self.assertTrue(
            out.strip().splitlines()[1].startswith("cursor:f1c00001")
        )

    def test_archived_is_hidden_by_default(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "cursor")
        self.assertEqual(code, 0, err)
        self.assertNotIn(CURSOR_ARCHIVED[:8], out)
        self.assertNotIn(CURSOR_EMPTY[:8], out)

        code, out, err = self.run_cli(
            "search", "--harness", "cursor", "--include-archived"
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 6)
        archived_lines = [line for line in lines if line.endswith("\tyes")]
        self.assertEqual(len(archived_lines), 2)

    def test_deep_search_scans_content(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "cursor", "--deep", CURSOR_DEEP_ONLY_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("cursor:f1c00002", out)
        self.assertNotIn("cursor:f1c00001", out)

        code, out, err = self.run_cli(
            "search", "--harness", "cursor", CURSOR_DEEP_ONLY_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_deep_search_respects_archive_and_subagent(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "cursor", "--deep", CURSOR_SUBAGENT_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "cursor", "--deep", CURSOR_DECOY_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "cursor", "--deep", CURSOR_ARCHIVED_NEEDLE
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "cursor",
            "--deep",
            "--include-archived",
            CURSOR_ARCHIVED_NEEDLE,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("cursor:f1c00003", out)
        self.assertNotIn("cursor:f1c00001", out)

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli("show", "cursor:f1c00001")
        self.assertEqual(code, 0, err)
        self.assertIn("- harness: cursor (desktop, cli)", out)
        self.assertIn("- cwd: `%s`" % CURSOR_PROJECT_ALPHA, out)
        self.assertIn("- branch: `feature/handoff`", out)
        self.assertIn("- turns: 4", out)
        self.assertIn("Compact summary", out)
        self.assertIn("Add prompt paging", out)
        self.assertIn("src/adapter.py", out)
        self.assertIn("todo_write", out)

    def test_show_json_fields(self) -> None:
        data = self.show_json("cursor:f1c00001")
        self.assertEqual(data["ref"], "cursor:f1c00001")
        self.assertEqual(data["harness"], "cursor")
        self.assertEqual(data["session_id"], CURSOR_MAIN)
        self.assertEqual(data["cwd"], CURSOR_PROJECT_ALPHA)
        self.assertEqual(data["title"], CURSOR_TITLE_MAIN)
        self.assertEqual(data["branch"], "feature/handoff")
        self.assertEqual(data["turn_count"], 4)
        self.assertFalse(data["archived"])
        self.assertEqual(data["variants"], "desktop, cli")
        self.assertIn(CURSOR_OVERVIEW.splitlines()[0], data["compact_summary"])
        self.assertEqual(len(data["todos"]), 2)
        self.assertEqual(
            {todo["status"] for todo in data["todos"]},
            {"completed", "in_progress"},
        )
        self.assertEqual(data["tool_counts"]["read_file"], 1)
        self.assertEqual(data["tool_counts"]["edit_file"], 1)
        self.assertTrue(data["edited_files"])
        self.assertTrue(data["recent_tools"])
        self.assertTrue(data["first_prompt"])
        self.assertTrue(data["last_prompt"])
        self.assertTrue(data["updated"])
        self.assertTrue(data["started"])

    def test_show_by_source_path(self) -> None:
        path = (
            self.cursor_home
            / "projects"
            / "Users-example-project-alpha"
            / "agent-transcripts"
            / CURSOR_MAIN
            / (CURSOR_MAIN + ".jsonl")
        )
        data = self.show_json(str(path))
        self.assertEqual(data["ref"], "cursor:f1c00001")

    def test_show_by_bare_prefix(self) -> None:
        data = self.show_json("f1c00001")
        self.assertEqual(data["ref"], "cursor:f1c00001")

        data = self.show_json("f1c00001", "--harness", "cursor")
        self.assertEqual(data["ref"], "cursor:f1c00001")

    def test_show_archived_session(self) -> None:
        code, out, err = self.run_cli("show", "cursor:f1c00003")
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)

        data = self.show_json("cursor:f1c00003")
        self.assertTrue(data["archived"])
        self.assertEqual(data["title"], CURSOR_TITLE_ARCHIVED)

    def test_show_missing_ambiguous_and_too_short_refs(self) -> None:
        code, out, err = self.run_cli("show", "cursor:zzzzzzzz")
        self.assertNotEqual(code, 0)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "c0d")
        self.assertNotEqual(code, 0)
        self.assertIn("too short", err)

        code, out, err = self.run_cli("show", "cursor:f1c0")
        self.assertNotEqual(code, 0)
        self.assertIn("ambiguous", err)

    def test_subagent_session_is_excluded(self) -> None:
        code, out, err = self.run_cli("show", "cursor:f1c00007")
        self.assertNotEqual(code, 0)
        self.assertIn("no session matched", err)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli("prompts", "cursor:f1c00001", "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "4")

        code, out, err = self.run_cli(
            "prompts", "cursor:f1c00001", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("total: 4, returned: 2", out)
        self.assertIn(CURSOR_PROMPTS[0], out)
        self.assertNotIn(CURSOR_PROMPTS[3], out)

        code, out, err = self.run_cli(
            "prompts", "cursor:f1c00001", "--order", "newest", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("order: newest", out)
        self.assertIn(CURSOR_PROMPTS[3], out)
        self.assertNotIn(CURSOR_PROMPTS[0], out)

        code, out, err = self.run_cli(
            "prompts", "cursor:f1c00001", "--offset", "10"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

    def test_prompts_json_and_archived(self) -> None:
        data = self.run_json("prompts", "cursor:f1c00001")
        self.assertEqual(data["total"], 4)
        self.assertEqual(data["returned"], 4)
        self.assertEqual(data["order"], "oldest")
        self.assertFalse(data["archived"])
        self.assertEqual(data["prompts"][0]["text"], CURSOR_PROMPTS[0])
        self.assertTrue(data["prompts"][0]["timestamp"])

        archived = self.run_json("prompts", "cursor:f1c00003")
        self.assertTrue(archived["archived"])
        self.assertEqual(archived["total"], 1)

        capped = self.run_json(
            "prompts", "cursor:f1c00001", "--chars", "10"
        )
        self.assertLessEqual(len(capped["prompts"][0]["text"]), 10)

    def test_non_human_records_never_become_prompts(self) -> None:
        data = self.run_json("prompts", "cursor:f1c00002")
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["prompts"][0]["text"], CURSOR_PLAIN_PROMPT)
        self.assertNotIn(CURSOR_INJECTED_NEEDLE, json.dumps(data))

        archived = self.run_json("prompts", "cursor:f1c00003")
        self.assertEqual(archived["total"], 1)
        self.assertNotIn("summary_request", json.dumps(archived))

    def test_empty_session_prompts(self) -> None:
        code, out, err = self.run_cli("prompts", "cursor:f1c00004", "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "0")

        code, out, err = self.run_cli("prompts", "cursor:f1c00004")
        self.assertEqual(code, 0, err)
        self.assertIn("no user prompts", out)

    def test_json_transcript_variant(self) -> None:
        data = self.show_json("cursor:f1c00006")
        self.assertEqual(data["turn_count"], 1)
        self.assertIn("Document the Cursor store.", data["first_prompt"])
        self.assertEqual(data["tool_counts"]["write_file"], 1)
        self.assertTrue(data["edited_files"])

    def test_missing_index_degrades_to_all_active(self) -> None:
        sessions = self.run_json(
            "search",
            "--harness",
            "cursor",
            "--limit",
            "0",
            cursor_app_db=self.no_cursor_db,
        )
        self.assertEqual(len(sessions), 6)
        self.assertTrue(all(session["archived"] is False for session in sessions))

    def test_empty_store_is_safe(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "cursor",
            cursor_home=self.empty_cursor_home,
            cursor_app_db=self.no_cursor_db,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "doctor", "--harness", "cursor", cursor_home=self.empty_cursor_home
        )
        self.assertEqual(code, 0, err)
        self.assertIn("candidates: 0", out)

    def test_commands_do_not_modify_cursor_store(self) -> None:
        def snapshot():
            state = {}
            for path in sorted(self.cursor_home.rglob("*")):
                if not path.is_file():
                    continue
                stat = path.stat()
                state[str(path)] = (stat.st_size, stat.st_mtime_ns)
            return state

        before = snapshot()
        for args in (
            ("search", "--harness", "cursor"),
            ("search", "--harness", "cursor", "--include-archived"),
            ("search", "--harness", "cursor", "--deep", CURSOR_DEEP_ONLY_NEEDLE),
            ("latest", "--harness", "cursor"),
            ("show", "cursor:f1c00001"),
            ("prompts", "cursor:f1c00001", "--count"),
            ("doctor", "--harness", "cursor"),
        ):
            self.run_cli(*args)
        after = snapshot()
        self.assertEqual(before, after)
        self.assertFalse(list(self.cursor_home.rglob("*-wal")))
        self.assertFalse(list(self.cursor_home.rglob("*-shm")))

    def test_fixture_data_is_synthetic(self) -> None:
        patterns = [
            re.compile(r"@[\w.-]+\.(?:com|net|org|io|ai)\b"),
            re.compile(r"/Users/(?!example)[A-Za-z0-9._-]+"),
            re.compile(r"/Volumes/"),
            re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
            re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        ]
        for path in self.cursor_home.rglob("*"):
            if not path.is_file() or path.suffix == ".sqlite":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in patterns:
                self.assertIsNone(
                    pattern.search(text),
                    "unexpected data in %s: %s" % (path, pattern.pattern),
                )

    def test_store_builder_is_reusable(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="fms-cursor-") as tmp:
            home = build_cursor_home(Path(tmp) / "cursor-home")
            sessions = self.run_json(
                "search",
                "--harness",
                "cursor",
                "--limit",
                "0",
                cursor_home=home,
                cursor_app_db=(
                    home / "User" / "globalStorage" / "conversation-search.db"
                ),
            )
            self.assertEqual(len(sessions), 4)
