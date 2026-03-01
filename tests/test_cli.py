from __future__ import annotations

from typer.testing import CliRunner

from osx_system_agent.cli import app

runner = CliRunner()


class TestStatusCommand:
    def test_runs(self) -> None:
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "CPU" in result.output
        assert "Memory" in result.output
        assert "Disk" in result.output

    def test_verbose(self) -> None:
        result = runner.invoke(app, ["-v", "status"])
        assert result.exit_code == 0


class TestProcessesCommand:
    def test_runs(self) -> None:
        result = runner.invoke(app, ["processes", "--limit", "5"])
        assert result.exit_code == 0
        assert "PID" in result.output

    def test_sort_mem(self) -> None:
        result = runner.invoke(app, ["processes", "--sort", "mem", "--limit", "3"])
        assert result.exit_code == 0


class TestScanDuplicatesCommand:
    def test_runs(self, tmp_path: str) -> None:
        result = runner.invoke(
            app, ["scan", "duplicates", "--path", str(tmp_path), "--min-size", "0"]
        )
        # May find 0 duplicates in a temp dir, but should not crash
        assert result.exit_code == 0


class TestScanAgingCommand:
    def test_runs(self, tmp_path: str) -> None:
        result = runner.invoke(
            app,
            ["scan", "aging", "--path", str(tmp_path), "--min-size", "0", "--limit", "10"],
        )
        assert result.exit_code == 0


class TestScanInventoryCommand:
    def test_runs(self, tmp_path: str) -> None:
        result = runner.invoke(
            app, ["scan", "inventory", "--path", str(tmp_path), "--min-size", "0"]
        )
        assert result.exit_code == 0


class TestVersionFlag:
    def test_version(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "osx-system-agent" in result.output
