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


def _apfs_container_usage() -> tuple[int, int, int] | None:
    """Get real disk usage from the APFS container (macOS).

    psutil/df report per-volume stats which are misleading on APFS —
    the 'used' value only covers one volume while 'total' is the shared
    container ceiling.  This function returns (total, used, free) for
    the container that holds the root filesystem.
    """
    try:
        output = subprocess.check_output(
            ["diskutil", "apfs", "list"], text=True, timeout=10,
        )
    except Exception:
        return None

    # Find the container block that contains the "/" mount
    containers = output.split("+-- Container ")
    for block in containers:
        if "Mount Point:" not in block:
            continue
        # Look for the container whose volume is mounted at /
        has_root = (
            re.search(r"Snapshot Mount Point:\s+/\s*$", block, re.MULTILINE)
            or re.search(r"Mount Point:\s+/\s*$", block, re.MULTILINE)
        )
        if not has_root:
            continue

        cap_match = re.search(
            r"Size \(Capacity Ceiling\):\s+(\d+)\s+B", block,
        )
        used_match = re.search(
            r"Capacity In Use By Volumes:\s+(\d+)\s+B", block,
        )
        free_match = re.search(
            r"Capacity Not Allocated:\s+(\d+)\s+B", block,
        )
        if cap_match and used_match and free_match:
            total = int(cap_match.group(1))
            used = int(used_match.group(1))
            free = int(free_match.group(1))
            return total, used, free

    return None


def get_system_status(path: str = "/") -> SystemStatus:
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    battery = get_battery_status()

    # Prefer APFS container-level stats on macOS for accurate numbers
    apfs = _apfs_container_usage()
    if apfs:
        disk_total, disk_used, disk_free = apfs
    else:
        disk = psutil.disk_usage(path)
        disk_total, disk_used, disk_free = disk.total, disk.used, disk.free

    return SystemStatus(
        cpu_percent=cpu,
        memory_total=mem.total,
        memory_used=mem.used,
        memory_available=mem.available,
        disk_total=disk_total,
        disk_used=disk_used,
        disk_free=disk_free,
        battery=battery,
    )
