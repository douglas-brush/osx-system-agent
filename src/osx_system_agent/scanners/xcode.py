from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from osx_system_agent.log import get_logger

log = get_logger("scanners.xcode")


@dataclass
class DerivedDataProject:
    name: str
    path: Path
    size: int
    last_modified: float


@dataclass
class XcodeArchive:
    name: str
    path: Path
    size: int


@dataclass
class Simulator:
    name: str
    udid: str
    runtime: str
    state: str
    data_size: int


@dataclass
class XcodeAudit:
    derived_data: list[DerivedDataProject] = field(default_factory=list)
    derived_data_total: int = 0
    archives: list[XcodeArchive] = field(default_factory=list)
    archives_total: int = 0
    simulators: list[Simulator] = field(default_factory=list)
    simulators_unavailable: list[Simulator] = field(default_factory=list)
    xcode_installed: bool = False


def _dir_size(path: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path, followlinks=False):
        for name in filenames:
            try:
                total += (Path(dirpath) / name).stat().st_size
            except OSError:
                continue
    return total


def _scan_derived_data() -> tuple[list[DerivedDataProject], int]:
    dd_path = Path.home() / "Library" / "Developer" / "Xcode" / "DerivedData"
    if not dd_path.exists():
        return [], 0

    projects: list[DerivedDataProject] = []
    total = 0

    for entry in dd_path.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        size = _dir_size(entry)
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            mtime = 0.0

        projects.append(DerivedDataProject(
            name=entry.name.rsplit("-", 1)[0],  # strip hash suffix
            path=entry,
            size=size,
            last_modified=mtime,
        ))
        total += size

    projects.sort(key=lambda p: p.size, reverse=True)
    return projects, total


def _scan_archives() -> tuple[list[XcodeArchive], int]:
    archive_path = Path.home() / "Library" / "Developer" / "Xcode" / "Archives"
    if not archive_path.exists():
        return [], 0

    archives: list[XcodeArchive] = []
    total = 0

    # Archives are organized by date subdirectories
    for date_dir in archive_path.iterdir():
        if not date_dir.is_dir():
            continue
        for xcarchive in date_dir.iterdir():
            if xcarchive.suffix != ".xcarchive":
                continue
            size = _dir_size(xcarchive)
            archives.append(XcodeArchive(
                name=xcarchive.stem,
                path=xcarchive,
                size=size,
            ))
            total += size

    archives.sort(key=lambda a: a.size, reverse=True)
    return archives, total


def _scan_simulators() -> tuple[list[Simulator], list[Simulator]]:
    """Parse simulators from simctl."""
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "-j"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return [], []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return [], []

    import json
    data = json.loads(result.stdout)
    devices = data.get("devices", {})

    available: list[Simulator] = []
    unavailable: list[Simulator] = []

    sim_data_root = (
        Path.home() / "Library" / "Developer"
        / "CoreSimulator" / "Devices"
    )

    for runtime, device_list in devices.items():
        runtime_name = runtime.replace(
            "com.apple.CoreSimulator.SimRuntime.", ""
        ).replace("-", " ").replace(".", " ")

        for dev in device_list:
            udid = dev.get("udid", "")
            data_path = sim_data_root / udid
            size = _dir_size(data_path) if data_path.exists() else 0

            sim = Simulator(
                name=dev.get("name", ""),
                udid=udid,
                runtime=runtime_name,
                state=dev.get("state", ""),
                data_size=size,
            )

            if dev.get("isAvailable", True):
                available.append(sim)
            else:
                unavailable.append(sim)

    available.sort(key=lambda s: s.data_size, reverse=True)
    unavailable.sort(key=lambda s: s.data_size, reverse=True)
    return available, unavailable


def scan_xcode() -> XcodeAudit:
    """Audit Xcode disk usage: DerivedData, Archives, Simulators."""
    xcode_installed = (
        Path("/Applications/Xcode.app").exists()
        or Path.home().joinpath(
            "Library", "Developer", "Xcode"
        ).exists()
    )

    derived, dd_total = _scan_derived_data()
    archives, arch_total = _scan_archives()
    available, unavailable = _scan_simulators()

    return XcodeAudit(
        derived_data=derived,
        derived_data_total=dd_total,
        archives=archives,
        archives_total=arch_total,
        simulators=available,
        simulators_unavailable=unavailable,
        xcode_installed=xcode_installed,
    )
