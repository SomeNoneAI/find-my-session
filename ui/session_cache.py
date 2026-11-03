"""In-memory snapshot cache for the local UI server.

The UI keeps one shared list of SessionSummary objects for the
/api/sessions and /api/projects endpoints, so a page load costs at most one
store scan. Session details, prompts, and deep search always read the
stores live; only metadata summaries are cached, in memory, never on disk.
"""

from __future__ import annotations

import threading
import time
from typing import List, Optional, Tuple

from fms_lib import service
from fms_lib.models import SessionSummary
from fms_lib.registry import get_adapters

# A snapshot older than this is served as-is while a single background
# rebuild refreshes it (stale-while-revalidate).
MAX_SNAPSHOT_AGE = 60.0

# How long one wait request may block for a newer snapshot revision.
WAIT_TIMEOUT = 10.0

# Cadence of the background refresh that keeps a long-running panel fresh.
REFRESH_INTERVAL = 60.0


def store_fingerprint() -> Tuple[Tuple[str, str], ...]:
    """Identify the store layout implied by the current environment.

    The fingerprint lets one cache serve callers that switch environments
    (tests pointing the harness homes at different fixtures) without ever
    mixing summaries between them.
    """
    return tuple(
        sorted((adapter.name, str(adapter.home())) for adapter in get_adapters(None))
    )


class ScanError(Exception):
    """A store scan failed and no usable snapshot exists for this environment."""


class SessionCache:
    """Thread-safe, single-flight snapshot of summarized sessions."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._snapshot: Optional[List[SessionSummary]] = None
        self._fingerprint: Optional[Tuple[Tuple[str, str], ...]] = None
        self._revision = 0
        self._created = 0.0
        self._refreshing = False
        self._generation = 0
        self._scan_generation = 0
        self._scan_error: Optional[BaseException] = None

    def serve(
        self,
        refresh: bool = False,
        revision: int = 0,
        wait: bool = False,
    ) -> Tuple[List[SessionSummary], int, bool]:
        """Serve the snapshot, coordinating refreshes and client revisions.

        With ``refresh`` the current snapshot is returned immediately while a
        rebuild runs in the background. With ``wait`` the call blocks until a
        rebuild lands a revision newer than ``revision``, the rebuild ends, or
        the bounded timeout expires.
        """
        if refresh and self.has_snapshot():
            snapshot, current, refreshing = self.request_refresh()
        else:
            snapshot, current, refreshing = self.snapshot_now()
        if wait and revision and revision == current and refreshing:
            return self.wait_for_newer(revision)
        return snapshot, current, refreshing

    def has_snapshot(self) -> bool:
        with self._condition:
            return self._snapshot is not None

    def is_refreshing(self) -> bool:
        with self._condition:
            return self._refreshing

    def snapshot_now(self) -> Tuple[List[SessionSummary], int, bool]:
        """Return the snapshot for this environment, blocking for the first scan.

        A warm snapshot is returned immediately; a stale one is returned
        while a single background rebuild refreshes it.
        """
        fingerprint = store_fingerprint()
        while True:
            with self._condition:
                if self._usable_locked(fingerprint):
                    self._revalidate_locked()
                    return self._result_locked()
                if not self._refreshing:
                    self._begin_refresh_locked()
                waited = self._generation
                while self._refreshing:
                    self._condition.wait()
                if self._usable_locked(fingerprint):
                    self._revalidate_locked()
                    return self._result_locked()
                if self._scan_generation == waited and self._scan_error is not None:
                    raise ScanError(
                        "cannot scan session stores: %s" % self._scan_error
                    ) from self._scan_error
            # The scan succeeded but captured another environment; rescan once.
            fingerprint = store_fingerprint()

    def request_refresh(self) -> Tuple[List[SessionSummary], int, bool]:
        """Start a rebuild unless one is running; return the current snapshot."""
        with self._condition:
            if not self._refreshing:
                self._begin_refresh_locked()
            return self._result_locked()

    def wait_for_newer(
        self, revision: int, timeout: float = WAIT_TIMEOUT
    ) -> Tuple[List[SessionSummary], int, bool]:
        """Block until the rebuild bumps the revision past ``revision``."""
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._revision == revision and self._refreshing:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            return self._result_locked()

    def reset(self) -> None:
        """Drop the snapshot; the next request scans again (test hook)."""
        with self._condition:
            self._generation += 1
            self._snapshot = None
            self._fingerprint = None
            self._revision = 0
            self._created = 0.0
            self._scan_generation = 0
            self._scan_error = None
            self._condition.notify_all()

    def _usable_locked(self, fingerprint: Tuple[Tuple[str, str], ...]) -> bool:
        return (
            self._snapshot is not None
            and self._fingerprint is not None
            and self._fingerprint == fingerprint
        )

    def _revalidate_locked(self) -> None:
        if not self._refreshing and time.monotonic() - self._created > MAX_SNAPSHOT_AGE:
            self._begin_refresh_locked()

    def _result_locked(self) -> Tuple[List[SessionSummary], int, bool]:
        snapshot = list(self._snapshot) if self._snapshot is not None else []
        return snapshot, self._revision, self._refreshing

    def _begin_refresh_locked(self) -> None:
        self._refreshing = True
        self._generation += 1
        generation = self._generation
        worker = threading.Thread(
            target=self._run_refresh,
            args=(generation,),
            name="fms-session-cache-refresh",
            daemon=True,
        )
        worker.start()

    def _run_refresh(self, generation: int) -> None:
        error: Optional[BaseException] = None
        try:
            fingerprint = store_fingerprint()
            snapshot: Optional[List[SessionSummary]] = service.gather_summaries()
        except Exception as exc:
            fingerprint = None
            snapshot = None
            error = exc
        with self._condition:
            # A newer refresh or a reset superseded this scan: publish nothing.
            if generation == self._generation and snapshot is not None:
                self._snapshot = snapshot
                self._fingerprint = fingerprint
                self._revision += 1
                self._created = time.monotonic()
            self._scan_generation = generation
            self._scan_error = error
            self._refreshing = False
            self._condition.notify_all()


_CACHE = SessionCache()


def get_cache() -> SessionCache:
    return _CACHE


def reset_cache() -> None:
    _CACHE.reset()


def start_background_maintenance(interval: float = REFRESH_INTERVAL) -> None:
    """Warm the snapshot and keep it fresh for a long-running panel."""
    worker = threading.Thread(
        target=_CACHE.request_refresh, name="fms-session-cache-warmup", daemon=True
    )
    worker.start()

    def tick() -> None:
        try:
            _CACHE.request_refresh()
        except Exception:
            pass
        timer = threading.Timer(interval, tick)
        timer.daemon = True
        timer.start()

    timer = threading.Timer(interval, tick)
    timer.daemon = True
    timer.start()
