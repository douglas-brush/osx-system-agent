from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from osx_system_agent.log import get_logger
from osx_system_agent.scanners.caches import scan_caches
from osx_system_agent.scanners.disk_hogs import scan_disk_hogs
from osx_system_agent.scanners.junk import scan_junk
from osx_system_agent.scanners.launch_agents import scan_launch_agents
from osx_system_agent.system.activity import get_system_status
from osx_system_agent.utils.human import bytes_to_human
from osx_system_agent.utils.paths import ensure_dir

log = get_logger("reports.consolidated")


def generate_report(
    output_dir: Path,
    scan_path: Path | None = None,
) -> Path:
    """Run all scanners and produce a single consolidated JSON report."""
    timestamp = datetime.now(tz=UTC).isoformat(timespec="seconds")
    report: dict[str, object] = {
        "generated_at": timestamp,
        "version": "1.0",
    }

    # System status
    log.info("collecting system status...")
    sys_status = get_system_status()
    report["system"] = {
        "cpu_percent": sys_status.cpu_percent,
        "memory_total": sys_status.memory_total,
        "memory_used": sys_status.memory_used,
        "memory_available": sys_status.memory_available,
        "memory_total_human": bytes_to_human(sys_status.memory_total),
        "memory_used_human": bytes_to_human(sys_status.memory_used),
        "disk_total": sys_status.disk_total,
        "disk_used": sys_status.disk_used,
        "disk_free": sys_status.disk_free,
        "disk_total_human": bytes_to_human(sys_status.disk_total),
        "disk_used_human": bytes_to_human(sys_status.disk_used),
        "disk_free_human": bytes_to_human(sys_status.disk_free),
        "battery": {
            "percent": sys_status.battery.percent if sys_status.battery else None,
            "plugged": sys_status.battery.power_plugged if sys_status.battery else None,
        },
    }

    # Disk hogs
    log.info("scanning disk hogs...")
    hogs = scan_disk_hogs(min_size=100 * 1024 * 1024)  # 100MB+
    report["disk_hogs"] = [
        {
            "path": str(d.path),
            "size": d.size,
            "size_human": bytes_to_human(d.size),
            "file_count": d.file_count,
        }
        for d in hogs
    ]

    # Caches
    log.info("scanning caches...")
    caches = scan_caches(min_size=10 * 1024 * 1024)  # 10MB+
    total_cache = sum(c.size for c in caches)
    report["caches"] = {
        "total_size": total_cache,
        "total_size_human": bytes_to_human(total_cache),
        "entries": [
            {
                "category": c.category,
                "path": str(c.path),
                "size": c.size,
                "size_human": bytes_to_human(c.size),
                "file_count": c.file_count,
            }
            for c in caches
        ],
    }

    # Launch agents
    log.info("scanning launch agents...")
    agents = scan_launch_agents(include_apple=False)
    report["launch_agents"] = [
        {
            "scope": a.scope,
            "label": a.label,
            "program": a.program,
            "run_at_load": a.run_at_load,
            "disabled": a.disabled,
        }
        for a in agents
    ]

    # Junk files (scan project dir or home)
    if scan_path:
        log.info("scanning junk files in %s...", scan_path)
        junk = scan_junk(scan_path)
        total_junk = sum(j.size for j in junk)
        report["junk"] = {
            "scan_path": str(scan_path),
            "total_count": len(junk),
            "total_size": total_junk,
            "total_size_human": bytes_to_human(total_junk),
            "by_category": {},
        }
        categories: dict[str, int] = {}
        for j in junk:
            categories[j.category] = categories.get(j.category, 0) + 1
        report["junk"]["by_category"] = categories

    # Write report
    ensure_dir(output_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = output_dir / f"system-report-{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))

    log.info("report written to %s", report_path)
    return report_path
