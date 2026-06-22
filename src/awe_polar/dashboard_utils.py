"""Shared helpers for Polar terminal dashboards.

Both ``monitor_polar_terminal.py`` and ``monitor_dual_polar.py`` import
from this module to avoid duplicating RMSSD, sparkline, Hz tracking,
battery reading, and CSV logging logic.
"""

from __future__ import annotations

import csv
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

# ── Constants ────────────────────────────────────────────────────────────────

BATTERY_SERVICE_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

# Sparkline block characters (dark → full).
_SPARK_CHARS = " ▂▃▄▅▆▇█"


# ── Calculations ─────────────────────────────────────────────────────────────


def calculate_rmssd(rr_list) -> float:
    """Root-mean-square of successive RR-interval differences."""
    if len(rr_list) < 2:
        return 0.0
    rr_array = np.array([float(rr) for rr in rr_list if rr is not None and rr > 0])
    if len(rr_array) < 2:
        return 0.0
    return float(np.sqrt(np.mean(np.diff(rr_array) ** 2)))


def draw_sparkline(history, width: int = 30) -> str:
    """Render a single-line text sparkline from a deque of numeric values."""
    if not history:
        return ""
    data = list(history)[-width:]
    if not data:
        return ""
    val_min = min(data)
    val_max = max(data)
    val_range = val_max - val_min or 1

    num_chars = len(_SPARK_CHARS)
    spark = ""
    for v in data:
        idx = int((v - val_min) / val_range * (num_chars - 1))
        idx = max(0, min(num_chars - 1, idx))
        spark += _SPARK_CHARS[idx]
    return spark


# ── Hz tracking ──────────────────────────────────────────────────────────────


def update_hz_for_state(
    state: dict[str, Any],
    *streams: tuple[str, deque],
    now: float | None = None,
) -> None:
    """Compute observed sample rates and write them into *state*.

    Each *streams* entry is ``(key_prefix, timestamp_deque)`` where
    ``timestamp_deque`` holds ``(t, sample_count)`` tuples.
    The result is written to ``state[f"{key_prefix}_hz"]``.
    """
    if now is None:
        now = time.time()
    for prefix, ts_list in streams:
        recent = [item for item in ts_list if now - item[0] <= 1.5]
        if not recent:
            state[f"{prefix}_hz"] = 0.0
            continue
        total_samples = sum(item[1] for item in recent)
        time_span = now - recent[0][0]
        state[f"{prefix}_hz"] = total_samples / time_span if time_span > 0.1 else 0.0


# ── Battery ──────────────────────────────────────────────────────────────────


async def read_battery(conn) -> str:
    """Read battery level from a connected Polar device, returning a display string."""
    try:
        data = await conn.polar_device._client.read_gatt_char(BATTERY_SERVICE_UUID)
        return f"{int(data[0])}%" if data else "-"
    except Exception:
        return "-"


async def update_battery_loop(conn, state: dict[str, Any]) -> None:
    """Background task: refresh battery level in *state* every 30 s."""
    while True:
        state["battery"] = await read_battery(conn)
        await __import__("asyncio").sleep(30)


# ── CSV helpers ──────────────────────────────────────────────────────────────


class CsvLogger:
    """Manages a single CSV log file with header validation."""

    def __init__(self, path: Path | str | None, columns: list[str]) -> None:
        self._path = Path(path) if path else None
        self._columns = columns
        self.rows_written = 0

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def path_str(self) -> str:
        return str(self._path) if self._path else "-"

    def write_header(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(self._columns)

    def write_row(self, values: list[Any]) -> None:
        if not self._path:
            return
        with self._path.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(values)
        self.rows_written += 1
