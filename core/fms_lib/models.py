from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .util import to_iso


@dataclass
class ToolCall:
    name: str
    detail: str = ""
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "detail": self.detail,
            "timestamp": to_iso(self.timestamp),
        }


@dataclass
class Exchange:
    user_text: str = ""
    timestamp: Optional[datetime] = None
    assistant_texts: List[str] = field(default_factory=list)
    tools: List[ToolCall] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user": self.user_text,
            "timestamp": to_iso(self.timestamp),
            "assistant": self.assistant_texts,
            "tools": [tool.to_dict() for tool in self.tools],
        }


@dataclass
class SessionSummary:
    harness: str
    session_id: str
    path: Path
    cwd: str
    updated: datetime
    title: str
    first_prompt: str = ""
    last_prompt: str = ""
    started: Optional[datetime] = None
    branch: str = ""
    model: str = ""
    entrypoint: str = ""
    version: str = ""
    size: int = 0
    variants: str = ""
    archived: bool = False
    ref_id: str = ""

    @property
    def ref(self) -> str:
        base = self.ref_id or self.session_id
        return "%s:%s" % (self.harness, base[:8])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ref": self.ref,
            "harness": self.harness,
            "session_id": self.session_id,
            "path": str(self.path),
            "cwd": self.cwd,
            "title": self.title,
            "first_prompt": self.first_prompt,
            "last_prompt": self.last_prompt,
            "started": to_iso(self.started),
            "updated": to_iso(self.updated),
            "branch": self.branch,
            "model": self.model,
            "entrypoint": self.entrypoint,
            "version": self.version,
            "size_bytes": self.size,
            "variants": self.variants,
            "archived": self.archived,
        }


@dataclass
class UserPrompt:
    text: str
    timestamp: Optional[datetime] = None


@dataclass
class PromptListing:
    summary: SessionSummary
    prompts: List[Tuple[int, UserPrompt]] = field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 0
    order: str = "oldest"
    has_more: bool = False
    count_only: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "ref": self.summary.ref,
            "harness": self.summary.harness,
            "session_id": self.summary.session_id,
            "path": str(self.summary.path),
            "cwd": self.summary.cwd,
            "archived": self.summary.archived,
            "total": self.total,
        }
        if self.count_only:
            return data
        data.update(
            {
                "offset": self.offset,
                "limit": self.limit,
                "order": self.order,
                "returned": len(self.prompts),
                "has_more": self.has_more,
                "prompts": [
                    {
                        "index": index,
                        "timestamp": to_iso(prompt.timestamp),
                        "text": prompt.text,
                    }
                    for index, prompt in self.prompts
                ],
            }
        )
        return data


@dataclass
class SessionDetail:
    summary: SessionSummary
    compact_summary: str = ""
    todos: List[Dict[str, Any]] = field(default_factory=list)
    exchanges: List[Exchange] = field(default_factory=list)
    edited_files: List[Dict[str, Any]] = field(default_factory=list)
    tool_counts: Dict[str, int] = field(default_factory=dict)
    recent_tools: List[ToolCall] = field(default_factory=list)
    turn_count: int = 0

    def to_dict(self, max_exchanges: int = 10) -> Dict[str, Any]:
        exchanges = self.exchanges
        if max_exchanges >= 0:
            exchanges = exchanges[-max_exchanges:] if max_exchanges else []
        data = self.summary.to_dict()
        data.update(
            {
                "compact_summary": self.compact_summary,
                "todos": self.todos,
                "turn_count": self.turn_count,
                "exchanges": [exchange.to_dict() for exchange in exchanges],
                "edited_files": self.edited_files,
                "tool_counts": self.tool_counts,
                "recent_tools": [tool.to_dict() for tool in self.recent_tools[-5:]],
            }
        )
        return data
