from __future__ import annotations

from unittest.mock import MagicMock, patch

from osx_system_agent.clean.brew import upgrade_outdated
from osx_system_agent.scanners.brew import BrewAudit, BrewPackage


def _mock_audit(outdated: list[BrewPackage] | None = None) -> BrewAudit:
    return BrewAudit(
        formulae=[],
        casks=[],
        outdated_formulae=outdated or [],
        outdated_casks=[],
        brew_version="Homebrew 4.0.0",
        brew_prefix="/opt/homebrew",
    )


class TestUpgradeOutdated:
    @patch("osx_system_agent.clean.brew.scan_brew")
    def test_no_outdated(self, mock_scan) -> None:
        mock_scan.return_value = _mock_audit()
        result = upgrade_outdated(dry_run=True)
        assert result.upgraded == []
        assert result.dry_run is True

    @patch("osx_system_agent.clean.brew.scan_brew")
    def test_dry_run_lists_packages(self, mock_scan) -> None:
        pkgs = [
            BrewPackage("pkg1", "1.0", False, True, False),
            BrewPackage("pkg2", "2.0", False, True, False),
        ]
        mock_scan.return_value = _mock_audit(outdated=pkgs)
        result = upgrade_outdated(dry_run=True)
        assert len(result.upgraded) == 2
        assert result.dry_run is True

    @patch("osx_system_agent.clean.brew.subprocess.run")
    @patch("osx_system_agent.clean.brew.scan_brew")
    def test_live_upgrade(self, mock_scan, mock_run) -> None:
        pkgs = [BrewPackage("pkg1", "1.0", False, True, False)]
        mock_scan.return_value = _mock_audit(outdated=pkgs)
        mock_run.return_value = MagicMock(returncode=0)
        result = upgrade_outdated(dry_run=False)
        assert len(result.upgraded) == 1
        assert result.dry_run is False
        assert mock_run.called
