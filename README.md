# osx-system-agent

Local macOS system agent for monitoring system health and cleaning up storage.

This repo is a scaffold you can extend in VS Code. It ships a CLI with a few
foundational tools:

- System status (CPU, memory, disk, battery)
- Process snapshots (top CPU/memory)
- File scans: duplicates, aging, and inventory summary
- JSON/CSV report outputs for dashboards

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .

# Example: get system status
osa status

# Example: scan home directory for duplicates over 10MB
osa scan duplicates --path ~ --min-size 10MB --out ./reports

# Example: list largest/oldest files
osa scan aging --path ~ --sort mtime --limit 200 --out ./reports

# Example: inventory by extension
osa scan inventory --path ~ --out ./reports
```

## Notes

- Scans default to skipping common system and build folders. You can override
  with `--exclude`.
- For full-disk scans, macOS may require granting Full Disk Access to your
  terminal or Python.
- Reports are written as JSON and CSV for easy dashboarding.

## Roadmap ideas

- LaunchAgents/LaunchDaemons inventory
- Background item/battery impact tracking
- Spotlight index status + reindex helpers
- Dedup move/symlink workflows with safety checks
- Local dashboard (e.g., FastAPI + React or a lightweight TUI)
