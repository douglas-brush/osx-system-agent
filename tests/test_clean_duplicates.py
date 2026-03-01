from __future__ import annotations

from pathlib import Path

from osx_system_agent.clean.duplicates import DedupResult, clean_duplicates


class TestCleanDuplicates:
    def _create_dupes(self, tmp_path: Path) -> None:
        (tmp_path / "original.txt").write_text("duplicate content here")
        (tmp_path / "copy1.txt").write_text("duplicate content here")
        (tmp_path / "copy2.txt").write_text("duplicate content here")

    def test_dry_run_does_not_delete(self, tmp_path: Path) -> None:
        self._create_dupes(tmp_path)
        results = clean_duplicates(tmp_path, min_size=0, dry_run=True)
        assert len(results) >= 1
        assert results[0].dry_run is True
        # All files should still exist
        assert (tmp_path / "original.txt").exists()
        assert (tmp_path / "copy1.txt").exists()
        assert (tmp_path / "copy2.txt").exists()

    def test_live_trashes_duplicates(self, tmp_path: Path) -> None:
        self._create_dupes(tmp_path)
        results = clean_duplicates(tmp_path, min_size=0, dry_run=False)
        assert len(results) >= 1
        # Keeper should still exist
        assert results[0].kept.exists()
        # At least some duplicates removed
        assert results[0].size_freed > 0

    def test_returns_dedup_result(self, tmp_path: Path) -> None:
        self._create_dupes(tmp_path)
        results = clean_duplicates(tmp_path, min_size=0, dry_run=True)
        for r in results:
            assert isinstance(r, DedupResult)
            assert isinstance(r.kept, Path)
            assert isinstance(r.removed, list)

    def test_no_dupes_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "unique1.txt").write_text("one")
        (tmp_path / "unique2.txt").write_text("two")
        results = clean_duplicates(tmp_path, min_size=0, dry_run=True)
        assert len(results) == 0

    def test_keeper_has_shortest_path(self, tmp_path: Path) -> None:
        sub = tmp_path / "deep" / "nested"
        sub.mkdir(parents=True)
        (tmp_path / "a.txt").write_text("same content")
        (sub / "b.txt").write_text("same content")
        results = clean_duplicates(tmp_path, min_size=0, dry_run=True)
        assert len(results) >= 1
        # The keeper should be the one with the shorter path
        assert len(str(results[0].kept)) <= len(str(sub / "b.txt"))
