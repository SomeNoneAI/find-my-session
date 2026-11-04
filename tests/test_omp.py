from __future__ import annotations

import hashlib
from pathlib import Path

from cli_support import FixtureTestCase
from omp_fixture import (
    COMPACT_SUMMARY,
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
    SUBAGENT_PROMPT,
    SUBAGENT_STEM,
    TITLE_MANUAL,
    TODO_SUBJECT,
    TOOL_OUTPUT_NEEDLE,
    VERSION_MAIN,
    EDIT_PATH,
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


class OmpTests(FixtureTestCase):
    def show_json(self, *args: str, **kwargs):
        code, out, err = self.run_cli("show", *args, "--format", "json", **kwargs)
        self.assertEqual(code, 0, err)
        import json

        return json.loads(out)

    def main_path(self) -> Path:
        return next(self.omp_home.glob("sessions/*/%s.jsonl" % MAIN_STEM))

    def subagent_path(self) -> Path:
        return self.main_path().parent.parent / MAIN_STEM / "reviewer.jsonl"

    def test_harness_listing(self) -> None:
        rows = self.run_json("harnesses")
        row = next(item for item in rows if item["name"] == "omp")
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["variants"], "cli")
        self.assertEqual(row["aliases"], "omp, oh-my-pi")
        self.assertEqual(row["store"], "~/.omp/agent/sessions")

    def test_lists_sessions_newest_first(self) -> None:
        sessions = self.run_json("search", "--harness", "omp", "--limit", "0")
        self.assertEqual(
            [item["ref"] for item in sessions], ["omp:a1b2c3d4", "omp:b2c3d4e5"]
        )
        self.assertEqual(sessions[0]["cwd"], PROJECT_MAIN)
        self.assertEqual(sessions[1]["cwd"], PROJECT_PLAIN)
        self.assertEqual(sessions[0]["title"], TITLE_MANUAL)
        self.assertEqual(sessions[0]["model"], MODEL_MAIN)
        self.assertEqual(sessions[0]["version"], VERSION_MAIN)

    def test_subagent_and_lock_are_not_sessions(self) -> None:
        sessions = self.run_json("search", "--harness", "omp", "--limit", "0")
        paths = {item["path"] for item in sessions}
        self.assertNotIn(str(self.subagent_path()), paths)

        rows = self.run_json("search", "--harness", "omp", SUBAGENT_PROMPT)
        self.assertEqual(rows, [])
        rows = self.run_json(
            "search", "--harness", "omp", "--deep", SUBAGENT_PROMPT
        )
        self.assertEqual(rows, [])

        code, out, err = self.run_cli("show", str(self.subagent_path()))
        self.assertNotEqual(code, 0)

    def test_keyword_id_cwd_since_limit(self) -> None:
        rows = self.run_json("search", "--harness", "omp", "title fallback")
        self.assertEqual([item["ref"] for item in rows], ["omp:a1b2c3d4"])

        rows = self.run_json("search", "--harness", "omp", "b2c3d4e5")
        self.assertEqual([item["ref"] for item in rows], ["omp:b2c3d4e5"])

        rows = self.run_json("search", "--harness", "omp", "--cwd", PROJECT_PLAIN)
        self.assertEqual([item["ref"] for item in rows], ["omp:b2c3d4e5"])

        rows = self.run_json("search", "--harness", "omp", "--since", "2026-10-25")
        self.assertEqual([item["ref"] for item in rows], ["omp:a1b2c3d4"])

        rows = self.run_json("search", "--harness", "omp", "--limit", "1")
        self.assertEqual(len(rows), 1)

        self.assertEqual(self.run_json("search", "--harness", "omp", "absent"), [])

    def test_aliases(self) -> None:
        for alias in ("omp", "oh-my-pi"):
            rows = self.run_json("search", "--harness", alias, "title fallback")
            self.assertEqual([item["ref"] for item in rows], ["omp:a1b2c3d4"])

    def test_deep_search(self) -> None:
        rows = self.run_json("search", "--harness", "omp", TOOL_OUTPUT_NEEDLE)
        self.assertEqual(rows, [])
        rows = self.run_json(
            "search", "--harness", "omp", "--deep", TOOL_OUTPUT_NEEDLE
        )
        self.assertEqual([item["ref"] for item in rows], ["omp:a1b2c3d4"])

    def test_latest(self) -> None:
        rows = self.run_json("latest", "--harness", "omp")
        self.assertEqual(rows[0]["ref"], "omp:a1b2c3d4")
        rows = self.run_json("latest", "--harness", "omp", "wording")
        self.assertEqual([item["ref"] for item in rows], ["omp:b2c3d4e5"])

    def test_show_markdown_and_json(self) -> None:
        code, out, err = self.run_cli("show", "omp:a1b2c3d4", "--messages", "5")
        self.assertEqual(code, 0, err)
        self.assertIn("omp:a1b2c3d4", out)
        self.assertIn(TODO_SUBJECT, out)
        self.assertIn(EDIT_PATH, out)

        data = self.show_json("omp:a1b2c3d4", "--messages", "5")
        self.assertEqual(data["title"], TITLE_MANUAL)
        self.assertEqual(data["compact_summary"], COMPACT_SUMMARY)
        self.assertEqual(data["model"], MODEL_MAIN)
        self.assertEqual(data["turn_count"], 3)
        self.assertEqual(data["edited_files"][0]["path"], EDIT_PATH)
        self.assertEqual(
            [todo["subject"] for todo in data["todos"]],
            [TODO_SUBJECT, "Run the suite"],
        )
        self.assertIn("todo", data["tool_counts"])
        assistant = "\n".join(
            text for exchange in data["exchanges"] for text in exchange["assistant"]
        )
        self.assertIn("provider rate limit exceeded", assistant)

    def test_prompt_listing(self) -> None:
        data = self.run_json("prompts", "omp:a1b2c3d4", "--limit", "0")
        self.assertEqual(data["total"], 3)
        self.assertEqual([p["text"] for p in data["prompts"]], PROMPTS_MAIN)
        self.assertFalse(any(INJECTED_NEEDLE in p["text"] for p in data["prompts"]))

        data = self.run_json("prompts", "omp:b2c3d4e5", "--limit", "0")
        self.assertEqual([p["text"] for p in data["prompts"]], PROMPTS_PLAIN)

        data = self.run_json(
            "prompts", "omp:a1b2c3d4", "--order", "newest", "--limit", "2"
        )
        self.assertEqual(
            [p["text"] for p in data["prompts"]],
            list(reversed(PROMPTS_MAIN[-2:])),
        )

        code, out, err = self.run_cli(
            "prompts", "omp:a1b2c3d4", "--offset", "9", "--limit", "2"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no prompts in this range", out)

        code, out, err = self.run_cli(
            "prompts", "omp:a1b2c3d4", "--limit", "1", "--chars", "10"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("…", out)

    def test_ref_resolution_and_isolation(self) -> None:
        code, out, err = self.run_cli("show", "omp:a1b2c3d4")
        self.assertEqual(code, 0, err)

        code, out, err = self.run_cli("show", "a1b2c3d4", "--harness", "omp")
        self.assertEqual(code, 0, err)

        code, out, err = self.run_cli("show", str(self.main_path()))
        self.assertEqual(code, 0, err)

        code, out, err = self.run_cli("show", "omp:ffffffff")
        self.assertNotEqual(code, 0)

        code, out, err = self.run_cli("show", "a1b2c3d4")
        self.assertNotEqual(code, 0)
        self.assertIn("ambiguous", err)

    def test_usage_and_resume(self) -> None:
        rows = self.run_json("stats", "--harness", "omp")
        self.assertEqual(rows[0]["sessions"], 2)
        self.assertEqual(rows[0]["tokens_input"], 240)
        self.assertEqual(rows[0]["tokens_output"], 50)

        code, out, err = self.run_cli("resume", "omp:a1b2c3d4")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "omp --resume %s" % SESSION_MAIN)

    def test_doctor_and_empty_home(self) -> None:
        rows = self.run_json("doctor", "--harness", "omp")
        store = rows["stores"][0]
        self.assertEqual(store["candidates"], 2)
        self.assertEqual(store["readable"], 2)
        self.assertEqual(store["skipped"], 0)

        rows = self.run_json("doctor", "--harness", "omp", omp_home=self.empty_omp_home)
        self.assertEqual(rows["stores"][0]["candidates"], 0)
        self.assertEqual(rows["stores"][0]["readable"], 0)

        code, out, err = self.run_cli(
            "search", "--harness", "omp", omp_home=self.empty_omp_home
        )
        self.assertEqual(code, 0, err)
        self.assertIn("no sessions matched", out)

    def test_read_only(self) -> None:
        before = _snapshot(self.omp_home)
        self.run_cli("search", "--harness", "omp", "--limit", "0")
        self.run_cli("search", "--harness", "omp", "--deep", TOOL_OUTPUT_NEEDLE)
        self.run_cli("show", "omp:a1b2c3d4", "--messages", "5")
        self.run_cli("prompts", "omp:a1b2c3d4", "--limit", "0")
        self.run_json("doctor", "--harness", "omp")
        self.assertEqual(_snapshot(self.omp_home), before)
