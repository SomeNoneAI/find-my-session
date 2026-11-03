from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cli_support import (
    FixtureTestCase,
    REPO_ROOT,
    SKILL_DIR,
    FIXTURE_HOME,
    FIXTURE_QODER_HOME,
    FIXTURE_KIMI_HOME,
    FMS,
    SESSION_A,
    SESSION_B,
    SESSION_C,
    SESSION_D,
    _copy_fixture_home,
    _write_archive_db,
    QoderCNAdapter,
    iter_tail_records,
    parse_timestamp,
)
from fms_lib import __version__


class UtilTests(unittest.TestCase):
    def test_tail_keeps_complete_last_line_without_newline(self) -> None:
        with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", delete=False) as handle:
            handle.write(b'{"a":1}\n{"b":2}')
            path = Path(handle.name)
        try:
            records = iter_tail_records(path, 1024)
            self.assertEqual([record.get("a") or record.get("b") for record in records], [1, 2])
        finally:
            path.unlink()

    def test_timestamp_accepts_epoch_milliseconds(self) -> None:
        parsed = parse_timestamp(1793176920893)
        self.assertIsNotNone(parsed)
        self.assertGreaterEqual(parsed.year, 2020)


class EntrypointTests(FixtureTestCase):
    def _run(self, command: str):
        env = dict(os.environ)
        env["FMS_QODER_CN_HOME"] = str(self.home)
        env["FMS_QODER_HOME"] = str(self.qoder_home)
        env["FMS_KIMI_CODE_HOME"] = str(self.kimi_home)
        env["FMS_ZCODE_HOME"] = str(self.zcode_home)
        env["FMS_ZCODE_APP_DB"] = str(self.zcode_app_db)
        argv = [command]
        if os.name == "nt":
            # The launchers are Python scripts; the shebang does not apply.
            argv = [sys.executable, command]
        return subprocess.run(
            [*argv, "--version"], capture_output=True, text=True, env=env
        )

    def test_entrypoint_runs_directly(self) -> None:
        result = self._run(str(FMS))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fms " + __version__, result.stdout)

    def test_entrypoint_runs_through_symlink(self) -> None:
        if os.name == "nt":
            self.skipTest("symlinks need elevated privileges on Windows")
        with tempfile.TemporaryDirectory(prefix="fms-link-") as raw:
            link = Path(raw) / "fms"
            link.symlink_to(FMS)
            result = self._run(str(link))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fms " + __version__, result.stdout)


class HarnessListingTests(FixtureTestCase):
    def test_lists_ready_and_planned(self) -> None:
        code, out, err = self.run_cli("harnesses")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], "harness\tstatus\tvariants\tstore\taliases")
        self.assertIn("qoder-cn\tready", out)
        self.assertIn("qoder\tready", out)
        self.assertIn("kimi-code\tready", out)
        self.assertIn("zcode\tready", out)
        self.assertIn("codearts-agent\tready", out)
        self.assertIn("workbuddy\tready", out)
        self.assertIn("codex\tready", out)
        self.assertIn("deepseek\tready", out)
        self.assertIn("claude-code\tready", out)
        self.assertIn("cline\tready", out)
        self.assertIn("grok-build\tready", out)
        self.assertIn("antigravity\tready", out)
        self.assertIn("antigravity-cli\tready", out)

    def test_json_rows(self) -> None:
        rows = self.run_json("harnesses")
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["qoder-cn"]["status"], "ready")
        self.assertEqual(by_name["qoder-cn"]["store"], "~/.qoder-cn")
        self.assertEqual(by_name["qoder"]["status"], "ready")
        self.assertEqual(by_name["qoder"]["store"], "~/.qoder")
        self.assertEqual(by_name["kimi-code"]["status"], "ready")
        self.assertEqual(by_name["kimi-code"]["store"], "~/.kimi-code")
        self.assertEqual(by_name["kimi-code"]["variants"], "desktop, cli")
        self.assertEqual(by_name["zcode"]["status"], "ready")
        self.assertEqual(by_name["zcode"]["store"], "~/.zcode")
        self.assertEqual(by_name["zcode"]["variants"], "desktop, cli")
        self.assertEqual(by_name["codex"]["status"], "ready")
        self.assertEqual(by_name["codex"]["store"], "~/.codex")
        self.assertEqual(by_name["codex"]["variants"], "desktop, ide, cli")
        self.assertEqual(by_name["codex"]["aliases"], "codex, chatgpt-codex")
        self.assertEqual(by_name["deepseek"]["status"], "ready")
        self.assertEqual(by_name["deepseek"]["store"], "~/.dsh")
        self.assertEqual(by_name["deepseek"]["variants"], "desktop")
        self.assertEqual(
            by_name["deepseek"]["aliases"], "deepseek, deepseek-harness, dsh"
        )
        self.assertEqual(by_name["claude-code"]["status"], "ready")
        self.assertEqual(by_name["claude-code"]["store"], "~/.claude")
        self.assertEqual(by_name["claude-code"]["variants"], "cli, ide")
        self.assertEqual(
            by_name["claude-code"]["aliases"], "claude, claude-code"
        )
        self.assertEqual(by_name["grok-build"]["status"], "ready")
        self.assertEqual(by_name["grok-build"]["store"], "~/.grok")
        self.assertEqual(
            by_name["grok-build"]["variants"], "tui, headless, acp"
        )
        self.assertEqual(
            by_name["grok-build"]["aliases"], "grok-build, grok, grok-cli"
        )
        self.assertEqual(by_name["antigravity"]["status"], "ready")
        self.assertEqual(
            by_name["antigravity"]["store"], "~/.gemini/antigravity"
        )
        self.assertEqual(by_name["antigravity"]["variants"], "desktop, ide")
        self.assertEqual(
            by_name["antigravity"]["aliases"],
            "antigravity, antigravity-desktop, antigravity-ide",
        )
        self.assertEqual(by_name["antigravity-cli"]["status"], "ready")
        self.assertEqual(
            by_name["antigravity-cli"]["store"], "~/.gemini/antigravity-cli"
        )
        self.assertEqual(by_name["antigravity-cli"]["variants"], "cli")
        self.assertEqual(
            by_name["antigravity-cli"]["aliases"], "antigravity-cli, agy"
        )

    def test_codex_is_not_planned(self) -> None:
        rows = self.run_json("harnesses")
        planned = {row["name"] for row in rows if row["status"] == "planned"}
        self.assertNotIn("codex", planned)

    def test_claude_code_is_not_planned(self) -> None:
        rows = self.run_json("harnesses")
        planned = {row["name"] for row in rows if row["status"] == "planned"}
        self.assertNotIn("claude-code", planned)

    def test_cline_is_not_planned(self) -> None:
        rows = self.run_json("harnesses")
        planned = {row["name"] for row in rows if row["status"] == "planned"}
        self.assertNotIn("cline", planned)
        self.assertIn("cline-vscode", planned)

    def test_deepseek_is_not_planned(self) -> None:
        rows = self.run_json("harnesses")
        planned = {row["name"] for row in rows if row["status"] == "planned"}
        self.assertNotIn("deepseek", planned)

    def test_grok_build_is_not_planned(self) -> None:
        rows = self.run_json("harnesses")
        planned = {row["name"] for row in rows if row["status"] == "planned"}
        self.assertNotIn("grok-build", planned)

    def test_antigravity_editions_are_separate_harnesses(self) -> None:
        rows = self.run_json("harnesses")
        planned = {row["name"] for row in rows if row["status"] == "planned"}
        ready = {row["name"] for row in rows if row["status"] == "ready"}
        self.assertLessEqual({"antigravity", "antigravity-cli"}, ready)
        self.assertNotIn("antigravity", planned)
        self.assertNotIn("antigravity-cli", planned)

    def test_kimi_code_is_not_planned(self) -> None:
        rows = self.run_json("harnesses")
        planned = {row["name"] for row in rows if row["status"] == "planned"}
        self.assertNotIn("kimi-code", planned)

    def test_zcode_is_not_planned(self) -> None:
        rows = self.run_json("harnesses")
        planned = {row["name"] for row in rows if row["status"] == "planned"}
        self.assertNotIn("zcode", planned)

    def test_qoder_products_are_separate_harnesses(self) -> None:
        rows = self.run_json("harnesses")
        ready = {row["name"] for row in rows if row["status"] == "ready"}
        self.assertLessEqual({"qoder-cn", "qoder"}, ready)
        self.assertNotIn("qoder", {row["name"] for row in rows if row["status"] == "planned"})

    def test_unknown_harness_errors(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "nope", "anything")
        self.assertEqual(code, 2)
        self.assertIn("unknown harness", err)
        self.assertIn("fms harnesses", err)

    def test_planned_harness_errors(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "codebuddy", "anything")
        self.assertEqual(code, 2)
        self.assertIn("planned but not implemented", err)
        self.assertIn("qoder-cn", err)


class SearchTests(FixtureTestCase):
    def test_lists_all_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qoder-cn")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("qoder-cn:b2c3d4e5"))
        self.assertTrue(lines[1].startswith("qoder-cn:a1b2c3d4"))

    def test_alias(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qcn", "oauth")
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:a1b2c3d4", out)
        self.assertNotIn("qoder-cn:b2c3d4e5", out)

    def test_keyword_matches_title(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qcn", "dark", "toggle")
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:b2c3d4e5", out)
        self.assertEqual(len(out.strip().splitlines()), 2)

    def test_all_tokens_must_match(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qcn", "oauth", "dark")
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_session_id_prefix(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qcn", "a1b2c3d4")
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:a1b2c3d4", out)
        self.assertNotIn("qoder-cn:b2c3d4e5", out)

    def test_cwd_filter(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "qcn", "--cwd", "/Users/example/project-alpha"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:a1b2c3d4", out)
        self.assertNotIn("qoder-cn:b2c3d4e5", out)

    def test_since_filter(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "qcn", "--since", "2026-10-25"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:b2c3d4e5", out)
        self.assertNotIn("qoder-cn:a1b2c3d4", out)

    def test_limit(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qcn", "--limit", "1")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 2)

    def test_limit_zero_means_all(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qcn", "--limit", "0")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.strip().splitlines()), 3)

    def test_no_match_message(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qcn", "no-such-topic")
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_deep_scans_transcripts(self) -> None:
        code, out, err = self.run_cli("search", "--harness", "qcn", "verifier-secret")
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)
        code, out, err = self.run_cli(
            "search", "--harness", "qcn", "--deep", "verifier-secret"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:a1b2c3d4", out)

    def test_json_output_fields(self) -> None:
        sessions = self.run_json("search", "--harness", "qcn", "oauth")
        self.assertEqual(len(sessions), 1)
        session = sessions[0]
        self.assertEqual(session["ref"], "qoder-cn:a1b2c3d4")
        self.assertEqual(session["session_id"], SESSION_A)
        self.assertEqual(session["cwd"], "/Users/example/project-alpha")
        self.assertTrue(Path(session["path"]).is_file())
        self.assertTrue(session["updated"].endswith("Z"))


class LatestTests(FixtureTestCase):
    def test_latest_returns_newest(self) -> None:
        code, out, err = self.run_cli("latest", "--harness", "qcn")
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:b2c3d4e5", out)
        self.assertEqual(len(out.strip().splitlines()), 2)

    def test_latest_with_cwd(self) -> None:
        code, out, err = self.run_cli(
            "latest", "--harness", "qcn", "--cwd", "/Users/example/project-alpha"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:a1b2c3d4", out)

    def test_latest_with_query(self) -> None:
        code, out, err = self.run_cli("latest", "--harness", "qcn", "PKCE")
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:a1b2c3d4", out)
        self.assertNotIn("qoder-cn:b2c3d4e5", out)


class ArchiveTests(FixtureTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        root = Path(cls._temp.name) / "app-db"
        root.mkdir()
        cls.cn_db = _write_archive_db(
            root / "cn-main.sqlite",
            [
                (SESSION_A, 1, 1793000000000, None),
                (SESSION_B, 0, None, None),
            ],
        )
        cls.qoder_db = _write_archive_db(
            root / "qoder-main.sqlite",
            [
                (SESSION_C, 1, 1793000000000, None),
                (SESSION_D, 0, None, None),
            ],
        )

    def test_search_excludes_archived_by_default(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "qcn", cn_db=self.cn_db
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:b2c3d4e5", out)
        self.assertNotIn("qoder-cn:a1b2c3d4", out)

        code, out, err = self.run_cli(
            "search", "--harness", "qoder", qoder_db=self.qoder_db
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder:d4e5f6a7", out)
        self.assertNotIn("qoder:c3d4e5f6", out)

        code, out, err = self.run_cli(
            "search", "--harness", "qoder", "--include-archived", qoder_db=self.qoder_db
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder:c3d4e5f6", out)

    def test_include_archived_lists_and_marks_rows(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "qcn", "--include-archived", cn_db=self.cn_db
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], "ref\tupdated\tcwd\ttitle\tarchived")
        marks = {
            parts[0]: parts[-1]
            for parts in (line.split("\t") for line in lines[1:])
        }
        self.assertEqual(marks["qoder-cn:a1b2c3d4"], "yes")
        self.assertEqual(marks["qoder-cn:b2c3d4e5"], "-")

    def test_latest_excludes_archived_unless_requested(self) -> None:
        code, out, err = self.run_cli(
            "latest", "--harness", "qcn", "oauth", cn_db=self.cn_db
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)
        self.assertIn("--include-archived", out)

        code, out, err = self.run_cli(
            "latest",
            "--harness",
            "qcn",
            "oauth",
            "--include-archived",
            cn_db=self.cn_db,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:a1b2c3d4", out)

    def test_json_exposes_archived_flag(self) -> None:
        sessions = self.run_json(
            "search",
            "--harness",
            "qcn",
            "oauth",
            "--include-archived",
            cn_db=self.cn_db,
        )
        self.assertTrue(sessions[0]["archived"])

        sessions = self.run_json("search", "--harness", "qcn", "dark", cn_db=self.cn_db)
        self.assertFalse(sessions[0]["archived"])

    def test_show_archived_session_by_ref(self) -> None:
        code, out, err = self.run_cli(
            "show", "qoder-cn:a1b2c3d4", cn_db=self.cn_db
        )
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)

        code, out, err = self.run_cli(
            "show", "qoder-cn:a1b2c3d4", "--format", "json", cn_db=self.cn_db
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["archived"])

        code, out, err = self.run_cli(
            "show", "qoder:c3d4e5f6", qoder_db=self.qoder_db
        )
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)

    def test_prompts_lists_archived_session(self) -> None:
        code, out, err = self.run_cli(
            "prompts", "qoder-cn:a1b2c3d4", cn_db=self.cn_db
        )
        self.assertEqual(code, 0, err)
        self.assertIn("- archived: yes", out)
        self.assertIn("total: 2", out)

        data = self.run_json(
            "prompts", "qoder-cn:a1b2c3d4", cn_db=self.cn_db
        )
        self.assertTrue(data["archived"])

        code, out, err = self.run_cli(
            "prompts", "qoder:c3d4e5f6", "--count", qoder_db=self.qoder_db
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "2")

    def test_deep_search_respects_archive_filter(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "qcn", "--deep", "verifier-secret", cn_db=self.cn_db
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "qcn",
            "--include-archived",
            "--deep",
            "verifier-secret",
            cn_db=self.cn_db,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:a1b2c3d4", out)

    def test_deleted_sessions_are_hidden_by_default(self) -> None:
        db = _write_archive_db(
            Path(self._temp.name) / "deleted-main.sqlite",
            [(SESSION_A, 0, None, 1793000000000)],
        )
        code, out, err = self.run_cli("search", "--harness", "qcn", cn_db=db)
        self.assertEqual(code, 0, err)
        self.assertNotIn("qoder-cn:a1b2c3d4", out)
        self.assertIn("qoder-cn:b2c3d4e5", out)

        code, out, err = self.run_cli(
            "search", "--harness", "qcn", "--include-archived", cn_db=db
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn:a1b2c3d4", out)

    def test_archive_state_does_not_cross_editions(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "qoder", cn_db=self.cn_db
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder:c3d4e5f6", out)
        self.assertIn("qoder:d4e5f6a7", out)

    def test_include_archived_empty_result_has_no_hint(self) -> None:
        code, out, err = self.run_cli(
            "search",
            "--harness",
            "qcn",
            "no-such-topic",
            "--include-archived",
            cn_db=self.cn_db,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "no sessions matched")

    def test_archive_databases_are_not_modified(self) -> None:
        paths = (self.cn_db, self.qoder_db)
        before = {path: path.read_bytes() for path in paths}
        self.run_cli("search", "--harness", "qcn", cn_db=self.cn_db)
        self.run_cli(
            "search",
            "--harness",
            "qoder",
            "--include-archived",
            qoder_db=self.qoder_db,
        )
        self.run_cli("show", "qoder-cn:a1b2c3d4", cn_db=self.cn_db)
        self.run_cli(
            "prompts", "qoder-cn:a1b2c3d4", "--count", cn_db=self.cn_db
        )
        self.assertEqual({path: path.read_bytes() for path in paths}, before)
        for path in paths:
            for suffix in ("-wal", "-shm"):
                self.assertFalse(Path(str(path) + suffix).exists())


class ShowTests(FixtureTestCase):
    def test_show_markdown_digest(self) -> None:
        code, out, err = self.run_cli("show", "qoder-cn:a1b2c3d4")
        self.assertEqual(code, 0, err)
        self.assertIn("# qoder-cn:a1b2c3d4", out)
        self.assertIn("## Task\nAdd OAuth token refresh to the CLI", out)
        self.assertIn("## Latest request\nAlso handle PKCE", out)
        self.assertIn("## Todos (2 open / 3 total)", out)
        self.assertIn("[in_progress] Refresh tokens before expiry", out)
        self.assertIn("## Edited files", out)
        self.assertIn("`/Users/example/project-alpha/src/auth.ts`", out)
        self.assertIn("## Recent tools", out)
        self.assertNotIn("Compact summary", out)
        self.assertNotIn("Sidechain", out)

    def test_show_compact_summary_and_todos(self) -> None:
        code, out, err = self.run_cli("show", "qoder-cn:b2c3d4e5")
        self.assertEqual(code, 0, err)
        self.assertIn("Add a dark mode toggle to settings", out)
        self.assertIn("## Compact summary (latest compaction)", out)
        self.assertIn("theme provider", out)
        self.assertIn("Verify contrast in light and dark themes", out)
        self.assertIn("src/settings/ThemeToggle.tsx", out)

    def test_show_by_path(self) -> None:
        path = (
            self.home
            / "projects"
            / "-Users-example-project-alpha"
            / (SESSION_A + ".jsonl")
        )
        code, out, err = self.run_cli("show", str(path))
        self.assertEqual(code, 0, err)
        self.assertIn("Add OAuth token refresh to the CLI", out)

    def test_show_alias_ref(self) -> None:
        code, out, err = self.run_cli("show", "qcn:a1b2c3d4")
        self.assertEqual(code, 0, err)
        self.assertIn("# qoder-cn:a1b2c3d4", out)

    def test_show_json(self) -> None:
        code, out, err = self.run_cli(
            "show", "qoder-cn:a1b2c3d4", "--format", "json", "--messages", "5"
        )
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["ref"], "qoder-cn:a1b2c3d4")
        self.assertEqual(data["turn_count"], 2)
        self.assertEqual([todo["status"] for todo in data["todos"]], ["completed", "in_progress", "pending"])
        self.assertEqual(len(data["exchanges"]), 2)
        self.assertEqual(data["edited_files"][0]["path"], "/Users/example/project-alpha/src/auth.ts")

    def test_show_messages_zero(self) -> None:
        code, out, err = self.run_cli(
            "show", "qoder-cn:a1b2c3d4", "--messages", "0"
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn("## Recent turns", out)

    def test_show_json_respects_bounds(self) -> None:
        code, out, err = self.run_cli(
            "show",
            "qoder-cn:a1b2c3d4",
            "--format",
            "json",
            "--messages",
            "1",
            "--chars",
            "40",
            "--no-todos",
            "--no-tools",
        )
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["todos"], [])
        self.assertEqual(data["recent_tools"], [])
        self.assertEqual(data["tool_counts"], {})
        self.assertEqual(len(data["exchanges"]), 1)
        for exchange in data["exchanges"]:
            self.assertEqual(exchange["tools"], [])
            self.assertLessEqual(len(exchange["user"]), 40)
            for text in exchange["assistant"]:
                self.assertLessEqual(len(text), 40)

        code, out, err = self.run_cli(
            "show", "qoder-cn:b2c3d4e5", "--format", "json", "--summary-chars", "0"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["compact_summary"], "")

        code, out, err = self.run_cli(
            "show", "qoder-cn:b2c3d4e5", "--format", "json", "--summary-chars", "30"
        )
        self.assertEqual(code, 0, err)
        self.assertLessEqual(len(json.loads(out)["compact_summary"]), 30)

        code, out, err = self.run_cli(
            "show", "qoder-cn:a1b2c3d4", "--format", "json", "--messages", "0"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["exchanges"], [])

    def test_show_summary_chars_zero(self) -> None:
        code, out, err = self.run_cli(
            "show", "qoder-cn:b2c3d4e5", "--summary-chars", "0"
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn("Compact summary", out)

    def test_show_no_todos(self) -> None:
        code, out, err = self.run_cli("show", "qoder-cn:a1b2c3d4", "--no-todos")
        self.assertEqual(code, 0, err)
        self.assertNotIn("## Todos", out)

    def test_short_ref_errors(self) -> None:
        code, out, err = self.run_cli("show", "a1b")
        self.assertEqual(code, 2)
        self.assertIn("too short", err)

    def test_unknown_ref_errors(self) -> None:
        code, out, err = self.run_cli("show", "qoder-cn:deadbeef")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_ambiguous_ref_errors(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-ambiguous-") as raw:
            home = _copy_fixture_home(FIXTURE_HOME, Path(raw) / "home")
            source = (
                home
                / "projects"
                / "-Users-example-project-alpha"
                / (SESSION_A + ".jsonl")
            )
            shutil.copyfile(
                source,
                source.with_name("a1b2c3d4-9999-4fff-8aaa-999999999999.jsonl"),
            )
            code, out, err = self.run_cli("show", "qoder-cn:a1b2c3d4", home=home)
            self.assertEqual(code, 2)
            self.assertIn("ambiguous", err)
            self.assertIn("qoder-cn:a1b2c3d4", err)
            self.assertIn("qoder-cn:a1b2c3d", err)
            code, out, err = self.run_cli(
                "show", "qoder-cn:a1b2c3d4-1111", home=home
            )
            self.assertEqual(code, 0, err)

    def test_path_outside_store_errors(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
            handle.write("{}\n")
            path = handle.name
        try:
            code, out, err = self.run_cli("show", path)
            self.assertEqual(code, 2)
            self.assertIn("not inside a known harness session store", err)
        finally:
            os.unlink(path)


class PromptsTests(FixtureTestCase):
    def test_lists_every_human_prompt(self) -> None:
        code, out, err = self.run_cli("prompts", "qoder-cn:a1b2c3d4")
        self.assertEqual(code, 0, err)
        self.assertIn("# qoder-cn:a1b2c3d4 user prompts", out)
        self.assertIn("total: 2, returned: 2, order: oldest", out)
        self.assertIn("## 1 · ", out)
        self.assertIn("Add OAuth token refresh to the CLI", out)
        self.assertIn("## 2 · ", out)
        self.assertIn("Also handle PKCE for the desktop login flow", out)
        self.assertNotIn("system-reminder", out)
        self.assertNotIn("Sidechain", out)

    def test_count_ignores_pagination_and_chars(self) -> None:
        code, out, err = self.run_cli(
            "prompts",
            "qoder-cn:a1b2c3d4",
            "--count",
            "--offset",
            "1",
            "--limit",
            "1",
            "--chars",
            "5",
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "2")

        count = self.run_json(
            "prompts", "qoder-cn:a1b2c3d4", "--count", "--offset", "1"
        )
        self.assertEqual(count["total"], 2)
        self.assertNotIn("prompts", count)
        self.assertNotIn("offset", count)

    def test_json_fields(self) -> None:
        data = self.run_json("prompts", "qoder-cn:a1b2c3d4")
        self.assertEqual(data["ref"], "qoder-cn:a1b2c3d4")
        self.assertEqual(data["session_id"], SESSION_A)
        self.assertEqual(data["cwd"], "/Users/example/project-alpha")
        self.assertFalse(data["archived"])
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["offset"], 0)
        self.assertEqual(data["limit"], 0)
        self.assertEqual(data["order"], "oldest")
        self.assertEqual(data["returned"], 2)
        self.assertFalse(data["has_more"])
        self.assertEqual([item["index"] for item in data["prompts"]], [1, 2])
        self.assertEqual(
            data["prompts"][0]["text"], "Add OAuth token refresh to the CLI"
        )
        self.assertTrue(data["prompts"][0]["timestamp"].endswith("Z"))

    def test_oldest_pagination(self) -> None:
        page = self.run_json(
            "prompts", "qoder-cn:a1b2c3d4", "--limit", "1"
        )
        self.assertEqual([item["index"] for item in page["prompts"]], [1])
        self.assertTrue(page["has_more"])
        self.assertEqual(page["returned"], 1)

        code, out, err = self.run_cli(
            "prompts", "qoder-cn:a1b2c3d4", "--limit", "1"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("next: --offset 1 --limit 1", out)
        self.assertNotIn("Also handle PKCE", out)

        page = self.run_json(
            "prompts",
            "qoder-cn:a1b2c3d4",
            "--offset",
            "1",
            "--limit",
            "1",
        )
        self.assertEqual([item["index"] for item in page["prompts"]], [2])
        self.assertFalse(page["has_more"])

    def test_newest_pagination_keeps_original_indices(self) -> None:
        page = self.run_json(
            "prompts",
            "qoder-cn:a1b2c3d4",
            "--order",
            "newest",
            "--limit",
            "1",
        )
        self.assertEqual([item["index"] for item in page["prompts"]], [2])
        self.assertTrue(page["has_more"])

        page = self.run_json(
            "prompts",
            "qoder-cn:a1b2c3d4",
            "--order",
            "newest",
            "--offset",
            "1",
            "--limit",
            "1",
        )
        self.assertEqual([item["index"] for item in page["prompts"]], [1])
        self.assertFalse(page["has_more"])

        page = self.run_json(
            "prompts", "qoder-cn:a1b2c3d4", "--order", "newest"
        )
        self.assertEqual([item["index"] for item in page["prompts"]], [2, 1])

    def test_offset_past_end(self) -> None:
        page = self.run_json(
            "prompts", "qoder-cn:a1b2c3d4", "--offset", "5", "--limit", "2"
        )
        self.assertEqual(page["total"], 2)
        self.assertEqual(page["prompts"], [])
        self.assertEqual(page["returned"], 0)
        self.assertFalse(page["has_more"])

        code, out, err = self.run_cli(
            "prompts", "qoder-cn:a1b2c3d4", "--offset", "5"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("total: 2, returned: 0", out)
        self.assertIn("no prompts in this range", out)

    def test_chars_cap(self) -> None:
        page = self.run_json(
            "prompts", "qoder-cn:a1b2c3d4", "--limit", "1", "--chars", "12"
        )
        self.assertEqual(len(page["prompts"][0]["text"]), 12)
        self.assertTrue(page["prompts"][0]["text"].endswith("…"))

        page = self.run_json(
            "prompts", "qoder-cn:a1b2c3d4", "--limit", "1", "--chars", "0"
        )
        self.assertEqual(
            page["prompts"][0]["text"], "Add OAuth token refresh to the CLI"
        )

    def test_empty_session(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-empty-") as raw:
            home = _copy_fixture_home(FIXTURE_HOME, Path(raw) / "home")
            path = (
                home
                / "projects"
                / "-Users-example-project-alpha"
                / "e5f6a7b8-5555-4e5f-9a6b-555555555555.jsonl"
            )
            path.write_text(
                json.dumps(
                    {
                        "type": "workspace-directories",
                        "directories": ["/Users/example/project-alpha"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            code, out, err = self.run_cli("prompts", str(path), home=home)
            self.assertEqual(code, 0, err)
            self.assertIn("total: 0, returned: 0", out)
            self.assertIn("no user prompts", out)

            code, out, err = self.run_cli(
                "prompts", str(path), "--count", home=home
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(out.strip(), "0")

    def test_by_path_and_alias(self) -> None:
        path = (
            self.home
            / "projects"
            / "-Users-example-project-alpha"
            / (SESSION_A + ".jsonl")
        )
        code, out, err = self.run_cli("prompts", str(path))
        self.assertEqual(code, 0, err)
        self.assertIn("total: 2", out)

        code, out, err = self.run_cli("prompts", "qcn:a1b2c3d4")
        self.assertEqual(code, 0, err)
        self.assertIn("# qoder-cn:a1b2c3d4 user prompts", out)

        code, out, err = self.run_cli(
            "prompts", "a1b2c3d4", "--harness", "qcn", "--count"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "2")

    def test_cross_store_ref_errors(self) -> None:
        code, out, err = self.run_cli("prompts", "qoder:a1b2c3d4")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

        code, out, err = self.run_cli("prompts", "qoder-cn:c3d4e5f6")
        self.assertEqual(code, 2)
        self.assertIn("no session matched", err)

    def test_unsupported_adapter_errors_cleanly(self) -> None:
        with mock.patch.object(
            QoderCNAdapter, "iter_prompts", side_effect=NotImplementedError
        ):
            code, out, err = self.run_cli("prompts", "qoder-cn:a1b2c3d4")
        self.assertEqual(code, 2)
        self.assertIn("cannot list user prompts", err)
        self.assertIn("qoder-cn", err)

    def test_international_prompts_exclude_meta_and_compaction(self) -> None:
        page = self.run_json("prompts", "qoder:d4e5f6a7")
        self.assertEqual(page["total"], 1)
        self.assertEqual(
            [item["text"] for item in page["prompts"]],
            ["Export invoices as CSV"],
        )
        self.assertNotIn("Expanded skill body", json.dumps(page))


class SafetyTests(FixtureTestCase):
    def test_fixture_data_is_synthetic(self) -> None:
        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        for root in (FIXTURE_HOME, FIXTURE_QODER_HOME, FIXTURE_KIMI_HOME):
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("/Volumes/", text, str(path))
                self.assertNotIn("/home/", text, str(path))
                self.assertNotIn("C:\\Users\\", text, str(path))
                self.assertNotIn("/Users/", text.replace("/Users/example/", ""), str(path))
                self.assertIsNone(email.search(text), str(path))
        for root in (FIXTURE_HOME, FIXTURE_QODER_HOME, FIXTURE_KIMI_HOME):
            for path in root.rglob("*.jsonl"):
                if "transcript" in path.parts:
                    continue
                if root == FIXTURE_KIMI_HOME and path.name in (
                    "wire.jsonl",
                    "session_index.jsonl",
                ):
                    continue
                stem = path.stem
                if stem.startswith("session_"):
                    stem = stem[len("session_") :]
                self.assertTrue(
                    stem.startswith(
                        (
                            "a1b2c3d4-",
                            "b2c3d4e5-",
                            "c3d4e5f6-",
                            "d4e5f6a7-",
                            "e5f6a7b8-",
                            "f6a7b8c9-",
                            "a7b8c9d0-",
                        )
                    ),
                    "unexpected fixture session id: %s" % path.stem,
                )

    def test_fixture_files_are_valid(self) -> None:
        for root in (FIXTURE_HOME, FIXTURE_QODER_HOME, FIXTURE_KIMI_HOME):
            for path in root.rglob("*.jsonl"):
                for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if line.strip():
                        self.assertIsInstance(
                            json.loads(line), dict, "%s:%d" % (path, line_number)
                        )
            for path in root.rglob("*.json"):
                self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)

    def test_commands_do_not_modify_store(self) -> None:
        def snapshot() -> dict:
            files = {}
            for home in (self.home, self.qoder_home, self.kimi_home):
                for path in home.rglob("*"):
                    if path.is_file():
                        files[str(path)] = (path.read_bytes(), path.stat().st_mtime_ns)
            return files

        before = snapshot()
        self.run_cli("search", "--harness", "qcn")
        self.run_cli("latest", "--harness", "qcn")
        self.run_cli("show", "qoder-cn:a1b2c3d4")
        self.run_cli("show", "qoder-cn:b2c3d4e5", "--format", "json")
        self.run_cli("search", "--harness", "qoder")
        self.run_cli("latest", "--harness", "qoder")
        self.run_cli("show", "qoder:c3d4e5f6")
        self.run_cli("show", "qoder:d4e5f6a7", "--format", "json")
        self.run_cli("prompts", "qoder-cn:a1b2c3d4")
        self.run_cli("prompts", "qoder-cn:a1b2c3d4", "--count")
        self.run_cli(
            "prompts", "qoder:d4e5f6a7", "--order", "newest", "--limit", "1"
        )
        self.run_cli("search", "--harness", "kimi-code")
        self.run_cli("latest", "--harness", "kimi-code", "--include-archived")
        self.run_cli("show", "kimi-code:e5f6a7b8")
        self.run_cli("prompts", "kimi-code:a7b8c9d0", "--count")
        self.assertEqual(snapshot(), before)


class SkillPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.lines = self.text.splitlines()

    def test_frontmatter_bounds(self) -> None:
        self.assertTrue(self.text.startswith("---\n"))
        end = self.text.index("\n---", 4)
        self.assertGreater(end, 0)

    def test_name_matches_folder(self) -> None:
        self.assertIn("\nname: find-my-session\n", self.text)
        self.assertEqual(SKILL_DIR.name, "find-my-session")

    def test_description_is_single_line_and_short(self) -> None:
        description_lines = [
            line for line in self.lines if line.startswith("description:")
        ]
        self.assertEqual(len(description_lines), 1)
        description = description_lines[0][len("description:") :].strip()
        self.assertLessEqual(len(description), 1024)
        self.assertGreater(len(description), 80)
        index = self.lines.index(description_lines[0])
        if index + 1 < len(self.lines):
            self.assertFalse(self.lines[index + 1].startswith("  "))

    def test_description_has_bilingual_triggers(self) -> None:
        description = next(
            line for line in self.lines if line.startswith("description:")
        )
        for keyword in ("find", "session", "找", "会话", "接力"):
            self.assertIn(keyword, description)

    def test_body_is_under_500_lines(self) -> None:
        self.assertLess(len(self.lines), 500)

    def test_references_exist(self) -> None:
        self.assertTrue((SKILL_DIR / "references" / "qoder-cn.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "qoder.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "kimi-code.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "zcode.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "codearts-agent.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "workbuddy.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "codex.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "deepseek.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "claude-code.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "cline.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "grok-build.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "antigravity.md").is_file())
        self.assertTrue(
            (SKILL_DIR / "references" / "antigravity-cli.md").is_file()
        )
        self.assertTrue((SKILL_DIR / "references" / "extending.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "contribution.md").is_file())

    def test_no_extraneous_top_level_files(self) -> None:
        allowed = {"SKILL.md", "scripts", "references"}
        actual = {path.name for path in SKILL_DIR.iterdir()}
        self.assertEqual(actual, allowed)

    def test_no_todo_markers(self) -> None:
        for path in SKILL_DIR.rglob("*"):
            if path.is_file() and path.suffix in (".md", ".py") and "__pycache__" not in path.parts:
                self.assertNotIn("TODO:", path.read_text(encoding="utf-8"), str(path))

    def test_skill_documents_prompt_listing(self) -> None:
        self.assertIn("fms prompts", self.text)
        self.assertIn("--count", self.text)
        self.assertIn("--offset", self.text)
        self.assertIn("iter_prompts", self.text)

    def test_skill_documents_maintenance_feedback(self) -> None:
        self.assertIn("## Maintenance feedback", self.text)
        self.assertIn("references/contribution.md", self.text)
        contribution = (SKILL_DIR / "references" / "contribution.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## Privacy gate", contribution)
        self.assertIn("## Ask first", contribution)
        self.assertIn("[bug] ", contribution)
        self.assertIn("[harness] ", contribution)
        self.assertIn(
            "github.com/SomeNoneAI/find-my-session/issues", contribution
        )

    def test_entrypoint_is_executable(self) -> None:
        if os.name == "nt":
            self.skipTest("executable bit is not meaningful on Windows")
        self.assertTrue(os.access(FMS, os.X_OK))


class ProjectGuidanceTests(unittest.TestCase):
    def test_agents_md_points_to_add_harness_skill(self) -> None:
        text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(".agents/skills/add-harness/SKILL.md", text)
        self.assertIn("--include-archived", text)
        self.assertIn("iter_prompts", text)
        self.assertLess(len(text.splitlines()), 80)

    def test_add_harness_skill_is_valid(self) -> None:
        skill_dir = REPO_ROOT / ".agents" / "skills" / "add-harness"
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("\nname: add-harness\n", text)
        self.assertEqual(skill_dir.name, "add-harness")
        description = next(
            line for line in text.splitlines() if line.startswith("description:")
        )
        self.assertLessEqual(len(description[len("description:") :].strip()), 1024)
        self.assertLess(len(text.splitlines()), 500)
        self.assertIn("archive", text)
        self.assertIn("Capability checklist", text)
        self.assertIn("iter_prompts", text)
        self.assertIn("--count", text)
        self.assertNotIn("TODO:", text)

    def test_add_harness_skill_has_no_extra_files(self) -> None:
        skill_dir = REPO_ROOT / ".agents" / "skills" / "add-harness"
        self.assertEqual({path.name for path in skill_dir.iterdir()}, {"SKILL.md"})
