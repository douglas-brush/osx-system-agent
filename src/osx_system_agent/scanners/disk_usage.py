from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DirEntry:
    path: Path
    size: int
    file_count: int
    is_hidden: bool


def scan_disk_usage(
    root: Path,
    depth: int = 1,
    min_size: int = 0,
    include_hidden: bool = True,
) -> list[DirEntry]:
    """Scan top-level children of root and report sizes (like du -sh --max-depth=1)."""
    root = root.expanduser().resolve()
    if not root.is_dir():
        return []

    entries: list[DirEntry] = []

    # Get direct children
    try:
        children = sorted(root.iterdir())
    except PermissionError:
        return []

    for child in children:
        if not child.is_dir():
            continue
        is_hidden = child.name.startswith(".")
        if not include_hidden and is_hidden:
            continue

        total_size = 0
        file_count = 0
        try:
            for dirpath, _dirnames, filenames in os.walk(child, followlinks=False):
                for name in filenames:
                    try:
                        total_size += (Path(dirpath) / name).stat().st_size
                        file_count += 1
                    except OSError:
                        continue
        except PermissionError:
            pass

        if total_size >= min_size:
            entries.append(DirEntry(
                path=child,
                size=total_size,
                file_count=file_count,
                is_hidden=is_hidden,
            ))

    # Also count loose files in root
    loose_size = 0
    loose_count = 0
    try:
        for item in root.iterdir():
            if item.is_file():
                try:
                    loose_size += item.stat().st_size
                    loose_count += 1
                except OSError:
                    continue
    except PermissionError:
        pass

    if loose_size >= min_size and loose_count > 0:
        entries.append(DirEntry(
            path=root / "(loose files)",
            size=loose_size,
            file_count=loose_count,
            is_hidden=False,
        ))

    entries.sort(key=lambda e: e.size, reverse=True)
    return entries
