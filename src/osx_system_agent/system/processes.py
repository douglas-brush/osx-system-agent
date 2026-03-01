from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass

import psutil


@dataclass
class ProcessInfo:
    pid: int
    name: str
    username: str | None
    cpu_percent: float
    memory_rss: int


def _iter_processes() -> Iterable[psutil.Process]:
    return psutil.process_iter(attrs=["pid", "name", "username"])


def snapshot_processes(sort: str = "cpu", limit: int = 20) -> list[ProcessInfo]:
    for proc in _iter_processes():
        try:
            proc.cpu_percent(interval=None)
        except Exception:
            continue

    time.sleep(0.2)

    rows: list[ProcessInfo] = []
    for proc in _iter_processes():
        try:
            mem = proc.memory_info().rss
            cpu = proc.cpu_percent(interval=None)
            info = proc.info
            rows.append(
                ProcessInfo(
                    pid=info.get("pid"),
                    name=info.get("name") or "",
                    username=info.get("username"),
                    cpu_percent=cpu,
                    memory_rss=mem,
                )
            )
        except Exception:
            continue

    key = "cpu_percent" if sort == "cpu" else "memory_rss"
    rows.sort(key=lambda p: getattr(p, key), reverse=True)
    return rows[:limit]
