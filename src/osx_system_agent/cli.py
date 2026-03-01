from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from osx_system_agent.reports.writer import write_csv, write_json
from osx_system_agent.scanners.aging import scan_aging
from osx_system_agent.scanners.duplicates import scan_duplicates
from osx_system_agent.scanners.inventory import scan_inventory
from osx_system_agent.system.activity import get_system_status
from osx_system_agent.system.processes import snapshot_processes
from osx_system_agent.utils.human import bytes_to_human, unix_to_iso
from osx_system_agent.utils.parse import parse_size
from osx_system_agent.utils.paths import ensure_dir, expand_path

app = typer.Typer(add_completion=False)
scan_app = typer.Typer()
app.add_typer(scan_app, name="scan")

console = Console()


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _default_outdir(out: Optional[str]) -> Path:
    return ensure_dir(out or "./reports")


@app.command()
def status(path: str = "/") -> None:
    """Print system status (CPU, memory, disk, battery)."""
    status = get_system_status(path)

    table = Table(title="System Status", show_header=False)
    table.add_row("CPU", f"{status.cpu_percent:.1f}%")
    table.add_row(
        "Memory",
        f"{bytes_to_human(status.memory_used)} / {bytes_to_human(status.memory_total)}",
    )
    table.add_row(
        "Disk",
        f"{bytes_to_human(status.disk_used)} / {bytes_to_human(status.disk_total)}",
    )
    if status.battery:
        battery = status.battery
        label = "Plugged" if battery.power_plugged else "On Battery"
        percent = f"{battery.percent:.0f}%" if battery.percent is not None else "Unknown"
        table.add_row("Battery", f"{percent} ({label})")
    else:
        table.add_row("Battery", "Unavailable")

    console.print(table)


@app.command()
def processes(
    sort: str = typer.Option("cpu", help="Sort by cpu or mem."),
    limit: int = typer.Option(20, help="Number of processes to show."),
) -> None:
    """Show top processes by CPU or memory."""
    rows = snapshot_processes(sort=sort, limit=limit)

    table = Table(title="Top Processes")
    table.add_column("PID", justify="right")
    table.add_column("Name")
    table.add_column("User")
    table.add_column("CPU%", justify="right")
    table.add_column("RSS", justify="right")

    for proc in rows:
        table.add_row(
            str(proc.pid),
            proc.name,
            proc.username or "",
            f"{proc.cpu_percent:.1f}",
            bytes_to_human(proc.memory_rss),
        )

    console.print(table)


@scan_app.command("duplicates")
def scan_duplicates_cmd(
    path: str = typer.Option(".", help="Root path to scan."),
    min_size: str = typer.Option("1MB", help="Minimum file size (e.g. 10MB)."),
    out: Optional[str] = typer.Option(None, help="Output directory for reports."),
    exclude: list[str] = typer.Option(None, help="Exclude path pattern (repeatable)."),
    follow_symlinks: bool = typer.Option(False, help="Follow symlinks."),
) -> None:
    """Scan for duplicate files by size + hash."""
    root = expand_path(path)
    min_size_bytes = parse_size(min_size)
    outdir = _default_outdir(out)

    groups = scan_duplicates(
        root,
        min_size=min_size_bytes,
        excludes=exclude if exclude else None,
        follow_symlinks=follow_symlinks,
    )

    json_payload = [
        {
            "size": g.size,
            "hash": g.digest,
            "files": [str(p) for p in g.files],
        }
        for g in groups
    ]

    flat_rows = []
    for idx, group in enumerate(groups, start=1):
        for file_path in group.files:
            flat_rows.append(
                {
                    "group_id": idx,
                    "size": group.size,
                    "hash": group.digest,
                    "path": str(file_path),
                }
            )

    stamp = _timestamp()
    json_path = write_json(json_payload, outdir / f"duplicates-{stamp}.json")
    csv_path = write_csv(flat_rows, outdir / f"duplicates-{stamp}.csv")

    console.print(f"Wrote {len(groups)} duplicate groups.")
    console.print(f"JSON: {json_path}")
    console.print(f"CSV: {csv_path}")


@scan_app.command("aging")
def scan_aging_cmd(
    path: str = typer.Option(".", help="Root path to scan."),
    min_size: str = typer.Option("1MB", help="Minimum file size (e.g. 10MB)."),
    sort: str = typer.Option("mtime", help="Sort by mtime, atime, ctime, or size."),
    limit: int = typer.Option(200, help="Number of rows to return."),
    out: Optional[str] = typer.Option(None, help="Output directory for reports."),
    exclude: list[str] = typer.Option(None, help="Exclude path pattern (repeatable)."),
    follow_symlinks: bool = typer.Option(False, help="Follow symlinks."),
) -> None:
    """Report large/old files for cleanup."""
    root = expand_path(path)
    min_size_bytes = parse_size(min_size)
    outdir = _default_outdir(out)

    rows = scan_aging(
        root,
        min_size=min_size_bytes,
        sort=sort,
        limit=limit,
        excludes=exclude if exclude else None,
        follow_symlinks=follow_symlinks,
    )

    for row in rows:
        row["size_human"] = bytes_to_human(int(row["size"]))
        row["mtime_iso"] = unix_to_iso(float(row["mtime"]))
        row["atime_iso"] = unix_to_iso(float(row["atime"]))
        row["ctime_iso"] = unix_to_iso(float(row["ctime"]))

    stamp = _timestamp()
    json_path = write_json(rows, outdir / f"aging-{stamp}.json")
    csv_path = write_csv(rows, outdir / f"aging-{stamp}.csv")

    console.print(f"Wrote {len(rows)} aging rows.")
    console.print(f"JSON: {json_path}")
    console.print(f"CSV: {csv_path}")


@scan_app.command("inventory")
def scan_inventory_cmd(
    path: str = typer.Option(".", help="Root path to scan."),
    min_size: str = typer.Option("0", help="Minimum file size (e.g. 10MB)."),
    out: Optional[str] = typer.Option(None, help="Output directory for reports."),
    exclude: list[str] = typer.Option(None, help="Exclude path pattern (repeatable)."),
    follow_symlinks: bool = typer.Option(False, help="Follow symlinks."),
) -> None:
    """Summarize file inventory by extension."""
    root = expand_path(path)
    min_size_bytes = parse_size(min_size)
    outdir = _default_outdir(out)

    rows = scan_inventory(
        root,
        min_size=min_size_bytes,
        excludes=exclude if exclude else None,
        follow_symlinks=follow_symlinks,
    )

    for row in rows:
        row["total_human"] = bytes_to_human(int(row["total_size"]))
        row["largest_human"] = bytes_to_human(int(row["largest"]))

    stamp = _timestamp()
    json_path = write_json(rows, outdir / f"inventory-{stamp}.json")
    csv_path = write_csv(rows, outdir / f"inventory-{stamp}.csv")

    console.print(f"Wrote {len(rows)} inventory rows.")
    console.print(f"JSON: {json_path}")
    console.print(f"CSV: {csv_path}")


if __name__ == "__main__":
    app()
