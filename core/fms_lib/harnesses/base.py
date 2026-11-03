from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Tuple

from ..models import SessionDetail, SessionSummary, UserPrompt
from ..util import file_contains_all


class HarnessAdapter(ABC):
    name: str
    aliases: Tuple[str, ...]
    variants: str
    store_hint: str

    @abstractmethod
    def home(self) -> Path:
        raise NotImplementedError

    def session_roots(self) -> List[Path]:
        return [self.home() / "projects"]

    def iter_session_paths(self) -> Iterator[Path]:
        raise NotImplementedError

    def summarize(self, path: Path) -> SessionSummary:
        raise NotImplementedError

    def load(self, summary: SessionSummary) -> SessionDetail:
        raise NotImplementedError

    def iter_prompts(self, summary: SessionSummary) -> Iterator[UserPrompt]:
        raise NotImplementedError

    def session_id_for(self, path: Path) -> str:
        return path.stem

    def find(self, needle: str) -> List[SessionSummary]:
        wanted = needle.casefold()
        matches: List[SessionSummary] = []
        for path in self.iter_session_paths():
            session_id = self.session_id_for(path).casefold()
            if not session_id.startswith(wanted):
                continue
            try:
                matches.append(self.summarize(path))
            except (OSError, ValueError):
                continue
        return matches

    def contains(self, summary: SessionSummary, tokens: Sequence[str]) -> bool:
        return file_contains_all(summary.path, tokens)

    def resume_argv(self, summary: SessionSummary) -> Optional[List[str]]:
        """Command that reopens this session in its own harness, if known.

        Returns an argv list (no shell) or None when the harness has no
        verified resume command. Only implement this for commands whose
        flag and id semantics have been verified.
        """
        return None

    def owns(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            return False
        for root in self.session_roots():
            try:
                resolved.relative_to(root.resolve())
                return True
            except (OSError, ValueError):
                continue
        return False
