from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from osx_system_agent.scanners.google_drive import (
    DriveAccount,
    DriveFile,
    GoogleDriveAudit,
    _categorize,
    _find_app,
    scan_google_drive,
)


class TestCategorize:
    def test_documents(self) -> None:
        assert _categorize(".pdf") == "Documents"
        assert _categorize(".docx") == "Documents"
        assert _categorize(".xlsx") == "Documents"

    def test_images(self) -> None:
        assert _categorize(".jpg") == "Images"
        assert _categorize(".PNG") == "Images"
        assert _categorize(".heic") == "Images"

    def test_video(self) -> None:
        assert _categorize(".mp4") == "Video"
        assert _categorize(".mov") == "Video"

    def test_code(self) -> None:
        assert _categorize(".py") == "Code"
        assert _categorize(".js") == "Code"

    def test_unknown(self) -> None:
        assert _categorize(".xyz") == "Other"
        assert _categorize("") == "Other"


class TestFindApp:
    @patch("osx_system_agent.scanners.google_drive.Path.exists", return_value=False)
    def test_not_installed(self, mock_exists) -> None:
        result = _find_app()
        assert result is None


class TestScanGoogleDrive:
    @patch(
        "osx_system_agent.scanners.google_drive._find_accounts",
        return_value=[],
    )
    @patch(
        "osx_system_agent.scanners.google_drive._find_app",
        return_value=None,
    )
    def test_no_drive_returns_error(self, mock_app, mock_accts) -> None:
        audit = scan_google_drive()
        assert isinstance(audit, GoogleDriveAudit)
        assert not audit.installed
        assert audit.error is not None
        assert "not installed" in audit.error

    @patch(
        "osx_system_agent.scanners.google_drive._find_accounts",
        return_value=[],
    )
    @patch(
        "osx_system_agent.scanners.google_drive._find_app",
        return_value="/Applications/Google Drive.app",
    )
    def test_installed_no_accounts(self, mock_app, mock_accts) -> None:
        audit = scan_google_drive()
        assert audit.installed
        assert audit.error is not None
        assert "no synced accounts" in audit.error

    @patch("osx_system_agent.scanners.google_drive._find_accounts")
    @patch(
        "osx_system_agent.scanners.google_drive._find_app",
        return_value="/Applications/Google Drive.app",
    )
    def test_with_account_scans_files(self, mock_app, mock_accts, tmp_path) -> None:
        # Set up a fake drive structure
        my_drive = tmp_path / "My Drive"
        my_drive.mkdir()
        (my_drive / "report.pdf").write_bytes(b"x" * 1000)
        (my_drive / "photo.jpg").write_bytes(b"y" * 2000)
        sub = my_drive / "Projects"
        sub.mkdir()
        (sub / "code.py").write_bytes(b"z" * 500)

        mock_accts.return_value = [
            DriveAccount(
                email="test@example.com",
                root_path=tmp_path,
                my_drive_path=my_drive,
            ),
        ]

        audit = scan_google_drive(limit=10)
        assert audit.installed
        assert audit.error is None
        assert audit.total_files == 3
        assert audit.total_size == 3500
        assert len(audit.largest_files) == 3
        assert audit.largest_files[0].name == "photo.jpg"
        assert "Images" in audit.categories
        assert "Documents" in audit.categories
        assert "Code" in audit.categories

    @patch("osx_system_agent.scanners.google_drive._find_accounts")
    @patch(
        "osx_system_agent.scanners.google_drive._find_app",
        return_value="/Applications/Google Drive.app",
    )
    def test_min_size_filter(self, mock_app, mock_accts, tmp_path) -> None:
        my_drive = tmp_path / "My Drive"
        my_drive.mkdir()
        (my_drive / "small.txt").write_bytes(b"x" * 100)
        (my_drive / "big.pdf").write_bytes(b"y" * 5000)

        mock_accts.return_value = [
            DriveAccount(
                email="test@example.com",
                root_path=tmp_path,
                my_drive_path=my_drive,
            ),
        ]

        audit = scan_google_drive(limit=10, min_size=1000)
        # total_files counts all, largest_files only above min_size
        assert audit.total_files == 2
        assert len(audit.largest_files) == 1
        assert audit.largest_files[0].name == "big.pdf"

    @patch("osx_system_agent.scanners.google_drive._find_accounts")
    @patch(
        "osx_system_agent.scanners.google_drive._find_app",
        return_value="/Applications/Google Drive.app",
    )
    def test_shared_drives(self, mock_app, mock_accts, tmp_path) -> None:
        shared = tmp_path / "Shared drives"
        shared.mkdir()
        team = shared / "Team Drive"
        team.mkdir()
        (team / "deck.pptx").write_bytes(b"p" * 3000)

        mock_accts.return_value = [
            DriveAccount(
                email="test@example.com",
                root_path=tmp_path,
                shared_drives_path=shared,
            ),
        ]

        audit = scan_google_drive()
        assert audit.total_files == 1
        assert len(audit.storage) == 1
        assert "Shared Drives" in audit.storage[0].location

    @patch("osx_system_agent.scanners.google_drive._find_accounts")
    @patch(
        "osx_system_agent.scanners.google_drive._find_app",
        return_value="/Applications/Google Drive.app",
    )
    def test_storage_summary_categories(self, mock_app, mock_accts, tmp_path) -> None:
        my_drive = tmp_path / "My Drive"
        my_drive.mkdir()
        (my_drive / "a.pdf").write_bytes(b"a" * 100)
        (my_drive / "b.pdf").write_bytes(b"b" * 200)
        (my_drive / "c.jpg").write_bytes(b"c" * 300)

        mock_accts.return_value = [
            DriveAccount(
                email="test@example.com",
                root_path=tmp_path,
                my_drive_path=my_drive,
            ),
        ]

        audit = scan_google_drive()
        assert len(audit.storage) == 1
        summary = audit.storage[0]
        assert "Documents" in summary.by_category
        assert summary.by_category["Documents"]["count"] == 2
        assert summary.by_category["Documents"]["size"] == 300
        assert "Images" in summary.by_category


class TestDriveFile:
    def test_dataclass_fields(self) -> None:
        f = DriveFile(
            name="test.pdf",
            path=Path("/tmp/test.pdf"),
            size=1000,
            mtime=1700000000.0,
            category="Documents",
        )
        assert f.name == "test.pdf"
        assert f.cloud_only is False
