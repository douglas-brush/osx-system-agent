from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Iterable

DEFAULT_EXCLUDES = [
    ".git",
    ".venv",
    "node_modules",
    "Library/Caches",
    "Library/Containers",
    "Library/Group Containers",
    "Library/Logs",
    "Library/Application Support/Code/Cache",
    "Library/Application Support/Code/CachedData",
]


def _normalized(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
        return str(rel)
    except Exception:
        return str(path)


def should_exclude(path: Path, root: Path, patterns: Iterable[str]) -> bool:
    rel = _normalized(path, root)
    for pattern in patterns:
        if "/" not in pattern and pattern in path.parts:
            return True
        if fnmatch.fnmatch(rel, pattern) or rel.startswith(pattern):
            return True
    return False


def iter_files(
    root: Path,
    excludes: Iterable[str],
    follow_symlinks: bool = False,
) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        dirpath = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames if not should_exclude(dirpath / d, root, excludes)
        ]
        for name in filenames:
            path = dirpath / name
            if should_exclude(path, root, excludes):
                continue
            if not follow_symlinks and path.is_symlink():
                continue
            yield path
