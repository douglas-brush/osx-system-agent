from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_tree(tmp_path: Path) -> Path:
    """Create a temp directory tree with known files for scanner tests."""
    # Regular files
    (tmp_path / "file_a.txt").write_text("hello world\n")
    (tmp_path / "file_b.txt").write_text("hello world\n")  # duplicate of file_a
    (tmp_path / "file_c.log").write_bytes(b"\x00" * 2048)
    (tmp_path / "unique.py").write_text("print('unique')\n")

    # Subdirectory
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "deep.txt").write_text("deep file content\n")
    (sub / "deep_dup.txt").write_text("deep file content\n")  # duplicate

    # Excluded directory
    git = tmp_path / ".git"
    git.mkdir()
    (git / "config").write_text("should be excluded\n")

    # Nested excluded
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("excluded too\n")

    return tmp_path


@pytest.fixture()
def large_tree(tmp_path: Path) -> Path:
    """Create a tree with files of varying sizes for aging/inventory tests."""
    sizes = {
        "small.txt": 100,
        "medium.bin": 5000,
        "large.dat": 50_000,
        "huge.iso": 500_000,
    }
    for name, size in sizes.items():
        (tmp_path / name).write_bytes(os.urandom(size))

    sub = tmp_path / "docs"
    sub.mkdir()
    (sub / "readme.md").write_text("# Docs\n" * 100)
    (sub / "notes.md").write_text("# Notes\n" * 50)

    return tmp_path
