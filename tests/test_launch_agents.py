from __future__ import annotations

import plistlib
from pathlib import Path

from osx_system_agent.scanners.launch_agents import LaunchItem, scan_launch_agents


class TestScanLaunchAgents:
    def _create_plist(self, directory: Path, label: str, program: str = "/usr/bin/true") -> Path:
        plist_path = directory / f"{label}.plist"
        data = {
            "Label": label,
            "ProgramArguments": [program],
            "RunAtLoad": True,
        }
        with plist_path.open("wb") as f:
            plistlib.dump(data, f)
        return plist_path

    def test_finds_plists(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "LaunchAgents"
        agent_dir.mkdir()
        self._create_plist(agent_dir, "com.test.agent")

        items = scan_launch_agents(dirs=[agent_dir])
        assert len(items) == 1
        assert items[0].label == "com.test.agent"
        assert isinstance(items[0], LaunchItem)

    def test_run_at_load(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "LaunchAgents"
        agent_dir.mkdir()
        self._create_plist(agent_dir, "com.test.loader")

        items = scan_launch_agents(dirs=[agent_dir])
        assert items[0].run_at_load is True

    def test_handles_missing_dir(self) -> None:
        items = scan_launch_agents(dirs=[Path("/nonexistent/path")])
        assert items == []

    def test_handles_invalid_plist(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "LaunchAgents"
        agent_dir.mkdir()
        (agent_dir / "bad.plist").write_text("not a plist")

        items = scan_launch_agents(dirs=[agent_dir])
        assert len(items) == 1
        assert items[0].error is not None

    def test_multiple_agents(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "LaunchAgents"
        agent_dir.mkdir()
        self._create_plist(agent_dir, "com.alpha.agent")
        self._create_plist(agent_dir, "com.beta.agent")

        items = scan_launch_agents(dirs=[agent_dir])
        assert len(items) == 2
        labels = {i.label for i in items}
        assert "com.alpha.agent" in labels
        assert "com.beta.agent" in labels
