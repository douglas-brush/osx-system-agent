from __future__ import annotations

from unittest.mock import patch

from osx_system_agent.scanners.docker import (
    DockerAudit,
    _parse_docker_size,
    scan_docker,
)


class TestParseDockerSize:
    def test_megabytes(self) -> None:
        assert _parse_docker_size("500MB") == 500_000_000

    def test_gigabytes(self) -> None:
        assert _parse_docker_size("1.2GB") == 1_200_000_000

    def test_kilobytes(self) -> None:
        assert _parse_docker_size("100kB") == 100_000

    def test_bytes(self) -> None:
        assert _parse_docker_size("42B") == 42

    def test_compound_size(self) -> None:
        # Docker sometimes shows "100MB (virtual 1.2GB)"
        result = _parse_docker_size("100MB (virtual 1.2GB)")
        assert result == 100_000_000

    def test_empty_string(self) -> None:
        assert _parse_docker_size("") == 0


class TestScanDocker:
    @patch("osx_system_agent.scanners.docker.shutil.which", return_value=None)
    def test_not_installed(self, mock_which) -> None:
        audit = scan_docker()
        assert isinstance(audit, DockerAudit)
        assert audit.installed is False
        assert audit.error == "Docker not installed"

    @patch(
        "osx_system_agent.scanners.docker._run_docker",
        return_value=None,
    )
    @patch(
        "osx_system_agent.scanners.docker.shutil.which",
        return_value="/usr/local/bin/docker",
    )
    def test_not_running(self, mock_which, mock_run) -> None:
        audit = scan_docker()
        assert audit.installed is True
        assert audit.running is False
