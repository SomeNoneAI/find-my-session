from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from cli_support import FixtureTestCase
from minimax_code_fixture import (
    COMPACT_SUMMARY_MAIN,
    DEEP_NEEDLE,
    DISPLAY_ARCHIVED,
    DISPLAY_MAIN,
    PROMPTS_MAIN,
    PROMPT_ARCHIVED,
    PROMPT_CHILD,
    PROMPT_CRON_MESSAGE,
    PROMPT_HIDDEN,
    PROMPT_PLAIN,
    PROMPT_QUESTIONNAIRE,
    SESSION_ARCHIVED,
    SESSION_CHILD,
    SESSION_CRON,
    SESSION_HIDDEN,
    SESSION_MAIN,
    SESSION_PEEK,
    SESSION_PLAIN,
)


def _display(raw_id: str) -> str:
    return raw_id[len("mvs_") :]


class MiniMaxCodeTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli(
            "show", *args, "--format", "json", **kwargs
        )
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def find_hidden_path(self) -> Path:
        day = self.minimax_code_home / "sessions" / "2026" / "10" / "24"
        folder = next(path for path in day.iterdir() if path.is_dir())
        return folder / "messages.jsonl"

    def test_harness_listing_and_aliases(self) -> None:
        rows = self.run_json("harnesses")
        matches = [row for row in rows if row["name"] == "minimax-code"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["status"], "ready")
        self.assertEqual(matches[0]["variants"], "cli")
        self.assertEqual(matches[0]["store"], "~/.minimax/v2")
        self.assertEqual(
            matches[0]["aliases"], "minimax-code, minimax, mcode"
        )

        expected = {
            "minimax-code:c0de4001",
            "minimax-code:c0de4002",
            "minimax-code:c0de4008",
        }
        for alias in ("minimax-code", "minimax", "mcode"):
            sessions = self.run_json(
                "search", "--harness", alias, "--limit", "0"
            )
            self.assertEqual(
                {session["ref"] for session in sessions}, expected, alias
            )

    def test_lists_active_sessions_newest_first(self) -> None:
        # Every fixture row carries a stale record_json that says "hidden" and
        # "branch"; only the columnar fields are authoritative.
        code, out, err = self.run_cli("search", "--harness", "minimax-code")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("minimax-code:c0de4001"))
        self.assertTrue(lines[1].startswith("minimax-code:c0de4002"))
        self.assertTrue(lines[2].startswith("minimax-code:c0de4008"))
        for hidden in (
            "c0de4003",
            "c0de4004",
            "c0de4005",
            "c0de4006",
            "c0de4007",
        ):
            self.assertNotIn(hidden, out)

    def test_keyword_session_id_cwd_since_and_limit(self) -> None:
        sessions = self.run_json(
            "search", "--harness", "minimax-code", "handoff"
        )
        self.assertEqual(
            [session["ref"] for session in sessions],
            ["minimax-code:c0de4001"],
        )

        sessions = self.run_json(
            "search", "--harness", "minimax-code", "migration"
        )
        self.assertEqual(
            [session["ref"] for session in sessions],
            ["minimax-code:c0de4002"],
        )
        self.assertEqual(sessions[0]["title"], "Investigate migration drift")

        sessions = self.run_json(
            "search", "--harness", "minimax-code", "c0de4002"
        )
        self.assertEqual(
            [session["ref"] for session in sessions],
            ["minimax-code:c0de4002"],
        )

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "minimax-code",
            "--cwd",
            "/Users/example/project-alpha",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("minimax-code:c0de4001", out)
        self.assertNotIn("c0de4002", out)

        code, out, err = self.run_cli(
            "search", "--harness", "minimax-code", "--cwd", "/Users/example"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("minimax-code:c0de4001", out)
        self.assertIn("minimax-code:c0de4002", out)
        self.assertIn("minimax-code:c0de4008", out)

        code, out, err = self.run_cli(
            "search", "--harness", "minimax-code", "--since", "2026-10-27"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("minimax-code:c0de4001", out)
        self.assertIn("minimax-code:c0de4002", out)
        self.assertNotIn("c0de4008", out)

        code, out, err = self.run_cli(
            "search", "--harness", "minimax-code", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

        code, out, err = self.run_cli(
            "search", "--harness", "minimax-code", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_latest(self) -> None:
        sessions = self.run_json("latest", "--harness", "minimax-code")
        self.assertEqual(
            [session["ref"] for session in sessions],
            ["minimax-code:c0de4001"],
        )
        self.assertEqual(sessions[0]["entrypoint"], "cli")
        self.assertEqual(sessions[0]["variants"], "cli")
        self.assertEqual(sessions[0]["first_prompt"], PROMPTS_MAIN[0])
        self.assertEqual(sessions[0]["last_prompt"], PROMPTS_MAIN[4])

        sessions = self.run_json(
            "latest", "--harness", "minimax-code", "migration"
        )
        self.assertEqual(
            [session["ref"] for session in sessions],
            ["minimax-code:c0de4002"],
        )

        code, out, err = self.run_cli(
            "latest", "--harness", "minimax-code", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_archived_hidden_and_internal_sessions(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "minimax-code", "--limit", "0"
        )
        self.assertEqual(code, 0, err)
        for hidden in (
            "c0de4003",
            "c0de4004",
            "c0de4005",
            "c0de4006",
            "c0de4007",
        ):
            self.assertNotIn(hidden, out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "minimax-code",
            "--include-archived",
            "--limit",
            "0",
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
                "minimax-code:c0de4001": "-",
                "minimax-code:c0de4002": "-",
                "minimax-code:c0de4008": "-",
                "minimax-code:c0de4003": "yes",
            },
        )
        for hidden in ("c0de4004", "c0de4005", "c0de4006", "c0de4007"):
            self.assertNotIn(hidden, out)

        code, out, err = self.run_cli(
            "show", "minimax-code:c0de4003"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)
        self.assertIn(PROMPT_ARCHIVED, out)

        code, out, err = self.run_cli(
            "show", "minimax-code:c0de4004"
        )
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_show_hidden_session_by_path(self) -> None:
        path = self.find_hidden_path()
        code, out, err = self.run_cli("show", str(path))
        self.assertEqual(code, 0, err)
        self.assertIn("# minimax-code:" + _display(SESSION_HIDDEN)[:8], out)
        self.assertIn("- archived: yes", out)
        self.assertIn(PROMPT_HIDDEN, out)

    def test_deep_search_isolation_and_compaction_fallback(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "minimax-code", "deep-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "minimax-code",
            "--deep",
            "deep-only-needle",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("minimax-code:c0de4001", out)
        self.assertNotIn("c0de4002", out)

        # The compaction summary exists only in messages.jsonl, never in the
        # runtime database, so this proves the transcript fallback runs.
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "minimax-code",
            "--deep",
            "compaction-only-needle",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("minimax-code:c0de4001", out)

        for needle in (PROMPT_CHILD, PROMPT_HIDDEN):
            code, out, err = self.run_cli(
                "search", "--harness", "minimax-code", "--deep", needle
            )
            self.assertEqual(code, 0, err)
            self.assertIn("no sessions matched", out, needle)

    def test_deep_search_respects_archive_filter(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "minimax-code", "--deep", "archived-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "minimax-code",
            "--include-archived",
            "--deep",
            "archived-needle",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("minimax-code:c0de4003", out)

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli(
            "show",
            "minimax-code:c0de4001",
            "--messages",
            "2",
            "--chars",
            "120",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("# minimax-code:c0de4001", out)
        self.assertIn("- harness: minimax-code (cli)", out)
        self.assertIn("- cwd: `/Users/example/project-alpha`", out)
        self.assertIn("- model: `minimax/MiniMax-M3.1-Flash`", out)
        self.assertIn("- turns: 5", out)
        self.assertIn("## Task", out)
        self.assertIn(PROMPTS_MAIN[0][:60], out)
        self.assertIn("## Latest request", out)
        self.assertIn(PROMPTS_MAIN[4], out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn(COMPACT_SUMMARY_MAIN, out)
        self.assertIn("## Todos (2 open / 3 total)", out)
        self.assertIn("- [in_progress] Document compaction fallback", out)
        self.assertIn("- [pending] Trim digest output", out)
        self.assertIn("src/handoff.ts` (x2)", out)
        self.assertIn("docs/handoff.md", out)
        self.assertIn(DEEP_NEEDLE, out)
        self.assertNotIn(PROMPT_CRON_MESSAGE, out)
        self.assertNotIn(PROMPT_QUESTIONNAIRE, out)

    def test_show_json_fields(self) -> None:
        data = self.show_json("minimax-code:c0de4001", "--messages", "0")
        self.assertEqual(data["ref"], "minimax-code:c0de4001")
        self.assertEqual(data["session_id"], DISPLAY_MAIN)
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertEqual(data["entrypoint"], "cli")
        self.assertEqual(data["variants"], "cli")
        self.assertEqual(data["version"], "")
        self.assertGreater(data["size_bytes"], 0)
        self.assertFalse(data["archived"])
        self.assertEqual(data["compact_summary"], COMPACT_SUMMARY_MAIN)
        self.assertEqual(data["turn_count"], 5)
        self.assertEqual(
            data["started"], "2026-10-27T14:00:00Z"
        )
        self.assertEqual(
            data["updated"], "2026-10-27T16:00:30Z"
        )
        self.assertEqual(
            data["todos"],
            [
                {"subject": "Refactor handoff parser", "status": "completed"},
                {
                    "subject": "Document compaction fallback",
                    "status": "in_progress",
                },
                {"subject": "Trim digest output", "status": "pending"},
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
            data["tool_counts"],
            {"read": 1, "edit": 2, "write": 1, "bash": 2},
        )
        self.assertTrue(data["path"].endswith("messages.jsonl"))
        self.assertIn("/sessions/2026/10/27/", data["path"])

    def test_show_by_transcript_path(self) -> None:
        data = self.show_json("minimax-code:c0de4001", "--messages", "0")
        source = data["path"]

        code, out, err = self.run_cli("show", source)
        self.assertEqual(code, 0, err)
        self.assertIn("# minimax-code:c0de4001", out)

        code, out, err = self.run_cli("prompts", source, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "5")

    def test_api_error_surfaces_in_digest(self) -> None:
        code, out, err = self.run_cli("show", "minimax-code:c0de4002")
        self.assertEqual(code, 0, err)
        self.assertIn("[API error] exceed quota limit (429)", out)

        data = self.show_json("minimax-code:c0de4002")
        self.assertEqual(data["last_prompt"], PROMPT_PLAIN)
        self.assertEqual(data["model"], "minimax/MiniMax-M2")

    def test_show_missing_and_ambiguous_refs(self) -> None:
        code, out, err = self.run_cli("show", "minimax-code:c0de4fff")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "minimax-code:c0de400")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", err)

        code, out, err = self.run_cli("show", "minimax-code:c0d")
        self.assertEqual(code, 2)
        self.assertIn("too short", err)

        code, out, err = self.run_cli("show", "minimax-code:mvs_c0de4001")
        self.assertEqual(code, 0, err)
        self.assertIn("# minimax-code:c0de4001", out)

        code, out, err = self.run_cli("show", "c0de4001")
        self.assertEqual(code, 0, err)
        self.assertIn("# minimax-code:c0de4001", out)

    def test_archive_state_does_not_cross_harnesses(self) -> None:
        sessions = self.run_json(
            "search",
            "--harness",
            "qoder-cn",
            "--include-archived",
            "--limit",
            "0",
        )
        refs = {session["ref"] for session in sessions}
        self.assertFalse(any(ref.startswith("minimax-code:") for ref in refs))

        code, out, err = self.run_cli(
            "show", "c0de4003", "--harness", "qoder-cn"
        )
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli(
            "prompts", "minimax-code:c0de4001", "--count"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "5")

        code, out, err = self.run_cli("prompts", "minimax-code:c0de4001")
        self.assertEqual(code, 0, err)
        for index, prompt in enumerate(PROMPTS_MAIN, 1):
            self.assertIn("## %d" % index, out)
            self.assertIn(prompt, out)
        self.assertNotIn(PROMPT_CRON_MESSAGE, out)
        self.assertNotIn(PROMPT_QUESTIONNAIRE, out)
        self.assertNotIn(COMPACT_SUMMARY_MAIN, out)

        code, out, err = self.run_cli(
            "prompts",
            "minimax-code:c0de4001",
            "--offset",
            "1",
            "--limit",
            "2",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("## 2", out)
        self.assertIn("## 3", out)
        self.assertNotIn(PROMPTS_MAIN[0], out)
        self.assertIn("next: --offset 3 --limit 2", out)

        code, out, err = self.run_cli(
            "prompts",
            "minimax-code:c0de4001",
            "--order",
            "newest",
            "--limit",
            "2",
        )
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("## 5"), out.index("## 4"))
        self.assertNotIn("## 3", out)

        code, out, err = self.run_cli(
            "prompts", "minimax-code:c0de4001", "--offset", "9"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts",
            "minimax-code:c0de4001",
            "--limit",
            "1",
            "--chars",
            "10",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Please re…", out)
        self.assertNotIn(PROMPTS_MAIN[0], out)

    def test_prompts_json_and_archived(self) -> None:
        data = self.run_json(
            "prompts", "minimax-code:c0de4001", "--limit", "2"
        )
        self.assertEqual(data["ref"], "minimax-code:c0de4001")
        self.assertEqual(data["session_id"], DISPLAY_MAIN)
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertFalse(data["archived"])
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["offset"], 0)
        self.assertEqual(data["limit"], 2)
        self.assertEqual(data["returned"], 2)
        self.assertTrue(data["has_more"])
        self.assertEqual(
            [prompt["index"] for prompt in data["prompts"]], [1, 2]
        )
        self.assertEqual(data["prompts"][0]["text"], PROMPTS_MAIN[0])
        self.assertIsNotNone(data["prompts"][0]["timestamp"])
        self.assertTrue(data["path"].endswith("messages.jsonl"))

        data = self.run_json(
            "prompts", "minimax-code:c0de4003", "--count"
        )
        self.assertTrue(data["archived"])
        self.assertEqual(data["total"], 1)

    def test_non_human_rows_never_become_prompts(self) -> None:
        data = self.run_json(
            "prompts", "minimax-code:c0de4001", "--limit", "0"
        )
        texts = [prompt["text"] for prompt in data["prompts"]]
        self.assertEqual(texts, list(PROMPTS_MAIN))
        for text in texts:
            self.assertNotIn("<system-reminder", text)
            self.assertNotIn("<questionnaire-response", text)

    def test_missing_database_falls_back_to_transcripts(self) -> None:
        sessions = self.run_json(
            "search",
            "--harness",
            "minimax-code",
            "--limit",
            "0",
            minimax_code_app_db=self.no_minimax_code_db,
        )
        by_id = {session["session_id"]: session for session in sessions}
        self.assertEqual(len(sessions), 8)
        for raw_id in (
            SESSION_MAIN,
            SESSION_PLAIN,
            SESSION_ARCHIVED,
            SESSION_HIDDEN,
            SESSION_CHILD,
            SESSION_PEEK,
            SESSION_CRON,
        ):
            self.assertIn(_display(raw_id), by_id)
        # Without the database there is no archive metadata and no way to
        # filter internal sessions; everything degrades to active.
        self.assertFalse(by_id[DISPLAY_ARCHIVED]["archived"])
        self.assertEqual(by_id[DISPLAY_MAIN]["title"], PROMPTS_MAIN[4])

        code, out, err = self.run_cli(
            "prompts",
            "minimax-code:c0de4001",
            "--count",
            minimax_code_app_db=self.no_minimax_code_db,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "2")

        data = self.show_json(
            "minimax-code:c0de4001",
            "--messages",
            "0",
            minimax_code_app_db=self.no_minimax_code_db,
        )
        self.assertEqual(data["compact_summary"], COMPACT_SUMMARY_MAIN)
        self.assertEqual(data["turn_count"], 2)
        self.assertEqual(
            data["todos"],
            [{"subject": "Trim digest output", "status": "pending"}],
        )
        self.assertEqual(
            data["tool_counts"], {"read": 1, "edit": 1, "todowrite": 1}
        )

        payload = self.run_json(
            "doctor",
            "--harness",
            "minimax-code",
            minimax_code_app_db=self.no_minimax_code_db,
        )
        store = payload["stores"][0]
        self.assertEqual(store["candidates"], 8)
        self.assertEqual(store["readable"], 8)
        self.assertEqual(store["skipped"], 0)

    def test_empty_store_is_safe(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "minimax-code",
            minimax_code_home=self.empty_minimax_code_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "latest",
            "--harness",
            "minimax-code",
            minimax_code_home=self.empty_minimax_code_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_doctor_counts(self) -> None:
        code, out, err = self.run_cli(
            "doctor", "--harness", "minimax-code"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("minimax-code (~/.minimax/v2) [present]", out)
        self.assertIn("candidates: 4, readable: 4, skipped: 0", out)

        payload = self.run_json("doctor", "--harness", "minimax-code")
        store = payload["stores"][0]
        self.assertEqual(store["harness"], "minimax-code")
        self.assertEqual(store["variants"], "cli")
        self.assertNotIn("c0de4001", json.dumps(payload))

        payload = self.run_json(
            "doctor",
            "--harness",
            "minimax-code",
            minimax_code_home=self.empty_minimax_code_home,
        )
        store = payload["stores"][0]
        self.assertTrue(store["present"])
        self.assertEqual(store["candidates"], 0)
        self.assertEqual(store["readable"], 0)

    def test_commands_do_not_modify_store(self) -> None:
        def snapshot() -> dict:
            files = {}
            for path in self.minimax_code_home.rglob("*"):
                if path.is_file():
                    files[str(path)] = (
                        path.read_bytes(),
                        path.stat().st_mtime_ns,
                    )
            return files

        before = snapshot()
        self.run_cli("search", "--harness", "minimax-code")
        self.run_cli(
            "search", "--harness", "minimax-code", "--include-archived"
        )
        self.run_cli(
            "search", "--harness", "minimax-code", "--deep", "deep-only-needle"
        )
        self.run_cli("latest", "--harness", "minimax-code")
        self.run_cli("show", "minimax-code:c0de4001")
        self.run_cli("show", "minimax-code:c0de4003", "--format", "json")
        self.run_cli("prompts", "minimax-code:c0de4001")
        self.run_cli("prompts", "minimax-code:c0de4001", "--count")
        self.run_cli("doctor", "--harness", "minimax-code")
        self.assertEqual(snapshot(), before)
        self.assertFalse(
            any(
                path.name.endswith(("-wal", "-shm", "-journal"))
                for path in self.minimax_code_home.rglob("*")
            )
        )

    def test_fixture_data_is_synthetic(self) -> None:
        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        for path in self.minimax_code_home.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8", "ignore")
            self.assertNotIn(str(Path.home()), text)
            self.assertNotIn("/Volumes/", text)
            self.assertNotIn("/home/", text)
            self.assertNotIn("/Users/", text.replace("/Users/example/", ""))
            self.assertIsNone(email.search(text), str(path))

        connection = sqlite3.connect(
            self.minimax_code_db.as_uri() + "?mode=ro", uri=True
        )
        try:
            ids = [
                row[0]
                for row in connection.execute(
                    "SELECT session_id FROM local_runtime_sessions"
                )
            ]
        finally:
            connection.close()
        self.assertEqual(len(ids), 8)
        for session_id in ids:
            self.assertTrue(session_id.startswith("mvs_c0de400"), session_id)
