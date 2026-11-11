from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List

from .limits import (
    SHOW_CHARS_DEFAULT,
    SHOW_MESSAGES_DEFAULT,
    SHOW_SUMMARY_CHARS_DEFAULT,
)
from .models import Exchange, PromptListing, SessionDetail, SessionSummary
from .util import abbreviate_path, block_text, format_local, normalize_text, one_line


def json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _cell(value: Any, limit: int = 0) -> str:
    text = one_line(value, limit)
    return text if text else "-"


def render_stats_text(rows: List[Dict[str, Any]]) -> str:
    header = (
        "harness\tsessions\tusage sessions\tinput tokens"
        "\toutput tokens\tcost (USD)"
    )
    lines = [header]
    for row in rows:
        if row["sessions_with_usage"] == 0:
            tokens_in = tokens_out = cost = "-"
        else:
            tokens_in = str(row["tokens_input"])
            tokens_out = str(row["tokens_output"])
            cost = "%.4f" % row["cost_usd"] if row["cost_usd"] is not None else "-"
        lines.append(
            "%s\t%d\t%d\t%s\t%s\t%s"
            % (
                row["harness"],
                row["sessions"],
                row["sessions_with_usage"],
                tokens_in,
                tokens_out,
                cost,
            )
        )
    return "\n".join(lines) + "\n"


def render_harness_tsv(rows: List[Dict[str, object]]) -> str:
    lines = ["harness\tstatus\tvariants\tstore\taliases"]
    for row in rows:
        lines.append(
            "\t".join(
                [
                    _cell(row.get("name")),
                    _cell(row.get("status")),
                    _cell(row.get("variants")),
                    _cell(row.get("store")),
                    _cell(row.get("aliases")),
                ]
            )
        )
    return "\n".join(lines) + "\n"


def render_search_tsv(
    results: List[SessionSummary],
    include_archived: bool = False,
) -> str:
    if not results:
        if include_archived:
            return "no sessions matched\n"
        return (
            "no sessions matched "
            "(archived sessions are excluded; retry with --include-archived)\n"
        )
    lines = ["ref\tupdated\tcwd\ttitle\tarchived"]
    for summary in results:
        lines.append(
            "\t".join(
                [
                    summary.ref,
                    format_local(summary.updated),
                    _cell(abbreviate_path(summary.cwd)),
                    _cell(summary.title, 100),
                    "yes" if summary.archived else "-",
                ]
            )
        )
    return "\n".join(lines) + "\n"


def render_prompts_markdown(listing: PromptListing, chars: int = 0) -> str:
    summary = listing.summary
    if listing.count_only:
        return "%d\n" % listing.total
    lines: List[str] = ["# %s user prompts" % summary.ref, ""]
    if summary.archived:
        lines.extend(["- archived: yes", ""])
    lines.extend(
        [
            "total: %d, returned: %d, order: %s"
            % (listing.total, len(listing.prompts), listing.order),
            "",
        ]
    )
    if not listing.prompts:
        lines.append(
            "no prompts in this range" if listing.total else "no user prompts"
        )
        return "\n".join(lines) + "\n"
    for index, prompt in listing.prompts:
        if prompt.timestamp:
            lines.append("## %d · %s" % (index, format_local(prompt.timestamp)))
        else:
            lines.append("## %d" % index)
        lines.extend([block_text(prompt.text, chars), ""])
    if listing.has_more:
        lines.append(
            "next: --offset %d --limit %d"
            % (listing.offset + len(listing.prompts), listing.limit)
        )
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def render_prompts_json(listing: PromptListing, chars: int = 0) -> str:
    data = listing.to_dict()
    if chars > 0:
        for prompt in data.get("prompts", []):
            prompt["text"] = block_text(prompt["text"], chars)
    return json_dump(data)


def _time_only(summary_text: str) -> str:
    return summary_text[11:] if len(summary_text) > 11 else summary_text


def _exchange_tools(exchange: Exchange) -> str:
    counts = Counter(tool.name for tool in exchange.tools)
    return ", ".join("%s x%d" % (name, count) for name, count in counts.most_common())


def render_show_markdown(
    detail: SessionDetail,
    messages: int = SHOW_MESSAGES_DEFAULT,
    chars: int = SHOW_CHARS_DEFAULT,
    summary_chars: int = SHOW_SUMMARY_CHARS_DEFAULT,
    include_todos: bool = True,
    include_tools: bool = True,
) -> str:
    summary = detail.summary
    lines: List[str] = ["# %s" % summary.ref, ""]

    harness_line = summary.harness
    if summary.variants:
        harness_line += " (%s)" % summary.variants
    lines.append("- harness: %s" % harness_line)
    if summary.cwd:
        lines.append("- cwd: `%s`" % summary.cwd)
    if summary.branch:
        lines.append("- branch: `%s`" % summary.branch)
    lines.append("- updated: %s" % format_local(summary.updated))
    if summary.archived:
        lines.append("- archived: yes")
    if summary.started:
        lines.append("- started: %s" % format_local(summary.started))
    lines.append("- turns: %d" % detail.turn_count)
    if summary.model:
        lines.append("- model: `%s`" % summary.model)
    if summary.version:
        lines.append("- version: `%s`" % summary.version)
    lines.append("- source: `%s`" % summary.path)
    lines.append("")

    first_prompt = block_text(summary.first_prompt, chars)
    last_prompt = block_text(summary.last_prompt, chars)
    if first_prompt:
        lines.extend(["## Task", first_prompt, ""])
    if last_prompt and normalize_text(last_prompt) != normalize_text(first_prompt):
        lines.extend(["## Latest request", last_prompt, ""])

    if summary_chars > 0 and detail.compact_summary:
        lines.extend(
            [
                "## Compact summary (latest compaction)",
                block_text(detail.compact_summary, summary_chars),
                "",
            ]
        )

    if include_todos and detail.todos:
        open_statuses = {"pending", "in_progress", "processing", "blocked"}
        open_todos = [todo for todo in detail.todos if todo.get("status") in open_statuses]
        completed = [todo for todo in detail.todos if todo.get("status") not in open_statuses]
        lines.append("## Todos (%d open / %d total)" % (len(open_todos), len(detail.todos)))
        if open_todos:
            for todo in open_todos[:8]:
                lines.append("- [%s] %s" % (todo.get("status") or "open", todo.get("subject") or ""))
            if len(open_todos) > 8:
                lines.append("- ... %d more open" % (len(open_todos) - 8))
        else:
            for todo in completed[-5:]:
                lines.append("- [completed] %s" % (todo.get("subject") or ""))
        lines.append("")

    if messages > 0 and detail.exchanges:
        selected = [exchange for exchange in detail.exchanges if exchange.user_text or exchange.assistant_texts or exchange.tools]
        selected = selected[-messages:]
        if selected:
            lines.append("## Recent turns")
            for exchange in selected:
                if exchange.user_text:
                    if exchange.timestamp:
                        lines.append("**User** %s" % format_local(exchange.timestamp))
                    else:
                        lines.append("**User**")
                    lines.extend([block_text(exchange.user_text, chars), ""])
                if exchange.assistant_texts:
                    if exchange.timestamp:
                        lines.append("**Assistant** %s" % format_local(exchange.timestamp))
                    else:
                        lines.append("**Assistant**")
                    lines.extend([block_text(exchange.assistant_texts[-1], chars), ""])
                if include_tools and exchange.tools:
                    tools = _exchange_tools(exchange)
                    if tools:
                        lines.extend(["Tools: %s" % tools, ""])
            if lines and lines[-1] == "":
                lines.pop()
            lines.append("")

    if detail.edited_files:
        lines.append("## Edited files")
        for item in detail.edited_files[-12:]:
            path = item.get("path") or ""
            count = int(item.get("count") or 1)
            suffix = " (x%d)" % count if count > 1 else ""
            lines.append("- `%s`%s" % (abbreviate_path(path), suffix))
        if len(detail.edited_files) > 12:
            lines.append("- ... %d more" % (len(detail.edited_files) - 12))
        lines.append("")

    if include_tools and detail.recent_tools:
        lines.append("## Recent tools")
        for tool in detail.recent_tools[-5:]:
            when = _time_only(format_local(tool.timestamp))
            detail_text = (": " + tool.detail) if tool.detail else ""
            lines.append("- %s %s%s" % (when, tool.name, detail_text))
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def render_show_json(
    detail: SessionDetail,
    messages: int = SHOW_MESSAGES_DEFAULT,
    chars: int = SHOW_CHARS_DEFAULT,
    summary_chars: int = SHOW_SUMMARY_CHARS_DEFAULT,
    include_todos: bool = True,
    include_tools: bool = True,
) -> str:
    data = detail.to_dict(max_exchanges=messages)
    if not include_todos:
        data["todos"] = []
    if not include_tools:
        data["recent_tools"] = []
        data["tool_counts"] = {}
        for exchange in data["exchanges"]:
            exchange["tools"] = []
    if chars > 0:
        for exchange in data["exchanges"]:
            exchange["user"] = block_text(exchange["user"], chars)
            exchange["assistant"] = [
                block_text(text, chars) for text in exchange["assistant"]
            ]
    data["compact_summary"] = (
        block_text(data["compact_summary"], summary_chars) if summary_chars > 0 else ""
    )
    return json_dump(data)
