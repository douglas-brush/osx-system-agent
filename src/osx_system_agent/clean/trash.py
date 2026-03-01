from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from osx_system_agent.log import get_logger
from osx_system_agent.utils.paths import ensure_dir

log = get_logger("clean.trash")

UNDO_DIR = Path.home() / ".local" / "share" / "osx-system-agent" / "undo"


def _undo_log_path() -> Path:
    ensure_dir(UNDO_DIR)
    return UNDO_DIR / "actions.jsonl"


def _log_action(action: str, source: Path, dest: Path | None = None) -> None:
    entry = {
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "action": action,
        "source": str(source),
        "dest": str(dest) if dest else None,
    }
    with _undo_log_path().open("a") as f:
        f.write(json.dumps(entry) + "\n")
    log.debug("logged action: %s %s -> %s", action, source, dest)


def move_to_trash(path: Path) -> bool:
    """Move a file to macOS Trash using Finder via osascript. Falls back to ~/.Trash."""
    if not path.exists():
        log.warning("file does not exist: %s", path)
        return False

    try:
        # Use macOS Finder to move to trash (supports undo in Finder)
        escaped = str(path).replace('"', '\\"')
        script = f'tell application "Finder" to delete POSIX file "{escaped}"'
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if not path.exists():
            _log_action("trash", path)
            return True
    except Exception:
        log.debug("osascript trash failed for %s, falling back to ~/.Trash", path)

    # Fallback: move to ~/.Trash manually
    trash = Path.home() / ".Trash"
    dest = trash / path.name
    # Handle name collisions
    counter = 1
    while dest.exists():
        dest = trash / f"{path.stem}_{counter}{path.suffix}"
        counter += 1

    try:
        shutil.move(str(path), str(dest))
        _log_action("trash_manual", path, dest)
        return True
    except Exception:
        log.error("failed to trash %s", path)
        return False


def delete_file(path: Path) -> bool:
    """Permanently delete a file."""
    if not path.exists():
        return False
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        _log_action("delete", path)
        return True
    except Exception:
        log.error("failed to delete %s", path)
        return False
