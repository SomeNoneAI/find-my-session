"""Adapter for the Antigravity CLI (``agy``).

The CLI keeps its own conversation store under ``~/.gemini/antigravity-cli``,
separate from the desktop app. Its summaries database carries no archive
state, so every listed CLI session stays active.
"""

from __future__ import annotations

from .antigravity_family import AntigravityBaseAdapter


class AntigravityCLIAdapter(AntigravityBaseAdapter):
    """Antigravity CLI: one conversation database per session."""

    name = "antigravity-cli"
    aliases = ("antigravity-cli", "agy")
    variants = "cli"
    store_hint = "~/.gemini/antigravity-cli"
    home_dirname = ".gemini/antigravity-cli"
    home_env = "FMS_ANTIGRAVITY_CLI_HOME"
    entrypoint_label = "cli"
    archive_source = False
