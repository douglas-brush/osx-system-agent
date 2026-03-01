# osx-system-agent

## What This Is
Local macOS system agent CLI (`osa`) for monitoring system health, scanning for file hygiene issues, and running cleanup actions. Internal tool — not published to PyPI.

## Quick Reference
- **Entry point:** `src/osx_system_agent/cli.py` → `osa` command
- **Package layout:** `src/` layout with setuptools
- **Python:** >=3.11, venv at `.venv/`
- **CLI framework:** Typer + Rich
- **Test framework:** pytest (`tests/`)
- **Linter:** ruff (config in `pyproject.toml`)

## Commands
- `osa status` — CPU, memory, disk, battery
- `osa processes` — top processes by CPU/memory
- `osa scan duplicates` — SHA-256 dedup scan
- `osa scan aging` — old/large file report
- `osa scan inventory` — file inventory by extension
- `osa scan launch-agents` — LaunchAgent/LaunchDaemon inventory
- `osa scan brew` — Homebrew package audit
- `osa scan disk-hogs` — large directory usage report
- `osa scan caches` — cache directory size report
- `osa scan junk` — .DS_Store and junk file scanner
- `osa clean caches` — purge cache directories
- `osa clean junk` — remove junk files

## Dev Workflow
```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src/ tests/
```

## Conventions
- All scanners live in `src/osx_system_agent/scanners/`
- System info modules in `src/osx_system_agent/system/`
- Reports (JSON/CSV) written via `reports/writer.py`
- Logging via `osx_system_agent.log` — always log to file, stderr only with `-v`
- Timestamps: ISO 8601 UTC
- Cleanup commands always support `--dry-run` and log actions
