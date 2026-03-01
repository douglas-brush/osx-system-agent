from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class BrewPackage:
    name: str
    version: str
    is_cask: bool
    outdated: bool
    pinned: bool


@dataclass
class BrewAudit:
    formulae: list[BrewPackage]
    casks: list[BrewPackage]
    outdated_formulae: list[BrewPackage]
    outdated_casks: list[BrewPackage]
    brew_version: str
    brew_prefix: str


def _run_brew(*args: str) -> str:
    brew = shutil.which("brew")
    if not brew:
        raise FileNotFoundError("Homebrew not found. Install from https://brew.sh")
    result = subprocess.run(
        [brew, *args],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"brew {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _parse_formula(data: dict) -> BrewPackage:
    return BrewPackage(
        name=data.get("name", data.get("full_name", "")),
        version=data.get("installed", [{}])[0].get("version", "") if data.get("installed") else "",
        is_cask=False,
        outdated=bool(data.get("outdated", False)),
        pinned=bool(data.get("pinned", False)),
    )


def _parse_cask(data: dict) -> BrewPackage:
    return BrewPackage(
        name=data.get("token", data.get("name", [""])[0] if data.get("name") else ""),
        version=data.get("installed", "") or data.get("version", ""),
        is_cask=True,
        outdated=bool(data.get("outdated", False)),
        pinned=False,
    )


def scan_brew() -> BrewAudit:
    # Get brew info
    brew_version = _run_brew("--version").split("\n")[0].strip()
    brew_prefix = _run_brew("--prefix").strip()

    # Installed formulae
    formulae_json = _run_brew("info", "--json=v2", "--installed")
    info = json.loads(formulae_json)

    formulae = [_parse_formula(f) for f in info.get("formulae", [])]
    casks = [_parse_cask(c) for c in info.get("casks", [])]

    # Check outdated
    outdated_json = _run_brew("outdated", "--json=v2")
    outdated = json.loads(outdated_json)

    outdated_formulae = [_parse_formula(f) for f in outdated.get("formulae", [])]
    outdated_casks = [_parse_cask(c) for c in outdated.get("casks", [])]

    # Mark outdated in main lists
    outdated_names = {p.name for p in outdated_formulae} | {p.name for p in outdated_casks}
    for pkg in [*formulae, *casks]:
        if pkg.name in outdated_names:
            pkg.outdated = True

    return BrewAudit(
        formulae=formulae,
        casks=casks,
        outdated_formulae=outdated_formulae,
        outdated_casks=outdated_casks,
        brew_version=brew_version,
        brew_prefix=brew_prefix,
    )
