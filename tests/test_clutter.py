"""Tests for the clutter scanner."""

from __future__ import annotations

from pathlib import Path

from osx_system_agent.scanners.clutter import scan_clutter


def test_scan_clutter_empty(tmp_path: Path) -> None:
    report = scan_clutter(tmp_path)
    assert report.total_files == 0
    assert report.items == []


def test_scan_clutter_word_temp(tmp_path: Path) -> None:
    (tmp_path / "~$MyDocument.docx").write_bytes(b"x" * 100)
    report = scan_clutter(tmp_path)
    assert len(report.items) == 1
    assert report.items[0].category == "word_temp"


def test_scan_clutter_webloc(tmp_path: Path) -> None:
    (tmp_path / "Bookmark.webloc").write_bytes(b"x" * 50)
    report = scan_clutter(tmp_path)
    assert len(report.items) == 1
    assert report.items[0].category == "webloc"


def test_scan_clutter_dmg(tmp_path: Path) -> None:
    (tmp_path / "Installer.dmg").write_bytes(b"x" * 1000)
    report = scan_clutter(tmp_path)
    assert len(report.items) == 1
    assert report.items[0].category == "dmg_installer"
    assert report.items[0].size == 1000


def test_scan_clutter_generic_names(tmp_path: Path) -> None:
    (tmp_path / "Untitled.png").write_bytes(b"x")
    (tmp_path / "image.png").write_bytes(b"x")
    (tmp_path / "IMG_1234.jpg").write_bytes(b"x")
    (tmp_path / "Pasted_Image_123.png").write_bytes(b"x")
    report = scan_clutter(tmp_path)
    generics = [i for i in report.items if i.category == "generic_name"]
    assert len(generics) == 4


def test_scan_clutter_numbered_copy(tmp_path: Path) -> None:
    (tmp_path / "report.docx").write_bytes(b"original")
    (tmp_path / "report_1.docx").write_bytes(b"copy")
    (tmp_path / "report_2.docx").write_bytes(b"copy2")
    report = scan_clutter(tmp_path)
    copies = [i for i in report.items if i.category == "numbered_copy"]
    assert len(copies) == 2


def test_scan_clutter_dead_file(tmp_path: Path) -> None:
    (tmp_path / "old.htaccess.olf").write_bytes(b"x")
    (tmp_path / ".localized").write_bytes(b"")
    report = scan_clutter(tmp_path)
    dead = [i for i in report.items if i.category == "dead_file"]
    # .localized starts with dot so it gets skipped; .olf ext is dead
    assert len(dead) >= 1


def test_scan_clutter_opaque_name(tmp_path: Path) -> None:
    (tmp_path / "7dcadb20b2c6b8c4f14ac099fb3132f7a21427.jpg").write_bytes(b"x")
    report = scan_clutter(tmp_path)
    opaque = [i for i in report.items if i.category == "opaque_name"]
    assert len(opaque) == 1


def test_scan_clutter_ignores_ds_store(tmp_path: Path) -> None:
    (tmp_path / ".DS_Store").write_bytes(b"x")
    report = scan_clutter(tmp_path)
    assert len(report.items) == 0


def test_scan_clutter_nonexistent_dir(tmp_path: Path) -> None:
    report = scan_clutter(tmp_path / "nope")
    assert report.total_files == 0
    assert report.items == []


def test_scan_clutter_normal_files_not_flagged(tmp_path: Path) -> None:
    (tmp_path / "2026_Tax_Return.pdf").write_bytes(b"x" * 1000)
    (tmp_path / "Meeting_Notes_Jan.docx").write_bytes(b"x" * 500)
    report = scan_clutter(tmp_path)
    # These have descriptive names and are recent — should not be flagged
    # (unless stale_days is set very low)
    non_stale = [i for i in report.items if i.category != "stale"]
    assert len(non_stale) == 0


def test_scan_clutter_report_totals(tmp_path: Path) -> None:
    (tmp_path / "~$temp.docx").write_bytes(b"x" * 100)
    (tmp_path / "good_file.txt").write_bytes(b"x" * 200)
    report = scan_clutter(tmp_path)
    assert report.total_files == 2
    assert report.total_size == 300
