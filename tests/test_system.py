from __future__ import annotations

from osx_system_agent.system.activity import (
    BatteryStatus,
    SystemStatus,
    get_battery_status,
    get_system_status,
)
from osx_system_agent.system.processes import ProcessInfo, snapshot_processes


class TestGetSystemStatus:
    def test_returns_system_status(self) -> None:
        result = get_system_status()
        assert isinstance(result, SystemStatus)

    def test_cpu_in_range(self) -> None:
        result = get_system_status()
        assert 0 <= result.cpu_percent <= 100 * 128  # multi-core can exceed 100

    def test_memory_fields(self) -> None:
        result = get_system_status()
        assert result.memory_total > 0
        assert result.memory_used > 0
        assert result.memory_available > 0
        assert result.memory_used <= result.memory_total

    def test_disk_fields(self) -> None:
        result = get_system_status()
        assert result.disk_total > 0
        assert result.disk_used > 0
        assert result.disk_free >= 0
        assert result.disk_used <= result.disk_total

    def test_battery_type(self) -> None:
        result = get_system_status()
        # Battery can be None on desktops
        if result.battery is not None:
            assert isinstance(result.battery, BatteryStatus)


class TestGetBatteryStatus:
    def test_returns_battery_or_none(self) -> None:
        result = get_battery_status()
        assert result is None or isinstance(result, BatteryStatus)

    def test_battery_fields_if_present(self) -> None:
        result = get_battery_status()
        if result is not None:
            if result.percent is not None:
                assert 0 <= result.percent <= 100
            assert isinstance(result.power_plugged, bool | type(None))


class TestSnapshotProcesses:
    def test_returns_list(self) -> None:
        result = snapshot_processes(limit=5)
        assert isinstance(result, list)
        assert len(result) <= 5

    def test_returns_process_info(self) -> None:
        result = snapshot_processes(limit=3)
        for proc in result:
            assert isinstance(proc, ProcessInfo)
            assert isinstance(proc.pid, int)
            assert isinstance(proc.name, str)
            assert isinstance(proc.cpu_percent, float)
            assert isinstance(proc.memory_rss, int)

    def test_sort_by_cpu(self) -> None:
        result = snapshot_processes(sort="cpu", limit=10)
        cpus = [p.cpu_percent for p in result]
        assert cpus == sorted(cpus, reverse=True)

    def test_sort_by_mem(self) -> None:
        result = snapshot_processes(sort="mem", limit=10)
        mems = [p.memory_rss for p in result]
        assert mems == sorted(mems, reverse=True)
