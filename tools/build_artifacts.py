#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

COPY_IGNORE_PATTERNS = ("__pycache__", "*.pyc", ".DS_Store")


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(*COPY_IGNORE_PATTERNS),
    )


def _write_sha256sums(output: Path, archives: List[Path]) -> Path:
    checksums = output / "SHA256SUMS.txt"
    lines = []
    for archive in archives:
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        lines.append("%s  %s" % (digest, archive.name))
    checksums.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return checksums


def build_artifacts(output: Path) -> List[Path]:
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "find-my-session-skill": output / "find-my-session-skill",
        "find-my-session-ui": output / "find-my-session-ui",
    }
    for name, directory in artifacts.items():
        if directory.exists():
            shutil.rmtree(directory)
        archive = output / (name + ".zip")
        if archive.exists():
            archive.unlink()
    stale_checksums = output / "SHA256SUMS.txt"
    if stale_checksums.exists():
        stale_checksums.unlink()

    skill = artifacts["find-my-session-skill"]
    skill.mkdir()
    shutil.copy2(REPO_ROOT / "LICENSE", skill / "LICENSE")
    shutil.copy2(REPO_ROOT / "skills" / "find-my-session" / "SKILL.md", skill / "SKILL.md")
    _copy_tree(REPO_ROOT / "skills" / "find-my-session" / "references", skill / "references")
    (skill / "scripts").mkdir()
    shutil.copy2(REPO_ROOT / "skills" / "find-my-session" / "scripts" / "fms", skill / "scripts" / "fms")
    _copy_tree(REPO_ROOT / "core" / "fms_lib", skill / "scripts" / "fms_lib")

    ui = artifacts["find-my-session-ui"]
    ui.mkdir()
    shutil.copy2(REPO_ROOT / "LICENSE", ui / "LICENSE")
    shutil.copy2(REPO_ROOT / "ui" / "README.md", ui / "README.md")
    shutil.copy2(REPO_ROOT / "ui" / "fms-ui", ui / "fms-ui")
    shutil.copy2(REPO_ROOT / "ui" / "server.py", ui / "server.py")
    shutil.copy2(REPO_ROOT / "ui" / "session_cache.py", ui / "session_cache.py")
    _copy_tree(REPO_ROOT / "ui" / "static", ui / "static")
    _copy_tree(REPO_ROOT / "core" / "fms_lib", ui / "fms_lib")

    archives = []
    for name, directory in artifacts.items():
        archive = shutil.make_archive(str(output / name), "zip", root_dir=directory)
        archives.append(Path(archive))
    _write_sha256sums(output, archives)
    return archives


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build standalone skill and UI artifacts.")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "dist",
        help="output directory (default: dist)",
    )
    args = parser.parse_args(argv)
    for archive in build_artifacts(args.output):
        print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
