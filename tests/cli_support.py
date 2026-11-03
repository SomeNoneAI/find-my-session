from __future__ import annotations

import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "find-my-session"
SCRIPTS_DIR = SKILL_DIR / "scripts"
CORE_DIR = REPO_ROOT / "core"
FIXTURE_HOME = Path(__file__).resolve().parent / "fixtures" / "qoder-cn-home"
FIXTURE_QODER_HOME = Path(__file__).resolve().parent / "fixtures" / "qoder-home"
FIXTURE_KIMI_HOME = Path(__file__).resolve().parent / "fixtures" / "kimi-code-home"
FMS = SCRIPTS_DIR / "fms"

sys.path.insert(0, str(CORE_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fms_lib import cli  # noqa: E402
from fms_lib.harnesses.qoder_cn import QoderCNAdapter  # noqa: E402
from fms_lib.util import iter_tail_records, parse_timestamp  # noqa: E402
from codearts_fixture import (  # noqa: E402
    DISPLAY_ARCHIVED as CODEARTS_DISPLAY_ARCHIVED,
    DISPLAY_MAIN as CODEARTS_DISPLAY_MAIN,
    DISPLAY_PLAIN as CODEARTS_DISPLAY_PLAIN,
    PROMPTS_MAIN as CODEARTS_PROMPTS,
    SESSION_ARCHIVED as CODEARTS_ARCHIVED,
    SESSION_CHILD as CODEARTS_CHILD,
    SESSION_MAIN as CODEARTS_MAIN,
    SESSION_PLAIN as CODEARTS_PLAIN,
    build_codearts_home,
)
from workbuddy_fixture import (  # noqa: E402
    PROMPTS_MAIN as WORKBUDDY_PROMPTS,
    SESSION_ARCHIVED as WORKBUDDY_ARCHIVED,
    SESSION_CLOUD as WORKBUDDY_CLOUD,
    SESSION_DELETED as WORKBUDDY_DELETED,
    SESSION_MAIN as WORKBUDDY_MAIN,
    SESSION_ORPHAN as WORKBUDDY_ORPHAN,
    SESSION_PLAIN as WORKBUDDY_PLAIN,
    build_workbuddy_home,
)
from workbuddy_cn_fixture import (  # noqa: E402
    PROMPTS_MAIN as WORKBUDDY_CN_PROMPTS,
    PROMPT_ORPHAN as WORKBUDDY_CN_ORPHAN_PROMPT,
    PROMPT_PLAIN as WORKBUDDY_CN_PLAIN_PROMPT,
    SESSION_ARCHIVED as WORKBUDDY_CN_ARCHIVED,
    SESSION_EMPTY as WORKBUDDY_CN_EMPTY,
    SESSION_MAIN as WORKBUDDY_CN_MAIN,
    SESSION_ORPHAN as WORKBUDDY_CN_ORPHAN,
    SESSION_PLAIN as WORKBUDDY_CN_PLAIN,
    build_workbuddy_cn_home,
)
from codex_fixture import (  # noqa: E402
    COMPACT_SUMMARY as CODEX_COMPACT_SUMMARY,
    HAS_ZSTD as CODEX_HAS_ZSTD,
    INDEX_TITLE_MAIN as CODEX_INDEX_TITLE_MAIN,
    PROMPTS_MAIN as CODEX_PROMPTS,
    PROMPTS_RESUMED as CODEX_PROMPTS_RESUMED,
    PROMPT_ARCHIVED as CODEX_ARCHIVED_PROMPT,
    PROMPT_PLAIN as CODEX_PLAIN_PROMPT,
    PROMPT_ZSTD as CODEX_ZSTD_PROMPT,
    RESUMED_COMPACT_SUMMARY as CODEX_RESUMED_COMPACT,
    SESSION_ARCHIVED as CODEX_ARCHIVED,
    SESSION_MAIN as CODEX_MAIN,
    SESSION_PLAIN as CODEX_PLAIN,
    SESSION_RESUMED as CODEX_RESUMED,
    SESSION_SUBAGENT as CODEX_SUBAGENT,
    SESSION_ZSTD as CODEX_ZSTD,
    VERSION_MAIN as CODEX_VERSION,
    build_codex_home,
    build_codex_zstd_home,
)
from claude_code_fixture import (  # noqa: E402
    COMPACT_SESSION_SUMMARY as CLAUDE_COMPACT_SESSION_SUMMARY,
    COMPACT_SUMMARY as CLAUDE_COMPACT_SUMMARY,
    HISTORY_PROMPT as CLAUDE_HISTORY_PROMPT,
    NEEDLE_DEEP_ONLY as CLAUDE_DEEP_ONLY_NEEDLE,
    NEEDLE_SUBAGENT as CLAUDE_SUBAGENT_NEEDLE,
    NEEDLE_TOOL_OUTPUT as CLAUDE_TOOL_OUTPUT_NEEDLE,
    PROMPTS_AUX as CLAUDE_PROMPTS_AUX,
    PROMPTS_MAIN as CLAUDE_PROMPTS,
    PROMPT_COMPACT_RESUME as CLAUDE_COMPACT_RESUME_PROMPT,
    PROMPT_PLAIN as CLAUDE_PLAIN_PROMPT,
    SESSION_AUX as CLAUDE_AUX,
    SESSION_COMPACT as CLAUDE_COMPACT,
    SESSION_MAIN as CLAUDE_MAIN,
    SESSION_PLAIN as CLAUDE_PLAIN,
    TITLE_MAIN as CLAUDE_TITLE_MAIN,
    VERSION_MAIN as CLAUDE_VERSION,
    build_claude_code_home,
)
from cline_fixture import (  # noqa: E402
    BRANCH_MAIN as CLINE_BRANCH_MAIN,
    COMPACT_SUMMARY as CLINE_COMPACT_SUMMARY,
    EDITOR_ABS as CLINE_EDITOR_ABS,
    MODEL_MAIN as CLINE_MODEL_MAIN,
    NEEDLE_COMPACTION_ONLY as CLINE_COMPACTION_ONLY_NEEDLE,
    NEEDLE_DEEP_ONLY as CLINE_DEEP_ONLY_NEEDLE,
    NEEDLE_INJECTED as CLINE_INJECTED_NEEDLE,
    NEEDLE_MAIN as CLINE_MAIN_NEEDLE,
    NEEDLE_SUBAGENT as CLINE_SUBAGENT_NEEDLE,
    NEEDLE_TOOL_OUTPUT as CLINE_TOOL_OUTPUT_NEEDLE,
    PROJECT_ALPHA as CLINE_PROJECT_ALPHA,
    PROMPTS_AUX as CLINE_PROMPTS_AUX,
    PROMPTS_MAIN as CLINE_PROMPTS,
    PROMPT_COMPACT_RESUME as CLINE_COMPACT_RESUME_PROMPT,
    PROMPT_PLAIN as CLINE_PLAIN_PROMPT,
    SESSION_AUX as CLINE_AUX,
    SESSION_COMPACT as CLINE_COMPACT,
    SESSION_MAIN as CLINE_MAIN,
    SESSION_PLAIN as CLINE_PLAIN,
    SUBAGENT_STEM as CLINE_SUBAGENT_STEM,
    TITLE_COMPACT as CLINE_TITLE_COMPACT,
    TITLE_MAIN as CLINE_TITLE_MAIN,
    VERSION_MAIN as CLINE_VERSION,
    build_cline_home,
)
from grok_fixture import (  # noqa: E402
    BRANCH_MAIN as GROK_BRANCH_MAIN,
    COMPACT_SESSION_SUMMARY as GROK_COMPACT_SESSION_SUMMARY,
    COMPACT_SUMMARY as GROK_COMPACT_SUMMARY,
    GROUP_ALPHA as GROK_GROUP_ALPHA,
    GROUP_DELTA_SLUG as GROK_GROUP_DELTA_SLUG,
    MODEL_MAIN as GROK_MODEL_MAIN,
    NEEDLE_CHAT_ONLY as GROK_CHAT_ONLY_NEEDLE,
    NEEDLE_COMPACTION_ONLY as GROK_COMPACTION_ONLY_NEEDLE,
    NEEDLE_DECOY as GROK_DECOY_NEEDLE,
    NEEDLE_DEEP_ONLY as GROK_DEEP_ONLY_NEEDLE,
    NEEDLE_SUBAGENT as GROK_SUBAGENT_NEEDLE,
    NEEDLE_TOOL_OUTPUT as GROK_TOOL_OUTPUT_NEEDLE,
    PROMPTS_AUX as GROK_PROMPTS_AUX,
    PROMPTS_MAIN as GROK_PROMPTS,
    PROMPT_COMPACT_EARLY as GROK_COMPACT_EARLY_PROMPT,
    PROMPT_COMPACT_RESUME as GROK_COMPACT_RESUME_PROMPT,
    PROMPT_DECOY as GROK_DECOY_PROMPT,
    PROMPT_HIDDEN as GROK_HIDDEN_PROMPT,
    PROMPT_INTERRUPT as GROK_INTERRUPT_PROMPT,
    PROMPT_PLAIN as GROK_PLAIN_PROMPT,
    PROMPT_SLASH as GROK_SLASH_PROMPT,
    PROMPT_SYNTHETIC as GROK_SYNTHETIC_PROMPT,
    PROJECT_ALPHA as GROK_PROJECT_ALPHA,
    PROJECT_DELTA as GROK_PROJECT_DELTA,
    SESSION_AUX as GROK_AUX,
    SESSION_COMPACT as GROK_COMPACT,
    SESSION_EMPTY as GROK_EMPTY,
    SESSION_MAIN as GROK_MAIN,
    SESSION_PLAIN as GROK_PLAIN,
    SESSION_SUBAGENT as GROK_SUBAGENT,
    TITLE_MAIN as GROK_TITLE_MAIN,
    build_grok_home,
)
from zcode_fixture import (  # noqa: E402
    DISPLAY_ARCHIVED,
    DISPLAY_ARCHIVED_IN_PLACE,
    DISPLAY_CLI,
    DISPLAY_DELETED,
    DISPLAY_DESKTOP,
    PROMPTS_DESKTOP,
    SESSION_ARCHIVED,
    SESSION_DELETED,
    SESSION_DESKTOP,
    SESSION_SUBAGENT,
    build_zcode_home,
)
from antigravity_fixture import (  # noqa: E402
    CLI_NEEDLE_DB_ONLY as ANTIGRAVITY_CLI_DB_ONLY_NEEDLE,
    CLI_NEEDLE_DEEP as ANTIGRAVITY_CLI_DEEP_NEEDLE,
    CLI_NEEDLE_HISTORY as ANTIGRAVITY_CLI_HISTORY_NEEDLE,
    CLI_NEEDLE_PROTO as ANTIGRAVITY_CLI_PROTO_NEEDLE,
    CLI_PROMPT_FALLBACK as ANTIGRAVITY_CLI_FALLBACK_PROMPT,
    CLI_PROMPT_SHORT as ANTIGRAVITY_CLI_SHORT_PROMPT,
    CLI_PROMPTS as ANTIGRAVITY_CLI_PROMPTS,
    CLI_SESSION_DEEP as ANTIGRAVITY_CLI_DEEP,
    CLI_SESSION_FALLBACK as ANTIGRAVITY_CLI_FALLBACK,
    CLI_SESSION_MAIN as ANTIGRAVITY_CLI_MAIN,
    CLI_SESSION_METADATA as ANTIGRAVITY_CLI_METADATA,
    CLI_SESSION_ORPHAN as ANTIGRAVITY_CLI_ORPHAN,
    CLI_ORPHAN_BRAIN as ANTIGRAVITY_CLI_ORPHAN_BRAIN,
    NEEDLE_ARCHIVED as ANTIGRAVITY_ARCHIVED_NEEDLE,
    NEEDLE_DB_DECOY as ANTIGRAVITY_DB_DECOY_NEEDLE,
    NEEDLE_DB_ONLY as ANTIGRAVITY_DB_ONLY_NEEDLE,
    NEEDLE_DEEP as ANTIGRAVITY_DEEP_NEEDLE,
    NEEDLE_IDE_ONLY as ANTIGRAVITY_IDE_ONLY_NEEDLE,
    NEEDLE_MAIN as ANTIGRAVITY_MAIN_NEEDLE,
    NEEDLE_NESTED as ANTIGRAVITY_NESTED_NEEDLE,
    NEEDLE_ORPHAN_BRAIN as ANTIGRAVITY_ORPHAN_BRAIN_NEEDLE,
    NEEDLE_SUBAGENT as ANTIGRAVITY_SUBAGENT_NEEDLE,
    NEEDLE_TOOL_OUTPUT as ANTIGRAVITY_TOOL_OUTPUT_NEEDLE,
    PROJECT_ALPHA as ANTIGRAVITY_PROJECT_ALPHA,
    PROJECT_ARCHIVE as ANTIGRAVITY_PROJECT_ARCHIVE,
    PROJECT_CLI as ANTIGRAVITY_PROJECT_CLI,
    PROJECT_DEEP as ANTIGRAVITY_PROJECT_DEEP,
    PROJECT_LEGACY as ANTIGRAVITY_PROJECT_LEGACY,
    PROMPT_ARCHIVED as ANTIGRAVITY_ARCHIVED_PROMPT,
    PROMPT_DEEP as ANTIGRAVITY_DEEP_PROMPT,
    PROMPT_IDE_ONLY as ANTIGRAVITY_IDE_ONLY_PROMPT,
    PROMPT_MIGRATED as ANTIGRAVITY_MIGRATED_PROMPT,
    PROMPT_NESTED as ANTIGRAVITY_NESTED_PROMPT,
    PROMPT_SHORT as ANTIGRAVITY_SHORT_PROMPT,
    PROMPT_SUBAGENT as ANTIGRAVITY_SUBAGENT_PROMPT,
    PROMPT_SYSTEM as ANTIGRAVITY_SYSTEM_PROMPT,
    PROMPTS_MAIN as ANTIGRAVITY_PROMPTS,
    SESSION_ARCHIVED as ANTIGRAVITY_ARCHIVED,
    SESSION_DEEP as ANTIGRAVITY_DEEP,
    SESSION_IDE_ONLY as ANTIGRAVITY_IDE_ONLY,
    SESSION_MAIN as ANTIGRAVITY_MAIN,
    SESSION_METADATA as ANTIGRAVITY_METADATA,
    SESSION_MIGRATED as ANTIGRAVITY_MIGRATED,
    SESSION_NESTED as ANTIGRAVITY_NESTED,
    SESSION_ORPHAN as ANTIGRAVITY_ORPHAN,
    SESSION_ORPHAN_BRAIN as ANTIGRAVITY_ORPHAN_BRAIN,
    TITLE_ARCHIVED as ANTIGRAVITY_TITLE_ARCHIVED,
    TITLE_CLI_MAIN as ANTIGRAVITY_CLI_TITLE_MAIN,
    TITLE_CLI_METADATA as ANTIGRAVITY_CLI_TITLE_METADATA,
    TITLE_DEEP as ANTIGRAVITY_TITLE_DEEP,
    TITLE_MAIN as ANTIGRAVITY_TITLE_MAIN,
    TITLE_METADATA as ANTIGRAVITY_TITLE_METADATA,
    TITLE_MIGRATED as ANTIGRAVITY_TITLE_MIGRATED,
    build_antigravity_cli_home,
    build_antigravity_home,
    build_antigravity_ide_home,
)
from minimax_code_fixture import build_minimax_code_home  # noqa: E402
from cursor_fixture import build_cursor_home  # noqa: E402
from deepseek_fixture import (  # noqa: E402
    COMPACT_SUMMARY as DEEPSEEK_COMPACT_SUMMARY,
    HAS_ZSTD as DEEPSEEK_HAS_ZSTD,
    MODEL_ALT as DEEPSEEK_MODEL_ALT,
    NEEDLE_ARCHIVED as DEEPSEEK_ARCHIVED_NEEDLE,
    NEEDLE_DEEP_ONLY as DEEPSEEK_DEEP_ONLY_NEEDLE,
    NEEDLE_SUBAGENT as DEEPSEEK_SUBAGENT_NEEDLE,
    NEEDLE_TOOL_OUTPUT as DEEPSEEK_TOOL_OUTPUT_NEEDLE,
    PROJECT_ALPHA as DEEPSEEK_PROJECT_ALPHA,
    PROJECT_BETA as DEEPSEEK_PROJECT_BETA,
    PROJECT_GAMMA as DEEPSEEK_PROJECT_GAMMA,
    PROMPTS_MAIN as DEEPSEEK_PROMPTS,
    PROMPT_ARCHIVED as DEEPSEEK_ARCHIVED_PROMPT,
    PROMPT_IMAGE_ONLY as DEEPSEEK_IMAGE_ONLY_PROMPT,
    PROMPT_MULTI as DEEPSEEK_MULTI_PROMPT,
    PROMPT_MULTI_ABANDONED as DEEPSEEK_ABANDONED_PROMPT,
    PROMPT_PLAIN as DEEPSEEK_PLAIN_PROMPT,
    PROMPT_SUBAGENT as DEEPSEEK_SUBAGENT_PROMPT,
    SESSION_ARCHIVED as DEEPSEEK_ARCHIVED,
    SESSION_EMPTY as DEEPSEEK_EMPTY,
    SESSION_MAIN as DEEPSEEK_MAIN,
    SESSION_MULTI as DEEPSEEK_MULTI,
    SESSION_PLAIN as DEEPSEEK_PLAIN,
    SESSION_SUBAGENT as DEEPSEEK_SUBAGENT,
    TITLE_ARCHIVED as DEEPSEEK_TITLE_ARCHIVED,
    TITLE_MAIN as DEEPSEEK_TITLE_MAIN,
    TITLE_MULTI as DEEPSEEK_TITLE_MULTI,
    TODOS_LATEST as DEEPSEEK_TODOS,
    build_deepseek_home,
    decompress as deepseek_decompress,
)

SESSION_A = "a1b2c3d4-1111-4a1b-8c1d-111111111111"
SESSION_B = "b2c3d4e5-2222-4b2c-9d2e-222222222222"
SESSION_C = "c3d4e5f6-3333-4c3d-9e4f-333333333333"
SESSION_D = "d4e5f6a7-4444-4d4e-8f5a-444444444444"
SESSION_E = "e5f6a7b8-5555-4e5f-9a6b-555555555555"
SESSION_F = "f6a7b8c9-6666-4f6a-8b7c-666666666666"
SESSION_G = "a7b8c9d0-7777-4a7b-9c8d-777777777777"


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> float:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp()


SESSION_STAMPS = {
    SESSION_A: _utc(2026, 10, 20, 9, 10),
    SESSION_B: _utc(2026, 10, 27, 15, 30),
    SESSION_C: _utc(2026, 10, 21, 10, 5),
    SESSION_D: _utc(2026, 10, 24, 11, 10),
}


def _copy_fixture_home(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    for path in destination.rglob("*"):
        if not path.is_file() or path.suffix != ".jsonl":
            continue
        stamp = SESSION_STAMPS.get(path.stem, _utc(2026, 10, 26, 12, 0))
        os.utime(path, (stamp, stamp))
    return destination


def _write_archive_db(path: Path, rows) -> Path:
    connection = sqlite3.connect(str(path))
    try:
        connection.execute(
            "CREATE TABLE chat_sessions ("
            "session_id TEXT PRIMARY KEY, "
            "archived INTEGER NOT NULL DEFAULT 0, "
            "archived_at INTEGER, "
            "deleted_at INTEGER)"
        )
        connection.executemany(
            "INSERT INTO chat_sessions "
            "(session_id, archived, archived_at, deleted_at) VALUES (?, ?, ?, ?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()
    return path


class FixtureTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory(prefix="fms-tests-")
        root = Path(cls._temp.name)
        cls.home = _copy_fixture_home(FIXTURE_HOME, root / "cn-home")
        cls.qoder_home = _copy_fixture_home(FIXTURE_QODER_HOME, root / "qoder-home")
        cls.kimi_home = _copy_fixture_home(
            FIXTURE_KIMI_HOME, root / "kimi-home"
        )
        cls.zcode_home = build_zcode_home(root / "zcode-home")
        cls.zcode_app_db = cls.zcode_home / "v2" / "tasks-index.sqlite"
        cls.empty_zcode_home = root / "empty-zcode-home"
        cls.empty_zcode_home.mkdir()
        cls.minimax_code_home = build_minimax_code_home(
            root / "minimax-code-home"
        )
        cls.minimax_code_db = (
            cls.minimax_code_home / "sqlite" / "runtime-state.sqlite"
        )
        cls.empty_minimax_code_home = root / "empty-minimax-code-home"
        cls.empty_minimax_code_home.mkdir()
        cls.no_minimax_code_db = root / "missing-minimax-code.sqlite"
        cls.codearts_home = build_codearts_home(root / "codearts-home")
        cls.empty_codearts_home = root / "empty-codearts-home"
        cls.empty_codearts_home.mkdir()
        cls.workbuddy_home = build_workbuddy_home(root / "workbuddy-home")
        cls.workbuddy_db = cls.workbuddy_home / "workbuddy.db"
        cls.workbuddy_cn_home = build_workbuddy_cn_home(
            root / "workbuddy-cn-home"
        )
        cls.workbuddy_cn_db = cls.workbuddy_cn_home / "workbuddy.db"
        cls.codex_home = build_codex_home(root / "codex-home")
        cls.codex_zstd_home = build_codex_zstd_home(root / "codex-zstd-home")
        cls.claude_home = build_claude_code_home(root / "claude-home")
        cls.cline_home = build_cline_home(root / "cline-home")
        cls.empty_cline_home = root / "empty-cline-home"
        cls.empty_cline_home.mkdir()
        cls.grok_home = build_grok_home(root / "grok-home")
        cls.antigravity_home = build_antigravity_home(root / "antigravity-home")
        cls.antigravity_ide_home = build_antigravity_ide_home(
            root / "antigravity-ide-home"
        )
        cls.antigravity_cli_home = build_antigravity_cli_home(
            root / "antigravity-cli-home"
        )
        cls.deepseek_home = build_deepseek_home(root / "deepseek-home")
        cls.deepseek_no_workspace_home = root / "deepseek-no-workspace-home"
        shutil.copytree(cls.deepseek_home, cls.deepseek_no_workspace_home)
        (cls.deepseek_no_workspace_home / "storages" / "workspace.json").unlink()
        cls.empty_deepseek_home = root / "empty-deepseek-home"
        cls.empty_deepseek_home.mkdir()
        cls.empty_codex_home = root / "empty-codex-home"
        cls.empty_codex_home.mkdir()
        cls.cursor_home = build_cursor_home(root / "cursor-home")
        cls.cursor_db = (
            cls.cursor_home / "User" / "globalStorage" / "conversation-search.db"
        )
        cls.empty_cursor_home = root / "empty-cursor-home"
        cls.empty_cursor_home.mkdir()
        cls.no_cursor_db = root / "missing-conversation-search.db"
        cls.empty_claude_home = root / "empty-claude-home"
        cls.empty_claude_home.mkdir()
        cls.empty_grok_home = root / "empty-grok-home"
        cls.empty_grok_home.mkdir()
        cls.empty_antigravity_home = root / "empty-antigravity-home"
        cls.empty_antigravity_home.mkdir()
        cls.empty_antigravity_ide_home = root / "empty-antigravity-ide-home"
        cls.empty_antigravity_ide_home.mkdir()
        cls.empty_antigravity_cli_home = root / "empty-antigravity-cli-home"
        cls.empty_antigravity_cli_home.mkdir()
        cls.empty_workbuddy_home = root / "empty-workbuddy-home"
        cls.empty_workbuddy_home.mkdir()
        cls.empty_workbuddy_cn_home = root / "empty-workbuddy-cn-home"
        cls.empty_workbuddy_cn_home.mkdir()
        cls.no_workbuddy_db = root / "missing-workbuddy.db"
        cls.no_workbuddy_cn_db = root / "missing-workbuddy-cn.db"
        cls.no_app_db = root / "missing-main.sqlite"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp.cleanup()

    def run_cli(
        self,
        *args: str,
        home: Path = None,
        qoder_home: Path = None,
        kimi_home: Path = None,
        zcode_home: Path = None,
        codearts_home: Path = None,
        workbuddy_home: Path = None,
        workbuddy_cn_home: Path = None,
        codex_home: Path = None,
        claude_home: Path = None,
        cline_home: Path = None,
        grok_home: Path = None,
        antigravity_home: Path = None,
        antigravity_ide_home: Path = None,
        antigravity_cli_home: Path = None,
        deepseek_home: Path = None,
        minimax_code_home: Path = None,
        cursor_home: Path = None,
        cn_db: Path = None,
        qoder_db: Path = None,
        zcode_app_db: Path = None,
        workbuddy_db: Path = None,
        workbuddy_cn_db: Path = None,
        minimax_code_app_db: Path = None,
        cursor_app_db: Path = None,
    ):
        out = io.StringIO()
        err = io.StringIO()
        env = {
            "FMS_QODER_CN_HOME": str(home or self.home),
            "FMS_QODER_HOME": str(qoder_home or self.qoder_home),
            "FMS_KIMI_CODE_HOME": str(kimi_home or self.kimi_home),
            "FMS_ZCODE_HOME": str(zcode_home or self.zcode_home),
            "FMS_CODEARTS_HOME": str(codearts_home or self.codearts_home),
            "FMS_WORKBUDDY_HOME": str(workbuddy_home or self.workbuddy_home),
            "FMS_WORKBUDDY_CN_HOME": str(
                workbuddy_cn_home or self.workbuddy_cn_home
            ),
            "FMS_CODEX_HOME": str(codex_home or self.codex_home),
            "FMS_CLAUDE_HOME": str(claude_home or self.claude_home),
            "FMS_CLINE_HOME": str(cline_home or self.cline_home),
            "FMS_GROK_HOME": str(grok_home or self.grok_home),
            "FMS_ANTIGRAVITY_HOME": str(
                antigravity_home or self.antigravity_home
            ),
            "FMS_ANTIGRAVITY_IDE_HOME": str(
                antigravity_ide_home or self.antigravity_ide_home
            ),
            "FMS_ANTIGRAVITY_CLI_HOME": str(
                antigravity_cli_home or self.antigravity_cli_home
            ),
            "FMS_DEEPSEEK_HOME": str(deepseek_home or self.deepseek_home),
            "FMS_MINIMAX_CODE_HOME": str(
                minimax_code_home or self.minimax_code_home
            ),
            "FMS_CURSOR_HOME": str(cursor_home or self.cursor_home),
            "FMS_CURSOR_APP_DB": str(cursor_app_db or self.cursor_db),
            "FMS_QODER_CN_APP_DB": str(cn_db or self.no_app_db),
            "FMS_QODER_APP_DB": str(qoder_db or self.no_app_db),
            "FMS_ZCODE_APP_DB": str(zcode_app_db or self.zcode_app_db),
            "FMS_WORKBUDDY_APP_DB": str(workbuddy_db or self.workbuddy_db),
            "FMS_WORKBUDDY_CN_APP_DB": str(
                workbuddy_cn_db or self.workbuddy_cn_db
            ),
            "FMS_MINIMAX_CODE_APP_DB": str(
                minimax_code_app_db or self.minimax_code_db
            ),
        }
        with mock.patch.dict(os.environ, env):
            with redirect_stdout(out), redirect_stderr(err):
                code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def run_json(
        self,
        *args: str,
        home: Path = None,
        qoder_home: Path = None,
        kimi_home: Path = None,
        zcode_home: Path = None,
        codearts_home: Path = None,
        workbuddy_home: Path = None,
        workbuddy_cn_home: Path = None,
        codex_home: Path = None,
        claude_home: Path = None,
        cline_home: Path = None,
        grok_home: Path = None,
        antigravity_home: Path = None,
        antigravity_ide_home: Path = None,
        antigravity_cli_home: Path = None,
        deepseek_home: Path = None,
        minimax_code_home: Path = None,
        cursor_home: Path = None,
        cn_db: Path = None,
        qoder_db: Path = None,
        zcode_app_db: Path = None,
        workbuddy_db: Path = None,
        workbuddy_cn_db: Path = None,
        minimax_code_app_db: Path = None,
        cursor_app_db: Path = None,
    ):
        code, out, err = self.run_cli(
            *args,
            "--json",
            home=home,
            qoder_home=qoder_home,
            kimi_home=kimi_home,
            zcode_home=zcode_home,
            codearts_home=codearts_home,
            workbuddy_home=workbuddy_home,
            workbuddy_cn_home=workbuddy_cn_home,
            cn_db=cn_db,
            qoder_db=qoder_db,
            zcode_app_db=zcode_app_db,
            workbuddy_db=workbuddy_db,
            workbuddy_cn_db=workbuddy_cn_db,
            codex_home=codex_home,
            claude_home=claude_home,
            cline_home=cline_home,
            grok_home=grok_home,
            antigravity_home=antigravity_home,
            antigravity_ide_home=antigravity_ide_home,
            antigravity_cli_home=antigravity_cli_home,
            deepseek_home=deepseek_home,
            minimax_code_home=minimax_code_home,
            minimax_code_app_db=minimax_code_app_db,
            cursor_home=cursor_home,
            cursor_app_db=cursor_app_db,
        )
        self.assertEqual(code, 0, err)
        return json.loads(out)
