"""Shared helpers for Polar terminal dashboards.

Both ``monitor_polar_terminal.py`` and ``monitor_dual_polar.py`` import
from this module to avoid duplicating RMSSD, sparkline, Hz tracking,
battery reading, CSV logging, and dashboard-rendering logic.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import math
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

BATTERY_SERVICE_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

# Sparkline block characters (dark → full).
_SPARK_CHARS = " ▂▃▄▅▆▇█"


# ── Device state factory ──────────────────────────────────────────────


def make_device_state(name: str = "Polar Device") -> dict[str, Any]:
    """Build a default state dict for a device dashboard."""
    return {
        "name": name,
        "address": "-",
        "status": "Scanning...",
        "hr": 0,
        "rr_intervals": [],
        "hr_history": deque(maxlen=40),
        "rr_history": deque(maxlen=50),
        "ppg_count": 0,
        "ppg_hz": 0.0,
        "ppg_last_sample": "-",
        "acc_count": 0,
        "acc_hz": 0.0,
        "acc_last_sample": "-",
        "acc_raw": (0.0, 0.0, 0.0),
        "gyro_count": 0,
        "gyro_hz": 0.0,
        "gyro_last_sample": "-",
        "gyro_raw": (0.0, 0.0, 0.0),
        "ecg_count": 0,
        "ecg_hz": 0.0,
        "ecg_last_sample": "-",
        "mag_count": 0,
        "mag_hz": 0.0,
        "mag_last_sample": "-",
        "mag_raw": (0.0, 0.0, 0.0),
        "ppi_count": 0,
        "ppi_hz": 0.0,
        "ppi_last_sample": "-",
        "battery": "-",
        "marker_log": deque(maxlen=5),
        "last_marker": "-",
        "csv_path": "-",
        "csv_rows_written": 0,
    }


# ── Generic callbacks (feed state from BLE data) ─────────────────────


def feed_hr(data, state: dict[str, Any]) -> None:
    """Update *state* from a (hr, rr_intervals) tuple."""
    if isinstance(data, tuple) and len(data) >= 2:
        hr_val, rr_ints = data
        if hr_val > 0:
            state["hr"] = hr_val
            state["hr_history"].append(hr_val)
        if rr_ints:
            state["rr_intervals"] = rr_ints
            state["rr_history"].extend(rr_ints)


def feed_ppg(data, state: dict[str, Any], ts: deque) -> None:
    """Update *state* and *ts* deque from PPG callback data."""
    timestamp, samples = data
    state["ppg_count"] += len(samples)
    ts.append((time.time(), len(samples)))
    state["ppg_last_sample"] = str(samples[-1] if samples else "")


def feed_acc(data, state: dict[str, Any], ts: deque) -> None:
    """Update *state* and *ts* deque from ACC callback data."""
    _timestamp, samples = data
    state["acc_count"] += len(samples)
    ts.append((time.time(), len(samples)))
    last_val = samples[-1]
    state["acc_raw"] = (last_val[0], last_val[1], last_val[2])
    state["acc_last_sample"] = (
        f"({last_val[0]:+4d}, {last_val[1]:+4d}, {last_val[2]:+4d}) mg"
    )


def feed_gyro(data, state: dict[str, Any], ts: deque) -> None:
    """Update *state* and *ts* deque from GYRO callback data."""
    _timestamp, samples = data
    state["gyro_count"] += len(samples)
    ts.append((time.time(), len(samples)))
    last_val = samples[-1]
    state["gyro_raw"] = (last_val[0], last_val[1], last_val[2])
    state["gyro_last_sample"] = (
        f"({last_val[0]:+4.1f}, {last_val[1]:+4.1f}, {last_val[2]:+4.1f}) dps"
    )


def feed_mag(data, state: dict[str, Any], ts: deque) -> None:
    """Update *state* and *ts* deque from MAG callback data."""
    _timestamp, samples = data
    state["mag_count"] += len(samples)
    ts.append((time.time(), len(samples)))
    last_val = samples[-1]
    state["mag_raw"] = (last_val[0], last_val[1], last_val[2])
    state["mag_last_sample"] = (
        f"({last_val[0]:+3.1f}, {last_val[1]:+3.1f}, {last_val[2]:+3.1f}) uT"
    )


def feed_ecg(data, state: dict[str, Any], ts: deque) -> None:
    """Update *state* and *ts* deque from ECG callback data."""
    _timestamp, samples = data
    state["ecg_count"] += len(samples)
    ts.append((time.time(), len(samples)))
    last_val = samples[-1]
    state["ecg_last_sample"] = f"{last_val:+5d} µV"


def feed_ppi(data, state: dict[str, Any], ts: deque) -> None:
    """Update *state* and *ts* deque from PPI callback data.
    data is a list of (timestamp_ns, ppi_ms) tuples."""
    if data:
        state["ppi_count"] += len(data)
        ts.append((time.time(), len(data)))
        state["ppi_last_sample"] = f"PPI={data[-1][1]} ms"


def make_callback(state: dict[str, Any], ts_deque: deque, kind: str) -> Callable:
    """Return a one-arg closure that updates *state* from BLE data.

    ``kind`` is one of: ecg, ppg, acc, gyro, mag, ppi.
    """
    feeders = {
        "ecg": feed_ecg,
        "ppg": feed_ppg,
        "acc": feed_acc,
        "gyro": feed_gyro,
        "mag": feed_mag,
        "ppi": feed_ppi,
    }
    fn = feeders[kind]

    def cb(data):
        fn(data, state, ts_deque)

    return cb


# ── Calculations ──────────────────────────────────────────────────────


def calculate_rmssd(rr_list) -> float:
    """Root-mean-square of successive RR-interval differences, pure Python."""
    vals = [float(rr) for rr in rr_list if rr is not None and rr > 0]
    if len(vals) < 2:
        return 0.0
    diffs = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    return float(math.sqrt(sum(d * d for d in diffs) / len(diffs)))


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


# ── Hz tracking ───────────────────────────────────────────────────────


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


# ── Battery ───────────────────────────────────────────────────────────


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
        await asyncio.sleep(30)


# ── CSV helpers ────────────────────────────────────────────────────────


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
        try:
            with self._path.open("a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(values)
            self.rows_written += 1
        except OSError as e:
            logger.warning("CSV write failed: %s", e)


# ── Dashboard rendering ────────────────────────────────────────────────


def device_panel(
    state: dict[str, Any],
    is_h10: bool,
    _rmssd: float | None = None,
    _sparkline: str | None = None,
    marker_legend: str = "",
) -> Panel:
    """Build a Rich Panel for a single device — raw streamed data only."""

    def _hr_style(val: int) -> str:
        if val > 90:
            return "bold red blink"
        if val > 55:
            return "bold green"
        return "red"

    hr_text = Text()
    hr_text.append(f"{state['hr']:3d}", style=_hr_style(state["hr"]))
    hr_text.append(" BPM", style="dim white")

    rr_display = [f"{rr:.0f}" for rr in list(state.get("rr_intervals", []))[-3:]]
    rr_text = Text()
    rr_text.append(f"RR: {rr_display} ms", style="bold magenta")

    metrics = Table.grid(expand=True)
    metrics.add_column(ratio=1)
    metrics.add_column(ratio=1)
    metrics.add_row(
        Panel(hr_text, title="Heart Rate", border_style="red", expand=True),
        Panel(
            rr_text, title="RR Intervals (last 3)", border_style="magenta", expand=True
        ),
    )

    streams = Table(expand=True)
    streams.add_column("Stream", style="cyan")
    streams.add_column("Status", style="magenta")
    streams.add_column("Latest", style="green", ratio=2)

    streams.add_row(
        "HR",
        "Active" if state["hr"] > 0 else "Waiting...",
        f"HR={state['hr']} BPM, RR={rr_display}",
    )

    if is_h10:
        streams.add_row(
            "ECG",
            "Active" if state["ecg_hz"] > 0 else "Inactive",
            state["ecg_last_sample"],
        )
        streams.add_row(
            "ACC",
            "Active" if state["acc_hz"] > 0 else "Inactive",
            state["acc_last_sample"],
        )
    else:
        streams.add_row(
            "PPG",
            "Active" if state["ppg_hz"] > 0 else "Inactive",
            state["ppg_last_sample"],
        )
        streams.add_row(
            "ACC",
            "Active" if state["acc_hz"] > 0 else "Inactive",
            state["acc_last_sample"],
        )
        streams.add_row(
            "GYRO",
            "Active" if state["gyro_hz"] > 0 else "Inactive",
            state["gyro_last_sample"],
        )
        streams.add_row(
            "MAG",
            "Active" if state["mag_hz"] > 0 else "Inactive",
            state["mag_last_sample"],
        )
        streams.add_row(
            "PPI",
            "Active" if state["ppi_hz"] > 0 else "Inactive",
            state["ppi_last_sample"],
        )

    info = Text()
    info.append(f"Battery: {state.get('battery', '-')}", style="green")
    csv_rows = state.get("csv_rows_written", 0)
    if csv_rows:
        info.append(f"  |  CSV: {csv_rows} rows", style="cyan")

    group = Group(metrics, streams, Panel(info, border_style="dim white"))
    border = (
        "green" if "connected" in str(state.get("status", "")).lower() else "yellow"
    )
    return Panel(
        group,
        title=f"{state.get('name', 'Device')} Dashboard",
        border_style=border,
        expand=True,
    )


def header_bar(
    elapsed: float,
    device_name: str = "",
    device_addr: str = "",
    status: str = "",
    battery: str = "",
    csv_path: str = "",
    csv_rows: int = 0,
    ecg_log_path: str = "",
    marker_legend: str = "",
) -> Text:
    """Build a one-line status bar for the dashboard title."""
    t = Text()
    if device_name:
        t.append(f"Device: {device_name} ", style="bold cyan")
    if device_addr:
        t.append(f"[{device_addr}]  ", style="dim cyan")
    if battery and battery != "-":
        t.append(f"Battery: {battery}  ", style="green")
    if status:
        t.append(
            f"Status: {status}  ",
            style="bold green" if "connected" in status.lower() else "bold yellow",
        )
    t.append(f"Elapsed: {elapsed:.1f}s", style="bold green")
    if csv_path and csv_path != "-":
        t.append(f"\nLog: {Path(csv_path).name} ({csv_rows} rows)", style="cyan")
    if ecg_log_path:
        t.append(f"\nECG: {Path(ecg_log_path).name}", style="green")
    if marker_legend:
        t.append(f"\nHotkeys: {marker_legend}", style="dim yellow")
    return t
