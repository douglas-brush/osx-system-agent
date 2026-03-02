from __future__ import annotations

import plistlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from osx_system_agent.log import get_logger

log = get_logger("scanners.security")


@dataclass
class SecurityCheck:
    name: str
    enabled: bool | None  # None = unknown / not applicable
    status: str  # human-readable detail
    severity: str  # "ok", "warn", "critical"


@dataclass
class SecurityAudit:
    filevault: SecurityCheck | None = None
    sip: SecurityCheck | None = None
    gatekeeper: SecurityCheck | None = None
    firewall: SecurityCheck | None = None
    xprotect: SecurityCheck | None = None
    remote_login: SecurityCheck | None = None
    remote_management: SecurityCheck | None = None
    auto_updates: SecurityCheck | None = None
    checks: list[SecurityCheck] = field(default_factory=list)
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


def _check_filevault() -> SecurityCheck:
    output = _run_cmd("fdesetup", "status")
    if output is None:
        return SecurityCheck("FileVault", None, "Unable to determine status", "warn")
    enabled = "On" in output
    return SecurityCheck(
        "FileVault",
        enabled,
        output,
        "ok" if enabled else "critical",
    )


def _check_sip() -> SecurityCheck:
    output = _run_cmd("csrutil", "status")
    if output is None:
        return SecurityCheck(
            "System Integrity Protection", None, "Unable to determine status", "warn",
        )
    enabled = "enabled" in output.lower()
    return SecurityCheck(
        "System Integrity Protection",
        enabled,
        output,
        "ok" if enabled else "critical",
    )


def _check_gatekeeper() -> SecurityCheck:
    output = _run_cmd("spctl", "--status")
    if output is None:
        return SecurityCheck("Gatekeeper", None, "Unable to determine status", "warn")
    enabled = "enabled" in output.lower() or "assessments enabled" in output.lower()
    return SecurityCheck(
        "Gatekeeper",
        enabled,
        output,
        "ok" if enabled else "critical",
    )


def _check_firewall() -> SecurityCheck:
    # Try socketfilterfw first
    output = _run_cmd("/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate")
    if output is not None:
        enabled = "enabled" in output.lower()
        return SecurityCheck(
            "Application Firewall",
            enabled,
            output,
            "ok" if enabled else "warn",
        )
    # Fallback: read the plist directly
    plist_path = Path("/Library/Preferences/com.apple.alf.plist")
    if plist_path.exists():
        try:
            with plist_path.open("rb") as f:
                data = plistlib.load(f)
            global_state = data.get("globalstate", 0)
            enabled = global_state > 0
            mode = {0: "off", 1: "on (specific services)", 2: "on (essential only)"}.get(
                global_state, f"unknown ({global_state})"
            )
            return SecurityCheck(
                "Application Firewall",
                enabled,
                f"Firewall mode: {mode}",
                "ok" if enabled else "warn",
            )
        except Exception:
            pass
    return SecurityCheck("Application Firewall", None, "Unable to determine status", "warn")


def _check_xprotect() -> SecurityCheck:
    # XProtect version from bundle
    xprotect_meta = Path(
        "/Library/Apple/System/Library/CoreServices/XProtect.bundle/Contents/Info.plist"
    )
    if not xprotect_meta.exists():
        # Older macOS path
        xprotect_meta = Path(
            "/System/Library/CoreServices/XProtect.bundle/Contents/Info.plist"
        )
    if xprotect_meta.exists():
        try:
            with xprotect_meta.open("rb") as f:
                data = plistlib.load(f)
            version = data.get("CFBundleShortVersionString", "unknown")
            return SecurityCheck(
                "XProtect",
                True,
                f"XProtect version: {version}",
                "ok",
            )
        except Exception:
            pass
    return SecurityCheck("XProtect", None, "XProtect bundle not found", "warn")


def _check_remote_login() -> SecurityCheck:
    output = _run_cmd("systemsetup", "-getremotelogin")
    if output is not None and "administrator access" not in output.lower():
        enabled = "on" in output.lower()
        return SecurityCheck(
            "Remote Login (SSH)",
            enabled,
            output,
            "warn" if enabled else "ok",
        )
    # Fallback: check if sshd is running
    ps_output = _run_cmd("pgrep", "-x", "sshd")
    if ps_output is not None and ps_output.strip():
        return SecurityCheck("Remote Login (SSH)", True, "sshd process running", "warn")
    return SecurityCheck("Remote Login (SSH)", False, "sshd not detected", "ok")


def _check_remote_management() -> SecurityCheck:
    # Check if ARDAgent is running
    output = _run_cmd("pgrep", "-x", "ARDAgent")
    if output is not None and output.strip():
        return SecurityCheck("Remote Management (ARD)", True, "ARDAgent process running", "warn")
    return SecurityCheck("Remote Management (ARD)", False, "ARD not active", "ok")


def _check_auto_updates() -> SecurityCheck:
    plist_path = Path("/Library/Preferences/com.apple.SoftwareUpdate.plist")
    if plist_path.exists():
        try:
            with plist_path.open("rb") as f:
                data = plistlib.load(f)
            auto_check = data.get("AutomaticCheckEnabled", False)
            auto_download = data.get("AutomaticDownload", False)
            auto_install = data.get("AutomaticallyInstallMacOSUpdates", False)
            details = (
                f"Check: {'on' if auto_check else 'off'}, "
                f"Download: {'on' if auto_download else 'off'}, "
                f"Install: {'on' if auto_install else 'off'}"
            )
            all_on = auto_check and auto_download
            return SecurityCheck(
                "Automatic Updates",
                all_on,
                details,
                "ok" if all_on else "warn",
            )
        except Exception:
            pass
    # Fallback: softwareupdate --schedule
    output = _run_cmd("softwareupdate", "--schedule")
    if output is not None:
        enabled = "on" in output.lower()
        return SecurityCheck(
            "Automatic Updates",
            enabled,
            output,
            "ok" if enabled else "warn",
        )
    return SecurityCheck("Automatic Updates", None, "Unable to determine status", "warn")


def scan_security() -> SecurityAudit:
    """Audit macOS security posture: FileVault, SIP, Gatekeeper, Firewall, etc."""
    audit = SecurityAudit()

    audit.filevault = _check_filevault()
    audit.sip = _check_sip()
    audit.gatekeeper = _check_gatekeeper()
    audit.firewall = _check_firewall()
    audit.xprotect = _check_xprotect()
    audit.remote_login = _check_remote_login()
    audit.remote_management = _check_remote_management()
    audit.auto_updates = _check_auto_updates()

    audit.checks = [
        c for c in [
            audit.filevault,
            audit.sip,
            audit.gatekeeper,
            audit.firewall,
            audit.xprotect,
            audit.remote_login,
            audit.remote_management,
            audit.auto_updates,
        ]
        if c is not None
    ]

    return audit
