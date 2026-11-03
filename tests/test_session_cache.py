from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = REPO_ROOT / "core"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(CORE_DIR))

from fms_lib import service  # noqa: E402
from fms_ui import session_cache  # noqa: E402
from fms_ui.server import api_response  # noqa: E402

try:
    from test_ui import synthetic_environment
except ImportError:  # pragma: no cover - allows running from the repo root
    from tests.test_ui import synthetic_environment


def write_session(home: Path, session_id: str, cwd: str, first: str, updated: str) -> Path:
    """Write one synthetic Qoder CN transcript into the store."""
    directory = home / "projects" / cwd.strip("/").replace("/", "-")
    directory.mkdir(parents=True, exist_ok=True)
    transcript = directory / (session_id + ".jsonl")
    records = [
        {
            "type": "user",
            "sessionId": session_id,
            "timestamp": updated,
            "cwd": cwd,
            "isSidechain": False,
            "humanInput": {"text": first},
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": first}],
            },
        },
        {
            "type": "last-prompt",
            "sessionId": session_id,
            "lastPrompt": first,
        },
    ]
    with transcript.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return transcript


def count_scans():
    """Patch the shared scan helper; returns (patch, calls list)."""
    real_gather = service._gather_summaries
    calls: list = []

    def counting(adapters, report=None):
        calls.append(1)
        return real_gather(adapters, report)

    return mock.patch.object(service, "_gather_summaries", counting), calls


def wait_for_idle(timeout: float = 10.0) -> None:
    cache = session_cache.get_cache()
    deadline = time.monotonic() + timeout
    while cache.is_refreshing() and time.monotonic() < deadline:
        time.sleep(0.01)


class SessionCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="fms-session-cache-")
        self.root = Path(self._temp.name)
        self.home = self.root / "qoder-cn-home"
        write_session(
            self.home,
            "aaaaaaaa-0000-4000-8000-000000000001",
            "/Users/example/alpha",
            "first alpha task",
            "2026-10-20T09:00:05.000Z",
        )
        write_session(
            self.home,
            "bbbbbbbb-0000-4000-8000-000000000002",
            "/Users/example/beta",
            "first beta task",
            "2026-10-21T09:00:05.000Z",
        )
        self.environment = mock.patch.dict(
            os.environ, synthetic_environment(self.root)
        )
        self.environment.start()
        wait_for_idle()
        session_cache.reset_cache()

    def tearDown(self) -> None:
        wait_for_idle()
        session_cache.reset_cache()
        self.environment.stop()
        self._temp.cleanup()

    def search(self, **params) -> dict:
        values = {"harness": ["qoder-cn"], "limit": ["50"]}
        values.update({key: [str(value)] for key, value in params.items()})
        return api_response("/api/sessions", values)

    def test_sessions_and_projects_share_a_single_scan(self) -> None:
        patch, calls = count_scans()
        with patch:
            first = self.search()
            second = self.search()
            projects = api_response("/api/projects", {"harness": ["qoder-cn"]})
        self.assertEqual(len(calls), 1)
        self.assertEqual(first["sessions"], second["sessions"])
        self.assertEqual(len(first["sessions"]), 2)
        self.assertEqual(
            projects["projects"],
            ["/Users/example/alpha", "/Users/example/beta"],
        )

    def test_metadata_filters_still_apply_on_cached_results(self) -> None:
        self.search()
        alpha = self.search(query="alpha")
        self.assertEqual(len(alpha["sessions"]), 1)
        self.assertEqual(alpha["sessions"][0]["cwd"], "/Users/example/alpha")
        limited = self.search(limit=1)
        self.assertEqual(len(limited["sessions"]), 1)

    def test_manual_refresh_serves_snapshot_then_publishes_changes(self) -> None:
        initial = self.search()
        first_revision = initial["revision"]
        self.assertFalse(initial["refreshing"])
        write_session(
            self.home,
            "cccccccc-0000-4000-8000-000000000003",
            "/Users/example/gamma",
            "first gamma task",
            "2026-10-22T09:00:05.000Z",
        )
        refreshed = self.search(refresh="true")
        self.assertTrue(refreshed["refreshing"])
        self.assertEqual(refreshed["revision"], first_revision)
        self.assertEqual(refreshed["sessions"], initial["sessions"])
        updated = self.search(revision=first_revision, wait="true")
        self.assertFalse(updated["refreshing"])
        self.assertNotEqual(updated["revision"], first_revision)
        self.assertEqual(len(updated["sessions"]), 3)
        cwds = {session["cwd"] for session in updated["sessions"]}
        self.assertIn("/Users/example/gamma", cwds)

    def test_concurrent_refreshes_scan_once(self) -> None:
        self.search()
        gate = threading.Event()
        real_gather = service._gather_summaries
        calls: list = []

        def gated(adapters, report=None):
            calls.append(1)
            gate.wait(timeout=10)
            return real_gather(adapters, report)

        responses: list = []
        with mock.patch.object(service, "_gather_summaries", gated):
            threads = [
                threading.Thread(
                    target=lambda: responses.append(self.search(refresh="true"))
                )
                for _ in range(5)
            ]
            for thread in threads:
                thread.start()
            # request_refresh answers immediately from the old snapshot, so
            # every request is collected while the single scan is still gated.
            deadline = time.monotonic() + 10
            while len(responses) < 5 and time.monotonic() < deadline:
                time.sleep(0.01)
            gate.set()
            for thread in threads:
                thread.join(timeout=10)
        wait_for_idle()
        self.assertEqual(len(responses), 5)
        self.assertEqual(len(calls), 1, "concurrent refreshes must share one scan")
        for response in responses:
            self.assertTrue(response["refreshing"])

    def test_cache_isolates_switched_environments(self) -> None:
        here = self.search()
        self.assertEqual(len(here["sessions"]), 2)

        other_root = self.root / "other-env"
        other_home = other_root / "qoder-cn-home"
        write_session(
            other_home,
            "dddddddd-0000-4000-8000-000000000004",
            "/Users/example/delta",
            "first delta task",
            "2026-10-23T09:00:05.000Z",
        )
        other_env = synthetic_environment(other_root)
        with mock.patch.dict(os.environ, other_env):
            there = self.search()
        self.assertEqual(len(there["sessions"]), 1)
        self.assertEqual(there["sessions"][0]["cwd"], "/Users/example/delta")
        # The original environment is served from its own snapshot again.
        back = self.search()
        self.assertEqual(back["sessions"], here["sessions"])

    def test_reset_forces_a_fresh_scan(self) -> None:
        patch, calls = count_scans()
        with patch:
            self.search()
            self.assertEqual(len(calls), 1)
            session_cache.reset_cache()
            self.search()
        self.assertEqual(len(calls), 2)

    def test_wait_returns_immediately_when_nothing_is_refreshing(self) -> None:
        initial = self.search()
        start = time.monotonic()
        waited = self.search(revision=initial["revision"], wait="true")
        self.assertLess(time.monotonic() - start, 5)
        self.assertFalse(waited["refreshing"])
        self.assertEqual(waited["revision"], initial["revision"])

    def test_deep_search_still_bypasses_the_cache(self) -> None:
        patch, calls = count_scans()
        with patch:
            self.search()
            self.assertEqual(len(calls), 1)
            deep = self.search(deep="true", query="alpha")
        self.assertEqual(len(deep["sessions"]), 1)
        self.assertEqual(len(calls), 2, "deep search must scan live")
        self.assertNotIn("revision", deep)

    def test_harness_selection_matches_cli_parsing(self) -> None:
        self.search()
        baseline = self.search()
        combined = self.search(harness="qoder-cn,kimi-code")
        self.assertEqual(combined["sessions"], baseline["sessions"])
        alias = self.search(harness="qcn")
        self.assertEqual(alias["sessions"], baseline["sessions"])
        for wildcard in ("all", "*"):
            everything = self.search(harness=wildcard)
            self.assertEqual(everything["sessions"], baseline["sessions"])
        projects = api_response("/api/projects", {"harness": ["qoder-cn,kimi-code"]})
        self.assertEqual(
            projects["projects"],
            ["/Users/example/alpha", "/Users/example/beta"],
        )
        from fms_lib.errors import UserError

        with self.assertRaises(UserError):
            self.search(harness="no-such-harness")

    def test_first_scan_failure_raises_and_recovers(self) -> None:
        failing = mock.patch.object(
            service, "_gather_summaries", side_effect=OSError("store unreadable")
        )
        with failing:
            with self.assertRaises(session_cache.ScanError) as caught:
                self.search()
            self.assertIn("store unreadable", str(caught.exception))
        self.assertFalse(session_cache.get_cache().is_refreshing())
        self.assertIsNone(session_cache.get_cache()._snapshot)
        healed = self.search()
        self.assertEqual(len(healed["sessions"]), 2)

    def test_warm_refresh_failure_keeps_snapshot_and_allows_retry(self) -> None:
        initial = self.search()
        write_session(
            self.home,
            "cccccccc-0000-4000-8000-000000000003",
            "/Users/example/gamma",
            "first gamma task",
            "2026-10-22T09:00:05.000Z",
        )
        failing = mock.patch.object(
            service, "_gather_summaries", side_effect=OSError("boom")
        )
        with failing:
            refreshed = self.search(refresh="true")
            self.assertEqual(refreshed["sessions"], initial["sessions"])
            wait_for_idle()
        cache = session_cache.get_cache()
        self.assertFalse(cache.is_refreshing())
        self.assertFalse(cache._refreshing)
        # The failed rebuild kept the old snapshot and revision.
        after = self.search()
        self.assertEqual(after["sessions"], initial["sessions"])
        self.assertEqual(after["revision"], initial["revision"])
        # A later retry picks up the change.
        retried = self.search(refresh="true")
        self.assertTrue(retried["refreshing"])
        updated = self.search(revision=retried["revision"], wait="true")
        self.assertEqual(len(updated["sessions"]), 3)


if __name__ == "__main__":
    unittest.main()
