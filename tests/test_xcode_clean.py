from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from osx_system_agent.clean.xcode import clean_xcode
from osx_system_agent.scanners.xcode import (
    DerivedDataProject,
    XcodeArchive,
    XcodeAudit,
)


def _mock_audit(
    derived: list[DerivedDataProject] | None = None,
    archives: list[XcodeArchive] | None = None,
) -> XcodeAudit:
    return XcodeAudit(
        derived_data=derived or [],
        derived_data_total=sum(d.size for d in (derived or [])),
        archives=archives or [],
        archives_total=sum(a.size for a in (archives or [])),
        simulators=[],
        simulators_unavailable=[],
        xcode_installed=True,
    )


class TestCleanXcode:
    @patch("osx_system_agent.clean.xcode.scan_xcode")
    def test_dry_run_derived_data(self, mock_scan, tmp_path: Path) -> None:
        proj = DerivedDataProject(
            name="TestApp",
            path=tmp_path / "DerivedData" / "TestApp-abc",
            size=500_000,
            last_modified=1000.0,
        )
        mock_scan.return_value = _mock_audit(derived=[proj])

        result = clean_xcode(
            derived_data=True, dry_run=True
        )
        assert result.dry_run is True
        assert result.derived_data_count == 1
        assert result.derived_data_freed == 500_000

    @patch("osx_system_agent.clean.xcode.scan_xcode")
    def test_no_data_returns_empty(self, mock_scan) -> None:
        mock_scan.return_value = _mock_audit()
        result = clean_xcode(dry_run=True)
        assert result.derived_data_count == 0
        assert result.archives_count == 0

    @patch("osx_system_agent.clean.xcode.shutil.rmtree")
    @patch("osx_system_agent.clean.xcode._log_action")
    @patch("osx_system_agent.clean.xcode.scan_xcode")
    def test_live_removes(
        self, mock_scan, mock_log, mock_rmtree, tmp_path: Path,
    ) -> None:
        proj = DerivedDataProject(
            name="App",
            path=tmp_path / "dd",
            size=1_000_000,
            last_modified=1000.0,
        )
        mock_scan.return_value = _mock_audit(derived=[proj])

        result = clean_xcode(
            derived_data=True, dry_run=False
        )
        assert result.dry_run is False
        assert result.derived_data_count == 1
        assert mock_rmtree.called
