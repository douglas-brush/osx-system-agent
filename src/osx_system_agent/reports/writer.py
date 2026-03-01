from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, Mapping

from osx_system_agent.utils.paths import ensure_dir


def write_json(data: object, output_path: str | Path) -> Path:
    path = Path(output_path)
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, default=str))
    return path


def write_csv(rows: Iterable[Mapping[str, object]], output_path: str | Path) -> Path:
    path = Path(output_path)
    ensure_dir(path.parent)
    rows = list(rows)
    if not rows:
        path.write_text("")
        return path
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path
