from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from cli_support import FixtureTestCase
from workbuddy_fixture import (
    PROMPTS_MAIN as WORKBUDDY_PROMPTS,
    SESSION_ARCHIVED as WORKBUDDY_ARCHIVED,
    SESSION_MAIN as WORKBUDDY_MAIN,
    SESSION_ORPHAN as WORKBUDDY_ORPHAN,
)
from workbuddy_cn_fixture import (
    PROMPTS_MAIN as WORKBUDDY_CN_PROMPTS,
    PROMPT_ORPHAN as WORKBUDDY_CN_ORPHAN_PROMPT,
    PROMPT_PLAIN as WORKBUDDY_CN_PLAIN_PROMPT,
    SESSION_ARCHIVED as WORKBUDDY_CN_ARCHIVED,
    SESSION_EMPTY as WORKBUDDY_CN_EMPTY,
    SESSION_MAIN as WORKBUDDY_CN_MAIN,
    SESSION_ORPHAN as WORKBUDDY_CN_ORPHAN,
)


class WorkBuddyTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli("show", *args, "--format", "json", **kwargs)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_harness_row(self) -> None:
        rows = self.run_json("harnesses")
        workbuddy_rows = [row for row in rows if row["name"] == "workbuddy"]
        self.assertEqual(len(workbuddy_rows), 1)
        self.assertEqual(workbuddy_rows[0]["status"], "ready")
        self.assertEqual(workbuddy_rows[0]["variants"], "desktop")
        self.assertEqual(workbuddy_rows[0]["store"], "~/.workbuddy-ai")
        self.assertEqual(
            workbuddy_rows[0]["aliases"], "workbuddy, workbuddy-ai, wb"
        )
        planned = {row["name"] for row in rows if row["status"] == "planned"}
        self.assertNotIn("workbuddy", planned)

    def test_lists_active_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "workbuddy")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("workbuddy:c0de2002"))
        self.assertTrue(lines[1].startswith("workbuddy:c0de2006"))
        self.assertTrue(lines[2].startswith("workbuddy:c0de2005"))
        self.assertTrue(lines[3].startswith("workbuddy:c0de2001"))
        self.assertNotIn("c0de2003", out)
        self.assertNotIn("c0de2004", out)

    def test_aliases(self) -> None:
        for alias in ("workbuddy", "workbuddy-ai", "wb"):
            sessions = self.run_json("search", "--harness", alias, "--limit", "0")
            self.assertEqual(len(sessions), 4)
            self.assertTrue(
                all(
                    session["ref"].startswith("workbuddy:") for session in sessions
                )
            )

    def test_keyword_session_id_and_title_fallback(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy", "handoff"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy:c0de2001", out)
        self.assertNotIn("c0de2002", out)

        sessions = self.run_json("search", "--harness", "workbuddy", "migration")
        self.assertEqual(
            [session["ref"] for session in sessions], ["workbuddy:c0de2002"]
        )
        self.assertEqual(
            sessions[0]["title"], "Investigate the migration drift in project gamma."
        )

        sessions = self.run_json("search", "--harness", "workbuddy", "c0de2002")
        self.assertEqual(
            [session["ref"] for session in sessions], ["workbuddy:c0de2002"]
        )

    def test_latest_and_query_filter(self) -> None:
        sessions = self.run_json("latest", "--harness", "workbuddy")
        self.assertEqual(
            [session["ref"] for session in sessions], ["workbuddy:c0de2002"]
        )
        self.assertEqual(sessions[0]["entrypoint"], "desktop")
        self.assertEqual(sessions[0]["variants"], "desktop")
        self.assertEqual(sessions[0]["last_prompt"], "继续")

        sessions = self.run_json("latest", "--harness", "workbuddy", "handoff")
        self.assertEqual(
            [session["ref"] for session in sessions], ["workbuddy:c0de2001"]
        )
        self.assertEqual(sessions[0]["first_prompt"], WORKBUDDY_PROMPTS[0])
        self.assertEqual(sessions[0]["last_prompt"], WORKBUDDY_PROMPTS[2])

        code, out, err = self.run_cli(
            "latest", "--harness", "workbuddy", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_cwd_since_limit_and_no_match(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "workbuddy",
            "--cwd",
            "/Users/example/project-alpha",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy:c0de2001", out)
        self.assertNotIn("c0de2002", out)

        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy", "--cwd", "/Users/example"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy:c0de2001", out)
        self.assertIn("workbuddy:c0de2002", out)

        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy", "--since", "2026-10-25"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy:c0de2002", out)
        self.assertIn("workbuddy:c0de2006", out)
        self.assertNotIn("c0de2001", out)

        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_archived_and_deleted_are_hidden_by_default(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy", "--include-archived", "--limit", "0"
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        marks = {
            parts[0]: parts[-1] for parts in (line.split("\t") for line in lines)
        }
        self.assertEqual(
            marks,
            {
                "workbuddy:c0de2002": "-",
                "workbuddy:c0de2006": "-",
                "workbuddy:c0de2004": "yes",
                "workbuddy:c0de2005": "-",
                "workbuddy:c0de2003": "yes",
                "workbuddy:c0de2001": "-",
            },
        )

    def test_archive_metadata_missing_degrades_to_active(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "workbuddy",
            "--limit",
            "0",
            workbuddy_db=self.no_workbuddy_db,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy:c0de2003", out)
        self.assertIn("workbuddy:c0de2004", out)

    def test_archive_state_does_not_cross_harnesses(self) -> None:
        sessions = self.run_json(
            "search", "--harness", "zcode", "--include-archived", "--limit", "0"
        )
        refs = {session["ref"] for session in sessions}
        self.assertFalse(any(ref.startswith("workbuddy:") for ref in refs))

        code, out, err = self.run_cli("show", "c0de2003", "--harness", "zcode")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_deep_search_scans_only_the_matching_session(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy", "deep-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy", "--deep", "deep-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy:c0de2002", out)
        self.assertNotIn("c0de2001", out)

    def test_deep_search_respects_archive_filter(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy", "--deep", "archived-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "workbuddy",
            "--include-archived",
            "--deep",
            "archived-needle",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy:c0de2003", out)

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli(
            "show", "workbuddy:c0de2001", "--messages", "2", "--chars", "120"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("# workbuddy:c0de2001", out)
        self.assertIn("- harness: workbuddy (desktop)", out)
        self.assertIn("- cwd: `/Users/example/project-alpha`", out)
        self.assertIn("- model: `wb-synthetic-1`", out)
        self.assertIn("- turns: 3", out)
        self.assertIn("## Task", out)
        self.assertIn(WORKBUDDY_PROMPTS[0][:60], out)
        self.assertIn("## Latest request", out)
        self.assertIn(WORKBUDDY_PROMPTS[2], out)
        self.assertIn("## Todos (2 open / 3 total)", out)
        self.assertIn("- [pending] Refactor handoff digest", out)
        self.assertIn("- [in_progress] Document compaction fallback", out)
        self.assertIn("src/handoff.ts", out)
        self.assertIn("docs/handoff.md", out)
        self.assertNotIn("<task-notification>", out)
        self.assertNotIn("OS Version: darwin", out)

    def test_show_json_fields(self) -> None:
        data = self.show_json("workbuddy:c0de2001", "--messages", "0")
        self.assertEqual(data["ref"], "workbuddy:c0de2001")
        self.assertEqual(data["session_id"], WORKBUDDY_MAIN)
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertEqual(data["entrypoint"], "desktop")
        self.assertEqual(data["variants"], "desktop")
        self.assertEqual(data["branch"], "")
        self.assertEqual(data["version"], "")
        self.assertGreater(data["size_bytes"], 0)
        self.assertFalse(data["archived"])
        self.assertEqual(data["compact_summary"], "")
        self.assertEqual(data["turn_count"], 3)
        self.assertEqual(
            data["todos"],
            [
                {"subject": "Refactor handoff digest", "status": "pending"},
                {"subject": "Document compaction fallback", "status": "in_progress"},
                {"subject": "Trim digest output", "status": "completed"},
            ],
        )
        self.assertEqual(
            data["edited_files"],
            [
                {"path": "/Users/example/project-alpha/src/handoff.ts", "count": 1},
                {"path": "/Users/example/project-alpha/docs/handoff.md", "count": 1},
            ],
        )
        self.assertEqual(
            data["tool_counts"], {"Edit": 2, "Read": 1, "Bash": 1}
        )
        self.assertEqual(
            data["path"],
            str(
                self.workbuddy_home
                / "projects"
                / "Users-example-project-alpha"
                / (WORKBUDDY_MAIN + ".jsonl")
            ),
        )

    def test_show_by_transcript_path(self) -> None:
        data = self.show_json("workbuddy:c0de2001", "--messages", "0")
        source = data["path"]

        code, out, err = self.run_cli("show", source)
        self.assertEqual(code, 0, err)
        self.assertIn("# workbuddy:c0de2001", out)

        code, out, err = self.run_cli("prompts", source, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "3")

    def test_show_archived_session(self) -> None:
        code, out, err = self.run_cli("show", "workbuddy:c0de2003")
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)

        data = self.show_json("workbuddy:c0de2004")
        self.assertTrue(data["archived"])

        data = self.show_json("workbuddy:c0de2005")
        self.assertFalse(data["archived"])

    def test_show_missing_and_ambiguous_refs(self) -> None:
        code, out, err = self.run_cli("show", "workbuddy:c0deffff")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "workbuddy:c0de200")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", err)

        code, out, err = self.run_cli("show", "workbuddy:c0d")
        self.assertEqual(code, 2)
        self.assertIn("too short", err)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli("prompts", "workbuddy:c0de2001", "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "3")

        code, out, err = self.run_cli("prompts", "workbuddy:c0de2001")
        self.assertEqual(code, 0, err)
        for index, prompt in enumerate(WORKBUDDY_PROMPTS, 1):
            self.assertIn("## %d" % index, out)
            self.assertIn(prompt, out)
        self.assertNotIn("<task-notification>", out)
        self.assertNotIn("OS Version: darwin", out)

        code, out, err = self.run_cli(
            "prompts", "workbuddy:c0de2001", "--offset", "1", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("## 2", out)
        self.assertNotIn(WORKBUDDY_PROMPTS[0], out)
        self.assertIn("next: --offset 2 --limit 1", out)

        code, out, err = self.run_cli(
            "prompts", "workbuddy:c0de2001", "--order", "newest", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("## 3"), out.index("## 2"))
        self.assertNotIn("## 1", out)

        code, out, err = self.run_cli(
            "prompts", "workbuddy:c0de2001", "--offset", "9"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts", "workbuddy:c0de2001", "--limit", "1", "--chars", "10"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Please re…", out)
        self.assertNotIn(WORKBUDDY_PROMPTS[0], out)

    def test_prompts_json_and_archived(self) -> None:
        data = self.run_json("prompts", "workbuddy:c0de2001", "--limit", "2")
        self.assertEqual(data["ref"], "workbuddy:c0de2001")
        self.assertEqual(data["session_id"], WORKBUDDY_MAIN)
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertFalse(data["archived"])
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["returned"], 2)
        self.assertTrue(data["has_more"])
        self.assertEqual([prompt["index"] for prompt in data["prompts"]], [1, 2])
        self.assertEqual(data["prompts"][0]["text"], WORKBUDDY_PROMPTS[0])
        self.assertEqual(data["prompts"][0]["timestamp"], '2026-10-20T09:10:00Z')

        data = self.run_json("prompts", "workbuddy:c0de2003", "--count")
        self.assertTrue(data["archived"])
        self.assertEqual(data["total"], 1)

    def test_non_human_records_never_become_prompts(self) -> None:
        prompts = self.run_json("prompts", "workbuddy:c0de2001", "--limit", "0")
        texts = [prompt["text"] for prompt in prompts["prompts"]]
        self.assertEqual(texts, list(WORKBUDDY_PROMPTS))
        for text in texts:
            self.assertNotIn("<system-reminder", text)
            self.assertNotIn("<task-notification>", text)
            self.assertNotIn("<user_query>", text)

    def test_orphan_transcript_without_row_is_listed(self) -> None:
        sessions = self.run_json("search", "--harness", "workbuddy", "--limit", "0")
        by_id = {session["session_id"]: session for session in sessions}
        self.assertIn(WORKBUDDY_ORPHAN, by_id)
        self.assertEqual(by_id[WORKBUDDY_ORPHAN]["cwd"], "/Users/example/project-gamma")
        self.assertEqual(
            by_id[WORKBUDDY_ORPHAN]["title"], "Orphan transcript without a row."
        )
        self.assertFalse(by_id[WORKBUDDY_ORPHAN]["archived"])

    def test_file_rollback_is_not_a_session(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy", "--include-archived", "--limit", "0"
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn("file-rollback", out)
        self.assertEqual(len(out.strip().splitlines()), 7)

    def test_empty_store_is_safe(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "workbuddy",
            workbuddy_home=self.empty_workbuddy_home,
            workbuddy_db=self.no_workbuddy_db,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "latest",
            "--harness",
            "workbuddy",
            workbuddy_home=self.empty_workbuddy_home,
            workbuddy_db=self.no_workbuddy_db,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_commands_do_not_modify_workbuddy_store(self) -> None:
        def snapshot() -> dict:
            files = {}
            for path in self.workbuddy_home.rglob("*"):
                if path.is_file():
                    files[str(path)] = (
                        path.read_bytes(),
                        path.stat().st_mtime_ns,
                    )
            return files

        before = snapshot()
        self.run_cli_checked("search", "--harness", "workbuddy")
        self.run_cli_checked("search", "--harness", "workbuddy", "--include-archived")
        self.run_cli_checked("search", "--harness", "workbuddy", "--deep", "deep-only-needle")
        self.run_cli_checked("latest", "--harness", "workbuddy")
        self.run_cli_checked("show", "workbuddy:c0de2001")
        self.run_cli_checked("show", "workbuddy:c0de2003", "--format", "json")
        self.run_cli_checked("prompts", "workbuddy:c0de2001")
        self.run_cli_checked("prompts", "workbuddy:c0de2001", "--count")
        self.assertEqual(snapshot(), before)
        self.assertFalse(
            any(
                path.name.endswith(("-wal", "-shm", "-journal"))
                for path in self.workbuddy_home.rglob("*")
            )
        )

    def test_fixture_data_is_synthetic(self) -> None:
        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        for path in self.workbuddy_home.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8", "ignore")
            self.assertNotIn(str(Path.home()), text)
            self.assertNotIn("/Volumes/", text)
            self.assertNotIn("/home/", text)
            self.assertNotIn("/Users/", text.replace("/Users/example/", ""))
            self.assertIsNone(email.search(text), str(path))

        connection = sqlite3.connect(
            self.workbuddy_db.as_uri() + "?mode=ro", uri=True
        )
        try:
            ids = [row[0] for row in connection.execute("SELECT id FROM sessions")]
        finally:
            connection.close()
        self.assertEqual(len(ids), 5)
        for session_id in ids:
            self.assertTrue(session_id.startswith("c0de200"), session_id)


class WorkBuddyCNTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli("show", *args, "--format", "json", **kwargs)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_harness_row(self) -> None:
        rows = self.run_json("harnesses")
        rows = [row for row in rows if row["name"] == "workbuddy-cn"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "ready")
        self.assertEqual(rows[0]["variants"], "desktop")
        self.assertEqual(rows[0]["store"], "~/.workbuddy")
        self.assertEqual(
            rows[0]["aliases"],
            "workbuddy-cn, workbuddycn, workbuddy_cn, wb-cn",
        )

    def test_lists_active_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "workbuddy-cn")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("workbuddy-cn:d0d0c002"))
        self.assertTrue(lines[1].startswith("workbuddy-cn:d0d0c006"))
        self.assertTrue(lines[2].startswith("workbuddy-cn:d0d0c005"))
        self.assertTrue(lines[3].startswith("workbuddy-cn:d0d0c001"))
        self.assertNotIn("d0d0c003", out)
        self.assertNotIn("d0d0c004", out)
        self.assertNotIn("d0d0c007", out)

    def test_aliases(self) -> None:
        for alias in ("workbuddy-cn", "workbuddycn", "workbuddy_cn", "wb-cn"):
            sessions = self.run_json("search", "--harness", alias, "--limit", "0")
            self.assertEqual(len(sessions), 4)
            self.assertTrue(
                all(
                    session["ref"].startswith("workbuddy-cn:")
                    for session in sessions
                )
            )

    def test_keyword_session_id_and_title_fallback(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy-cn", "handoff"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy-cn:d0d0c001", out)
        self.assertNotIn("d0d0c002", out)

        sessions = self.run_json("search", "--harness", "workbuddy-cn", "migration")
        self.assertEqual(
            [session["ref"] for session in sessions], ["workbuddy-cn:d0d0c002"]
        )
        self.assertEqual(
            sessions[0]["title"], WORKBUDDY_CN_PLAIN_PROMPT
        )

        sessions = self.run_json("search", "--harness", "workbuddy-cn", "d0d0c002")
        self.assertEqual(
            [session["ref"] for session in sessions], ["workbuddy-cn:d0d0c002"]
        )

    def test_latest_and_query_filter(self) -> None:
        sessions = self.run_json("latest", "--harness", "workbuddy-cn")
        self.assertEqual(
            [session["ref"] for session in sessions], ["workbuddy-cn:d0d0c002"]
        )
        self.assertEqual(sessions[0]["entrypoint"], "desktop")
        self.assertEqual(sessions[0]["variants"], "desktop")
        self.assertEqual(sessions[0]["last_prompt"], "继续")

        sessions = self.run_json("latest", "--harness", "workbuddy-cn", "handoff")
        self.assertEqual(
            [session["ref"] for session in sessions], ["workbuddy-cn:d0d0c001"]
        )
        self.assertEqual(
            sessions[0]["first_prompt"], WORKBUDDY_CN_PROMPTS[0]
        )
        self.assertEqual(
            sessions[0]["last_prompt"], WORKBUDDY_CN_PROMPTS[2]
        )

        code, out, err = self.run_cli(
            "latest", "--harness", "workbuddy-cn", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_cwd_since_limit_and_no_match(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "workbuddy-cn",
            "--cwd",
            "/Users/example/project-alpha",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy-cn:d0d0c001", out)
        self.assertNotIn("d0d0c002", out)

        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy-cn", "--cwd", "/Users/example"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy-cn:d0d0c001", out)
        self.assertIn("workbuddy-cn:d0d0c002", out)

        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy-cn", "--since", "2026-10-25"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy-cn:d0d0c002", out)
        self.assertIn("workbuddy-cn:d0d0c006", out)
        self.assertNotIn("d0d0c001", out)

        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy-cn", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy-cn", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_archived_and_deleted_are_hidden_by_default(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "workbuddy-cn",
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
                "workbuddy-cn:d0d0c002": "-",
                "workbuddy-cn:d0d0c006": "-",
                "workbuddy-cn:d0d0c004": "yes",
                "workbuddy-cn:d0d0c005": "-",
                "workbuddy-cn:d0d0c003": "yes",
                "workbuddy-cn:d0d0c001": "-",
            },
        )

    def test_archive_metadata_missing_degrades_to_active(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "workbuddy-cn",
            "--limit",
            "0",
            workbuddy_cn_db=self.no_workbuddy_cn_db,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy-cn:d0d0c003", out)
        self.assertIn("workbuddy-cn:d0d0c004", out)

    def test_archive_state_does_not_cross_harnesses(self) -> None:
        sessions = self.run_json(
            "search", "--harness", "workbuddy", "--include-archived", "--limit", "0"
        )
        refs = {session["ref"] for session in sessions}
        self.assertFalse(any(ref.startswith("workbuddy-cn:") for ref in refs))

        code, out, err = self.run_cli(
            "show", WORKBUDDY_CN_ARCHIVED, "--harness", "workbuddy"
        )
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli(
            "show", WORKBUDDY_ARCHIVED, "--harness", "workbuddy-cn"
        )
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        sessions = self.run_json(
            "search",
            "--harness",
            "workbuddy-cn",
            "--include-archived",
            "--limit",
            "0",
        )
        self.assertTrue(
            all(
                session["ref"].startswith("workbuddy-cn:")
                for session in sessions
            )
        )

    def test_deep_search_scans_only_the_matching_session(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy-cn", "deep-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy-cn", "--deep", "deep-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy-cn:d0d0c002", out)
        self.assertNotIn("d0d0c001", out)

        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy-cn", "--deep", "main-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy-cn:d0d0c001", out)
        self.assertNotIn("d0d0c002", out)

    def test_deep_search_respects_archive_filter(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy-cn", "--deep", "archived-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "workbuddy-cn",
            "--include-archived",
            "--deep",
            "archived-needle",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("workbuddy-cn:d0d0c003", out)

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli(
            "show", "workbuddy-cn:d0d0c001", "--messages", "2", "--chars", "120"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("# workbuddy-cn:d0d0c001", out)
        self.assertIn("- harness: workbuddy-cn (desktop)", out)
        self.assertIn("- cwd: `/Users/example/project-alpha`", out)
        self.assertIn("- model: `wb-cn-synthetic-1`", out)
        self.assertIn("- turns: 3", out)
        self.assertIn("## Task", out)
        self.assertIn(WORKBUDDY_CN_PROMPTS[0][:60], out)
        self.assertIn("## Latest request", out)
        self.assertIn(WORKBUDDY_CN_PROMPTS[2], out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn("A previous turn asked to bound the handoff digest.", out)
        self.assertIn("## Todos (2 open / 3 total)", out)
        self.assertIn("- [pending] Refactor handoff digest", out)
        self.assertIn("- [in_progress] Document compaction fallback", out)
        self.assertIn("src/handoff.ts", out)
        self.assertIn("docs/handoff.md", out)
        self.assertNotIn("<task-notification>", out)
        self.assertNotIn("OS Version: darwin", out)
        self.assertNotIn("<cb_summary>", out)

    def test_show_json_fields(self) -> None:
        data = self.show_json("workbuddy-cn:d0d0c001", "--messages", "0")
        self.assertEqual(data["ref"], "workbuddy-cn:d0d0c001")
        self.assertEqual(data["session_id"], WORKBUDDY_CN_MAIN)
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertEqual(data["entrypoint"], "desktop")
        self.assertEqual(data["variants"], "desktop")
        self.assertEqual(data["branch"], "")
        self.assertEqual(data["version"], "")
        self.assertGreater(data["size_bytes"], 0)
        self.assertFalse(data["archived"])
        self.assertIn(
            "A previous turn asked to bound the handoff digest.",
            data["compact_summary"],
        )
        self.assertNotIn("<cb_summary>", data["compact_summary"])
        self.assertEqual(data["turn_count"], 3)
        self.assertEqual(
            data["todos"],
            [
                {"subject": "Refactor handoff digest", "status": "pending"},
                {"subject": "Document compaction fallback", "status": "in_progress"},
                {"subject": "Trim digest output", "status": "completed"},
            ],
        )
        self.assertEqual(
            data["edited_files"],
            [
                {"path": "/Users/example/project-alpha/src/handoff.ts", "count": 1},
                {"path": "/Users/example/project-alpha/docs/handoff.md", "count": 1},
            ],
        )
        self.assertEqual(
            data["tool_counts"], {"Edit": 2, "Read": 1, "Bash": 1}
        )
        self.assertEqual(
            data["path"],
            str(
                self.workbuddy_cn_home
                / "projects"
                / "Users-example-project-alpha"
                / (WORKBUDDY_CN_MAIN + ".jsonl")
            ),
        )

    def test_show_by_transcript_path(self) -> None:
        data = self.show_json("workbuddy-cn:d0d0c001", "--messages", "0")
        source = data["path"]

        code, out, err = self.run_cli("show", source)
        self.assertEqual(code, 0, err)
        self.assertIn("# workbuddy-cn:d0d0c001", out)

        code, out, err = self.run_cli("prompts", source, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "3")

    def test_show_archived_session(self) -> None:
        code, out, err = self.run_cli("show", "workbuddy-cn:d0d0c003")
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)

        data = self.show_json("workbuddy-cn:d0d0c004")
        self.assertTrue(data["archived"])

        data = self.show_json("workbuddy-cn:d0d0c005")
        self.assertFalse(data["archived"])

    def test_show_missing_and_ambiguous_refs(self) -> None:
        code, out, err = self.run_cli("show", "workbuddy-cn:d0d0cfff")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "workbuddy-cn:d0d0c00")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", err)

        code, out, err = self.run_cli("show", "workbuddy-cn:d0d")
        self.assertEqual(code, 2)
        self.assertIn("too short", err)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli("prompts", "workbuddy-cn:d0d0c001", "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "3")

        code, out, err = self.run_cli("prompts", "workbuddy-cn:d0d0c001")
        self.assertEqual(code, 0, err)
        for index, prompt in enumerate(WORKBUDDY_CN_PROMPTS, 1):
            self.assertIn("## %d" % index, out)
            self.assertIn(prompt, out)
        self.assertNotIn("<task-notification>", out)
        self.assertNotIn("OS Version: darwin", out)
        self.assertNotIn("<cb_summary>", out)
        self.assertNotIn("<previous_user_message>", out)

        code, out, err = self.run_cli(
            "prompts", "workbuddy-cn:d0d0c001", "--offset", "1", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("## 2", out)
        self.assertNotIn(WORKBUDDY_CN_PROMPTS[0], out)
        self.assertIn("next: --offset 2 --limit 1", out)

        code, out, err = self.run_cli(
            "prompts",
            "workbuddy-cn:d0d0c001",
            "--order",
            "newest",
            "--limit",
            "2",
        )
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("## 3"), out.index("## 2"))
        self.assertNotIn("## 1", out)

        code, out, err = self.run_cli(
            "prompts", "workbuddy-cn:d0d0c001", "--offset", "9"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts",
            "workbuddy-cn:d0d0c001",
            "--limit",
            "1",
            "--chars",
            "10",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Please re…", out)
        self.assertNotIn(WORKBUDDY_CN_PROMPTS[0], out)

    def test_prompts_json_and_archived(self) -> None:
        data = self.run_json("prompts", "workbuddy-cn:d0d0c001", "--limit", "2")
        self.assertEqual(data["ref"], "workbuddy-cn:d0d0c001")
        self.assertEqual(data["session_id"], WORKBUDDY_CN_MAIN)
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertFalse(data["archived"])
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["returned"], 2)
        self.assertTrue(data["has_more"])
        self.assertEqual([prompt["index"] for prompt in data["prompts"]], [1, 2])
        self.assertEqual(
            data["prompts"][0]["text"], WORKBUDDY_CN_PROMPTS[0]
        )
        self.assertEqual(data["prompts"][0]["timestamp"], '2026-10-20T09:10:00Z')

        data = self.run_json("prompts", "workbuddy-cn:d0d0c003", "--count")
        self.assertTrue(data["archived"])
        self.assertEqual(data["total"], 1)

    def test_non_human_records_never_become_prompts(self) -> None:
        prompts = self.run_json(
            "prompts", "workbuddy-cn:d0d0c001", "--limit", "0"
        )
        texts = [prompt["text"] for prompt in prompts["prompts"]]
        self.assertEqual(texts, list(WORKBUDDY_CN_PROMPTS))
        self.assertEqual(texts.count(WORKBUDDY_CN_PROMPTS[0]), 1)
        for text in texts:
            self.assertNotIn("<system-reminder", text)
            self.assertNotIn("<task-notification>", text)
            self.assertNotIn("<user_query>", text)
            self.assertNotIn("<cb_summary>", text)
            self.assertNotIn("<previous_user_message>", text)

    def test_local_prompts_are_included(self) -> None:
        prompts = self.run_json(
            "prompts", "workbuddy-cn:d0d0c001", "--limit", "0"
        )
        texts = [prompt["text"] for prompt in prompts["prompts"]]
        self.assertIn(WORKBUDDY_CN_PROMPTS[0], texts)
        self.assertIn(WORKBUDDY_CN_PROMPTS[2], texts)

    def test_orphan_transcript_without_row_is_listed(self) -> None:
        sessions = self.run_json(
            "search", "--harness", "workbuddy-cn", "--limit", "0"
        )
        by_id = {session["session_id"]: session for session in sessions}
        self.assertIn(WORKBUDDY_CN_ORPHAN, by_id)
        self.assertEqual(
            by_id[WORKBUDDY_CN_ORPHAN]["cwd"], "/Users/example/project-gamma"
        )
        self.assertEqual(
            by_id[WORKBUDDY_CN_ORPHAN]["title"], WORKBUDDY_CN_ORPHAN_PROMPT
        )
        self.assertFalse(by_id[WORKBUDDY_CN_ORPHAN]["archived"])

    def test_empty_transcript_is_not_listed(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "workbuddy-cn",
            "--include-archived",
            "--limit",
            "0",
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn(WORKBUDDY_CN_EMPTY[:8], out)

        code, out, err = self.run_cli(
            "show", "workbuddy-cn:" + WORKBUDDY_CN_EMPTY[:8]
        )
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli(
            "search", "--harness", "workbuddy-cn", WORKBUDDY_CN_EMPTY[:8]
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_file_rollback_is_not_a_session(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "workbuddy-cn",
            "--include-archived",
            "--limit",
            "0",
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn("file-rollback", out)
        self.assertEqual(len(out.strip().splitlines()), 7)

    def test_empty_store_is_safe(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "workbuddy-cn",
            workbuddy_cn_home=self.empty_workbuddy_cn_home,
            workbuddy_cn_db=self.no_workbuddy_cn_db,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "latest",
            "--harness",
            "workbuddy-cn",
            workbuddy_cn_home=self.empty_workbuddy_cn_home,
            workbuddy_cn_db=self.no_workbuddy_cn_db,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_commands_do_not_modify_workbuddy_cn_store(self) -> None:
        def snapshot() -> dict:
            files = {}
            for path in self.workbuddy_cn_home.rglob("*"):
                if path.is_file():
                    files[str(path)] = (
                        path.read_bytes(),
                        path.stat().st_mtime_ns,
                    )
            return files

        before = snapshot()
        self.run_cli_checked("search", "--harness", "workbuddy-cn")
        self.run_cli_checked(
            "search", "--harness", "workbuddy-cn", "--include-archived"
        )
        self.run_cli_checked(
            "search", "--harness", "workbuddy-cn", "--deep", "deep-only-needle"
        )
        self.run_cli_checked("latest", "--harness", "workbuddy-cn")
        self.run_cli_checked("show", "workbuddy-cn:d0d0c001")
        self.run_cli_checked("show", "workbuddy-cn:d0d0c003", "--format", "json")
        self.run_cli_checked("prompts", "workbuddy-cn:d0d0c001")
        self.run_cli_checked("prompts", "workbuddy-cn:d0d0c001", "--count")
        self.assertEqual(snapshot(), before)
        self.assertFalse(
            any(
                path.name.endswith(("-wal", "-shm", "-journal"))
                for path in self.workbuddy_cn_home.rglob("*")
            )
        )

    def test_fixture_data_is_synthetic(self) -> None:
        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        for path in self.workbuddy_cn_home.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8", "ignore")
            self.assertNotIn(str(Path.home()), text)
            self.assertNotIn("/Volumes/", text)
            self.assertNotIn("/home/", text)
            self.assertNotIn("/Users/", text.replace("/Users/example/", ""))
            self.assertIsNone(email.search(text), str(path))

        connection = sqlite3.connect(
            self.workbuddy_cn_db.as_uri() + "?mode=ro", uri=True
        )
        try:
            ids = [row[0] for row in connection.execute("SELECT id FROM sessions")]
        finally:
            connection.close()
        self.assertEqual(len(ids), 6)
        for session_id in ids:
            self.assertTrue(session_id.startswith("d0d0c00"), session_id)
