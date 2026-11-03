from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = REPO_ROOT / "core"
sys.path.insert(0, str(CORE_DIR))

from fms_lib import __version__  # noqa: E402

SKILL_REQUIRED = ("LICENSE", "SKILL.md", "scripts/fms", "scripts/fms_lib/__init__.py")
UI_REQUIRED = (
    "LICENSE",
    "README.md",
    "fms-ui",
    "server.py",
    "static/index.html",
    "fms_lib/__init__.py",
)
SKILL_TOP_LEVEL = ("LICENSE", "SKILL.md", "references", "scripts")
UI_TOP_LEVEL = ("LICENSE", "README.md", "fms-ui", "server.py", "session_cache.py", "static", "fms_lib")


class BuiltArtifactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory(prefix="fms-artifact-tests-")
        cls.output = Path(cls._temp.name) / "dist"
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "build_artifacts.py"),
                "--output",
                str(cls.output),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            cls._temp.cleanup()
            raise RuntimeError("build_artifacts failed: " + result.stderr)
        cls.skill_archive = cls.output / "find-my-session-skill.zip"
        cls.ui_archive = cls.output / "find-my-session-ui.zip"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp.cleanup()

    def _names(self, archive: Path) -> list:
        with zipfile.ZipFile(archive) as handle:
            return handle.namelist()

    def _assert_clean_contents(self, names: list, required: tuple, top_level: tuple) -> None:
        for member in required:
            self.assertIn(member, names)
        for name in names:
            parts = name.split("/")
            self.assertIn(parts[0], top_level, name)
            self.assertNotIn("__pycache__", parts, name)
            self.assertNotIn(".DS_Store", parts, name)
            self.assertFalse(name.endswith(".pyc"), name)
            self.assertNotIn("fixtures", parts, name)
            self.assertNotIn("qoder-cn-home", parts, name)

    def test_zip_contents_are_self_contained(self) -> None:
        self._assert_clean_contents(
            self._names(self.skill_archive), SKILL_REQUIRED, SKILL_TOP_LEVEL
        )
        self._assert_clean_contents(
            self._names(self.ui_archive), UI_REQUIRED, UI_TOP_LEVEL
        )

    def test_sha256sums_matches_archives(self) -> None:
        checksums = self.output / "SHA256SUMS.txt"
        self.assertTrue(checksums.is_file())
        entries = {}
        for line in checksums.read_text(encoding="utf-8").splitlines():
            digest, name = line.split("  ", 1)
            entries[name] = digest
        self.assertEqual(sorted(entries), sorted([self.skill_archive.name, self.ui_archive.name]))
        for archive in (self.skill_archive, self.ui_archive):
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(entries[archive.name], expected)

    @unittest.skipIf(
        os.name == "nt",
        "executable bits are not representable on Windows file systems",
    )
    def test_zip_launchers_preserve_executable_bits(self) -> None:
        for archive_path, launcher in (
            (self.skill_archive, "scripts/fms"),
            (self.ui_archive, "fms-ui"),
        ):
            with zipfile.ZipFile(archive_path) as archive:
                mode = (archive.getinfo(launcher).external_attr >> 16) & 0o777
            self.assertTrue(mode & 0o111, (archive_path, oct(mode)))

    def test_extracted_artifacts_run_independently(self) -> None:
        checks = (
            (
                self.output / "find-my-session-skill" / "scripts" / "fms",
                "fms %s" % __version__,
            ),
            (
                self.output / "find-my-session-ui" / "fms-ui",
                "fms-ui %s" % __version__,
            ),
        )
        for command, expected in checks:
            # The launchers are Python scripts with a shebang: direct
            # execution needs POSIX; Windows runs them via sys.executable.
            argv = [str(command)]
            if os.name == "nt":
                argv = [sys.executable, str(command)]
            result = subprocess.run(
                [*argv, "--version"], capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), expected)
            if os.name != "nt":
                self.assertTrue(os.access(command, os.X_OK))


if __name__ == "__main__":
    unittest.main()
