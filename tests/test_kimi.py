from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from cli_support import (
    FixtureTestCase,
    FIXTURE_KIMI_HOME,
    SESSION_E,
    _copy_fixture_home,
)


class KimiCodeTests(FixtureTestCase):
    def wire_path(self, session_id: str) -> Path:
        return next(
            self.kimi_home.glob(
                "sessions/*/session_%s/agents/main/wire.jsonl" % session_id
            )
        )

    def event_path(self, session_id: str) -> Path:
        return (
            self.kimi_home
            / "server"
            / "events"
            / ("session_%s.jsonl" % session_id)
        )

    def test_desktop_and_cli_share_one_harness(self) -> None:
        rows = self.run_json("harnesses")
        kimi_rows = [row for row in rows if row["name"] == "kimi-code"]
        self.assertEqual(len(kimi_rows), 1)
        self.assertEqual(kimi_rows[0]["variants"], "desktop, cli")
        self.assertEqual(kimi_rows[0]["aliases"], "kimi-code, kimi, kimi-code-cli, kimi-code-desktop")

        sessions = self.run_json(
            "search", "--harness", "kimi", "--limit", "0"
        )
        variants = {session["variants"] for session in sessions}
        self.assertEqual(variants, {"desktop", "cli"})

    def test_lists_active_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "kimi-code")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("kimi-code:e5f6a7b8"))
        self.assertTrue(lines[1].startswith("kimi-code:a7b8c9d0"))
        self.assertNotIn("kimi-code:f6a7b8c9", out)

    def test_aliases(self) -> None:
        for alias in ("kimi", "kimi-code-cli", "kimi-code-desktop"):
            code, out, err = self.run_cli(
                "search", "--harness", alias, "handoff"
            )
            self.assertEqual(code, 0, err)
            self.assertIn("kimi-code:e5f6a7b8", out)

    def test_keyword_and_session_id_prefix(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "kimi-code", "handoff"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("kimi-code:e5f6a7b8", out)
        self.assertNotIn("kimi-code:a7b8c9d0", out)

        code, out, err = self.run_cli(
            "search", "--harness", "kimi-code", "e5f6a7b8"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("kimi-code:e5f6a7b8", out)
        self.assertNotIn("kimi-code:a7b8c9d0", out)

        code, out, err = self.run_cli(
            "show", "kimi-code:session_e5f6a7b8"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("# kimi-code:e5f6a7b8", out)

    def test_cwd_since_limit_and_no_match(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "kimi-code",
            "--cwd",
            "/Users/example/project-alpha",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("kimi-code:e5f6a7b8", out)
        self.assertNotIn("kimi-code:a7b8c9d0", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "kimi-code",
            "--cwd",
            "/Users/example/project-gamma",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("kimi-code:a7b8c9d0", out)
        self.assertNotIn("kimi-code:e5f6a7b8", out)

        code, out, err = self.run_cli(
            "search", "--harness", "kimi-code", "--since", "2026-10-23"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("kimi-code:e5f6a7b8", out)
        self.assertIn("kimi-code:a7b8c9d0", out)

        code, out, err = self.run_cli(
            "search", "--harness", "kimi-code", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

        code, out, err = self.run_cli(
            "search", "--harness", "kimi-code", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_deep_search_scans_main_wire_only(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "kimi-code", "deep-only-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        for token, expected in (
            ("deep-only-needle", "kimi-code:e5f6a7b8"),
            ("wire-only-needle", "kimi-code:a7b8c9d0"),
        ):
            code, out, err = self.run_cli(
                "search", "--harness", "kimi-code", "--deep", token
            )
            self.assertEqual(code, 0, err)
            self.assertIn(expected, out)

        code, out, err = self.run_cli(
            "search", "--harness", "kimi-code", "--deep", "reviewer-only-marker"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_archive_filter(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "kimi-code", "invoice"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "kimi-code",
            "--include-archived",
            "invoice",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("kimi-code:f6a7b8c9", out)
        self.assertIn("\tyes", out)

        code, out, err = self.run_cli(
            "search", "--harness", "kimi-code", "--deep", "archived-needle"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "kimi-code",
            "--include-archived",
            "--deep",
            "archived-needle",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("kimi-code:f6a7b8c9", out)

    def test_latest_excludes_archived(self) -> None:
        code, out, err = self.run_cli("latest", "--harness", "kimi-code")
        self.assertEqual(code, 0, err)
        self.assertIn("kimi-code:e5f6a7b8", out)
        self.assertNotIn("kimi-code:f6a7b8c9", out)

        sessions = self.run_json(
            "latest", "--harness", "kimi-code", "--include-archived", "--limit", "0"
        )
        self.assertEqual(
            [session["ref"] for session in sessions],
            ["kimi-code:e5f6a7b8", "kimi-code:a7b8c9d0", "kimi-code:f6a7b8c9"],
        )
        self.assertTrue(sessions[-1]["archived"])

    def test_show_digest(self) -> None:
        code, out, err = self.run_cli("show", "kimi-code:e5f6a7b8")
        self.assertEqual(code, 0, err)
        self.assertIn("# kimi-code:e5f6a7b8", out)
        self.assertIn("- harness: kimi-code (desktop)", out)
        self.assertIn("- cwd: `/Users/example/project-alpha`", out)
        self.assertIn("- turns: 5", out)
        self.assertIn("- model: `kimi-k2`", out)
        self.assertIn("## Task\nRefactor handoff parser for the CLI", out)
        self.assertIn("## Latest request\nExplain the token budget", out)
        self.assertIn("## Todos (1 open / 2 total)", out)
        self.assertIn("[in_progress] Extract token budget helper", out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn("Handoff parser work summarized.", out)
        self.assertIn("## Edited files", out)
        self.assertIn("`/Users/example/project-alpha/src/handoff.ts` (x2)", out)
        self.assertIn("`/Users/example/project-alpha/docs/handoff.md`", out)
        self.assertIn("## Recent tools", out)
        self.assertNotIn("hidden reasoning", out)
        self.assertNotIn("File contents:", out)
        self.assertNotIn("reviewer-only-marker", out)

    def test_show_json(self) -> None:
        code, out, err = self.run_cli(
            "show",
            "kimi-code:e5f6a7b8",
            "--format",
            "json",
            "--messages",
            "5",
        )
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["ref"], "kimi-code:e5f6a7b8")
        self.assertEqual(data["session_id"], SESSION_E)
        self.assertEqual(data["variants"], "desktop")
        self.assertEqual(data["model"], "kimi-k2")
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertEqual(data["turn_count"], 5)
        self.assertEqual(
            [todo["status"] for todo in data["todos"]],
            ["in_progress", "completed"],
        )
        self.assertEqual(len(data["exchanges"]), 5)
        self.assertEqual(
            [exchange["user"] for exchange in data["exchanges"]],
            [
                "Refactor handoff parser for the CLI",
                "Also list every edited file",
                "Keep the output under two pages",
                "继续",
                "Explain the token budget",
            ],
        )
        self.assertEqual(
            data["edited_files"][0],
            {
                "path": "/Users/example/project-alpha/src/handoff.ts",
                "count": 2,
            },
        )
        self.assertEqual(data["tool_counts"]["Edit"], 2)
        self.assertNotIn(
            "hidden reasoning",
            json.dumps([exchange["assistant"] for exchange in data["exchanges"]]),
        )

    def test_show_archived_and_by_path(self) -> None:
        code, out, err = self.run_cli("show", "kimi-code:f6a7b8c9")
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)
        self.assertIn("## Task\nExport invoices as CSV", out)
        self.assertIn("## Latest request\nInclude a totals row", out)
        self.assertIn("`/Users/example/project-beta/src/invoice.ts`", out)

        code, out, err = self.run_cli("show", str(self.wire_path(SESSION_E)))
        self.assertEqual(code, 0, err)
        self.assertIn("# kimi-code:e5f6a7b8", out)

        code, out, err = self.run_cli("show", str(self.event_path(SESSION_E)))
        self.assertEqual(code, 0, err)
        self.assertIn("# kimi-code:e5f6a7b8", out)

    def test_show_wire_fallback_session(self) -> None:
        code, out, err = self.run_cli("show", "kimi-code:a7b8c9d0")
        self.assertEqual(code, 0, err)
        self.assertIn("- harness: kimi-code (cli)", out)
        self.assertIn("- cwd: `/Users/example/project-gamma`", out)
        self.assertIn("- model: `kimi-for-coding`", out)
        self.assertIn("## Task\nMigration checklist for legacy sessions", out)
        self.assertIn("`/Users/example/project-gamma/src/migrate.ts`", out)
        self.assertNotIn("task-generated prompt", out)
        self.assertNotIn("skill activation body", out)

    def test_prompts_listing_and_exclusions(self) -> None:
        code, out, err = self.run_cli("prompts", "kimi-code:e5f6a7b8")
        self.assertEqual(code, 0, err)
        self.assertIn("# kimi-code:e5f6a7b8 user prompts", out)
        self.assertIn("total: 5, returned: 5, order: oldest", out)
        self.assertIn("Refactor handoff parser for the CLI", out)
        self.assertIn("Also list every edited file", out)
        self.assertIn("Keep the output under two pages", out)
        self.assertIn("继续", out)
        self.assertIn("Explain the token budget", out)
        self.assertNotIn("Expanded skill body", out)
        self.assertNotIn("Review the parser changes", out)
        self.assertNotIn("only hidden context", out)
        self.assertNotIn("skill activation body", out)
        self.assertNotIn("File contents:", out)

        code, out, err = self.run_cli(
            "prompts", "kimi-code:e5f6a7b8", "--count"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "5")

        code, out, err = self.run_cli(
            "prompts", "kimi-code:a7b8c9d0", "--count"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "1")

        code, out, err = self.run_cli("prompts", "kimi-code:f6a7b8c9")
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)
        self.assertIn("total: 2, returned: 2", out)

    def test_prompts_paging_and_chars(self) -> None:
        page = self.run_json(
            "prompts", "kimi-code:e5f6a7b8", "--limit", "2"
        )
        self.assertEqual([item["index"] for item in page["prompts"]], [1, 2])
        self.assertTrue(page["has_more"])

        page = self.run_json(
            "prompts",
            "kimi-code:e5f6a7b8",
            "--order",
            "newest",
            "--limit",
            "2",
        )
        self.assertEqual([item["index"] for item in page["prompts"]], [5, 4])
        self.assertTrue(page["has_more"])

        page = self.run_json(
            "prompts",
            "kimi-code:e5f6a7b8",
            "--offset",
            "99",
            "--limit",
            "2",
        )
        self.assertEqual(page["prompts"], [])
        self.assertEqual(page["returned"], 0)
        self.assertFalse(page["has_more"])

        page = self.run_json(
            "prompts", "kimi-code:e5f6a7b8", "--limit", "1", "--chars", "12"
        )
        self.assertEqual(len(page["prompts"][0]["text"]), 12)
        self.assertTrue(page["prompts"][0]["text"].endswith("…"))

        page = self.run_json("prompts", "kimi-code:e5f6a7b8")
        self.assertTrue(page["prompts"][0]["timestamp"].endswith("Z"))
        self.assertEqual(page["archived"], False)

    def test_refs_do_not_cross_stores(self) -> None:
        code, out, err = self.run_cli(
            "show", "e5f6a7b8", "--harness", "kimi-code"
        )
        self.assertEqual(code, 0, err)

        code, out, err = self.run_cli("show", "kimi-code:a1b2c3d4")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("prompts", "qoder-cn:e5f6a7b8")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("show", "qoder-cn:a7b8c9d0")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_ambiguous_prefix(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-kimi-ambiguous-") as raw:
            home = _copy_fixture_home(
                FIXTURE_KIMI_HOME, Path(raw) / "kimi-home"
            )
            source = next(
                home.glob(
                    "sessions/*/session_%s" % SESSION_E
                )
            )
            duplicate = source.with_name(
                "session_e5f6a7b8-9999-4fff-8aaa-999999999999"
            )
            shutil.copytree(source, duplicate)
            state_path = duplicate / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["id"] = "session_e5f6a7b8-9999-4fff-8aaa-999999999999"
            state_path.write_text(json.dumps(state), encoding="utf-8")

            code, out, err = self.run_cli(
                "show", "kimi-code:e5f6a7b8", kimi_home=home
            )
            self.assertEqual(code, 2)
            self.assertIn("ambiguous", err)
            self.assertIn("kimi-code:e5f6a7b8", err)
            self.assertIn("kimi-code:e5f6a7b8", err)

            code, out, err = self.run_cli(
                "show", "kimi-code:e5f6a7b8-5555", kimi_home=home
            )
            self.assertEqual(code, 0, err)

    def test_partial_final_line_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-kimi-partial-") as raw:
            home = _copy_fixture_home(
                FIXTURE_KIMI_HOME, Path(raw) / "kimi-home"
            )
            wire = next(
                home.glob(
                    "sessions/*/session_%s/agents/main/wire.jsonl" % SESSION_E
                )
            )
            event = (
                home
                / "server"
                / "events"
                / ("session_%s.jsonl" % SESSION_E)
            )
            for path in (wire, event):
                with path.open("a", encoding="utf-8") as handle:
                    handle.write('{"type":"turn.prompt","origin":')

            code, out, err = self.run_cli(
                "show", "kimi-code:e5f6a7b8", kimi_home=home
            )
            self.assertEqual(code, 0, err)
            code, out, err = self.run_cli(
                "prompts", "kimi-code:e5f6a7b8", "--count", kimi_home=home
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(out.strip(), "5")

    def test_archive_state_does_not_cross_editions(self) -> None:
        sessions = self.run_json(
            "search", "--harness", "qoder", "--include-archived", "--limit", "0"
        )
        refs = {session["ref"] for session in sessions}
        self.assertNotIn("kimi-code:f6a7b8c9", refs)
        self.assertLessEqual({"qoder:c3d4e5f6", "qoder:d4e5f6a7"}, refs)

    def test_commands_do_not_modify_kimi_store(self) -> None:
        def snapshot() -> dict:
            files = {}
            for path in self.kimi_home.rglob("*"):
                if path.is_file():
                    files[str(path)] = (
                        path.read_bytes(),
                        path.stat().st_mtime_ns,
                    )
            return files

        before = snapshot()
        self.run_cli("search", "--harness", "kimi-code")
        self.run_cli("latest", "--harness", "kimi-code", "--include-archived")
        self.run_cli("show", "kimi-code:e5f6a7b8")
        self.run_cli("show", "kimi-code:f6a7b8c9", "--format", "json")
        self.run_cli("prompts", "kimi-code:e5f6a7b8")
        self.run_cli("prompts", "kimi-code:a7b8c9d0", "--count")
        self.assertEqual(snapshot(), before)
