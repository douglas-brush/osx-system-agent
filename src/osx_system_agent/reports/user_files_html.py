"""Generate a branded HTML report from a user-files-scan JSON."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from osx_system_agent.reports.html import _HTML_HEAD, _HTML_TAIL, _esc, _logo_data_uri
from osx_system_agent.utils.paths import ensure_dir


def _shorten_path(path: str, max_len: int = 80) -> str:
    """Shorten a long path for display, keeping the meaningful tail."""
    if len(path) <= max_len:
        return path
    # Strip the common OneDrive prefix noise
    short = path
    for prefix in (
        "/Users/douglas_brush/Library/CloudStorage/OneDrive-SharedLibraries-BrushCyber/",
        "/Users/douglas_brush/Library/CloudStorage/OneDrive-BrushCyber/",
        "/Users/douglas_brush/Library/CloudStorage/",
        "/Users/douglas_brush/",
    ):
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
    """Render a tiny inline bar chart."""
    pct = min(value / max_val * 100, 100) if max_val > 0 else 0
    return (
        f'<div style="background:var(--bc-light-gray);border-radius:4px;height:8px;'
        f'width:100%;margin-top:4px">'
        f'<div style="background:{color};border-radius:4px;height:8px;'
        f'width:{pct:.1f}%"></div></div>'
    )


def _severity_color(wasted: int) -> str:
    """Color based on waste severity."""
    if wasted >= 100 * 1024 * 1024:
        return "var(--bc-crimson)"
    if wasted >= 10 * 1024 * 1024:
        return "#F57F17"
    return "var(--bc-indigo)"


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

    # Extra CSS for this report
    parts.append("""
<style>
.progress-bar {
  background: var(--bc-light-gray);
  border-radius: 4px;
  height: 10px;
  width: 100%;
  margin-top: 4px;
}
.progress-fill {
  border-radius: 4px;
  height: 10px;
}
.cat-row { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.6rem; }
.cat-label { min-width: 100px; font-weight: 500; font-size: 0.8rem; }
.cat-bar { flex: 1; }
.cat-val { min-width: 80px; text-align: right; font-family: 'Montserrat', sans-serif;
           font-weight: 600; font-size: 0.8rem; }
.cat-count { min-width: 70px; text-align: right; font-size: 0.75rem;
             color: var(--bc-muted-purple); }
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
.dup-card .dup-path {
  font-size: 0.7rem;
  color: var(--bc-muted-purple);
  padding: 0.15rem 0;
  word-break: break-all;
}
.remediation-box {
  background: linear-gradient(135deg, var(--bc-deep-navy) 0%, var(--bc-deep-purple) 100%);
  border-radius: 12px;
  padding: 1.5rem 2rem;
  color: var(--bc-white);
  margin-bottom: 1.25rem;
}
.remediation-box h2 {
  color: var(--bc-white) !important;
  border-bottom-color: var(--bc-deep-purple) !important;
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
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Montserrat', sans-serif;
  font-weight: 700;
  font-size: 0.7rem;
  flex-shrink: 0;
}
.remediation-box .rec-text {
  font-size: 0.8rem;
  line-height: 1.5;
}
.remediation-box .rec-text strong {
  color: var(--bc-sky-blue);
}
</style>
""")

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

    # ── File Inventory by Category ──
    max_cat_size = max(c["size"] for c in cats.values()) if cats else 1
    cat_rows = []
    colors = [
        "var(--bc-indigo)", "var(--bc-magenta)", "var(--bc-sky-blue)",
        "var(--bc-crimson)", "var(--bc-lavender)", "var(--bc-rich-magenta)",
        "var(--bc-deep-purple)",
    ]
    for i, (cat_name, cat_data) in enumerate(cats.items()):
        color = colors[i % len(colors)]
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
        max_dup_cat = max(v["wasted"] for v in dup_cats.values()) if dup_cats else 1
        dup_cat_rows = []
        for cat_name, cat_data in dup_cats.items():
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
        parts.append(f"""
<div class="section">
  <h2>Duplicate Waste by Category</h2>
  {"".join(dup_cat_rows)}
</div>
""")

    # ── Top Duplicate Groups (top 30) ──
    groups = dups.get("groups", [])
    if groups:
        top_groups = groups[:30]
        group_cards = []
        for g in top_groups:
            files_html = []
            for f in g["files"]:
                sp = _shorten_path(f["path"])
                files_html.append(f'<div class="dup-path">{_esc(sp)}</div>')

            waste_color = _severity_color(g["wasted"])
            match_badge = (
                '<span class="badge badge-pass">SHA-256</span>'
                if g.get("match_type") == "sha256"
                else '<span class="badge badge-warn">name+size</span>'
            )

            first_name = g["files"][0]["name"] if g["files"] else "unknown"
            group_cards.append(
                f'<div class="dup-card">'
                f'<div class="dup-header">'
                f'<div class="dup-name">{_esc(first_name)}</div>'
                f'<div class="dup-waste" style="color:{waste_color}">'
                f'-{g["wasted_human"]}</div>'
                f'</div>'
                f'<div class="dup-meta">{g["count"]} copies &middot; '
                f'{g.get("category", "")} &middot; '
                f'{match_badge}</div>'
                f'{"".join(files_html)}'
                f'</div>'
            )

        parts.append(f"""
<div class="section">
  <h2>Top Duplicate Groups (by wasted space)</h2>
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
    # Build targeted recommendations from the data
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

    # 1. Enagic inventory files — biggest single waste source
    enagic_waste = 0
    enagic_groups = 0
    for g in groups:
        if any("ENANAS" in f.get("name", "") or "Enagic" in f.get("dir", "")
               for f in g.get("files", [])):
            enagic_waste += g["wasted"]
            enagic_groups += 1
    if enagic_waste > 50 * 1024 * 1024:
        from osx_system_agent.utils.human import bytes_to_human
        recs.append(
            f"<strong>Enagic file inventories:</strong> {enagic_groups} duplicate groups "
            f"wasting {bytes_to_human(enagic_waste)}. Consolidate ShareInventory CSVs to "
            f"a single canonical location (OneDrive-BrushCyber/ShareInventory) and remove "
            f"copies from Synology paths and Power Query uploads."
        )

    # 2. Denali/litigation duplicates — need careful handling
    legal_waste = 0
    legal_groups = 0
    for g in groups:
        if any("Denali" in f.get("dir", "") for f in g.get("files", [])):
            legal_waste += g["wasted"]
            legal_groups += 1
    if legal_waste > 10 * 1024 * 1024:
        from osx_system_agent.utils.human import bytes_to_human
        recs.append(
            f"<strong>Denali litigation files:</strong> {legal_groups} duplicate groups "
            f"({bytes_to_human(legal_waste)}). Cross-posted in Brown/Calhoun correspondence "
            f"and case filings. <em>Review before deleting</em> — retain originals in "
            f"Case Filings, remove redundant copies from correspondence Working folders."
        )

    # 3. Winrock/ShareFile cross-sync
    winrock_waste = 0
    for g in groups:
        if any("Winrock" in f.get("dir", "") or "ShareFile" in f.get("dir", "")
               for f in g.get("files", [])):
            winrock_waste += g["wasted"]
    if winrock_waste > 10 * 1024 * 1024:
        from osx_system_agent.utils.human import bytes_to_human
        recs.append(
            f"<strong>Winrock/ShareFile sync duplicates:</strong> {bytes_to_human(winrock_waste)} "
            f"wasted. Reports are mirrored between OneDrive and ShareFile. Pick one as "
            f"primary (OneDrive) and remove duplicates from ShareFile shared folders."
        )

    # 4. Category-level recommendations
    by_cat = dups.get("by_category", {})
    if by_cat.get("Images", {}).get("wasted", 0) > 100 * 1024 * 1024:
        img = by_cat["Images"]
        recs.append(
            f"<strong>Image duplicates:</strong> {img['groups']} groups, "
            f"{img['wasted_human']} wasted across {img['files']} files. "
            f"Run <code>osa clean duplicates</code> with image extensions filtered "
            f"to consolidate. Many are likely screenshots and photo exports."
        )

    if by_cat.get("Spreadsheets", {}).get("wasted", 0) > 100 * 1024 * 1024:
        ss = by_cat["Spreadsheets"]
        recs.append(
            f"<strong>Spreadsheet duplicates:</strong> {ss['groups']} groups, "
            f"{ss['wasted_human']} wasted. Primarily large CSV exports. Archive "
            f"completed inventory runs and keep only the latest version."
        )

    # 5. Cloud storage dominance
    locs = data.get("locations", {})
    cloud = locs.get("/Users/douglas_brush/Library/CloudStorage", {})
    if cloud:
        cloud_pct = cloud["size"] / data["total_size"] * 100 if data["total_size"] > 0 else 0
        recs.append(
            f"<strong>Cloud storage:</strong> {cloud['size_human']} ({cloud_pct:.0f}% of all "
            f"user files) in cloud sync. Verify OneDrive Files On-Demand is enabled to "
            f"avoid unnecessary local copies of cloud-only files."
        )

    # 6. Downloads cleanup
    dl = locs.get("/Users/douglas_brush/Downloads", {})
    if dl and dl.get("size", 0) > 100 * 1024 * 1024:
        recs.append(
            f"<strong>Downloads folder:</strong> {dl['size_human']} across {dl['count']} files. "
            f"Review and purge old downloads — installers, DMGs, and ZIP archives "
            f"that have already been extracted."
        )

    # 7. Overall summary
    recs.append(
        f"<strong>Total recoverable:</strong> {dups['total_wasted_human']} across "
        f"{dups['total_groups']:,} duplicate groups. Prioritize the top 10 groups "
        f"(Enagic inventories, MES archives, Denali legal docs) for the biggest wins. "
        f"Use <code>osa clean duplicates --no-dry-run</code> after review for safe "
        f"dedup with undo capability."
    )

    return recs
