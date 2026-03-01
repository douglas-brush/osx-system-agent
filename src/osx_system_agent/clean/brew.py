from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from osx_system_agent.log import get_logger
from osx_system_agent.scanners.brew import BrewPackage, scan_brew

log = get_logger("clean.brew")


@dataclass
class BrewCleanResult:
    upgraded: list[BrewPackage] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    cleaned_bytes: int = 0
    dry_run: bool = True


def upgrade_outdated(dry_run: bool = True) -> BrewCleanResult:
    """Upgrade outdated Homebrew packages."""
    audit = scan_brew()
    all_outdated = [*audit.outdated_formulae, *audit.outdated_casks]

    if not all_outdated:
        log.info("no outdated packages")
        return BrewCleanResult(dry_run=dry_run)

    if dry_run:
        log.info("[dry-run] would upgrade %d packages", len(all_outdated))
        return BrewCleanResult(upgraded=all_outdated, dry_run=True)

    result = BrewCleanResult(dry_run=False)

    for pkg in all_outdated:
        cmd = ["brew", "upgrade"]
        if pkg.is_cask:
            cmd.append("--cask")
        cmd.append(pkg.name)

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                check=True,
            )
            result.upgraded.append(pkg)
            log.info("upgraded %s", pkg.name)
        except subprocess.CalledProcessError as exc:
            msg = f"failed to upgrade {pkg.name}: {exc.stderr.strip()}"
            result.failed.append(msg)
            log.error(msg)
        except subprocess.TimeoutExpired:
            msg = f"timeout upgrading {pkg.name}"
            result.failed.append(msg)
            log.error(msg)

    return result


def brew_cleanup(dry_run: bool = True) -> int:
    """Run brew cleanup to remove old versions and cache."""
    if dry_run:
        result = subprocess.run(
            ["brew", "cleanup", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        log.info("[dry-run] brew cleanup output:\n%s", result.stdout)
        return 0

    result = subprocess.run(
        ["brew", "cleanup"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    log.info("brew cleanup: %s", result.stdout.strip())
    return result.returncode
