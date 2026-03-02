"""Generate a branded HTML report from a user-files-scan JSON."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from osx_system_agent.reports.html import _HTML_HEAD, _HTML_TAIL, _esc, _logo_data_uri
from osx_system_agent.utils.human import bytes_to_human
from osx_system_agent.utils.paths import ensure_dir

# ---------------------------------------------------------------------------
# Path / label helpers
# ---------------------------------------------------------------------------

_PATH_PREFIXES = (
    "/Users/douglas_brush/Library/CloudStorage/OneDrive-SharedLibraries-BrushCyber/",
    "/Users/douglas_brush/Library/CloudStorage/OneDrive-BrushCyber/",
    "/Users/douglas_brush/Library/CloudStorage/ShareFile-ShareFile",
    "/Users/douglas_brush/Library/CloudStorage/",
    "/Users/douglas_brush/",
)


def _shorten_path(path: str, max_len: int = 100) -> str:
    """Shorten a long path for display, keeping the meaningful tail."""
    short = path
    for prefix in _PATH_PREFIXES:
        if short.startswith(prefix):
            short = "~/" + short[len(prefix):]
            break
    if len(short) <= max_len:
        return short
    return "..." + short[-(max_len - 3):]


def _location_label(loc: str) -> str:
    """Return a friendlier label for a top-level location path."""
    for prefix, label in (
        ("/Users/douglas_brush/Library/CloudStorage", "Cloud Storage"),
        ("/Users/douglas_brush/Pictures", "Pictures"),
        ("/Users/douglas_brush/Documents", "Documents"),
        ("/Users/douglas_brush/Downloads", "Downloads"),
        ("/Users/douglas_brush/Desktop", "Desktop"),
        ("/Users/douglas_brush/Music", "Music"),
        ("/Users/douglas_brush/Movies", "Movies"),
    ):
        if loc == prefix:
            return label
    return loc


def _bar_html(value: float, max_val: float, color: str = "var(--bc-indigo)") -> str:
    pct = min(value / max_val * 100, 100) if max_val > 0 else 0
    return (
        f'<div style="background:var(--bc-light-gray);border-radius:4px;height:8px;'
        f'width:100%;margin-top:4px">'
        f'<div style="background:{color};border-radius:4px;height:8px;'
        f'width:{pct:.1f}%"></div></div>'
    )


def _severity_color(wasted: int) -> str:
    if wasted >= 100 * 1024 * 1024:
        return "var(--bc-crimson)"
    if wasted >= 10 * 1024 * 1024:
        return "#F57F17"
    return "var(--bc-indigo)"


# ---------------------------------------------------------------------------
# Cluster classification
# ---------------------------------------------------------------------------

_CLUSTER_RULES: list[tuple[list[str], str]] = [
    (["Enagic", "ENANAS", "Project Fuji"], "Enagic / Project Fuji"),
    (["Denali"], "Denali (Google Litigation)"),
    (["MKR", "McCormick", "Miers"], "MKR / Miers DFIR"),
    (["Winrock"], "Winrock"),
    (["Granicus"], "Granicus"),
    (["Brand_Kit", "Sales and Marketing"], "Brush Cyber (Sales/Marketing)"),
    (["Brush Cyber - Documents", "Services Development"], "Brush Cyber (Services)"),
    (["Management - Documents"], "Brush Cyber (Management)"),
    (["ShareFile"], "ShareFile Sync"),
]

_CLUSTER_COLORS: dict[str, str] = {
    "Enagic / Project Fuji": "var(--bc-crimson)",
    "Denali (Google Litigation)": "var(--bc-indigo)",
    "MKR / Miers DFIR": "var(--bc-magenta)",
    "Winrock": "var(--bc-sky-blue)",
    "Brush Cyber (Sales/Marketing)": "var(--bc-lavender)",
    "Brush Cyber (Services)": "var(--bc-rich-magenta)",
    "Brush Cyber (Management)": "var(--bc-deep-purple)",
    "ShareFile Sync": "#F57F17",
    "Photos / Pictures": "var(--bc-sky-blue)",
    "Local Documents": "var(--bc-indigo)",
}


def _classify_cluster(group: dict) -> str:
    paths = " ".join(f.get("path", "") + " " + f.get("dir", "") for f in group.get("files", []))
    for keywords, cluster_name in _CLUSTER_RULES:
        if any(kw in paths for kw in keywords):
            return cluster_name
    if any("Pictures" in f.get("path", "") or "Photos" in f.get("path", "")
           for f in group.get("files", [])):
        return "Photos / Pictures"
    if any("Desktop" in f.get("path", "") for f in group.get("files", [])):
        return "Desktop"
    if any("Downloads" in f.get("path", "") for f in group.get("files", [])):
        return "Downloads"
    if any(f.get("path", "").startswith("/Users/douglas_brush/Documents")
           for f in group.get("files", [])):
        return "Local Documents"
    return "Other"


def _location_key(path: str) -> str:
    if "OneDrive-SharedLibraries-BrushCyber" in path:
        return "SharePoint"
    if "OneDrive-BrushCyber" in path:
        return "OneDrive"
    if "ShareFile" in path:
        return "ShareFile"
    if "/Pictures/" in path:
        return "Pictures"
    if "/Desktop/" in path:
        return "Desktop"
    if "/Downloads/" in path:
        return "Downloads"
    if "/Documents/" in path:
        return "Documents"
    if "/Music/" in path:
        return "Music"
    return "Other"


def _build_clusters(groups: list[dict]) -> dict[str, list[dict]]:
    clusters: dict[str, list[dict]] = defaultdict(list)
    for g in groups:
        cluster = _classify_cluster(g)
        clusters[cluster].append(g)
    return dict(sorted(
        clusters.items(),
        key=lambda kv: sum(g["wasted"] for g in kv[1]),
        reverse=True,
    ))


def _build_cross_location(groups: list[dict]) -> list[tuple[str, int, int]]:
    patterns: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "waste": 0})
    for g in groups:
        locs = set()
        for f in g["files"]:
            locs.add(_location_key(f["path"]))
        if len(locs) > 1:
            key = " ↔ ".join(sorted(locs))
            patterns[key]["count"] += 1
            patterns[key]["waste"] += g["wasted"]
    return sorted(
        [(k, v["count"], v["waste"]) for k, v in patterns.items()],
        key=lambda x: x[2],
        reverse=True,
    )


# ---------------------------------------------------------------------------
# CSS additions
# ---------------------------------------------------------------------------

_EXTRA_CSS = """
<style>
.cat-row { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.6rem; }
.cat-label { min-width: 100px; font-weight: 500; font-size: 0.8rem; }
.cat-bar { flex: 1; }
.cat-val { min-width: 80px; text-align: right; font-family: 'Montserrat', sans-serif;
           font-weight: 600; font-size: 0.8rem; }
.cat-count { min-width: 70px; text-align: right; font-size: 0.75rem;
             color: var(--bc-muted-purple); }

.cluster-section {
  background: var(--bc-white);
  border-radius: 12px;
  padding: 1.5rem 2rem;
  margin-bottom: 1.25rem;
  box-shadow: 0 1px 3px rgba(33,26,55,0.06);
}
.cluster-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid var(--bc-light-gray);
}
.cluster-header h2 {
  font-family: 'Montserrat', sans-serif;
  font-weight: 600;
  font-size: 1.1rem;
  margin: 0;
  padding: 0;
  border: none;
}
.cluster-stats {
  font-family: 'Montserrat', sans-serif;
  font-weight: 600;
  font-size: 0.85rem;
  text-align: right;
  white-space: nowrap;
}
.cluster-pattern {
  font-size: 0.75rem;
  color: var(--bc-muted-purple);
  margin-bottom: 1rem;
  line-height: 1.6;
  background: var(--bc-light-gray);
  border-radius: 8px;
  padding: 0.75rem 1rem;
}

.dup-card {
  background: var(--bc-light-gray);
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin-bottom: 0.75rem;
}
.dup-card .dup-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}
.dup-card .dup-name {
  font-family: 'Montserrat', sans-serif;
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--bc-deep-navy);
  word-break: break-all;
}
.dup-card .dup-waste {
  font-family: 'Montserrat', sans-serif;
  font-weight: 700;
  font-size: 0.85rem;
  white-space: nowrap;
  margin-left: 1rem;
}
.dup-card .dup-meta {
  font-size: 0.7rem;
  color: var(--bc-muted-purple);
  margin-bottom: 0.4rem;
}
.dup-card .dup-hash {
  font-size: 0.65rem;
  color: var(--bc-medium-gray);
  font-family: 'Courier New', monospace;
  margin-bottom: 0.3rem;
}
.dup-card .dup-path {
  font-size: 0.72rem;
  color: var(--bc-muted-purple);
  padding: 0.2rem 0;
  word-break: break-all;
  line-height: 1.4;
}
.dup-card .dup-path::before {
  content: "→ ";
  color: var(--bc-medium-gray);
}

.cross-loc-row {
  display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;
}
.cross-loc-label {
  min-width: 200px; font-weight: 500; font-size: 0.8rem;
}
.cross-loc-val {
  min-width: 80px; text-align: right; font-family: 'Montserrat', sans-serif;
  font-weight: 600; font-size: 0.8rem;
}
.cross-loc-count {
  font-size: 0.75rem; color: var(--bc-muted-purple);
}

.verification-banner {
  background: linear-gradient(135deg, #E8F5E9 0%, #C8E6C9 100%);
  border-radius: 8px;
  padding: 0.75rem 1.25rem;
  margin-bottom: 1.25rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.8rem;
  color: #2E7D32;
}
.verification-banner .v-icon {
  font-size: 1.2rem;
}
.verification-banner .v-detail {
  font-size: 0.7rem;
  color: #558B2F;
}

.remediation-box {
  background: linear-gradient(135deg, var(--bc-deep-navy) 0%, var(--bc-deep-purple) 100%);
  border-radius: 12px;
  padding: 1.5rem 2rem;
  color: var(--bc-white);
  margin-bottom: 1.25rem;
}
.remediation-box h2 {
  font-family: 'Montserrat', sans-serif;
  font-weight: 600;
  font-size: 1.1rem;
  color: var(--bc-white) !important;
  border-bottom-color: var(--bc-deep-purple) !important;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid var(--bc-deep-purple);
}
.remediation-box .rec {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.6rem;
  align-items: flex-start;
}
.remediation-box .rec-num {
  background: var(--bc-indigo);
  color: var(--bc-white);
  border-radius: 50%;
  width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  font-family: 'Montserrat', sans-serif;
  font-weight: 700; font-size: 0.7rem; flex-shrink: 0;
}
.remediation-box .rec-text {
  font-size: 0.8rem;
  line-height: 1.5;
}
.remediation-box .rec-text strong {
  color: var(--bc-sky-blue);
}
</style>
"""

# ---------------------------------------------------------------------------
# Cluster description blurbs
# ---------------------------------------------------------------------------

_CLUSTER_DESCRIPTIONS: dict[str, str] = {
    "Enagic / Project Fuji": (
        "Synology FileInventory CSVs duplicated across OneDrive personal, Power Query uploads, "
        "and SharePoint Enagic channel. MES_Output.zip nested in Takeone subfolder. "
        "Winrock presentations mirrored to ShareFile."
    ),
    "Denali (Google Litigation)": (
        "Court filings cross-posted between Parties Correspondence (Brown &amp; Calhoun), "
        "Case Filings, and Special Master Workstreams. Same SEALED exhibits in 2-4 locations. "
        "<em>Retain originals in Case Filings; remove copies from "
        "correspondence Working folders.</em>"
    ),
    "MKR / Miers DFIR": (
        "Discord warrant return attachments duplicated between <code>03_DFIR/From Seth</code> "
        "and <code>00_Discovery/_received</code>. Timeline CSVs in both DFIR analysis and "
        "RawExports. Same content, two extraction paths."
    ),
    "Photos / Pictures": (
        "Two sub-patterns: (1) Job photos <code>IMG_75xx.JPG</code> triplicated across "
        "<code>_DB_FILE</code>, <code>_old/Pictures</code>, and "
        "<code>Rennovations/_DB_FILE</code>. "
        "(2) Apple Photos Library internal dupes (originals vs renders vs backdrop descriptors)."
    ),
    "Local Documents": (
        "<code>_DB_FILE</code> directory mirrored into "
        "<code>_Finances/01_House/Rennovations</code>. "
        "Entra directory sync reports with multiple timestamped runs. "
        "Prowler docs images quadruplicated across doc restructuring. "
        "Tax forms in parallel <code>02_Taxes/</code> and <code>02_Taxes/Taxes/</code> folders."
    ),
    "Brush Cyber (Sales/Marketing)": (
        "Presentations and CVs duplicated between Attachments folder and canonical "
        "Sales &amp; Marketing paths. Industry reports in multiple category folders. "
        "Website backup contains quadruplicated font assets."
    ),
    "Winrock": (
        "NIST publications and proposals duplicated between ShareFile shared folders "
        "and Brush Cyber Services Development library. "
        "Pick OneDrive/SharePoint as canonical and remove ShareFile copies."
    ),
    "ShareFile Sync": (
        "ShareFile installer DMG and personal documents synced to multiple locations."
    ),
    "Brush Cyber (Management)": (
        "Archer Hall forensic report duplicated between Pristine evidence and Working copies."
    ),
}


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_user_files_report(
    scan_json: Path,
    output_dir: Path,
) -> Path:
    """Generate a branded HTML report from user-files-scan.json."""
    with scan_json.open() as f:
        data = json.load(f)

    timestamp = datetime.now(tz=UTC).isoformat(timespec="seconds")
    local_time = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    parts: list[str] = []

    parts.append(_HTML_HEAD.format(title="User File Inventory &amp; Dedup Report — Brush Cyber"))
    parts.append(_EXTRA_CSS)

    # Header
    logo_uri = _logo_data_uri()
    logo_tag = f'<img src="{logo_uri}" alt="Brush Cyber">' if logo_uri else ""
    parts.append(f"""
<div class="report-header">
  {logo_tag}
  <div class="meta">
    <div class="title">User File Inventory &amp; Dedup Report</div>
    {local_time}<br>{timestamp}
  </div>
</div>
""")

    # ── Executive Summary ──
    cats = data["categories"]
    dups = data["duplicates"]
    dup_pct = dups["total_wasted"] / data["total_size"] * 100 if data["total_size"] > 0 else 0

    parts.append(f"""
<div class="section">
  <h2>Executive Summary</h2>
  <div class="stat-grid">
    <div class="stat-card">
      <div class="label">Total Files</div>
      <div class="value">{data['total_files']:,}</div>
      <div class="sub">{len(cats)} categories</div>
    </div>
    <div class="stat-card">
      <div class="label">Total Size</div>
      <div class="value">{data['total_size_human']}</div>
    </div>
    <div class="stat-card">
      <div class="label">Duplicate Groups</div>
      <div class="value" style="color:var(--bc-crimson)">{dups['total_groups']:,}</div>
      <div class="sub">{dups['total_duplicate_files']:,} extra files</div>
    </div>
    <div class="stat-card">
      <div class="label">Wasted Space</div>
      <div class="value" style="color:var(--bc-crimson)">{dups['total_wasted_human']}</div>
      <div class="sub">{dup_pct:.1f}% of total</div>
    </div>
  </div>
</div>
""")

    # ── Verification Banner ──
    verification = dups.get("verification")
    if verification:
        parts.append(f"""
<div class="verification-banner">
  <div class="v-icon">&#x2714;</div>
  <div>
    <strong>All duplicates SHA-256 verified</strong> &mdash;
    {verification['confirmed']} confirmed,
    {verification['false_positives']} false positives removed,
    {verification['errors']} unreadable (cloud timeout)
    <div class="v-detail">Verified {verification.get('verified_at', '')}</div>
  </div>
</div>
""")

    # ── File Inventory by Category ──
    max_cat_size = max(c["size"] for c in cats.values()) if cats else 1
    cat_rows = []
    bar_colors = [
        "var(--bc-indigo)", "var(--bc-magenta)", "var(--bc-sky-blue)",
        "var(--bc-crimson)", "var(--bc-lavender)", "var(--bc-rich-magenta)",
        "var(--bc-deep-purple)",
    ]
    for i, (cat_name, cat_data) in enumerate(cats.items()):
        color = bar_colors[i % len(bar_colors)]
        cat_rows.append(
            f'<div class="cat-row">'
            f'<div class="cat-label">{_esc(cat_name)}</div>'
            f'<div class="cat-bar">{_bar_html(cat_data["size"], max_cat_size, color)}</div>'
            f'<div class="cat-val">{cat_data["size_human"]}</div>'
            f'<div class="cat-count">{cat_data["count"]:,} files</div>'
            f'</div>'
        )
    parts.append(f"""
<div class="section">
  <h2>File Inventory by Category</h2>
  {"".join(cat_rows)}
</div>
""")

    # ── Storage by Location ──
    locs = data.get("locations", {})
    if locs:
        max_loc_size = max(v["size"] for v in locs.values()) if locs else 1
        loc_rows = []
        for loc_path, loc_data in locs.items():
            label = _location_label(loc_path)
            loc_rows.append(
                f'<div class="cat-row">'
                f'<div class="cat-label">{_esc(label)}</div>'
                f'<div class="cat-bar">'
                f'{_bar_html(loc_data["size"], max_loc_size, "var(--bc-sky-blue)")}</div>'
                f'<div class="cat-val">{loc_data["size_human"]}</div>'
                f'<div class="cat-count">{loc_data["count"]:,} files</div>'
                f'</div>'
            )
        parts.append(f"""
<div class="section">
  <h2>Storage by Location</h2>
  {"".join(loc_rows)}
</div>
""")

    # ── Top Extensions ──
    exts = data.get("extensions", {})
    if exts:
        ext_items = list(exts.items())[:15]
        ext_rows = []
        for ext_name, ext_data in ext_items:
            ext_rows.append(
                f"<tr><td><code>.{_esc(ext_name)}</code></td>"
                f"<td class='num'>{ext_data['count']:,}</td>"
                f"<td class='size'>{ext_data['size_human']}</td></tr>"
            )
        parts.append(f"""
<div class="section">
  <h2>Top File Extensions</h2>
  <table>
    <thead><tr><th>Extension</th><th>Count</th><th>Size</th></tr></thead>
    <tbody>{"".join(ext_rows)}</tbody>
  </table>
</div>
""")

    # ── Duplicate Waste by Category ──
    dup_cats = dups.get("by_category", {})
    if dup_cats:
        max_dup_cat = max(
            (v["wasted"] for v in dup_cats.values() if v["wasted"] > 0), default=1,
        )
        dup_cat_rows = []
        for cat_name, cat_data in dup_cats.items():
            if cat_data["wasted"] <= 0:
                continue
            color = _severity_color(cat_data["wasted"])
            dup_cat_rows.append(
                f'<div class="cat-row">'
                f'<div class="cat-label">{_esc(cat_name)}</div>'
                f'<div class="cat-bar">{_bar_html(cat_data["wasted"], max_dup_cat, color)}</div>'
                f'<div class="cat-val" style="color:{color}">{cat_data["wasted_human"]}</div>'
                f'<div class="cat-count">{cat_data["groups"]} groups / '
                f'{cat_data["files"]} files</div>'
                f'</div>'
            )
        if dup_cat_rows:
            parts.append(f"""
<div class="section">
  <h2>Duplicate Waste by Category</h2>
  {"".join(dup_cat_rows)}
</div>
""")

    # ── Cross-Location Patterns ──
    groups = [g for g in dups.get("groups", []) if g.get("match_type") == "sha256"]
    cross_locs = _build_cross_location(groups)
    if cross_locs:
        max_cross = max(w for _, _, w in cross_locs) if cross_locs else 1
        cross_rows = []
        for pattern, count, waste in cross_locs:
            cross_rows.append(
                f'<div class="cross-loc-row">'
                f'<div class="cross-loc-label">{_esc(pattern)}</div>'
                f'<div class="cat-bar">'
                f'{_bar_html(waste, max_cross, "var(--bc-magenta)")}</div>'
                f'<div class="cross-loc-val">{bytes_to_human(waste)}</div>'
                f'<div class="cross-loc-count">{count} groups</div>'
                f'</div>'
            )
        parts.append(f"""
<div class="section">
  <h2>Cross-Location Duplicate Patterns</h2>
  {"".join(cross_rows)}
</div>
""")

    # ── Clustered Duplicates ──
    clusters = _build_clusters(groups)
    for cluster_name, cluster_groups in clusters.items():
        cluster_waste = sum(g["wasted"] for g in cluster_groups)
        cluster_files = sum(g["count"] for g in cluster_groups)
        cluster_color = _CLUSTER_COLORS.get(cluster_name, "var(--bc-indigo)")
        description = _CLUSTER_DESCRIPTIONS.get(cluster_name, "")

        # Sort groups by waste descending within cluster
        sorted_groups = sorted(cluster_groups, key=lambda g: g["wasted"], reverse=True)

        group_cards = []
        for g in sorted_groups:
            files_html = []
            for f in g["files"]:
                sp = _shorten_path(f["path"])
                files_html.append(f'<div class="dup-path">{_esc(sp)}</div>')

            waste_color = _severity_color(g["wasted"])
            match_badge = (
                '<span class="badge badge-pass">SHA-256</span>'
                if g.get("match_type") == "sha256"
                else '<span class="badge badge-warn">unverified</span>'
            )
            hash_line = ""
            if g.get("hash"):
                hash_line = f'<div class="dup-hash">SHA-256: {g["hash"]}</div>'

            first_name = g["files"][0]["name"] if g["files"] else "unknown"
            group_cards.append(
                f'<div class="dup-card">'
                f'<div class="dup-header">'
                f'<div class="dup-name">{_esc(first_name)}</div>'
                f'<div class="dup-waste" style="color:{waste_color}">'
                f'-{g["wasted_human"]}</div>'
                f'</div>'
                f'<div class="dup-meta">{g["count"]} copies &middot; '
                f'{bytes_to_human(g["size"])} each &middot; '
                f'{g.get("category", "")} &middot; '
                f'{match_badge}</div>'
                f'{hash_line}'
                f'{"".join(files_html)}'
                f'</div>'
            )

        desc_html = ""
        if description:
            desc_html = f'<div class="cluster-pattern">{description}</div>'

        parts.append(f"""
<div class="cluster-section">
  <div class="cluster-header">
    <h2 style="color:{cluster_color}">{_esc(cluster_name)}</h2>
    <div class="cluster-stats">
      <span style="color:{cluster_color}">{bytes_to_human(cluster_waste)}</span>
      &nbsp;&middot;&nbsp;
      {len(cluster_groups)} groups &middot; {cluster_files} files
    </div>
  </div>
  {desc_html}
  {"".join(group_cards)}
</div>
""")

    # ── Largest Files ──
    largest = data.get("largest_files", [])
    if largest:
        large_rows = []
        for lf in largest[:20]:
            sp = _shorten_path(lf["path"])
            large_rows.append(
                f"<tr><td class='path'>{_esc(sp)}</td>"
                f"<td>{_esc(lf.get('category', ''))}</td>"
                f"<td class='size'>{lf['size_human']}</td></tr>"
            )
        parts.append(f"""
<div class="section">
  <h2>Largest Files (Top 20)</h2>
  <table>
    <thead><tr><th>File</th><th>Category</th><th>Size</th></tr></thead>
    <tbody>{"".join(large_rows)}</tbody>
  </table>
</div>
""")

    # ── Top Directories ──
    top_dirs = data.get("top_directories", [])
    if top_dirs:
        dir_rows = []
        for d in top_dirs[:15]:
            sp = _shorten_path(d["path"])
            dir_rows.append(
                f"<tr><td class='path'>{_esc(sp)}</td>"
                f"<td class='num'>{d['count']:,}</td>"
                f"<td class='size'>{d['size_human']}</td></tr>"
            )
        parts.append(f"""
<div class="section">
  <h2>Top Directories (by size)</h2>
  <table>
    <thead><tr><th>Directory</th><th>Files</th><th>Size</th></tr></thead>
    <tbody>{"".join(dir_rows)}</tbody>
  </table>
</div>
""")

    # ── Remediation Plan ──
    recs = _build_recommendations(data)
    rec_html = []
    for i, rec in enumerate(recs, 1):
        rec_html.append(
            f'<div class="rec">'
            f'<div class="rec-num">{i}</div>'
            f'<div class="rec-text">{rec}</div>'
            f'</div>'
        )
    parts.append(f"""
<div class="remediation-box">
  <h2>Remediation Plan</h2>
  {"".join(rec_html)}
</div>
""")

    parts.append(_HTML_TAIL)

    # Write
    ensure_dir(output_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = output_dir / f"user-files-report-{stamp}.html"
    report_path.write_text("".join(parts))
    return report_path


def _build_recommendations(data: dict) -> list[str]:
    """Generate actionable remediation recommendations from scan data."""
    recs: list[str] = []
    dups = data["duplicates"]
    groups = dups.get("groups", [])

    # 1. Enagic inventory files
    enagic_waste = 0
    enagic_groups = 0
    for g in groups:
        if any("ENANAS" in f.get("name", "") or "Enagic" in f.get("dir", "")
               for f in g.get("files", [])):
            enagic_waste += g["wasted"]
            enagic_groups += 1
    if enagic_waste > 50 * 1024 * 1024:
        recs.append(
            f"<strong>Enagic file inventories:</strong> {enagic_groups} duplicate groups "
            f"wasting {bytes_to_human(enagic_waste)}. Consolidate ShareInventory CSVs to "
            f"a single canonical location (OneDrive-BrushCyber/ShareInventory) and remove "
            f"copies from Synology paths and Power Query uploads."
        )

    # 2. Denali/litigation duplicates
    legal_waste = 0
    legal_groups = 0
    for g in groups:
        if any("Denali" in f.get("dir", "") for f in g.get("files", [])):
            legal_waste += g["wasted"]
            legal_groups += 1
    if legal_waste > 10 * 1024 * 1024:
        recs.append(
            f"<strong>Denali litigation files:</strong> {legal_groups} duplicate groups "
            f"({bytes_to_human(legal_waste)}). Cross-posted in Brown/Calhoun correspondence "
            f"and case filings. <em>Review before deleting</em> — retain originals in "
            f"Case Filings, remove redundant copies from correspondence Working folders."
        )

    # 3. MKR / Miers DFIR
    mkr_waste = 0
    mkr_groups = 0
    for g in groups:
        if any("MKR" in f.get("dir", "") or "Miers" in f.get("dir", "")
               for f in g.get("files", [])):
            mkr_waste += g["wasted"]
            mkr_groups += 1
    if mkr_waste > 10 * 1024 * 1024:
        recs.append(
            f"<strong>MKR / Miers DFIR:</strong> {mkr_groups} duplicate groups "
            f"({bytes_to_human(mkr_waste)}). Discord warrant attachments exist in both "
            f"<code>03_DFIR</code> and <code>00_Discovery/_received</code>. "
            f"Keep originals in <code>00_Discovery</code>, remove working copies."
        )

    # 4. Photos
    by_cat = dups.get("by_category", {})
    if by_cat.get("Images", {}).get("wasted", 0) > 50 * 1024 * 1024:
        img = by_cat["Images"]
        recs.append(
            f"<strong>Image duplicates:</strong> {img['groups']} groups, "
            f"{img['wasted_human']} wasted. Job photos triplicated across _DB_FILE paths. "
            f"Apple Photos Library has internal originals/renders duplication. "
            f"Consolidate _DB_FILE copies; leave Photos Library internal dupes alone."
        )

    # 5. Local documents
    if by_cat.get("Spreadsheets", {}).get("wasted", 0) > 50 * 1024 * 1024:
        ss = by_cat["Spreadsheets"]
        recs.append(
            f"<strong>Spreadsheet duplicates:</strong> {ss['groups']} groups, "
            f"{ss['wasted_human']} wasted. Primarily large CSV exports and Entra sync runs. "
            f"Archive completed inventory runs and keep only the latest version."
        )

    # 6. Cross-location sync
    recs.append(
        "<strong>Cross-location sync:</strong> OneDrive ↔ SharePoint is the biggest "
        "cross-sync pattern. This is expected for shared team libraries. "
        "OneDrive ↔ ShareFile duplicates can be cleaned — pick OneDrive as canonical."
    )

    # 7. Overall summary
    verified = dups.get("verification", {})
    method_note = ""
    if verified:
        method_note = (
            f" All {verified.get('confirmed', 0)} groups SHA-256 hash verified. "
            f"{verified.get('false_positives', 0)} false positives already removed."
        )
    recs.append(
        f"<strong>Total recoverable:</strong> {dups['total_wasted_human']} across "
        f"{dups['total_groups']:,} duplicate groups.{method_note} "
        f"Prioritize Enagic inventories, MKR/Miers discovery, and Denali filings "
        f"for the biggest wins."
    )

    return recs
