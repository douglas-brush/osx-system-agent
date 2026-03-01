# osx-system-agent

## What This Is
Local macOS system agent CLI (`osa`) for monitoring system health, scanning for file hygiene issues, running cleanup actions, and generating reports. Internal tool — not published to PyPI.

## Quick Reference
- **Entry point:** `src/osx_system_agent/cli.py` → `osa` command
- **Package layout:** `src/` layout with setuptools
- **Python:** >=3.11, venv at `.venv/`
- **CLI framework:** Typer + Rich
- **Test framework:** pytest (`tests/`), 173 tests
- **Linter:** ruff (config in `pyproject.toml`)
- **CI:** GitHub Actions (`.github/workflows/ci.yml`) — ruff + pytest on macOS, Python 3.11-3.13

## Commands

### System
- `osa status` — CPU, memory, disk, battery
- `osa processes [--sort cpu|mem] [--limit N]` — top processes
- `osa doctor [--path PATH]` — system health diagnostics with fix suggestions
- `osa config [--key K] [--value V] [--reset]` — persistent configuration

### Scan
- `osa scan all` — summary dashboard of all scanners
- `osa scan duplicates` — SHA-256 dedup scan
- `osa scan aging` — old/large file report
- `osa scan inventory` — file inventory by extension
- `osa scan launch-agents` — LaunchAgent/LaunchDaemon inventory
- `osa scan login-items` — macOS login items
- `osa scan brew` — Homebrew package audit
- `osa scan disk-hogs` — large directory usage report
- `osa scan disk-usage` — du-style directory breakdown
- `osa scan caches` — cache directory size report
- `osa scan junk` — .DS_Store and junk file scanner
- `osa scan xcode` — Xcode DerivedData, Archives, Simulators
- `osa scan docker` — Docker images, containers, volumes

### Clean (all support `--dry-run`/`--no-dry-run`)
- `osa clean caches` — purge cache directories
- `osa clean junk` — remove junk files
- `osa clean duplicates` — deduplicate files (trash safety)
- `osa clean brew` — upgrade outdated Homebrew packages
- `osa clean xcode [--archives] [--sims]` — clean Xcode artifacts

### Reports & Trending
- `osa report [--out DIR]` — consolidated JSON system report
- `osa export [--fmt markdown|json]` — export Markdown or JSON report
- `osa snapshot` — record point-in-time disk/cache metrics
- `osa trend` — show historical disk usage with deltas
- `osa schedule [--interval N] [--remove]` — install LaunchAgent for periodic reports
- `osa undo [--restore N] [--clear]` — view/restore recent clean operations

## Module Layout
```
src/osx_system_agent/
├── cli.py                 # Main CLI entry point (Typer)
├── log.py                 # Structured logging (file + console)
├── config.py              # Persistent JSON config (~/.config/osx-system-agent/)
├── doctor.py              # System health diagnostics
├── schedule.py            # LaunchAgent plist generation
├── undo.py                # Undo action log reader
├── scanners/              # All scan modules
│   ├── filters.py         # File iteration with excludes
│   ├── duplicates.py      # SHA-256 dedup scanner
│   ├── aging.py           # Old/large file scanner
│   ├── inventory.py       # File extension inventory
│   ├── launch_agents.py   # LaunchAgent/Daemon parser
│   ├── login_items.py     # macOS login items
│   ├── brew.py            # Homebrew audit
│   ├── disk_hogs.py       # Large directory scanner
│   ├── disk_usage.py      # du-style breakdown
│   ├── caches.py          # Cache directory scanner
│   ├── junk.py            # .DS_Store / junk scanner
│   ├── xcode.py           # Xcode DerivedData/Archives/Sims
│   └── docker.py          # Docker images/containers/volumes
├── clean/                 # Cleanup/remediation modules
│   ├── trash.py           # Finder trash + undo logging
│   ├── caches.py          # Cache purge
│   ├── junk.py            # Junk file removal
│   ├── duplicates.py      # Dedup with keeper selection
│   ├── brew.py            # Homebrew upgrade/cleanup
│   └── xcode.py           # Xcode artifact cleanup
├── reports/               # Report generation
│   ├── writer.py          # JSON/CSV writer
│   ├── consolidated.py    # Full JSON report
│   ├── history.py         # JSONL snapshot trending
│   └── markdown.py        # Markdown report export
├── system/                # System info collectors
│   ├── activity.py        # CPU, memory, disk, battery (psutil)
│   └── processes.py       # Process snapshots
└── utils/                 # Shared utilities
    ├── human.py           # bytes_to_human, unix_to_iso
    ├── parse.py           # parse_size ("10MB" → int)
    └── paths.py           # expand_path, ensure_dir
```

## Data Locations
- **Config:** `~/.config/osx-system-agent/config.json`
- **Logs:** `~/.local/share/osx-system-agent/logs/`
- **Undo log:** `~/.local/share/osx-system-agent/undo/actions.jsonl`
- **Snapshots:** `~/.local/share/osx-system-agent/history/snapshots.jsonl`
- **Reports:** `./reports/` or `--out` override

## Dev Workflow
```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
```

## Conventions
- All scanners return dataclasses, sorted by size descending
- Cleanup commands default to `--dry-run` — require `--no-dry-run` for execution
- All cleanup actions logged to undo JSONL for restore capability
- Logging: always to file (DEBUG), console only with `-v`
- Timestamps: ISO 8601 UTC
- Conventional commits: `feat:`, `fix:`, `chore:`, `refactor:`
