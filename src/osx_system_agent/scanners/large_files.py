from __future__ import annotations

import heapq
import os
from dataclasses import dataclass
from pathlib import Path

from osx_system_agent.log import get_logger
from osx_system_agent.scanners.filters import DEFAULT_EXCLUDES, should_exclude

log = get_logger("scanners.large_files")


@dataclass
class LargeFile:
    path: Path
    size: int
    mtime: float


def scan_large_files(
    roots: list[Path] | None = None,
    limit: int = 50,
    min_size: int = 100 * 1024 * 1024,  # 100MB default
    excludes: list[str] | None = None,
) -> list[LargeFile]:
    """Find the N largest individual files across given root directories."""
    if roots is None:
        roots = [Path.home()]

    exclude_patterns = excludes or list(DEFAULT_EXCLUDES)

    # Use a min-heap of size `limit` for efficient top-N
    heap: list[tuple[int, str, float]] = []

    for root in roots:
        if not root.exists():
            continue

        for dirpath, dirnames, filenames in os.walk(
            root, followlinks=False, onerror=lambda e: None,
        ):
            # Prune excluded directories in-place
            dirnames[:] = [
                d for d in dirnames
                if not should_exclude(Path(dirpath) / d, exclude_patterns)
            ]

            for name in filenames:
                filepath = Path(dirpath) / name
                try:
                    st = filepath.lstat()
                    if not stat_is_regular(st):
                        continue
                    size = st.st_size
                    if size < min_size:
                        continue

                    item = (size, str(filepath), st.st_mtime)
                    if len(heap) < limit:
                        heapq.heappush(heap, item)
                    elif size > heap[0][0]:
                        heapq.heapreplace(heap, item)
                except OSError:
                    continue

    # Sort by size descending
    results = sorted(heap, key=lambda x: x[0], reverse=True)
    return [
        LargeFile(path=Path(path), size=size, mtime=mtime)
        for size, path, mtime in results
    ]


def stat_is_regular(st: os.stat_result) -> bool:
    """Check if stat result is a regular file (not symlink, dir, etc)."""
    import stat
    return stat.S_ISREG(st.st_mode)
