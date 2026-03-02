from __future__ import annotations

from unittest.mock import patch

from osx_system_agent.scanners.security import (
    SecurityAudit,
    SecurityCheck,
    _check_auto_updates,
    _check_filevault,
    _check_firewall,
    _check_gatekeeper,
    _check_remote_login,
    _check_remote_management,
    _check_sip,
    _check_xprotect,
    scan_security,
)


class TestCheckFileVault:
    @patch("osx_system_agent.scanners.security._run_cmd", return_value="FileVault is On.")
    def test_enabled(self, mock_cmd) -> None:
        check = _check_filevault()
        assert check.enabled is True
        assert check.severity == "ok"

    @patch("osx_system_agent.scanners.security._run_cmd", return_value="FileVault is Off.")
    def test_disabled(self, mock_cmd) -> None:
        check = _check_filevault()
        assert check.enabled is False
        assert check.severity == "critical"

    @patch("osx_system_agent.scanners.security._run_cmd", return_value=None)
    def test_unknown(self, mock_cmd) -> None:
        check = _check_filevault()
        assert check.enabled is None
        assert check.severity == "warn"


class TestCheckSIP:
    @patch(
        "osx_system_agent.scanners.security._run_cmd",
        return_value="System Integrity Protection status: enabled.",
    )
    def test_enabled(self, mock_cmd) -> None:
        check = _check_sip()
        assert check.enabled is True
        assert check.severity == "ok"

    @patch(
        "osx_system_agent.scanners.security._run_cmd",
        return_value="System Integrity Protection status: disabled.",
    )
    def test_disabled(self, mock_cmd) -> None:
        check = _check_sip()
        assert check.enabled is False
        assert check.severity == "critical"


class TestCheckGatekeeper:
    @patch(
        "osx_system_agent.scanners.security._run_cmd",
        return_value="assessments enabled",
    )
    def test_enabled(self, mock_cmd) -> None:
        check = _check_gatekeeper()
        assert check.enabled is True
        assert check.severity == "ok"

    @patch(
        "osx_system_agent.scanners.security._run_cmd",
        return_value="assessments disabled",
    )
    def test_disabled(self, mock_cmd) -> None:
        check = _check_gatekeeper()
        assert check.enabled is False
        assert check.severity == "critical"


class TestCheckFirewall:
    @patch(
        "osx_system_agent.scanners.security._run_cmd",
        return_value="Firewall is enabled. (State = 1)",
    )
    def test_enabled(self, mock_cmd) -> None:
        check = _check_firewall()
        assert check.enabled is True
        assert check.severity == "ok"

    @patch(
        "osx_system_agent.scanners.security._run_cmd",
        return_value="Firewall is disabled. (State = 0)",
    )
    def test_disabled(self, mock_cmd) -> None:
        check = _check_firewall()
        assert check.enabled is False
        assert check.severity == "warn"


class TestCheckXProtect:
    @patch("osx_system_agent.scanners.security.Path.exists", return_value=False)
    def test_not_found(self, mock_exists) -> None:
        check = _check_xprotect()
        assert check.enabled is None
        assert check.severity == "warn"


class TestCheckRemoteLogin:
    @patch(
        "osx_system_agent.scanners.security._run_cmd",
        return_value="Remote Login: On",
    )
    def test_ssh_enabled(self, mock_cmd) -> None:
        check = _check_remote_login()
        assert check.enabled is True
        assert check.severity == "warn"

    @patch(
        "osx_system_agent.scanners.security._run_cmd",
        return_value="Remote Login: Off",
    )
    def test_ssh_disabled(self, mock_cmd) -> None:
        check = _check_remote_login()
        assert check.enabled is False
        assert check.severity == "ok"


class TestCheckRemoteManagement:
    @patch("osx_system_agent.scanners.security._run_cmd", return_value="12345")
    def test_ard_running(self, mock_cmd) -> None:
        check = _check_remote_management()
        assert check.enabled is True
        assert check.severity == "warn"

    @patch("osx_system_agent.scanners.security._run_cmd", return_value=None)
    def test_ard_not_running(self, mock_cmd) -> None:
        check = _check_remote_management()
        assert check.enabled is False
        assert check.severity == "ok"
        assert "not active" in check.status


class TestCheckAutoUpdates:
    @patch(
        "osx_system_agent.scanners.security._run_cmd",
        return_value="Automatic check is on",
    )
    @patch("osx_system_agent.scanners.security.Path.exists", return_value=False)
    def test_schedule_on(self, mock_exists, mock_cmd) -> None:
        check = _check_auto_updates()
        assert check.enabled is True
        assert check.severity == "ok"


class TestScanSecurity:
    @patch("osx_system_agent.scanners.security._run_cmd", return_value=None)
    @patch("osx_system_agent.scanners.security.Path.exists", return_value=False)
    def test_returns_audit(self, mock_exists, mock_cmd) -> None:
        audit = scan_security()
        assert isinstance(audit, SecurityAudit)
        assert len(audit.checks) == 8
        for check in audit.checks:
            assert isinstance(check, SecurityCheck)

    @patch("osx_system_agent.scanners.security._run_cmd", return_value=None)
    @patch("osx_system_agent.scanners.security.Path.exists", return_value=False)
    def test_all_unknown_when_commands_fail(self, mock_exists, mock_cmd) -> None:
        audit = scan_security()
        # When all commands fail, checks should have severity "warn" or "ok"
        for check in audit.checks:
            assert check.severity in ("warn", "ok")
