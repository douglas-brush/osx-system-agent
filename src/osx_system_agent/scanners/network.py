from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field

from osx_system_agent.log import get_logger

log = get_logger("scanners.network")


@dataclass
class NetworkInterface:
    name: str
    service_name: str
    ip_address: str | None
    subnet_mask: str | None
    router: str | None
    dns_servers: list[str]
    status: str  # "active", "inactive", "not connected"
    media: str | None = None


@dataclass
class ListeningPort:
    proto: str  # "tcp", "udp"
    address: str
    port: int
    pid: int | None
    process: str | None


@dataclass
class DNSConfig:
    servers: list[str]
    search_domains: list[str]
    resolver_count: int


@dataclass
class ProxyConfig:
    http_enabled: bool = False
    http_server: str | None = None
    http_port: int | None = None
    https_enabled: bool = False
    https_server: str | None = None
    https_port: int | None = None
    socks_enabled: bool = False
    socks_server: str | None = None
    socks_port: int | None = None


@dataclass
class ConnectivityTest:
    target: str
    success: bool
    latency_ms: float | None = None
    error: str | None = None


@dataclass
class NetworkAudit:
    interfaces: list[NetworkInterface] = field(default_factory=list)
    listening_ports: list[ListeningPort] = field(default_factory=list)
    dns: DNSConfig | None = None
    proxy: ProxyConfig | None = None
    connectivity: list[ConnectivityTest] = field(default_factory=list)
    vpn_active: bool = False
    wifi_ssid: str | None = None
    error: str | None = None


def _run_cmd(*args: str, timeout: int = 10) -> str | None:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _scan_interfaces() -> list[NetworkInterface]:
    interfaces: list[NetworkInterface] = []

    # Get list of network services
    output = _run_cmd("networksetup", "-listallnetworkservices")
    if output is None:
        return interfaces

    services = [
        line for line in output.splitlines()
        if not line.startswith("An asterisk") and line.strip()
    ]

    for service in services:
        info_output = _run_cmd("networksetup", "-getinfo", service)
        if info_output is None:
            continue

        ip_address = None
        subnet = None
        router = None
        dns_servers: list[str] = []

        for line in info_output.splitlines():
            if line.startswith("IP address:"):
                val = line.split(":", 1)[1].strip()
                if val and val != "none":
                    ip_address = val
            elif line.startswith("Subnet mask:"):
                val = line.split(":", 1)[1].strip()
                if val and val != "none":
                    subnet = val
            elif line.startswith("Router:"):
                val = line.split(":", 1)[1].strip()
                if val and val != "none":
                    router = val

        # DNS for this service
        dns_output = _run_cmd("networksetup", "-getdnsservers", service)
        if dns_output and "There aren't any DNS Servers" not in dns_output:
            dns_servers = [
                line.strip() for line in dns_output.splitlines()
                if line.strip() and not line.startswith("There")
            ]

        status = "active" if ip_address else "inactive"

        # Get media info for hardware ports
        media_output = _run_cmd("networksetup", "-getMedia", service)

        interfaces.append(NetworkInterface(
            name=_service_to_interface(service) or service,
            service_name=service,
            ip_address=ip_address,
            subnet_mask=subnet,
            router=router,
            dns_servers=dns_servers,
            status=status,
            media=media_output,
        ))

    return interfaces


def _service_to_interface(service: str) -> str | None:
    """Map a network service name to its BSD interface name."""
    output = _run_cmd("networksetup", "-listallhardwareports")
    if output is None:
        return None
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if f"Hardware Port: {service}" in line:
            for j in range(i + 1, min(i + 3, len(lines))):
                if lines[j].startswith("Device:"):
                    return lines[j].split(":", 1)[1].strip()
    return None


def _scan_listening_ports() -> list[ListeningPort]:
    ports: list[ListeningPort] = []
    output = _run_cmd("lsof", "-iTCP", "-sTCP:LISTEN", "-nP", "-F", "pcnT", timeout=15)
    if output is None:
        return ports

    current_pid: int | None = None
    current_process: str | None = None

    for line in output.splitlines():
        if not line:
            continue
        tag = line[0]
        value = line[1:]
        if tag == "p":
            current_pid = int(value) if value.isdigit() else None
        elif tag == "c":
            current_process = value
        elif tag == "n":
            # Parse "host:port" or "*:port"
            match = re.match(r"^(.+):(\d+)$", value)
            if match:
                addr = match.group(1)
                port_num = int(match.group(2))
                ports.append(ListeningPort(
                    proto="tcp",
                    address=addr,
                    port=port_num,
                    pid=current_pid,
                    process=current_process,
                ))

    # Deduplicate by (address, port, process)
    seen: set[tuple[str, int, str | None]] = set()
    unique: list[ListeningPort] = []
    for p in ports:
        key = (p.address, p.port, p.process)
        if key not in seen:
            seen.add(key)
            unique.append(p)

    unique.sort(key=lambda p: p.port)
    return unique


def _scan_dns() -> DNSConfig:
    servers: list[str] = []
    search_domains: list[str] = []
    resolver_count = 0

    output = _run_cmd("scutil", "--dns")
    if output:
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("nameserver["):
                match = re.search(r":\s*(.+)", line)
                if match:
                    server = match.group(1).strip()
                    if server not in servers:
                        servers.append(server)
            elif line.startswith("search domain["):
                match = re.search(r":\s*(.+)", line)
                if match:
                    domain = match.group(1).strip()
                    if domain not in search_domains:
                        search_domains.append(domain)
            elif line.startswith("resolver #"):
                resolver_count += 1

    return DNSConfig(
        servers=servers,
        search_domains=search_domains,
        resolver_count=resolver_count,
    )


def _scan_proxy(service: str = "Wi-Fi") -> ProxyConfig:
    proxy = ProxyConfig()

    # HTTP proxy
    output = _run_cmd("networksetup", "-getwebproxy", service)
    if output:
        for line in output.splitlines():
            if line.startswith("Enabled:") and "Yes" in line:
                proxy.http_enabled = True
            elif line.startswith("Server:"):
                val = line.split(":", 1)[1].strip()
                if val:
                    proxy.http_server = val
            elif line.startswith("Port:"):
                val = line.split(":", 1)[1].strip()
                if val and val != "0":
                    proxy.http_port = int(val)

    # HTTPS proxy
    output = _run_cmd("networksetup", "-getsecurewebproxy", service)
    if output:
        for line in output.splitlines():
            if line.startswith("Enabled:") and "Yes" in line:
                proxy.https_enabled = True
            elif line.startswith("Server:"):
                val = line.split(":", 1)[1].strip()
                if val:
                    proxy.https_server = val
            elif line.startswith("Port:"):
                val = line.split(":", 1)[1].strip()
                if val and val != "0":
                    proxy.https_port = int(val)

    # SOCKS proxy
    output = _run_cmd("networksetup", "-getsocksfirewallproxy", service)
    if output:
        for line in output.splitlines():
            if line.startswith("Enabled:") and "Yes" in line:
                proxy.socks_enabled = True
            elif line.startswith("Server:"):
                val = line.split(":", 1)[1].strip()
                if val:
                    proxy.socks_server = val
            elif line.startswith("Port:"):
                val = line.split(":", 1)[1].strip()
                if val and val != "0":
                    proxy.socks_port = int(val)

    return proxy


def _test_connectivity() -> list[ConnectivityTest]:
    tests: list[ConnectivityTest] = []

    targets = [
        ("Gateway", None),
        ("Internet (8.8.8.8)", "8.8.8.8"),
        ("DNS (google.com)", "google.com"),
    ]

    # Determine gateway
    route_output = _run_cmd("route", "-n", "get", "default")
    gateway = None
    if route_output:
        for line in route_output.splitlines():
            if "gateway:" in line:
                gateway = line.split(":", 1)[1].strip()
                break

    for label, target in targets:
        if target is None:
            target = gateway
            if target is None:
                tests.append(ConnectivityTest(label, False, error="No default gateway"))
                continue

        ping_output = _run_cmd("ping", "-c", "1", "-t", "3", target, timeout=5)
        if ping_output is not None:
            match = re.search(r"time[=<](\d+\.?\d*)", ping_output)
            latency = float(match.group(1)) if match else None
            tests.append(ConnectivityTest(label, True, latency_ms=latency))
        else:
            tests.append(ConnectivityTest(label, False, error="No response"))

    return tests


def _detect_vpn() -> bool:
    """Check for active VPN by looking at utun interfaces with routes."""
    output = _run_cmd("ifconfig", "-l")
    if output is None:
        return False
    interfaces = output.split()
    utun_count = sum(1 for i in interfaces if i.startswith("utun"))
    # utun0 is usually system; multiple utuns suggest VPN
    return utun_count > 1


def _get_wifi_ssid() -> str | None:
    # macOS 14.4+ uses the airport binary or wdutil
    output = _run_cmd(
        "system_profiler", "SPAirPortDataType", "-json", timeout=15
    )
    if output:
        try:
            data = json.loads(output)
            airport = data.get("SPAirPortDataType", [{}])
            for entry in airport:
                interfaces = entry.get("spairport_airport_interfaces", [])
                for iface in interfaces:
                    current = iface.get("spairport_current_network_information", {})
                    ssid = current.get("_name")
                    if ssid:
                        return ssid
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
    return None


def scan_network() -> NetworkAudit:
    """Audit network configuration: interfaces, DNS, ports, proxies, connectivity."""
    audit = NetworkAudit()

    audit.interfaces = _scan_interfaces()
    audit.listening_ports = _scan_listening_ports()
    audit.dns = _scan_dns()

    # Find the active service for proxy lookup
    active_service = "Wi-Fi"
    for iface in audit.interfaces:
        if iface.status == "active":
            active_service = iface.service_name
            break
    audit.proxy = _scan_proxy(active_service)

    audit.connectivity = _test_connectivity()
    audit.vpn_active = _detect_vpn()
    audit.wifi_ssid = _get_wifi_ssid()

    return audit
