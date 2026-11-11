"""Tests for the diagnostics surface: ``fms doctor`` and ``search --verbose``.

All stores are synthetic and live in temporary directories. The missing-
decoder scenario is simulated by patching the DeepSeek adapter's decoder
probe, so it runs on any machine; corrupt-transcript scenarios need a real
zstd decoder and are skipped when none is available.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = REPO_ROOT / "core"
sys.path.insert(0, str(CORE_DIR))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli_support import FixtureTestCase  # noqa: E402
from deepseek_fixture import HAS_ZSTD  # noqa: E402
from fms_lib import diagnostics, fingerprint as fingerprint_module  # noqa: E402
from fms_lib import service  # noqa: E402
from fms_lib.fingerprint import fingerprint_store  # noqa: E402
from fms_lib.harnesses import deepseek as deepseek_module  # noqa: E402

SESSION_ONE = "d1a60001-1111-4a1b-8c1d-111111111111"
SESSION_TWO = "d2a60002-2222-4b2c-9d2e-222222222222"
SESSION_BAD = "d3a60003-3333-4c3d-9e3f-333333333333"
PROJECT = "/Users/example/project-diag"

_MS = 1760000000000


def _header(session_id: str) -> dict:
    return {
        "type": "session",
        "version": 3,
        "id": "session-" + session_id,
        "createdAt": _MS,
        "cwd": PROJECT,
        "isSeeded": False,
        "delegationDepth": 0,
        "agentPreset": "standard",
    }


def _user(text: str) -> dict:
    return {
        "type": "user/message",
        "seq": 2,
        "time": _MS + 1000,
        "data": {
            "content": [{"type": "text", "text": text}],
            "source": {"kind": "user"},
            "role": "user",
            "id": "msg-2",
        },
    }


def _records(session_id: str, prompt: str):
    return [_header(session_id), _user(prompt)]


def _compress_jsonl(path: Path) -> Path:
    target = path.with_name(path.name + ".zstd")
    data = path.read_bytes()
    if deepseek_module._zstd is not None:
        with deepseek_module._zstd.ZstdFile(target, "wb") as handle:
            handle.write(data)
    else:
        with target.open("wb") as handle:
            subprocess.run(
                [shutil.which("zstd"), "-q", "-c", "--", str(path)],
                check=True,
                stdout=handle,
                stderr=subprocess.DEVNULL,
            )
    path.unlink()
    return target


def _write_transcript(home: Path, session_id: str, records, name="session.v3.jsonl") -> Path:
    session_dir = home / "sessions" / "diag-group" / ("session-" + session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / name
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    target = _compress_jsonl(path)
    stamp = _MS / 1000.0
    os.utime(target, (stamp, stamp))
    return target


def _write_corrupt_transcript(home: Path, session_id: str) -> Path:
    session_dir = home / "sessions" / "diag-group" / ("session-" + session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    target = session_dir / "session.v3.jsonl.zstd"
    target.write_bytes(b"\x28\xb5\x2f\xfd" + b"not-a-real-zstd-frame" * 8)
    return target


def _build_home(root: Path, *, corrupt: bool = False) -> Path:
    home = root / "dsh-home"
    home.mkdir(parents=True)
    _write_transcript(home, SESSION_ONE, _records(SESSION_ONE, "First diagnostic prompt."))
    _write_transcript(home, SESSION_TWO, _records(SESSION_TWO, "Second diagnostic prompt."))
    if corrupt:
        _write_corrupt_transcript(home, SESSION_BAD)
    return home


def _no_decoder():
    """Simulate a host without any zstd decoder (module or CLI)."""
    from fms_lib.harnesses import zstd_support

    return mock.patch.multiple(
        zstd_support,
        _zstd=None,
        zstd_cli=lambda: None,
    )


class DiagnosticsUnitTests(unittest.TestCase):
    def test_classify_decoder_missing(self) -> None:
        exc = ValueError("zstd decoder unavailable; install the zstd CLI")
        self.assertEqual(diagnostics.classify(exc), "decoder-missing")

    def test_classify_oserror_and_value_error(self) -> None:
        self.assertEqual(
            diagnostics.classify(PermissionError(13, "denied", "/x")),
            "unreadable",
        )
        self.assertEqual(
            diagnostics.classify(
                OSError("cannot decompress session: Unsupported frame parameter")
            ),
            "parse-error",
        )
        self.assertEqual(
            diagnostics.classify(ValueError("cannot read session header")),
            "parse-error",
        )

    def test_sanitize_strips_paths(self) -> None:
        path = Path("/Users/example/.dsh/sessions/g/session-abc/session.v3.jsonl.zstd")
        exc = ValueError("cannot read DeepSeek session header: %s" % path)
        detail = diagnostics.sanitize_detail(exc, path)
        self.assertNotIn(str(path), detail)
        self.assertNotIn("session-abc", detail)
        self.assertIn("<session>", detail)

    def test_sanitize_oserror_uses_strerror_only(self) -> None:
        exc = PermissionError(13, "Permission denied", "/Users/example/secret")
        detail = diagnostics.sanitize_detail(exc, Path("/Users/example/secret"))
        self.assertEqual(detail, "Permission denied")

    def test_report_groups_and_issues(self) -> None:
        report = diagnostics.ScanReport()
        path = Path("/tmp/fake/session.v3.jsonl.zstd")
        report.candidates = 3
        report.record(
            "deepseek", ValueError("zstd decoder unavailable; install zstd"), path
        )
        report.record(
            "deepseek", ValueError("zstd decoder unavailable; install zstd"), path
        )
        self.assertEqual(
            report.grouped(),
            [
                (
                    "deepseek",
                    "decoder-missing",
                    2,
                    "zstd decoder unavailable; install zstd",
                    [path, path],
                )
            ],
        )
        issues = report.to_dict()["issues"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["count"], 2)
        # The detail lacks the full advice, so the hint field is added.
        self.assertIn("install the zstd CLI or use Python 3.14+", issues[0]["hint"])

    def test_issue_hint_suppressed_when_detail_has_it(self) -> None:
        report = diagnostics.ScanReport()
        report.record(
            "deepseek",
            ValueError(
                "zstd decoder unavailable; install the zstd CLI or use Python 3.14+"
            ),
        )
        issues = report.to_dict()["issues"]
        self.assertNotIn("hint", issues[0])

    def test_zstd_status_shape(self) -> None:
        status = diagnostics.zstd_status()
        self.assertIsInstance(status["available"], bool)
        self.assertEqual(
            status["available"],
            status["python_compression"] or status["cli"],
        )

    def test_render_doctor_text_missing_store(self) -> None:
        payload = {
            "fms": "0.0.0",
            "python": "3.9.0",
            "platform": "TestOS 1.0 arm64",
            "zstd": {
                "available": False,
                "python_compression": False,
                "cli": False,
                "hint": "install the zstd CLI or use Python 3.14+",
            },
            "stores": [
                {
                    "harness": "example",
                    "store": "~/.example",
                    "present": False,
                    "candidates": 0,
                    "readable": 0,
                    "skipped": 0,
                    "issues": [],
                }
            ],
        }
        text = diagnostics.render_doctor_text(payload)
        self.assertIn("fms 0.0.0", text)
        self.assertIn("zstd: missing (install the zstd CLI or use Python 3.14+)", text)
        self.assertIn("example (~/.example) [not found]", text)
        self.assertIn("candidates: 0, readable: 0, skipped: 0", text)


class DoctorTests(FixtureTestCase):
    def test_text_reports_counts_and_categories(self) -> None:
        if not HAS_ZSTD:
            self.skipTest("zstd decoder unavailable")
        with tempfile.TemporaryDirectory(prefix="fms-doctor-") as raw:
            home = _build_home(Path(raw), corrupt=True)
            code, out, err = self.run_cli("doctor", "--harness", "deepseek", deepseek_home=home)
            self.assertEqual(code, 0, err)
            self.assertIn("deepseek (~/.dsh) [present]", out)
            self.assertIn("candidates: 3, readable: 2, skipped: 1", out)
            self.assertIn("parse-error x1", out)
            self.assertIn("<session>", out)
            self.assertTrue(out.startswith("fms "))

    def test_json_fields_and_privacy(self) -> None:
        if not HAS_ZSTD:
            self.skipTest("zstd decoder unavailable")
        with tempfile.TemporaryDirectory(prefix="fms-doctor-") as raw:
            home = _build_home(Path(raw), corrupt=True)
            payload = self.run_json("doctor", "--harness", "deepseek", deepseek_home=home)
            self.assertIn("fms", payload)
            self.assertIn("python", payload)
            self.assertIn("platform", payload)
            self.assertIn("zstd", payload)
            self.assertEqual(len(payload["stores"]), 1)
            store = payload["stores"][0]
            self.assertEqual(store["harness"], "deepseek")
            self.assertEqual(store["store"], "~/.dsh")
            self.assertTrue(store["present"])
            self.assertEqual(store["candidates"], 3)
            self.assertEqual(store["readable"], 2)
            self.assertEqual(store["skipped"], 1)
            self.assertEqual(len(store["issues"]), 1)
            self.assertEqual(store["issues"][0]["reason"], "parse-error")
            self.assertEqual(store["issues"][0]["count"], 1)
            serialized = json.dumps(payload, ensure_ascii=False)
            for private in (
                SESSION_BAD,
                SESSION_ONE,
                PROJECT,
                "session.v3.jsonl.zstd",
                str(home),
            ):
                self.assertNotIn(private, serialized)

    def test_harness_filter_and_missing_store_is_not_an_error(self) -> None:
        missing = Path(self._temp.name) / "never-created-store"
        code, out, err = self.run_cli(
            "doctor",
            "--harness",
            "qcn",
            home=missing,
            deepseek_home=self.empty_deepseek_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("qoder-cn", out)
        self.assertNotIn("deepseek", out)
        self.assertIn("not found", out)
        self.assertIn("candidates: 0, readable: 0, skipped: 0", out)

    def test_empty_store_is_not_an_error(self) -> None:
        code, out, err = self.run_cli("doctor", "--harness", "deepseek", deepseek_home=self.empty_deepseek_home)
        self.assertEqual(code, 0, err)
        self.assertIn("candidates: 0, readable: 0, skipped: 0", out)
        self.assertNotIn("parse-error", out)
        self.assertNotIn("unreadable", out)

    def test_default_covers_every_ready_harness(self) -> None:
        payload = self.run_json("doctor", deepseek_home=self.empty_deepseek_home)
        names = {store["harness"] for store in payload["stores"]}
        self.assertLessEqual({"deepseek", "qoder-cn", "kimi-code"}, names)
        for store in payload["stores"]:
            for key in (
                "harness", "variants", "store", "home", "present",
                "candidates", "readable", "skipped", "issues",
            ):
                self.assertIn(key, store)

    def test_decoder_missing_reports_actionable_hint(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-doctor-") as raw:
            home = _build_home(Path(raw))
            with _no_decoder():
                code, out, err = self.run_cli("doctor", "--harness", "deepseek", deepseek_home=home)
                self.assertEqual(code, 0, err)
            self.assertIn("candidates: 2, readable: 0, skipped: 2", out)
            self.assertIn("decoder-missing x2", out)
            self.assertIn("install the zstd CLI or use Python 3.14+", out)
            self.assertNotIn(SESSION_ONE, out)

    def test_decoder_missing_json_issue_shape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-doctor-") as raw:
            home = _build_home(Path(raw))
            with _no_decoder():
                payload = self.run_json("doctor", "--harness", "deepseek", deepseek_home=home)
            store = payload["stores"][0]
            self.assertEqual(store["skipped"], 2)
            self.assertEqual(store["issues"][0]["reason"], "decoder-missing")
            self.assertEqual(store["issues"][0]["count"], 2)
            # The actionable advice is present, inline or via the hint field.
            self.assertIn(
                "install the zstd CLI or use Python 3.14+",
                json.dumps(store["issues"][0], ensure_ascii=False),
            )


class FingerprintUnitTests(unittest.TestCase):
    def _write_jsonl(self, path: Path, records) -> Path:
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path

    def test_jsonl_shape_and_privacy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-fp-") as raw:
            path = self._write_jsonl(
                Path(raw) / "session.jsonl",
                [
                    {
                        "type": "session",
                        "cwd": "/Users/example/secret-project",
                        "n": 3,
                        "flag": True,
                        "note": None,
                        "nested": {"key": "value"},
                    },
                    {
                        "type": "user",
                        "text": "TOP SECRET PROMPT WORDS",
                        "seq": 2.5,
                        "tags": ["alpha"],
                    },
                ],
            )
            out = fingerprint_store([path])
        kinds = out["kinds"]
        self.assertEqual(kinds["jsonl"]["files"], 1)
        self.assertEqual(kinds["jsonl"]["records"], 2)
        self.assertEqual(kinds["jsonl"]["records_unparsed"], 0)
        fields = kinds["jsonl"]["fields"]
        self.assertEqual(fields["type"], {"str": 2})
        self.assertEqual(fields["n"], {"int": 1})
        self.assertEqual(fields["seq"], {"float": 1})
        self.assertEqual(fields["flag"], {"bool": 1})
        self.assertEqual(fields["note"], {"null": 1})
        self.assertEqual(fields["tags"], {"list": 1})
        self.assertEqual(fields["nested"], {"object": 1})
        self.assertIn("bounds", out)
        serialized = json.dumps(out, ensure_ascii=False)
        for private in (
            "secret-project",
            "TOP SECRET PROMPT WORDS",
            "/Users/example",
        ):
            self.assertNotIn(private, serialized)

    def test_blank_and_unparsed_lines(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-fp-") as raw:
            path = Path(raw) / "session.jsonl"
            path.write_text('\n{"type": "a"}\nnot-json\n\n{"type": "b"}\n')
            out = fingerprint_store([path])
        entry = out["kinds"]["jsonl"]
        self.assertEqual(entry["records"], 2)
        self.assertEqual(entry["records_unparsed"], 1)

    def test_json_document_and_text_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-fp-") as raw:
            document = Path(raw) / "state.json"
            document.write_text('{\n  "version": 3,\n  "title": "SECRET TITLE"\n}')
            broken = Path(raw) / "broken.json"
            broken.write_text('{"version": 3,')
            plain = Path(raw) / "notes.txt"
            plain.write_text("just some plain notes\n")
            out = fingerprint_store([document, broken, plain])
        kinds = out["kinds"]
        self.assertEqual(kinds["json"]["files"], 1)
        self.assertEqual(kinds["json"]["records"], 1)
        self.assertEqual(kinds["json"]["fields"]["version"], {"int": 1})
        self.assertEqual(kinds["text"]["files"], 2)
        self.assertEqual(kinds["json"]["fields"].get("title"), {"str": 1})
        self.assertNotIn("SECRET TITLE", json.dumps(out, ensure_ascii=False))

    def test_empty_and_binary_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-fp-") as raw:
            empty = Path(raw) / "empty.jsonl"
            empty.write_text("")
            blob = Path(raw) / "blob.bin"
            blob.write_bytes(b"\x00\x01\x02\xff\xfe")
            out = fingerprint_store([empty, blob])
        self.assertEqual(out["kinds"]["empty"]["files"], 1)
        self.assertEqual(out["kinds"]["binary"]["files"], 1)

    def test_missing_file_counts_as_unreadable(self) -> None:
        out = fingerprint_store([Path("/nonexistent/fms-fp/session.jsonl")])
        self.assertEqual(out["kinds"]["unreadable"]["files"], 1)

    def test_sqlite_shape_excludes_row_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-fp-") as raw:
            path = Path(raw) / "store.db"
            connection = sqlite3.connect(str(path))
            try:
                connection.execute(
                    "CREATE TABLE chat_sessions ("
                    "session_id TEXT PRIMARY KEY, archived INTEGER)"
                )
                connection.executemany(
                    "INSERT INTO chat_sessions VALUES (?, ?)",
                    [("secret-id-1", 0), ("secret-id-2", 1)],
                )
                connection.commit()
            finally:
                connection.close()
            out = fingerprint_store([path])
        entry = out["kinds"]["sqlite"]
        self.assertEqual(entry["files"], 1)
        self.assertEqual(entry["records"], 2)
        table = entry["tables"][0]
        self.assertEqual(table["name"], "chat_sessions")
        self.assertEqual(table["rows"], 2)
        self.assertEqual(
            table["columns"],
            [
                {"name": "session_id", "type": "TEXT"},
                {"name": "archived", "type": "INTEGER"},
            ],
        )
        self.assertNotIn("secret-id-1", json.dumps(out, ensure_ascii=False))

    def test_field_cap_is_reported(self) -> None:
        record = {("field%03d" % index): index for index in range(70)}
        with tempfile.TemporaryDirectory(prefix="fms-fp-") as raw:
            path = self._write_jsonl(Path(raw) / "wide.jsonl", [record])
            out = fingerprint_store([path])
        entry = out["kinds"]["jsonl"]
        self.assertEqual(len(entry["fields"]), fingerprint_module.MAX_FIELDS)
        self.assertTrue(entry["truncated_fields"])

    def test_zstd_undecodable_without_decoder(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-fp-") as raw:
            path = Path(raw) / "session.jsonl.zstd"
            path.write_bytes(b"\x28\xb5\x2f\xfd" + b"payload" * 32)
            with mock.patch.object(fingerprint_module, "_zstd_module", None):
                with mock.patch.object(
                    fingerprint_module.shutil, "which", return_value=None
                ):
                    out = fingerprint_store([path])
        self.assertEqual(out["kinds"]["zstd-undecodable"]["files"], 1)

    def test_zstd_sampled_when_decoder_available(self) -> None:
        if not HAS_ZSTD:
            self.skipTest("zstd decoder unavailable")
        with tempfile.TemporaryDirectory(prefix="fms-fp-") as raw:
            plain = self._write_jsonl(
                Path(raw) / "session.jsonl",
                [{"type": "session", "cwd": "/Users/example/project-x"}],
            )
            target = plain.with_name("session.jsonl.zstd")
            self._compress(plain, target)
            plain.unlink()
            out = fingerprint_store([target])
        self.assertEqual(out["kinds"]["jsonl"]["files"], 1)
        self.assertEqual(
            out["kinds"]["jsonl"]["fields"]["cwd"], {"str": 1}
        )
        self.assertNotIn("project-x", json.dumps(out, ensure_ascii=False))

    def _compress(self, source: Path, target: Path) -> None:
        if deepseek_module._zstd is not None:
            with deepseek_module._zstd.ZstdFile(target, "wb") as handle:
                handle.write(source.read_bytes())
        else:
            with target.open("wb") as handle:
                subprocess.run(
                    [shutil.which("zstd"), "-q", "-c", "--", str(source)],
                    check=True,
                    stdout=handle,
                    stderr=subprocess.DEVNULL,
                )


class DoctorFingerprintTests(FixtureTestCase):
    def test_json_without_flag_has_no_fingerprint(self) -> None:
        payload = self.run_json(
            "doctor", "--harness", "deepseek", deepseek_home=self.deepseek_home
        )
        for store in payload["stores"]:
            self.assertNotIn("fingerprint", store)

    def test_text_fingerprint_only_with_flag(self) -> None:
        if not HAS_ZSTD:
            self.skipTest("zstd decoder unavailable")
        code, out, err = self.run_cli(
            "doctor", "--harness", "deepseek", deepseek_home=self.deepseek_home
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn("fingerprint", out)
        code, out, err = self.run_cli(
            "doctor",
            "--harness",
            "deepseek",
            "--fingerprint",
            deepseek_home=self.deepseek_home,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("fingerprint: jsonl x", out)
        self.assertIn("cwd: str x", out)
        self.assertNotIn(self.deepseek_home.name, out)

    def test_json_fingerprint_shape_and_privacy(self) -> None:
        if not HAS_ZSTD:
            self.skipTest("zstd decoder unavailable")
        with tempfile.TemporaryDirectory(prefix="fms-doctor-") as raw:
            home = _build_home(Path(raw))
            payload = self.run_json(
                "doctor",
                "--harness",
                "deepseek",
                "--fingerprint",
                deepseek_home=home,
            )
        store = payload["stores"][0]
        self.assertIn("fingerprint", store)
        fingerprint = store["fingerprint"]
        self.assertEqual(fingerprint["bounds"]["records_per_file"], 200)
        kinds = fingerprint["kinds"]
        self.assertEqual(kinds["jsonl"]["files"], 2)
        self.assertEqual(kinds["jsonl"]["records"], 4)
        self.assertEqual(kinds["jsonl"]["fields"]["cwd"], {"str": 2})
        self.assertEqual(kinds["jsonl"]["fields"]["version"], {"int": 2})
        serialized = json.dumps(payload, ensure_ascii=False)
        for private in (
            SESSION_ONE,
            SESSION_TWO,
            PROJECT,
            "First diagnostic prompt.",
            str(home),
        ):
            self.assertNotIn(private, serialized)


class VerboseSearchTests(FixtureTestCase):
    def test_verbose_warns_on_skipped_sessions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-verbose-") as raw:
            home = _build_home(Path(raw))
            with _no_decoder():
                code, out, err = self.run_cli(
                    "search", "--harness", "deepseek", "--verbose", deepseek_home=home
                )
                self.assertEqual(code, 0, err)
            self.assertIn("no sessions matched", out)
            self.assertIn("warning", err)
            self.assertIn("deepseek", err)
            self.assertIn("2x decoder-missing", err)
            self.assertIn("install the zstd CLI or use Python 3.14+", err)

    def test_verbose_shows_paths_only_when_verbose(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-verbose-") as raw:
            home = _build_home(Path(raw))
            with _no_decoder():
                code, out, err = self.run_cli(
                    "search", "--harness", "deepseek", "--verbose", deepseek_home=home
                )
                self.assertEqual(code, 0, err)
                self.assertIn("session-" + SESSION_ONE, err)
                self.assertIn("session.v3.jsonl.zstd", err)

    def test_default_search_stays_quiet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-verbose-") as raw:
            home = _build_home(Path(raw))
            with _no_decoder():
                code, out, err = self.run_cli(
                    "search", "--harness", "deepseek", deepseek_home=home
                )
                self.assertEqual(code, 0, err)
            self.assertIn("no sessions matched", out)
            self.assertEqual(err, "")

    def test_verbose_keeps_json_stdout_clean(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-verbose-") as raw:
            home = _build_home(Path(raw))
            with _no_decoder():
                code, out, err = self.run_cli(
                    "search", "--harness", "deepseek", "--verbose", "--json", deepseek_home=home
                )
                self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out), [])
            self.assertIn("decoder-missing", err)

    def test_verbose_latest_warns_too(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-verbose-") as raw:
            home = _build_home(Path(raw))
            with _no_decoder():
                code, out, err = self.run_cli(
                    "latest", "--harness", "deepseek", "--verbose", deepseek_home=home
                )
                self.assertEqual(code, 0, err)
            self.assertIn("no sessions matched", out)
            self.assertIn("decoder-missing", err)

    def test_single_corrupt_file_does_not_fail_search(self) -> None:
        if not HAS_ZSTD:
            self.skipTest("zstd decoder unavailable")
        with tempfile.TemporaryDirectory(prefix="fms-corrupt-") as raw:
            home = _build_home(Path(raw), corrupt=True)
            code, out, err = self.run_cli("search", "--harness", "deepseek", deepseek_home=home)
            self.assertEqual(code, 0, err)
            self.assertIn("deepseek:" + SESSION_ONE[:8], out)
            self.assertIn("deepseek:" + SESSION_TWO[:8], out)
            self.assertEqual(err, "")

    def test_corrupt_file_surfaces_in_verbose_warning(self) -> None:
        if not HAS_ZSTD:
            self.skipTest("zstd decoder unavailable")
        with tempfile.TemporaryDirectory(prefix="fms-corrupt-") as raw:
            home = _build_home(Path(raw), corrupt=True)
            code, out, err = self.run_cli(
                "search", "--harness", "deepseek", "--verbose", deepseek_home=home
            )
            self.assertEqual(code, 0, err)
            self.assertIn("1x parse-error", err)
            # Verbose lists the raw path while exception details stay sanitized.
            self.assertIn("session-" + SESSION_BAD, err)
            self.assertIn("<session>", err)


class ServiceCompatibilityTests(FixtureTestCase):
    def _service_env(self, deepseek_home: Path) -> dict:
        empty = Path(self._temp.name) / "compat-empty"
        empty.mkdir(exist_ok=True)
        return {
            "FMS_QODER_CN_HOME": str(empty),
            "FMS_QODER_HOME": str(empty),
            "FMS_KIMI_CODE_HOME": str(empty),
            "FMS_ZCODE_HOME": str(empty),
            "FMS_CODEARTS_HOME": str(empty),
            "FMS_WORKBUDDY_HOME": str(empty),
            "FMS_WORKBUDDY_CN_HOME": str(empty),
            "FMS_CODEX_HOME": str(empty),
            "FMS_CLAUDE_HOME": str(empty),
            "FMS_CLINE_HOME": str(empty),
            "FMS_GROK_HOME": str(empty),
            "FMS_ANTIGRAVITY_HOME": str(empty),
            "FMS_ANTIGRAVITY_IDE_HOME": str(empty),
            "FMS_ANTIGRAVITY_CLI_HOME": str(empty),
            "FMS_DEEPSEEK_HOME": str(deepseek_home),
            "FMS_MINIMAX_CODE_HOME": str(empty),
            "FMS_CURSOR_HOME": str(empty),
            "FMS_QODER_CN_APP_DB": str(self.no_app_db),
            "FMS_QODER_APP_DB": str(self.no_app_db),
            "FMS_ZCODE_APP_DB": str(self.no_app_db),
            "FMS_WORKBUDDY_APP_DB": str(self.no_app_db),
            "FMS_WORKBUDDY_CN_APP_DB": str(self.no_app_db),
            "FMS_MINIMAX_CODE_APP_DB": str(self.no_app_db),
            "FMS_CURSOR_APP_DB": str(self.no_app_db),
        }

    def test_existing_callers_ignore_the_report_parameter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-compat-") as raw:
            home = _build_home(Path(raw))
            with mock.patch.dict(os.environ, self._service_env(home)):
                results = service.search_sessions((), harness=["deepseek"])
                self.assertEqual(len(results), 2)
                projects = service.list_project_paths(harness=["deepseek"])
                self.assertEqual(projects, [PROJECT])
                detail = service.load_session("deepseek:" + SESSION_ONE[:8])
                self.assertEqual(detail.summary.session_id, SESSION_ONE)

    def test_ui_endpoints_still_work(self) -> None:
        from fms_ui.server import api_response

        with tempfile.TemporaryDirectory(prefix="fms-compat-") as raw:
            home = _build_home(Path(raw))
            with mock.patch.dict(os.environ, self._service_env(home)):
                sessions = api_response("/api/sessions", {"harness": ["deepseek"], "limit": ["10"]})
                self.assertEqual(len(sessions["sessions"]), 2)
                projects = api_response("/api/projects", {"harness": ["deepseek"]})
                self.assertEqual(projects["projects"], [PROJECT])
                listing = api_response("/api/prompts", {"ref": ["deepseek:" + SESSION_ONE[:8]]})
                self.assertEqual(listing["total"], 1)
                detail = api_response("/api/session", {"ref": ["deepseek:" + SESSION_TWO[:8]], "messages": ["5"]})
                self.assertEqual(detail["session_id"], SESSION_TWO)


if __name__ == "__main__":
    unittest.main()
