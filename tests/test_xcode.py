from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from osx_system_agent.scanners.xcode import (
    XcodeAudit,
    _dir_size,
    _scan_derived_data,
    scan_xcode,
)


class TestDirSize:
    def test_calculates_size(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        f2 = tmp_path / "sub" / "b.txt"
        f2.parent.mkdir()
        f2.write_text("world!")
        size = _dir_size(tmp_path)
        assert size == 5 + 6

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert _dir_size(tmp_path) == 0


class TestScanDerivedData:
    def test_no_xcode_dir(self, tmp_path: Path) -> None:
        with patch(
            "osx_system_agent.scanners.xcode.Path.home",
            return_value=tmp_path,
        ):
            projects, total = _scan_derived_data()
        assert projects == []
        assert total == 0

    def test_finds_projects(self, tmp_path: Path) -> None:
        dd = tmp_path / "Library" / "Developer" / "Xcode" / "DerivedData"
        dd.mkdir(parents=True)
        proj = dd / "MyApp-abcdef123"
        proj.mkdir()
        (proj / "Build").mkdir()
        (proj / "Build" / "output.o").write_bytes(b"x" * 1000)

        with patch(
            "osx_system_agent.scanners.xcode.Path.home",
            return_value=tmp_path,
        ):
            projects, total = _scan_derived_data()

        assert len(projects) == 1
        assert projects[0].name == "MyApp"
        assert total == 1000


class TestScanXcode:
    def test_returns_audit(self, tmp_path: Path) -> None:
        with (
            patch(
                "osx_system_agent.scanners.xcode.Path.home",
                return_value=tmp_path,
            ),
            patch(
                "osx_system_agent.scanners.xcode._scan_simulators",
                return_value=([], []),
            ),
        ):
            audit = scan_xcode()
        assert isinstance(audit, XcodeAudit)
