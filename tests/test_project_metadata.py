from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "core"))

from fms_lib.registry import harness_rows  # noqa: E402


class ProjectMetadataTests(unittest.TestCase):
    def test_repository_documents_have_no_placeholder_clone_url(self) -> None:
        documents = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "README.zh-CN.md",
            REPO_ROOT / "CONTRIBUTING.md",
        ]
        for document in documents:
            with self.subTest(document=document.name):
                self.assertNotIn("your-org", document.read_text(encoding="utf-8"))
                self.assertIn(
                    "https://github.com/SomeNoneAI/find-my-session",
                    document.read_text(encoding="utf-8"),
                )

    def test_compatibility_matrix_covers_every_registered_harness(self) -> None:
        matrix = (REPO_ROOT / "docs" / "compatibility.md").read_text(encoding="utf-8")
        for row in harness_rows():
            with self.subTest(harness=row["name"]):
                self.assertIn("`%s`" % row["name"], matrix)

    def test_readmes_link_compatibility_and_both_release_products(self) -> None:
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(document=name):
                text = (REPO_ROOT / name).read_text(encoding="utf-8")
                self.assertIn("docs/compatibility.md", text)
                self.assertIn("find-my-session-skill.zip", text)
                self.assertIn("find-my-session-ui.zip", text)
                for row in harness_rows():
                    self.assertIn("`%s`" % row["name"], text)


if __name__ == "__main__":
    unittest.main()
