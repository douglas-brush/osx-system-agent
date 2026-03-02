"""Google Drive scanner — local DriveFS audit and API-based cloud analysis."""

from __future__ import annotations

import os
import sqlite3
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path

from osx_system_agent.log import get_logger

log = get_logger("scanners.google_drive")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CLOUD_STORAGE = Path.home() / "Library" / "CloudStorage"
_DRIVEFS_SUPPORT = (
    Path.home() / "Library" / "Application Support" / "Google" / "DriveFS"
)
_CONFIG_DIR = (
    Path.home() / ".config" / "osx-system-agent" / "google-drive"
)
_SCOPES = ["https://www.googleapis.com/auth/drive.metadata.readonly"]

# Google Workspace MIME types (zero-byte in API, not downloadable)
_GDOC_MIMES = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
    "application/vnd.google-apps.form",
    "application/vnd.google-apps.drawing",
    "application/vnd.google-apps.site",
    "application/vnd.google-apps.script",
    "application/vnd.google-apps.jam",
    "application/vnd.google-apps.map",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


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
    """A file synced through Google Drive (local or API)."""

    name: str
    path: Path | str
    size: int
    mtime: float
    category: str
    cloud_only: bool = False
    mime_type: str | None = None
    shared: bool = False
    owner: str | None = None
    file_id: str | None = None


@dataclass
class DriveQuota:
    """Google Drive storage quota."""

    email: str
    display_name: str
    limit: int | None = None
    usage: int = 0
    usage_in_drive: int = 0
    usage_in_trash: int = 0

    @property
    def pct_used(self) -> float | None:
        if self.limit and self.limit > 0:
            return (self.usage / self.limit) * 100
        return None


@dataclass
class SharedDrive:
    """A Google Shared Drive."""

    drive_id: str
    name: str
    file_count: int = 0
    total_size: int = 0


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
    api_mode: bool = False
    accounts: list[DriveAccount] = field(default_factory=list)
    quota: DriveQuota | None = None
    shared_drives: list[SharedDrive] = field(default_factory=list)
    storage: list[DriveStorageSummary] = field(default_factory=list)
    largest_files: list[DriveFile] = field(default_factory=list)
    trashed_files: list[DriveFile] = field(default_factory=list)
    categories: dict[str, dict[str, int]] = field(default_factory=dict)
    total_files: int = 0
    total_size: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# Category classification (shared between local and API modes)
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

# MIME-type to category for API mode (Google native types + common MIME)
_MIME_CATEGORY: dict[str, str] = {
    "application/vnd.google-apps.document": "Google Docs",
    "application/vnd.google-apps.spreadsheet": "Google Sheets",
    "application/vnd.google-apps.presentation": "Google Slides",
    "application/vnd.google-apps.form": "Google Forms",
    "application/vnd.google-apps.drawing": "Google Drawings",
    "application/vnd.google-apps.folder": "Folders",
    "application/pdf": "Documents",
    "image/": "Images",
    "video/": "Video",
    "audio/": "Audio",
    "text/": "Documents",
    "application/zip": "Archives",
    "application/x-gzip": "Archives",
    "application/x-tar": "Archives",
}


def _categorize(ext: str) -> str:
    return _CATEGORY_MAP.get(ext.lower(), "Other")


def _categorize_mime(mime: str, name: str) -> str:
    """Categorize by MIME type (API mode), fallback to extension."""
    # Exact match first
    if mime in _MIME_CATEGORY:
        return _MIME_CATEGORY[mime]
    # Prefix match (image/*, video/*, etc.)
    for prefix, cat in _MIME_CATEGORY.items():
        if prefix.endswith("/") and mime.startswith(prefix):
            return cat
    # Fallback to extension
    ext = Path(name).suffix.lower() if name else ""
    return _categorize(ext)


# ---------------------------------------------------------------------------
# Detection helpers (local mode)
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
                mirror = entry / "root" / "content_cache"
                if mirror.exists():
                    for acct in accounts:
                        if acct.account_hash is None:
                            acct.account_hash = entry.name
                            break

    return accounts


# ---------------------------------------------------------------------------
# Local file walking
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
# API mode — OAuth + Drive v3
# ---------------------------------------------------------------------------


def _get_credentials(credentials_path: Path | None = None):
    """Load or create OAuth2 credentials for Drive API."""
    # Late import — these are optional deps
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    token_path = _CONFIG_DIR / "token.json"

    if credentials_path is None:
        credentials_path = _CONFIG_DIR / "credentials.json"

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"OAuth credentials not found at {credentials_path}. "
                    "Download from Google Cloud Console > APIs & Services > "
                    "Credentials > OAuth 2.0 Client ID (Desktop app) and "
                    f"save to {credentials_path}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), _SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token with restrictive permissions
        token_path.write_text(creds.to_json())
        token_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    return creds


def _build_service(credentials_path: Path | None = None):
    """Build authenticated Drive v3 service."""
    from googleapiclient.discovery import build

    creds = _get_credentials(credentials_path)
    return build("drive", "v3", credentials=creds)


def _api_get_quota(service) -> DriveQuota:
    """Fetch storage quota via Drive API."""
    about = service.about().get(
        fields="storageQuota, user(displayName, emailAddress)"
    ).execute()

    quota = about["storageQuota"]
    return DriveQuota(
        email=about["user"]["emailAddress"],
        display_name=about["user"]["displayName"],
        limit=int(quota["limit"]) if "limit" in quota else None,
        usage=int(quota["usage"]),
        usage_in_drive=int(quota.get("usageInDrive", 0)),
        usage_in_trash=int(quota.get("usageInDriveTrash", 0)),
    )


def _api_list_files(
    service,
    max_results: int = 200,
    trashed: bool = False,
) -> list[dict]:
    """List files sorted by quotaBytesUsed desc via Drive API."""
    from googleapiclient.errors import HttpError

    files: list[dict] = []
    page_token = None
    q = f"trashed = {str(trashed).lower()}"

    while len(files) < max_results:
        page_size = min(100, max_results - len(files))
        try:
            resp = service.files().list(
                q=q,
                orderBy="quotaBytesUsed desc",
                pageSize=page_size,
                pageToken=page_token,
                fields=(
                    "nextPageToken, "
                    "files(id, name, mimeType, size, quotaBytesUsed, "
                    "owners, shared, trashed, createdTime, modifiedTime)"
                ),
                spaces="drive",
                includeItemsFromAllDrives=False,
                supportsAllDrives=True,
            ).execute()
        except HttpError as exc:
            if exc.resp.status in (403, 429):
                log.warning("Rate limited, backing off: %s", exc)
                time.sleep(2)
                continue
            raise

        batch = resp.get("files", [])
        files.extend(batch)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return files


def _api_list_shared_drives(service) -> list[SharedDrive]:
    """List shared drives via API."""
    drives: list[SharedDrive] = []
    page_token = None

    while True:
        resp = service.drives().list(
            pageSize=100,
            pageToken=page_token,
        ).execute()

        for d in resp.get("drives", []):
            drives.append(SharedDrive(
                drive_id=d["id"],
                name=d["name"],
            ))

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return drives


def _parse_api_time(ts: str | None) -> float:
    """Convert API ISO timestamp to Unix epoch."""
    if not ts:
        return 0.0
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, AttributeError):
        return 0.0


def _api_files_to_drive_files(raw_files: list[dict]) -> list[DriveFile]:
    """Convert API file dicts to DriveFile dataclasses."""
    results: list[DriveFile] = []
    for f in raw_files:
        mime = f.get("mimeType", "")
        name = f.get("name", "")
        size = int(f.get("quotaBytesUsed") or f.get("size") or 0)
        owners = f.get("owners", [])
        owner_name = owners[0].get("displayName", "") if owners else ""

        results.append(DriveFile(
            name=name,
            path=f"drive://{f.get('id', '')}",
            size=size,
            mtime=_parse_api_time(f.get("modifiedTime")),
            category=_categorize_mime(mime, name),
            cloud_only=True,
            mime_type=mime,
            shared=f.get("shared", False),
            owner=owner_name,
            file_id=f.get("id"),
        ))

    results.sort(key=lambda x: x.size, reverse=True)
    return results


# ---------------------------------------------------------------------------
# Main scan functions
# ---------------------------------------------------------------------------


def scan_google_drive(
    limit: int = 50,
    min_size: int = 0,
) -> GoogleDriveAudit:
    """Audit Google Drive via local DriveFS paths."""
    audit = GoogleDriveAudit()

    audit.app_path = _find_app()
    audit.installed = audit.app_path is not None
    audit.accounts = _find_accounts()

    if not audit.accounts:
        if not audit.installed:
            audit.error = "Google Drive not installed and no accounts found"
        else:
            audit.error = "Google Drive installed but no synced accounts found"
        return audit

    all_files: list[DriveFile] = []

    for acct in audit.accounts:
        if acct.root_path and acct.root_path.exists():
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

    for summary in audit.storage:
        for cat, stats in summary.by_category.items():
            if cat not in audit.categories:
                audit.categories[cat] = {"count": 0, "size": 0}
            audit.categories[cat]["count"] += stats["count"]
            audit.categories[cat]["size"] += stats["size"]

    all_files.sort(key=lambda f: f.size, reverse=True)
    audit.largest_files = all_files[:limit]

    return audit


def scan_google_drive_api(
    credentials_path: Path | None = None,
    limit: int = 200,
) -> GoogleDriveAudit:
    """Audit Google Drive via API — quota, largest files, trash, shared drives."""
    audit = GoogleDriveAudit(api_mode=True)

    try:
        service = _build_service(credentials_path)
    except FileNotFoundError as exc:
        audit.error = str(exc)
        return audit
    except Exception as exc:
        audit.error = f"Google Drive API auth failed: {exc}"
        return audit

    # Quota
    try:
        audit.quota = _api_get_quota(service)
        audit.accounts = [DriveAccount(email=audit.quota.email)]
    except Exception as exc:
        audit.error = f"Failed to get quota: {exc}"
        return audit

    # Largest files (My Drive, not trashed)
    try:
        raw_files = _api_list_files(service, max_results=limit, trashed=False)
        audit.largest_files = _api_files_to_drive_files(raw_files)
    except Exception as exc:
        log.warning("Failed to list files: %s", exc)

    # Trashed files (recoverable space)
    try:
        raw_trash = _api_list_files(service, max_results=50, trashed=True)
        audit.trashed_files = _api_files_to_drive_files(raw_trash)
    except Exception as exc:
        log.debug("Failed to list trash: %s", exc)

    # Shared drives
    try:
        audit.shared_drives = _api_list_shared_drives(service)
    except Exception as exc:
        log.debug("Failed to list shared drives: %s", exc)

    # Build category stats from largest files
    for f in audit.largest_files:
        cat = f.category
        if cat not in audit.categories:
            audit.categories[cat] = {"count": 0, "size": 0}
        audit.categories[cat]["count"] += 1
        audit.categories[cat]["size"] += f.size

    audit.total_files = len(audit.largest_files)
    audit.total_size = sum(f.size for f in audit.largest_files)

    return audit
