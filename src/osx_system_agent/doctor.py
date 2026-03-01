from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from osx_system_agent.log import get_logger
from osx_system_agent.scanners.caches import scan_caches
from osx_system_agent.scanners.disk_hogs import scan_disk_hogs
from osx_system_agent.scanners.junk import scan_junk
from osx_system_agent.scanners.launch_agents import scan_launch_agents
from osx_system_agent.system.activity import get_system_status
from osx_system_agent.utils.human import bytes_to_human

log = get_logger("doctor")


@dataclass
class DiagnosticItem:
    category: str
    severity: str  # "info", "warning", "critical"
    message: str
    suggestion: str


def run_diagnostics(scan_path: Path | None = None) -> list[DiagnosticItem]:
    """Run system health diagnostics and return findings."""
    items: list[DiagnosticItem] = []

    # Disk space check
    sys_status = get_system_status()
    disk_pct = (sys_status.disk_used / sys_status.disk_total * 100
                if sys_status.disk_total > 0 else 0)

    if disk_pct > 90:
        items.append(DiagnosticItem(
            category="disk",
            severity="critical",
            message=f"Disk {disk_pct:.0f}% full "
                    f"({bytes_to_human(sys_status.disk_free)} free)",
            suggestion="Run 'osa clean caches --no-dry-run' to free cache space",
        ))
    elif disk_pct > 80:
        items.append(DiagnosticItem(
            category="disk",
            severity="warning",
            message=f"Disk {disk_pct:.0f}% full "
                    f"({bytes_to_human(sys_status.disk_free)} free)",
            suggestion="Review 'osa scan disk-hogs' for cleanup opportunities",
        ))
    else:
        items.append(DiagnosticItem(
            category="disk",
            severity="info",
            message=f"Disk {disk_pct:.0f}% full "
                    f"({bytes_to_human(sys_status.disk_free)} free)",
            suggestion="",
        ))

    # Memory check
    mem_pct = (sys_status.memory_used / sys_status.memory_total * 100
               if sys_status.memory_total > 0 else 0)
    if mem_pct > 90:
        items.append(DiagnosticItem(
            category="memory",
            severity="warning",
            message=f"Memory {mem_pct:.0f}% used "
                    f"({bytes_to_human(sys_status.memory_used)})",
            suggestion="Check 'osa processes --sort mem' for heavy consumers",
        ))
    else:
        items.append(DiagnosticItem(
            category="memory",
            severity="info",
            message=f"Memory {mem_pct:.0f}% used",
            suggestion="",
        ))

    # Cache bloat
    caches = scan_caches(min_size=100 * 1024 * 1024)  # 100MB+
    total_cache = sum(c.size for c in caches)
    if total_cache > 10 * 1024**3:  # 10GB
        items.append(DiagnosticItem(
            category="caches",
            severity="warning",
            message=f"{bytes_to_human(total_cache)} in {len(caches)} "
                    f"large cache locations",
            suggestion="Run 'osa clean caches' to review",
        ))
    elif total_cache > 0:
        items.append(DiagnosticItem(
            category="caches",
            severity="info",
            message=f"{bytes_to_human(total_cache)} in caches",
            suggestion="",
        ))

    # Disk hogs
    hogs = scan_disk_hogs(min_size=5 * 1024**3)  # 5GB+
    if hogs:
        names = ", ".join(str(h.path.name) for h in hogs[:3])
        items.append(DiagnosticItem(
            category="disk_hogs",
            severity="warning",
            message=f"{len(hogs)} directories over 5GB: {names}",
            suggestion="Run 'osa scan disk-hogs' for details",
        ))

    # Launch agents running at load
    agents = scan_launch_agents(include_apple=False)
    run_at_load = [a for a in agents if a.run_at_load and not a.disabled]
    if len(run_at_load) > 15:
        items.append(DiagnosticItem(
            category="launch_agents",
            severity="warning",
            message=f"{len(run_at_load)} agents set to run at load",
            suggestion="Review 'osa scan launch-agents' — "
                       "disable unused agents for faster boot",
        ))
    else:
        items.append(DiagnosticItem(
            category="launch_agents",
            severity="info",
            message=f"{len(run_at_load)} agents run at load",
            suggestion="",
        ))

    # Junk files
    if scan_path:
        junk = scan_junk(scan_path)
        junk_size = sum(j.size for j in junk)
        if len(junk) > 100:
            items.append(DiagnosticItem(
                category="junk",
                severity="warning",
                message=f"{len(junk)} junk files ({bytes_to_human(junk_size)})",
                suggestion="Run 'osa clean junk' to review",
            ))
        elif junk:
            items.append(DiagnosticItem(
                category="junk",
                severity="info",
                message=f"{len(junk)} junk files ({bytes_to_human(junk_size)})",
                suggestion="",
            ))

    # Battery health
    if sys_status.battery:
        bat = sys_status.battery
        if bat.percent is not None and bat.percent < 20 and not bat.power_plugged:
            items.append(DiagnosticItem(
                category="battery",
                severity="warning",
                message=f"Battery at {bat.percent:.0f}% (not plugged in)",
                suggestion="Plug in to avoid unexpected shutdown",
            ))

    # Homebrew check
    if shutil.which("brew"):
        items.append(DiagnosticItem(
            category="homebrew",
            severity="info",
            message="Homebrew installed",
            suggestion="Run 'osa scan brew' for package audit",
        ))

    return items
