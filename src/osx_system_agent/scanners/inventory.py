from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from osx_system_agent.scanners.filters import iter_files, merge_excludes


def scan_inventory(
    root: Path,
    min_size: int = 0,
    excludes: Iterable[str] | None = None,
    follow_symlinks: bool = False,
) -> list[dict[str, object]]:
    excludes = merge_excludes(excludes)

    summary: dict[str, dict[str, object]] = defaultdict(
        lambda: {"extension": "", "count": 0, "total_size": 0, "largest": 0}
    )

    for path in iter_files(root, excludes, follow_symlinks=follow_symlinks):
        try:
            stat = path.stat()
        except Exception:
            continue
        if stat.st_size < min_size:
            continue
        ext = path.suffix.lower() or "(no_ext)"
        entry = summary[ext]
        entry["extension"] = ext
        entry["count"] += 1
        entry["total_size"] += stat.st_size
        entry["largest"] = max(entry["largest"], stat.st_size)

    rows = list(summary.values())
    rows.sort(key=lambda r: r["total_size"], reverse=True)
    return rows
