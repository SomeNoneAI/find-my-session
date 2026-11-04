from __future__ import annotations

import json
import unittest


from cli_support import FixtureTestCase  # noqa: E402


# Required keys per docs/json-output.md. New fields may be added freely;
# removing or renaming one of these breaks the contract and must fail here.
HARNESS_KEYS = {"name", "status", "variants", "store", "aliases"}

SUMMARY_KEYS = {
    "ref",
    "harness",
    "session_id",
    "path",
    "cwd",
    "title",
    "first_prompt",
    "last_prompt",
    "started",
    "updated",
    "branch",
    "model",
    "entrypoint",
    "version",
    "size_bytes",
    "variants",
    "archived",
}

SHOW_EXTRA_KEYS = {
    "compact_summary",
    "todos",
    "turn_count",
    "exchanges",
    "edited_files",
    "tool_counts",
    "recent_tools",
}

EXCHANGE_KEYS = {"user", "timestamp", "assistant", "tools"}
TOOL_KEYS = {"name", "detail", "timestamp"}
EDITED_FILE_KEYS = {"path", "count"}
TODO_KEYS = {"id", "subject", "description", "status"}

PROMPT_PAGE_KEYS = {
    "ref",
    "harness",
    "session_id",
    "path",
    "cwd",
    "archived",
    "total",
}
PROMPT_PAGE_FULL_KEYS = PROMPT_PAGE_KEYS | {
    "offset",
    "limit",
    "order",
    "returned",
    "has_more",
    "prompts",
}
PROMPT_KEYS = {"index", "timestamp", "text"}

STATS_KEYS = {
    "harness",
    "sessions",
    "sessions_with_usage",
    "tokens_input",
    "tokens_output",
    "tokens_cache_read",
    "cost_usd",
}


class JsonContractTests(FixtureTestCase):
    def test_harnesses_shape(self) -> None:
        rows = self.run_json("harnesses")
        self.assertGreater(len(rows), 0)
        for row in rows:
            with self.subTest(harness=row.get("name")):
                self.assertLessEqual(HARNESS_KEYS, set(row))

    def test_search_shape(self) -> None:
        sessions = self.run_json("search", "--harness", "qcn", "--limit", "0")
        self.assertGreater(len(sessions), 0)
        for session in sessions:
            with self.subTest(ref=session.get("ref")):
                self.assertLessEqual(SUMMARY_KEYS, set(session))
                self.assertIsInstance(session["archived"], bool)
                self.assertTrue(session["updated"].endswith("Z"))

    def test_latest_shape(self) -> None:
        sessions = self.run_json("latest", "--harness", "qcn", "--json")
        self.assertEqual(len(sessions), 1)
        self.assertLessEqual(SUMMARY_KEYS, set(sessions[0]))

    def test_show_shape(self) -> None:
        code, out, err = self.run_cli(
            "show", "qoder-cn:a1b2c3d4", "--format", "json"
        )
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertLessEqual(SUMMARY_KEYS | SHOW_EXTRA_KEYS, set(data))
        self.assertIsInstance(data["exchanges"], list)
        self.assertIsInstance(data["turn_count"], int)
        for exchange in data["exchanges"]:
            with self.subTest(exchange=exchange.get("user", "")[:20]):
                self.assertLessEqual(EXCHANGE_KEYS, set(exchange))
                self.assertIsInstance(exchange["assistant"], list)
                for tool in exchange["tools"]:
                    self.assertLessEqual(TOOL_KEYS, set(tool))
        for edited in data["edited_files"]:
            self.assertLessEqual(EDITED_FILE_KEYS, set(edited))
        for todo in data["todos"]:
            self.assertLessEqual(TODO_KEYS, set(todo))

    def test_prompts_shape(self) -> None:
        data = self.run_json("prompts", "qoder-cn:a1b2c3d4", "--limit", "2")
        self.assertLessEqual(PROMPT_PAGE_FULL_KEYS, set(data))
        self.assertEqual(data["returned"], len(data["prompts"]))
        for prompt in data["prompts"]:
            self.assertLessEqual(PROMPT_KEYS, set(prompt))

    def test_prompts_count_shape(self) -> None:
        data = self.run_json("prompts", "qoder-cn:a1b2c3d4", "--count")
        self.assertLessEqual(PROMPT_PAGE_KEYS, set(data))
        self.assertIsInstance(data["total"], int)

    def test_stats_shape(self) -> None:
        rows = self.run_json("stats")
        self.assertGreater(len(rows), 0)
        for row in rows:
            with self.subTest(harness=row.get("harness")):
                self.assertLessEqual(STATS_KEYS, set(row))


if __name__ == "__main__":
    unittest.main()
