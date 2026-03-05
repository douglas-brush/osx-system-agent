"""Content-aware file renamer using macOS Spotlight metadata.

Uses `mdls` to extract document titles, EXIF dates, email subjects, etc.
Falls back to modification-date prefixing for files with no extractable metadata.
"""

from __future__ import annotations

import plistlib
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class RenameProposal:
    original: Path
    proposed: Path
    reason: str
    # metadata source: "mdls_title", "exif_date", "webloc_url", "email_subject", "date_prefix"
    source: str

    @property
    def changed(self) -> bool:
        return self.original.name != self.proposed.name


# ---- Name quality detection ---------------------------------------------------

_GENERIC_RE = re.compile(
    r"^(Untitled|image|IMG_\d|Pasted_Image|Screenshot \d|Screen Shot \d)",
    re.IGNORECASE,
)

_OPAQUE_RE = re.compile(
    r"^[0-9a-fA-F~_\-]{16,}$"
)

_NUMBERED_COPY_RE = re.compile(
    r"^(.+?)[\s_]\(?(\d+)\)?$"
)


def needs_rename(path: Path) -> bool:
    """Return True if the filename is generic/opaque enough to warrant renaming."""
    stem = path.stem
    if _GENERIC_RE.match(stem):
        return True
    if _OPAQUE_RE.match(stem):
        return True
    # "(1)" style copies
    return bool(re.search(r"\(\d+\)$", stem))


# ---- Metadata extraction ------------------------------------------------------

_MDLS_ATTRS = [
    "kMDItemTitle",
    "kMDItemDisplayName",
    "kMDItemSubject",
    "kMDItemContentType",
    "kMDItemContentCreationDate",
    "kMDItemDateAdded",
    "kMDItemAuthors",
]


def _run_mdls(path: Path) -> dict[str, str]:
    """Extract Spotlight metadata via mdls.

    Uses explicit -name flags to force on-demand attribute queries,
    since bare `mdls` only returns FS attrs for unindexed files.
    """
    cmd = ["mdls"]
    for attr in _MDLS_ATTRS:
        cmd.extend(["-name", attr])
    cmd.append(str(path))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {}
    except (OSError, subprocess.TimeoutExpired):
        return {}

    attrs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"')
        if val and val != "(null)":
            attrs[key] = val
    return attrs


def _extract_title_from_mdls(attrs: dict[str, str]) -> str | None:
    """Try to get a meaningful title from Spotlight attributes."""
    for key in ("kMDItemTitle", "kMDItemDisplayName", "kMDItemSubject"):
        val = attrs.get(key, "").strip()
        if val and val != "(null)" and not _GENERIC_RE.match(val):
            # Don't use display name if it's just the filename
            if key == "kMDItemDisplayName":
                continue
            return val
    return None


def _extract_exif_date(attrs: dict[str, str]) -> str | None:
    """Get EXIF creation date for images."""
    for key in ("kMDItemContentCreationDate", "kMDItemDateAdded"):
        val = attrs.get(key, "")
        if val and val != "(null)":
            # Parse: "2026-01-08 09:54:00 +0000"
            try:
                dt = datetime.strptime(val[:19], "%Y-%m-%d %H:%M:%S")
                return dt.strftime("%Y-%m-%d_%H%M%S")
            except (ValueError, IndexError):
                continue
    return None


def _extract_webloc_title(path: Path) -> str | None:
    """Parse .webloc plist for URL to derive a name."""
    try:
        with path.open("rb") as f:
            plist = plistlib.load(f)
        url = plist.get("URL", "")
        if url:
            # Extract domain + path hint
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "")
            # Use last meaningful path segment
            segments = [s for s in parsed.path.strip("/").split("/") if s]
            if segments:
                return f"{domain}_{segments[-1]}"
            return domain
    except Exception:
        return None


def _extract_email_subject(path: Path) -> str | None:
    """Parse .eml file for Subject header."""
    if path.suffix.lower() != ".eml":
        return None
    try:
        import email
        with path.open("rb") as f:
            msg = email.message_from_binary_file(f)
        subject = msg.get("Subject", "")
        if subject:
            # Decode if needed
            from email.header import decode_header
            parts = decode_header(subject)
            decoded = ""
            for part, enc in parts:
                if isinstance(part, bytes):
                    decoded += part.decode(enc or "utf-8", errors="replace")
                else:
                    decoded += part
            return decoded.strip()
    except Exception:
        return None


def _sanitize_filename(name: str, max_len: int = 80) -> str:
    """Clean a proposed filename: remove unsafe chars, truncate."""
    # Replace problematic characters
    name = re.sub(r'[/\\:*?"<>|]', "_", name)
    # Collapse whitespace
    name = re.sub(r"\s+", "_", name)
    # Collapse consecutive underscores
    name = re.sub(r"_+", "_", name)
    # Remove leading/trailing underscores and dots
    name = name.strip("_.")
    # Truncate
    if len(name) > max_len:
        name = name[:max_len].rstrip("_")
    return name


def _date_prefix(path: Path) -> str:
    """Get YYYY-MM-DD from file mtime."""
    try:
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d")
    except OSError:
        return datetime.now(tz=UTC).strftime("%Y-%m-%d")


# ---- Core rename logic --------------------------------------------------------

def propose_rename(path: Path) -> RenameProposal:
    """Generate a rename proposal for a single file."""
    ext = path.suffix
    parent = path.parent

    # 1. Try webloc-specific extraction
    if path.suffix.lower() == ".webloc":
        title = _extract_webloc_title(path)
        if title:
            new_name = _sanitize_filename(title) + ext
            return RenameProposal(
                original=path,
                proposed=parent / new_name,
                reason="Derived from bookmark URL",
                source="webloc_url",
            )

    # 2. Try email subject extraction
    if path.suffix.lower() == ".eml":
        subject = _extract_email_subject(path)
        if subject:
            new_name = _sanitize_filename(subject) + ext
            return RenameProposal(
                original=path,
                proposed=parent / new_name,
                reason=f"Email subject: {subject[:60]}",
                source="email_subject",
            )

    # 3. Try mdls metadata
    attrs = _run_mdls(path)

    title = _extract_title_from_mdls(attrs)
    if title:
        new_name = _sanitize_filename(title) + ext
        return RenameProposal(
            original=path,
            proposed=parent / new_name,
            reason=f"Document title: {title[:60]}",
            source="mdls_title",
        )

    # 4. For images/videos, use EXIF date
    content_type = attrs.get("kMDItemContentType", "")
    is_media = any(
        t in content_type
        for t in ("image", "video", "public.jpeg", "public.png", "public.heic", "public.tiff")
    )
    if is_media or ext.lower() in (
        ".jpg", ".jpeg", ".png", ".heic", ".mp4", ".mov", ".gif",
    ):
        exif_date = _extract_exif_date(attrs)
        if exif_date:
            # Prefix with date, keep partial original for context
            stem = path.stem
            # If stem is just IMG_XXXX, replace entirely
            if re.match(r"^IMG_\d+$", stem, re.IGNORECASE):
                new_name = f"photo_{exif_date}{ext}"
            elif re.match(r"^(image|Untitled|Pasted_Image)", stem, re.IGNORECASE):
                new_name = f"capture_{exif_date}{ext}"
            else:
                new_name = f"{exif_date}_{_sanitize_filename(stem)}{ext}"
            return RenameProposal(
                original=path,
                proposed=parent / new_name,
                reason=f"EXIF/creation date: {exif_date}",
                source="exif_date",
            )

    # 5. Fallback: date-prefix the existing name
    date_prefix = _date_prefix(path)
    clean_stem = _sanitize_filename(path.stem)
    new_name = f"{date_prefix}_{clean_stem}{ext}"
    return RenameProposal(
        original=path,
        proposed=parent / new_name,
        reason="Date-prefixed (no extractable title)",
        source="date_prefix",
    )


def _deconflict(proposed: Path) -> Path:
    """If proposed path exists, append _2, _3 etc."""
    if not proposed.exists():
        return proposed
    stem = proposed.stem
    ext = proposed.suffix
    parent = proposed.parent
    for i in range(2, 100):
        candidate = parent / f"{stem}_{i}{ext}"
        if not candidate.exists():
            return candidate
    return proposed  # give up


def scan_for_renames(
    root: Path,
    include_all: bool = False,
) -> list[RenameProposal]:
    """Scan a directory and propose renames for files with bad names.

    Args:
        root: Directory to scan (non-recursive).
        include_all: If True, propose renames for ALL files, not just bad names.
    """
    proposals: list[RenameProposal] = []

    if not root.is_dir():
        return proposals

    for entry in sorted(root.iterdir()):
        if entry.name.startswith("."):
            continue
        if not entry.is_file():
            continue

        if include_all or needs_rename(entry):
            proposal = propose_rename(entry)
            if proposal.changed:
                # Deconflict
                proposal.proposed = _deconflict(proposal.proposed)
                # Re-check after deconflict
                if proposal.original != proposal.proposed:
                    proposals.append(proposal)

    return proposals


def execute_renames(
    proposals: list[RenameProposal],
    dry_run: bool = True,
) -> list[dict]:
    """Execute rename proposals. Returns list of results.

    Args:
        proposals: List of RenameProposal objects.
        dry_run: If True, only preview. If False, actually rename.
    """
    results = []
    for p in proposals:
        if not p.changed:
            continue
        entry = {
            "original": str(p.original),
            "proposed": str(p.proposed),
            "reason": p.reason,
            "source": p.source,
            "status": "dry_run" if dry_run else "pending",
        }
        if not dry_run:
            try:
                p.original.rename(p.proposed)
                entry["status"] = "renamed"
            except OSError as e:
                entry["status"] = f"error: {e}"
        results.append(entry)
    return results
