from __future__ import annotations

from unittest.mock import patch

from osx_system_agent.reports.html import (
    _conn_badge,
    _esc,
    _severity_badge,
    _status_badge,
    generate_html_report,
)


class TestEsc:
    def test_html_entities(self) -> None:
        assert _esc("<script>") == "&lt;script&gt;"
        assert _esc("A & B") == "A &amp; B"

    def test_plain_text(self) -> None:
        assert _esc("hello") == "hello"


class TestBadges:
    def test_severity_ok(self) -> None:
        html = _severity_badge("ok")
        assert "badge-pass" in html
        assert "ok" in html

    def test_severity_warn(self) -> None:
        html = _severity_badge("warn")
        assert "badge-warn" in html

    def test_severity_critical(self) -> None:
        html = _severity_badge("critical")
        assert "badge-critical" in html

    def test_status_pass(self) -> None:
        html = _status_badge(True)
        assert "PASS" in html

    def test_status_fail(self) -> None:
        html = _status_badge(False)
        assert "FAIL" in html

    def test_status_unknown(self) -> None:
        html = _status_badge(None)
        assert "UNKNOWN" in html

    def test_conn_ok(self) -> None:
        html = _conn_badge(True)
        assert "badge-ok" in html

    def test_conn_fail(self) -> None:
        html = _conn_badge(False)
        assert "badge-fail" in html


class TestGenerateHtmlReport:
    @patch("osx_system_agent.reports.html.scan_launch_agents", return_value=[])
    @patch("osx_system_agent.reports.html.scan_caches", return_value=[])
    @patch("osx_system_agent.reports.html.scan_disk_hogs", return_value=[])
    @patch("osx_system_agent.reports.html.scan_network")
    @patch("osx_system_agent.reports.html.scan_security")
    @patch("osx_system_agent.reports.html.get_system_status")
    @patch("osx_system_agent.reports.html._logo_data_uri", return_value="")
    def test_generates_html_file(
        self, mock_logo, mock_sys, mock_sec, mock_net,
        mock_hogs, mock_caches, mock_agents, tmp_path,
    ) -> None:
        from osx_system_agent.scanners.network import (
            DNSConfig,
            NetworkAudit,
            ProxyConfig,
        )
        from osx_system_agent.scanners.security import SecurityAudit, SecurityCheck
        from osx_system_agent.system.activity import BatteryStatus, SystemStatus

        mock_sys.return_value = SystemStatus(
            cpu_percent=25.0,
            memory_total=16 * 1024**3,
            memory_used=8 * 1024**3,
            memory_available=8 * 1024**3,
            disk_total=500 * 1024**3,
            disk_used=250 * 1024**3,
            disk_free=250 * 1024**3,
            battery=BatteryStatus(percent=85.0, power_plugged=True),
        )
        mock_sec.return_value = SecurityAudit(
            checks=[
                SecurityCheck("FileVault", True, "On", "ok"),
                SecurityCheck("SIP", True, "Enabled", "ok"),
            ],
        )
        mock_net.return_value = NetworkAudit(
            dns=DNSConfig(servers=["8.8.8.8"], search_domains=[], resolver_count=1),
            proxy=ProxyConfig(),
        )

        report_path = generate_html_report(tmp_path)
        assert report_path.exists()
        assert report_path.suffix == ".html"

        content = report_path.read_text()
        assert "<!DOCTYPE html>" in content
        assert "Brush Cyber" in content
        assert "System Health Report" in content
        assert "Security Posture" in content
        assert "FileVault" in content
        assert "25.0%" in content
