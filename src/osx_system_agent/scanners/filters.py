from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable
from pathlib import Path

DEFAULT_EXCLUDES = [
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".Trash",
    "Library/Caches",
    "Library/Containers",
    "Library/Group Containers",
    "Library/Logs",
    "Library/Application Support/Code/Cache",
    "Library/Application Support/Code/CachedData",
    "Library/Developer/Xcode/DerivedData",
    ".Spotlight-V100",
    ".fseventsd",
]


def _normalized(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
        return str(rel)
    except Exception:
        return str(path)


def merge_excludes(user_excludes: Iterable[str] | None) -> list[str]:
    merged = list(DEFAULT_EXCLUDES)
    if user_excludes:
        for pat in user_excludes:
            if pat not in merged:
                merged.append(pat)
    return merged


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
