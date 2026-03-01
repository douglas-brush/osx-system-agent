from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from osx_system_agent.clean.trash import _log_action
from osx_system_agent.log import get_logger
from osx_system_agent.scanners.caches import scan_caches
from osx_system_agent.utils.human import bytes_to_human

log = get_logger("clean.caches")


@dataclass
class CleanResult:
    path: Path
    category: str
    size_before: int
    deleted: bool
    error: str | None = None


def clean_caches(
    min_size: int = 0,
    dry_run: bool = True,
) -> list[CleanResult]:
    entries = scan_caches(min_size=min_size)
    results: list[CleanResult] = []

    for entry in entries:
        if dry_run:
            log.info("[dry-run] would clean %s (%s)", entry.category, bytes_to_human(entry.size))
            results.append(CleanResult(
                path=entry.path,
                category=entry.category,
                size_before=entry.size,
                deleted=False,
            ))
            continue

        try:
            shutil.rmtree(entry.path)
            entry.path.mkdir(parents=True, exist_ok=True)  # recreate empty dir
            _log_action("clean_cache", entry.path)
            log.info("cleaned %s (%s)", entry.category, bytes_to_human(entry.size))
            results.append(CleanResult(
                path=entry.path,
                category=entry.category,
                size_before=entry.size,
                deleted=True,
            ))
        except Exception as exc:
            log.error("failed to clean %s: %s", entry.category, exc)
            results.append(CleanResult(
                path=entry.path,
                category=entry.category,
                size_before=entry.size,
                deleted=False,
                error=str(exc),
            ))

    return results
