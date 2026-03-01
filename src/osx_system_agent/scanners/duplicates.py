from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from osx_system_agent.scanners.filters import DEFAULT_EXCLUDES, iter_files


@dataclass
class DuplicateGroup:
    size: int
    digest: str
    files: list[Path]


def hash_file(path: Path, block_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(block_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def scan_duplicates(
    root: Path,
    min_size: int = 0,
    excludes: Iterable[str] | None = None,
    follow_symlinks: bool = False,
) -> list[DuplicateGroup]:
    excludes = list(DEFAULT_EXCLUDES if excludes is None else excludes)

    by_size: dict[int, list[Path]] = defaultdict(list)
    for path in iter_files(root, excludes, follow_symlinks=follow_symlinks):
        try:
            size = path.stat().st_size
        except Exception:
            continue
        if size < min_size:
            continue
        by_size[size].append(path)

    dup_groups: list[DuplicateGroup] = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_hash: dict[str, list[Path]] = defaultdict(list)
        for path in paths:
            try:
                digest = hash_file(path)
            except Exception:
                continue
            by_hash[digest].append(path)
        for digest, dup_paths in by_hash.items():
            if len(dup_paths) > 1:
                dup_groups.append(DuplicateGroup(size=size, digest=digest, files=dup_paths))

    dup_groups.sort(key=lambda g: g.size, reverse=True)
    return dup_groups
