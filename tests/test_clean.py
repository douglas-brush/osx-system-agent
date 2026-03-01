from __future__ import annotations

from pathlib import Path

from osx_system_agent.clean.junk import clean_junk
from osx_system_agent.clean.trash import delete_file


class TestDeleteFile:
    def test_deletes_file(self, tmp_path: Path) -> None:
        f = tmp_path / "delete_me.txt"
        f.write_text("bye")
        assert delete_file(f) is True
        assert not f.exists()

    def test_deletes_directory(self, tmp_path: Path) -> None:
        d = tmp_path / "delete_dir"
        d.mkdir()
        (d / "inner.txt").write_text("x")
        assert delete_file(d) is True
        assert not d.exists()

    def test_nonexistent_returns_false(self, tmp_path: Path) -> None:
        assert delete_file(tmp_path / "ghost.txt") is False


class TestCleanJunk:
    def test_dry_run_does_not_delete(self, tmp_path: Path) -> None:
        (tmp_path / ".DS_Store").write_bytes(b"\x00" * 100)
        results = clean_junk(tmp_path, dry_run=True)
        assert len(results) >= 1
        assert all(not r.deleted for r in results)
        assert (tmp_path / ".DS_Store").exists()

    def test_live_deletes_junk(self, tmp_path: Path) -> None:
        (tmp_path / ".DS_Store").write_bytes(b"\x00" * 100)
        (tmp_path / "._extra").write_bytes(b"\x00" * 50)
        results = clean_junk(tmp_path, dry_run=False)
        assert all(r.deleted for r in results)
        assert not (tmp_path / ".DS_Store").exists()
        assert not (tmp_path / "._extra").exists()

    def test_clean_dir_no_results(self, tmp_path: Path) -> None:
        (tmp_path / "clean.txt").write_text("ok")
        results = clean_junk(tmp_path, dry_run=True)
        assert len(results) == 0
