from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from osx_system_agent.log import setup_logging
from osx_system_agent.reports.writer import write_csv, write_json
from osx_system_agent.scanners.aging import scan_aging
from osx_system_agent.scanners.brew import scan_brew
from osx_system_agent.scanners.caches import scan_caches
from osx_system_agent.scanners.disk_hogs import scan_disk_hogs
from osx_system_agent.scanners.disk_usage import scan_disk_usage
from osx_system_agent.scanners.duplicates import scan_duplicates
from osx_system_agent.scanners.inventory import scan_inventory
from osx_system_agent.scanners.junk import scan_junk
from osx_system_agent.scanners.launch_agents import scan_launch_agents
from osx_system_agent.scanners.login_items import scan_login_items
from osx_system_agent.system.activity import get_system_status
from osx_system_agent.system.processes import snapshot_processes
from osx_system_agent.utils.human import bytes_to_human, unix_to_iso
from osx_system_agent.utils.parse import parse_size
from osx_system_agent.utils.paths import ensure_dir, expand_path

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
scan_app = typer.Typer(help="File and system scanners.")
clean_app = typer.Typer(help="Cleanup and remediation commands.")
app.add_typer(scan_app, name="scan")
app.add_typer(clean_app, name="clean")

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        from osx_system_agent import __version__

        console.print(f"osx-system-agent {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose/debug output."),
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version."
    ),
) -> None:
    """OSA — macOS system agent for monitoring and file hygiene."""
    setup_logging(verbose=verbose)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _default_outdir(out: str | None) -> Path:
    return ensure_dir(out or "./reports")


# ---------------------------------------------------------------------------
# System commands
# ---------------------------------------------------------------------------


@app.command()
def status(path: str = "/") -> None:
    """Print system status (CPU, memory, disk, battery)."""
    info = get_system_status(path)

    table = Table(title="System Status", show_header=False)
    table.add_row("CPU", f"{info.cpu_percent:.1f}%")
    table.add_row(
        "Memory",
        f"{bytes_to_human(info.memory_used)} / {bytes_to_human(info.memory_total)}",
    )
    table.add_row(
        "Disk",
        f"{bytes_to_human(info.disk_used)} / {bytes_to_human(info.disk_total)}",
    )
    if info.battery:
        battery = info.battery
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


# ---------------------------------------------------------------------------
# Scan commands
# ---------------------------------------------------------------------------


@scan_app.command("duplicates")
def scan_duplicates_cmd(
    path: str = typer.Option(".", help="Root path to scan."),
    min_size: str = typer.Option("1MB", help="Minimum file size (e.g. 10MB)."),
    out: str | None = typer.Option(None, help="Output directory for reports."),
    exclude: list[str] | None = typer.Option(None, help="Exclude path pattern (repeatable)."),
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
    out: str | None = typer.Option(None, help="Output directory for reports."),
    exclude: list[str] | None = typer.Option(None, help="Exclude path pattern (repeatable)."),
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
    out: str | None = typer.Option(None, help="Output directory for reports."),
    exclude: list[str] | None = typer.Option(None, help="Exclude path pattern (repeatable)."),
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


@scan_app.command("launch-agents")
def scan_launch_agents_cmd(
    include_apple: bool = typer.Option(False, help="Include Apple system agents."),
    out: str | None = typer.Option(None, help="Output directory for reports."),
) -> None:
    """Inventory LaunchAgents and LaunchDaemons."""
    items = scan_launch_agents(include_apple=include_apple)
    outdir = _default_outdir(out)

    table = Table(title="Launch Agents / Daemons")
    table.add_column("Scope")
    table.add_column("Label")
    table.add_column("Program")
    table.add_column("RunAtLoad")
    table.add_column("Disabled")

    for item in items:
        table.add_row(
            item.scope,
            item.label,
            str(item.program)[:60],
            "yes" if item.run_at_load else "",
            "yes" if item.disabled else "",
        )

    console.print(table)

    rows = [
        {
            "scope": i.scope,
            "label": i.label,
            "program": i.program,
            "run_at_load": i.run_at_load,
            "keep_alive": i.keep_alive,
            "disabled": i.disabled,
            "path": str(i.path),
            "error": i.error or "",
        }
        for i in items
    ]

    stamp = _timestamp()
    json_path = write_json(rows, outdir / f"launch-agents-{stamp}.json")
    csv_path = write_csv(rows, outdir / f"launch-agents-{stamp}.csv")

    console.print(f"\nFound {len(items)} launch items.")
    console.print(f"JSON: {json_path}")
    console.print(f"CSV: {csv_path}")


@scan_app.command("brew")
def scan_brew_cmd(
    out: str | None = typer.Option(None, help="Output directory for reports."),
) -> None:
    """Audit Homebrew packages (installed, outdated)."""
    audit = scan_brew()
    outdir = _default_outdir(out)

    console.print(f"[bold]{audit.brew_version}[/bold]  ({audit.brew_prefix})")
    console.print(f"Formulae: {len(audit.formulae)}  |  Casks: {len(audit.casks)}")

    if audit.outdated_formulae or audit.outdated_casks:
        table = Table(title="Outdated Packages")
        table.add_column("Name")
        table.add_column("Version")
        table.add_column("Type")
        for pkg in [*audit.outdated_formulae, *audit.outdated_casks]:
            table.add_row(pkg.name, pkg.version, "cask" if pkg.is_cask else "formula")
        console.print(table)
    else:
        console.print("[green]All packages up to date.[/green]")

    rows = [
        {
            "name": p.name,
            "version": p.version,
            "type": "cask" if p.is_cask else "formula",
            "outdated": p.outdated,
            "pinned": p.pinned,
        }
        for p in [*audit.formulae, *audit.casks]
    ]

    stamp = _timestamp()
    json_path = write_json(rows, outdir / f"brew-{stamp}.json")
    csv_path = write_csv(rows, outdir / f"brew-{stamp}.csv")
    console.print(f"JSON: {json_path}")
    console.print(f"CSV: {csv_path}")


@scan_app.command("disk-hogs")
def scan_disk_hogs_cmd(
    min_size: str = typer.Option("100MB", help="Minimum directory size to report."),
    out: str | None = typer.Option(None, help="Output directory for reports."),
) -> None:
    """Report largest directories on disk."""
    min_bytes = parse_size(min_size)
    results = scan_disk_hogs(min_size=min_bytes)
    outdir = _default_outdir(out)

    table = Table(title="Disk Hogs")
    table.add_column("Directory")
    table.add_column("Size", justify="right")
    table.add_column("Files", justify="right")

    for d in results:
        style = "red" if d.size > 1024**3 else ""
        table.add_row(str(d.path), bytes_to_human(d.size), str(d.file_count), style=style)

    console.print(table)

    rows = [
        {
            "path": str(d.path),
            "size": d.size,
            "size_human": bytes_to_human(d.size),
            "file_count": d.file_count,
            "error": d.error or "",
        }
        for d in results
    ]

    stamp = _timestamp()
    json_path = write_json(rows, outdir / f"disk-hogs-{stamp}.json")
    csv_path = write_csv(rows, outdir / f"disk-hogs-{stamp}.csv")
    console.print(f"JSON: {json_path}")
    console.print(f"CSV: {csv_path}")


@scan_app.command("caches")
def scan_caches_cmd(
    min_size: str = typer.Option("10MB", help="Minimum cache size to report."),
    out: str | None = typer.Option(None, help="Output directory for reports."),
) -> None:
    """Report cache directory sizes."""
    min_bytes = parse_size(min_size)
    results = scan_caches(min_size=min_bytes)
    outdir = _default_outdir(out)

    total = sum(c.size for c in results)

    table = Table(title=f"Caches ({bytes_to_human(total)} total)")
    table.add_column("Category")
    table.add_column("Size", justify="right")
    table.add_column("Files", justify="right")
    table.add_column("Path")

    for c in results:
        table.add_row(c.category, bytes_to_human(c.size), str(c.file_count), str(c.path))

    console.print(table)

    rows = [
        {
            "category": c.category,
            "path": str(c.path),
            "size": c.size,
            "size_human": bytes_to_human(c.size),
            "file_count": c.file_count,
        }
        for c in results
    ]

    stamp = _timestamp()
    json_path = write_json(rows, outdir / f"caches-{stamp}.json")
    csv_path = write_csv(rows, outdir / f"caches-{stamp}.csv")
    console.print(f"JSON: {json_path}")
    console.print(f"CSV: {csv_path}")


@scan_app.command("junk")
def scan_junk_cmd(
    path: str = typer.Option(".", help="Root path to scan."),
    out: str | None = typer.Option(None, help="Output directory for reports."),
) -> None:
    """Find .DS_Store, ._* files, and other junk."""
    root = expand_path(path)
    results = scan_junk(root)
    outdir = _default_outdir(out)

    total = sum(j.size for j in results)

    table = Table(title=f"Junk Files ({len(results)} found, {bytes_to_human(total)})")
    table.add_column("Category")
    table.add_column("Size", justify="right")
    table.add_column("Path")

    for j in results[:50]:  # limit display
        table.add_row(j.category, bytes_to_human(j.size), str(j.path))

    if len(results) > 50:
        table.add_row("...", "", f"({len(results) - 50} more)")

    console.print(table)

    rows = [
        {
            "category": j.category,
            "path": str(j.path),
            "size": j.size,
            "size_human": bytes_to_human(j.size),
        }
        for j in results
    ]

    stamp = _timestamp()
    json_path = write_json(rows, outdir / f"junk-{stamp}.json")
    csv_path = write_csv(rows, outdir / f"junk-{stamp}.csv")
    console.print(f"JSON: {json_path}")
    console.print(f"CSV: {csv_path}")


# ---------------------------------------------------------------------------
# Clean commands
# ---------------------------------------------------------------------------


@clean_app.command("caches")
def clean_caches_cmd(
    min_size: str = typer.Option("10MB", help="Minimum cache size to clean."),
    dry_run: bool = typer.Option(True, help="Preview only; pass --no-dry-run to execute."),
) -> None:
    """Purge cache directories. Use --no-dry-run to execute."""
    from osx_system_agent.clean.caches import clean_caches

    min_bytes = parse_size(min_size)
    results = clean_caches(min_size=min_bytes, dry_run=dry_run)

    mode = "[bold yellow]DRY RUN[/bold yellow]" if dry_run else "[bold red]LIVE[/bold red]"
    total = sum(r.size_before for r in results)

    table = Table(title=f"Cache Cleanup ({mode})")
    table.add_column("Category")
    table.add_column("Size", justify="right")
    table.add_column("Status")

    for r in results:
        status = "deleted" if r.deleted else ("would delete" if dry_run else r.error or "skipped")
        table.add_row(r.category, bytes_to_human(r.size_before), status)

    console.print(table)
    console.print(f"Total: {bytes_to_human(total)}")

    if dry_run:
        console.print("\n[yellow]Pass --no-dry-run to execute cleanup.[/yellow]")


@clean_app.command("junk")
def clean_junk_cmd(
    path: str = typer.Option(".", help="Root path to scan."),
    dry_run: bool = typer.Option(True, help="Preview only; pass --no-dry-run to execute."),
) -> None:
    """Remove .DS_Store, ._* files, and other junk. Use --no-dry-run to execute."""
    from osx_system_agent.clean.junk import clean_junk

    root = expand_path(path)
    results = clean_junk(root, dry_run=dry_run)

    mode = "[bold yellow]DRY RUN[/bold yellow]" if dry_run else "[bold red]LIVE[/bold red]"
    total = sum(r.size for r in results)

    table = Table(title=f"Junk Cleanup ({mode})")
    table.add_column("Category")
    table.add_column("Size", justify="right")
    table.add_column("Status")
    table.add_column("Path")

    for r in results[:50]:
        status = "deleted" if r.deleted else ("would delete" if dry_run else r.error or "skipped")
        table.add_row(r.category, bytes_to_human(r.size), status, str(r.path))

    if len(results) > 50:
        table.add_row("...", "", "", f"({len(results) - 50} more)")

    console.print(table)
    console.print(f"Total: {len(results)} files, {bytes_to_human(total)}")

    if dry_run:
        console.print("\n[yellow]Pass --no-dry-run to execute cleanup.[/yellow]")


@clean_app.command("duplicates")
def clean_duplicates_cmd(
    path: str = typer.Option(".", help="Root path to scan."),
    min_size: str = typer.Option("1MB", help="Minimum file size."),
    exclude: list[str] | None = typer.Option(None, help="Exclude path pattern (repeatable)."),
    dry_run: bool = typer.Option(True, help="Preview only; pass --no-dry-run to execute."),
) -> None:
    """Deduplicate files by trashing duplicates. Use --no-dry-run to execute."""
    from osx_system_agent.clean.duplicates import clean_duplicates

    root = expand_path(path)
    min_bytes = parse_size(min_size)
    results = clean_duplicates(
        root,
        min_size=min_bytes,
        excludes=list(exclude) if exclude else None,
        dry_run=dry_run,
    )

    mode = "[bold yellow]DRY RUN[/bold yellow]" if dry_run else "[bold red]LIVE[/bold red]"
    total_freed = sum(r.size_freed for r in results)

    table = Table(title=f"Duplicate Cleanup ({mode})")
    table.add_column("Keep")
    table.add_column("Trash", justify="right")
    table.add_column("Freed", justify="right")

    for r in results[:50]:
        table.add_row(
            str(r.kept.name),
            str(len(r.removed)),
            bytes_to_human(r.size_freed),
        )

    console.print(table)
    console.print(f"Total: {len(results)} groups, {bytes_to_human(total_freed)} freed")

    if dry_run:
        console.print("\n[yellow]Pass --no-dry-run to execute cleanup.[/yellow]")


# ---------------------------------------------------------------------------
# Additional scan commands
# ---------------------------------------------------------------------------


@scan_app.command("disk-usage")
def scan_disk_usage_cmd(
    path: str = typer.Option("~", help="Root path to analyze."),
    min_size: str = typer.Option("100MB", help="Minimum directory size to show."),
    include_hidden: bool = typer.Option(True, help="Include hidden directories."),
    out: str | None = typer.Option(None, help="Output directory for reports."),
) -> None:
    """Show disk usage breakdown by directory (like du -sh)."""
    root = expand_path(path)
    min_bytes = parse_size(min_size)
    results = scan_disk_usage(root, min_size=min_bytes, include_hidden=include_hidden)
    outdir = _default_outdir(out)

    total = sum(d.size for d in results)

    table = Table(title=f"Disk Usage: {root} ({bytes_to_human(total)} total)")
    table.add_column("Directory")
    table.add_column("Size", justify="right")
    table.add_column("Files", justify="right")

    for d in results:
        style = "red" if d.size > 10 * 1024**3 else ("yellow" if d.size > 1024**3 else "")
        name = "(loose files)" if d.path.name == "(loose files)" else d.path.name
        table.add_row(name, bytes_to_human(d.size), str(d.file_count), style=style)

    console.print(table)

    rows = [
        {
            "path": str(d.path),
            "size": d.size,
            "size_human": bytes_to_human(d.size),
            "file_count": d.file_count,
            "hidden": d.is_hidden,
        }
        for d in results
    ]
    stamp = _timestamp()
    json_path = write_json(rows, outdir / f"disk-usage-{stamp}.json")
    csv_path = write_csv(rows, outdir / f"disk-usage-{stamp}.csv")
    console.print(f"JSON: {json_path}")
    console.print(f"CSV: {csv_path}")


@scan_app.command("login-items")
def scan_login_items_cmd() -> None:
    """List macOS login items."""
    items = scan_login_items()

    table = Table(title="Login Items")
    table.add_column("Name")
    table.add_column("Kind")
    table.add_column("Source")
    table.add_column("Path")

    for item in items:
        table.add_row(item.name, item.kind, item.source, item.path[:60] if item.path else "")

    console.print(table)
    console.print(f"\nFound {len(items)} login items.")


# ---------------------------------------------------------------------------
# Consolidated report
# ---------------------------------------------------------------------------


@app.command()
def report(
    path: str | None = typer.Option(None, help="Optional path to scan for junk files."),
    out: str | None = typer.Option(None, help="Output directory for report."),
) -> None:
    """Generate a consolidated system health report (JSON)."""
    from osx_system_agent.reports.consolidated import generate_report

    outdir = _default_outdir(out)
    scan_path = expand_path(path) if path else None
    report_path = generate_report(outdir, scan_path=scan_path)
    console.print(f"[bold green]Report generated:[/bold green] {report_path}")


if __name__ == "__main__":
    app()
