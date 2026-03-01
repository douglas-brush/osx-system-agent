from __future__ import annotations

from pathlib import Path


def expand_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def ensure_dir(path: str | Path) -> Path:
    p = expand_path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
