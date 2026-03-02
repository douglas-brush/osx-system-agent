from __future__ import annotations

import json
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
from osx_system_agent.scanners.network import scan_network
from osx_system_agent.scanners.security import scan_security
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


@scan_app.command("security")
def scan_security_cmd() -> None:
    """Audit macOS security posture (FileVault, SIP, Gatekeeper, Firewall, etc.)."""
    audit = scan_security()

    table = Table(title="Security Audit")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")

    severity_style = {"ok": "green", "warn": "yellow", "critical": "red"}

    for check in audit.checks:
        if check.enabled is True:
            badge = "[green]PASS[/green]"
        elif check.enabled is False:
            badge = "[red]FAIL[/red]" if check.severity == "critical" else "[yellow]WARN[/yellow]"
        else:
            badge = "[dim]UNKNOWN[/dim]"
        style = severity_style.get(check.severity, "")
        table.add_row(check.name, badge, check.status[:80], style=style)

    console.print(table)

    critical = sum(1 for c in audit.checks if c.severity == "critical")
    warn = sum(1 for c in audit.checks if c.severity == "warn")
    ok = sum(1 for c in audit.checks if c.severity == "ok")
    console.print(
        f"\n[green]{ok} passed[/green]  [yellow]{warn} warnings[/yellow]"
        f"  [red]{critical} critical[/red]"
    )


@scan_app.command("network")
def scan_network_cmd() -> None:
    """Audit network: interfaces, DNS, listening ports, proxies, connectivity."""
    audit = scan_network()

    # Interfaces
    iface_table = Table(title="Network Interfaces")
    iface_table.add_column("Service")
    iface_table.add_column("Interface")
    iface_table.add_column("IP Address")
    iface_table.add_column("Router")
    iface_table.add_column("Status")

    for iface in audit.interfaces:
        style = "green" if iface.status == "active" else "dim"
        iface_table.add_row(
            iface.service_name,
            iface.name,
            iface.ip_address or "-",
            iface.router or "-",
            iface.status,
            style=style,
        )
    console.print(iface_table)

    # DNS
    if audit.dns:
        dns_table = Table(title="DNS Configuration")
        dns_table.add_column("Servers")
        dns_table.add_column("Search Domains")
        dns_table.add_column("Resolvers")
        dns_table.add_row(
            ", ".join(audit.dns.servers) or "(none)",
            ", ".join(audit.dns.search_domains) or "(none)",
            str(audit.dns.resolver_count),
        )
        console.print(dns_table)

    # Listening ports
    if audit.listening_ports:
        port_table = Table(title="Listening Ports")
        port_table.add_column("Port", justify="right")
        port_table.add_column("Address")
        port_table.add_column("Process")
        port_table.add_column("PID", justify="right")
        for p in audit.listening_ports[:30]:
            port_table.add_row(
                str(p.port),
                p.address,
                p.process or "-",
                str(p.pid) if p.pid else "-",
            )
        if len(audit.listening_ports) > 30:
            port_table.add_row("...", f"+{len(audit.listening_ports) - 30} more", "", "")
        console.print(port_table)

    # Proxy
    if audit.proxy:
        any_proxy = (
            audit.proxy.http_enabled or audit.proxy.https_enabled or audit.proxy.socks_enabled
        )
        if any_proxy:
            proxy_table = Table(title="Proxy Configuration")
            proxy_table.add_column("Type")
            proxy_table.add_column("Server")
            proxy_table.add_column("Port")
            if audit.proxy.http_enabled:
                proxy_table.add_row(
                    "HTTP", audit.proxy.http_server or "-",
                    str(audit.proxy.http_port or "-"),
                )
            if audit.proxy.https_enabled:
                proxy_table.add_row(
                    "HTTPS", audit.proxy.https_server or "-",
                    str(audit.proxy.https_port or "-"),
                )
            if audit.proxy.socks_enabled:
                proxy_table.add_row(
                    "SOCKS", audit.proxy.socks_server or "-",
                    str(audit.proxy.socks_port or "-"),
                )
            console.print(proxy_table)
        else:
            console.print("[dim]No proxy configured.[/dim]")

    # Connectivity
    if audit.connectivity:
        conn_table = Table(title="Connectivity")
        conn_table.add_column("Target")
        conn_table.add_column("Status")
        conn_table.add_column("Latency")
        for test in audit.connectivity:
            status = "[green]OK[/green]" if test.success else f"[red]FAIL[/red] {test.error or ''}"
            latency = f"{test.latency_ms:.1f}ms" if test.latency_ms else "-"
            conn_table.add_row(test.target, status, latency)
        console.print(conn_table)

    # VPN / Wi-Fi
    extras = []
    if audit.vpn_active:
        extras.append("[yellow]VPN detected[/yellow]")
    if audit.wifi_ssid:
        extras.append(f"Wi-Fi SSID: {audit.wifi_ssid}")
    if extras:
        console.print("  ".join(extras))


@scan_app.command("all")
def scan_all_cmd() -> None:
    """Run all scanners and print a summary dashboard."""
    from rich.panel import Panel

    console.print("[bold]Running all scanners...[/bold]\n")

    # System status
    info = get_system_status()
    status_table = Table(title="System Status", show_header=False)
    status_table.add_row("CPU", f"{info.cpu_percent:.1f}%")
    status_table.add_row(
        "Memory",
        f"{bytes_to_human(info.memory_used)} / {bytes_to_human(info.memory_total)}",
    )
    status_table.add_row(
        "Disk",
        f"{bytes_to_human(info.disk_used)} / {bytes_to_human(info.disk_total)}"
        f" ({bytes_to_human(info.disk_free)} free)",
    )
    console.print(status_table)

    # Caches
    caches = scan_caches(min_size=10 * 1024 * 1024)
    total_cache = sum(c.size for c in caches)
    console.print(
        Panel(
            f"[bold]{bytes_to_human(total_cache)}[/bold] in {len(caches)} cache locations",
            title="Caches",
        )
    )

    # Disk hogs
    hogs = scan_disk_hogs(min_size=500 * 1024 * 1024)
    if hogs:
        hog_table = Table(title="Disk Hogs (>500MB)")
        hog_table.add_column("Directory")
        hog_table.add_column("Size", justify="right")
        for d in hogs[:10]:
            style = "red" if d.size > 1024**3 else ""
            hog_table.add_row(str(d.path), bytes_to_human(d.size), style=style)
        console.print(hog_table)

    # Launch agents
    agents = scan_launch_agents(include_apple=False)
    run_at_load = [a for a in agents if a.run_at_load]
    console.print(
        Panel(
            f"[bold]{len(agents)}[/bold] agents/daemons, "
            f"[bold]{len(run_at_load)}[/bold] run at load",
            title="Launch Agents",
        )
    )

    # Login items
    logins = scan_login_items()
    if logins:
        console.print(
            Panel(
                ", ".join(i.name for i in logins[:10])
                + (f" (+{len(logins) - 10} more)" if len(logins) > 10 else ""),
                title=f"Login Items ({len(logins)})",
            )
        )

    # Security posture
    sec_audit = scan_security()
    critical = sum(1 for c in sec_audit.checks if c.severity == "critical")
    warn = sum(1 for c in sec_audit.checks if c.severity == "warn")
    ok = sum(1 for c in sec_audit.checks if c.severity == "ok")
    sec_color = "red" if critical else "yellow" if warn else "green"
    console.print(
        Panel(
            f"[green]{ok} passed[/green]  [yellow]{warn} warnings[/yellow]  "
            f"[red]{critical} critical[/red]",
            title="Security Posture",
            border_style=sec_color,
        )
    )

    # Network connectivity
    net_audit = scan_network()
    active_ifaces = [i for i in net_audit.interfaces if i.status == "active"]
    conn_ok = sum(1 for t in net_audit.connectivity if t.success)
    conn_total = len(net_audit.connectivity)
    net_parts = [
        f"[bold]{len(active_ifaces)}[/bold] active interfaces",
        f"[bold]{conn_ok}/{conn_total}[/bold] connectivity checks passed",
        f"[bold]{len(net_audit.listening_ports)}[/bold] listening ports",
    ]
    if net_audit.vpn_active:
        net_parts.append("[yellow]VPN active[/yellow]")
    if net_audit.wifi_ssid:
        net_parts.append(f"SSID: {net_audit.wifi_ssid}")
    console.print(
        Panel(
            "  |  ".join(net_parts),
            title="Network",
        )
    )

    console.print("\n[bold green]Scan complete.[/bold green] Run individual scans for details.")


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


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------


@app.command()
def schedule(
    interval: int = typer.Option(24, help="Run interval in hours."),
    report_dir: str = typer.Option(
        "~/Documents/osx-system-agent-reports", help="Directory for scheduled reports."
    ),
    remove: bool = typer.Option(False, help="Remove the scheduled agent."),
) -> None:
    """Install/remove a LaunchAgent for periodic system reports."""
    from osx_system_agent.schedule import generate_launchagent, remove_launchagent

    if remove:
        if remove_launchagent():
            console.print("[green]Scheduled agent removed.[/green]")
        else:
            console.print("[yellow]No scheduled agent found.[/yellow]")
        return

    plist_path = generate_launchagent(
        interval_hours=interval,
        report_dir=report_dir,
    )
    console.print(f"[green]LaunchAgent installed:[/green] {plist_path}")
    console.print(f"Reports every {interval}h to {report_dir}")
    console.print("\nTo load now:")
    console.print(f"  launchctl load {plist_path}")
    console.print("To unload:")
    console.print(f"  launchctl unload {plist_path}")


@app.command()
def snapshot() -> None:
    """Record a point-in-time disk/cache snapshot for trend tracking."""
    from osx_system_agent.reports.history import record_snapshot

    snap = record_snapshot()
    console.print(f"[green]Snapshot recorded[/green] at {snap['timestamp']}")
    console.print(
        f"Disk: {bytes_to_human(snap['disk_used'])} used, "
        f"{bytes_to_human(snap['disk_free'])} free"
    )
    console.print(f"Caches: {bytes_to_human(snap['cache_total'])}")


@app.command()
def trend() -> None:
    """Show disk usage trend compared to last snapshot."""
    from osx_system_agent.reports.history import compare_latest, load_history

    history = load_history(limit=10)
    if not history:
        console.print("[yellow]No snapshots yet. Run 'osa snapshot' first.[/yellow]")
        return

    table = Table(title="Disk Usage History")
    table.add_column("Timestamp")
    table.add_column("Disk Used", justify="right")
    table.add_column("Disk Free", justify="right")
    table.add_column("Caches", justify="right")

    for snap in history:
        table.add_row(
            snap["timestamp"],
            bytes_to_human(snap["disk_used"]),
            bytes_to_human(snap["disk_free"]),
            bytes_to_human(snap["cache_total"]),
        )

    console.print(table)

    delta = compare_latest()
    if delta:
        direction = "[red]+[/red]" if delta["disk_used_delta"] > 0 else "[green]-[/green]"
        console.print(
            f"\nDisk change: {direction}{delta['disk_used_delta_human']} "
            f"since {delta['prev_timestamp']}"
        )
        cache_dir = "[red]+[/red]" if delta["cache_delta"] > 0 else "[green]-[/green]"
        console.print(f"Cache change: {cache_dir}{delta['cache_delta_human']}")


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------


@app.command()
def doctor(
    path: str | None = typer.Option(None, help="Path to scan for junk."),
) -> None:
    """Run system health diagnostics and suggest fixes."""
    from osx_system_agent.doctor import run_diagnostics

    scan_path = expand_path(path) if path else None
    items = run_diagnostics(scan_path=scan_path)

    severity_styles = {
        "critical": "[bold red]CRITICAL[/bold red]",
        "warning": "[yellow]WARNING[/yellow]",
        "info": "[green]OK[/green]",
    }

    table = Table(title="System Health Check")
    table.add_column("Status", width=12)
    table.add_column("Category")
    table.add_column("Finding")
    table.add_column("Suggestion")

    for item in items:
        style = severity_styles.get(item.severity, item.severity)
        table.add_row(style, item.category, item.message, item.suggestion)

    console.print(table)

    crits = sum(1 for i in items if i.severity == "critical")
    warns = sum(1 for i in items if i.severity == "warning")
    if crits:
        console.print(f"\n[bold red]{crits} critical issue(s)[/bold red]")
    elif warns:
        console.print(f"\n[yellow]{warns} warning(s)[/yellow]")
    else:
        console.print("\n[bold green]All checks passed.[/bold green]")


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------


@app.command()
def undo(
    limit: int = typer.Option(20, help="Number of recent actions to show."),
    restore: int | None = typer.Option(
        None, help="Restore a specific action by index (1-based)."
    ),
    clear: bool = typer.Option(False, help="Clear the undo log."),
) -> None:
    """View and undo recent clean operations."""
    from osx_system_agent.undo import (
        clear_undo_log,
        load_undo_log,
        undo_trash,
    )

    if clear:
        clear_undo_log()
        console.print("[green]Undo log cleared.[/green]")
        return

    entries = load_undo_log(limit=limit)
    if not entries:
        console.print("[yellow]No actions in undo log.[/yellow]")
        return

    if restore is not None:
        idx = restore - 1
        if idx < 0 or idx >= len(entries):
            console.print(f"[red]Invalid index. Range: 1-{len(entries)}[/red]")
            return
        entry = entries[idx]
        if undo_trash(entry):
            console.print(f"[green]Restored:[/green] {entry.source}")
        else:
            console.print(f"[red]Failed to restore:[/red] {entry.source}")
        return

    table = Table(title="Recent Actions (undo log)")
    table.add_column("#", justify="right")
    table.add_column("Timestamp")
    table.add_column("Action")
    table.add_column("Source")

    for idx, entry in enumerate(entries, 1):
        table.add_row(
            str(idx),
            entry.timestamp[:19],
            entry.action,
            entry.source,
        )

    console.print(table)
    console.print(
        "\nTo restore: [bold]osa undo --restore N[/bold]"
    )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@app.command("config")
def config_cmd(
    show: bool = typer.Option(False, help="Show current config."),
    key: str | None = typer.Option(None, help="Config key to get/set."),
    value: str | None = typer.Option(None, help="Value to set."),
    reset: bool = typer.Option(False, help="Reset config to defaults."),
) -> None:
    """View or modify persistent configuration."""
    from osx_system_agent.config import (
        get_value,
        load_config,
        reset_config,
        set_value,
    )

    if reset:
        cfg = reset_config()
        console.print("[green]Config reset to defaults.[/green]")
        console.print_json(data=cfg)
        return

    if key and value is not None:
        # Try to parse JSON values (for lists, booleans, numbers)
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed = value
        cfg = set_value(key, parsed)
        console.print(f"[green]Set {key} = {parsed!r}[/green]")
        return

    if key:
        val = get_value(key)
        console.print(f"{key} = {val!r}")
        return

    # Default: show all config
    cfg = load_config()
    console.print_json(data=cfg)


# ---------------------------------------------------------------------------
# Clean brew
# ---------------------------------------------------------------------------


@clean_app.command("brew")
def clean_brew_cmd(
    dry_run: bool = typer.Option(
        True, help="Preview only; pass --no-dry-run to execute."
    ),
    cleanup: bool = typer.Option(
        True, help="Also run brew cleanup to remove old versions."
    ),
) -> None:
    """Upgrade outdated Homebrew packages. Use --no-dry-run to execute."""
    from osx_system_agent.clean.brew import brew_cleanup, upgrade_outdated

    result = upgrade_outdated(dry_run=dry_run)
    mode = (
        "[bold yellow]DRY RUN[/bold yellow]"
        if dry_run
        else "[bold red]LIVE[/bold red]"
    )

    if not result.upgraded:
        console.print("[green]All Homebrew packages are up to date.[/green]")
        return

    table = Table(title=f"Brew Upgrade ({mode})")
    table.add_column("Package")
    table.add_column("Version")
    table.add_column("Type")

    for pkg in result.upgraded:
        table.add_row(
            pkg.name,
            pkg.version,
            "cask" if pkg.is_cask else "formula",
        )

    console.print(table)

    if result.failed:
        console.print(f"\n[red]{len(result.failed)} failures:[/red]")
        for msg in result.failed:
            console.print(f"  {msg}")

    if cleanup and not dry_run:
        console.print("\nRunning brew cleanup...")
        brew_cleanup(dry_run=False)
        console.print("[green]Cleanup complete.[/green]")
    elif cleanup and dry_run:
        console.print("\n[yellow]Pass --no-dry-run to execute upgrades.[/yellow]")


# ---------------------------------------------------------------------------
# Scan Xcode
# ---------------------------------------------------------------------------


@scan_app.command("xcode")
def scan_xcode_cmd() -> None:
    """Audit Xcode disk usage (DerivedData, Archives, Simulators)."""
    from osx_system_agent.scanners.xcode import scan_xcode

    audit = scan_xcode()

    if not audit.xcode_installed:
        console.print("[yellow]Xcode not detected.[/yellow]")
        return

    # Derived Data
    if audit.derived_data:
        dd_table = Table(
            title=f"DerivedData ({bytes_to_human(audit.derived_data_total)})"
        )
        dd_table.add_column("Project")
        dd_table.add_column("Size", justify="right")
        for proj in audit.derived_data[:20]:
            dd_table.add_row(proj.name, bytes_to_human(proj.size))
        console.print(dd_table)

    # Archives
    if audit.archives:
        arch_table = Table(
            title=f"Archives ({bytes_to_human(audit.archives_total)})"
        )
        arch_table.add_column("Name")
        arch_table.add_column("Size", justify="right")
        for arch in audit.archives[:15]:
            arch_table.add_row(arch.name, bytes_to_human(arch.size))
        console.print(arch_table)

    # Simulators
    if audit.simulators or audit.simulators_unavailable:
        sim_table = Table(title="Simulators")
        sim_table.add_column("Name")
        sim_table.add_column("Runtime")
        sim_table.add_column("State")
        sim_table.add_column("Size", justify="right")
        sim_table.add_column("Available")
        for sim in audit.simulators[:10]:
            sim_table.add_row(
                sim.name, sim.runtime, sim.state,
                bytes_to_human(sim.data_size), "yes",
            )
        for sim in audit.simulators_unavailable[:10]:
            sim_table.add_row(
                sim.name, sim.runtime, sim.state,
                bytes_to_human(sim.data_size), "[red]no[/red]",
            )
        console.print(sim_table)
        if audit.simulators_unavailable:
            console.print(
                f"\n[yellow]{len(audit.simulators_unavailable)} "
                "unavailable simulators — clean with "
                "'osa clean xcode --sims'[/yellow]"
            )

    console.print(
        f"\nTotal: DerivedData={bytes_to_human(audit.derived_data_total)}"
        f", Archives={bytes_to_human(audit.archives_total)}"
    )


# ---------------------------------------------------------------------------
# Scan Docker
# ---------------------------------------------------------------------------


@scan_app.command("docker")
def scan_docker_cmd() -> None:
    """Audit Docker images, containers, and volumes."""
    from osx_system_agent.scanners.docker import scan_docker

    audit = scan_docker()

    if not audit.installed:
        console.print("[yellow]Docker not installed.[/yellow]")
        return

    if not audit.running:
        console.print("[yellow]Docker not running.[/yellow]")
        return

    # Images
    if audit.images:
        img_table = Table(title=f"Docker Images ({len(audit.images)})")
        img_table.add_column("Repository")
        img_table.add_column("Tag")
        img_table.add_column("Size", justify="right")
        for img in audit.images[:20]:
            img_table.add_row(
                img.repository, img.tag, bytes_to_human(img.size),
            )
        console.print(img_table)

    # Containers
    if audit.containers:
        ctr_table = Table(title=f"Containers ({len(audit.containers)})")
        ctr_table.add_column("Name")
        ctr_table.add_column("Image")
        ctr_table.add_column("State")
        ctr_table.add_column("Status")
        for ctr in audit.containers[:20]:
            style = "green" if ctr.state == "running" else "dim"
            ctr_table.add_row(
                ctr.name, ctr.image, ctr.state,
                ctr.status[:40], style=style,
            )
        console.print(ctr_table)

    # Volumes
    if audit.volumes:
        console.print(f"Volumes: {len(audit.volumes)}")

    # Disk usage
    if audit.disk_usage:
        console.print("\n[bold]Docker disk usage:[/bold]")
        for dtype, size in audit.disk_usage.items():
            console.print(f"  {dtype}: {bytes_to_human(size)}")


# ---------------------------------------------------------------------------
# Scan Google Drive
# ---------------------------------------------------------------------------


@scan_app.command("google-drive")
def scan_google_drive_cmd(
    api: bool = typer.Option(
        False, "--api", help="Use Google Drive API instead of local DriveFS.",
    ),
    credentials: str | None = typer.Option(
        None, "--credentials", help="Path to OAuth credentials.json.",
    ),
    limit: int = typer.Option(50, help="Number of largest files to show."),
    min_size: str = typer.Option("0", help="Minimum file size (e.g., 1MB, 100KB)."),
    out: str | None = typer.Option(None, help="Output directory for reports."),
) -> None:
    """Audit Google Drive accounts, storage usage, and largest files."""
    from osx_system_agent.scanners.google_drive import (
        scan_google_drive,
        scan_google_drive_api,
    )

    if api:
        creds_path = expand_path(credentials) if credentials else None
        audit = scan_google_drive_api(
            credentials_path=creds_path, limit=limit,
        )
    else:
        min_bytes = parse_size(min_size)
        audit = scan_google_drive(limit=limit, min_size=min_bytes)

    if audit.error and not audit.accounts:
        console.print(f"[yellow]{audit.error}[/yellow]")
        return

    # Quota (API mode)
    if audit.quota:
        console.print(f"\n[bold]Account:[/bold] {audit.quota.email}"
                       f" ({audit.quota.display_name})")
        console.print(
            f"[bold]Storage:[/bold] "
            f"{bytes_to_human(audit.quota.usage)} used"
            f" / {bytes_to_human(audit.quota.limit) if audit.quota.limit else '∞'}"
            f" ({audit.quota.pct_used:.1f}%)"
            if audit.quota.pct_used is not None
            else f"[bold]Storage:[/bold] "
            f"{bytes_to_human(audit.quota.usage)} used (unlimited plan)"
        )
        console.print(
            f"  Drive: {bytes_to_human(audit.quota.usage_in_drive)}"
            f"  |  Trash: {bytes_to_human(audit.quota.usage_in_trash)}"
        )
        console.print()

    # Accounts (local mode)
    if not audit.api_mode and audit.accounts:
        acct_table = Table(title=f"Google Drive Accounts ({len(audit.accounts)})")
        acct_table.add_column("Email")
        acct_table.add_column("My Drive")
        acct_table.add_column("Shared Drives")
        for acct in audit.accounts:
            acct_table.add_row(
                acct.email,
                "Yes" if acct.my_drive_path else "No",
                "Yes" if acct.shared_drives_path else "No",
            )
        console.print(acct_table)

    # Shared drives (API mode)
    if audit.shared_drives:
        sd_table = Table(title=f"Shared Drives ({len(audit.shared_drives)})")
        sd_table.add_column("Name")
        sd_table.add_column("Drive ID")
        for sd in audit.shared_drives:
            sd_table.add_row(sd.name, sd.drive_id)
        console.print(sd_table)

    # Storage summary (local mode)
    if audit.storage:
        stor_table = Table(title="Storage by Location")
        stor_table.add_column("Location")
        stor_table.add_column("Files", justify="right")
        stor_table.add_column("Size", justify="right")
        for s in audit.storage:
            stor_table.add_row(
                s.location,
                f"{s.total_files:,}",
                bytes_to_human(s.total_size),
            )
        stor_table.add_row(
            "[bold]Total[/bold]",
            f"[bold]{audit.total_files:,}[/bold]",
            f"[bold]{bytes_to_human(audit.total_size)}[/bold]",
        )
        console.print(stor_table)

    # Categories
    if audit.categories:
        cat_table = Table(title="Files by Category")
        cat_table.add_column("Category")
        cat_table.add_column("Files", justify="right")
        cat_table.add_column("Size", justify="right")
        sorted_cats = sorted(
            audit.categories.items(),
            key=lambda x: x[1]["size"],
            reverse=True,
        )
        for cat, stats in sorted_cats:
            cat_table.add_row(
                cat, f"{stats['count']:,}", bytes_to_human(stats["size"]),
            )
        console.print(cat_table)

    # Largest files
    if audit.largest_files:
        file_table = Table(
            title=f"Largest Files (top {min(limit, len(audit.largest_files))})"
        )
        file_table.add_column("Name")
        file_table.add_column("Size", justify="right")
        file_table.add_column("Category")
        file_table.add_column("Modified")
        if audit.api_mode:
            file_table.add_column("Shared")
            file_table.add_column("Owner")
        else:
            file_table.add_column("Cloud-only")
        for f in audit.largest_files[:limit]:
            style = "red" if f.size > 100 * 1024 * 1024 else ""
            if audit.api_mode:
                file_table.add_row(
                    f.name[:60],
                    bytes_to_human(f.size),
                    f.category,
                    unix_to_iso(f.mtime)[:10] if f.mtime else "",
                    "Yes" if f.shared else "",
                    (f.owner or "")[:30],
                    style=style,
                )
            else:
                file_table.add_row(
                    f.name[:60],
                    bytes_to_human(f.size),
                    f.category,
                    unix_to_iso(f.mtime)[:10],
                    "Yes" if f.cloud_only else "",
                    style=style,
                )
        console.print(file_table)

    # Trashed files (API mode)
    if audit.trashed_files:
        trash_size = sum(f.size for f in audit.trashed_files)
        console.print(
            f"\n[yellow]Trash:[/yellow] {len(audit.trashed_files)} files"
            f" using {bytes_to_human(trash_size)}"
            " — empty trash to reclaim space"
        )

    # Export
    outdir = _default_outdir(out)
    rows = [
        {
            "name": f.name,
            "path": str(f.path),
            "size": f.size,
            "size_human": bytes_to_human(f.size),
            "category": f.category,
            "mtime": unix_to_iso(f.mtime) if f.mtime else "",
            "cloud_only": f.cloud_only,
            "shared": f.shared,
            "owner": f.owner or "",
            "file_id": f.file_id or "",
        }
        for f in audit.largest_files
    ]
    stamp = _timestamp()
    json_path = write_json(rows, outdir / f"google-drive-{stamp}.json")
    csv_path = write_csv(rows, outdir / f"google-drive-{stamp}.csv")
    console.print(f"\nJSON → {json_path}")
    console.print(f"CSV  → {csv_path}")


# ---------------------------------------------------------------------------
# Clean Xcode
# ---------------------------------------------------------------------------


@clean_app.command("xcode")
def clean_xcode_cmd(
    derived: bool = typer.Option(
        True, help="Clean DerivedData."
    ),
    archives: bool = typer.Option(
        False, help="Also clean Archives."
    ),
    sims: bool = typer.Option(
        False, "--sims", help="Remove unavailable simulators."
    ),
    dry_run: bool = typer.Option(
        True, help="Preview only; pass --no-dry-run to execute."
    ),
) -> None:
    """Clean Xcode DerivedData, Archives, and Simulators."""
    from osx_system_agent.clean.xcode import clean_xcode

    result = clean_xcode(
        derived_data=derived,
        archives=archives,
        unavailable_sims=sims,
        dry_run=dry_run,
    )

    mode = (
        "[bold yellow]DRY RUN[/bold yellow]"
        if dry_run
        else "[bold red]LIVE[/bold red]"
    )

    table = Table(title=f"Xcode Cleanup ({mode})")
    table.add_column("Category")
    table.add_column("Items", justify="right")
    table.add_column("Size", justify="right")

    if result.derived_data_count:
        table.add_row(
            "DerivedData",
            str(result.derived_data_count),
            bytes_to_human(result.derived_data_freed),
        )
    if result.archives_count:
        table.add_row(
            "Archives",
            str(result.archives_count),
            bytes_to_human(result.archives_freed),
        )
    if result.simulators_removed:
        table.add_row(
            "Unavailable Sims",
            str(result.simulators_removed),
            "",
        )

    console.print(table)

    total = result.derived_data_freed + result.archives_freed
    console.print(f"Total freed: {bytes_to_human(total)}")

    if result.errors:
        for err in result.errors:
            console.print(f"[red]{err}[/red]")

    if dry_run:
        console.print(
            "\n[yellow]Pass --no-dry-run to execute cleanup.[/yellow]"
        )


# ---------------------------------------------------------------------------
# Export (markdown report)
# ---------------------------------------------------------------------------


@app.command("export")
def export_cmd(
    fmt: str = typer.Option("markdown", help="Export format (markdown, json, html)."),
    out: str | None = typer.Option(None, help="Output directory."),
    path: str | None = typer.Option(
        None, help="Optional path to scan for junk files."
    ),
    scan_json: str | None = typer.Option(
        None, "--scan-json", help="Path to user-files-scan.json for dedup report."
    ),
) -> None:
    """Export a system health report in markdown, JSON, or HTML format."""
    outdir = _default_outdir(out)
    scan_path = expand_path(path) if path else None

    if scan_json:
        from osx_system_agent.reports.user_files_html import generate_user_files_report

        report_path = generate_user_files_report(Path(scan_json), outdir)
    elif fmt == "markdown" or fmt == "md":
        from osx_system_agent.reports.markdown import generate_markdown_report

        report_path = generate_markdown_report(outdir, scan_path=scan_path)
    elif fmt == "html":
        from osx_system_agent.reports.html import generate_html_report

        report_path = generate_html_report(outdir, scan_path=scan_path)
    else:
        from osx_system_agent.reports.consolidated import generate_report

        report_path = generate_report(outdir, scan_path=scan_path)

    console.print(f"[bold green]Report exported:[/bold green] {report_path}")


# ---------------------------------------------------------------------------
# Scan large files
# ---------------------------------------------------------------------------


@scan_app.command("large-files")
def scan_large_files_cmd(
    path: str = typer.Option("~", help="Root path to scan."),
    limit: int = typer.Option(50, help="Number of files to show."),
    min_size: str = typer.Option("100MB", help="Minimum file size."),
    out: str | None = typer.Option(None, help="Output directory for reports."),
) -> None:
    """Find the largest individual files on disk."""
    from osx_system_agent.scanners.large_files import scan_large_files

    root = expand_path(path)
    min_bytes = parse_size(min_size)
    results = scan_large_files(
        roots=[root], limit=limit, min_size=min_bytes,
    )
    outdir = _default_outdir(out)

    table = Table(title=f"Largest Files ({len(results)} found)")
    table.add_column("#", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Modified")
    table.add_column("Path")

    for idx, f in enumerate(results, 1):
        style = "red" if f.size > 1024**3 else ""
        table.add_row(
            str(idx),
            bytes_to_human(f.size),
            unix_to_iso(f.mtime),
            str(f.path),
            style=style,
        )

    console.print(table)

    rows = [
        {
            "path": str(f.path),
            "size": f.size,
            "size_human": bytes_to_human(f.size),
            "mtime": unix_to_iso(f.mtime),
        }
        for f in results
    ]
    stamp = _timestamp()
    json_path = write_json(rows, outdir / f"large-files-{stamp}.json")
    csv_path = write_csv(rows, outdir / f"large-files-{stamp}.csv")
    console.print(f"JSON: {json_path}")
    console.print(f"CSV: {csv_path}")


# ---------------------------------------------------------------------------
# Clean Docker
# ---------------------------------------------------------------------------


@clean_app.command("docker")
def clean_docker_cmd(
    all_images: bool = typer.Option(
        False, "--all", help="Remove all unused images, not just dangling."
    ),
    volumes: bool = typer.Option(
        False, help="Also prune volumes."
    ),
    dry_run: bool = typer.Option(
        True, help="Preview only; pass --no-dry-run to execute."
    ),
) -> None:
    """Run Docker system prune. Use --no-dry-run to execute."""
    from osx_system_agent.clean.docker import docker_prune

    result = docker_prune(
        all_images=all_images, volumes=volumes, dry_run=dry_run,
    )

    if result.error:
        console.print(f"[red]{result.error}[/red]")
        return

    mode = (
        "[bold yellow]DRY RUN[/bold yellow]"
        if dry_run
        else "[bold red]LIVE[/bold red]"
    )
    console.print(f"Docker Prune ({mode})")
    if result.space_reclaimed:
        console.print(result.space_reclaimed)

    if dry_run:
        console.print(
            "\n[yellow]Pass --no-dry-run to execute prune.[/yellow]"
        )


if __name__ == "__main__":
    app()


