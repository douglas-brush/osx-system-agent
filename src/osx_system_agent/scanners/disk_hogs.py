from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DirUsage:
    path: Path
    size: int
    file_count: int
    error: str | None = None


# Directories worth checking on a typical macOS system
DEFAULT_TARGETS = [
    "~/Downloads",
    "~/Desktop",
    "~/Documents",
    "~/Movies",
    "~/Music",
    "~/Pictures",
    "~/.Trash",
    "~/Library/Caches",
    "~/Library/Logs",
    "~/Library/Application Support",
    "~/Library/Developer/Xcode/DerivedData",
    "~/Library/Developer/CoreSimulator",
    "~/Library/Containers",
    "~/Library/Group Containers",
    "/Library/Caches",
    "/private/var/folders",
]


def _dir_size(path: Path) -> tuple[int, int]:
    total = 0
    count = 0
    for dirpath, _dirnames, filenames in os.walk(path, followlinks=False):
        for name in filenames:
            try:
                total += (Path(dirpath) / name).stat().st_size
                count += 1
            except OSError:
                continue
    return total, count


def scan_disk_hogs(
    targets: list[str] | None = None,
    min_size: int = 0,
) -> list[DirUsage]:
    paths = targets or DEFAULT_TARGETS
    results: list[DirUsage] = []

    for raw in paths:
        path = Path(raw).expanduser()
        if not path.exists():
            continue
        try:
            size, count = _dir_size(path)
        except PermissionError as exc:
            results.append(DirUsage(path=path, size=0, file_count=0, error=str(exc)))
            continue

        if size >= min_size:
            results.append(DirUsage(path=path, size=size, file_count=count))

    results.sort(key=lambda d: d.size, reverse=True)
    return results
