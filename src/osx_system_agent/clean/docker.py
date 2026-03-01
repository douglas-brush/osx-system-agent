from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from osx_system_agent.log import get_logger

log = get_logger("clean.docker")


@dataclass
class DockerCleanResult:
    images_removed: int = 0
    containers_removed: int = 0
    volumes_removed: int = 0
    space_reclaimed: str = ""
    dry_run: bool = True
    error: str | None = None


def docker_prune(
    all_images: bool = False,
    volumes: bool = False,
    dry_run: bool = True,
) -> DockerCleanResult:
    """Run Docker system prune."""
    docker = shutil.which("docker")
    if not docker:
        return DockerCleanResult(
            error="Docker not installed", dry_run=dry_run,
        )

    # Check Docker is running
    try:
        check = subprocess.run(
            [docker, "info"],
            capture_output=True,
            timeout=10,
        )
        if check.returncode != 0:
            return DockerCleanResult(
                error="Docker not running", dry_run=dry_run,
            )
    except (subprocess.TimeoutExpired, OSError):
        return DockerCleanResult(
            error="Docker not responding", dry_run=dry_run,
        )

    if dry_run:
        # Show what would be pruned
        cmd = [docker, "system", "df"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        log.info("[dry-run] docker system df:\n%s", result.stdout)
        return DockerCleanResult(
            space_reclaimed=result.stdout.strip(), dry_run=True,
        )

    cmd = [docker, "system", "prune", "-f"]
    if all_images:
        cmd.append("-a")
    if volumes:
        cmd.append("--volumes")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        log.info("docker prune output: %s", result.stdout.strip())

        return DockerCleanResult(
            space_reclaimed=result.stdout.strip(),
            dry_run=False,
        )
    except subprocess.TimeoutExpired:
        return DockerCleanResult(
            error="Docker prune timed out", dry_run=False,
        )
