from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from osx_system_agent.log import get_logger
from osx_system_agent.utils.paths import ensure_dir

log = get_logger("undo")

UNDO_DIR = Path.home() / ".local" / "share" / "osx-system-agent" / "undo"


@dataclass
class UndoEntry:
    timestamp: str
    action: str
    source: str
    dest: str | None


def load_undo_log(limit: int = 50) -> list[UndoEntry]:
    """Load the most recent N undo log entries."""
    log_file = UNDO_DIR / "actions.jsonl"
    if not log_file.exists():
        return []

    lines = log_file.read_text().strip().splitlines()
    entries: list[UndoEntry] = []

    for line in lines[-limit:]:
        try:
            data = json.loads(line)
            entries.append(UndoEntry(
                timestamp=data.get("timestamp", ""),
                action=data.get("action", ""),
                source=data.get("source", ""),
                dest=data.get("dest"),
            ))
        except json.JSONDecodeError:
            continue

    return entries


def undo_trash(entry: UndoEntry) -> bool:
    """Attempt to restore a trashed file from ~/.Trash back to its source."""
    if entry.action not in ("trash_manual", "trash"):
        log.warning("cannot undo action type: %s", entry.action)
        return False

    source = Path(entry.source)

    if entry.dest:
        dest = Path(entry.dest)
        if not dest.exists():
            log.warning("trash file not found: %s", dest)
            return False
        try:
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(source))
            log.info("restored %s from %s", source, dest)
            return True
        except Exception:
            log.error("failed to restore %s", source)
            return False

    # For osascript trash, look in ~/.Trash by name
    trash = Path.home() / ".Trash"
    trash_file = trash / source.name
    if not trash_file.exists():
        log.warning("file not found in Trash: %s", source.name)
        return False

    try:
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(trash_file), str(source))
        log.info("restored %s from Trash", source)
        return True
    except Exception:
        log.error("failed to restore %s", source)
        return False


def clear_undo_log() -> None:
    """Clear the undo action log."""
    log_file = UNDO_DIR / "actions.jsonl"
    if log_file.exists():
        log_file.unlink()
        log.info("cleared undo log")


def undo_log_path() -> Path:
    ensure_dir(UNDO_DIR)
    return UNDO_DIR / "actions.jsonl"
