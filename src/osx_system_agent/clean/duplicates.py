from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from osx_system_agent.clean.trash import move_to_trash
from osx_system_agent.log import get_logger
from osx_system_agent.scanners.duplicates import scan_duplicates
from osx_system_agent.utils.human import bytes_to_human

log = get_logger("clean.duplicates")


@dataclass
class DedupResult:
    kept: Path
    removed: list[Path]
    size_freed: int
    dry_run: bool
    errors: list[str]


def _pick_keeper(files: list[Path]) -> Path:
    """Pick which file to keep. Prefer shorter path, then alphabetically first."""
    return min(files, key=lambda p: (len(str(p)), str(p)))


def clean_duplicates(
    root: Path,
    min_size: int = 0,
    excludes: list[str] | None = None,
    dry_run: bool = True,
    follow_symlinks: bool = False,
) -> list[DedupResult]:
    groups = scan_duplicates(
        root,
        min_size=min_size,
        excludes=excludes,
        follow_symlinks=follow_symlinks,
    )

    results: list[DedupResult] = []

    for group in groups:
        keeper = _pick_keeper(group.files)
        to_remove = [f for f in group.files if f != keeper]
        errors: list[str] = []

        if dry_run:
            log.info(
                "[dry-run] keep %s, would trash %d dupes (%s each)",
                keeper,
                len(to_remove),
                bytes_to_human(group.size),
            )
        else:
            actually_removed = []
            for path in to_remove:
                if move_to_trash(path):
                    log.info("trashed duplicate: %s", path)
                    actually_removed.append(path)
                else:
                    msg = f"failed to trash: {path}"
                    log.error(msg)
                    errors.append(msg)
            to_remove = actually_removed

        results.append(DedupResult(
            kept=keeper,
            removed=to_remove,
            size_freed=group.size * len(to_remove),
            dry_run=dry_run,
            errors=errors,
        ))

    return results
