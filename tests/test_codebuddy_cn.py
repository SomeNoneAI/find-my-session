from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cli_support import FixtureTestCase
from codebuddy_cn_fixture import (
    PROJECT_ALPHA,
    PROMPTS_MAIN,
    PROMPT_IMAGE,
    PROMPT_PLAIN,
    SESSION_ARCHIVED,
    SESSION_MAIN,
    SESSION_NO_QUEUE,
    TITLE_MAIN,
)


def _snapshot(root: Path):
    files = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        files[str(path)] = (
            stat.st_size,
            stat.st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    return files


class CodeBuddyCNTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli("show", *args, "--format", "json", **kwargs)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_harness_listing(self) -> None:
        rows = self.run_json("harnesses")
        row = next(item for item in rows if item["name"] == "codebuddy-cn")
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["variants"], "desktop")
        self.assertEqual(
            row["aliases"], "codebuddy-cn, codebuddycn, cb-cn"
        )
        self.assertIn("codebuddy-sessions.vscdb", row["store"])
        planned = {item["name"] for item in rows if item["status"] == "planned"}
        self.assertNotIn("codebuddy-cn", planned)

    def test_lists_sessions_newest_first(self) -> None:
        code, out, err = self.run_cli(
            "search", "--harness", "codebuddy-cn", "--limit", "0"
        )
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()[1:]
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("codebuddy-cn:c0de9004"))
        self.assertTrue(lines[1].startswith("codebuddy-cn:c0de9003"))
        self.assertTrue(lines[2].startswith("codebuddy-cn:c0de9002"))
        self.assertTrue(lines[3].startswith("codebuddy-cn:c0de9001"))

    def test_keyword_and_title_fallback(self) -> None:
        sessions = self.run_json(
            "search", "--harness", "codebuddy-cn", "handoff"
        )
        self.assertEqual(
            [s["ref"] for s in sessions], ["codebuddy-cn:c0de9001"]
        )
        self.assertEqual(sessions[0]["title"], TITLE_MAIN)

        # No stored title: falls back to the latest meaningful prompt.
        sessions = self.run_json(
            "search", "--harness", "codebuddy-cn", "migration"
        )
        self.assertEqual(
            [s["ref"] for s in sessions], ["codebuddy-cn:c0de9002"]
        )
        self.assertEqual(sessions[0]["title"], PROMPT_PLAIN)

        sessions = self.run_json(
            "search", "--harness", "codebuddy-cn", "c0de9002"
        )
        self.assertEqual(
            [s["ref"] for s in sessions], ["codebuddy-cn:c0de9002"]
        )

        code, out, err = self.run_cli(
            "search", "--harness", "codebuddy-cn", "no-such-topic"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_latest_cwd_since_limit(self) -> None:
        sessions = self.run_json("latest", "--harness", "codebuddy-cn")
        self.assertEqual(
            [s["ref"] for s in sessions], ["codebuddy-cn:c0de9004"]
        )

        sessions = self.run_json(
            "latest", "--harness", "codebuddy-cn", "handoff"
        )
        self.assertEqual(
            [s["ref"] for s in sessions], ["codebuddy-cn:c0de9001"]
        )
        self.assertEqual(sessions[0]["first_prompt"], PROMPTS_MAIN[0])

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "codebuddy-cn",
            "--cwd",
            PROJECT_ALPHA,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codebuddy-cn:c0de9001", out)
        self.assertNotIn("c0de9002", out)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "codebuddy-cn",
            "--since",
            "2026-10-23",
            "--limit",
            "0",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codebuddy-cn:c0de9004", out)
        self.assertNotIn("c0de9001", out)

    def test_deep_search(self) -> None:
        sessions = self.run_json(
            "search",
            "--harness",
            "codebuddy-cn",
            "--deep",
            "codebuddy-main-needle",
        )
        self.assertEqual(
            [s["ref"] for s in sessions], ["codebuddy-cn:c0de9001"]
        )

    def test_archived_sessions(self) -> None:
        # Archived sessions hide by default.
        code, out, err = self.run_cli(
            "search", "--harness", "codebuddy-cn", "--limit", "0"
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn("c0de9005", out)

        # --include-archived brings them back with the archived mark.
        sessions = self.run_json(
            "search",
            "--harness",
            "codebuddy-cn",
            "--include-archived",
            "--limit",
            "0",
        )
        archived = [s for s in sessions if s["ref"] == "codebuddy-cn:c0de9005"]
        self.assertEqual(len(archived), 1)
        self.assertTrue(archived[0]["archived"])
        self.assertEqual(len(sessions), 5)

        # --deep does not read archived transcripts by default ...
        sessions = self.run_json(
            "search",
            "--harness",
            "codebuddy-cn",
            "--deep",
            "codebuddy-archived-needle",
        )
        self.assertEqual(sessions, [])

        # ... but finds them when archived sessions are included.
        sessions = self.run_json(
            "search",
            "--harness",
            "codebuddy-cn",
            "--deep",
            "codebuddy-archived-needle",
            "--include-archived",
        )
        self.assertEqual(
            [s["ref"] for s in sessions], ["codebuddy-cn:c0de9005"]
        )

        # Explicit show and prompts still open an archived session.
        detail = self.show_json("codebuddy-cn:c0de9005")
        self.assertTrue(detail["archived"])
        self.assertEqual(detail["turn_count"], 1)

        code, out, err = self.run_cli(
            "prompts", "codebuddy-cn:c0de9005", "--count"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "1")
    def test_show_markdown_and_json(self) -> None:
        code, out, err = self.run_cli("show", "codebuddy-cn:c0de9001")
        self.assertEqual(code, 0, err)
        self.assertIn("# codebuddy-cn:c0de9001", out)
        self.assertIn(PROMPTS_MAIN[0], out)
        self.assertIn("Add prompt paging", out)
        self.assertIn("handoff.ts", out)

        detail = self.show_json("codebuddy-cn:c0de9001")
        self.assertEqual(detail["session_id"], SESSION_MAIN)
        self.assertEqual(detail["title"], TITLE_MAIN)
        self.assertEqual(detail["model"], "hy4-synthetic")
        self.assertEqual(detail["turn_count"], 4)
        contents = [t["subject"] for t in detail["todos"]]
        self.assertIn("Add prompt paging", contents)

        # Session without a message queue still opens from index metadata.
        detail = self.show_json("codebuddy-cn:c0de9003")
        self.assertEqual(detail["session_id"], SESSION_NO_QUEUE)
        self.assertEqual(
            detail["title"], "Session without a message queue"
        )
        self.assertEqual(detail["turn_count"], 0)

    def test_prompts_paging(self) -> None:
        code, out, err = self.run_cli(
            "prompts", "codebuddy-cn:c0de9001", "--count"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "4")

        code, out, err = self.run_cli(
            "prompts", "codebuddy-cn:c0de9001", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertIn(PROMPTS_MAIN[0], out)
        self.assertIn(PROMPTS_MAIN[1], out)
        self.assertNotIn(PROMPTS_MAIN[2], out)

        code, out, err = self.run_cli(
            "prompts",
            "codebuddy-cn:c0de9001",
            "--limit",
            "2",
            "--offset",
            "2",
        )
        self.assertEqual(code, 0, err)
        self.assertIn(PROMPTS_MAIN[2], out)
        self.assertIn("Check the preview layout.", out)

        # System-reminder wrapper is stripped.
        self.assertNotIn("stale context", out)

        # Assistant items never become prompts; image block is dropped.
        code, out, err = self.run_cli(
            "prompts", "codebuddy-cn:c0de9004", "--limit", "0"
        )
        self.assertEqual(code, 0, err)
        self.assertIn(PROMPT_IMAGE, out)
        self.assertNotIn("synthetic reply", out)

        # Offset past the end.
        code, out, err = self.run_cli(
            "prompts", "codebuddy-cn:c0de9001", "--offset", "99"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

    def test_ref_resolution(self) -> None:
        sessions = self.run_json(
            "search", "--harness", "codebuddy-cn", "c0de9001"
        )
        self.assertEqual(len(sessions), 1)

        code, out, err = self.run_cli("show", "codebuddy-cn:c0de9001")
        self.assertEqual(code, 0, err)

        # Bare prefix resolves within the harness.
        code, out, err = self.run_cli(
            "show", "c0de9001", "--harness", "codebuddy-cn"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("codebuddy-cn:c0de9001", out)

        # Virtual source path opens the session.
        virtual = "%s#%s" % (
            self.codebuddy_cn_home / "codebuddy-sessions.vscdb",
            SESSION_MAIN,
        )
        code, out, err = self.run_cli("show", virtual)
        self.assertEqual(code, 0, err)
        self.assertIn("codebuddy-cn:c0de9001", out)

        code, out, err = self.run_cli("show", "codebuddy-cn:ffffffff")
        self.assertNotEqual(code, 0)

    def test_doctor_and_empty_home(self) -> None:
        rows = self.run_json("doctor", "--harness", "codebuddy-cn")
        store = rows["stores"][0]
        self.assertEqual(store["candidates"], 5)
        self.assertEqual(store["readable"], 5)
        self.assertEqual(store["skipped"], 0)

        rows = self.run_json(
            "doctor",
            "--harness",
            "codebuddy-cn",
            codebuddy_cn_home=self.empty_codebuddy_cn_home,
        )
        self.assertEqual(rows["stores"][0]["candidates"], 0)

        code, out, err = self.run_cli(
            "search",
            "--harness",
            "codebuddy-cn",
            codebuddy_cn_home=self.empty_codebuddy_cn_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_privacy_scan(self) -> None:
        for path in sorted(self.codebuddy_cn_home.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix in (".vscdb", ".sqlite", ".db"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("calvinchen", text)
            self.assertNotIn("@", text)

    def test_read_only(self) -> None:
        before = _snapshot(self.codebuddy_cn_home)
        self.run_cli("search", "--harness", "codebuddy-cn", "--limit", "0")
        self.run_cli(
            "search", "--harness", "codebuddy-cn", "--deep", "handoff"
        )
        self.run_cli("show", "codebuddy-cn:c0de9001", "--messages", "5")
        self.run_cli("prompts", "codebuddy-cn:c0de9001", "--limit", "0")
        self.run_json("doctor", "--harness", "codebuddy-cn")
        self.assertEqual(_snapshot(self.codebuddy_cn_home), before)
        leftovers = list(self.codebuddy_cn_home.rglob("*-wal")) + list(
            self.codebuddy_cn_home.rglob("*-shm")
        )
        self.assertEqual(leftovers, [])
