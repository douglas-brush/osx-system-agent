from __future__ import annotations

from pathlib import Path

from osx_system_agent.scanners.junk import JunkFile, scan_junk


class TestScanJunk:
    def test_finds_ds_store(self, tmp_path: Path) -> None:
        (tmp_path / ".DS_Store").write_bytes(b"\x00" * 4096)
        results = scan_junk(tmp_path)
        assert len(results) >= 1
        assert any(j.category == "ds_store" for j in results)

    def test_finds_apple_double(self, tmp_path: Path) -> None:
        (tmp_path / "._somefile").write_bytes(b"\x00" * 100)
        results = scan_junk(tmp_path)
        assert any(j.category == "apple_double" for j in results)

    def test_finds_thumbs_db(self, tmp_path: Path) -> None:
        (tmp_path / "Thumbs.db").write_bytes(b"\x00" * 100)
        results = scan_junk(tmp_path)
        assert any(j.category == "windows_junk" for j in results)

    def test_finds_nested_junk(self, tmp_path: Path) -> None:
        sub = tmp_path / "project" / "subdir"
        sub.mkdir(parents=True)
        (sub / ".DS_Store").write_bytes(b"\x00" * 100)
        results = scan_junk(tmp_path)
        assert len(results) >= 1

    def test_no_junk_in_clean_dir(self, tmp_path: Path) -> None:
        (tmp_path / "clean.txt").write_text("clean")
        results = scan_junk(tmp_path)
        assert len(results) == 0

    def test_returns_junk_file_dataclass(self, tmp_path: Path) -> None:
        (tmp_path / ".DS_Store").write_bytes(b"\x00" * 100)
        results = scan_junk(tmp_path)
        for j in results:
            assert isinstance(j, JunkFile)
            assert isinstance(j.size, int)
            assert isinstance(j.category, str)
            assert isinstance(j.path, Path)

    def test_spotlight_dir(self, tmp_path: Path) -> None:
        spotlight = tmp_path / ".Spotlight-V100"
        spotlight.mkdir()
        (spotlight / "index").write_bytes(b"\x00" * 500)
        results = scan_junk(tmp_path)
        assert any(j.category == "spotlight" for j in results)
