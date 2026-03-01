from __future__ import annotations

from pathlib import Path

from osx_system_agent.scanners.large_files import LargeFile, scan_large_files


class TestScanLargeFiles:
    def test_finds_large_files(self, tmp_path: Path) -> None:
        big = tmp_path / "big.bin"
        big.write_bytes(b"x" * 2000)
        small = tmp_path / "small.txt"
        small.write_bytes(b"y" * 10)

        results = scan_large_files(
            roots=[tmp_path], limit=10, min_size=1000,
        )
        assert len(results) == 1
        assert results[0].path == big
        assert results[0].size == 2000

    def test_respects_min_size(self, tmp_path: Path) -> None:
        f = tmp_path / "medium.bin"
        f.write_bytes(b"x" * 500)

        results = scan_large_files(
            roots=[tmp_path], limit=10, min_size=1000,
        )
        assert len(results) == 0

    def test_respects_limit(self, tmp_path: Path) -> None:
        for i in range(10):
            (tmp_path / f"file{i}.bin").write_bytes(b"x" * (1000 + i))

        results = scan_large_files(
            roots=[tmp_path], limit=3, min_size=100,
        )
        assert len(results) == 3
        # Should be sorted by size desc
        assert results[0].size >= results[1].size >= results[2].size

    def test_empty_dir(self, tmp_path: Path) -> None:
        results = scan_large_files(
            roots=[tmp_path], limit=10, min_size=0,
        )
        assert results == []

    def test_nonexistent_root(self, tmp_path: Path) -> None:
        results = scan_large_files(
            roots=[tmp_path / "nonexistent"], limit=10, min_size=0,
        )
        assert results == []

    def test_returns_dataclass(self, tmp_path: Path) -> None:
        f = tmp_path / "file.bin"
        f.write_bytes(b"x" * 500)
        results = scan_large_files(
            roots=[tmp_path], limit=10, min_size=100,
        )
        assert len(results) == 1
        assert isinstance(results[0], LargeFile)
        assert results[0].mtime > 0

    def test_sorted_by_size_desc(self, tmp_path: Path) -> None:
        (tmp_path / "small.bin").write_bytes(b"x" * 500)
        (tmp_path / "big.bin").write_bytes(b"x" * 2000)
        (tmp_path / "medium.bin").write_bytes(b"x" * 1000)

        results = scan_large_files(
            roots=[tmp_path], limit=10, min_size=100,
        )
        sizes = [r.size for r in results]
        assert sizes == sorted(sizes, reverse=True)
