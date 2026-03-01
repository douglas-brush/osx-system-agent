from __future__ import annotations

import plistlib
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LoginItem:
    name: str
    path: str
    kind: str  # "app", "agent", "smappservice", "legacy"
    hidden: bool
    source: str  # where we found it


def _sfltool_items() -> list[LoginItem]:
    """Use sfltool to dump shared file list login items (legacy mechanism)."""
    items: list[LoginItem] = []
    try:
        result = subprocess.run(
            ["sfltool", "dump", "-n", "com.apple.LSSharedFileList.RecentApplications"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # sfltool output is unstructured; best-effort parse
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
                items.append(LoginItem(
                    name=name,
                    path="",
                    kind="legacy",
                    hidden=False,
                    source="sfltool",
                ))
    except Exception:
        pass
    return items


def _backgrounditems_btm() -> list[LoginItem]:
    """Parse background items from BTM (Background Task Management) plist."""
    items: list[LoginItem] = []

    # macOS 13+ stores background items here
    btm_path = (
        Path.home() / "Library" / "Application Support"
        / "com.apple.backgroundtaskmanagementagent" / "backgrounditems.btm"
    )
    if not btm_path.exists():
        return items

    try:
        with btm_path.open("rb") as f:
            data = plistlib.load(f)

        # The structure varies by macOS version; extract what we can
        store = data.get("$objects", [])
        for obj in store:
            if isinstance(obj, dict):
                name = obj.get("Name", obj.get("BundleIdentifier", ""))
                path = obj.get("URL", obj.get("Path", ""))
                if name and isinstance(name, str):
                    items.append(LoginItem(
                        name=name,
                        path=str(path) if path else "",
                        kind="smappservice",
                        hidden=False,
                        source="backgrounditems.btm",
                    ))
    except Exception:
        pass

    return items


def _osascript_login_items() -> list[LoginItem]:
    """Get login items via osascript (System Events)."""
    items: list[LoginItem] = []
    try:
        script = (
            'tell application "System Events" to get the name of every login item'
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            names = result.stdout.strip().split(", ")
            for name in names:
                items.append(LoginItem(
                    name=name,
                    path="",
                    kind="app",
                    hidden=False,
                    source="System Events",
                ))
    except Exception:
        pass
    return items


def scan_login_items() -> list[LoginItem]:
    """Collect login items from all available sources."""
    items: list[LoginItem] = []

    # Try multiple sources
    items.extend(_osascript_login_items())
    items.extend(_backgrounditems_btm())

    # Deduplicate by name
    seen: set[str] = set()
    deduped: list[LoginItem] = []
    for item in items:
        if item.name not in seen:
            seen.add(item.name)
            deduped.append(item)

    deduped.sort(key=lambda i: i.name.lower())
    return deduped
