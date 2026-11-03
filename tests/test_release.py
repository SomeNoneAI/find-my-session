from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
import tarfile
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
import fms_ui.server  # noqa: E402

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
    def test_version_has_a_single_source(self) -> None:
        source = PYPROJECT.read_text(encoding="utf-8")
        self.assertIn('dynamic = ["version"]', source)
        self.assertNotRegex(source, r'^version = "', re.MULTILINE)
        self.assertIn("[tool.setuptools.dynamic]", source)
        self.assertIn('version = { attr = "fms_lib.__version__" }', source)
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")


class PackagingMetadataTests(unittest.TestCase):
    def test_pyproject_declares_entry_points(self) -> None:
        source = PYPROJECT.read_text(encoding="utf-8")
        self.assertIn('fms = "fms_lib.cli:main"', source)
        self.assertIn('fms-ui = "fms_ui.server:main"', source)
        self.assertIn('requires-python = ">=3.9"', source)
        self.assertIn('license = "MIT"', source)
        self.assertIn('license-files = ["LICENSE"]', source)
        self.assertIn("setuptools.build_meta", source)

    def test_pyproject_has_discoverable_metadata(self) -> None:
        source = PYPROJECT.read_text(encoding="utf-8")
        self.assertIn("authors =", source)
        self.assertIn("keywords = [", source)
        self.assertIn("classifiers = [", source)
        self.assertIn('Homepage = "https://github.com/SomeNoneAI/find-my-session"', source)

    def test_no_runtime_dependencies(self) -> None:
        source = PYPROJECT.read_text(encoding="utf-8")
        match = re.search(r"^dependencies = (.+)$", source, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1).strip(), "[]")

    def test_entry_points_resolve_to_callables(self) -> None:
        self.assertTrue(callable(fms_main))
        self.assertTrue(callable(fms_ui.server.main))


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
            ignore = shutil.ignore_patterns(
                "__pycache__", "*.pyc", ".DS_Store", "node_modules", "dist"
            )
            shutil.copytree(CORE_DIR, staging / "core", ignore=ignore)
            shutil.copytree(REPO_ROOT / "fms_ui", staging / "fms_ui", ignore=ignore)

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
                self.assertIn("fms_ui/server.py", names)
                self.assertIn("fms_ui/static/index.html", names)
                metadata_name = next(
                    n for n in names if n.endswith(".dist-info/METADATA")
                )
                metadata = (
                    archive.read(metadata_name)
                    .decode("utf-8")
                    .replace("\r\n", "\n")
                )
                self.assertIn("Name: find-my-session\n", metadata)
                self.assertIn("Version: %s\n" % __version__, metadata)
                self.assertIn("Requires-Python: >=3.9\n", metadata)
                self.assertIn("License-Expression: MIT\n", metadata)
                self.assertIn("License-File: LICENSE\n", metadata)
                self.assertIn("Classifier: Environment :: Console\n", metadata)
                self.assertIn("Project-URL: Homepage, ", metadata)
                entry_points_name = next(
                    n for n in names if n.endswith(".dist-info/entry_points.txt")
                )
                entry_points = archive.read(entry_points_name).decode("utf-8")
                self.assertIn("fms = fms_lib.cli:main", entry_points)
                self.assertIn("fms-ui = fms_ui.server:main", entry_points)

    def test_wheel_build_leaves_no_repo_litter(self) -> None:
        self.assertFalse((REPO_ROOT / "build").exists())
        self.assertFalse((REPO_ROOT / "dist" / "build").exists())
        for directory in (REPO_ROOT, CORE_DIR, REPO_ROOT / "fms_ui"):
            self.assertEqual(list(directory.glob("*.egg-info")), [], directory)


@unittest.skipUnless(
    importlib.util.find_spec("build") is not None,
    "the build package is required to test source distributions",
)
class SdistBuildTests(unittest.TestCase):
    def test_sdist_contains_code_static_assets_and_license(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-sdist-test-") as raw:
            staging = Path(raw) / "src"
            out = Path(raw) / "dist"
            staging.mkdir()
            out.mkdir()
            shutil.copy2(PYPROJECT, staging / "pyproject.toml")
            for name in ("LICENSE", "README.md"):
                shutil.copy2(REPO_ROOT / name, staging / name)
            ignore = shutil.ignore_patterns(
                "__pycache__", "*.pyc", ".DS_Store", "node_modules", "dist"
            )
            shutil.copytree(CORE_DIR, staging / "core", ignore=ignore)
            shutil.copytree(REPO_ROOT / "fms_ui", staging / "fms_ui", ignore=ignore)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    "--sdist",
                    "--outdir",
                    str(out),
                ],
                cwd=str(staging),
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            built = list(out.glob("*.tar.gz"))
            self.assertEqual(len(built), 1, result.stdout)
            with tarfile.open(built[0]) as archive:
                names = archive.getnames()
            prefix = built[0].name[: -len(".tar.gz")] + "/"
            expected = (
                prefix + "pyproject.toml",
                prefix + "LICENSE",
                prefix + "core/fms_lib/cli.py",
                prefix + "fms_ui/server.py",
                prefix + "fms_ui/static/index.html",
            )
            for name in expected:
                self.assertIn(name, names)


if __name__ == "__main__":
    unittest.main()
