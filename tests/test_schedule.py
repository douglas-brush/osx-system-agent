from __future__ import annotations

import plistlib
from pathlib import Path
from unittest.mock import patch

from osx_system_agent.schedule import generate_launchagent, remove_launchagent


class TestGenerateLaunchAgent:
    def test_creates_plist(self, tmp_path: Path) -> None:
        with (
            patch("osx_system_agent.schedule.PLIST_DIR", tmp_path),
            patch("osx_system_agent.schedule._find_osa_binary", return_value="/usr/bin/osa"),
        ):
            plist_path = generate_launchagent(
                interval_hours=12,
                report_dir=str(tmp_path / "reports"),
                label="com.test.agent",
            )

        assert plist_path.exists()
        with plist_path.open("rb") as f:
            data = plistlib.load(f)

        assert data["Label"] == "com.test.agent"
        assert data["StartInterval"] == 12 * 3600
        assert "/usr/bin/osa" in data["ProgramArguments"]

    def test_interval_calculation(self, tmp_path: Path) -> None:
        with (
            patch("osx_system_agent.schedule.PLIST_DIR", tmp_path),
            patch("osx_system_agent.schedule._find_osa_binary", return_value="/usr/bin/osa"),
        ):
            plist_path = generate_launchagent(interval_hours=6, label="com.test.6h")

        with plist_path.open("rb") as f:
            data = plistlib.load(f)
        assert data["StartInterval"] == 21600


class TestRemoveLaunchAgent:
    def test_removes_existing(self, tmp_path: Path) -> None:
        plist = tmp_path / "com.test.remove.plist"
        plist.write_text("test")
        with patch("osx_system_agent.schedule.PLIST_DIR", tmp_path):
            assert remove_launchagent(label="com.test.remove") is True
        assert not plist.exists()

    def test_returns_false_if_missing(self, tmp_path: Path) -> None:
        with patch("osx_system_agent.schedule.PLIST_DIR", tmp_path):
            assert remove_launchagent(label="com.nonexistent") is False
