from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "core"))

from fms_lib.harnesses.common import (  # noqa: E402
    GENERIC_PROMPTS,
    choose_title,
    file_path,
    is_generic,
    tool_detail,
    tool_detail_for,
)


class GenericPromptTests(unittest.TestCase):
    def test_common_fillers_are_generic(self) -> None:
        for value in ("", "?", "？", "123", "ok", "YES", " go   on ", "继续", "好的"):
            self.assertTrue(is_generic(value), value)

    def test_real_requests_are_not_generic(self) -> None:
        for value in ("fix the parser", "继续实现 MiniMax", "hello", "hi"):
            self.assertFalse(is_generic(value), value)

    def test_callers_can_extend_the_set(self) -> None:
        extended = GENERIC_PROMPTS | {"hello", "hi", "你好"}
        self.assertTrue(is_generic("hello", extended))
        self.assertFalse(is_generic("hello"))


class TitleTests(unittest.TestCase):
    def test_latest_specific_prompt_wins(self) -> None:
        self.assertEqual(
            choose_title("initial request", "follow-up request"),
            "follow-up request",
        )

    def test_generic_latest_falls_back_to_the_first_prompt(self) -> None:
        self.assertEqual(choose_title("build the panel", "continue"), "build the panel")

    def test_all_generic_keeps_the_prompt(self) -> None:
        self.assertEqual(choose_title("?, continue", "ok"), "?, continue")

    def test_titles_are_single_line_and_bounded(self) -> None:
        title = choose_title("x" * 400, "")
        self.assertEqual(len(title), 100)
        self.assertEqual(choose_title("a\nb", ""), "a b")


class FilePathTests(unittest.TestCase):
    def test_keys_are_tried_in_order(self) -> None:
        arguments = {"path": "/tmp/second", "file_path": "/tmp/first"}
        self.assertEqual(file_path(arguments, "/work"), "/tmp/first")
        self.assertEqual(file_path(arguments, "/work", ("path",)), "/tmp/second")

    def test_relative_path_is_joined_to_cwd(self) -> None:
        self.assertEqual(
            file_path({"path": "src/app.py"}, "/work/project"),
            "/work/project/src/app.py",
        )

    def test_missing_or_non_string_values_are_ignored(self) -> None:
        self.assertEqual(file_path({"path": None}, "/work"), "")
        self.assertEqual(file_path({"path": 3}, "/work"), "")
        self.assertEqual(file_path(None, "/work"), "")

    def test_home_expansion(self) -> None:
        expanded = os.path.expanduser("~/notes.md")
        self.assertEqual(file_path({"path": "~/notes.md"}, ""), expanded)


class ToolDetailTests(unittest.TestCase):
    def test_preferred_keys_win(self) -> None:
        arguments = {"command": "pytest -q", "path": "tests"}
        self.assertEqual(tool_detail(arguments, ("command",)), "pytest -q")

    def test_falls_back_to_any_string(self) -> None:
        self.assertEqual(tool_detail({"unknown": "value"}), "value")

    def test_non_dict_and_non_string_values_are_ignored(self) -> None:
        self.assertEqual(tool_detail("not a dict"), "")
        self.assertEqual(tool_detail({"count": 2, "flag": True}), "")

    def test_per_tool_mapping(self) -> None:
        mapping = {"Bash": ("command",), "Read": ("path",)}
        self.assertEqual(
            tool_detail_for("Bash", {"command": "ls", "path": "/tmp"}, mapping),
            "ls",
        )
        self.assertEqual(
            tool_detail_for("Read", {"command": "ls", "path": "/tmp"}, mapping),
            "/tmp",
        )
        self.assertEqual(tool_detail_for("Unknown", {"path": "/tmp"}, mapping), "/tmp")

    def test_detail_is_bounded(self) -> None:
        self.assertEqual(len(tool_detail({"path": "y" * 500})), 160)


if __name__ == "__main__":
    unittest.main()
