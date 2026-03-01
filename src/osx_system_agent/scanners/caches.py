from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CacheEntry:
    path: Path
    size: int
    file_count: int
    category: str


CACHE_TARGETS: list[tuple[str, str]] = [
    ("~/Library/Caches", "User Caches"),
    ("~/Library/Logs", "User Logs"),
    ("~/Library/Application Support/Code/Cache", "VS Code Cache"),
    ("~/Library/Application Support/Code/CachedData", "VS Code Cached Data"),
    ("~/Library/Application Support/Code/CachedExtensions", "VS Code Cached Extensions"),
    ("~/Library/Developer/Xcode/DerivedData", "Xcode DerivedData"),
    ("~/Library/Developer/Xcode/Archives", "Xcode Archives"),
    ("~/Library/Developer/CoreSimulator/Caches", "Simulator Caches"),
    (
        "~/Library/Application Support/Google/Chrome/Default/Service Worker/CacheStorage",
        "Chrome SW Cache",
    ),
    ("~/Library/Application Support/Firefox/Profiles", "Firefox Profiles"),
    ("~/Library/Containers/com.docker.docker/Data", "Docker Data"),
    ("/Library/Caches", "System Caches"),
    ("~/.npm/_cacache", "npm Cache"),
    ("~/.cache/pip", "pip Cache"),
    ("~/Library/Application Support/Slack/Cache", "Slack Cache"),
    ("~/Library/Application Support/Slack/Service Worker/CacheStorage", "Slack SW Cache"),
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


def scan_caches(
    targets: list[tuple[str, str]] | None = None,
    min_size: int = 0,
) -> list[CacheEntry]:
    target_list = targets or CACHE_TARGETS
    results: list[CacheEntry] = []

    for raw_path, category in target_list:
        path = Path(raw_path).expanduser()
        if not path.exists():
            continue
        try:
            size, count = _dir_size(path)
        except PermissionError:
            continue

        if size >= min_size:
            results.append(CacheEntry(
                path=path,
                size=size,
                file_count=count,
                category=category,
            ))

    results.sort(key=lambda c: c.size, reverse=True)
    return results
