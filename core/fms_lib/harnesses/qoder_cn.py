from __future__ import annotations

from .qoder_family import QoderFamilyAdapter


class QoderCNAdapter(QoderFamilyAdapter):
    name = "qoder-cn"
    aliases = ("qoder-cn", "qodercn", "qoder_cn", "qcn")
    variants = "desktop, cli"
    store_hint = "~/.qoder-cn"
    default_home_dir = ".qoder-cn"
    home_env = "FMS_QODER_CN_HOME"
    app_bundle_dirs = ("com.qodercn.app.stable", "QoderCN")
    app_db_env = "FMS_QODER_CN_APP_DB"
