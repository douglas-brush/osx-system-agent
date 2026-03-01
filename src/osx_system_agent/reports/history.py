from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from osx_system_agent.log import get_logger
from osx_system_agent.scanners.caches import scan_caches
from osx_system_agent.scanners.disk_hogs import scan_disk_hogs
from osx_system_agent.system.activity import get_system_status
from osx_system_agent.utils.human import bytes_to_human
from osx_system_agent.utils.paths import ensure_dir

log = get_logger("reports.history")

HISTORY_DIR = Path.home() / ".local" / "share" / "osx-system-agent" / "history"


def _history_file() -> Path:
    ensure_dir(HISTORY_DIR)
    return HISTORY_DIR / "snapshots.jsonl"


def record_snapshot() -> dict:
    """Record a point-in-time snapshot of key metrics."""
    sys_status = get_system_status()
    caches = scan_caches(min_size=0)
    hogs = scan_disk_hogs(min_size=0)

    snapshot = {
        "timestamp": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "disk_total": sys_status.disk_total,
        "disk_used": sys_status.disk_used,
        "disk_free": sys_status.disk_free,
        "memory_used": sys_status.memory_used,
        "cache_total": sum(c.size for c in caches),
        "top_hogs": [
            {"path": str(h.path), "size": h.size}
            for h in hogs[:10]
        ],
    }

    with _history_file().open("a") as f:
        f.write(json.dumps(snapshot) + "\n")

    log.info("recorded snapshot at %s", snapshot["timestamp"])
    return snapshot


def load_history(limit: int = 30) -> list[dict]:
    """Load the most recent N snapshots."""
    hf = _history_file()
    if not hf.exists():
        return []

    lines = hf.read_text().strip().splitlines()
    snapshots = []
    for line in lines[-limit:]:
        try:
            snapshots.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return snapshots


def compare_latest() -> dict | None:
    """Compare the two most recent snapshots and return deltas."""
    history = load_history(limit=2)
    if len(history) < 2:
        return None

    prev, curr = history[-2], history[-1]

    return {
        "prev_timestamp": prev["timestamp"],
        "curr_timestamp": curr["timestamp"],
        "disk_used_delta": curr["disk_used"] - prev["disk_used"],
        "disk_used_delta_human": bytes_to_human(abs(curr["disk_used"] - prev["disk_used"])),
        "disk_used_direction": "+" if curr["disk_used"] > prev["disk_used"] else "-",
        "cache_delta": curr["cache_total"] - prev["cache_total"],
        "cache_delta_human": bytes_to_human(abs(curr["cache_total"] - prev["cache_total"])),
        "cache_direction": "+" if curr["cache_total"] > prev["cache_total"] else "-",
        "disk_free_current": curr["disk_free"],
        "disk_free_human": bytes_to_human(curr["disk_free"]),
    }
