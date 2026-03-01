from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_DIR = Path.home() / ".local" / "share" / "osx-system-agent" / "logs"
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s  %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

_configured = False


def setup_logging(verbose: bool = False) -> None:
    global _configured
    if _configured:
        return
    _configured = True

    level = logging.DEBUG if verbose else logging.WARNING
    root = logging.getLogger("osa")
    root.setLevel(level)

    # Console handler
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(console)

    # File handler — always DEBUG regardless of verbosity
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(LOG_DIR / "osa.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"osa.{name}")
