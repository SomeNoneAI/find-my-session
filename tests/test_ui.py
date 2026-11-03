from __future__ import annotations

import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from urllib.parse import urlencode

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = REPO_ROOT / "core"
UI_ENTRYPOINT = REPO_ROOT / "ui" / "fms-ui"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(CORE_DIR))

from fms_lib import __version__  # noqa: E402
from ui.server import create_server  # noqa: E402


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
        "FMS_QODER_CN_APP_DB": str(missing_db),
        "FMS_QODER_APP_DB": str(missing_db),
        "FMS_ZCODE_APP_DB": str(missing_db),
        "FMS_WORKBUDDY_APP_DB": str(missing_db),
        "FMS_WORKBUDDY_CN_APP_DB": str(missing_db),
    }


class UITestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory(prefix="fms-ui-tests-")
        cls.root = Path(cls._temp.name)
        cls.home = shutil.copytree(
            REPO_ROOT / "tests" / "fixtures" / "qoder-cn-home",
            cls.root / "qoder-cn-home",
        )
        cls.environment = synthetic_environment(cls.root)
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
        html = (REPO_ROOT / "ui" / "static" / "index.html").read_text(encoding="utf-8")
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
            "/api/sessions?deep=perhaps",
            "/api/session",
            "/api/prompts?ref=qoder-cn:a1b2c3d4&order=sideways",
        ):
            status, _, data = self.request_json(path)
            self.assertEqual(status, 400, path)
            self.assertTrue(data["error"])

        status, _, data = self.request_json("/api/harnesses", host="evil.example")
        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "forbidden host")

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
        result = subprocess.run(
            [str(UI_ENTRYPOINT), "--version"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "fms-ui " + __version__)
        if os.name != "nt":
            self.assertTrue(os.access(UI_ENTRYPOINT, os.X_OK))


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
            result = subprocess.run(
                [str(skill_fms), "search", "--harness", "qoder-cn", "--json"],
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout))

            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            process = subprocess.Popen(
                [
                    str(output / "find-my-session-ui" / "fms-ui"),
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
                deadline = time.monotonic() + 10
                while True:
                    if process.poll() is not None:
                        self.fail("built UI exited: " + process.stderr.read())
                    try:
                        connection = http.client.HTTPConnection(
                            "127.0.0.1", port, timeout=1
                        )
                        connection.request("GET", "/api/sessions?harness=qoder-cn")
                        response = connection.getresponse()
                        payload = json.loads(response.read())
                        connection.close()
                        self.assertEqual(response.status, 200, payload)
                        self.assertTrue(payload["sessions"])
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            self.fail("built UI did not start")
                        time.sleep(0.05)
            finally:
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()


if __name__ == "__main__":
    unittest.main()
