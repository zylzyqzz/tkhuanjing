"""Single source of product and wire-contract metadata."""

APP_NAME = "VD开播助手"
APP_VERSION = "2.10.0"
REPORT_SCHEMA_VERSION = 6
UPDATE_CHANNEL = "stable"
SUPPORTED_REPORT_SCHEMAS = frozenset({4, 5, 6})
CURRENT_CHECK_CATEGORIES = frozenset({"网络环境", "系统环境", "电脑性能"})
CURRENT_CHECK_PREFIXES = ("network.", "system.", "environment.", "performance.")
