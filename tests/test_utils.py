from __future__ import annotations

from pathlib import Path

import pytest

from osx_system_agent.utils.human import bytes_to_human, unix_to_iso
from osx_system_agent.utils.parse import parse_size
from osx_system_agent.utils.paths import ensure_dir, expand_path


class TestBytesToHuman:
    def test_bytes(self) -> None:
        assert bytes_to_human(0) == "0.0B"
        assert bytes_to_human(512) == "512.0B"

    def test_kilobytes(self) -> None:
        assert bytes_to_human(1024) == "1.0KB"
        assert bytes_to_human(1536) == "1.5KB"

    def test_megabytes(self) -> None:
        assert bytes_to_human(1024**2) == "1.0MB"

    def test_gigabytes(self) -> None:
        assert bytes_to_human(1024**3) == "1.0GB"

    def test_terabytes(self) -> None:
        assert bytes_to_human(1024**4) == "1.0TB"


class TestUnixToIso:
    def test_none_returns_empty(self) -> None:
        assert unix_to_iso(None) == ""

    def test_epoch_zero(self) -> None:
        result = unix_to_iso(0)
        assert result == "1970-01-01T00:00:00+00:00"

    def test_known_timestamp(self) -> None:
        # 2024-01-15T12:00:00 UTC
        result = unix_to_iso(1705320000)
        assert "2024-01-15" in result
        assert "+00:00" in result

    def test_float_timestamp(self) -> None:
        result = unix_to_iso(1705320000.5)
        assert "2024-01-15" in result


class TestParseSize:
    def test_plain_int(self) -> None:
        assert parse_size(42) == 42

    def test_bytes_string(self) -> None:
        assert parse_size("100") == 100
        assert parse_size("100B") == 100

    def test_kilobytes(self) -> None:
        assert parse_size("1K") == 1024
        assert parse_size("1KB") == 1024

    def test_megabytes(self) -> None:
        assert parse_size("10MB") == 10 * 1024**2
        assert parse_size("10M") == 10 * 1024**2

    def test_gigabytes(self) -> None:
        assert parse_size("2GB") == 2 * 1024**3

    def test_terabytes(self) -> None:
        assert parse_size("1TB") == 1024**4

    def test_case_insensitive(self) -> None:
        assert parse_size("10mb") == parse_size("10MB")

    def test_with_spaces(self) -> None:
        assert parse_size(" 10 MB ") == 10 * 1024**2

    def test_decimal(self) -> None:
        assert parse_size("1.5GB") == int(1.5 * 1024**3)

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid size"):
            parse_size("notasize")

    def test_zero(self) -> None:
        assert parse_size("0") == 0


class TestExpandPath:
    def test_resolves_tilde(self) -> None:
        result = expand_path("~/test")
        assert "~" not in str(result)
        assert result.is_absolute()

    def test_resolves_relative(self) -> None:
        result = expand_path(".")
        assert result.is_absolute()

    def test_path_input(self) -> None:
        result = expand_path(Path("/tmp/test"))
        # macOS resolves /tmp -> /private/tmp
        assert result == Path("/tmp/test").resolve()


class TestEnsureDir:
    def test_creates_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c"
        result = ensure_dir(target)
        assert result.exists()
        assert result.is_dir()

    def test_existing_directory(self, tmp_path: Path) -> None:
        result = ensure_dir(tmp_path)
        assert result == tmp_path
