"""Adapter for WorkBuddy AI, the international WorkBuddy desktop agent.

Sessions are JSONL transcripts under ``projects/<slug>/<session id>.jsonl``
with a per-session todo directory and an application database that carries the
title, status, and archive flag. This is the international edition; the
domestic WorkBuddy app keeps a separate store and is ``workbuddy-cn``.
"""

from __future__ import annotations

from .workbuddy_family import WorkBuddyBaseAdapter


class WorkBuddyAdapter(WorkBuddyBaseAdapter):
    """WorkBuddy AI desktop: JSONL transcripts plus one application database."""

    name = "workbuddy"
    aliases = ("workbuddy", "workbuddy-ai", "wb")
    store_hint = "~/.workbuddy-ai"
    home_dirname = ".workbuddy-ai"
    home_env = "FMS_WORKBUDDY_HOME"
    app_db_env = "FMS_WORKBUDDY_APP_DB"
