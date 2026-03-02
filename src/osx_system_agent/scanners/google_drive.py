"""Google Drive scanner — local DriveFS audit and cloud storage analysis."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from osx_system_agent.log import get_logger

log = get_logger("scanners.google_drive")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

_CLOUD_STORAGE = Path.home() / "Library" / "CloudStorage"
_DRIVEFS_SUPPORT = (
    Path.home() / "Library" / "Application Support" / "Google" / "DriveFS"
)


@dataclass
class DriveAccount:
    """A Google account configured in DriveFS."""

    email: str
    root_path: Path | None = None
    my_drive_path: Path | None = None
    shared_drives_path: Path | None = None
    account_hash: str | None = None


@dataclass
class DriveFile:
    """A file synced through Google Drive."""

    name: str
    path: Path
    size: int
    mtime: float
    category: str
    cloud_only: bool = False


@dataclass
class DriveStorageSummary:
    """Aggregate storage stats for a Drive location."""

    location: str
    total_files: int = 0
    total_size: int = 0
    by_category: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class GoogleDriveAudit:
    """Full Google Drive audit result."""

    installed: bool = False
    app_path: str | None = None
    accounts: list[DriveAccount] = field(default_factory=list)
    storage: list[DriveStorageSummary] = field(default_factory=list)
    largest_files: list[DriveFile] = field(default_factory=list)
    categories: dict[str, dict[str, int]] = field(default_factory=dict)
    total_files: int = 0
    total_size: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# Category classification
# ---------------------------------------------------------------------------

_CATEGORY_MAP: dict[str, str] = {
    ".pdf": "Documents",
    ".doc": "Documents",
    ".docx": "Documents",
    ".xls": "Documents",
    ".xlsx": "Documents",
    ".ppt": "Documents",
    ".pptx": "Documents",
    ".txt": "Documents",
    ".rtf": "Documents",
    ".odt": "Documents",
    ".ods": "Documents",
    ".odp": "Documents",
    ".csv": "Data",
    ".json": "Data",
    ".xml": "Data",
    ".sql": "Data",
    ".db": "Data",
    ".sqlite": "Data",
    ".jpg": "Images",
    ".jpeg": "Images",
    ".png": "Images",
    ".gif": "Images",
    ".bmp": "Images",
    ".tiff": "Images",
    ".tif": "Images",
    ".heic": "Images",
    ".webp": "Images",
    ".svg": "Images",
    ".raw": "Images",
    ".cr2": "Images",
    ".nef": "Images",
    ".mp4": "Video",
    ".mov": "Video",
    ".avi": "Video",
    ".mkv": "Video",
    ".wmv": "Video",
    ".flv": "Video",
    ".mp3": "Audio",
    ".wav": "Audio",
    ".aac": "Audio",
    ".flac": "Audio",
    ".m4a": "Audio",
    ".ogg": "Audio",
    ".zip": "Archives",
    ".tar": "Archives",
    ".gz": "Archives",
    ".bz2": "Archives",
    ".7z": "Archives",
    ".rar": "Archives",
    ".dmg": "Archives",
    ".iso": "Archives",
    ".py": "Code",
    ".js": "Code",
    ".ts": "Code",
    ".java": "Code",
    ".go": "Code",
    ".rs": "Code",
    ".c": "Code",
    ".cpp": "Code",
    ".h": "Code",
    ".cs": "Code",
    ".rb": "Code",
    ".php": "Code",
    ".sh": "Code",
    ".ps1": "Code",
    ".html": "Web",
    ".css": "Web",
    ".htm": "Web",
}


def _categorize(ext: str) -> str:
    return _CATEGORY_MAP.get(ext.lower(), "Other")


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def _find_app() -> str | None:
    """Return the path to Google Drive Desktop if installed."""
    candidates = [
        "/Applications/Google Drive.app",
        Path.home() / "Applications" / "Google Drive.app",
    ]
    for p in candidates:
        if Path(p).exists():
            return str(p)
    return None


def _find_accounts() -> list[DriveAccount]:
    """Discover Google Drive accounts from CloudStorage and DriveFS."""
    accounts: list[DriveAccount] = []
    seen_emails: set[str] = set()

    # Method 1: CloudStorage mount points (GoogleDrive-<email>)
    if _CLOUD_STORAGE.exists():
        for entry in _CLOUD_STORAGE.iterdir():
            if entry.name.startswith("GoogleDrive-") and entry.is_dir():
                email = entry.name.removeprefix("GoogleDrive-")
                if email not in seen_emails:
                    seen_emails.add(email)
                    acct = DriveAccount(email=email, root_path=entry)
                    my_drive = entry / "My Drive"
                    if my_drive.exists():
                        acct.my_drive_path = my_drive
                    shared = entry / "Shared drives"
                    if shared.exists():
                        acct.shared_drives_path = shared
                    accounts.append(acct)

    # Method 2: DriveFS root_preference_sqlite.db for historical accounts
    pref_db = (
        Path.home()
        / "Library"
        / "Application Support"
        / "Google"
        / "Drive"
        / "root_preference_sqlite.db"
    )
    if pref_db.exists():
        try:
            conn = sqlite3.connect(f"file:{pref_db}?mode=ro", uri=True)
            cursor = conn.execute(
                "SELECT key, value FROM root_preference"
            )
            for key, value in cursor.fetchall():
                if "@" in str(value) and str(value) not in seen_emails:
                    seen_emails.add(str(value))
                    accounts.append(DriveAccount(email=str(value)))
                elif "@" in str(key) and str(key) not in seen_emails:
                    seen_emails.add(str(key))
                    accounts.append(DriveAccount(email=str(key)))
            conn.close()
        except (sqlite3.Error, OSError) as exc:
            log.debug("Failed to read DriveFS preferences: %s", exc)

    # Method 3: DriveFS account directories
    if _DRIVEFS_SUPPORT.exists():
        for entry in _DRIVEFS_SUPPORT.iterdir():
            if entry.is_dir() and len(entry.name) > 10:
                # Account hash directories
                mirror = entry / "root" / "content_cache"
                if mirror.exists():
                    for acct in accounts:
                        if acct.account_hash is None:
                            acct.account_hash = entry.name
                            break

    return accounts


# ---------------------------------------------------------------------------
# File walking
# ---------------------------------------------------------------------------


def _walk_drive_path(
    root: Path,
    min_size: int = 0,
) -> tuple[list[DriveFile], dict[str, dict[str, int]], int, int]:
    """Walk a Drive path, collecting files and category stats."""
    files: list[DriveFile] = []
    categories: dict[str, dict[str, int]] = {}
    total_files = 0
    total_size = 0

    if not root.exists():
        return files, categories, total_files, total_size

    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda e: None):
        for name in filenames:
            if name.startswith("."):
                continue
            filepath = Path(dirpath) / name
            try:
                st = filepath.stat()
                fsize = st.st_size
            except OSError:
                continue

            total_files += 1
            total_size += fsize

            ext = filepath.suffix.lower()
            cat = _categorize(ext)
            if cat not in categories:
                categories[cat] = {"count": 0, "size": 0}
            categories[cat]["count"] += 1
            categories[cat]["size"] += fsize

            # Check if cloud-only (OneDrive-style extended attrs)
            cloud_only = False
            try:
                xattr_size = os.getxattr(
                    str(filepath), "com.apple.fileprovider.downloadPolicy"
                )
                cloud_only = xattr_size is not None
            except (OSError, AttributeError):
                pass

            if fsize >= min_size:
                files.append(DriveFile(
                    name=name,
                    path=filepath,
                    size=fsize,
                    mtime=st.st_mtime,
                    category=cat,
                    cloud_only=cloud_only,
                ))

    files.sort(key=lambda f: f.size, reverse=True)
    return files, categories, total_files, total_size


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------


def scan_google_drive(
    limit: int = 50,
    min_size: int = 0,
) -> GoogleDriveAudit:
    """Audit Google Drive: accounts, storage usage, largest files."""
    audit = GoogleDriveAudit()

    # Detect installation
    audit.app_path = _find_app()
    audit.installed = audit.app_path is not None

    # Find accounts
    audit.accounts = _find_accounts()

    if not audit.accounts:
        if not audit.installed:
            audit.error = "Google Drive not installed and no accounts found"
        else:
            audit.error = "Google Drive installed but no synced accounts found"
        return audit

    # Walk each account's drive paths
    all_files: list[DriveFile] = []

    for acct in audit.accounts:
        if acct.root_path and acct.root_path.exists():
            # Scan My Drive
            if acct.my_drive_path and acct.my_drive_path.exists():
                files, cats, count, size = _walk_drive_path(
                    acct.my_drive_path, min_size=min_size,
                )
                all_files.extend(files)
                audit.total_files += count
                audit.total_size += size
                audit.storage.append(DriveStorageSummary(
                    location=f"{acct.email} — My Drive",
                    total_files=count,
                    total_size=size,
                    by_category=cats,
                ))

            # Scan Shared drives
            if acct.shared_drives_path and acct.shared_drives_path.exists():
                files, cats, count, size = _walk_drive_path(
                    acct.shared_drives_path, min_size=min_size,
                )
                all_files.extend(files)
                audit.total_files += count
                audit.total_size += size
                audit.storage.append(DriveStorageSummary(
                    location=f"{acct.email} — Shared Drives",
                    total_files=count,
                    total_size=size,
                    by_category=cats,
                ))

            # Scan any other top-level dirs (Shared with me, etc.)
            for entry in acct.root_path.iterdir():
                if (
                    entry.is_dir()
                    and entry != acct.my_drive_path
                    and entry != acct.shared_drives_path
                    and not entry.name.startswith(".")
                ):
                    files, cats, count, size = _walk_drive_path(
                        entry, min_size=min_size,
                    )
                    all_files.extend(files)
                    audit.total_files += count
                    audit.total_size += size
                    audit.storage.append(DriveStorageSummary(
                        location=f"{acct.email} — {entry.name}",
                        total_files=count,
                        total_size=size,
                        by_category=cats,
                    ))

    # Aggregate categories
    for summary in audit.storage:
        for cat, stats in summary.by_category.items():
            if cat not in audit.categories:
                audit.categories[cat] = {"count": 0, "size": 0}
            audit.categories[cat]["count"] += stats["count"]
            audit.categories[cat]["size"] += stats["size"]

    # Top files
    all_files.sort(key=lambda f: f.size, reverse=True)
    audit.largest_files = all_files[:limit]

    return audit
