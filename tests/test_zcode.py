from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from cli_support import FixtureTestCase
from zcode_fixture import (
    DISPLAY_ARCHIVED,
    DISPLAY_ARCHIVED_IN_PLACE,
    DISPLAY_CLI,
    DISPLAY_DELETED,
    DISPLAY_DESKTOP,
    PROMPTS_DESKTOP,
    SESSION_ARCHIVED,
    SESSION_DELETED,
    SESSION_DESKTOP,
    SESSION_SUBAGENT,
)


class ZCodeTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli(
            "show", *args, "--format", "json", **kwargs
        )
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_desktop_and_cli_share_one_harness(self) -> None:
        rows = self.run_json("harnesses")
        zcode_rows = [row for row in rows if row["name"] == "zcode"]
        self.assertEqual(len(zcode_rows), 1)
        self.assertEqual(zcode_rows[0]["status"], "ready")
        self.assertEqual(zcode_rows[0]["variants"], "desktop, cli")
        self.assertEqual(zcode_rows[0]["store"], "~/.zcode")
        self.assertEqual(zcode_rows[0]["aliases"], "zcode, z-code, zai")

        sessions = self.run_json(
            "search", "--harness", "zcode", "--limit", "0"
        )
        variants = {session["variants"] for session in sessions}
        self.assertEqual(variants, {"desktop", "cli"})

    def test_lists_active_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "zcode")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("zcode:c0de0002"))
        self.assertTrue(lines[1].startswith("zcode:c0de0001"))
        self.assertNotIn("c0de0006", out)

    def test_aliases(self) -> None:
        for alias in ("zcode", "z-code", "zai"):
            sessions = self.run_json(
                "search", "--harness", alias, "--limit", "0"
            )
            self.assertEqual(
                {session["ref"] for session in sessions},
                {"zcode:c0de0001", "zcode:c0de0002"},
            )

    def test_keyword_session_id_and_title_fallback(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "zcode", "handoff"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("zcode:c0de0001", out)
        self.assertNotIn("c0de0002", out)

        sessions = self.run_json(
            "search", "--harness", "zcode", "migration"
        )
        self.assertEqual([session["ref"] for session in sessions], ["zcode:c0de0002"])
        self.assertEqual(
            sessions[0]["title"], "Investigate the migration drift in project gamma."
        )

        sessions = self.run_json(
            "search", "--harness", "zcode", "c0de0002"
        )
        self.assertEqual([session["ref"] for session in sessions], ["zcode:c0de0002"])

        code, out, err = self.run_cli("show", "zcode:session_c0de0001")
        self.assertEqual(code, 0, err)
        self.assertIn("# zcode:c0de0001", out)

        code, out, err = self.run_cli("show", "zcode:sess_c0de0002")
        self.assertEqual(code, 0, err)
        self.assertIn("# zcode:c0de0002", out)

    def test_latest_and_query_filter(self) -> None:
        sessions = self.run_json("latest", "--harness", "zcode")
        self.assertEqual([session["ref"] for session in sessions], ["zcode:c0de0002"])
        self.assertEqual(sessions[0]["entrypoint"], "cli")
        self.assertEqual(sessions[0]["last_prompt"], "继续")

        sessions = self.run_json("latest", "--harness", "zcode", "handoff")
        self.assertEqual([session["ref"] for session in sessions], ["zcode:c0de0001"])
        self.assertEqual(sessions[0]["first_prompt"], PROMPTS_DESKTOP[0])
        self.assertEqual(sessions[0]["last_prompt"], PROMPTS_DESKTOP[-1])

        code, out, err = self.run_cli("latest", "--harness", "zcode", "no-such-topic")
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_cwd_since_limit_and_no_match(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "zcode", "--cwd", "/Users/example/project-alpha"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("zcode:c0de0001", out)
        self.assertNotIn("c0de0002", out)

        code, out, err = self.run_cli(
            "search", "--harness", "zcode", "--cwd", "/Users/example"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("zcode:c0de0001", out)
        self.assertIn("zcode:c0de0002", out)

        code, out, err = self.run_cli(
            "search", "--harness", "zcode", "--since", "2026-10-25"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("zcode:c0de0002", out)
        self.assertNotIn("c0de0001", out)

        code, out, err = self.run_cli(
            "search", "--harness", "zcode", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

        code, out, err = self.run_cli(
            "search", "--harness", "zcode", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_archived_and_deleted_are_hidden_by_default(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "zcode", "--limit", "0"
        )
        self.assertEqual(code, 0, err)
        for hidden in ("c0de0003", "c0de0004", "c0de0005", "c0de0006"):
            self.assertNotIn(hidden, out)

        code, out, err = self.run_cli(
            "search", "--harness", "zcode", "--include-archived", "--limit", "0"
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        marks = {
            parts[0]: parts[-1]
            for parts in (line.split("\t") for line in lines)
        }
        self.assertEqual(
            marks,
            {
                "zcode:c0de0002": "-",
                "zcode:c0de0005": "yes",
                "zcode:c0de0004": "yes",
                "zcode:c0de0003": "yes",
                "zcode:c0de0001": "-",
            },
        )
        self.assertNotIn("c0de0006", out)

    def test_archive_metadata_missing_degrades_to_active(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "zcode",
            "--limit",
            "0",
            zcode_app_db=self.no_app_db,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("zcode:c0de0003", out)
        self.assertIn("zcode:c0de0004", out)
        self.assertNotIn("c0de0005", out)

    def test_archive_state_does_not_cross_harnesses(self) -> None:
        sessions = self.run_json(
            "search", "--harness", "qoder-cn", "--include-archived", "--limit", "0"
        )
        refs = {session["ref"] for session in sessions}
        self.assertFalse(any(ref.startswith("zcode:") for ref in refs))

        code, out, err = self.run_cli(
            "show", "c0de0003", "--harness", "qoder-cn"
        )
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_deep_search_scans_only_the_matching_session(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "zcode", "deep-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "zcode", "--deep", "deep-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("zcode:c0de0002", out)
        self.assertNotIn("c0de0001", out)

        code, out, err = self.run_cli(
            "search", "--harness", "zcode", "--deep", "summarized"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("zcode:c0de0001", out)

    def test_deep_search_respects_archive_filter(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "zcode", "--deep", "archived-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "zcode",
            "--include-archived",
            "--deep",
            "archived-needle",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("zcode:c0de0003", out)

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli(
            "show", "zcode:c0de0001", "--messages", "2", "--chars", "120"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("# zcode:c0de0001", out)
        self.assertIn("- harness: zcode (desktop)", out)
        self.assertIn("- branch: `feature/handoff`", out)
        self.assertIn("- model: `zcode-synthetic-1`", out)
        self.assertIn("- turns: 5", out)
        self.assertIn("## Task", out)
        self.assertIn(PROMPTS_DESKTOP[0][:60], out)
        self.assertIn("## Latest request", out)
        self.assertIn(PROMPTS_DESKTOP[-1], out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn("Handoff parser work summarized.", out)
        self.assertIn("## Todos (2 open / 3 total)", out)
        self.assertIn("- [pending] Refactor handoff parser", out)
        self.assertIn("- [in_progress] Document compaction fallback", out)
        self.assertIn("src/handoff.ts` (x2)", out)
        self.assertIn("docs/handoff.md", out)
        self.assertIn("[API error] exceed quota limit", out)
        self.assertNotIn("You have not used the TodoWrite", out)
        self.assertNotIn("This hidden row must not appear.", out)

    def test_show_json_fields(self) -> None:
        data = self.show_json("zcode:c0de0001", "--messages", "0")
        self.assertEqual(data["ref"], "zcode:c0de0001")
        self.assertEqual(data["session_id"], DISPLAY_DESKTOP)
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertEqual(data["entrypoint"], "desktop")
        self.assertEqual(data["variants"], "desktop")
        self.assertEqual(data["version"], "0.17.0")
        self.assertEqual(data["size_bytes"], 0)
        self.assertFalse(data["archived"])
        self.assertEqual(data["compact_summary"], "Handoff parser work summarized.")
        self.assertEqual(data["turn_count"], 5)
        self.assertEqual(
            data["todos"],
            [
                {"subject": "Refactor handoff parser", "status": "pending"},
                {"subject": "Document compaction fallback", "status": "in_progress"},
                {"subject": "Trim digest output", "status": "completed"},
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
            ],
        )
        self.assertEqual(
            data["tool_counts"], {"Edit": 2, "Read": 1, "Write": 1, "Bash": 1}
        )
        self.assertEqual(
            data["path"], str(self.zcode_home / "cli" / "db" / "db.sqlite")
            + "#" + SESSION_DESKTOP
        )

    def test_show_by_virtual_source_path(self) -> None:
        data = self.show_json("zcode:c0de0001", "--messages", "0")
        source = data["path"]
        self.assertTrue(source.endswith("#" + SESSION_DESKTOP))

        code, out, err = self.run_cli("show", source)
        self.assertEqual(code, 0, err)
        self.assertIn("# zcode:c0de0001", out)

        code, out, err = self.run_cli("prompts", source, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "5")

    def test_compaction_part_fallback(self) -> None:
        data = self.show_json("zcode:c0de0002", "--messages", "0")
        self.assertEqual(
            data["compact_summary"],
            "Compaction fallback summary for project gamma.",
        )

    def test_show_archived_session(self) -> None:
        code, out, err = self.run_cli("show", "zcode:c0de0003")
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)

        data = self.show_json("zcode:c0de0005")
        self.assertTrue(data["archived"])

    def test_show_missing_and_ambiguous_refs(self) -> None:
        code, out, err = self.run_cli("show", "zcode:c0dfffff")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "zcode:c0de0006")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "zcode:c0de")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", err)

        code, out, err = self.run_cli("show", "zcode:c0")
        self.assertEqual(code, 2)
        self.assertIn("too short", err)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli("prompts", "zcode:c0de0001", "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "5")

        code, out, err = self.run_cli("prompts", "zcode:c0de0001")
        self.assertEqual(code, 0, err)
        for index, prompt in enumerate(PROMPTS_DESKTOP, 1):
            self.assertIn("## %d" % index, out)
            self.assertIn(prompt, out)
        self.assertNotIn("You have not used the TodoWrite", out)
        self.assertNotIn("Handoff parser work summarized.", out)
        self.assertNotIn("This hidden row must not appear.", out)

        code, out, err = self.run_cli(
            "prompts", "zcode:c0de0001", "--offset", "1", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("## 2", out)
        self.assertIn("## 3", out)
        self.assertNotIn(PROMPTS_DESKTOP[0], out)
        self.assertIn("next: --offset 3 --limit 2", out)

        code, out, err = self.run_cli(
            "prompts", "zcode:c0de0001", "--order", "newest", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("## 5"), out.index("## 4"))
        self.assertNotIn("## 3", out)

        code, out, err = self.run_cli(
            "prompts", "zcode:c0de0001", "--offset", "9"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts", "zcode:c0de0001", "--limit", "1", "--chars", "10"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Please re…", out)
        self.assertNotIn(PROMPTS_DESKTOP[0], out)

    def test_prompts_json_and_archived(self) -> None:
        data = self.run_json("prompts", "zcode:c0de0001", "--limit", "2")
        self.assertEqual(data["ref"], "zcode:c0de0001")
        self.assertEqual(data["session_id"], DISPLAY_DESKTOP)
        self.assertIn("#" + SESSION_DESKTOP, data["path"])
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertFalse(data["archived"])
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["offset"], 0)
        self.assertEqual(data["limit"], 2)
        self.assertEqual(data["returned"], 2)
        self.assertTrue(data["has_more"])
        self.assertEqual([prompt["index"] for prompt in data["prompts"]], [1, 2])
        self.assertEqual(data["prompts"][0]["text"], PROMPTS_DESKTOP[0])
        self.assertEqual(data["prompts"][0]["timestamp"], '2026-10-20T09:10:00Z')

        data = self.run_json("prompts", "zcode:c0de0003", "--count")
        self.assertTrue(data["archived"])
        self.assertEqual(data["total"], 1)

    def test_empty_store_is_safe(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "zcode",
            zcode_home=self.empty_zcode_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "latest",
            "--harness",
            "zcode",
            zcode_home=self.empty_zcode_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_commands_do_not_modify_zcode_store(self) -> None:
        def snapshot() -> dict:
            files = {}
            for path in self.zcode_home.rglob("*"):
                if path.is_file():
                    files[str(path)] = (
                        path.read_bytes(),
                        path.stat().st_mtime_ns,
                    )
            return files

        before = snapshot()
        self.run_cli_checked("search", "--harness", "zcode")
        self.run_cli_checked("search", "--harness", "zcode", "--include-archived")
        self.run_cli_checked("search", "--harness", "zcode", "--deep", "deep-only-needle")
        self.run_cli_checked("latest", "--harness", "zcode")
        self.run_cli_checked("show", "zcode:c0de0001")
        self.run_cli_checked("show", "zcode:c0de0003", "--format", "json")
        self.run_cli_checked("prompts", "zcode:c0de0001")
        self.run_cli_checked("prompts", "zcode:c0de0001", "--count")
        self.assertEqual(snapshot(), before)
        self.assertFalse(
            any(
                path.name.endswith(("-wal", "-shm", "-journal"))
                for path in self.zcode_home.rglob("*")
            )
        )

    def test_fixture_data_is_synthetic(self) -> None:
        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        for path in self.zcode_home.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8", "ignore")
            self.assertNotIn(str(Path.home()), text)
            self.assertNotIn("/Volumes/", text)
            self.assertNotIn("/home/", text)
            self.assertNotIn("/Users/", text.replace("/Users/example/", ""))
            self.assertIsNone(email.search(text), str(path))

        connection = sqlite3.connect(
            (self.zcode_home / "cli" / "db" / "db.sqlite").as_uri() + "?mode=ro",
            uri=True,
        )
        try:
            ids = [row[0] for row in connection.execute("SELECT id FROM session")]
        finally:
            connection.close()
        self.assertEqual(len(ids), 6)
        for session_id in ids:
            self.assertTrue(
                session_id.startswith(
                    ("session_c0de", "sess_c0de", "sess_subagent_agent_c0de")
                ),
                session_id,
            )

        app = sqlite3.connect(
            (self.zcode_home / "v2" / "tasks-index.sqlite").as_uri() + "?mode=ro",
            uri=True,
        )
        try:
            task_ids = [row[0] for row in app.execute("SELECT task_id FROM tasks")]
        finally:
            app.close()
        self.assertEqual(
            sorted(task_ids), sorted((SESSION_ARCHIVED, SESSION_DELETED))
        )

    def test_deleted_and_subagent_sessions_are_absent(self) -> None:
        sessions = self.run_json(
            "search", "--harness", "zcode", "--include-archived", "--limit", "0"
        )
        session_ids = {session["session_id"] for session in sessions}
        self.assertNotIn(SESSION_SUBAGENT, session_ids)
        self.assertEqual(
            session_ids,
            {
                DISPLAY_DESKTOP,
                DISPLAY_CLI,
                DISPLAY_ARCHIVED,
                DISPLAY_DELETED,
                DISPLAY_ARCHIVED_IN_PLACE,
            },
        )
