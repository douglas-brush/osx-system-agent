from __future__ import annotations

import json
from pathlib import Path

from osx_system_agent.log import get_logger
from osx_system_agent.utils.paths import ensure_dir

log = get_logger("config")

CONFIG_DIR = Path.home() / ".config" / "osx-system-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS: dict = {
    "scan_paths": ["~"],
    "exclude_patterns": [],
    "min_size_duplicates": "1MB",
    "min_size_aging": "1MB",
    "min_size_caches": "10MB",
    "min_size_disk_hogs": "100MB",
    "report_dir": "~/Documents/osx-system-agent-reports",
    "schedule_interval_hours": 24,
    "verbose": False,
}


def _config_path() -> Path:
    ensure_dir(CONFIG_DIR)
    return CONFIG_FILE


def load_config() -> dict:
    """Load config from disk, merged with defaults."""
    cfg = dict(DEFAULTS)
    path = _config_path()

    if path.exists():
        try:
            user_cfg = json.loads(path.read_text())
            cfg.update(user_cfg)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("failed to load config: %s", exc)

    return cfg


def save_config(cfg: dict) -> Path:
    """Save config to disk."""
    path = _config_path()
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    log.info("saved config to %s", path)
    return path


def get_value(key: str) -> object:
    """Get a single config value."""
    cfg = load_config()
    return cfg.get(key, DEFAULTS.get(key))


def set_value(key: str, value: object) -> dict:
    """Set a single config value and save."""
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)
    return cfg


def reset_config() -> dict:
    """Reset config to defaults."""
    save_config(DEFAULTS)
    return dict(DEFAULTS)
