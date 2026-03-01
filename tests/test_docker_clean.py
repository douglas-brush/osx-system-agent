from __future__ import annotations

from unittest.mock import patch

from osx_system_agent.clean.docker import DockerCleanResult, docker_prune


class TestDockerPrune:
    @patch("osx_system_agent.clean.docker.shutil.which", return_value=None)
    def test_not_installed(self, mock_which) -> None:
        result = docker_prune(dry_run=True)
        assert isinstance(result, DockerCleanResult)
        assert result.error == "Docker not installed"

    @patch("osx_system_agent.clean.docker.subprocess.run")
    @patch(
        "osx_system_agent.clean.docker.shutil.which",
        return_value="/usr/local/bin/docker",
    )
    def test_not_running(self, mock_which, mock_run) -> None:
        from unittest.mock import MagicMock

        mock_run.return_value = MagicMock(returncode=1)
        result = docker_prune(dry_run=True)
        assert result.error == "Docker not running"

    @patch("osx_system_agent.clean.docker.subprocess.run")
    @patch(
        "osx_system_agent.clean.docker.shutil.which",
        return_value="/usr/local/bin/docker",
    )
    def test_dry_run_shows_df(self, mock_which, mock_run) -> None:
        from unittest.mock import MagicMock

        # First call: docker info (success)
        # Second call: docker system df
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout="TYPE  TOTAL  RECLAIMABLE\n"),
        ]
        result = docker_prune(dry_run=True)
        assert result.dry_run is True
        assert result.error is None
