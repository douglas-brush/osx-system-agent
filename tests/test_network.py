from __future__ import annotations

from unittest.mock import patch

from osx_system_agent.scanners.network import (
    DNSConfig,
    NetworkAudit,
    ProxyConfig,
    _detect_vpn,
    _scan_dns,
    _scan_interfaces,
    _scan_listening_ports,
    _scan_proxy,
    _test_connectivity,
    scan_network,
)


class TestScanInterfaces:
    @patch("osx_system_agent.scanners.network._run_cmd", return_value=None)
    def test_returns_empty_on_failure(self, mock_cmd) -> None:
        result = _scan_interfaces()
        assert result == []

    @patch("osx_system_agent.scanners.network._service_to_interface", return_value="en0")
    @patch(
        "osx_system_agent.scanners.network._run_cmd",
        side_effect=lambda *args, **kwargs: {
            ("networksetup", "-listallnetworkservices"): (
                "An asterisk (*) denotes that a network service is disabled.\nWi-Fi"
            ),
            ("networksetup", "-getinfo", "Wi-Fi"): (
                "IP address: 10.0.1.50\nSubnet mask: 255.255.255.0\nRouter: 10.0.1.1"
            ),
            ("networksetup", "-getdnsservers", "Wi-Fi"): "8.8.8.8\n8.8.4.4",
        }.get(args),
    )
    def test_parses_active_interface(self, mock_cmd, mock_iface) -> None:
        result = _scan_interfaces()
        assert len(result) == 1
        assert result[0].ip_address == "10.0.1.50"
        assert result[0].router == "10.0.1.1"
        assert result[0].dns_servers == ["8.8.8.8", "8.8.4.4"]
        assert result[0].status == "active"


class TestScanListeningPorts:
    @patch("osx_system_agent.scanners.network._run_cmd", return_value=None)
    def test_returns_empty_on_failure(self, mock_cmd) -> None:
        result = _scan_listening_ports()
        assert result == []

    @patch(
        "osx_system_agent.scanners.network._run_cmd",
        return_value="p1234\ncHTTPd\nn*:8080\np5678\ncnode\nn127.0.0.1:3000",
    )
    def test_parses_lsof_output(self, mock_cmd) -> None:
        result = _scan_listening_ports()
        assert len(result) == 2
        assert result[0].port == 3000
        assert result[0].process == "node"
        assert result[1].port == 8080
        assert result[1].process == "HTTPd"


class TestScanDNS:
    @patch(
        "osx_system_agent.scanners.network._run_cmd",
        return_value=(
            "resolver #1\n  nameserver[0] : 8.8.8.8\n  nameserver[1] : 8.8.4.4\n"
            "  search domain[0] : local\nresolver #2\n  nameserver[0] : 192.168.1.1"
        ),
    )
    def test_parses_dns_config(self, mock_cmd) -> None:
        result = _scan_dns()
        assert isinstance(result, DNSConfig)
        assert "8.8.8.8" in result.servers
        assert "8.8.4.4" in result.servers
        assert "192.168.1.1" in result.servers
        assert "local" in result.search_domains
        assert result.resolver_count == 2


class TestScanProxy:
    @patch(
        "osx_system_agent.scanners.network._run_cmd",
        return_value="Enabled: No\nServer: \nPort: 0\nAuthenticated Proxy Enabled: 0",
    )
    def test_no_proxy(self, mock_cmd) -> None:
        result = _scan_proxy()
        assert isinstance(result, ProxyConfig)
        assert result.http_enabled is False
        assert result.https_enabled is False
        assert result.socks_enabled is False


class TestConnectivity:
    @patch(
        "osx_system_agent.scanners.network._run_cmd",
        side_effect=lambda *args, **kwargs: (
            "gateway: 10.0.1.1\ninterface: en0"
            if "route" in args
            else "64 bytes from 10.0.1.1: icmp_seq=0 ttl=64 time=1.234 ms"
            if "ping" in args
            else None
        ),
    )
    def test_successful_ping(self, mock_cmd) -> None:
        result = _test_connectivity()
        assert len(result) == 3
        assert result[0].success is True
        assert result[0].latency_ms is not None

    @patch("osx_system_agent.scanners.network._run_cmd", return_value=None)
    def test_all_fail(self, mock_cmd) -> None:
        result = _test_connectivity()
        assert len(result) == 3
        for test in result:
            assert test.success is False


class TestDetectVPN:
    @patch(
        "osx_system_agent.scanners.network._run_cmd",
        return_value="lo0 en0 utun0 utun1 utun2",
    )
    def test_vpn_detected(self, mock_cmd) -> None:
        assert _detect_vpn() is True

    @patch(
        "osx_system_agent.scanners.network._run_cmd",
        return_value="lo0 en0 utun0",
    )
    def test_no_vpn(self, mock_cmd) -> None:
        assert _detect_vpn() is False

    @patch("osx_system_agent.scanners.network._run_cmd", return_value=None)
    def test_command_failure(self, mock_cmd) -> None:
        assert _detect_vpn() is False


class TestScanNetwork:
    @patch("osx_system_agent.scanners.network._get_wifi_ssid", return_value=None)
    @patch("osx_system_agent.scanners.network._detect_vpn", return_value=False)
    @patch("osx_system_agent.scanners.network._test_connectivity", return_value=[])
    @patch(
        "osx_system_agent.scanners.network._scan_proxy",
        return_value=ProxyConfig(),
    )
    @patch(
        "osx_system_agent.scanners.network._scan_dns",
        return_value=DNSConfig(servers=[], search_domains=[], resolver_count=0),
    )
    @patch("osx_system_agent.scanners.network._scan_listening_ports", return_value=[])
    @patch("osx_system_agent.scanners.network._scan_interfaces", return_value=[])
    def test_returns_audit(self, *mocks) -> None:
        audit = scan_network()
        assert isinstance(audit, NetworkAudit)
        assert audit.interfaces == []
        assert audit.listening_ports == []
        assert audit.vpn_active is False
