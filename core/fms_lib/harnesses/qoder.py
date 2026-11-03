from __future__ import annotations

from .qoder_family import QoderFamilyAdapter


class QoderAdapter(QoderFamilyAdapter):
    name = "qoder"
    aliases = ("qoder", "qoder-intl", "qoder-global", "qoder-international")
    variants = "desktop, cli"
    store_hint = "~/.qoder"
    default_home_dir = ".qoder"
    home_env = "FMS_QODER_HOME"
    app_bundle_dirs = ("com.qoder.app.stable", "Qoder")
    app_db_env = "FMS_QODER_APP_DB"
