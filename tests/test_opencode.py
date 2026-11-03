"""Tests for the OpenCode adapter.

The store is generated at runtime by ``opencode_fixture`` and mirrors the
2.2.5 schema transition: ``session_v2`` is authoritative and one session
exists only there. Every identifier, path, and prompt is synthetic.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from cli_support import FixtureTestCase  # noqa: E402
from opencode_fixture import (  # noqa: E402
    COMPACT_SUMMARY,
    DISPLAY_ARCHIVED,
    DISPLAY_MAIN,
    DISPLAY_NOTITLE,
    DISPLAY_PLAIN,
    DISPLAY_V2ONLY,
    MODEL_MAIN,
    NEEDLE_ARCHIVED,
    NEEDLE_DEEP_ONLY,
    NEEDLE_SUBAGENT,
    PROJECT_ALPHA,
    PROJECT_GAMMA,
    PROMPTS_MAIN,
    SESSION_MAIN,
    TITLE_PLAIN,
    TITLE_V2ONLY,
    VERSION_MAIN,
)

REF_MAIN = "opencode:" + DISPLAY_MAIN[:8]
REF_PLAIN = "opencode:" + DISPLAY_PLAIN[:8]
REF_ARCHIVED = "opencode:" + DISPLAY_ARCHIVED[:8]
REF_V2ONLY = "opencode:" + DISPLAY_V2ONLY[:8]
REF_NOTITLE = "opencode:" + DISPLAY_NOTITLE[:8]


class OpenCodeTests(FixtureTestCase):
    def test_harness_row(self) -> None:
        payload = self.run_json("harnesses")
        row = next(row for row in payload if row["name"] == "opencode")
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["variants"], "cli, tui, ide")
        self.assertEqual(row["store"], "~/.local/share/opencode")
        self.assertIn("opencode", row["aliases"].split(", "))

    def test_lists_active_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "opencode")
        self.assertEqual(code, 0, err)
        refs = [line.split("\t")[0] for line in out.strip().splitlines()[1:]]
        self.assertEqual(
            refs,
            [REF_V2ONLY, REF_NOTITLE, REF_PLAIN, REF_MAIN],
        )
        self.assertNotIn(DISPLAY_ARCHIVED, out)
        self.assertNotIn("Explore the handoff module", out)

    def test_session_v2_only_session_is_listed(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "opencode", "session_v2 knows"
        )
        self.assertEqual(code, 0, err)
        self.assertIn(REF_V2ONLY, out)
        self.assertIn(TITLE_V2ONLY, out)

    def test_keyword_session_id_and_cwd_filters(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "opencode", "fallback")
        self.assertEqual(code, 0, err)
        self.assertIn(REF_PLAIN, out)
        self.assertIn(TITLE_PLAIN, out)

        code, out, err = self.run_cli("search", "--harness", "opencode", "0adc0001")
        self.assertEqual(code, 0, err)
        self.assertIn(REF_MAIN, out)

        code, out, err = self.run_cli(
            "search", "--harness", "opencode", "--cwd", PROJECT_ALPHA
        )
        self.assertEqual(code, 0, err)
        self.assertIn(REF_MAIN, out)
        self.assertIn(REF_V2ONLY, out)
        self.assertNotIn(REF_PLAIN, out)

        code, out, err = self.run_cli(
            "search", "--harness", "opencode", "no-such-keyword-anywhere"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_latest_and_query_filter(self) -> None:
        code, out, err = self.run_cli("latest", "--harness", "opencode")
        self.assertEqual(code, 0, err)
        self.assertIn(REF_V2ONLY, out)

        code, out, err = self.run_cli(
            "latest", "--harness", "opencode", "--cwd", PROJECT_GAMMA
        )
        self.assertEqual(code, 0, err)
        self.assertIn(REF_NOTITLE, out)

    def test_archived_sessions_hidden_by_default(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "opencode", "--include-archived"
        )
        self.assertEqual(code, 0, err)
        self.assertIn(REF_ARCHIVED, out)
        archived_row = next(
            line
            for line in out.splitlines()
            if line.startswith(REF_ARCHIVED + "\t")
        )
        self.assertTrue(archived_row.rstrip().endswith("\tyes"))

        code, out, err = self.run_cli("latest", "--harness", "opencode")
        self.assertEqual(code, 0, err)
        self.assertNotIn(REF_ARCHIVED, out)

    def test_deep_search_scans_only_the_matching_session(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "opencode", NEEDLE_DEEP_ONLY
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search", "--harness", "opencode", "--deep", NEEDLE_DEEP_ONLY
        )
        self.assertEqual(code, 0, err)
        self.assertIn(REF_MAIN, out)
        self.assertNotIn(REF_PLAIN, out)
        self.assertNotIn(REF_V2ONLY, out)

    def test_subagent_session_is_never_searched(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "opencode", "--deep", NEEDLE_SUBAGENT
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_deep_search_respects_archive_filter(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "opencode", "--deep", NEEDLE_ARCHIVED
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "opencode",
            "--include-archived",
            "--deep",
            NEEDLE_ARCHIVED,
        )
        self.assertEqual(code, 0, err)
        self.assertIn(REF_ARCHIVED, out)

    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli("show", REF_MAIN)
        self.assertEqual(code, 0, err)
        self.assertIn("# opencode:0adc0001", out)
        self.assertIn("- harness: opencode (cli, tui, ide)", out)
        self.assertIn("- cwd: `%s`" % PROJECT_ALPHA, out)
        self.assertIn("- turns: 3", out)
        self.assertIn("- model: `%s`" % MODEL_MAIN, out)
        self.assertIn("- version: `%s`" % VERSION_MAIN, out)
        self.assertIn("- source: `", out)
        self.assertIn("#" + SESSION_MAIN, out)
        self.assertIn("## Task", out)
        self.assertIn(PROMPTS_MAIN[0], out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn(COMPACT_SUMMARY, out)
        self.assertIn("## Todos (2 open / 3 total)", out)
        self.assertIn("[in_progress] Add prompt paging", out)
        self.assertIn("[API error] exceed quota limit", out)
        self.assertIn("src/handoff.py", out)
        self.assertIn("src/digest.py", out)
        self.assertIn("bash: python3 -m unittest tests.test_handoff", out)
        self.assertNotIn("Explore the parser entry points.", out)
        self.assertNotIn(NEEDLE_SUBAGENT, out)

    def test_show_json_fields(self) -> None:
        code, out, err = self.run_cli("show", REF_MAIN, "--format", "json")
        self.assertEqual(code, 0, err)
        detail = json.loads(out)
        self.assertEqual(detail["harness"], "opencode")
        self.assertEqual(detail["session_id"], DISPLAY_MAIN)
        self.assertEqual(detail["cwd"], PROJECT_ALPHA)
        self.assertEqual(detail["model"], MODEL_MAIN)
        self.assertEqual(detail["version"], VERSION_MAIN)
        self.assertEqual(detail["size_bytes"], 0)
        self.assertEqual(detail["turn_count"], 3)
        self.assertEqual(detail["compact_summary"], COMPACT_SUMMARY)
        self.assertEqual(
            [todo["status"] for todo in detail["todos"]],
            ["completed", "in_progress", "pending"],
        )
        edited = {entry["path"]: entry["count"] for entry in detail["edited_files"]}
        self.assertEqual(edited[PROJECT_ALPHA + "/src/handoff.py"], 1)
        self.assertEqual(edited[PROJECT_ALPHA + "/src/digest.py"], 1)
        tool_names = set(detail["tool_counts"])
        self.assertIn("read", tool_names)
        self.assertIn("bash", tool_names)
        self.assertIn("edit", tool_names)
        self.assertEqual(detail["archived"], False)
        self.assertTrue(detail["path"].endswith("#" + SESSION_MAIN))

    def test_show_by_virtual_source_path(self) -> None:
        virtual = str(self.opencode_home / "opencode.db") + "#" + SESSION_MAIN
        code, out, err = self.run_cli("show", virtual)
        self.assertEqual(code, 0, err)
        self.assertIn(PROMPTS_MAIN[0], out)
        self.assertIn(SESSION_MAIN, out)

    def test_show_archived_session(self) -> None:
        code, out, err = self.run_cli("show", REF_ARCHIVED)
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)

        code, out, err = self.run_cli(
            "show", REF_ARCHIVED, "--format", "json"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["archived"], True)

    def test_bare_prefix_and_missing_refs(self) -> None:
        code, out, err = self.run_cli("show", DISPLAY_MAIN)
        self.assertEqual(code, 0, err)
        self.assertIn("# opencode:0adc0001", out)
        self.assertIn(PROMPTS_MAIN[0], out)

        code, out, err = self.run_cli("show", "opencode:zzzz")
        self.assertEqual(code, 2, err)
        self.assertIn("no session matched", err)

    def test_prompts_count_and_paging(self) -> None:
        code, out, err = self.run_cli("prompts", REF_MAIN, "--count")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "3")

        code, out, err = self.run_cli("prompts", REF_MAIN, "--limit", "2")
        self.assertEqual(code, 0, err)
        self.assertIn("total: 3, returned: 2, order: oldest", out)
        self.assertIn(PROMPTS_MAIN[0], out)
        self.assertIn(PROMPTS_MAIN[1], out)
        self.assertNotIn(PROMPTS_MAIN[2], out)
        self.assertIn("next: --offset 2 --limit 2", out)

        code, out, err = self.run_cli(
            "prompts", REF_MAIN, "--limit", "2", "--offset", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertIn(PROMPTS_MAIN[2], out)
        self.assertNotIn(PROMPTS_MAIN[0], out)

        code, out, err = self.run_cli(
            "prompts", REF_MAIN, "--order", "newest", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertIn(PROMPTS_MAIN[2], out)
        self.assertNotIn(PROMPTS_MAIN[0], out)

        code, out, err = self.run_cli("prompts", REF_MAIN, "--offset", "9")
        self.assertEqual(code, 0, err)
        self.assertIn("returned: 0", out)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts", REF_MAIN, "--chars", "20"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("…", out)

    def test_prompts_exclude_injected_and_command_records(self) -> None:
        code, out, err = self.run_cli("prompts", REF_MAIN)
        self.assertEqual(code, 0, err)
        # The multi-part prompt keeps both halves, in order.
        self.assertIn("Continue with the tests.\nThen update the docs.", out)
        # Synthetic context, attachments, slash commands, and child-session
        # prompts never appear.
        self.assertNotIn("system-reminder", out)
        self.assertNotIn("notes.txt", out)
        self.assertNotIn("/agents", out)
        self.assertNotIn(NEEDLE_SUBAGENT, out)

        code, out, err = self.run_cli("prompts", REF_PLAIN, "--count")
        self.assertEqual(code, 0, err)
        # The partially written part after the valid prompt is skipped.
        self.assertEqual(out.strip(), "1")

    def test_prompts_json(self) -> None:
        code, out, err = self.run_cli(
            "prompts", REF_MAIN, "--json", "--limit", "1", "--chars", "40"
        )
        self.assertEqual(code, 0, err)
        listing = json.loads(out)
        self.assertEqual(listing["total"], 3)
        self.assertEqual(listing["returned"], 1)
        self.assertEqual(listing["limit"], 1)
        prompt = listing["prompts"][0]
        self.assertEqual(prompt["index"], 1)
        self.assertTrue(prompt["text"].endswith("…"))
        self.assertTrue(prompt["timestamp"].startswith("2026-10-20T"))

    def test_doctor_reports_the_store(self) -> None:
        payload = self.run_json("doctor", "--harness", "opencode", "--fingerprint")
        store = next(item for item in payload["stores"] if item["harness"] == "opencode")
        self.assertTrue(store["present"])
        self.assertEqual(store["candidates"], 5)
        self.assertEqual(store["readable"], 5)
        self.assertEqual(store["skipped"], 0)
        self.assertEqual(store["home"], "<custom>")
        fingerprint = store["fingerprint"]
        self.assertEqual(fingerprint["kinds"]["sqlite"]["files"], 1)
        tables = {
            table["name"]: table for table in fingerprint["kinds"]["sqlite"]["tables"]
        }
        self.assertIn("session_v2", tables)
        self.assertEqual(tables["session_v2"]["rows"], 6)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(PROJECT_ALPHA, serialized)
        self.assertNotIn("Users/example", serialized)

    def test_empty_store_is_safe(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "opencode", opencode_home=self.empty_opencode_home
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "doctor", "--harness", "opencode", opencode_home=self.empty_opencode_home
        )
        self.assertEqual(code, 0, err)
        self.assertIn("candidates: 0, readable: 0, skipped: 0", out)

    def test_commands_do_not_modify_opencode_store(self) -> None:
        db = self.opencode_home / "opencode.db"
        snapshot = {}
        for path in (db, Path(str(db) + "-wal"), Path(str(db) + "-shm")):
            if path.is_file():
                snapshot[path.name] = (path.read_bytes(), path.stat().st_mtime_ns)
        snapshot_files = sorted(
            path.name for path in self.opencode_home.rglob("*") if path.is_file()
        )

        self.run_cli("search", "--harness", "opencode")
        self.run_cli("latest", "--harness", "opencode")
        self.run_cli("show", REF_MAIN)
        self.run_cli("prompts", REF_MAIN, "--count")
        self.run_cli("search", "--harness", "opencode", "--deep", NEEDLE_DEEP_ONLY)
        self.run_cli("doctor", "--harness", "opencode")

        for name, (data, mtime) in snapshot.items():
            path = self.opencode_home / name
            self.assertEqual(path.read_bytes(), data, name)
            self.assertEqual(path.stat().st_mtime_ns, mtime, name)
        self.assertEqual(
            sorted(
                path.name for path in self.opencode_home.rglob("*") if path.is_file()
            ),
            snapshot_files,
        )
        self.assertNotIn("opencode.db-wal", snapshot_files)
        self.assertNotIn("opencode.db-shm", snapshot_files)

    def test_wal_mode_store_is_not_written(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-opencode-wal-") as temp:
            home = Path(temp) / "wal-home"
            shutil.copytree(self.opencode_home, home)
            db = home / "opencode.db"
            writer = sqlite3.connect(str(db))
            try:
                writer.execute("PRAGMA journal_mode=WAL")
                writer.execute("PRAGMA wal_autocheckpoint=0")
                writer.execute("UPDATE session_v2 SET time_updated = time_updated + 1")
                writer.commit()
                wal = Path(str(db) + "-wal")
                self.assertTrue(wal.is_file())
                db_bytes = db.read_bytes()
                db_mtime = db.stat().st_mtime_ns
                wal_bytes = wal.read_bytes()

                self.run_cli("search", "--harness", "opencode", opencode_home=home)
                self.run_cli("latest", "--harness", "opencode", opencode_home=home)
                self.run_cli("show", REF_MAIN, opencode_home=home)
                self.run_cli(
                    "prompts", REF_MAIN, "--count", opencode_home=home
                )
                self.run_cli(
                    "search",
                    "--harness",
                    "opencode",
                    "--deep",
                    NEEDLE_DEEP_ONLY,
                    opencode_home=home,
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
        from opencode_fixture import SCHEMA  # noqa: F401

        module = sys.modules["opencode_fixture"]
        for name in dir(module):
            value = getattr(module, name)
            if isinstance(value, str) and value.startswith("/Users/"):
                self.assertTrue(
                    value.startswith("/Users/example/"),
                    "unexpected real path in fixture: %s" % value,
                )


if __name__ == "__main__":
    unittest.main()
