"""Single source of truth for shared presentation limits.

Every CLI and MCP default that shapes how much of a session is shown lives
here so the surfaces cannot drift apart. Frontend presentation limits (the
browser panel) stay with the frontend by design; see ``fms_ui/server.py``.
"""

# search and latest
SEARCH_LIMIT_DEFAULT = 10
LATEST_LIMIT_DEFAULT = 1

# show digest
SHOW_MESSAGES_DEFAULT = 2
SHOW_CHARS_DEFAULT = 600
SHOW_SUMMARY_CHARS_DEFAULT = 1000

# prompts; 0 means full text / no limit
PROMPTS_CHARS_DEFAULT = 0
PROMPTS_LIMIT_DEFAULT = 0
PROMPTS_OFFSET_DEFAULT = 0
