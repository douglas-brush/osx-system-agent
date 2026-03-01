from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from osx_system_agent.clean.trash import _log_action
from osx_system_agent.log import get_logger
from osx_system_agent.scanners.xcode import scan_xcode
from osx_system_agent.utils.human import bytes_to_human

log = get_logger("clean.xcode")


@dataclass
class XcodeCleanResult:
    derived_data_freed: int = 0
    derived_data_count: int = 0
    archives_freed: int = 0
    archives_count: int = 0
    simulators_removed: int = 0
    errors: list[str] | None = None
    dry_run: bool = True


def clean_xcode(
    derived_data: bool = True,
    archives: bool = False,
    unavailable_sims: bool = False,
    dry_run: bool = True,
) -> XcodeCleanResult:
    """Clean Xcode derived data, archives, and unavailable simulators."""
    audit = scan_xcode()
    result = XcodeCleanResult(dry_run=dry_run)
    errors: list[str] = []

    # Derived data
    if derived_data and audit.derived_data:
        for proj in audit.derived_data:
            if dry_run:
                log.info(
                    "[dry-run] would remove derived data: %s (%s)",
                    proj.name, bytes_to_human(proj.size),
                )
                result.derived_data_freed += proj.size
                result.derived_data_count += 1
            else:
                try:
                    shutil.rmtree(proj.path)
                    _log_action("clean_xcode_dd", proj.path)
                    result.derived_data_freed += proj.size
                    result.derived_data_count += 1
                    log.info("removed derived data: %s", proj.name)
                except Exception as exc:
                    errors.append(f"failed to remove {proj.path}: {exc}")

    # Archives
    if archives and audit.archives:
        for arch in audit.archives:
            if dry_run:
                log.info(
                    "[dry-run] would remove archive: %s (%s)",
                    arch.name, bytes_to_human(arch.size),
                )
                result.archives_freed += arch.size
                result.archives_count += 1
            else:
                try:
                    shutil.rmtree(arch.path)
                    _log_action("clean_xcode_archive", arch.path)
                    result.archives_freed += arch.size
                    result.archives_count += 1
                    log.info("removed archive: %s", arch.name)
                except Exception as exc:
                    errors.append(f"failed to remove {arch.path}: {exc}")

    # Unavailable simulators
    if unavailable_sims and audit.simulators_unavailable:
        if dry_run:
            result.simulators_removed = len(audit.simulators_unavailable)
            log.info(
                "[dry-run] would remove %d unavailable simulators",
                result.simulators_removed,
            )
        else:
            try:
                subprocess.run(
                    ["xcrun", "simctl", "delete", "unavailable"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=True,
                )
                result.simulators_removed = len(audit.simulators_unavailable)
                log.info("removed unavailable simulators")
            except (subprocess.CalledProcessError, FileNotFoundError) as exc:
                errors.append(f"failed to remove simulators: {exc}")

    result.errors = errors if errors else None
    return result
