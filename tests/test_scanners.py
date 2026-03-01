from __future__ import annotations

from pathlib import Path

from osx_system_agent.scanners.aging import scan_aging
from osx_system_agent.scanners.duplicates import DuplicateGroup, hash_file, scan_duplicates
from osx_system_agent.scanners.inventory import scan_inventory


class TestHashFile:
    def test_deterministic(self, tmp_path: Path) -> None:
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        h1 = hash_file(f)
        h2 = hash_file(f)
        assert h1 == h2

    def test_different_content(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"hello")
        f2.write_bytes(b"world")
        assert hash_file(f1) != hash_file(f2)

    def test_same_content(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"same content")
        f2.write_bytes(b"same content")
        assert hash_file(f1) == hash_file(f2)

    def test_sha256_length(self, tmp_path: Path) -> None:
        f = tmp_path / "test.bin"
        f.write_bytes(b"test")
        assert len(hash_file(f)) == 64  # SHA-256 hex digest


class TestScanDuplicates:
    def test_finds_duplicates(self, tmp_tree: Path) -> None:
        groups = scan_duplicates(tmp_tree, min_size=0)
        assert len(groups) >= 1
        # file_a.txt and file_b.txt have identical content
        all_files = []
        for g in groups:
            all_files.extend(g.files)
        names = {f.name for f in all_files}
        assert "file_a.txt" in names
        assert "file_b.txt" in names

    def test_min_size_filter(self, tmp_tree: Path) -> None:
        # file_a.txt is 12 bytes — setting min_size above that should exclude it
        groups = scan_duplicates(tmp_tree, min_size=1000)
        all_names = {f.name for g in groups for f in g.files}
        assert "file_a.txt" not in all_names

    def test_sorted_by_size_desc(self, tmp_tree: Path) -> None:
        groups = scan_duplicates(tmp_tree, min_size=0)
        if len(groups) >= 2:
            assert groups[0].size >= groups[1].size

    def test_no_duplicates_when_unique(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("unique_a")
        (tmp_path / "b.txt").write_text("unique_b")
        groups = scan_duplicates(tmp_path, min_size=0)
        assert len(groups) == 0

    def test_returns_duplicate_group_dataclass(self, tmp_tree: Path) -> None:
        groups = scan_duplicates(tmp_tree, min_size=0)
        for g in groups:
            assert isinstance(g, DuplicateGroup)
            assert isinstance(g.size, int)
            assert isinstance(g.digest, str)
            assert len(g.files) >= 2


class TestScanAging:
    def test_returns_rows(self, large_tree: Path) -> None:
        rows = scan_aging(large_tree, min_size=0)
        assert len(rows) > 0

    def test_min_size_filter(self, large_tree: Path) -> None:
        rows = scan_aging(large_tree, min_size=100_000)
        for row in rows:
            assert row["size"] >= 100_000

    def test_limit(self, large_tree: Path) -> None:
        rows = scan_aging(large_tree, min_size=0, limit=2)
        assert len(rows) <= 2

    def test_sort_by_size_descending(self, large_tree: Path) -> None:
        rows = scan_aging(large_tree, min_size=0, sort="size")
        sizes = [row["size"] for row in rows]
        assert sizes == sorted(sizes, reverse=True)

    def test_sort_by_mtime_ascending(self, large_tree: Path) -> None:
        rows = scan_aging(large_tree, min_size=0, sort="mtime")
        mtimes = [row["mtime"] for row in rows]
        assert mtimes == sorted(mtimes)

    def test_row_fields(self, large_tree: Path) -> None:
        rows = scan_aging(large_tree, min_size=0)
        for row in rows:
            assert "path" in row
            assert "size" in row
            assert "mtime" in row
            assert "atime" in row
            assert "ctime" in row


class TestScanInventory:
    def test_returns_rows(self, large_tree: Path) -> None:
        rows = scan_inventory(large_tree, min_size=0)
        assert len(rows) > 0

    def test_groups_by_extension(self, large_tree: Path) -> None:
        rows = scan_inventory(large_tree, min_size=0)
        extensions = {row["extension"] for row in rows}
        assert ".md" in extensions
        assert ".txt" in extensions

    def test_sorted_by_total_size_desc(self, large_tree: Path) -> None:
        rows = scan_inventory(large_tree, min_size=0)
        total_sizes = [row["total_size"] for row in rows]
        assert total_sizes == sorted(total_sizes, reverse=True)

    def test_count_accuracy(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "c.txt").write_text("c")
        rows = scan_inventory(tmp_path, min_size=0)
        txt_row = next(r for r in rows if r["extension"] == ".txt")
        assert txt_row["count"] == 3

    def test_row_fields(self, large_tree: Path) -> None:
        rows = scan_inventory(large_tree, min_size=0)
        for row in rows:
            assert "extension" in row
            assert "count" in row
            assert "total_size" in row
            assert "largest" in row
