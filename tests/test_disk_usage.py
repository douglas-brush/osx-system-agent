from __future__ import annotations

import os
from pathlib import Path

from osx_system_agent.scanners.disk_usage import DirEntry, scan_disk_usage


class TestScanDiskUsage:
    def test_returns_entries(self, tmp_path: Path) -> None:
        sub = tmp_path / "big_dir"
        sub.mkdir()
        (sub / "data.bin").write_bytes(os.urandom(10_000))

        results = scan_disk_usage(tmp_path, min_size=0)
        assert len(results) >= 1
        assert any(isinstance(r, DirEntry) for r in results)

    def test_sorted_by_size_desc(self, tmp_path: Path) -> None:
        small = tmp_path / "small"
        small.mkdir()
        (small / "a.txt").write_bytes(b"x" * 100)

        big = tmp_path / "big"
        big.mkdir()
        (big / "b.bin").write_bytes(os.urandom(50_000))

        results = scan_disk_usage(tmp_path, min_size=0)
        sizes = [r.size for r in results if r.path.name != "(loose files)"]
        assert sizes == sorted(sizes, reverse=True)

    def test_min_size_filter(self, tmp_path: Path) -> None:
        sub = tmp_path / "tiny"
        sub.mkdir()
        (sub / "small.txt").write_text("x")

        results = scan_disk_usage(tmp_path, min_size=1_000_000)
        dir_results = [r for r in results if r.path.name != "(loose files)"]
        assert len(dir_results) == 0

    def test_hidden_dirs(self, tmp_path: Path) -> None:
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.txt").write_bytes(b"x" * 500)

        with_hidden = scan_disk_usage(tmp_path, min_size=0, include_hidden=True)
        without_hidden = scan_disk_usage(tmp_path, min_size=0, include_hidden=False)

        hidden_names_with = {r.path.name for r in with_hidden}
        hidden_names_without = {r.path.name for r in without_hidden}
        assert ".hidden" in hidden_names_with
        assert ".hidden" not in hidden_names_without

    def test_nonexistent_returns_empty(self) -> None:
        results = scan_disk_usage(Path("/nonexistent/path"), min_size=0)
        assert results == []

    def test_loose_files(self, tmp_path: Path) -> None:
        (tmp_path / "loose.txt").write_bytes(b"x" * 500)
        results = scan_disk_usage(tmp_path, min_size=0)
        loose = [r for r in results if r.path.name == "(loose files)"]
        assert len(loose) == 1
        assert loose[0].size >= 500
