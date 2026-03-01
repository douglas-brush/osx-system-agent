from __future__ import annotations

import os
from pathlib import Path

from osx_system_agent.scanners.disk_hogs import DirUsage, scan_disk_hogs


class TestScanDiskHogs:
    def test_returns_results(self, tmp_path: Path) -> None:
        sub = tmp_path / "bigdir"
        sub.mkdir()
        (sub / "data.bin").write_bytes(os.urandom(10_000))

        results = scan_disk_hogs(targets=[str(sub)], min_size=0)
        assert len(results) == 1
        assert isinstance(results[0], DirUsage)
        assert results[0].size >= 10_000
        assert results[0].file_count == 1

    def test_min_size_filter(self, tmp_path: Path) -> None:
        sub = tmp_path / "small"
        sub.mkdir()
        (sub / "tiny.txt").write_text("x")

        results = scan_disk_hogs(targets=[str(sub)], min_size=1_000_000)
        assert len(results) == 0

    def test_nonexistent_skipped(self) -> None:
        results = scan_disk_hogs(targets=["/nonexistent/path"], min_size=0)
        assert len(results) == 0

    def test_sorted_by_size_desc(self, tmp_path: Path) -> None:
        small = tmp_path / "small"
        small.mkdir()
        (small / "a.txt").write_bytes(b"x" * 100)

        big = tmp_path / "big"
        big.mkdir()
        (big / "b.bin").write_bytes(os.urandom(50_000))

        results = scan_disk_hogs(targets=[str(small), str(big)], min_size=0)
        assert results[0].size >= results[-1].size
