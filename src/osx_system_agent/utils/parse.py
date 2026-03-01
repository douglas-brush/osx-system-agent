from __future__ import annotations

import re

SIZE_RE = re.compile(r"^(\d+(?:\.\d+)?)([KMGTP]?B?)?$", re.IGNORECASE)

UNIT_MAP = {
    "": 1,
    "B": 1,
    "K": 1024,
    "KB": 1024,
    "M": 1024 ** 2,
    "MB": 1024 ** 2,
    "G": 1024 ** 3,
    "GB": 1024 ** 3,
    "T": 1024 ** 4,
    "TB": 1024 ** 4,
    "P": 1024 ** 5,
    "PB": 1024 ** 5,
}


def parse_size(value: str | int) -> int:
    if isinstance(value, int):
        return value
    raw = value.strip().upper().replace(" ", "")
    match = SIZE_RE.match(raw)
    if not match:
        raise ValueError(f"Invalid size: {value}")
    number = float(match.group(1))
    unit = match.group(2) or ""
    unit = unit.upper()
    if unit not in UNIT_MAP:
        raise ValueError(f"Unknown size unit: {unit}")
    return int(number * UNIT_MAP[unit])
