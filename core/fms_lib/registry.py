from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .errors import UserError
from .harnesses.antigravity import AntigravityAdapter
from .harnesses.antigravity_cli import AntigravityCLIAdapter
from .harnesses.base import HarnessAdapter
from .harnesses.claude_code import ClaudeCodeAdapter
from .harnesses.cline import ClineAdapter
from .harnesses.codearts_agent import CodeArtsAgentAdapter
from .harnesses.codex import CodexAdapter
from .harnesses.deepseek import DeepSeekAdapter
from .harnesses.grok_build import GrokBuildAdapter
from .harnesses.kimi_code import KimiCodeAdapter
from .harnesses.minimax_code import MiniMaxCodeAdapter
from .harnesses.qoder import QoderAdapter
from .harnesses.qoder_cn import QoderCNAdapter
from .harnesses.workbuddy import WorkBuddyAdapter
from .harnesses.workbuddy_cn import WorkBuddyCNAdapter
from .harnesses.zcode import ZCodeAdapter


@dataclass(frozen=True)
class PlannedHarness:
    name: str
    aliases: Tuple[str, ...]
    variants: str
    store_hint: str


READY: Tuple[HarnessAdapter, ...] = (
    QoderCNAdapter(),
    QoderAdapter(),
    KimiCodeAdapter(),
    ZCodeAdapter(),
    CodeArtsAgentAdapter(),
    WorkBuddyAdapter(),
    WorkBuddyCNAdapter(),
    CodexAdapter(),
    DeepSeekAdapter(),
    ClaudeCodeAdapter(),
    ClineAdapter(),
    GrokBuildAdapter(),
    AntigravityAdapter(),
    AntigravityCLIAdapter(),
    MiniMaxCodeAdapter(),
)

PLANNED: Tuple[PlannedHarness, ...] = (
    PlannedHarness(
        name="codebuddy",
        aliases=("codebuddy", "codebuddy-cn"),
        variants="desktop, ide",
        store_hint="~/.codebuddy",
    ),
    PlannedHarness(
        name="cline-vscode",
        aliases=("cline-vscode",),
        variants="vscode",
        store_hint="Code globalStorage/saoudrizwan.claude-dev",
    ),
)

ALIASES: Dict[str, str] = {}
for _adapter in READY:
    for _alias in _adapter.aliases:
        ALIASES[_alias] = _adapter.name
for _planned in PLANNED:
    for _alias in _planned.aliases:
        ALIASES[_alias] = _planned.name


def ready_names() -> List[str]:
    return [adapter.name for adapter in READY]


def has_harness(name: str) -> bool:
    return name.strip().casefold() in ALIASES


def lookup_harness(name: str) -> HarnessAdapter:
    key = name.strip().casefold()
    target = ALIASES.get(key)
    if target is None:
        suggestions = difflib.get_close_matches(key, ALIASES.keys(), n=3)
        hint = ""
        if suggestions:
            hint = " Did you mean: %s?" % ", ".join(suggestions)
        raise UserError("unknown harness '%s'. Run 'fms harnesses'.%s" % (name, hint))
    for adapter in READY:
        if adapter.name == target:
            return adapter
    for planned in PLANNED:
        if planned.name == target:
            raise UserError(
                "harness '%s' is planned but not implemented yet. Ready harnesses: %s"
                % (planned.name, ", ".join(ready_names()))
            )
    raise UserError("harness '%s' is not available" % name)


def get_adapters(requested: Optional[Sequence[str]]) -> List[HarnessAdapter]:
    if not requested:
        return list(READY)
    names: Set[str] = set()
    for value in requested:
        for part in str(value).split(","):
            key = part.strip().casefold()
            if not key:
                continue
            if key in ("all", "*"):
                names.update(adapter.name for adapter in READY)
                continue
            names.add(lookup_harness(key).name)
    if not names:
        raise UserError("no harness selected")
    return [adapter for adapter in READY if adapter.name in names]


def adapter_for_path(path: Path) -> Optional[HarnessAdapter]:
    for adapter in READY:
        if adapter.owns(path):
            return adapter
    return None


def harness_rows() -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for adapter in READY:
        rows.append(
            {
                "name": adapter.name,
                "status": "ready",
                "variants": adapter.variants,
                "store": adapter.store_hint,
                "aliases": ", ".join(adapter.aliases),
            }
        )
    for planned in PLANNED:
        rows.append(
            {
                "name": planned.name,
                "status": "planned",
                "variants": planned.variants,
                "store": planned.store_hint,
                "aliases": ", ".join(planned.aliases),
            }
        )
    return rows
