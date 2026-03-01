from __future__ import annotations

import plistlib
import shutil
from pathlib import Path

from osx_system_agent.log import get_logger

log = get_logger("schedule")

LABEL = "com.osx-system-agent.scheduled-report"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"


def _find_osa_binary() -> str:
    """Find the osa binary path."""
    osa = shutil.which("osa")
    if osa:
        return osa
    # Check common venv locations
    for candidate in [
        Path.home() / "Documents" / "GitHub" / "osx-system-agent" / ".venv" / "bin" / "osa",
        Path.cwd() / ".venv" / "bin" / "osa",
    ]:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError("Cannot find osa binary. Is the package installed?")


def generate_launchagent(
    interval_hours: int = 24,
    report_dir: str = "~/Documents/osx-system-agent-reports",
    label: str = LABEL,
) -> Path:
    """Generate a LaunchAgent plist for periodic report generation."""
    osa_bin = _find_osa_binary()
    report_path = str(Path(report_dir).expanduser())

    plist = {
        "Label": label,
        "ProgramArguments": [
            osa_bin,
            "report",
            "--out",
            report_path,
        ],
        "StartInterval": interval_hours * 3600,
        "RunAtLoad": False,
        "StandardOutPath": str(
            Path.home() / ".local" / "share" / "osx-system-agent" / "logs" / "scheduled.log"
        ),
        "StandardErrorPath": str(
            Path.home() / ".local" / "share" / "osx-system-agent" / "logs" / "scheduled.err"
        ),
    }

    PLIST_DIR.mkdir(parents=True, exist_ok=True)
    plist_path = PLIST_DIR / f"{label}.plist"

    with plist_path.open("wb") as f:
        plistlib.dump(plist, f)

    log.info("wrote LaunchAgent plist: %s", plist_path)
    return plist_path


def remove_launchagent(label: str = LABEL) -> bool:
    """Remove the scheduled LaunchAgent plist."""
    plist_path = PLIST_DIR / f"{label}.plist"
    if plist_path.exists():
        plist_path.unlink()
        log.info("removed LaunchAgent plist: %s", plist_path)
        return True
    return False
