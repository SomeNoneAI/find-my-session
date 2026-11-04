from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from typing import Optional, Sequence

from . import __version__
from .diagnostics import ScanReport, hint_for, render_doctor_text
from .errors import UserError
from .mcp import serve as mcp_serve
from .registry import get_adapters, harness_rows
from .render import (
    json_dump,
    render_harness_tsv,
    render_prompts_json,
    render_prompts_markdown,
    render_search_tsv,
    render_show_json,
    render_show_markdown,
    render_stats_text,
)
from .search import explain_score, tokenize_query
from .service import (
    doctor,
    list_prompts,
    load_session,
    resolve_session,
    search_sessions,
)
from .service import (
    stats as stats_service,
)

PROGRAM = "fms"


def _print_explain(query, results) -> None:
    """Print per-token scoring breakdowns to stderr (never stdout)."""
    tokens = tokenize_query(query)
    if not tokens:
        return
    for summary in results:
        breakdown = explain_score(summary, tokens)
        if breakdown is None:
            sys.stderr.write(
                "%s: %s: deep-only match (no metadata score)\n"
                % (PROGRAM, summary.ref)
            )
            continue
        parts = ", ".join(
            "%s=%s+%d" % (token, field, points)
            for token, field, points in breakdown
        )
        total = sum(points for _, _, points in breakdown)
        sys.stderr.write(
            "%s: %s: score %d (%s)\n" % (PROGRAM, summary.ref, total, parts)
        )


def _positive_or_zero(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return number


def _fail(message: str) -> int:
    sys.stderr.write("%s: %s\n" % (PROGRAM, message))
    return 2


def cmd_harnesses(args: argparse.Namespace) -> int:
    rows = harness_rows()
    if args.json:
        print(json_dump(rows))
        return 0
    sys.stdout.write(render_harness_tsv(rows))
    if not any(row["status"] == "ready" for row in rows):
        return 1
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    report = ScanReport() if args.verbose else None
    results = search_sessions(
        args.query,
        harness=args.harness,
        cwd=args.cwd,
        since=args.since,
        limit=args.limit,
        deep=args.deep,
        include_archived=args.include_archived,
        report=report,
        timeout=args.timeout,
    )
    if args.json:
        print(json_dump([summary.to_dict() for summary in results]))
    else:
        sys.stdout.write(render_search_tsv(results, args.include_archived))
    if args.explain:
        _print_explain(args.query, results)
    _warn_skipped(report, args.verbose)
    return 0


def cmd_latest(args: argparse.Namespace) -> int:
    report = ScanReport() if args.verbose else None
    results = search_sessions(
        args.query,
        harness=args.harness,
        cwd=args.cwd,
        since=args.since,
        limit=args.limit,
        deep=args.deep,
        include_archived=args.include_archived,
        latest=True,
        report=report,
        timeout=args.timeout,
    )
    if args.json:
        print(json_dump([summary.to_dict() for summary in results]))
    else:
        sys.stdout.write(render_search_tsv(results, args.include_archived))
    if args.explain:
        _print_explain(args.query, results)
    _warn_skipped(report, args.verbose)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    payload = doctor(harness=args.harness, fingerprint=args.fingerprint)
    if args.json:
        print(json_dump(payload))
    else:
        sys.stdout.write(render_doctor_text(payload))
    return 0


def _warn_skipped(report: Optional[ScanReport], verbose: bool) -> None:
    if report is None or not report.skipped:
        return
    sys.stderr.write(
        "%s: warning: %d session(s) skipped while scanning\n"
        % (PROGRAM, len(report.skipped))
    )
    for harness, reason, count, detail, paths in report.grouped():
        line = "%s:   %s: %dx %s" % (PROGRAM, harness, count, reason)
        if detail:
            line += ": %s" % detail
        hint = hint_for(reason, detail)
        if hint:
            line += " — %s" % hint
        sys.stderr.write(line + "\n")
        if verbose:
            for path in paths:
                sys.stderr.write("%s:     %s\n" % (PROGRAM, path))


def cmd_prompts(args: argparse.Namespace) -> int:
    listing = list_prompts(
        args.ref,
        harness=args.harness,
        offset=args.offset,
        limit=args.limit,
        order=args.order,
        count_only=args.count,
    )
    if args.json:
        print(render_prompts_json(listing, args.chars))
    else:
        sys.stdout.write(render_prompts_markdown(listing, args.chars))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    adapter, summary = resolve_session(args.ref, get_adapters(args.harness))
    argv = adapter.resume_argv(summary)
    if args.json:
        print(
            json_dump(
                {
                    "ref": summary.ref,
                    "harness": adapter.name,
                    "resume_argv": argv,
                    "executed": bool(argv and args.exec),
                }
            )
        )
        return 0
    if argv is None:
        sys.stdout.write(
            "no verified resume command for harness '%s' yet; "
            "hand off with: fms show %s\n" % (adapter.name, summary.ref)
        )
        return 0
    sys.stdout.write(shlex.join(argv) + "\n")
    if args.exec:
        sys.stderr.write("fms: launching %s\n" % shlex.join(argv))
        try:
            return subprocess.run(argv).returncode
        except FileNotFoundError as exc:
            sys.stderr.write("fms: %s\n" % exc)
            return 2
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    rows = stats_service(
        harness=args.harness,
        cwd=args.cwd,
        since=args.since,
        include_archived=args.include_archived,
    )
    if args.json:
        print(json_dump(rows))
    else:
        sys.stdout.write(render_stats_text(rows))
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    return mcp_serve()


def cmd_show(args: argparse.Namespace) -> int:
    detail = load_session(args.ref, harness=args.harness)
    if args.format == "json":
        print(
            render_show_json(
                detail,
                messages=args.messages,
                chars=args.chars,
                summary_chars=args.summary_chars,
                include_todos=not args.no_todos,
                include_tools=not args.no_tools,
            )
        )
    else:
        sys.stdout.write(
            render_show_markdown(
                detail,
                messages=args.messages,
                chars=args.chars,
                summary_chars=args.summary_chars,
                include_todos=not args.no_todos,
                include_tools=not args.no_tools,
            )
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "Find and summarize past agent sessions across coding harnesses. "
            "Read-only: never modifies session stores."
        ),
        epilog=(
            "examples:\n"
            "  fms harnesses\n"
            "  fms search --harness qoder-cn oauth token refresh\n"
            "  fms latest --harness qoder-cn --cwd .\n"
            "  fms show qoder-cn:3f2a9c1d\n"
            "  fms show qoder-cn:3f2a9c1d --messages 3 --format json\n"
            "  fms prompts qoder-cn:3f2a9c1d --count\n"
            "  fms prompts qoder-cn:3f2a9c1d --limit 20 --offset 40\n"
            "  fms resume claude-code:c1a0de03 --exec\n"
            "  fms stats --since 7d\n"
            "  fms doctor --harness deepseek\n"
            "\nPrefer --harness to avoid scanning every store."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version="%s %s" % (PROGRAM, __version__)
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    harnesses = subparsers.add_parser(
        "harnesses", help="list supported and planned harnesses"
    )
    harnesses.add_argument(
        "--json", action="store_true", help="emit JSON instead of TSV"
    )
    harnesses.set_defaults(func=cmd_harnesses)

    def add_search_options(sub: argparse.ArgumentParser, default_limit: int) -> None:
        sub.add_argument(
            "query",
            nargs="*",
            help="fuzzy keywords; every keyword must match somewhere",
        )
        sub.add_argument(
            "--harness",
            action="append",
            metavar="NAME",
            help="restrict to a harness (alias allowed); repeat or comma-separate",
        )
        sub.add_argument(
            "--cwd",
            metavar="PATH",
            help="only sessions from this working directory or its descendants",
        )
        sub.add_argument(
            "--since",
            metavar="WHEN",
            help="only sessions updated since this time (7d, 24h, 2026-10-01)",
        )
        sub.add_argument(
            "--limit",
            type=_positive_or_zero,
            default=default_limit,
            metavar="N",
            help="max results; 0 means no limit (default: %d)" % default_limit,
        )
        sub.add_argument(
            "--deep",
            action="store_true",
            help="also scan full transcripts when head/tail metadata misses",
        )
        sub.add_argument(
            "--include-archived",
            action="store_true",
            help="include archived sessions (excluded by default)",
        )
        sub.add_argument(
            "--verbose",
            action="store_true",
            help="warn on stderr about sessions skipped as unreadable",
        )
        sub.add_argument(
            "--explain",
            action="store_true",
            help="print per-token scoring breakdowns to stderr",
        )
        sub.add_argument(
            "--json", action="store_true", help="emit JSON instead of TSV"
        )
        sub.add_argument(
            "--timeout",
            type=float,
            default=0,
            metavar="SECONDS",
            help="stop deep scanning after N seconds and show partial results (0 = no limit)",
        )

    search = subparsers.add_parser(
        "search", help="find sessions by fuzzy keywords or metadata"
    )
    add_search_options(search, 10)
    search.set_defaults(func=cmd_search)

    latest = subparsers.add_parser(
        "latest", help="show the most recently updated matching sessions"
    )
    add_search_options(latest, 1)
    latest.set_defaults(func=cmd_latest)

    doctor_parser = subparsers.add_parser(
        "doctor", help="diagnose store readability without reading session content"
    )
    doctor_parser.add_argument(
        "--harness",
        action="append",
        metavar="NAME",
        help="restrict to a harness (alias allowed); repeat or comma-separate",
    )
    doctor_parser.add_argument(
        "--json", action="store_true", help="emit JSON instead of text"
    )
    doctor_parser.add_argument(
        "--fingerprint",
        action="store_true",
        help=(
            "add a redacted shape fingerprint per store: layout kinds, "
            "top-level field names with value types and counts only — "
            "never prompts, paths, ids, or other content"
        ),
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    mcp_parser = subparsers.add_parser(
        "mcp",
        help="run the Model Context Protocol server on stdio (read-only tools)",
    )
    mcp_parser.set_defaults(func=cmd_mcp)

    stats_parser = subparsers.add_parser(
        "stats",
        help="aggregate recorded token/cost usage per harness",
    )
    stats_parser.add_argument(
        "--harness",
        action="append",
        metavar="NAME",
        help="restrict to a harness (alias allowed); repeat or comma-separate",
    )
    stats_parser.add_argument(
        "--cwd",
        metavar="PATH",
        help="only sessions from this working directory or its descendants",
    )
    stats_parser.add_argument(
        "--since",
        metavar="WHEN",
        help="only sessions updated since this time (7d, 24h, 2026-10-01)",
    )
    stats_parser.add_argument(
        "--include-archived",
        action="store_true",
        help="include archived sessions (excluded by default)",
    )
    stats_parser.add_argument(
        "--json", action="store_true", help="emit JSON instead of TSV"
    )
    stats_parser.set_defaults(func=cmd_stats)

    resume = subparsers.add_parser(
        "resume",
        help="print (or with --exec, run) the harness command that reopens a session",
    )
    resume.add_argument(
        "ref",
        help="session ref like qoder-cn:3f2a9c1d, a unique id prefix, or a transcript path",
    )
    resume.add_argument(
        "--harness",
        action="append",
        metavar="NAME",
        help="restrict bare-prefix lookup to a harness",
    )
    resume.add_argument(
        "--exec",
        action="store_true",
        help="run the resume command instead of only printing it",
    )
    resume.add_argument(
        "--json", action="store_true", help="emit JSON instead of text"
    )
    resume.set_defaults(func=cmd_resume)

    show = subparsers.add_parser(
        "show", help="show a bounded handoff digest for one session"
    )
    show.add_argument(
        "ref",
        help="session ref like qoder-cn:3f2a9c1d, a unique id prefix, or a transcript path",
    )
    show.add_argument(
        "--harness",
        action="append",
        metavar="NAME",
        help="restrict bare-prefix lookup to a harness",
    )
    show.add_argument(
        "--messages",
        type=_positive_or_zero,
        default=2,
        metavar="N",
        help="recent user/assistant turns to include (default: 2, 0 disables)",
    )
    show.add_argument(
        "--chars",
        type=_positive_or_zero,
        default=600,
        metavar="N",
        help="max characters per message block (default: 600)",
    )
    show.add_argument(
        "--summary-chars",
        type=_positive_or_zero,
        default=1000,
        metavar="N",
        help="max characters for the compact summary (default: 1000, 0 disables)",
    )
    show.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="output format (default: markdown)",
    )
    show.add_argument(
        "--no-todos", action="store_true", help="omit the todo section"
    )
    show.add_argument(
        "--no-tools", action="store_true", help="omit tool summaries"
    )
    show.set_defaults(func=cmd_show)

    prompts = subparsers.add_parser(
        "prompts", help="list every user prompt in one session"
    )
    prompts.add_argument(
        "ref",
        help="session ref like qoder-cn:3f2a9c1d, a unique id prefix, or a transcript path",
    )
    prompts.add_argument(
        "--harness",
        action="append",
        metavar="NAME",
        help="restrict bare-prefix lookup to a harness",
    )
    prompts.add_argument(
        "--offset",
        type=_positive_or_zero,
        default=0,
        metavar="N",
        help="skip the first N prompts (default: 0)",
    )
    prompts.add_argument(
        "--limit",
        type=_positive_or_zero,
        default=0,
        metavar="N",
        help="max prompts to print; 0 means all (default: 0)",
    )
    prompts.add_argument(
        "--chars",
        type=_positive_or_zero,
        default=0,
        metavar="N",
        help="max characters per prompt; 0 means full text (default: 0)",
    )
    prompts.add_argument(
        "--order",
        choices=("oldest", "newest"),
        default="oldest",
        help="page order (default: oldest)",
    )
    prompts.add_argument(
        "--count",
        action="store_true",
        help="print only the total number of user prompts",
    )
    prompts.add_argument(
        "--json", action="store_true", help="emit JSON instead of Markdown"
    )
    prompts.set_defaults(func=cmd_prompts)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except UserError as exc:
        return _fail(str(exc))
    except ValueError as exc:
        return _fail(str(exc))
    except OSError as exc:
        return _fail("cannot read session store: %s" % exc)
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
