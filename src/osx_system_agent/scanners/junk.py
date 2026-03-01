from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

JUNK_PATTERNS = {
    ".DS_Store",
    "._.DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".Spotlight-V100",
    ".Trashes",
    ".fseventsd",
    "__MACOSX",
}

JUNK_PREFIXES = ("._",)


@dataclass
class JunkFile:
    path: Path
    size: int
    category: str  # "ds_store", "apple_double", "thumbs", "spotlight", etc.


def _classify(name: str) -> str | None:
    if name == ".DS_Store" or name == "._.DS_Store":
        return "ds_store"
    if name == "Thumbs.db" or name == "desktop.ini":
        return "windows_junk"
    if name in (".Spotlight-V100", ".fseventsd"):
        return "spotlight"
    if name == ".Trashes":
        return "trashes"
    if name == "__MACOSX":
        return "macosx_resource"
    if name.startswith("._") and name != "._.DS_Store":
        return "apple_double"
    return None


def scan_junk(
    root: Path,
    follow_symlinks: bool = False,
) -> list[JunkFile]:
    results: list[JunkFile] = []

    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        # Check directory names for junk dirs
        junk_dirs = []
        for d in dirnames:
            cat = _classify(d)
            if cat:
                full = Path(dirpath) / d
                try:
                    size = sum(
                        f.stat().st_size
                        for f in full.rglob("*")
                        if f.is_file()
                    )
                except OSError:
                    size = 0
                results.append(JunkFile(path=full, size=size, category=cat))
                junk_dirs.append(d)
        # Don't descend into junk dirs
        for d in junk_dirs:
            dirnames.remove(d)

        # Check file names
        for name in filenames:
            cat = _classify(name)
            if cat:
                full = Path(dirpath) / name
                try:
                    size = full.stat().st_size
                except OSError:
                    size = 0
                results.append(JunkFile(path=full, size=size, category=cat))

    results.sort(key=lambda j: j.size, reverse=True)
    return results
