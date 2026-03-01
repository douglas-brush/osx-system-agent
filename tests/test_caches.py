from __future__ import annotations

import os
from pathlib import Path

from osx_system_agent.scanners.caches import CacheEntry, scan_caches


class TestScanCaches:
    def test_returns_results(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "caches"
        cache_dir.mkdir()
        (cache_dir / "data.bin").write_bytes(os.urandom(5_000))

        results = scan_caches(targets=[(str(cache_dir), "Test Cache")], min_size=0)
        assert len(results) == 1
        assert isinstance(results[0], CacheEntry)
        assert results[0].category == "Test Cache"
        assert results[0].size >= 5_000

    def test_min_size_filter(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "small_cache"
        cache_dir.mkdir()
        (cache_dir / "tiny.txt").write_text("x")

        results = scan_caches(targets=[(str(cache_dir), "Tiny")], min_size=1_000_000)
        assert len(results) == 0

    def test_nonexistent_skipped(self) -> None:
        results = scan_caches(targets=[("/nonexistent", "Missing")], min_size=0)
        assert len(results) == 0

    def test_multiple_entries_sorted(self, tmp_path: Path) -> None:
        small = tmp_path / "small"
        small.mkdir()
        (small / "a.txt").write_bytes(b"x" * 100)

        big = tmp_path / "big"
        big.mkdir()
        (big / "b.bin").write_bytes(os.urandom(50_000))

        results = scan_caches(
            targets=[(str(small), "Small"), (str(big), "Big")],
            min_size=0,
        )
        assert results[0].category == "Big"
