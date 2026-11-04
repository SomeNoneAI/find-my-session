"""Model Context Protocol server for find-my-session.

``fms mcp`` speaks the MCP stdio transport: one JSON-RPC 2.0 message per
line on stdin/stdout. It exposes the read-only fms surface as MCP tools so
MCP-native hosts can search, inspect, and hand off agent sessions without
shelling out. The write side of the CLI does not exist, so there is no
write tool to worry about: every tool maps to a read-only service call.

Implemented against the MCP schema revisions "2025-06-18" and
"2024-11-05"; a client proposing another revision gets the newest one we
support.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from .errors import UserError
from .registry import harness_rows
from .render import json_dump, render_prompts_json
from .service import (
    doctor,
    list_prompts,
    load_session,
    search_sessions,
)
from .service import (
    stats as stats_service,
)

SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2024-11-05")
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

_SERVER_INFO = {"name": "find-my-session", "version": __version__}

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "harnesses",
        "description": (
            "List supported and planned coding-agent harnesses with their "
            "variants, store locations, and aliases."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_sessions",
        "description": (
            "Search sessions across coding-agent stores by fuzzy keywords or "
            "metadata filters. Returns session summaries with refs, titles, "
            "cwd, and timestamps — never transcript content."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Fuzzy keywords; every keyword must match.",
                },
                "harness": {
                    "type": "string",
                    "description": "Restrict to one harness name or alias.",
                },
                "cwd": {"type": "string", "description": "Working-directory filter."},
                "since": {
                    "type": "string",
                    "description": "Only sessions updated since this time (7d, 24h, 2026-10-01).",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Max results; 0 means no limit (default 10).",
                },
                "deep": {
                    "type": "boolean",
                    "description": "Also scan full transcripts (slower).",
                },
                "include_archived": {"type": "boolean"},
            },
        },
    },
    {
        "name": "latest_session",
        "description": "Return the most recent matching session summary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "harness": {"type": "string"},
                "cwd": {"type": "string"},
                "since": {"type": "string"},
            },
        },
    },
    {
        "name": "show_session",
        "description": (
            "Low-token handoff digest for one session: task, latest request, "
            "compaction summary, todos, recent turns, and tools."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Session ref (harness:prefix) or transcript path.",
                },
                "messages": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Recent user/assistant turns to include (default 2).",
                },
                "chars": {"type": "integer", "minimum": 0},
            },
            "required": ["ref"],
        },
    },
    {
        "name": "session_prompts",
        "description": (
            "List every human-authored prompt in one session, with count and "
            "paging; excludes tool results, sidechains, and injected content."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "limit": {"type": "integer", "minimum": 0},
                "offset": {"type": "integer", "minimum": 0},
                "order": {"type": "string", "enum": ["oldest", "newest"]},
                "chars": {"type": "integer", "minimum": 0},
            },
            "required": ["ref"],
        },
    },
    {
        "name": "usage_stats",
        "description": (
            "Per-harness token and cost totals from the usage data the "
            "harness apps themselves record; null totals mean not recorded."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "harness": {"type": "string"},
                "cwd": {"type": "string"},
                "since": {"type": "string"},
                "include_archived": {"type": "boolean"},
            },
        },
    },
    {
        "name": "doctor",
        "description": (
            "Diagnose store readability per harness without reading session "
            "content: candidate/readable/skipped counts and sanitized issues."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "harness": {"type": "string"},
                "fingerprint": {
                    "type": "boolean",
                    "description": "Add the content-free shape summary per store.",
                },
            },
        },
    },
]


def _text_result(text: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _error_result(message: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _clean_kwargs(arguments: Dict[str, Any], keys: Sequence[str]) -> Dict[str, Any]:
    return {key: arguments[key] for key in keys if key in arguments}


def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Run one MCP tool and return its tool result mapping."""

    try:
        if name == "harnesses":
            return _text_result(json_dump(harness_rows()))
        if name == "search_sessions":
            kwargs = _clean_kwargs(
                arguments, ("cwd", "since", "limit", "deep", "include_archived")
            )
            harness = arguments.get("harness")
            results = search_sessions(
                query=arguments.get("query") or (),
                harness=[harness] if harness else None,
                **kwargs,
            )
            return _text_result(json_dump([s.to_dict() for s in results]))
        if name == "latest_session":
            kwargs = _clean_kwargs(arguments, ("cwd", "since"))
            harness = arguments.get("harness")
            results = search_sessions(
                latest=True, harness=[harness] if harness else None, **kwargs
            )
            return _text_result(
                json_dump(results[0].to_dict() if results else None)
            )
        if name == "show_session":
            detail = load_session(
                str(arguments["ref"]),
                harness=[arguments["harness"]] if arguments.get("harness") else None,
            )
            return _text_result(
                json_dump(
                    detail.to_dict(
                        max_exchanges=10,
                    )
                )
            )
        if name == "session_prompts":
            listing = list_prompts(
                str(arguments["ref"]),
                harness=[arguments["harness"]] if arguments.get("harness") else None,
                offset=int(arguments.get("offset") or 0),
                limit=int(arguments.get("limit") or 0),
                order=arguments.get("order") or "oldest",
                count_only=False,
            )
            return _text_result(
                render_prompts_json(listing, int(arguments.get("chars") or 0))
            )
        if name == "usage_stats":
            kwargs = _clean_kwargs(arguments, ("cwd", "since", "include_archived"))
            harness = arguments.get("harness")
            return _text_result(
                json_dump(
                    stats_service(
                        harness=[harness] if harness else None, **kwargs
                    )
                )
            )
        if name == "doctor":
            payload = doctor(
                harness=[arguments["harness"]] if arguments.get("harness") else None,
                fingerprint=bool(arguments.get("fingerprint")),
            )
            return _text_result(json_dump(payload))
    except (UserError, ValueError, OSError) as exc:
        return _error_result(str(exc))
    raise LookupError("unknown tool: %s" % name)


def handle_message(message: Any) -> Optional[Dict[str, Any]]:
    """Handle one decoded JSON-RPC message; None for notifications."""

    if not isinstance(message, dict):
        return _error_response(None, -32600, "Invalid request")
    method = message.get("method")
    request_id = message.get("id")
    if method is None:
        if request_id is not None:
            return _error_response(request_id, -32600, "Invalid request")
        return None
    params = message.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    if method == "initialize":
        requested = str(params.get("protocolVersion") or "")
        negotiated = (
            requested if requested in SUPPORTED_PROTOCOL_VERSIONS
            else LATEST_PROTOCOL_VERSION
        )
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": negotiated,
                "capabilities": {"tools": {}},
                "serverInfo": dict(_SERVER_INFO),
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": TOOL_DEFINITIONS},
        }
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        try:
            result = call_tool(name, arguments)
        except LookupError:
            return _error_response(
                request_id, -32602, "Unknown tool: %s" % name
            )
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    if request_id is not None:
        return _error_response(request_id, -32601, "Method not found: %s" % method)
    return None


def _error_response(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def serve(stdin: Any = None, stdout: Any = None) -> int:
    """Read newline-delimited JSON-RPC messages until EOF."""

    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            response: Optional[Dict[str, Any]] = _error_response(
                None, -32700, "Parse error"
            )
        else:
            response = handle_message(message)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()
    return 0
