from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from osx_system_agent.undo import (
    UndoEntry,
    clear_undo_log,
    load_undo_log,
    undo_trash,
)


class TestLoadUndoLog:
    def test_returns_empty_if_no_file(self, tmp_path: Path) -> None:
        with patch("osx_system_agent.undo.UNDO_DIR", tmp_path):
            assert load_undo_log() == []

    def test_loads_entries(self, tmp_path: Path) -> None:
        log_file = tmp_path / "actions.jsonl"
        entries = [
            {"timestamp": "2024-01-01T00:00:00", "action": "trash",
             "source": "/tmp/a.txt", "dest": None},
            {"timestamp": "2024-01-02T00:00:00", "action": "delete",
             "source": "/tmp/b.txt", "dest": None},
        ]
        log_file.write_text(
            "\n".join(json.dumps(e) for e in entries)
        )
        with patch("osx_system_agent.undo.UNDO_DIR", tmp_path):
            result = load_undo_log()
        assert len(result) == 2
        assert result[0].action == "trash"
        assert result[1].action == "delete"

    def test_respects_limit(self, tmp_path: Path) -> None:
        log_file = tmp_path / "actions.jsonl"
        entries = [
            {"timestamp": f"2024-01-{i:02d}", "action": "trash",
             "source": f"/tmp/{i}.txt", "dest": None}
            for i in range(1, 21)
        ]
        log_file.write_text(
            "\n".join(json.dumps(e) for e in entries)
        )
        with patch("osx_system_agent.undo.UNDO_DIR", tmp_path):
            result = load_undo_log(limit=5)
        assert len(result) == 5


class TestUndoTrash:
    def test_restores_manual_trash(self, tmp_path: Path) -> None:
        source = tmp_path / "original" / "file.txt"
        dest = tmp_path / "trash" / "file.txt"
        dest.parent.mkdir(parents=True)
        dest.write_text("content")

        entry = UndoEntry(
            timestamp="2024-01-01",
            action="trash_manual",
            source=str(source),
            dest=str(dest),
        )
        assert undo_trash(entry) is True
        assert source.exists()
        assert source.read_text() == "content"
        assert not dest.exists()

    def test_returns_false_for_missing_trash_file(
        self, tmp_path: Path
    ) -> None:
        entry = UndoEntry(
            timestamp="2024-01-01",
            action="trash_manual",
            source=str(tmp_path / "gone.txt"),
            dest=str(tmp_path / "nonexistent.txt"),
        )
        assert undo_trash(entry) is False

    def test_rejects_non_trash_action(self) -> None:
        entry = UndoEntry(
            timestamp="2024-01-01",
            action="delete",
            source="/tmp/file.txt",
            dest=None,
        )
        assert undo_trash(entry) is False


class TestClearUndoLog:
    def test_clears_existing_log(self, tmp_path: Path) -> None:
        log_file = tmp_path / "actions.jsonl"
        log_file.write_text("something")
        with patch("osx_system_agent.undo.UNDO_DIR", tmp_path):
            clear_undo_log()
        assert not log_file.exists()

    def test_handles_missing_log(self, tmp_path: Path) -> None:
        with patch("osx_system_agent.undo.UNDO_DIR", tmp_path):
            clear_undo_log()  # should not raise
