from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field

from osx_system_agent.log import get_logger

log = get_logger("scanners.docker")


@dataclass
class DockerImage:
    repository: str
    tag: str
    image_id: str
    size: int
    created: str


@dataclass
class DockerContainer:
    container_id: str
    name: str
    image: str
    status: str
    state: str
    size: int


@dataclass
class DockerVolume:
    name: str
    driver: str
    mountpoint: str


@dataclass
class DockerAudit:
    installed: bool = False
    running: bool = False
    images: list[DockerImage] = field(default_factory=list)
    containers: list[DockerContainer] = field(default_factory=list)
    volumes: list[DockerVolume] = field(default_factory=list)
    disk_usage: dict[str, int] = field(default_factory=dict)
    error: str | None = None


def _run_docker(*args: str) -> str | None:
    docker = shutil.which("docker")
    if not docker:
        return None
    try:
        result = subprocess.run(
            [docker, *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.debug("docker %s failed: %s", " ".join(args), result.stderr)
            return None
        return result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return None


def scan_docker() -> DockerAudit:
    """Audit Docker images, containers, and volumes."""
    audit = DockerAudit()

    if not shutil.which("docker"):
        audit.error = "Docker not installed"
        return audit

    audit.installed = True

    # Check if Docker is running
    info_output = _run_docker("info", "--format", "{{.ServerVersion}}")
    if info_output is None:
        audit.error = "Docker not running"
        return audit

    audit.running = True

    # Images
    img_output = _run_docker(
        "image", "ls", "--format",
        '{"repository":"{{.Repository}}","tag":"{{.Tag}}",'
        '"id":"{{.ID}}","size":"{{.Size}}","created":"{{.CreatedAt}}"}',
    )
    if img_output:
        for line in img_output.strip().splitlines():
            try:
                data = json.loads(line)
                audit.images.append(DockerImage(
                    repository=data["repository"],
                    tag=data["tag"],
                    image_id=data["id"],
                    size=_parse_docker_size(data["size"]),
                    created=data["created"],
                ))
            except (json.JSONDecodeError, KeyError):
                continue

    # Containers (including stopped)
    ctr_output = _run_docker(
        "container", "ls", "-a", "--format",
        '{"id":"{{.ID}}","name":"{{.Names}}","image":"{{.Image}}",'
        '"status":"{{.Status}}","state":"{{.State}}","size":"{{.Size}}"}',
        "--size",
    )
    if ctr_output:
        for line in ctr_output.strip().splitlines():
            try:
                data = json.loads(line)
                audit.containers.append(DockerContainer(
                    container_id=data["id"],
                    name=data["name"],
                    image=data["image"],
                    status=data["status"],
                    state=data["state"],
                    size=_parse_docker_size(data.get("size", "0B")),
                ))
            except (json.JSONDecodeError, KeyError):
                continue

    # Volumes
    vol_output = _run_docker(
        "volume", "ls", "--format",
        '{"name":"{{.Name}}","driver":"{{.Driver}}",'
        '"mountpoint":"{{.Mountpoint}}"}',
    )
    if vol_output:
        for line in vol_output.strip().splitlines():
            try:
                data = json.loads(line)
                audit.volumes.append(DockerVolume(
                    name=data["name"],
                    driver=data["driver"],
                    mountpoint=data["mountpoint"],
                ))
            except (json.JSONDecodeError, KeyError):
                continue

    # Disk usage summary
    du_output = _run_docker("system", "df", "--format", "json")
    if du_output:
        try:
            # Docker returns one JSON array
            du_data = json.loads(du_output)
            if isinstance(du_data, list):
                for item in du_data:
                    audit.disk_usage[item.get("Type", "")] = item.get(
                        "Size", 0
                    )
        except (json.JSONDecodeError, TypeError):
            pass

    audit.images.sort(key=lambda i: i.size, reverse=True)
    return audit


def _parse_docker_size(size_str: str) -> int:
    """Parse Docker size strings like '1.2GB', '500MB', '12.3kB'."""
    size_str = size_str.strip()
    # Handle compound sizes like "100MB (virtual 1.2GB)"
    if "(" in size_str:
        size_str = size_str.split("(")[0].strip()

    multipliers = {
        "B": 1,
        "kB": 1000,
        "KB": 1024,
        "MB": 1_000_000,
        "GB": 1_000_000_000,
        "TB": 1_000_000_000_000,
    }

    for suffix, mult in sorted(
        multipliers.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if size_str.endswith(suffix):
            try:
                return int(float(size_str[: -len(suffix)]) * mult)
            except ValueError:
                return 0
    return 0
