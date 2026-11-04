from __future__ import annotations

import hashlib
import os
from pathlib import Path
from unittest import mock

from cli_support import FixtureTestCase
from pi_fixture import (
    COMPACT_SUMMARY,
    DEEP_ONLY_NEEDLE,
    EDIT_PATH,
    INJECTED_NEEDLE,
    MAIN_STEM,
    MODEL_MAIN,
    PLAIN_STEM,
    PROJECT_MAIN,
    PROJECT_PLAIN,
    PROMPTS_MAIN,
    PROMPTS_PLAIN,
    SESSION_MAIN,
    SESSION_PLAIN,
    TITLE_MAIN,
    TODO_SUBJECT,
    TOOL_OUTPUT_NEEDLE,
    VERSION_MAIN,
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


class PiTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli("show", *args, "--format", "json", **kwargs)
        self.assertEqual(code, 0, err)
        import json

        return json.loads(out)

    def main_path(self) -> Path:
        return next(self.pi_home.glob("sessions/*/%s.jsonl" % MAIN_STEM))

    def plain_path(self) -> Path:
        return next(self.pi_home.glob("sessions/*/%s.jsonl" % PLAIN_STEM))

    def test_harness_listing(self) -> None:
        rows = self.run_json("harnesses")
        row = next(item for item in rows if item["name"] == "pi")
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["variants"], "cli")
        self.assertEqual(row["aliases"], "pi, pi-cli")
        self.assertEqual(row["store"], "~/.pi/agent/sessions")

    def test_lists_sessions_newest_first(self) -> None:
        sessions = self.run_json("search", "--harness", "pi", "--limit", "0")
        self.assertEqual([item["ref"] for item in sessions], ["pi:a1b2c3d4", "pi:b2c3d4e5"])
        self.assertEqual(sessions[0]["cwd"], PROJECT_MAIN)
        self.assertEqual(sessions[1]["cwd"], PROJECT_PLAIN)
        self.assertEqual(sessions[0]["title"], TITLE_MAIN)
        self.assertEqual(sessions[0]["model"], MODEL_MAIN)
        self.assertEqual(sessions[0]["version"], VERSION_MAIN)
        self.assertFalse(sessions[0]["archived"])

    def test_keyword_id_cwd_since_limit(self) -> None:
        rows = self.run_json("search", "--harness", "pi", "paging")
        self.assertEqual([item["ref"] for item in rows], ["pi:a1b2c3d4"])

        rows = self.run_json("search", "--harness", "pi", "b2c3d4e5")
        self.assertEqual([item["ref"] for item in rows], ["pi:b2c3d4e5"])

        rows = self.run_json("search", "--harness", "pi", "--cwd", PROJECT_PLAIN)
        self.assertEqual([item["ref"] for item in rows], ["pi:b2c3d4e5"])

        rows = self.run_json("search", "--harness", "pi", "--since", "2026-10-25")
        self.assertEqual([item["ref"] for item in rows], ["pi:a1b2c3d4"])

        rows = self.run_json("search", "--harness", "pi", "--limit", "1")
        self.assertEqual(len(rows), 1)

        rows = self.run_json("search", "--harness", "pi", "no-such-text")
        self.assertEqual(rows, [])

    def test_aliases(self) -> None:
        for alias in ("pi", "pi-cli"):
            rows = self.run_json("search", "--harness", alias, "paging")
            self.assertEqual([item["ref"] for item in rows], ["pi:a1b2c3d4"])

    def test_deep_search_stays_in_session(self) -> None:
        rows = self.run_json("search", "--harness", "pi", TOOL_OUTPUT_NEEDLE)
        self.assertEqual(rows, [])
        rows = self.run_json(
            "search", "--harness", "pi", "--deep", TOOL_OUTPUT_NEEDLE
        )
        self.assertEqual([item["ref"] for item in rows], ["pi:a1b2c3d4"])
        rows = self.run_json(
            "search", "--harness", "pi", "--deep", DEEP_ONLY_NEEDLE
        )
        self.assertEqual(rows, [])

    def test_latest(self) -> None:
        rows = self.run_json("latest", "--harness", "pi")
        self.assertEqual(rows[0]["ref"], "pi:a1b2c3d4")
        rows = self.run_json("latest", "--harness", "pi", "opening")
        self.assertEqual([item["ref"] for item in rows], ["pi:b2c3d4e5"])

    def test_show_markdown_and_json(self) -> None:
        code, out, err = self.run_cli("show", "pi:a1b2c3d4", "--messages", "5")
        self.assertEqual(code, 0, err)
        self.assertIn("pi:a1b2c3d4", out)
        self.assertIn(TODO_SUBJECT, out)
        self.assertIn(EDIT_PATH, out)

        data = self.show_json("pi:a1b2c3d4", "--messages", "5")
        self.assertEqual(data["title"], TITLE_MAIN)
        self.assertEqual(data["compact_summary"], COMPACT_SUMMARY)
        self.assertEqual(data["turn_count"], 3)
        self.assertEqual(
            [todo["subject"] for todo in data["todos"]],
            [TODO_SUBJECT, "Run the suite"],
        )
        self.assertEqual(data["edited_files"][0]["path"], EDIT_PATH)
        self.assertIn("bash", data["tool_counts"])
        assistant = "\n".join(
            text for exchange in data["exchanges"] for text in exchange["assistant"]
        )
        self.assertIn("provider rate limit exceeded", assistant)
        self.assertNotIn(INJECTED_NEEDLE, [item["user"] for item in data["exchanges"]])

    def test_prompt_listing(self) -> None:
        data = self.run_json("prompts", "pi:a1b2c3d4", "--limit", "0")
        self.assertEqual(data["total"], 3)
        self.assertEqual([p["text"] for p in data["prompts"]], PROMPTS_MAIN)

        data = self.run_json("prompts", "pi:b2c3d4e5", "--limit", "0")
        self.assertEqual([p["text"] for p in data["prompts"]], PROMPTS_PLAIN)

        data = self.run_json(
            "prompts", "pi:a1b2c3d4", "--order", "newest", "--limit", "2"
        )
        self.assertEqual(
            [p["text"] for p in data["prompts"]],
            list(reversed(PROMPTS_MAIN[-2:])),
        )

        code, out, err = self.run_cli(
            "prompts", "pi:a1b2c3d4", "--offset", "9", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts", "pi:a1b2c3d4", "--limit", "1", "--chars", "10"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("…", out)

    def test_prompt_excludes_non_human_records(self) -> None:
        data = self.run_json("prompts", "pi:a1b2c3d4", "--limit", "0")
        texts = [item["text"] for item in data["prompts"]]
        self.assertEqual(texts, PROMPTS_MAIN)
        self.assertFalse(any(INJECTED_NEEDLE in text for text in texts))
        self.assertFalse(any(TOOL_OUTPUT_NEEDLE in text for text in texts))
        self.assertFalse(any(COMPACT_SUMMARY in text for text in texts))

    def test_ref_resolution_and_isolation(self) -> None:
        code, out, err = self.run_cli("show", "pi:a1b2c3d4")
        self.assertEqual(code, 0, err)

        code, out, err = self.run_cli("show", "a1b2c3d4", "--harness", "pi")
        self.assertEqual(code, 0, err)

        code, out, err = self.run_cli("show", str(self.main_path()))
        self.assertEqual(code, 0, err)

        code, out, err = self.run_cli("show", "pi:ffffffff")
        self.assertNotEqual(code, 0)

    def test_usage_and_resume(self) -> None:
        rows = self.run_json("stats", "--harness", "pi")
        self.assertEqual(rows[0]["sessions"], 2)
        self.assertEqual(rows[0]["tokens_input"], 200)
        self.assertEqual(rows[0]["tokens_output"], 60)

        code, out, err = self.run_cli("resume", "pi:a1b2c3d4")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "pi --session %s" % SESSION_MAIN)

    def test_session_dir_override(self) -> None:
        adapter = self._adapter()
        env = {
            "FMS_PI_HOME": str(self.pi_home),
            "PI_CODING_AGENT_SESSION_DIR": str(self.pi_home / "sessions"),
        }
        with mock.patch.dict(os.environ, env):
            self.assertEqual(adapter._sessions_root(), self.pi_home / "sessions")
        with mock.patch.dict(
            os.environ,
            {"FMS_PI_HOME": str(self.pi_home), "PI_CODING_AGENT_SESSION_DIR": ""},
        ):
            self.assertEqual(adapter._sessions_root(), self.pi_home / "sessions")

    def test_doctor_and_empty_home(self) -> None:
        rows = self.run_json("doctor", "--harness", "pi")
        store = rows["stores"][0]
        self.assertEqual(store["candidates"], 2)
        self.assertEqual(store["readable"], 2)
        self.assertEqual(store["skipped"], 0)

        code, out, err = self.run_cli("search", "--harness", "pi", pi_home=self.empty_pi_home)
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

        rows = self.run_json("doctor", "--harness", "pi", pi_home=self.empty_pi_home)
        self.assertEqual(rows["stores"][0]["candidates"], 0)
        self.assertEqual(rows["stores"][0]["readable"], 0)

    def test_read_only(self) -> None:
        before = _snapshot(self.pi_home)
        self.run_cli("search", "--harness", "pi", "--limit", "0")
        self.run_cli("search", "--harness", "pi", "--deep", TOOL_OUTPUT_NEEDLE)
        self.run_cli("show", "pi:a1b2c3d4", "--messages", "5")
        self.run_cli("prompts", "pi:a1b2c3d4", "--limit", "0")
        self.run_json("doctor", "--harness", "pi")
        self.assertEqual(_snapshot(self.pi_home), before)

    def _adapter(self):
        from fms_lib.harnesses.pi import PiAdapter

        return PiAdapter()
