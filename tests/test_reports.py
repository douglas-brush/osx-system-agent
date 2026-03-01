from __future__ import annotations

import csv
import json
from pathlib import Path

from osx_system_agent.reports.writer import write_csv, write_json


class TestWriteJson:
    def test_writes_valid_json(self, tmp_path: Path) -> None:
        data = [{"key": "value", "num": 42}]
        out = write_json(data, tmp_path / "test.json")
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert loaded == data

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        out = write_json({"a": 1}, tmp_path / "sub" / "deep" / "test.json")
        assert out.exists()

    def test_handles_nested_data(self, tmp_path: Path) -> None:
        data = {"nested": {"deep": [1, 2, 3]}}
        out = write_json(data, tmp_path / "nested.json")
        loaded = json.loads(out.read_text())
        assert loaded["nested"]["deep"] == [1, 2, 3]


class TestWriteCsv:
    def test_writes_csv_with_header(self, tmp_path: Path) -> None:
        rows = [{"name": "alice", "age": 30}, {"name": "bob", "age": 25}]
        out = write_csv(rows, tmp_path / "test.csv")
        assert out.exists()
        with out.open() as f:
            reader = csv.DictReader(f)
            data = list(reader)
        assert len(data) == 2
        assert data[0]["name"] == "alice"

    def test_empty_rows(self, tmp_path: Path) -> None:
        out = write_csv([], tmp_path / "empty.csv")
        assert out.exists()
        assert out.read_text() == ""

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        rows = [{"x": 1}]
        out = write_csv(rows, tmp_path / "sub" / "test.csv")
        assert out.exists()
