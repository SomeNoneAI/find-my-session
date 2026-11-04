from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPO_ROOT / "core"))

from fms_lib import __version__  # noqa: E402


class ServerManifestTests(unittest.TestCase):
    def test_server_json_matches_release(self) -> None:
        manifest = json.loads((REPO_ROOT / "server.json").read_text())
        self.assertEqual(
            manifest["name"], "io.github.SomeNoneAI/find-my-session"
        )
        self.assertEqual(manifest["version"], __version__)
        packages = manifest["packages"]
        self.assertEqual(len(packages), 1)
        package = packages[0]
        self.assertEqual(package["registryType"], "pypi")
        self.assertEqual(package["identifier"], "find-my-session")
        self.assertEqual(package["version"], __version__)
        self.assertEqual(package["transport"], {"type": "stdio"})

    def test_readme_carries_registry_ownership_token(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "mcp-name: io.github.SomeNoneAI/find-my-session", readme
        )


if __name__ == "__main__":
    unittest.main()
