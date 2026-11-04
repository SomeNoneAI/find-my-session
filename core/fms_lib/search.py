from __future__ import annotations

from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from .models import SessionSummary
from .util import normalize_text


def tokenize_query(parts: Sequence[str]) -> List[str]:
    text = " ".join(parts)
    return [token for token in normalize_text(text).split() if token]


def score_summary(summary: SessionSummary, tokens: Sequence[str]) -> Optional[int]:
    if not tokens:
        return 0
    session_id = normalize_text(summary.session_id)
    cwd = normalize_text(summary.cwd)
    title = normalize_text(summary.title)
    first = normalize_text(summary.first_prompt)
    last = normalize_text(summary.last_prompt)
    other = normalize_text(
        " ".join(
            [
                summary.branch,
                summary.model,
                summary.entrypoint,
                summary.version,
                summary.path.parent.name,
            ]
        )
    )
    score = 0
    for token in tokens:
        best = 0
        if token in session_id:
            best = 200 if session_id.startswith(token) else 100
        if token in cwd:
            best = max(best, 80)
        if token in title or token in last:
            best = max(best, 60)
        if token in first:
            best = max(best, 50)
        if token in other:
            best = max(best, 10)
        if best == 0:
            return None
        score += best
    return score

def explain_score(
    summary: SessionSummary, tokens: Sequence[str]
) -> Optional[List[Tuple[str, str, int]]]:
    """Break down score_summary per token: (token, field, points)."""
    if not tokens:
        return []
    session_id = normalize_text(summary.session_id)
    cwd = normalize_text(summary.cwd)
    title = normalize_text(summary.title)
    first = normalize_text(summary.first_prompt)
    last = normalize_text(summary.last_prompt)
    other = normalize_text(
        " ".join(
            [
                summary.branch,
                summary.model,
                summary.entrypoint,
                summary.version,
                summary.path.parent.name,
            ]
        )
    )
    breakdown: List[Tuple[str, str, int]] = []
    for token in tokens:
        best = 0
        field = ""
        if token in session_id:
            points = 200 if session_id.startswith(token) else 100
            if points > best:
                best, field = points, "session_id"
        if token in cwd and 80 > best:
            best, field = 80, "cwd"
        if (token in title or token in last) and 60 > best:
            best, field = 60, "title/last_prompt"
        if token in first and 50 > best:
            best, field = 50, "first_prompt"
        if token in other and 10 > best:
            best, field = 10, "other"
        if best == 0:
            return None
        breakdown.append((token, field, best))
    return breakdown


class DeepTimeout(Exception):
    """Raised when a deep-search deadline expires; carries partial results."""

    def __init__(self, partial: List[SessionSummary], scanned: int) -> None:
        super().__init__("deep search timed out")
        self.partial = partial
        self.scanned = scanned


def search_summaries(
    summaries: Iterable[SessionSummary],
    tokens: Sequence[str],
    deep: bool = False,
    deep_match: Optional[Callable[[SessionSummary, Sequence[str]], bool]] = None,
    deadline: Optional[float] = None,
) -> List[SessionSummary]:
    import time as _time

    if not tokens:
        return sorted(summaries, key=lambda summary: summary.updated, reverse=True)
    scored: List[Tuple[int, SessionSummary]] = []
    scanned = 0
    for summary in summaries:
        score = score_summary(summary, tokens)
        if score is None and deep and deep_match is not None:
            if deadline is not None and _time.perf_counter() >= deadline:
                partial = [summary for _, summary in scored]
                raise DeepTimeout(partial, scanned)
            scanned += 1
            if deep_match(summary, tokens):
                score = 1
        if score is not None:
            scored.append((score, summary))
    scored.sort(key=lambda pair: (pair[0], pair[1].updated), reverse=True)
    return [summary for _, summary in scored]
