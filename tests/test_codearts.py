from __future__ import annotations

import json
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

from cli_support import FixtureTestCase
from codearts_fixture import (
    DISPLAY_ARCHIVED as CODEARTS_DISPLAY_ARCHIVED,
    DISPLAY_MAIN as CODEARTS_DISPLAY_MAIN,
    DISPLAY_PLAIN as CODEARTS_DISPLAY_PLAIN,
    PROMPTS_MAIN as CODEARTS_PROMPTS,
    SESSION_CHILD as CODEARTS_CHILD,
    SESSION_MAIN as CODEARTS_MAIN,
)


class CodeArtsAgentTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli(
            "show", *args, "--format", "json", **kwargs
        )
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_harness_row(self) -> None:
        rows = self.run_json("harnesses")
        codearts_rows = [row for row in rows if row["name"] == "codearts-agent"]
        self.assertEqual(len(codearts_rows), 1)
        self.assertEqual(codearts_rows[0]["status"], "ready")
        self.assertEqual(codearts_rows[0]["variants"], "desktop")
        self.assertEqual(codearts_rows[0]["store"], "~/.codeartsdoer")
        self.assertEqual(
            codearts_rows[0]["aliases"],
            "codearts-agent, codearts, codeartsdoer, codearts-doer",
        )
        planned = {row["name"] for row in rows if row["status"] == "planned"}
        self.assertNotIn("codearts-agent", planned)

    def test_lists_active_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "codearts-agent")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("codearts-agent:c0de1002"))
        self.assertTrue(lines[1].startswith("codearts-agent:c0de1001"))
        self.assertNotIn("c0de1003", out)
        self.assertNotIn("c0de1004", out)

    def test_aliases(self) -> None:
        for alias in ("codearts-agent", "codearts", "codeartsdoer", "codearts-doer"):
            sessions = self.run_json(
                "search", "--harness", alias, "--limit", "0"
            )
            self.assertEqual(
                {session["ref"] for session in sessions},
                {"codearts-agent:c0de1001", "codearts-agent:c0de1002"},
            )

    def test_keyword_session_id_and_title_fallback(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "codearts-agent", "handoff"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codearts-agent:c0de1001", out)
        self.assertNotIn("c0de1002", out)

        sessions = self.run_json(
            "search", "--harness", "codearts-agent", "migration"
        )
        self.assertEqual(
            [session["ref"] for session in sessions], ["codearts-agent:c0de1002"]
        )
        self.assertEqual(
            sessions[0]["title"],
            "Investigate the migration drift in project gamma.",
        )

        sessions = self.run_json(
            "search", "--harness", "codearts-agent", "c0de1002"
        )
        self.assertEqual(
            [session["ref"] for session in sessions], ["codearts-agent:c0de1002"]
        )

        code, out, err = self.run_cli("show", "codearts-agent:ses_c0de1001")
        self.assertEqual(code, 0, err)
        self.assertIn("# codearts-agent:c0de1001", out)

    def test_latest_and_query_filter(self) -> None:
        sessions = self.run_json("latest", "--harness", "codearts-agent")
        self.assertEqual(
            [session["ref"] for session in sessions], ["codearts-agent:c0de1002"]
        )
        self.assertEqual(sessions[0]["entrypoint"], "desktop")
        self.assertEqual(sessions[0]["variants"], "desktop")
        self.assertEqual(sessions[0]["last_prompt"], CODEARTS_PROMPTS[1])

        sessions = self.run_json(
            "latest", "--harness", "codearts-agent", "handoff"
        )
        self.assertEqual(
            [session["ref"] for session in sessions], ["codearts-agent:c0de1001"]
        )
        self.assertEqual(sessions[0]["first_prompt"], CODEARTS_PROMPTS[0])
        self.assertEqual(sessions[0]["last_prompt"], CODEARTS_PROMPTS[4])

        code, out, err = self.run_cli(
            "latest", "--harness", "codearts-agent", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_cwd_since_limit_and_no_match(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "codearts-agent",
            "--cwd",
            "/Users/example/project-alpha",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codearts-agent:c0de1001", out)
        self.assertNotIn("c0de1002", out)

        code, out, err = self.run_cli(
            "search", "--harness", "codearts-agent", "--cwd", "/Users/example"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codearts-agent:c0de1001", out)
        self.assertIn("codearts-agent:c0de1002", out)

        code, out, err = self.run_cli(
            "search", "--harness", "codearts-agent", "--since", "2026-10-25"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codearts-agent:c0de1002", out)
        self.assertNotIn("c0de1001", out)

        code, out, err = self.run_cli(
            "search", "--harness", "codearts-agent", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

        code, out, err = self.run_cli(
            "search", "--harness", "codearts-agent", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_archived_sessions_hidden_by_default(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "codearts-agent", "--limit", "0"
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn("c0de1003", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "codearts-agent",
            "--include-archived",
            "--limit",
            "0",
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        marks = {
            parts[0]: parts[-1] for parts in (line.split("\t") for line in lines)
        }
        self.assertEqual(
            marks,
            {
                "codearts-agent:c0de1002": "-",
                "codearts-agent:c0de1003": "yes",
                "codearts-agent:c0de1001": "-",
            },
        )
        self.assertNotIn("c0de1004", out)

    def test_archive_state_does_not_cross_harnesses(self) -> None:
        sessions = self.run_json(
            "search", "--harness", "qoder-cn", "--include-archived", "--limit", "0"
        )
        refs = {session["ref"] for session in sessions}
        self.assertFalse(any(ref.startswith("codearts-agent:") for ref in refs))

        code, out, err = self.run_cli(
            "show", "c0de1003", "--harness", "qoder-cn"
        )
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_deep_search_scans_only_the_matching_session(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "codearts-agent", "deep-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "codearts-agent", "--deep", "deep-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codearts-agent:c0de1002", out)
        self.assertNotIn("c0de1001", out)

    def test_deep_search_respects_archive_filter(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "codearts-agent", "--deep", "archived-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "codearts-agent",
            "--include-archived",
            "--deep",
            "archived-needle",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codearts-agent:c0de1003", out)

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli(
            "show", "codearts-agent:c0de1001", "--messages", "2", "--chars", "120"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("# codearts-agent:c0de1001", out)
        self.assertIn("- harness: codearts-agent (desktop)", out)
        self.assertIn("- branch: `feature/handoff`", out)
        self.assertIn("- model: `codearts-synthetic-1`", out)
        self.assertIn("- turns: 5", out)
        self.assertIn("## Task", out)
        self.assertIn(CODEARTS_PROMPTS[0][:60], out)
        self.assertIn("## Latest request", out)
        self.assertIn(CODEARTS_PROMPTS[4], out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn("Handoff parser work summarized.", out)
        self.assertIn("## Todos (2 open / 3 total)", out)
        self.assertIn("- [pending] Refactor handoff digest", out)
        self.assertIn("- [in_progress] Document compaction fallback", out)
        self.assertIn("src/handoff.ts` (x3)", out)
        self.assertIn("docs/handoff.md", out)
        self.assertIn("[API error] exceed quota limit", out)
        self.assertNotIn("You have not used the TodoWrite", out)
        self.assertNotIn("Always answer in the project language", out)

    def test_show_json_fields(self) -> None:
        data = self.show_json("codearts-agent:c0de1001", "--messages", "0")
        self.assertEqual(data["ref"], "codearts-agent:c0de1001")
        self.assertEqual(data["session_id"], CODEARTS_DISPLAY_MAIN)
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertEqual(data["branch"], "feature/handoff")
        self.assertEqual(data["entrypoint"], "desktop")
        self.assertEqual(data["variants"], "desktop")
        self.assertEqual(data["version"], "1.0.0-synthetic")
        self.assertEqual(data["size_bytes"], 0)
        self.assertFalse(data["archived"])
        self.assertEqual(data["compact_summary"], "Handoff parser work summarized.")
        self.assertEqual(data["turn_count"], 5)
        self.assertEqual(
            data["todos"],
            [
                {"subject": "Refactor handoff digest", "status": "pending"},
                {"subject": "Document compaction fallback", "status": "in_progress"},
                {"subject": "Trim digest output", "status": "completed"},
            ],
        )
        # Edited files are ordered by the most recent edit, so the file touched
        # by the final tool call comes last.
        self.assertEqual(
            data["edited_files"],
            [
                {
                    "path": "/Users/example/project-alpha/docs/handoff.md",
                    "count": 1,
                },
                {
                    "path": "/Users/example/project-alpha/src/handoff.ts",
                    "count": 3,
                },
            ],
        )
        self.assertEqual(
            data["tool_counts"], {"edit": 3, "bash": 2, "read": 1, "write": 1}
        )
        self.assertEqual(
            data["path"],
            str(self.codearts_home / "codearts-data" / "opencode.db")
            + "#"
            + CODEARTS_MAIN,
        )

    def test_show_by_virtual_source_path(self) -> None:
        data = self.show_json("codearts-agent:c0de1001", "--messages", "0")
        source = data["path"]
        self.assertTrue(source.endswith("#" + CODEARTS_MAIN))

        code, out, err = self.run_cli("show", source)
        self.assertEqual(code, 0, err)
        self.assertIn("# codearts-agent:c0de1001", out)

        code, out, err = self.run_cli("prompts", source, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "5")

    def test_show_archived_session(self) -> None:
        code, out, err = self.run_cli("show", "codearts-agent:c0de1003")
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)

        data = self.show_json("codearts-agent:c0de1003")
        self.assertTrue(data["archived"])

    def test_bare_prefix_resolves_across_harnesses(self) -> None:
        code, out, err = self.run_cli("show", "c0de1001")
        self.assertEqual(code, 0, err)
        self.assertIn("# codearts-agent:c0de1001", out)

    def test_show_missing_and_ambiguous_refs(self) -> None:
        code, out, err = self.run_cli("show", "codearts-agent:c0dfffff")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "codearts-agent:c0de1004")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "codearts-agent:c0de")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", err)

        code, out, err = self.run_cli("show", "codearts-agent:c0")
        self.assertEqual(code, 2)
        self.assertIn("too short", err)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli(
            "prompts", "codearts-agent:c0de1001", "--count"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "5")

        code, out, err = self.run_cli("prompts", "codearts-agent:c0de1001")
        self.assertEqual(code, 0, err)
        for index, prompt in enumerate(CODEARTS_PROMPTS, 1):
            self.assertIn("## %d" % index, out)
            self.assertIn(prompt, out)
        self.assertNotIn("You have not used the TodoWrite", out)
        self.assertNotIn("Handoff parser work summarized.", out)
        self.assertNotIn("Always answer in the project language", out)

        code, out, err = self.run_cli(
            "prompts", "codearts-agent:c0de1001", "--offset", "1", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("## 2", out)
        self.assertIn("## 3", out)
        self.assertNotIn(CODEARTS_PROMPTS[0], out)
        self.assertIn("next: --offset 3 --limit 2", out)

        code, out, err = self.run_cli(
            "prompts", "codearts-agent:c0de1001", "--order", "newest", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("## 5"), out.index("## 4"))
        self.assertNotIn("## 3", out)

        code, out, err = self.run_cli(
            "prompts", "codearts-agent:c0de1001", "--offset", "9"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts", "codearts-agent:c0de1001", "--limit", "1", "--chars", "10"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Please re…", out)
        self.assertNotIn(CODEARTS_PROMPTS[0], out)

    def test_prompts_json_and_archived(self) -> None:
        data = self.run_json(
            "prompts", "codearts-agent:c0de1001", "--limit", "2"
        )
        self.assertEqual(data["ref"], "codearts-agent:c0de1001")
        self.assertEqual(data["session_id"], CODEARTS_DISPLAY_MAIN)
        self.assertIn("#" + CODEARTS_MAIN, data["path"])
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertFalse(data["archived"])
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["offset"], 0)
        self.assertEqual(data["limit"], 2)
        self.assertEqual(data["returned"], 2)
        self.assertTrue(data["has_more"])
        self.assertEqual([prompt["index"] for prompt in data["prompts"]], [1, 2])
        self.assertEqual(data["prompts"][0]["text"], CODEARTS_PROMPTS[0])
        self.assertEqual(data["prompts"][0]["timestamp"], '2026-10-20T09:10:00Z')

        data = self.run_json("prompts", "codearts-agent:c0de1003", "--count")
        self.assertTrue(data["archived"])
        self.assertEqual(data["total"], 1)

    def test_child_session_is_never_listed(self) -> None:
        sessions = self.run_json(
            "search", "--harness", "codearts-agent", "--include-archived", "--limit", "0"
        )
        session_ids = {session["session_id"] for session in sessions}
        self.assertNotIn(CODEARTS_CHILD, session_ids)
        self.assertEqual(
            session_ids,
            {
                CODEARTS_DISPLAY_MAIN,
                CODEARTS_DISPLAY_PLAIN,
                CODEARTS_DISPLAY_ARCHIVED,
            },
        )

    def test_empty_store_is_safe(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "codearts-agent",
            codearts_home=self.empty_codearts_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "latest",
            "--harness",
            "codearts-agent",
            codearts_home=self.empty_codearts_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_commands_do_not_modify_codearts_store(self) -> None:
        def snapshot() -> dict:
            files = {}
            for path in self.codearts_home.rglob("*"):
                if path.is_file():
                    files[str(path)] = (
                        path.read_bytes(),
                        path.stat().st_mtime_ns,
                    )
            return files

        before = snapshot()
        self.run_cli_checked("search", "--harness", "codearts-agent")
        self.run_cli_checked("search", "--harness", "codearts-agent", "--include-archived")
        self.run_cli_checked(
            "search", "--harness", "codearts-agent", "--deep", "deep-only-needle"
        )
        self.run_cli_checked("latest", "--harness", "codearts-agent")
        self.run_cli_checked("show", "codearts-agent:c0de1001")
        self.run_cli_checked("show", "codearts-agent:c0de1003", "--format", "json")
        self.run_cli_checked("prompts", "codearts-agent:c0de1001")
        self.run_cli_checked("prompts", "codearts-agent:c0de1001", "--count")
        self.assertEqual(snapshot(), before)
        self.assertFalse(
            any(
                path.name.endswith(("-wal", "-shm", "-journal"))
                for path in self.codearts_home.rglob("*")
            )
        )

    def test_partially_written_record_is_skipped(self) -> None:
        code, out, err = self.run_cli(
            "prompts", "codearts-agent:c0de1002", "--count"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "2")

        code, out, err = self.run_cli("show", "codearts-agent:c0de1002")
        self.assertEqual(code, 0, err)
        self.assertIn("- turns: 2", out)

    def test_wal_mode_store_is_not_written(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-codearts-wal-") as temp:
            home = Path(temp) / "wal-home"
            shutil.copytree(self.codearts_home, home)
            db = home / "codearts-data" / "opencode.db"
            writer = sqlite3.connect(str(db))
            try:
                writer.execute("PRAGMA journal_mode=WAL")
                writer.execute("PRAGMA wal_autocheckpoint=0")
                writer.execute("UPDATE session SET time_updated = time_updated + 1")
                writer.commit()
                wal = Path(str(db) + "-wal")
                self.assertTrue(wal.is_file())
                db_bytes = db.read_bytes()
                db_mtime = db.stat().st_mtime_ns
                wal_bytes = wal.read_bytes()

                self.run_cli(
                    "search", "--harness", "codearts-agent", codearts_home=home
                )
                self.run_cli("latest", "--harness", "codearts-agent", codearts_home=home)
                self.run_cli("show", "codearts-agent:c0de1001", codearts_home=home)
                self.run_cli(
                    "prompts", "codearts-agent:c0de1001", "--count", codearts_home=home
                )
                self.run_cli(
                    "search",
                    "--harness",
                    "codearts-agent",
                    "--deep",
                    "deep-only-needle",
                    codearts_home=home,
                )

                self.assertEqual(db.read_bytes(), db_bytes)
                self.assertEqual(db.stat().st_mtime_ns, db_mtime)
                self.assertEqual(wal.read_bytes(), wal_bytes)
                self.assertEqual(
                    sorted(path.name for path in db.parent.glob("opencode.db*")),
                    ["opencode.db", "opencode.db-shm", "opencode.db-wal"],
                )
            finally:
                writer.close()

    def test_fixture_data_is_synthetic(self) -> None:
        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        for path in self.codearts_home.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8", "ignore")
            self.assertNotIn(str(Path.home()), text)
            self.assertNotIn("/Volumes/", text)
            self.assertNotIn("/home/", text)
            self.assertNotIn("/Users/", text.replace("/Users/example/", ""))
            self.assertIsNone(email.search(text), str(path))

        connection = sqlite3.connect(
            (self.codearts_home / "codearts-data" / "opencode.db").as_uri()
            + "?mode=ro",
            uri=True,
        )
        try:
            ids = [row[0] for row in connection.execute("SELECT id FROM session")]
        finally:
            connection.close()
        self.assertEqual(len(ids), 4)
        for session_id in ids:
            self.assertTrue(session_id.startswith("ses_c0de"), session_id)
