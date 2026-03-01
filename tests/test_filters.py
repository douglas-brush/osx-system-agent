from __future__ import annotations

from pathlib import Path

from osx_system_agent.scanners.filters import (
    DEFAULT_EXCLUDES,
    iter_files,
    merge_excludes,
    should_exclude,
)


class TestShouldExclude:
    def test_git_directory(self, tmp_path: Path) -> None:
        path = tmp_path / ".git" / "config"
        assert should_exclude(path, tmp_path, [".git"])

    def test_nested_match(self, tmp_path: Path) -> None:
        path = tmp_path / "Library" / "Caches" / "something"
        assert should_exclude(path, tmp_path, ["Library/Caches"])

    def test_no_match(self, tmp_path: Path) -> None:
        path = tmp_path / "src" / "main.py"
        assert not should_exclude(path, tmp_path, [".git", "node_modules"])

    def test_fnmatch_glob(self, tmp_path: Path) -> None:
        path = tmp_path / "build" / "output.o"
        assert should_exclude(path, tmp_path, ["build/*"])

    def test_component_match(self, tmp_path: Path) -> None:
        path = tmp_path / "project" / "node_modules" / "pkg" / "index.js"
        assert should_exclude(path, tmp_path, ["node_modules"])


class TestMergeExcludes:
    def test_none_returns_defaults(self) -> None:
        result = merge_excludes(None)
        assert result == DEFAULT_EXCLUDES

    def test_merges_user_patterns(self) -> None:
        result = merge_excludes(["*.tmp", "build"])
        assert "*.tmp" in result
        assert "build" in result
        assert ".git" in result  # default preserved

    def test_no_duplicates(self) -> None:
        result = merge_excludes([".git", "custom"])
        assert result.count(".git") == 1

    def test_empty_list(self) -> None:
        result = merge_excludes([])
        assert result == DEFAULT_EXCLUDES


class TestIterFiles:
    def test_excludes_git(self, tmp_tree: Path) -> None:
        files = list(iter_files(tmp_tree, DEFAULT_EXCLUDES))
        paths_str = [str(f) for f in files]
        assert not any(".git" in p for p in paths_str)

    def test_excludes_venv(self, tmp_tree: Path) -> None:
        files = list(iter_files(tmp_tree, DEFAULT_EXCLUDES))
        paths_str = [str(f) for f in files]
        assert not any(".venv" in p for p in paths_str)

    def test_finds_regular_files(self, tmp_tree: Path) -> None:
        files = list(iter_files(tmp_tree, DEFAULT_EXCLUDES))
        names = {f.name for f in files}
        assert "file_a.txt" in names
        assert "file_b.txt" in names
        assert "unique.py" in names

    def test_finds_nested_files(self, tmp_tree: Path) -> None:
        files = list(iter_files(tmp_tree, DEFAULT_EXCLUDES))
        names = {f.name for f in files}
        assert "deep.txt" in names

    def test_skips_symlinks_by_default(self, tmp_tree: Path) -> None:
        link = tmp_tree / "link.txt"
        link.symlink_to(tmp_tree / "file_a.txt")
        files = list(iter_files(tmp_tree, DEFAULT_EXCLUDES, follow_symlinks=False))
        names = {f.name for f in files}
        assert "link.txt" not in names

    def test_custom_excludes(self, tmp_tree: Path) -> None:
        files = list(iter_files(tmp_tree, ["subdir"]))
        names = {f.name for f in files}
        assert "deep.txt" not in names
