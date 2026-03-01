from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from osx_system_agent.config import (
    DEFAULTS,
    get_value,
    load_config,
    reset_config,
    save_config,
    set_value,
)


class TestLoadConfig:
    def test_returns_defaults_if_no_file(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        with (
            patch("osx_system_agent.config.CONFIG_FILE", cfg_file),
            patch("osx_system_agent.config.CONFIG_DIR", tmp_path),
        ):
            cfg = load_config()
        assert cfg == DEFAULTS

    def test_merges_user_config(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"verbose": True, "custom_key": 42}))
        with (
            patch("osx_system_agent.config.CONFIG_FILE", cfg_file),
            patch("osx_system_agent.config.CONFIG_DIR", tmp_path),
        ):
            cfg = load_config()
        assert cfg["verbose"] is True
        assert cfg["custom_key"] == 42
        assert cfg["scan_paths"] == DEFAULTS["scan_paths"]

    def test_handles_corrupt_file(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text("not valid json {{{")
        with (
            patch("osx_system_agent.config.CONFIG_FILE", cfg_file),
            patch("osx_system_agent.config.CONFIG_DIR", tmp_path),
        ):
            cfg = load_config()
        assert cfg == DEFAULTS


class TestSaveConfig:
    def test_saves_to_disk(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        with (
            patch("osx_system_agent.config.CONFIG_FILE", cfg_file),
            patch("osx_system_agent.config.CONFIG_DIR", tmp_path),
        ):
            save_config({"key": "value"})
        data = json.loads(cfg_file.read_text())
        assert data["key"] == "value"


class TestGetSetValue:
    def test_get_default(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        with (
            patch("osx_system_agent.config.CONFIG_FILE", cfg_file),
            patch("osx_system_agent.config.CONFIG_DIR", tmp_path),
        ):
            assert get_value("verbose") is False

    def test_set_and_get(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        with (
            patch("osx_system_agent.config.CONFIG_FILE", cfg_file),
            patch("osx_system_agent.config.CONFIG_DIR", tmp_path),
        ):
            set_value("verbose", True)
            assert get_value("verbose") is True

    def test_set_preserves_other_keys(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        with (
            patch("osx_system_agent.config.CONFIG_FILE", cfg_file),
            patch("osx_system_agent.config.CONFIG_DIR", tmp_path),
        ):
            set_value("verbose", True)
            set_value("custom", "hello")
            assert get_value("verbose") is True
            assert get_value("custom") == "hello"


class TestResetConfig:
    def test_resets_to_defaults(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        with (
            patch("osx_system_agent.config.CONFIG_FILE", cfg_file),
            patch("osx_system_agent.config.CONFIG_DIR", tmp_path),
        ):
            set_value("verbose", True)
            set_value("custom", "hello")
            cfg = reset_config()
        assert cfg == DEFAULTS
