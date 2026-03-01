from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from osx_system_agent.clean.trash import delete_file
from osx_system_agent.log import get_logger
from osx_system_agent.scanners.junk import scan_junk
from osx_system_agent.utils.human import bytes_to_human

log = get_logger("clean.junk")


@dataclass
class JunkCleanResult:
    path: Path
    category: str
    size: int
    deleted: bool
    error: str | None = None


def clean_junk(
    root: Path,
    dry_run: bool = True,
) -> list[JunkCleanResult]:
    junk_files = scan_junk(root)
    results: list[JunkCleanResult] = []

    for jf in junk_files:
        if dry_run:
            log.info("[dry-run] would delete %s (%s)", jf.path, bytes_to_human(jf.size))
            results.append(JunkCleanResult(
                path=jf.path,
                category=jf.category,
                size=jf.size,
                deleted=False,
            ))
            continue

        success = delete_file(jf.path)
        if success:
            log.info("deleted %s (%s)", jf.path, bytes_to_human(jf.size))
        else:
            log.error("failed to delete %s", jf.path)

        results.append(JunkCleanResult(
            path=jf.path,
            category=jf.category,
            size=jf.size,
            deleted=success,
            error=None if success else "delete failed",
        ))

    return results
