"""Shared zstd decoding and scan caching for compressed transcript stores.

Codex and DeepSeek keep transcripts as zstd-compressed JSONL, and decoding
dominates their metadata scans. This module shares the decoder plumbing
between those adapters, looks the zstd CLI up once per process, and memoizes
bounded scan results by file identity (path, mtime, size) so long-lived
hosts (the UI server, MCP servers) can re-query stores without
re-decompressing unchanged transcripts.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional, Tuple

try:
    from compression import zstd as _zstd  # type: ignore[import-not-found]
except ImportError:
    _zstd = None

DECODER_MISSING = (
    "zstd decoder unavailable; install the zstd CLI or use Python 3.14+"
)

_SCAN_CACHE_MAX_ENTRIES = 32
_SCAN_CACHE_MAX_BYTES = 8 * 1024 * 1024


class _ProcessStream:
    """Wrap a ``zstd`` subprocess stdout as a context-managed binary stream."""

    def __init__(self, process: "subprocess.Popen[bytes]") -> None:
        self._process = process

    def __enter__(self):
        return self._process.stdout

    def __exit__(self, exc_type, exc, tb) -> "Literal[False]":
        stream = self._process.stdout
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
        if self._process.poll() is None:
            self._process.kill()
        try:
            self._process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        return False


_cli_lock = threading.Lock()
_cli_checked = False
_cli_path: Optional[str] = None


def zstd_cli() -> Optional[str]:
    """Locate the zstd CLI once per process instead of once per decode."""
    global _cli_checked, _cli_path
    with _cli_lock:
        if not _cli_checked:
            _cli_path = shutil.which("zstd")
            _cli_checked = True
        return _cli_path


def reset_zstd_cli_cache() -> None:
    """Forget the cached CLI path (tests that fake the PATH use this)."""
    global _cli_checked
    with _cli_lock:
        _cli_checked = False


def open_zstd(path: Path):
    if _zstd is not None:
        return _zstd.ZstdFile(path, "rb")
    executable = zstd_cli()
    if not executable:
        raise ValueError(DECODER_MISSING)
    process = subprocess.Popen(
        [executable, "-dc", "--quiet", "--", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return _ProcessStream(process)


def iter_raw_lines(path: Path, compressed: bool) -> Iterator[bytes]:
    """Yield raw lines from a transcript, decompressing when compressed."""
    if not compressed:
        with open(path, "rb") as handle:
            for raw in handle:
                yield raw
        return
    with open_zstd(path) as handle:
        iterator = iter(handle)
        while True:
            try:
                raw = next(iterator)
            except StopIteration:
                return
            except OSError:
                raise
            except Exception as exc:
                raise OSError("cannot decompress %s: %s" % (path, exc)) from exc
            yield raw


_scan_lock = threading.Lock()
_scan_cache: "OrderedDict[Tuple[str, int, int], Tuple[Any, int]]" = OrderedDict()
_scan_cache_bytes = 0


def _value_size(value: Any) -> int:
    if isinstance(value, tuple) and len(value) == 2 and all(
        isinstance(part, list) for part in value
    ):
        return sum(len(line) for part in value for line in part)
    size = 0
    for field in getattr(value, "__dict__", {}).values():
        if isinstance(field, str):
            size += len(field)
        elif isinstance(field, dict):
            size += len(str(field))
    return size


def scan_cache_key(path: Path) -> Optional[Tuple[str, int, int]]:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (str(path), stat.st_mtime_ns, stat.st_size)


def cached_scan(
    key: Optional[Tuple[str, int, int]], produce: Callable[[], Any]
) -> Any:
    """Return ``produce()``, memoized by file identity when a key exists."""
    global _scan_cache_bytes
    if key is None:
        return produce()
    with _scan_lock:
        hit = _scan_cache.get(key)
        if hit is not None:
            _scan_cache.move_to_end(key)
            return hit[0]
    value = produce()
    size = _value_size(value)
    with _scan_lock:
        _scan_cache[key] = (value, size)
        _scan_cache_bytes += size
        _scan_cache.move_to_end(key)
        while len(_scan_cache) > _SCAN_CACHE_MAX_ENTRIES or (
            _scan_cache_bytes > _SCAN_CACHE_MAX_BYTES and len(_scan_cache) > 1
        ):
            _, (_, evicted) = _scan_cache.popitem(last=False)
            _scan_cache_bytes -= evicted
    return value


def clear_scan_cache() -> None:
    global _scan_cache_bytes
    with _scan_lock:
        _scan_cache.clear()
        _scan_cache_bytes = 0
