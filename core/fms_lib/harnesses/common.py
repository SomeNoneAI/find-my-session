"""Format-neutral helpers shared by harness adapters.

Adapters keep their own store-specific parsing, but prompt classification,
title selection, tool-call detail, and edited-file extraction follow the same
rules everywhere. Key tuples stay in the adapters because they encode each
product's field names.
"""

from __future__ import annotations

import os
import re
from typing import AbstractSet, Any, Mapping, Sequence

from ..util import one_line

GENERIC_PROMPTS = frozenset(
    {
        "continue",
        "go on",
        "keep going",
        "next",
        "ok",
        "yes",
        "继续",
        "接着",
        "继续吧",
        "好的",
        "好",
        "下一步",
        "?",
        "？",
    }
)

FILE_KEYS = ("file_path", "notebook_path", "path", "target_file")


def is_generic(
    value: str, generic_prompts: AbstractSet[str] = GENERIC_PROMPTS
) -> bool:
    compact = re.sub(r"\s+", " ", value).strip().casefold()
    if not compact or len(compact) <= 1:
        return True
    if re.fullmatch(r"[\d\W_]+", compact):
        return True
    return compact in generic_prompts


def choose_title(
    first_prompt: str,
    last_prompt: str,
    generic_prompts: AbstractSet[str] = GENERIC_PROMPTS,
) -> str:
    for candidate in (last_prompt, first_prompt):
        if candidate and not is_generic(candidate, generic_prompts):
            return one_line(candidate, 100)
    return one_line(last_prompt or first_prompt, 100)


def file_path(
    arguments: Any, cwd: str, keys: Sequence[str] = FILE_KEYS
) -> str:
    """Echo a recorded path in the style the harness stored it.

    Absolute paths (leading slash or drive letter) pass through
    untouched; relative paths join onto ``cwd`` using the recorded
    path's own separator. No normalization happens: the digest shows
    what the harness wrote, not what this OS would write.
    """
    if not isinstance(arguments, dict):
        return ""
    value = ""
    for key in keys:
        candidate = arguments.get(key)
        if isinstance(candidate, str) and candidate.strip():
            value = candidate.strip()
            break
    if not value:
        return ""
    if value.startswith("~"):
        value = os.path.expanduser(value)
    absolute = value.startswith(("/", "\\")) or (
        len(value) > 1 and value[1] == ":"
    )
    if absolute or not cwd:
        return value
    separator = "\\" if "\\" in value else "/"
    return cwd.rstrip("/\\") + separator + value


def tool_detail(arguments: Any, keys: Sequence[str] = ()) -> str:
    if not isinstance(arguments, dict):
        return ""
    for key in keys:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
    for value in arguments.values():
        if isinstance(value, str) and value.strip():
            return one_line(value, 160)
    return ""


def tool_detail_for(
    name: str,
    arguments: Any,
    keys_by_tool: Mapping[str, Sequence[str]],
) -> str:
    return tool_detail(arguments, keys_by_tool.get(name, ()))
