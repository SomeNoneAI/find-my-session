from __future__ import annotations

import http.client
import io
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock
from urllib.parse import urlencode

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = REPO_ROOT / "core"
UI_ENTRYPOINT = REPO_ROOT / "fms_ui" / "fms-ui"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(CORE_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from claude_code_fixture import build_claude_code_home  # noqa: E402
from opencode_fixture import build_opencode_home  # noqa: E402

from fms_lib import __version__  # noqa: E402
from fms_ui import server as server_module  # noqa: E402
from fms_ui.server import create_server  # noqa: E402


def synthetic_environment(root: Path) -> dict:
    empty = root / "empty"
    empty.mkdir(parents=True, exist_ok=True)
    missing_db = empty / "missing.sqlite"
    return {
        "FMS_QODER_CN_HOME": str(root / "qoder-cn-home"),
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
        "FMS_DEEPSEEK_HOME": str(empty),
        "FMS_MINIMAX_CODE_HOME": str(empty),
        "FMS_CURSOR_HOME": str(empty),
        "FMS_OPENCODE_HOME": str(empty),
        "FMS_GEMINI_CLI_HOME": str(empty),
        "FMS_QWEN_HOME": str(empty),
        "FMS_PI_HOME": str(empty),
        "PI_CODING_AGENT_SESSION_DIR": "",
        "FMS_QODER_CN_APP_DB": str(missing_db),
        "FMS_QODER_APP_DB": str(missing_db),
        "FMS_ZCODE_APP_DB": str(missing_db),
        "FMS_WORKBUDDY_APP_DB": str(missing_db),
        "FMS_WORKBUDDY_CN_APP_DB": str(missing_db),
        "FMS_MINIMAX_CODE_APP_DB": str(missing_db),
        "FMS_CURSOR_APP_DB": str(missing_db),
    }


class UITestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory(prefix="fms-ui-tests-")
        cls.root = Path(cls._temp.name)
        cls.opencode_home = build_opencode_home(cls.root / "opencode-home")
        cls.claude_home = build_claude_code_home(cls.root / "claude-home")
        cls.home = shutil.copytree(
            REPO_ROOT / "tests" / "fixtures" / "qoder-cn-home",
            cls.root / "qoder-cn-home",
        )
        cls.environment = synthetic_environment(cls.root)
        cls.environment["FMS_OPENCODE_HOME"] = str(cls.opencode_home)
        cls.environment["FMS_CLAUDE_HOME"] = str(cls.claude_home)
        cls._environment_patch = mock.patch.dict(os.environ, cls.environment)
        cls._environment_patch.start()
        cls.server = create_server(0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls._environment_patch.stop()
        cls._temp.cleanup()

    def request(self, path: str, host: str = None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": host} if host else {}
        try:
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            body = response.read()
            return response.status, dict(response.getheaders()), body
        finally:
            connection.close()

    def request_json(self, path: str, host: str = None):
        status, headers, body = self.request(path, host=host)
        return status, headers, json.loads(body)

    def search(self, **params) -> list:
        values = {"harness": "qoder-cn", "limit": 50}
        values.update(params)
        status, _, data = self.request_json("/api/sessions?" + urlencode(values))
        self.assertEqual(status, 200, data)
        return data["sessions"]


class UIStatsTests(UITestCase):
    def test_stats_endpoint_aggregates_recorded_usage(self) -> None:
        status, _, data = self.request_json("/api/stats?" + urlencode({"harness": "opencode"}))
        self.assertEqual(status, 200, data)
        rows = data["stats"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["harness"], "opencode")
        self.assertEqual(rows[0]["sessions"], 4)
        self.assertEqual(rows[0]["sessions_with_usage"], 2)
        self.assertEqual(rows[0]["tokens_input"], 1800)
        self.assertAlmostEqual(rows[0]["cost_usd"], 0.5)
        self.assertNotIn("resume_argv", rows[0])

    def test_stats_endpoint_marks_unrecorded_harnesses(self) -> None:
        status, _, data = self.request_json("/api/stats?" + urlencode({"harness": "qoder-cn"}))
        self.assertEqual(status, 200, data)
        rows = data["stats"]
        self.assertEqual(rows[0]["harness"], "qoder-cn")
        self.assertGreater(rows[0]["sessions"], 0)
        self.assertEqual(rows[0]["sessions_with_usage"], 0)
        self.assertIsNone(rows[0]["tokens_input"])
        self.assertIsNone(rows[0]["cost_usd"])

    def test_session_detail_includes_resume_argv(self) -> None:
        session = self.search(harness="claude-code", limit=1)[0]
        status, _, data = self.request_json("/api/session?" + urlencode({"ref": session["ref"]}))
        self.assertEqual(status, 200, data)
        self.assertEqual(
            data["resume_argv"],
            ["claude", "--resume", session["session_id"]],
        )

    def test_session_detail_resume_argv_null_without_mapping(self) -> None:
        session = self.search(harness="qoder-cn", limit=1)[0]
        status, _, data = self.request_json("/api/session?" + urlencode({"ref": session["ref"]}))
        self.assertEqual(status, 200, data)
        self.assertIsNone(data["resume_argv"])


class UIApiTests(UITestCase):
    def test_static_assets_and_security_headers(self) -> None:
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Find My Session", body)
        self.assertIn(b"/app.js", body)
        self.assertIn(b"/styles.css", body)
        self.assertIn(b"/theme-init.js", body)
        self.assertNotIn(b"i18n.js", body)
        self.assertNotIn(b"projects.js", body)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Cache-Control"], "no-store")

        for asset in ("/app.js", "/styles.css", "/theme-init.js", "/favicon.svg"):
            status, headers, body = self.request(asset)
            self.assertEqual(status, 200, asset)
            self.assertTrue(body)

        status, _, data = self.request_json("/api/not-found")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"], "not found")

        status, _, data = self.request_json("/%2e%2e/core/fms_lib/models.py")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"], "not found")

    def test_built_frontend_is_self_contained(self) -> None:
        html = (REPO_ROOT / "fms_ui" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("eval", html)

    def test_harnesses_and_session_filters(self) -> None:
        status, _, data = self.request_json("/api/harnesses")
        self.assertEqual(status, 200)
        self.assertTrue(any(row["name"] == "qoder-cn" for row in data["harnesses"]))

        sessions = self.search()
        self.assertTrue(sessions)
        self.assertTrue(all(row["harness"] == "qoder-cn" for row in sessions))
        self.assertTrue(all(not row["archived"] for row in sessions))
        self.assertEqual(self.search(query="no-such-session-topic"), [])

        included = self.search(archived="true")
        self.assertGreaterEqual(len(included), len(sessions))

    def test_project_listing_comes_from_sessions(self) -> None:
        sessions = self.search()
        expected = sorted({session["cwd"] for session in sessions if session["cwd"]})
        status, _, data = self.request_json("/api/projects?harness=qoder-cn")
        self.assertEqual(status, 200, data)
        self.assertEqual(data["projects"], expected)
        self.assertNotIn("", data["projects"])

        status, _, included = self.request_json(
            "/api/projects?harness=qoder-cn&archived=true"
        )
        self.assertEqual(status, 200, included)
        self.assertLessEqual(set(expected), set(included["projects"]))

    def test_detail_and_prompt_pages(self) -> None:
        sessions = self.search()
        selected = None
        listing = None
        for session in sessions:
            ref = session["ref"]
            status, _, candidate = self.request_json(
                "/api/prompts?" + urlencode({"ref": ref, "limit": 1})
            )
            self.assertEqual(status, 200, candidate)
            if candidate["total"] >= 2:
                selected = ref
                listing = candidate
                break
        self.assertIsNotNone(selected)
        self.assertTrue(listing["has_more"])
        self.assertEqual(listing["returned"], 1)
        self.assertEqual(listing["prompts"][0]["index"], 1)

        status, _, second = self.request_json(
            "/api/prompts?" + urlencode({"ref": selected, "limit": 1, "offset": 1})
        )
        self.assertEqual(status, 200, second)
        self.assertEqual(second["prompts"][0]["index"], 2)
        self.assertNotEqual(
            listing["prompts"][0]["text"], second["prompts"][0]["text"]
        )

        status, _, detail = self.request_json(
            "/api/session?" + urlencode({"ref": selected, "messages": 2})
        )
        self.assertEqual(status, 200, detail)
        self.assertEqual(detail["ref"], selected)
        self.assertLessEqual(len(detail["exchanges"]), 2)

    def test_invalid_requests_and_host_protection(self) -> None:
        for path in (
            "/api/sessions?limit=-1",
            "/api/sessions?limit=abc",
            "/api/sessions?deep=perhaps",
            "/api/session",
            "/api/prompts?ref=qoder-cn:a1b2c3d4&order=sideways",
        ):
            status, _, data = self.request_json(path)
            self.assertEqual(status, 400, path)
            self.assertTrue(data["error"])

        status, _, data = self.request_json("/api/unknown")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"], "not found")

        for host in ("evil.example", "[::1"):
            status, _, data = self.request_json("/api/harnesses", host=host)
            self.assertEqual(status, 403, host)
            self.assertEqual(data["error"], "forbidden host")

    def test_missing_static_asset_is_not_found(self) -> None:
        with mock.patch.object(server_module, "STATIC_DIR", self.root / "empty"):
            status, _, data = self.request_json("/app.js")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"], "not found")

    def test_requests_do_not_modify_session_store(self) -> None:
        def snapshot() -> dict:
            return {
                str(path): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.home.rglob("*")
                if path.is_file()
            }

        before = snapshot()
        sessions = self.search()
        ref = sessions[0]["ref"]
        self.request_json("/api/session?" + urlencode({"ref": ref}))
        self.request_json("/api/prompts?" + urlencode({"ref": ref, "limit": 1}))
        self.assertEqual(snapshot(), before)


class UIEntrypointTests(unittest.TestCase):
    def test_version_and_executable_bit(self) -> None:
        argv = [str(UI_ENTRYPOINT)]
        if os.name == "nt":
            argv = [sys.executable, str(UI_ENTRYPOINT)]
        result = subprocess.run([*argv, "--version"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "fms-ui " + __version__)
        if os.name != "nt":
            self.assertTrue(os.access(UI_ENTRYPOINT, os.X_OK))


class UIServerStartupTests(unittest.TestCase):
    def test_create_server_skips_reverse_dns(self) -> None:
        with mock.patch(
            "socket.getfqdn", side_effect=AssertionError("reverse DNS lookup")
        ):
            server = create_server(0)
            try:
                self.assertEqual(server.server_name, "127.0.0.1")
                self.assertGreater(server.server_port, 0)
            finally:
                server.server_close()


class UIServerMainTests(unittest.TestCase):
    def test_main_rejects_out_of_range_port(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = server_module.main(["--port", "70000"])
        self.assertEqual(code, 2)
        self.assertIn("between 0 and 65535", stderr.getvalue())

    def test_main_reports_bind_failure(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(
            server_module, "create_server", side_effect=OSError("address in use")
        ), redirect_stderr(stderr):
            code = server_module.main(["--port", "8765"])
        self.assertEqual(code, 2)
        self.assertIn("cannot start local server: address in use", stderr.getvalue())

    def test_main_serves_and_closes_on_interrupt(self) -> None:
        server = mock.Mock()
        server.server_address = ("127.0.0.1", 43210)
        server.serve_forever.side_effect = KeyboardInterrupt
        stdout = io.StringIO()
        with mock.patch.object(
            server_module, "create_server", return_value=server
        ), mock.patch.object(
            server_module.session_cache, "start_background_maintenance"
        ), redirect_stdout(stdout):
            code = server_module.main(["--no-browser", "--port", "0"])
        self.assertEqual(code, 0)
        self.assertIn("http://127.0.0.1:43210/", stdout.getvalue())
        server.server_close.assert_called_once()

    def test_main_opens_browser_unless_disabled(self) -> None:
        server = mock.Mock()
        server.server_address = ("127.0.0.1", 43211)
        server.serve_forever.side_effect = KeyboardInterrupt
        timer = mock.Mock()
        with mock.patch.object(
            server_module, "create_server", return_value=server
        ), mock.patch.object(
            server_module.session_cache, "start_background_maintenance"
        ), mock.patch.object(
            server_module.threading, "Timer", return_value=timer
        ) as timer_class, redirect_stdout(io.StringIO()):
            code = server_module.main(["--port", "0"])
        self.assertEqual(code, 0)
        self.assertEqual(timer_class.call_args.args[0], 0.4)
        timer.start.assert_called_once()


class ArtifactBuildTests(unittest.TestCase):
    def test_skill_and_ui_artifacts_run_independently(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fms-artifacts-") as raw:
            root = Path(raw)
            output = root / "dist"
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "tools" / "build_artifacts.py"),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            skill_archive = output / "find-my-session-skill.zip"
            ui_archive = output / "find-my-session-ui.zip"
            self.assertTrue(skill_archive.is_file())
            self.assertTrue(ui_archive.is_file())
            with zipfile.ZipFile(skill_archive) as archive:
                self.assertIn("SKILL.md", archive.namelist())
                self.assertIn("scripts/fms_lib/service.py", archive.namelist())
            with zipfile.ZipFile(ui_archive) as archive:
                self.assertIn("static/index.html", archive.namelist())
                self.assertIn("fms_lib/service.py", archive.namelist())

            shutil.copytree(
                REPO_ROOT / "tests" / "fixtures" / "qoder-cn-home",
                root / "qoder-cn-home",
            )
            environment = dict(os.environ)
            environment.update(synthetic_environment(root))
            skill_fms = output / "find-my-session-skill" / "scripts" / "fms"
            skill_argv = [str(skill_fms)]
            if os.name == "nt":
                skill_argv = [sys.executable, str(skill_fms)]
            result = subprocess.run(
                [*skill_argv, "search", "--harness", "qoder-cn", "--json"],
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout))

            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            environment["PYTHONUNBUFFERED"] = "1"
            ui_argv = [str(output / "find-my-session-ui" / "fms-ui")]
            if os.name == "nt":
                ui_argv = [sys.executable, *ui_argv]
            process = subprocess.Popen(
                [
                    *ui_argv,
                    "--no-browser",
                    "--port",
                    str(port),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            )
            try:
                lines: "queue.Queue[str]" = queue.Queue()
                threading.Thread(
                    target=lambda: lines.put(process.stdout.readline()),
                    daemon=True,
                ).start()
                try:
                    first_line = lines.get(timeout=10)
                except queue.Empty:
                    self.fail("built UI did not start")
                if not first_line:
                    self.fail("built UI exited: " + process.stderr.read())
                self.assertIn(
                    "Find My Session: http://127.0.0.1:%d/" % port,
                    first_line,
                )
                self.assertIsNone(process.poll())
            finally:
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()


if __name__ == "__main__":
    unittest.main()
