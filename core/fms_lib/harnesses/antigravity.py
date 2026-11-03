"""Adapter for Antigravity desktop and its retired IDE edition.

Both editions share one SQLite conversation store under
``~/.gemini/antigravity``. The IDE's conversations were migrated into the
desktop store byte for byte; their brain transcripts stayed under
``~/.gemini/antigravity-ide`` and are read as a legacy companion root. The
Antigravity CLI keeps a separate store and is ``antigravity-cli``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

from .antigravity_family import AntigravityBaseAdapter


class AntigravityAdapter(AntigravityBaseAdapter):
    """Antigravity desktop: one conversation database per session."""

    name = "antigravity"
    aliases = ("antigravity", "antigravity-desktop", "antigravity-ide")
    variants = "desktop, ide"
    store_hint = "~/.gemini/antigravity"
    home_dirname = ".gemini/antigravity"
    home_env = "FMS_ANTIGRAVITY_HOME"
    legacy_home_env = "FMS_ANTIGRAVITY_IDE_HOME"
    entrypoint_label = "desktop"
    archive_source = True

    def _legacy_home(self) -> Optional[Path]:
        override = os.environ.get(self.legacy_home_env)
        if override:
            return Path(override).expanduser()
        if os.environ.get(self.home_env):
            return None
        return Path.home() / ".gemini" / "antigravity-ide"

    def _brain_roots(self) -> List[Tuple[Path, str]]:
        roots = [(self.home() / "brain", "desktop")]
        legacy = self._legacy_home()
        if legacy is not None:
            roots.append((legacy / "brain", "ide"))
        return roots
