from __future__ import annotations

import base64
from datetime import UTC, datetime
from pathlib import Path

from osx_system_agent.log import get_logger
from osx_system_agent.scanners.caches import scan_caches
from osx_system_agent.scanners.disk_hogs import scan_disk_hogs
from osx_system_agent.scanners.launch_agents import scan_launch_agents
from osx_system_agent.scanners.network import scan_network
from osx_system_agent.scanners.security import scan_security
from osx_system_agent.system.activity import get_system_status
from osx_system_agent.utils.human import bytes_to_human
from osx_system_agent.utils.paths import ensure_dir

log = get_logger("reports.html")

# Brush Cyber brand logo — embedded as data URI
_LOGO_PATH = (
    Path.home()
    / "Library/CloudStorage/OneDrive-SharedLibraries-BrushCyber"
    / "Sales and Marketing - Documents/General/_Brand_Kit/-working"
    / "long-logo-brush-cyber.png"
)


def _logo_data_uri() -> str:
    """Return a base64 data URI for the brand logo, or empty string."""
    if _LOGO_PATH.exists():
        data = base64.b64encode(_LOGO_PATH.read_bytes()).decode()
        return f"data:image/png;base64,{data}"
    return ""


# ---------------------------------------------------------------------------
# Brand-themed HTML shell
# ---------------------------------------------------------------------------

_HTML_HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700&family=Poppins:wght@300;400;500&display=swap"
      rel="stylesheet">
<style>
:root {{
  --bc-indigo:       #413BBE;
  --bc-deep-navy:    #211A37;
  --bc-magenta:      #D447B2;
  --bc-sky-blue:     #47B6EE;
  --bc-crimson:      #DB0A38;
  --bc-lavender:     #6D67CE;
  --bc-muted-purple: #595477;
  --bc-deep-purple:  #4A3E6A;
  --bc-rich-magenta: #A12D87;
  --bc-deep-red:     #AA0830;
  --bc-white:        #FFFFFF;
  --bc-light-gray:   #F4F3F8;
  --bc-medium-gray:  #9994B0;
  --bc-dark-gray:    #2C2640;
  --bc-black:        #0D0A14;
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  font-family: 'Poppins', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 0.875rem;
  line-height: 1.5;
  color: var(--bc-deep-navy);
  background: var(--bc-light-gray);
}}

.report-wrapper {{
  max-width: 960px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}}

/* Header */
.report-header {{
  background: var(--bc-deep-navy);
  border-radius: 12px;
  padding: 2rem 2.5rem;
  margin-bottom: 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}}
.report-header img {{
  height: 36px;
}}
.report-header .meta {{
  text-align: right;
  color: var(--bc-medium-gray);
  font-size: 0.75rem;
  font-weight: 300;
}}
.report-header .meta .title {{
  font-family: 'Montserrat', sans-serif;
  font-weight: 700;
  font-size: 1.25rem;
  color: var(--bc-white);
  margin-bottom: 0.25rem;
}}

/* Sections */
.section {{
  background: var(--bc-white);
  border-radius: 12px;
  padding: 1.5rem 2rem;
  margin-bottom: 1.25rem;
  box-shadow: 0 1px 3px rgba(33,26,55,0.06);
}}
.section h2 {{
  font-family: 'Montserrat', sans-serif;
  font-weight: 600;
  font-size: 1.1rem;
  color: var(--bc-indigo);
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid var(--bc-light-gray);
}}

/* Stat cards */
.stat-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  margin-bottom: 0.5rem;
}}
.stat-card {{
  background: var(--bc-light-gray);
  border-radius: 8px;
  padding: 1rem 1.25rem;
  text-align: center;
}}
.stat-card .label {{
  font-size: 0.7rem;
  font-weight: 500;
  color: var(--bc-muted-purple);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}
.stat-card .value {{
  font-family: 'Montserrat', sans-serif;
  font-weight: 700;
  font-size: 1.5rem;
  color: var(--bc-deep-navy);
  margin-top: 0.25rem;
}}
.stat-card .sub {{
  font-size: 0.7rem;
  color: var(--bc-muted-purple);
  font-weight: 300;
}}

/* Tables */
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}}
th {{
  text-align: left;
  font-family: 'Montserrat', sans-serif;
  font-weight: 600;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--bc-muted-purple);
  padding: 0.6rem 0.75rem;
  border-bottom: 2px solid var(--bc-light-gray);
}}
td {{
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--bc-light-gray);
  vertical-align: top;
}}
tr:last-child td {{ border-bottom: none; }}
td.size {{ text-align: right; font-family: 'Montserrat', sans-serif; font-weight: 500; }}
td.num {{ text-align: right; }}
td.path {{ word-break: break-all; color: var(--bc-muted-purple); font-size: 0.75rem; }}

/* Badges */
.badge {{
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.65rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}}
.badge-pass {{ background: #E8F5E9; color: #2E7D32; }}
.badge-warn {{ background: #FFF8E1; color: #F57F17; }}
.badge-critical {{ background: #FFEBEE; color: var(--bc-crimson); }}
.badge-unknown {{ background: var(--bc-light-gray); color: var(--bc-muted-purple); }}
.badge-ok {{ background: #E3F2FD; color: #1565C0; }}
.badge-fail {{ background: #FFEBEE; color: var(--bc-crimson); }}

/* Footer */
.report-footer {{
  text-align: center;
  padding: 1.5rem 0;
  font-size: 0.7rem;
  color: var(--bc-muted-purple);
  font-weight: 300;
}}
.report-footer a {{
  color: var(--bc-indigo);
  text-decoration: none;
}}
</style>
</head>
<body>
<div class="report-wrapper">
"""

_HTML_TAIL = """\
<div class="report-footer">
  Generated by <strong>osx-system-agent</strong> &mdash; Brush Cyber
</div>
</div>
</body>
</html>
"""


def _severity_badge(severity: str) -> str:
    cls = {"ok": "badge-pass", "warn": "badge-warn", "critical": "badge-critical"}
    return f'<span class="badge {cls.get(severity, "badge-unknown")}">{severity}</span>'


def _status_badge(enabled: bool | None) -> str:
    if enabled is True:
        return '<span class="badge badge-pass">PASS</span>'
    if enabled is False:
        return '<span class="badge badge-warn">FAIL</span>'
    return '<span class="badge badge-unknown">UNKNOWN</span>'


def _conn_badge(success: bool) -> str:
    if success:
        return '<span class="badge badge-ok">OK</span>'
    return '<span class="badge badge-fail">FAIL</span>'


def _esc(text: str) -> str:
    """Minimal HTML escaping."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_html_report(
    output_dir: Path,
    scan_path: Path | None = None,
) -> Path:
    """Generate a branded HTML system health report."""
    timestamp = datetime.now(tz=UTC).isoformat(timespec="seconds")
    local_time = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    parts: list[str] = []

    parts.append(_HTML_HEAD.format(title="System Health Report — Brush Cyber"))

    # Header
    logo_uri = _logo_data_uri()
    logo_tag = f'<img src="{logo_uri}" alt="Brush Cyber">' if logo_uri else ""
    parts.append(f"""
<div class="report-header">
  {logo_tag}
  <div class="meta">
    <div class="title">System Health Report</div>
    {local_time}<br>{timestamp}
  </div>
</div>
""")

    # ── System Overview ──
    sys_status = get_system_status()
    disk_pct = (
        sys_status.disk_used / sys_status.disk_total * 100
        if sys_status.disk_total > 0 else 0
    )
    mem_pct = (
        sys_status.memory_used / sys_status.memory_total * 100
        if sys_status.memory_total > 0 else 0
    )
    bat_str = ""
    if sys_status.battery:
        plug = "Plugged In" if sys_status.battery.power_plugged else "Battery"
        pct = (
            f"{sys_status.battery.percent:.0f}%"
            if sys_status.battery.percent is not None else "N/A"
        )
        bat_str = f"""
    <div class="stat-card">
      <div class="label">Battery</div>
      <div class="value">{pct}</div>
      <div class="sub">{plug}</div>
    </div>"""

    parts.append(f"""
<div class="section">
  <h2>System Overview</h2>
  <div class="stat-grid">
    <div class="stat-card">
      <div class="label">CPU</div>
      <div class="value">{sys_status.cpu_percent:.1f}%</div>
    </div>
    <div class="stat-card">
      <div class="label">Memory</div>
      <div class="value">{bytes_to_human(sys_status.memory_used)}</div>
      <div class="sub">of {bytes_to_human(sys_status.memory_total)} ({mem_pct:.0f}%)</div>
    </div>
    <div class="stat-card">
      <div class="label">Disk Used</div>
      <div class="value">{bytes_to_human(sys_status.disk_used)}</div>
      <div class="sub">of {bytes_to_human(sys_status.disk_total)} ({disk_pct:.0f}%)</div>
    </div>
    <div class="stat-card">
      <div class="label">Disk Free</div>
      <div class="value">{bytes_to_human(sys_status.disk_free)}</div>
    </div>{bat_str}
  </div>
</div>
""")

    # ── Security Posture ──
    sec = scan_security()
    sec_rows = []
    for check in sec.checks:
        sec_rows.append(
            f"<tr><td>{_esc(check.name)}</td>"
            f"<td>{_status_badge(check.enabled)}</td>"
            f"<td>{_severity_badge(check.severity)}</td>"
            f"<td class='path'>{_esc(check.status[:100])}</td></tr>"
        )
    critical = sum(1 for c in sec.checks if c.severity == "critical")
    warn = sum(1 for c in sec.checks if c.severity == "warn")
    ok = sum(1 for c in sec.checks if c.severity == "ok")

    parts.append(f"""
<div class="section">
  <h2>Security Posture</h2>
  <div class="stat-grid">
    <div class="stat-card">
      <div class="label">Passed</div>
      <div class="value" style="color:#2E7D32">{ok}</div>
    </div>
    <div class="stat-card">
      <div class="label">Warnings</div>
      <div class="value" style="color:#F57F17">{warn}</div>
    </div>
    <div class="stat-card">
      <div class="label">Critical</div>
      <div class="value" style="color:var(--bc-crimson)">{critical}</div>
    </div>
  </div>
  <table>
    <thead><tr><th>Check</th><th>Status</th><th>Severity</th><th>Detail</th></tr></thead>
    <tbody>{"".join(sec_rows)}</tbody>
  </table>
</div>
""")

    # ── Network ──
    net = scan_network()
    iface_rows = []
    for iface in net.interfaces:
        style = "" if iface.status == "active" else ' style="opacity:0.5"'
        iface_rows.append(
            f"<tr{style}><td>{_esc(iface.service_name)}</td>"
            f"<td>{_esc(iface.name)}</td>"
            f"<td>{_esc(iface.ip_address or '-')}</td>"
            f"<td>{_esc(iface.router or '-')}</td>"
            f"<td>{_esc(iface.status)}</td></tr>"
        )

    conn_rows = []
    for t in net.connectivity:
        latency = f"{t.latency_ms:.1f}ms" if t.latency_ms else "-"
        conn_rows.append(
            f"<tr><td>{_esc(t.target)}</td>"
            f"<td>{_conn_badge(t.success)}</td>"
            f"<td class='num'>{latency}</td></tr>"
        )

    port_rows = []
    for p in net.listening_ports[:25]:
        port_rows.append(
            f"<tr><td class='num'>{p.port}</td>"
            f"<td>{_esc(p.address)}</td>"
            f"<td>{_esc(p.process or '-')}</td>"
            f"<td class='num'>{p.pid or '-'}</td></tr>"
        )
    if len(net.listening_ports) > 25:
        port_rows.append(
            f"<tr><td colspan='4' class='path'>"
            f"+{len(net.listening_ports) - 25} more</td></tr>"
        )

    dns_servers = ", ".join(net.dns.servers) if net.dns else "-"
    vpn_tag = (
        ' <span class="badge badge-warn">VPN</span>' if net.vpn_active else ""
    )
    ssid_tag = (
        f" &mdash; SSID: {_esc(net.wifi_ssid)}" if net.wifi_ssid else ""
    )

    parts.append(f"""
<div class="section">
  <h2>Network{vpn_tag}{ssid_tag}</h2>

  <h3 style="font-family:'Montserrat',sans-serif;font-weight:500;font-size:0.85rem;
             color:var(--bc-deep-navy);margin:0.75rem 0 0.5rem">Connectivity</h3>
  <table>
    <thead><tr><th>Target</th><th>Status</th><th>Latency</th></tr></thead>
    <tbody>{"".join(conn_rows)}</tbody>
  </table>

  <h3 style="font-family:'Montserrat',sans-serif;font-weight:500;font-size:0.85rem;
             color:var(--bc-deep-navy);margin:1rem 0 0.5rem">DNS: {_esc(dns_servers)}</h3>

  <h3 style="font-family:'Montserrat',sans-serif;font-weight:500;font-size:0.85rem;
             color:var(--bc-deep-navy);margin:1rem 0 0.5rem">Interfaces</h3>
  <table>
    <thead><tr><th>Service</th><th>Interface</th><th>IP</th><th>Router</th><th>Status</th></tr></thead>
    <tbody>{"".join(iface_rows)}</tbody>
  </table>

  <h3 style="font-family:'Montserrat',sans-serif;font-weight:500;font-size:0.85rem;
             color:var(--bc-deep-navy);margin:1rem 0 0.5rem">
    Listening Ports ({len(net.listening_ports)})</h3>
  <table>
    <thead><tr><th>Port</th><th>Address</th><th>Process</th><th>PID</th></tr></thead>
    <tbody>{"".join(port_rows)}</tbody>
  </table>
</div>
""")

    # ── Disk Hogs ──
    hogs = scan_disk_hogs(min_size=500 * 1024 * 1024)
    if hogs:
        hog_rows = []
        for d in hogs[:15]:
            hog_rows.append(
                f"<tr><td class='path'>{_esc(str(d.path))}</td>"
                f"<td class='size'>{bytes_to_human(d.size)}</td>"
                f"<td class='num'>{d.file_count:,}</td></tr>"
            )
        parts.append(f"""
<div class="section">
  <h2>Disk Hogs (&gt;500MB)</h2>
  <table>
    <thead><tr><th>Directory</th><th>Size</th><th>Files</th></tr></thead>
    <tbody>{"".join(hog_rows)}</tbody>
  </table>
</div>
""")

    # ── Caches ──
    caches = scan_caches(min_size=50 * 1024 * 1024)
    if caches:
        total_cache = sum(c.size for c in caches)
        cache_rows = []
        for c in caches:
            cache_rows.append(
                f"<tr><td>{_esc(c.category)}</td>"
                f"<td class='size'>{bytes_to_human(c.size)}</td>"
                f"<td class='num'>{c.file_count:,}</td></tr>"
            )
        parts.append(f"""
<div class="section">
  <h2>Caches ({bytes_to_human(total_cache)} total)</h2>
  <table>
    <thead><tr><th>Category</th><th>Size</th><th>Files</th></tr></thead>
    <tbody>{"".join(cache_rows)}</tbody>
  </table>
</div>
""")

    # ── Launch Agents ──
    agents = scan_launch_agents(include_apple=False)
    run_at_load = [a for a in agents if a.run_at_load and not a.disabled]
    if agents:
        agent_rows = []
        for a in run_at_load[:25]:
            agent_rows.append(
                f"<tr><td>{_esc(a.label)}</td>"
                f"<td>{_esc(a.scope)}</td>"
                f"<td class='path'>{_esc(a.program[:80])}</td></tr>"
            )
        parts.append(f"""
<div class="section">
  <h2>Launch Agents ({len(agents)} total, {len(run_at_load)} at boot)</h2>
  <table>
    <thead><tr><th>Label</th><th>Scope</th><th>Program</th></tr></thead>
    <tbody>{"".join(agent_rows)}</tbody>
  </table>
</div>
""")

    parts.append(_HTML_TAIL)

    # Write
    ensure_dir(output_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = output_dir / f"system-report-{stamp}.html"
    report_path.write_text("".join(parts))

    log.info("HTML report written to %s", report_path)
    return report_path
