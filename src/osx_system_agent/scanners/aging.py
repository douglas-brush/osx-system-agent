from __future__ import annotations

from pathlib import Path
from typing import Iterable

from osx_system_agent.scanners.filters import DEFAULT_EXCLUDES, iter_files


def scan_aging(
    root: Path,
    min_size: int = 0,
    sort: str = "mtime",
    limit: int = 200,
    excludes: Iterable[str] | None = None,
    follow_symlinks: bool = False,
) -> list[dict[str, object]]:
    excludes = list(DEFAULT_EXCLUDES if excludes is None else excludes)
    rows: list[dict[str, object]] = []

    for path in iter_files(root, excludes, follow_symlinks=follow_symlinks):
        try:
            stat = path.stat()
        except Exception:
            continue
        if stat.st_size < min_size:
            continue
        rows.append(
            {
                "path": str(path),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "atime": stat.st_atime,
                "ctime": stat.st_ctime,
            }
        )

    key = sort if sort in {"mtime", "atime", "ctime", "size"} else "mtime"
    rows.sort(key=lambda r: r[key], reverse=True if key == "size" else False)
    return rows[:limit]
