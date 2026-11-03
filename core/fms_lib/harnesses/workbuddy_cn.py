"""Adapter for the domestic WorkBuddy desktop agent.

The domestic edition (Tencent WorkBuddy, ``com.tencent.workbuddy.mac``) uses
the same JSONL transcript layout as WorkBuddy AI but a different store at
``~/.workbuddy``. It is a separate harness and ref namespace. Its transcripts
also carry ``<cb_summary>`` compaction records and a trailing ``summary``
record holding the initial prompt.
"""

from __future__ import annotations

from .workbuddy_family import WorkBuddyBaseAdapter


class WorkBuddyCNAdapter(WorkBuddyBaseAdapter):
    """Domestic WorkBuddy desktop: JSONL transcripts plus one application database."""

    name = "workbuddy-cn"
    aliases = ("workbuddy-cn", "workbuddycn", "workbuddy_cn", "wb-cn")
    store_hint = "~/.workbuddy"
    home_dirname = ".workbuddy"
    home_env = "FMS_WORKBUDDY_CN_HOME"
    app_db_env = "FMS_WORKBUDDY_CN_APP_DB"
