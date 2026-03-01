from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from osx_system_agent.reports.history import (
    compare_latest,
    load_history,
    record_snapshot,
)


class TestRecordSnapshot:
    def test_records_snapshot(self, tmp_path: Path) -> None:
        history_file = tmp_path / "snapshots.jsonl"
        with patch("osx_system_agent.reports.history._history_file", return_value=history_file):
            snap = record_snapshot()

        assert "timestamp" in snap
        assert "disk_total" in snap
        assert "disk_used" in snap
        assert "cache_total" in snap
        assert history_file.exists()

        lines = history_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["timestamp"] == snap["timestamp"]

    def test_appends_multiple(self, tmp_path: Path) -> None:
        history_file = tmp_path / "snapshots.jsonl"
        with patch("osx_system_agent.reports.history._history_file", return_value=history_file):
            record_snapshot()
            record_snapshot()

        lines = history_file.read_text().strip().splitlines()
        assert len(lines) == 2


class TestLoadHistory:
    def test_returns_empty_if_no_file(self, tmp_path: Path) -> None:
        with patch(
            "osx_system_agent.reports.history._history_file",
            return_value=tmp_path / "nonexistent.jsonl",
        ):
            assert load_history() == []

    def test_loads_entries(self, tmp_path: Path) -> None:
        history_file = tmp_path / "snapshots.jsonl"
        entries = [
            {"timestamp": "2024-01-01T00:00:00", "disk_used": 100},
            {"timestamp": "2024-01-02T00:00:00", "disk_used": 200},
        ]
        history_file.write_text("\n".join(json.dumps(e) for e in entries))

        with patch("osx_system_agent.reports.history._history_file", return_value=history_file):
            result = load_history(limit=10)

        assert len(result) == 2

    def test_respects_limit(self, tmp_path: Path) -> None:
        history_file = tmp_path / "snapshots.jsonl"
        entries = [{"timestamp": f"2024-01-{i:02d}", "val": i} for i in range(1, 21)]
        history_file.write_text("\n".join(json.dumps(e) for e in entries))

        with patch("osx_system_agent.reports.history._history_file", return_value=history_file):
            result = load_history(limit=5)

        assert len(result) == 5


class TestCompareLatest:
    def test_returns_none_with_no_history(self, tmp_path: Path) -> None:
        with patch(
            "osx_system_agent.reports.history._history_file",
            return_value=tmp_path / "empty.jsonl",
        ):
            assert compare_latest() is None

    def test_returns_delta(self, tmp_path: Path) -> None:
        history_file = tmp_path / "snapshots.jsonl"
        entries = [
            {"timestamp": "2024-01-01", "disk_used": 100_000,
             "disk_free": 900_000, "cache_total": 5000},
            {"timestamp": "2024-01-02", "disk_used": 120_000,
             "disk_free": 880_000, "cache_total": 6000},
        ]
        history_file.write_text("\n".join(json.dumps(e) for e in entries))

        with patch("osx_system_agent.reports.history._history_file", return_value=history_file):
            delta = compare_latest()

        assert delta is not None
        assert delta["disk_used_delta"] == 20_000
        assert delta["disk_used_direction"] == "+"
        assert delta["cache_delta"] == 1000
