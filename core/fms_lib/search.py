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


def search_summaries(
    summaries: Iterable[SessionSummary],
    tokens: Sequence[str],
    deep: bool = False,
    deep_match: Optional[Callable[[SessionSummary, Sequence[str]], bool]] = None,
) -> List[SessionSummary]:
    if not tokens:
        return sorted(summaries, key=lambda summary: summary.updated, reverse=True)
    scored: List[Tuple[int, SessionSummary]] = []
    for summary in summaries:
        score = score_summary(summary, tokens)
        if score is None and deep and deep_match is not None:
            if deep_match(summary, tokens):
                score = 1
        if score is not None:
            scored.append((score, summary))
    scored.sort(key=lambda pair: (pair[0], pair[1].updated), reverse=True)
    return [summary for _, summary in scored]
