"""Clutter scanner — categorises Desktop/Downloads files for triage.

Categories:
- word_temp: ~$* lock files from Word
- webloc: Safari bookmark files (.webloc)
- dmg_installer: mounted disk images (usually done after install)
- generic_name: Untitled*, image*, IMG_*, Pasted_Image*
- numbered_copy: filename_1.ext, filename (1).ext patterns
- opaque_name: filenames that are hashes/UUIDs/tracking numbers
- stale: files older than threshold with no recent access
- dead_file: htaccess, .olf, .localized — zero-utility files
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

# Patterns that identify useless / generic file names
_GENERIC_RE = re.compile(
    r"^(Untitled|image|IMG_|Pasted_Image|Screenshot \d|Screen Shot \d)",
    re.IGNORECASE,
)

# Numbered copy: foo_1.ext, foo (1).ext, foo_2.ext, etc.
_NUMBERED_COPY_RE = re.compile(
    r"^(.+?)[\s_]\(?(\d+)\)?(\.[^.]+)$"
)

# Opaque: filenames that are mostly hex, UUIDs, or tracking numbers with no words
_OPAQUE_RE = re.compile(
    r"^[0-9a-fA-F~_\-]{16,}\.[^.]+$"  # 16+ hex-ish chars
)

# Dead file extensions / names
_DEAD_NAMES = {".localized", ".htaccess.html", "desktop.ini", "Thumbs.db"}
_DEAD_EXTENSIONS = {".olf", ".tmp", ".crdownload", ".part"}

# Word temp lock files
_WORD_TEMP_RE = re.compile(r"^~\$")

STALE_DAYS_DEFAULT = 180


@dataclass
class ClutterFile:
    path: Path
    size: int
    category: str
    age_days: int
    suggestion: str = ""


@dataclass
class ClutterReport:
    directory: Path
    total_files: int = 0
    total_size: int = 0
    items: list[ClutterFile] = field(default_factory=list)


def _age_days(path: Path) -> int:
    try:
        mtime = path.stat().st_mtime
        return int((time.time() - mtime) / 86400)
    except OSError:
        return 0


def _classify(path: Path, stale_days: int) -> str | None:
    name = path.name

    # Skip dotfiles that are not interesting
    if name == ".DS_Store" or name == "._.DS_Store":
        return None  # handled by junk scanner

    # Word temp files
    if _WORD_TEMP_RE.match(name):
        return "word_temp"

    # Dead files
    if name in _DEAD_NAMES:
        return "dead_file"
    if path.suffix.lower() in _DEAD_EXTENSIONS:
        return "dead_file"

    # Webloc bookmarks
    if path.suffix.lower() == ".webloc":
        return "webloc"

    # DMG installers
    if path.suffix.lower() == ".dmg":
        return "dmg_installer"

    # Generic / meaningless names
    stem = path.stem
    if _GENERIC_RE.match(stem):
        return "generic_name"

    # Numbered copies — only flag the _1, _2 etc. not the original
    m = _NUMBERED_COPY_RE.match(name)
    if m and m.group(2) != "0":
        return "numbered_copy"

    # Opaque names (hashes, tracking numbers)
    if _OPAQUE_RE.match(name):
        return "opaque_name"

    # Stale files
    if _age_days(path) > stale_days:
        return "stale"

    return None


def _suggestion(category: str) -> str:
    return {
        "word_temp": "Delete — orphaned Word lock file",
        "webloc": "Delete or move to bookmarks — stale Safari shortcut",
        "dmg_installer": "Delete — installer, already used",
        "generic_name": "Rename based on content or delete",
        "numbered_copy": "Keep latest version, delete older copies",
        "opaque_name": "Rename based on content",
        "stale": "Archive or delete — untouched for 6+ months",
        "dead_file": "Delete — no utility",
    }.get(category, "Review")


def scan_clutter(
    root: Path,
    stale_days: int = STALE_DAYS_DEFAULT,
    max_depth: int = 1,
) -> ClutterReport:
    """Scan a directory for clutter files.

    Only scans top-level files by default (max_depth=1) since this targets
    Desktop / Downloads style directories, not deep trees.
    """
    report = ClutterReport(directory=root)

    if not root.is_dir():
        return report

    for entry in sorted(root.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            if max_depth > 1:
                sub = scan_clutter(entry, stale_days=stale_days, max_depth=max_depth - 1)
                report.items.extend(sub.items)
                report.total_files += sub.total_files
                report.total_size += sub.total_size
            continue

        if not entry.is_file():
            continue

        try:
            size = entry.stat().st_size
        except OSError:
            size = 0

        report.total_files += 1
        report.total_size += size

        cat = _classify(entry, stale_days)
        if cat:
            report.items.append(
                ClutterFile(
                    path=entry,
                    size=size,
                    category=cat,
                    age_days=_age_days(entry),
                    suggestion=_suggestion(cat),
                )
            )

    # Sort: category groups, then largest first within each
    report.items.sort(key=lambda c: (c.category, -c.size))
    return report
