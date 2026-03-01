from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

import psutil


@dataclass
class BatteryStatus:
    percent: float | None
    power_plugged: bool | None
    raw: str | None = None


@dataclass
class SystemStatus:
    cpu_percent: float
    memory_total: int
    memory_used: int
    memory_available: int
    disk_total: int
    disk_used: int
    disk_free: int
    battery: BatteryStatus | None


def _battery_from_pmset() -> BatteryStatus | None:
    try:
        output = subprocess.check_output(["pmset", "-g", "batt"], text=True)
    except Exception:
        return None

    # Example: "Now drawing from 'Battery Power'"
    # and "-InternalBattery-0 87%; discharging; (no estimate)"
    percent_match = re.search(r"(\d+)%", output)
    plugged = "AC Power" in output
    percent = float(percent_match.group(1)) if percent_match else None
    return BatteryStatus(percent=percent, power_plugged=plugged, raw=output.strip())


def get_battery_status() -> BatteryStatus | None:
    try:
        batt = psutil.sensors_battery()
        if batt:
            return BatteryStatus(percent=batt.percent, power_plugged=batt.power_plugged)
    except Exception:
        pass
    return _battery_from_pmset()


def get_system_status(path: str = "/") -> SystemStatus:
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(path)
    battery = get_battery_status()

    return SystemStatus(
        cpu_percent=cpu,
        memory_total=mem.total,
        memory_used=mem.used,
        memory_available=mem.available,
        disk_total=disk.total,
        disk_used=disk.used,
        disk_free=disk.free,
        battery=battery,
    )
