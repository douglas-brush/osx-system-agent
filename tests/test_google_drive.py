from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from osx_system_agent.scanners.google_drive import (
    DriveAccount,
    DriveFile,
    DriveQuota,
    GoogleDriveAudit,
    SharedDrive,
    _api_files_to_drive_files,
    _categorize,
    _categorize_mime,
    _find_app,
    _parse_api_time,
    scan_google_drive,
    scan_google_drive_api,
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


class TestCategorizeMime:
    def test_google_docs(self) -> None:
        assert _categorize_mime(
            "application/vnd.google-apps.document", "Untitled"
        ) == "Google Docs"

    def test_google_sheets(self) -> None:
        assert _categorize_mime(
            "application/vnd.google-apps.spreadsheet", "Budget"
        ) == "Google Sheets"

    def test_image_prefix(self) -> None:
        assert _categorize_mime("image/jpeg", "photo.jpg") == "Images"
        assert _categorize_mime("image/png", "screenshot.png") == "Images"

    def test_video_prefix(self) -> None:
        assert _categorize_mime("video/mp4", "clip.mp4") == "Video"

    def test_fallback_to_extension(self) -> None:
        assert _categorize_mime(
            "application/octet-stream", "archive.zip"
        ) == "Archives"

    def test_unknown_mime_unknown_ext(self) -> None:
        assert _categorize_mime("application/x-custom", "file.xyz") == "Other"


class TestParseApiTime:
    def test_valid_iso(self) -> None:
        ts = _parse_api_time("2026-01-15T10:30:00.000Z")
        assert ts > 0

    def test_none(self) -> None:
        assert _parse_api_time(None) == 0.0

    def test_empty(self) -> None:
        assert _parse_api_time("") == 0.0

    def test_invalid(self) -> None:
        assert _parse_api_time("not-a-date") == 0.0


class TestApiFilesToDriveFiles:
    def test_converts_files(self) -> None:
        raw = [
            {
                "id": "abc123",
                "name": "report.pdf",
                "mimeType": "application/pdf",
                "quotaBytesUsed": "5000",
                "owners": [{"displayName": "Douglas Brush"}],
                "shared": True,
                "modifiedTime": "2026-01-15T10:30:00.000Z",
            },
            {
                "id": "def456",
                "name": "photo.jpg",
                "mimeType": "image/jpeg",
                "size": "3000",
                "owners": [],
                "shared": False,
                "modifiedTime": "2025-12-01T00:00:00.000Z",
            },
        ]
        files = _api_files_to_drive_files(raw)
        assert len(files) == 2
        # Sorted by size desc
        assert files[0].name == "report.pdf"
        assert files[0].size == 5000
        assert files[0].category == "Documents"
        assert files[0].shared is True
        assert files[0].owner == "Douglas Brush"
        assert files[0].file_id == "abc123"
        assert files[0].cloud_only is True
        assert files[1].name == "photo.jpg"
        assert files[1].size == 3000
        assert files[1].category == "Images"

    def test_google_doc_zero_size(self) -> None:
        raw = [
            {
                "id": "gdoc1",
                "name": "My Doc",
                "mimeType": "application/vnd.google-apps.document",
                "quotaBytesUsed": "0",
                "owners": [{"displayName": "Test"}],
                "shared": False,
            },
        ]
        files = _api_files_to_drive_files(raw)
        assert len(files) == 1
        assert files[0].size == 0
        assert files[0].category == "Google Docs"


class TestFindApp:
    @patch("osx_system_agent.scanners.google_drive.Path.exists", return_value=False)
    def test_not_installed(self, mock_exists) -> None:
        result = _find_app()
        assert result is None


class TestDriveQuota:
    def test_pct_used(self) -> None:
        q = DriveQuota(
            email="test@example.com",
            display_name="Test",
            limit=100_000_000,
            usage=75_000_000,
        )
        assert q.pct_used is not None
        assert abs(q.pct_used - 75.0) < 0.1

    def test_unlimited_plan(self) -> None:
        q = DriveQuota(
            email="test@example.com",
            display_name="Test",
            limit=None,
            usage=50_000_000,
        )
        assert q.pct_used is None


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


class TestScanGoogleDriveApi:
    @patch("osx_system_agent.scanners.google_drive._build_service")
    def test_api_scan_success(self, mock_build) -> None:
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Mock about().get()
        mock_service.about().get().execute.return_value = {
            "user": {
                "emailAddress": "douglas@brushcyber.com",
                "displayName": "Douglas Brush",
            },
            "storageQuota": {
                "limit": "16106127360",
                "usage": "8053063680",
                "usageInDrive": "7000000000",
                "usageInDriveTrash": "500000000",
            },
        }

        # Mock files().list() — My Drive files
        mock_service.files().list().execute.return_value = {
            "files": [
                {
                    "id": "f1",
                    "name": "big_video.mp4",
                    "mimeType": "video/mp4",
                    "quotaBytesUsed": "500000000",
                    "owners": [{"displayName": "Douglas Brush"}],
                    "shared": False,
                    "modifiedTime": "2026-01-15T10:00:00.000Z",
                },
                {
                    "id": "f2",
                    "name": "report.pdf",
                    "mimeType": "application/pdf",
                    "quotaBytesUsed": "5000000",
                    "owners": [{"displayName": "Douglas Brush"}],
                    "shared": True,
                    "modifiedTime": "2026-02-01T00:00:00.000Z",
                },
            ],
        }

        # Mock drives().list()
        mock_service.drives().list().execute.return_value = {
            "drives": [
                {"id": "sd1", "name": "Team Drive"},
            ],
        }

        audit = scan_google_drive_api(limit=10)
        assert audit.api_mode is True
        assert audit.quota is not None
        assert audit.quota.email == "douglas@brushcyber.com"
        assert audit.quota.usage == 8053063680
        assert audit.quota.pct_used is not None
        assert len(audit.largest_files) == 2
        assert audit.largest_files[0].name == "big_video.mp4"
        assert len(audit.shared_drives) == 1

    @patch("osx_system_agent.scanners.google_drive._build_service")
    def test_api_no_credentials(self, mock_build) -> None:
        mock_build.side_effect = FileNotFoundError(
            "OAuth credentials not found at /nonexistent/credentials.json"
        )
        audit = scan_google_drive_api(
            credentials_path=Path("/nonexistent/credentials.json"),
        )
        assert audit.error is not None
        assert "credentials" in audit.error.lower()


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
        assert f.shared is False
        assert f.file_id is None

    def test_api_file_fields(self) -> None:
        f = DriveFile(
            name="cloud.pdf",
            path="drive://abc123",
            size=5000,
            mtime=1700000000.0,
            category="Documents",
            cloud_only=True,
            mime_type="application/pdf",
            shared=True,
            owner="Douglas Brush",
            file_id="abc123",
        )
        assert f.cloud_only is True
        assert f.file_id == "abc123"
        assert f.owner == "Douglas Brush"


class TestSharedDrive:
    def test_defaults(self) -> None:
        sd = SharedDrive(drive_id="sd1", name="Team")
        assert sd.file_count == 0
        assert sd.total_size == 0
