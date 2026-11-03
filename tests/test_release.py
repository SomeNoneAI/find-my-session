from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = REPO_ROOT / "core"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(CORE_DIR))

from fms_lib import __version__  # noqa: E402
from fms_lib.cli import main as fms_main  # noqa: E402
import ui.server  # noqa: E402

PYPROJECT = REPO_ROOT / "pyproject.toml"


def pip_supports_pep621() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    if result.returncode != 0:
        return False
    match = re.search(r"pip (\d+)\.(\d+)", result.stdout)
    if not match:
        return False
    return (int(match.group(1)), int(match.group(2))) >= (22, 0)


class VersionConsistencyTests(unittest.TestCase):
    def test_version_matches_pyproject(self) -> None:
        source = PYPROJECT.read_text(encoding="utf-8")
        match = re.search(r'^version = "([^"]+)"', source, re.MULTILINE)
        self.assertIsNotNone(match, "pyproject.toml declares a [project] version")
        self.assertEqual(match.group(1), __version__)
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")


class PackagingMetadataTests(unittest.TestCase):
    def test_pyproject_declares_entry_points(self) -> None:
        source = PYPROJECT.read_text(encoding="utf-8")
        self.assertIn('fms = "fms_lib.cli:main"', source)
        self.assertIn('fms-ui = "ui.server:main"', source)
        self.assertIn('requires-python = ">=3.9"', source)
        self.assertIn("setuptools.build_meta", source)

    def test_no_runtime_dependencies(self) -> None:
        source = PYPROJECT.read_text(encoding="utf-8")
        match = re.search(r"^dependencies = (.+)$", source, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1).strip(), "[]")

    def test_entry_points_resolve_to_callables(self) -> None:
        self.assertTrue(callable(fms_main))
        self.assertTrue(callable(ui.server.main))


@unittest.skipUnless(
    pip_supports_pep621(), "pip >= 22 is required to build PEP 621 wheels"
)
class WheelBuildTests(unittest.TestCase):
    def test_wheel_contains_code_static_assets_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-wheel-test-") as raw:
            staging = Path(raw) / "src"
            wheels = Path(raw) / "wheels"
            staging.mkdir()
            wheels.mkdir()
            shutil.copy2(PYPROJECT, staging / "pyproject.toml")
            for name in ("LICENSE", "README.md"):
                shutil.copy2(REPO_ROOT / name, staging / name)
            ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
            shutil.copytree(CORE_DIR, staging / "core", ignore=ignore)
            shutil.copytree(REPO_ROOT / "ui", staging / "ui", ignore=ignore)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--wheel-dir",
                    str(wheels),
                    str(staging),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            built = list(wheels.glob("*.whl"))
            self.assertEqual(len(built), 1, result.stdout)
            with zipfile.ZipFile(built[0]) as archive:
                names = archive.namelist()
                self.assertIn("fms_lib/cli.py", names)
                self.assertIn("fms_lib/harnesses/__init__.py", names)
                self.assertIn("ui/server.py", names)
                self.assertIn("ui/static/index.html", names)
                metadata_name = next(
                    n for n in names if n.endswith(".dist-info/METADATA")
                )
                metadata = archive.read(metadata_name).decode("utf-8")
                self.assertIn("Name: find-my-session\n", metadata)
                self.assertIn("Version: %s\n" % __version__, metadata)
                self.assertIn("Requires-Python: >=3.9\n", metadata)
                entry_points_name = next(
                    n for n in names if n.endswith(".dist-info/entry_points.txt")
                )
                entry_points = archive.read(entry_points_name).decode("utf-8")
                self.assertIn("fms = fms_lib.cli:main", entry_points)
                self.assertIn("fms-ui = ui.server:main", entry_points)

    def test_wheel_build_leaves_no_repo_litter(self) -> None:
        self.assertFalse((REPO_ROOT / "build").exists())
        self.assertFalse((REPO_ROOT / "dist" / "build").exists())
        for directory in (REPO_ROOT, CORE_DIR, REPO_ROOT / "ui"):
            self.assertEqual(list(directory.glob("*.egg-info")), [], directory)


if __name__ == "__main__":
    unittest.main()
