from __future__ import annotations

import argparse
import json
import mimetypes
import secrets
import socketserver
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlsplit

from fms_lib import __version__
from fms_lib.errors import UserError
from fms_lib.models import SessionSummary
from fms_lib.registry import get_adapters, harness_rows
from fms_lib.service import (
    list_prompts,
    project_paths_from,
    query_summaries,
    resolve_session,
    search_sessions,
)
from fms_lib.service import (
    stats as stats_service,
)

try:
    from . import session_cache
except ImportError:  # standalone extracted layout: fms-ui puts this dir on sys.path
    import session_cache  # type: ignore

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Frontend-owned presentation limits (the shared service owns counting and
# paging; the panel decides how much to show by default).
UI_SEARCH_LIMIT_DEFAULT = 50
UI_SEARCH_LIMIT_MAX = 500
UI_MESSAGES_DEFAULT = 20
UI_MESSAGES_MAX = 100
UI_PROMPTS_OFFSET_DEFAULT = 0
UI_PROMPTS_LIMIT_DEFAULT = 20
UI_PROMPTS_LIMIT_MAX = 200
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/theme-init.js": "theme-init.js",
    "/app.js": "app.js",
    "/styles.css": "styles.css",
    "/favicon.svg": "favicon.svg",
}
STATIC_ASSET_DIRS = ("harness-logos",)


def _static_asset(path: str) -> Optional[str]:
    """Map /harness-logos/<file>.png to a build artifact without path traversal."""
    for dirname in STATIC_ASSET_DIRS:
        prefix = "/%s/" % dirname
        if not path.startswith(prefix):
            continue
        name = path[len(prefix):]
        if (
            not name.endswith(".png")
            or "/" in name
            or "\\" in name
            or not all(ch.isalnum() or ch in "-_.@" for ch in name)
        ):
            return None
        return "%s/%s" % (dirname, name)
    return None


def _parameter(params: Dict[str, List[str]], name: str, default: str = "") -> str:
    return params.get(name, [default])[0].strip()


def _integer(
    params: Dict[str, List[str]], name: str, default: int, maximum: int
) -> int:
    raw = _parameter(params, name, str(default))
    try:
        value = int(raw)
    except ValueError:
        raise ValueError("%s must be an integer" % name)
    if value < 0 or (maximum and value > maximum):
        raise ValueError("%s must be between 0 and %d" % (name, maximum))
    return value


def _boolean(params: Dict[str, List[str]], name: str) -> bool:
    raw = _parameter(params, name, "false").casefold()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off", ""):
        return False
    raise ValueError("%s must be true or false" % name)


def _required_ref(params: Dict[str, List[str]]) -> str:
    ref = _parameter(params, "ref")
    if not ref:
        raise ValueError("ref is required")
    return ref


def _cache_result(params: Dict[str, List[str]]):
    """Serve the shared snapshot, honoring refresh/revision/wait coordination."""
    return session_cache.get_cache().serve(
        refresh=_boolean(params, "refresh"),
        revision=_integer(params, "revision", 0, 0),
        wait=_boolean(params, "wait"),
    )


def _harness_summaries(
    snapshot: List[SessionSummary], harness: Optional[List[str]]
) -> List[SessionSummary]:
    if not harness:
        return list(snapshot)
    wanted = {adapter.name for adapter in get_adapters(harness)}
    return [summary for summary in snapshot if summary.harness in wanted]


def api_response(path: str, params: Dict[str, List[str]]) -> object:
    if path == "/api/harnesses":
        return {"harnesses": harness_rows()}
    if path == "/api/projects":
        snapshot, revision, refreshing = _cache_result(params)
        summaries = _harness_summaries(snapshot, params.get("harness"))
        return {
            "projects": project_paths_from(
                summaries, include_archived=_boolean(params, "archived")
            ),
            "revision": revision,
            "refreshing": refreshing,
        }
    if path == "/api/sessions":
        query = _parameter(params, "query")
        limit = _integer(params, "limit", UI_SEARCH_LIMIT_DEFAULT, UI_SEARCH_LIMIT_MAX)
        include_archived = _boolean(params, "archived")
        if _boolean(params, "deep"):
            sessions = search_sessions(
                [query] if query else [],
                harness=params.get("harness"),
                cwd=_parameter(params, "cwd") or None,
                since=_parameter(params, "since") or None,
                limit=limit,
                deep=True,
                include_archived=include_archived,
            )
            return {"sessions": [session.to_dict() for session in sessions]}
        snapshot, revision, refreshing = _cache_result(params)
        summaries = _harness_summaries(snapshot, params.get("harness"))
        sessions = query_summaries(
            summaries,
            [query] if query else [],
            cwd=_parameter(params, "cwd") or None,
            since=_parameter(params, "since") or None,
            limit=limit,
            include_archived=include_archived,
        )
        return {
            "sessions": [session.to_dict() for session in sessions],
            "revision": revision,
            "refreshing": refreshing,
        }
    if path == "/api/stats":
        return {
            "stats": stats_service(
                harness=params.get("harness"),
                cwd=_parameter(params, "cwd") or None,
                since=_parameter(params, "since") or None,
                include_archived=_boolean(params, "archived"),
            )
        }
    if path == "/api/session":
        adapter, summary = resolve_session(
            _required_ref(params), get_adapters(None)
        )
        detail = adapter.load(summary)
        payload = detail.to_dict(
            max_exchanges=_integer(params, "messages", UI_MESSAGES_DEFAULT, UI_MESSAGES_MAX)
        )
        payload["resume_argv"] = adapter.resume_argv(summary)
        return payload
    if path == "/api/prompts":
        order = _parameter(params, "order", "oldest")
        if order not in ("oldest", "newest"):
            raise ValueError("order must be oldest or newest")
        listing = list_prompts(
            _required_ref(params),
            offset=_integer(
                params, "offset", UI_PROMPTS_OFFSET_DEFAULT, UI_PROMPTS_OFFSET_DEFAULT
            ),
            limit=_integer(
                params, "limit", UI_PROMPTS_LIMIT_DEFAULT, UI_PROMPTS_LIMIT_MAX
            ),
            order=order,
        )
        return listing.to_dict()
    raise UserError("not found")


class UIRequestHandler(BaseHTTPRequestHandler):
    server_version = "FindMySessionUI/" + __version__

    def _send_bytes(
        self, status: int, content_type: str, body: bytes, cache: bool = False
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, data: object) -> None:
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self._send_bytes(status, "application/json; charset=utf-8", body)

    def _valid_host(self) -> bool:
        host_header = self.headers.get("Host", "")
        # Reject userinfo tricks like "evil.example@127.0.0.1" and match the
        # full authority (host plus port), not just the parsed hostname.
        if not host_header or "@" in host_header:
            return False
        if host_header.startswith("["):
            end = host_header.find("]")
            if end == -1:
                return False
            host = host_header[: end + 1]
            rest = host_header[end + 1 :]
        else:
            host, _, port = host_header.partition(":")
            rest = ":" + port if port else ""
        if host not in ("127.0.0.1", "localhost", "[::1]"):
            return False
        if rest:
            if not rest.startswith(":"):
                return False
            port = rest[1:]
            if not port.isdigit() or int(port) != self.server.server_port:
                return False
        return True

    def _allowed_origins(self) -> set:
        port = self.server.server_port
        return {
            "http://127.0.0.1:%d" % port,
            "http://localhost:%d" % port,
            "http://[::1]:%d" % port,
        }

    def _api_auth_error(self) -> Optional[tuple]:
        """Return (status, message) when an API request is not authorized."""
        origin = self.headers.get("Origin")
        if origin is not None and origin not in self._allowed_origins():
            return (403, "forbidden origin")
        fetch_site = self.headers.get("Sec-Fetch-Site")
        if fetch_site is not None and fetch_site not in ("same-origin", "none"):
            return (403, "forbidden cross-site request")
        token = self.headers.get("X-FMS-Token", "")
        expected = getattr(self.server, "auth_token", "")
        if not expected or not secrets.compare_digest(
            token.encode("utf-8"), expected.encode("utf-8")
        ):
            return (401, "unauthorized")
        return None

    def do_GET(self) -> None:
        if not self._valid_host():
            self._send_json(403, {"error": "forbidden host"})
            return
        parsed = urlsplit(self.path)
        if parsed.path.startswith("/api/"):
            auth_error = self._api_auth_error()
            if auth_error is not None:
                status, message = auth_error
                self._send_json(status, {"error": message})
                return
            try:
                data = api_response(parsed.path, parse_qs(parsed.query))
            except UserError as exc:
                status = 404 if str(exc) == "not found" else 400
                self._send_json(status, {"error": str(exc)})
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except session_cache.ScanError as exc:
                self._send_json(500, {"error": str(exc)})
            except OSError:
                self._send_json(500, {"error": "cannot read session store"})
            except Exception:
                self._send_json(500, {"error": "internal server error"})
            else:
                self._send_json(200, data)
            return
        filename = STATIC_FILES.get(parsed.path) or _static_asset(parsed.path)
        if filename is None:
            self._send_json(404, {"error": "not found"})
            return
        try:
            body = (STATIC_DIR / filename).read_bytes()
        except OSError:
            self._send_json(404, {"error": "not found"})
            return
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"
        self._send_bytes(200, content_type, body, cache=filename == "favicon.svg")

    def do_POST(self) -> None:
        self._send_json(405, {"error": "method not allowed"})

    def do_HEAD(self) -> None:
        self._send_bytes(405, "application/json; charset=utf-8", b"")

    def do_OPTIONS(self) -> None:
        self._send_json(405, {"error": "method not allowed"})

    def log_message(self, format: str, *args: object) -> None:
        return


class LocalHTTPServer(ThreadingHTTPServer):
    auth_token: str = ""

    def server_bind(self) -> None:
        # Skip the reverse-DNS lookup in the base class: on some CI hosts it
        # blocks for many seconds, delaying startup past client timeouts.
        socketserver.TCPServer.server_bind(self)
        host = self.server_address[0]
        if isinstance(host, (bytes, bytearray)):
            host = bytes(host).decode("ascii", "replace")
        self.server_name = host
        self.server_port = self.server_address[1]


def create_server(port: int = 8765) -> LocalHTTPServer:
    server = LocalHTTPServer(("127.0.0.1", port), UIRequestHandler)
    server.auth_token = secrets.token_urlsafe(32)
    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fms-ui",
        description="Open the local, read-only Find My Session browser panel.",
    )
    parser.add_argument("--version", action="version", version="fms-ui " + __version__)
    parser.add_argument("--port", type=int, default=8765, help="local port (default: 8765)")
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open the panel automatically"
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.port < 0 or args.port > 65535:
        print("fms-ui: port must be between 0 and 65535", file=sys.stderr)
        return 2
    try:
        server = create_server(args.port)
    except OSError as exc:
        print("fms-ui: cannot start local server: %s" % exc, file=sys.stderr)
        return 2
    session_cache.start_background_maintenance()
    url = "http://127.0.0.1:%d/?token=%s" % (
        server.server_address[1],
        server.auth_token,
    )
    print("Find My Session: %s" % url)
    print("Read-only local panel. Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
