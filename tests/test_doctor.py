from __future__ import annotations

from unittest.mock import MagicMock, patch

from osx_system_agent.doctor import DiagnosticItem, run_diagnostics


def _mock_system_status(disk_pct: float = 50.0, mem_pct: float = 50.0):
    """Create a mock SystemStatus with given usage percentages."""
    total_disk = 1_000_000_000_000  # 1TB
    used_disk = int(total_disk * disk_pct / 100)
    free_disk = total_disk - used_disk

    total_mem = 16_000_000_000  # 16GB
    used_mem = int(total_mem * mem_pct / 100)

    mock = MagicMock()
    mock.disk_total = total_disk
    mock.disk_used = used_disk
    mock.disk_free = free_disk
    mock.memory_total = total_mem
    mock.memory_used = used_mem
    mock.cpu_percent = 25.0
    mock.battery = None
    return mock


class TestRunDiagnostics:
    @patch("osx_system_agent.doctor.scan_launch_agents", return_value=[])
    @patch("osx_system_agent.doctor.scan_disk_hogs", return_value=[])
    @patch("osx_system_agent.doctor.scan_caches", return_value=[])
    @patch("osx_system_agent.doctor.get_system_status")
    def test_healthy_system(
        self, mock_status, mock_caches, mock_hogs, mock_agents
    ) -> None:
        mock_status.return_value = _mock_system_status(
            disk_pct=50, mem_pct=50
        )
        items = run_diagnostics()
        severities = [i.severity for i in items]
        assert "critical" not in severities

    @patch("osx_system_agent.doctor.scan_launch_agents", return_value=[])
    @patch("osx_system_agent.doctor.scan_disk_hogs", return_value=[])
    @patch("osx_system_agent.doctor.scan_caches", return_value=[])
    @patch("osx_system_agent.doctor.get_system_status")
    def test_critical_disk(
        self, mock_status, mock_caches, mock_hogs, mock_agents
    ) -> None:
        mock_status.return_value = _mock_system_status(disk_pct=95)
        items = run_diagnostics()
        disk_items = [i for i in items if i.category == "disk"]
        assert len(disk_items) == 1
        assert disk_items[0].severity == "critical"

    @patch("osx_system_agent.doctor.scan_launch_agents", return_value=[])
    @patch("osx_system_agent.doctor.scan_disk_hogs", return_value=[])
    @patch("osx_system_agent.doctor.scan_caches", return_value=[])
    @patch("osx_system_agent.doctor.get_system_status")
    def test_warning_disk(
        self, mock_status, mock_caches, mock_hogs, mock_agents
    ) -> None:
        mock_status.return_value = _mock_system_status(disk_pct=85)
        items = run_diagnostics()
        disk_items = [i for i in items if i.category == "disk"]
        assert disk_items[0].severity == "warning"

    @patch("osx_system_agent.doctor.scan_launch_agents", return_value=[])
    @patch("osx_system_agent.doctor.scan_disk_hogs", return_value=[])
    @patch("osx_system_agent.doctor.scan_caches", return_value=[])
    @patch("osx_system_agent.doctor.get_system_status")
    def test_returns_diagnostic_items(
        self, mock_status, mock_caches, mock_hogs, mock_agents
    ) -> None:
        mock_status.return_value = _mock_system_status()
        items = run_diagnostics()
        assert all(isinstance(i, DiagnosticItem) for i in items)
        assert len(items) >= 2  # at least disk + memory

    @patch("osx_system_agent.doctor.scan_launch_agents", return_value=[])
    @patch("osx_system_agent.doctor.scan_disk_hogs", return_value=[])
    @patch("osx_system_agent.doctor.scan_caches", return_value=[])
    @patch("osx_system_agent.doctor.get_system_status")
    def test_high_memory_warning(
        self, mock_status, mock_caches, mock_hogs, mock_agents
    ) -> None:
        mock_status.return_value = _mock_system_status(mem_pct=95)
        items = run_diagnostics()
        mem_items = [i for i in items if i.category == "memory"]
        assert len(mem_items) == 1
        assert mem_items[0].severity == "warning"
