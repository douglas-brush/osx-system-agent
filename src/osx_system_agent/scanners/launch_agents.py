from __future__ import annotations

import plistlib
from dataclasses import dataclass, field
from pathlib import Path

LAUNCH_AGENT_DIRS = [
    Path.home() / "Library" / "LaunchAgents",
    Path("/Library/LaunchAgents"),
    Path("/Library/LaunchDaemons"),
    Path("/System/Library/LaunchAgents"),
    Path("/System/Library/LaunchDaemons"),
]


@dataclass
class LaunchItem:
    path: Path
    label: str
    program: str
    run_at_load: bool
    keep_alive: bool
    disabled: bool
    scope: str  # "user", "system", "apple"
    error: str | None = None
    extra: dict[str, object] = field(default_factory=dict)


def _classify_scope(path: Path) -> str:
    parts = str(path)
    if "/System/Library/" in parts:
        return "apple"
    if str(Path.home()) in parts:
        return "user"
    return "system"


def _parse_plist(path: Path) -> LaunchItem:
    scope = _classify_scope(path)
    try:
        with path.open("rb") as f:
            data = plistlib.load(f)
    except Exception as exc:
        return LaunchItem(
            path=path,
            label=path.stem,
            program="(parse error)",
            run_at_load=False,
            keep_alive=False,
            disabled=False,
            scope=scope,
            error=str(exc),
        )

    label = data.get("Label", path.stem)
    program = data.get("Program", "")
    if not program:
        args = data.get("ProgramArguments", [])
        program = args[0] if args else "(none)"

    return LaunchItem(
        path=path,
        label=label,
        program=program,
        run_at_load=bool(data.get("RunAtLoad", False)),
        keep_alive=bool(data.get("KeepAlive", False)),
        disabled=bool(data.get("Disabled", False)),
        scope=scope,
    )


def scan_launch_agents(
    include_apple: bool = False,
    dirs: list[Path] | None = None,
) -> list[LaunchItem]:
    search_dirs = dirs if dirs is not None else LAUNCH_AGENT_DIRS
    items: list[LaunchItem] = []

    for directory in search_dirs:
        if not directory.exists():
            continue
        for plist in sorted(directory.glob("*.plist")):
            item = _parse_plist(plist)
            if not include_apple and item.scope == "apple":
                continue
            items.append(item)

    items.sort(key=lambda i: (i.scope, i.label))
    return items
