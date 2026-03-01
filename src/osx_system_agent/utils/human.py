from __future__ import annotations

from datetime import UTC, datetime


def bytes_to_human(num_bytes: int) -> str:
    step = 1024.0
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num_bytes)
    for unit in units:
        if size < step:
            return f"{size:.1f}{unit}"
        size /= step
    return f"{size:.1f}EB"


def unix_to_iso(ts: float | int | None) -> str:
    if ts is None:
        return ""
    return datetime.fromtimestamp(ts, tz=UTC).isoformat(timespec="seconds")
