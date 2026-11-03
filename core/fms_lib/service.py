from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from .diagnostics import ScanReport, environment, issue_dicts, store_home
from .errors import UserError
from .fingerprint import fingerprint_store
from .harnesses.base import HarnessAdapter
from .models import PromptListing, SessionDetail, SessionSummary, UserPrompt
from .registry import adapter_for_path, get_adapters, lookup_harness
from .search import search_summaries, tokenize_query
from .util import cwd_matches, parse_since


def _summarize_pair(
    pair: Tuple[HarnessAdapter, Path], report: Optional[ScanReport] = None
) -> Optional[SessionSummary]:
    adapter, path = pair
    try:
        summary = adapter.summarize(path)
    except (OSError, ValueError) as exc:
        if report is not None:
            report.record(adapter.name, exc, path)
        return None
    if report is not None:
        report.note_readable()
    return summary


def _gather_summaries(
    adapters: Sequence[HarnessAdapter], report: Optional[ScanReport] = None
) -> List[SessionSummary]:
    pairs: List[Tuple[HarnessAdapter, Path]] = []
    for adapter in adapters:
        try:
            paths = list(adapter.iter_session_paths())
        except OSError as exc:
            if report is not None:
                report.note_store_error(adapter.name, exc)
            continue
        pairs.extend((adapter, path) for path in paths)
    if report is not None:
        report.candidates += len(pairs)

    if not pairs:
        return []
    if len(pairs) == 1:
        summary = _summarize_pair(pairs[0], report)
        return [summary] if summary else []
    workers = min(8, len(pairs))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda pair: _summarize_pair(pair, report), pairs))
    return [summary for summary in results if summary is not None]


def _filter_summaries(
    summaries: Sequence[SessionSummary],
    cwd: Optional[str],
    since: Optional[str],
    include_archived: bool = False,
) -> List[SessionSummary]:
    threshold = parse_since(since) if since else None
    selected: List[SessionSummary] = []
    for summary in summaries:
        if not include_archived and summary.archived:
            continue
        if cwd and not cwd_matches(summary.cwd, cwd):
            continue
        if threshold is not None and summary.updated < threshold:
            continue
        selected.append(summary)
    return selected


def _limit(summaries: Sequence[SessionSummary], limit: int) -> List[SessionSummary]:
    if limit <= 0:
        return list(summaries)
    return list(summaries[:limit])


def _deep_matcher(
    adapters: Sequence[HarnessAdapter],
) -> Callable[[SessionSummary, Sequence[str]], bool]:
    by_name = {adapter.name: adapter for adapter in adapters}

    def match(summary: SessionSummary, tokens: Sequence[str]) -> bool:
        adapter = by_name.get(summary.harness)
        if adapter is None:
            return False
        try:
            return adapter.contains(summary, tokens)
        except (OSError, ValueError):
            return False

    return match


def gather_summaries(
    harness: Optional[Sequence[str]] = None,
    report: Optional[ScanReport] = None,
) -> List[SessionSummary]:
    """Scan the session stores once and summarize every candidate."""
    return _gather_summaries(get_adapters(harness), report)


def query_summaries(
    summaries: Sequence[SessionSummary],
    query: Sequence[str] = (),
    cwd: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 10,
    include_archived: bool = False,
    latest: bool = False,
) -> List[SessionSummary]:
    """Apply the standard metadata filter/score/order pipeline without scanning."""
    selected = _filter_summaries(summaries, cwd, since, include_archived)
    results = search_summaries(selected, tokenize_query(query))
    if latest:
        results.sort(key=lambda summary: summary.updated, reverse=True)
    return _limit(results, limit)


def search_sessions(
    query: Sequence[str] = (),
    harness: Optional[Sequence[str]] = None,
    cwd: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 10,
    deep: bool = False,
    include_archived: bool = False,
    latest: bool = False,
    report: Optional[ScanReport] = None,
) -> List[SessionSummary]:
    adapters = get_adapters(harness)
    summaries = _filter_summaries(
        _gather_summaries(adapters, report), cwd, since, include_archived
    )
    tokens = tokenize_query(query)
    deep_match = _deep_matcher(adapters) if deep else None
    results = search_summaries(summaries, tokens, deep, deep_match)
    if latest:
        results.sort(key=lambda summary: summary.updated, reverse=True)
    return _limit(results, limit)


def _fingerprint_paths(adapter: HarnessAdapter) -> List[Path]:
    """Real, existing files behind the adapter's candidates.

    Database-row adapters yield virtual ``<db>#<id>`` paths; the fingerprint
    describes the underlying store files, deduplicated in candidate order.
    """
    paths: List[Path] = []
    seen: Set[Path] = set()
    try:
        candidates = list(adapter.iter_session_paths())
    except OSError:
        return paths
    for candidate in candidates:
        target = candidate
        if not target.is_file():
            target = Path(str(target).split("#", 1)[0])
        try:
            real = target.expanduser().resolve()
        except OSError:
            continue
        if not real.is_file() or real in seen:
            continue
        seen.add(real)
        paths.append(real)
    return paths


def doctor(
    harness: Optional[Sequence[str]] = None, fingerprint: bool = False
) -> Dict[str, Any]:
    """Report store readability per harness without exposing session content."""
    payload = environment()
    stores: List[Dict[str, Any]] = []
    for adapter in get_adapters(harness):
        report = ScanReport()
        home = adapter.home()
        present = home.is_dir()
        if present:
            _gather_summaries([adapter], report)
        store: Dict[str, Any] = {
            "harness": adapter.name,
            "variants": adapter.variants,
            "store": adapter.store_hint,
            "home": store_home(home),
            "present": present,
            "candidates": report.candidates,
            "readable": report.readable,
            "skipped": len(report.skipped),
            "issues": issue_dicts(report),
        }
        if fingerprint and present:
            store["fingerprint"] = fingerprint_store(
                _fingerprint_paths(adapter)
            )
        stores.append(store)
    payload["stores"] = stores
    return payload


def project_paths_from(
    summaries: Sequence[SessionSummary],
    include_archived: bool = False,
) -> List[str]:
    selected = _filter_summaries(summaries, None, None, include_archived)
    projects = {summary.cwd.strip() for summary in selected if summary.cwd.strip()}
    return sorted(projects, key=lambda path: (path.casefold(), path))


def list_project_paths(
    harness: Optional[Sequence[str]] = None,
    include_archived: bool = False,
) -> List[str]:
    return project_paths_from(
        _gather_summaries(get_adapters(harness)), include_archived
    )


def resolve_session(
    ref: str,
    adapters: Sequence[HarnessAdapter],
) -> Tuple[HarnessAdapter, SessionSummary]:
    path = Path(ref).expanduser()
    if path.is_file():
        adapter = adapter_for_path(path)
        if adapter is None:
            raise UserError(
                "file is not inside a known harness session store: %s" % path
            )
        return adapter, adapter.summarize(path)

    if "#" in path.name:
        base = Path(str(path).split("#", 1)[0])
        if base.is_file():
            adapter = adapter_for_path(base)
            if adapter is not None:
                return adapter, adapter.summarize(path)

    prefix = ref
    if ":" in ref:
        harness_name, _, prefix = ref.partition(":")
        adapters = [lookup_harness(harness_name)]
    prefix = prefix.strip()
    if len(prefix) < 4:
        raise UserError(
            "session ref '%s' is too short; use at least 4 characters, "
            "for example qoder-cn:3f2a9c1d" % ref
        )

    matches: List[Tuple[HarnessAdapter, SessionSummary]] = []
    for adapter in adapters:
        for summary in adapter.find(prefix):
            matches.append((adapter, summary))
    if not matches:
        raise UserError(
            "no session matched '%s'. Run 'fms search %s' to look it up."
            % (ref, prefix)
        )
    if len(matches) > 1:
        exact = [
            item
            for item in matches
            if item[1].session_id.casefold() == prefix.casefold()
        ]
        if len(exact) == 1:
            return exact[0]
        ordered = sorted(matches, key=lambda item: item[1].updated, reverse=True)
        candidates = ", ".join(summary.ref for _, summary in ordered[:8])
        raise UserError(
            "session ref '%s' is ambiguous; candidates: %s" % (ref, candidates)
        )
    return matches[0]


def load_session(ref: str, harness: Optional[Sequence[str]] = None) -> SessionDetail:
    adapter, summary = resolve_session(ref, get_adapters(harness))
    return adapter.load(summary)


def _select_prompt_page(
    adapter: HarnessAdapter,
    summary: SessionSummary,
    total: int,
    offset: int,
    limit: int,
    order: str,
) -> Tuple[List[Tuple[int, UserPrompt]], bool]:
    if total == 0 or offset >= total:
        return [], False
    if limit <= 0:
        first, last = 1, total
    elif order == "newest":
        last = total - offset
        first = max(1, last - limit + 1)
    else:
        first = offset + 1
        last = min(total, offset + limit)
    selected: List[Tuple[int, UserPrompt]] = []
    for index, prompt in enumerate(adapter.iter_prompts(summary), 1):
        if index > last:
            break
        if index >= first:
            selected.append((index, prompt))
    if order == "newest":
        selected.reverse()
    return selected, limit > 0 and offset + limit < total


def list_prompts(
    ref: str,
    harness: Optional[Sequence[str]] = None,
    offset: int = 0,
    limit: int = 0,
    order: str = "oldest",
    count_only: bool = False,
) -> PromptListing:
    adapter, summary = resolve_session(ref, get_adapters(harness))
    try:
        total = sum(1 for _ in adapter.iter_prompts(summary))
        listing = PromptListing(
            summary=summary,
            total=total,
            offset=offset,
            limit=limit,
            order=order,
            count_only=count_only,
        )
        if not count_only:
            listing.prompts, listing.has_more = _select_prompt_page(
                adapter, summary, total, offset, limit, order
            )
    except NotImplementedError:
        raise UserError("harness '%s' cannot list user prompts yet" % adapter.name)
    return listing
