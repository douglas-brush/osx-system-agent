"""Tests for the content-aware file renamer."""

from __future__ import annotations

import plistlib
from pathlib import Path
from unittest.mock import patch

from osx_system_agent.renamer import (
    RenameProposal,
    _deconflict,
    _sanitize_filename,
    execute_renames,
    needs_rename,
    propose_rename,
    scan_for_renames,
)


# ---- needs_rename -----------------------------------------------------------


def test_needs_rename_generic_names() -> None:
    assert needs_rename(Path("Untitled.png")) is True
    assert needs_rename(Path("image.png")) is True
    assert needs_rename(Path("IMG_1234.jpg")) is True
    assert needs_rename(Path("Pasted_Image_123.png")) is True


def test_needs_rename_opaque_names() -> None:
    assert needs_rename(Path("7dcadb20b2c6b8c4f14ac099fb3132f7a21427.jpg")) is True
    assert needs_rename(Path("abcdef1234567890abcd.pdf")) is True


def test_needs_rename_copy_suffix() -> None:
    assert needs_rename(Path("document (1).pdf")) is True


def test_needs_rename_good_names() -> None:
    assert needs_rename(Path("2026_Tax_Return.pdf")) is False
    assert needs_rename(Path("Meeting_Notes.docx")) is False
    assert needs_rename(Path("BrushCyber_MSA.docx")) is False


# ---- _sanitize_filename ----------------------------------------------------


def test_sanitize_removes_unsafe_chars() -> None:
    assert _sanitize_filename('foo/bar:baz*"qux') == "foo_bar_baz_qux"


def test_sanitize_collapses_whitespace() -> None:
    assert _sanitize_filename("hello   world  test") == "hello_world_test"


def test_sanitize_truncates() -> None:
    long_name = "a" * 100
    assert len(_sanitize_filename(long_name)) <= 80


# ---- _deconflict -----------------------------------------------------------


def test_deconflict_no_conflict(tmp_path: Path) -> None:
    proposed = tmp_path / "newfile.txt"
    assert _deconflict(proposed) == proposed


def test_deconflict_with_conflict(tmp_path: Path) -> None:
    (tmp_path / "newfile.txt").write_text("existing")
    proposed = tmp_path / "newfile.txt"
    result = _deconflict(proposed)
    assert result.name == "newfile_2.txt"


def test_deconflict_multiple_conflicts(tmp_path: Path) -> None:
    (tmp_path / "newfile.txt").write_text("existing")
    (tmp_path / "newfile_2.txt").write_text("existing")
    (tmp_path / "newfile_3.txt").write_text("existing")
    proposed = tmp_path / "newfile.txt"
    result = _deconflict(proposed)
    assert result.name == "newfile_4.txt"


# ---- propose_rename ---------------------------------------------------------


def test_propose_rename_webloc(tmp_path: Path) -> None:
    webloc = tmp_path / "Some Bookmark.webloc"
    plist_data = {"URL": "https://www.example.com/articles/cool-stuff"}
    webloc.write_bytes(plistlib.dumps(plist_data))

    proposal = propose_rename(webloc)
    assert proposal.source == "webloc_url"
    assert "example.com" in proposal.proposed.name


def test_propose_rename_eml(tmp_path: Path) -> None:
    eml = tmp_path / "message.eml"
    eml.write_text(
        "From: sender@example.com\n"
        "Subject: Urgent Security Alert\n"
        "\n"
        "Body content here.\n"
    )
    proposal = propose_rename(eml)
    assert proposal.source == "email_subject"
    assert "Urgent" in proposal.proposed.stem or "Security" in proposal.proposed.stem


def test_propose_rename_image_with_mdls_fallback(tmp_path: Path) -> None:
    img = tmp_path / "IMG_1234.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

    # Mock mdls to return EXIF date
    mock_attrs = {
        "kMDItemContentType": "public.jpeg",
        "kMDItemContentCreationDate": "2026-01-08 09:54:00 +0000",
    }
    with patch("osx_system_agent.renamer._run_mdls", return_value=mock_attrs):
        proposal = propose_rename(img)

    assert proposal.source == "exif_date"
    assert "2026-01-08" in proposal.proposed.name
    assert proposal.proposed.suffix == ".jpg"


def test_propose_rename_with_mdls_title(tmp_path: Path) -> None:
    doc = tmp_path / "Untitled.docx"
    doc.write_bytes(b"fake docx")

    mock_attrs = {"kMDItemTitle": "Quarterly Budget Review 2026"}
    with patch("osx_system_agent.renamer._run_mdls", return_value=mock_attrs):
        proposal = propose_rename(doc)

    assert proposal.source == "mdls_title"
    assert "Quarterly" in proposal.proposed.name


def test_propose_rename_fallback_date_prefix(tmp_path: Path) -> None:
    f = tmp_path / "Untitled.txt"
    f.write_text("some content")

    with patch("osx_system_agent.renamer._run_mdls", return_value={}):
        proposal = propose_rename(f)

    assert proposal.source == "date_prefix"
    # Should have YYYY-MM-DD prefix
    assert proposal.proposed.stem[:4].isdigit()


# ---- scan_for_renames -------------------------------------------------------


def test_scan_for_renames_empty(tmp_path: Path) -> None:
    proposals = scan_for_renames(tmp_path)
    assert proposals == []


def test_scan_for_renames_skips_good_names(tmp_path: Path) -> None:
    (tmp_path / "Budget_2026.xlsx").write_bytes(b"x")
    (tmp_path / "Meeting_Notes.docx").write_bytes(b"x")
    proposals = scan_for_renames(tmp_path)
    assert len(proposals) == 0


def test_scan_for_renames_finds_bad_names(tmp_path: Path) -> None:
    (tmp_path / "Untitled.png").write_bytes(b"x")
    (tmp_path / "Good_Name.docx").write_bytes(b"x")

    with patch("osx_system_agent.renamer._run_mdls", return_value={}):
        proposals = scan_for_renames(tmp_path)

    assert len(proposals) == 1
    assert proposals[0].original.name == "Untitled.png"


def test_scan_for_renames_nonexistent_dir(tmp_path: Path) -> None:
    proposals = scan_for_renames(tmp_path / "nope")
    assert proposals == []


# ---- execute_renames --------------------------------------------------------


def test_execute_renames_dry_run(tmp_path: Path) -> None:
    original = tmp_path / "Untitled.txt"
    original.write_text("content")
    proposed = tmp_path / "Better_Name.txt"

    proposals = [
        RenameProposal(
            original=original,
            proposed=proposed,
            reason="test",
            source="test",
        )
    ]

    results = execute_renames(proposals, dry_run=True)
    assert len(results) == 1
    assert results[0]["status"] == "dry_run"
    assert original.exists()  # not actually renamed


def test_execute_renames_live(tmp_path: Path) -> None:
    original = tmp_path / "Untitled.txt"
    original.write_text("content")
    proposed = tmp_path / "Better_Name.txt"

    proposals = [
        RenameProposal(
            original=original,
            proposed=proposed,
            reason="test",
            source="test",
        )
    ]

    results = execute_renames(proposals, dry_run=False)
    assert len(results) == 1
    assert results[0]["status"] == "renamed"
    assert not original.exists()
    assert proposed.exists()
    assert proposed.read_text() == "content"
