from __future__ import annotations

import builtins
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "core"))

from fms_lib.harnesses.qoder_family import TAIL_BYTES  # noqa: E402
from fms_lib.harnesses.qoder_cn import QoderCNAdapter  # noqa: E402
from fms_lib.render import render_show_markdown  # noqa: E402

SESSION_ID = "a9b8c7d6-1111-4a1b-8c1d-111111111111"


class _TrackingReader:
    def __init__(self, handle, tracker):
        self._handle = handle
        self._tracker = tracker

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._handle.close()
        return False

    def __iter__(self):
        return self

    def __next__(self):
        raw = next(self._handle)
        self._tracker.bytes_read += len(raw)
        return raw

    def read(self, *args):
        data = self._handle.read(*args)
        self._tracker.bytes_read += len(data)
        return data

    def seek(self, *args):
        return self._handle.seek(*args)


class _ReadTracker:
    def __init__(self, transcript: Path):
        self.transcript = transcript
        self.bytes_read = 0
        self._real_open = builtins.open

    def open(self, file, *args, **kwargs):
        handle = self._real_open(file, *args, **kwargs)
        if Path(file) == self.transcript and args and args[0] == "rb":
            return _TrackingReader(handle, self)
        return handle


def _write_large_transcript(path: Path) -> None:
    first = {
        "type": "user",
        "sessionId": SESSION_ID,
        "timestamp": "2026-10-20T09:00:05.000Z",
        "cwd": "/Users/example/project-performance",
        "isSidechain": False,
        "humanInput": {"text": "Inspect the large session without loading it all"},
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Inspect the large session without loading it all",
                }
            ],
        },
    }
    last_text = "Summarize only the current state"
    last = {
        "type": "user",
        "sessionId": SESSION_ID,
        "timestamp": "2026-10-20T10:00:05.000Z",
        "cwd": "/Users/example/project-performance",
        "isSidechain": False,
        "humanInput": {"text": last_text},
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": last_text}],
        },
    }
    filler = {
        "type": "assistant",
        "sessionId": SESSION_ID,
        "timestamp": "2026-10-20T09:30:05.000Z",
        "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "x" * 4096}],
        },
    }
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(first) + "\n")
        for _ in range(1600):
            handle.write(json.dumps(filler) + "\n")
        handle.write(json.dumps(last) + "\n")
        handle.write(
            json.dumps(
                {
                    "type": "last-prompt",
                    "sessionId": SESSION_ID,
                    "lastPrompt": last_text,
                }
            )
            + "\n"
        )


class LargeSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="fms-performance-")
        self.root = Path(self._temp.name)
        self.home = self.root / "home"
        transcript_dir = self.home / "projects" / "-Users-example-project-performance"
        transcript_dir.mkdir(parents=True)
        self.transcript = transcript_dir / (SESSION_ID + ".jsonl")
        _write_large_transcript(self.transcript)
        self.environment = mock.patch.dict(
            os.environ,
            {
                "FMS_QODER_CN_HOME": str(self.home),
                "FMS_QODER_CN_APP_DB": str(self.root / "missing.sqlite"),
            },
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self._temp.cleanup()

    def test_metadata_search_reads_bounded_slices_of_a_large_transcript(self) -> None:
        self.assertGreater(self.transcript.stat().st_size, 6_000_000)
        tracker = _ReadTracker(self.transcript)
        with mock.patch("builtins.open", new=tracker.open):
            summary = QoderCNAdapter().summarize(self.transcript)
        self.assertEqual(summary.session_id, SESSION_ID)
        self.assertEqual(summary.first_prompt, "Inspect the large session without loading it all")
        self.assertEqual(summary.last_prompt, "Summarize only the current state")
        self.assertLess(tracker.bytes_read, TAIL_BYTES + 100_000)
        self.assertLess(tracker.bytes_read, self.transcript.stat().st_size // 8)

    def test_large_transcript_still_produces_a_bounded_handoff(self) -> None:
        adapter = QoderCNAdapter()
        summary = adapter.summarize(self.transcript)
        detail = adapter.load(summary)
        output = render_show_markdown(
            detail,
            messages=2,
            chars=600,
            summary_chars=1000,
        )
        self.assertIn("Inspect the large session without loading it all", output)
        self.assertIn("Summarize only the current state", output)
        self.assertLess(len(output), 20_000)


if __name__ == "__main__":
    unittest.main()
