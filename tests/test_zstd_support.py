"""Unit tests for the shared zstd support helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "core"))

from fms_lib.harnesses import zstd_support  # noqa: E402


class ScanCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        zstd_support.clear_scan_cache()

    def tearDown(self) -> None:
        zstd_support.clear_scan_cache()

    def test_cached_scan_produces_once_per_key(self) -> None:
        calls = []

        def produce() -> str:
            calls.append(1)
            return "value"

        key = ("some-path", 1, 100)
        self.assertEqual(zstd_support.cached_scan(key, produce), "value")
        self.assertEqual(zstd_support.cached_scan(key, produce), "value")
        self.assertEqual(len(calls), 1)

    def test_cached_scan_new_key_reproduces(self) -> None:
        calls = []

        def produce() -> str:
            calls.append(1)
            return "value"

        zstd_support.cached_scan(("path", 1, 100), produce)
        zstd_support.cached_scan(("path", 2, 100), produce)  # mtime changed
        zstd_support.cached_scan(("path", 1, 200), produce)  # size changed
        self.assertEqual(len(calls), 3)

    def test_cached_scan_without_key_always_produces(self) -> None:
        calls = []

        def produce() -> str:
            calls.append(1)
            return "value"

        zstd_support.cached_scan(None, produce)
        zstd_support.cached_scan(None, produce)
        self.assertEqual(len(calls), 2)

    def test_cache_evicts_oldest_beyond_entry_limit(self) -> None:
        calls = []

        def produce() -> str:
            calls.append(1)
            return "x"

        limit = zstd_support._SCAN_CACHE_MAX_ENTRIES
        for index in range(limit + 1):
            zstd_support.cached_scan(("p", index, 1), produce)
        self.assertEqual(len(calls), limit + 1)
        # The oldest key was evicted, so producing again re-runs.
        zstd_support.cached_scan(("p", 0, 1), produce)
        self.assertEqual(len(calls), limit + 2)
        # The newest key is still cached.
        zstd_support.cached_scan(("p", limit, 1), produce)
        self.assertEqual(len(calls), limit + 2)

    def test_cli_lookup_is_memoized_and_resettable(self) -> None:
        zstd_support.reset_zstd_cli_cache()
        first = zstd_support.zstd_cli()
        second = zstd_support.zstd_cli()
        self.assertEqual(first, second)
        zstd_support.reset_zstd_cli_cache()


if __name__ == "__main__":
    unittest.main()
