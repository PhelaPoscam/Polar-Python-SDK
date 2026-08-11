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

# ── Logging constants ─────────────────────────────────────────────────

SEVERITY_ICONS = {
    "info": "·",
    "success": "●",
    "warning": "▲",
    "error": "✖",
}

SEVERITY_STYLES = {
    "info": "dim white",
    "success": "green",
    "warning": "yellow",
    "error": "bold red",
}


def log_event(
    log_panel: LogPanel,
    msg: str,
    severity: str = "info",
    *,
    device: str = "",
    log_file: Any = None,
) -> None:
    """Format a log line and push it to the LogPanel (and optionally a file)."""
    ts = time.strftime("%H:%M:%S")
    icon = SEVERITY_ICONS.get(severity, "·")
    prefix = f"[{device}] " if device else ""
    styled = Text.assemble(
        (f"{ts} ", "dim"),
        (f"{icon} ", SEVERITY_STYLES.get(severity, "dim white")),
        (f"{prefix}{msg}", SEVERITY_STYLES.get(severity, "dim white")),
    )
    log_panel.push(styled)
    if log_file:
        try:
            log_file.write(f"{ts} [{severity.upper()}] {prefix}{msg}\n")
            log_file.flush()
        except OSError:
            pass


# ── Rolling log panel ────────────────────────────────────────────────


class LogPanel:
    """Rolling tail of styled log lines with severity filtering."""

    def __init__(self, max_lines: int = 200) -> None:
        self._lines: deque[Text] = deque(maxlen=max_lines)
        self._level: str = "moderate"

    @property
    def level(self) -> str:
        return self._level

    def set_level(self, level: str) -> None:
        self._level = level

    def cycle_level(self) -> str:
        """Toggle between moderate and verbose. Returns the new level."""
        self._level = "verbose" if self._level == "moderate" else "moderate"
        return self._level

    def push(self, styled_line: Text) -> None:
        self._lines.append(styled_line)

    def _visible(self) -> list[Text]:
        if self._level == "minimal":
            return [ln for ln in self._lines if not ln.plain.startswith("· ")]
        return list(self._lines)

    def render(self, height: int | None = None) -> Panel:
        visible = self._visible()
        if height is not None:
            visible = visible[-height:] if len(visible) > height else visible
        if not visible:
            visible = [Text("  waiting for events...", style="dim")]
        return Panel(
            Group(*visible),
            title="Log",
            border_style="dim white",
            expand=True,
        )


# ── Constants ─────────────────────────────────────────────────────────

BATTERY_SERVICE_UUID = "00002a19-0000-1000-8000-00805f9b34fb"


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
        # Session-level accumulators for Hz verification (survive deque rotation)
        "_session_streams": {},
    }


# ── Generic callbacks (feed state from BLE data) ─────────────────────


def _track_session(state: dict[str, Any], stream: str, sample_count: int) -> None:
    """Increment session-level accumulators for Hz verification."""
    now = time.time()
    acc = state["_session_streams"].setdefault(
        stream, {"samples": 0, "first_ts": now, "last_ts": now}
    )
    acc["samples"] += sample_count
    acc["last_ts"] = now


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
    _track_session(state, "ppg", len(samples))


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
    _track_session(state, "acc", len(samples))


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
    _track_session(state, "gyro", len(samples))


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
    _track_session(state, "mag", len(samples))


def feed_ecg(data, state: dict[str, Any], ts: deque) -> None:
    """Update *state* and *ts* deque from ECG callback data."""
    _timestamp, samples = data
    state["ecg_count"] += len(samples)
    ts.append((time.time(), len(samples)))
    last_val = samples[-1]
    state["ecg_last_sample"] = f"{last_val:+5d} µV"
    _track_session(state, "ecg", len(samples))


def feed_ppi(data, state: dict[str, Any], ts: deque) -> None:
    """Update *state* and *ts* deque from PPI callback data.

    data is a list of (timestamp_ns, ppi_ms) tuples.

    The PPI stream is the Verity Sense's source of pulse-to-pulse intervals
    (the HR stream carries an empty RR list), so feed the RR deques too —
    this is what populates RMSSD and the dashboard RR display.
    """
    if data:
        state["ppi_count"] += len(data)
        ts.append((time.time(), len(data)))
        state["ppi_last_sample"] = f"PPI={data[-1][1]} ms"
        _track_session(state, "ppi", len(data))
        ppi_ms = [float(ppi) for _ts, ppi in data if ppi is not None and ppi > 0]
        if ppi_ms:
            state["rr_intervals"] = ppi_ms
            state["rr_history"].extend(ppi_ms)


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


# ── Session Hz summary ────────────────────────────────────────────────


def compute_session_hz(state: dict[str, Any], stream: str) -> float:
    """Compute average Hz over the full session from session accumulators.

    Returns 0.0 if insufficient data.
    """
    acc = state["_session_streams"].get(stream)
    if not acc or acc["last_ts"] <= acc["first_ts"]:
        return 0.0
    return acc["samples"] / (acc["last_ts"] - acc["first_ts"])


def print_hz_summary(
    configured: dict[str, int],
    state: dict[str, Any],
) -> None:
    """Print a session-end Hz summary table comparing configured vs actual rates."""
    print("\n" + "=" * 56)
    print("  SESSION HZ VERIFICATION")
    print("=" * 56)
    print(f"  {'Stream':<8} {'Configured':>10} {'Observed':>10} {'Match':>8}")
    print("-" * 56)
    for name, cfg_rate in configured.items():
        actual = compute_session_hz(state, name)
        match = "OK" if abs(actual - cfg_rate) / max(cfg_rate, 1) < 0.05 else "X"
        print(f"  {name:<8} {cfg_rate:>8} Hz {actual:>8.2f} Hz {match:>8}")
    print("=" * 56 + "\n")


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


# ── Full-resolution frame CSV logger ────────────────────────────────────


class StreamFrameLogger:
    """Writes PMD/HR/PPI frames to a CSV file inside the session directory."""

    _COLUMNS: dict[str, list[str]] = {
        "ecg": ["Timestamp_s", "uV_Samples"],
        "ppg": ["Timestamp_s", "Sample_Channels"],
        "acc": ["Timestamp_s", "X_mG", "Y_mG", "Z_mG"],
        "gyro": ["Timestamp_s", "X_dps", "Y_dps", "Z_dps"],
        "mag": ["Timestamp_s", "X_G", "Y_G", "Z_G"],
        "hr": ["Timestamp_s", "HeartRate_BPM", "RR_Intervals_ms"],
        "ppi": ["Timestamp_s", "PPI_ms"],
    }

    _WIDE_COLUMNS: set[str] = {"ecg", "ppg"}

    def __init__(self, path: Path, stream: str) -> None:
        self._path = path
        self._stream = stream
        self._writer: Any = None
        self._file: Any = None
        self._first_ts_ns: int | None = None
        self._ppi_cumulative_s: float = 0.0

    def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self._path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)  # type: ignore[arg-type]
        self._writer.writerow(self._COLUMNS[self._stream])

    def write_frame(self, timestamp_ns: int, data) -> None:
        if not self._writer:
            return
        if self._first_ts_ns is None:
            self._first_ts_ns = timestamp_ns
        rel_s = (timestamp_ns - self._first_ts_ns) / 1e9
        if self._stream == "hr":
            hr_val, rr_list = data
            rr_str = ";".join(f"{rr:.1f}" for rr in rr_list) if rr_list else ""
            self._writer.writerow([f"{rel_s:.3f}", hr_val, rr_str])
        elif self._stream in self._WIDE_COLUMNS:
            self._writer.writerow([f"{rel_s:.3f}", *data])
        else:
            for sample in data:
                self._writer.writerow([f"{rel_s:.3f}", *sample])

    def write_ppi_frames(self, data) -> None:
        if not self._writer:
            return
        for _ppi_ts_ns, ppi_val in data:
            self._writer.writerow([f"{self._ppi_cumulative_s:.3f}", ppi_val])
            self._ppi_cumulative_s += ppi_val / 1000.0

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
            self._writer = None

    @property
    def path_str(self) -> str:
        return str(self._path)


def make_frame_callback(dashboard_cb, frame_logger: StreamFrameLogger):
    """Wrap a dashboard callback to also log full-res frames."""

    def cb(data):
        dashboard_cb(data)
        timestamp, samples = data
        frame_logger.write_frame(timestamp, samples)

    return cb


def make_ppi_callback(dashboard_cb, frame_logger: StreamFrameLogger):
    """Wrap a PPI dashboard callback to also log full-res frames."""

    def cb(data):
        dashboard_cb(data)
        frame_logger.write_ppi_frames(data)

    return cb


# ── Dashboard rendering ────────────────────────────────────────────────


def device_panel(
    state: dict[str, Any],
    is_h10: bool,
    _rmssd: float | None = None,
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

    group = Group(metrics, streams)
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
    device_name: str = "",
    device_addr: str = "",
    status: str = "",
) -> Text:
    """Build a slim identity strip: name, address, connection status."""
    t = Text()
    if device_name:
        t.append(device_name, style="bold cyan")
    if device_addr:
        t.append(f" ({device_addr})", style="dim cyan")
    if status:
        dot = "●" if "connected" in status.lower() else "○"
        style = "bold green" if "connected" in status.lower() else "bold yellow"
        t.append(f"  {dot} {status}", style=style)
    return t


def info_bar(
    elapsed: float,
    battery: str = "",
    csv_path: str = "",
    csv_rows: int = 0,
    marker_legend: str = "",
    log_level: str = "moderate",
) -> Panel:
    """Build a compact status footer: battery, elapsed, CSV stats, hotkeys."""
    t = Text()
    if battery and battery != "-":
        t.append(f"🔋 {battery}", style="green")
    t.append(f"  ⏱ {elapsed:.1f}s", style="bold green")
    if csv_path and csv_path != "-":
        t.append(f"  📄 {Path(csv_path).name} ({csv_rows} rows)", style="cyan")
    if marker_legend:
        t.append(f"  ⌨ {marker_legend}", style="dim yellow")
    t.append(f"  L:Log({log_level[0].upper()})", style="dim yellow")
    return Panel(t, border_style="dim white", expand=True)


# ── RSSI polling loop ─────────────────────────────────────────────────


async def _read_rssi(client) -> int | None:
    """Read RSSI from a BleakClient, trying public API then WinRT backend."""
    # bleak 3.x removed get_rssi() from the public API
    if hasattr(client, "get_rssi"):
        return await client.get_rssi()
    # WinRT backend stores RSSI on the BLEDevice object
    backend = getattr(client, "_backend", None)
    if backend and hasattr(backend, "_notification_callbacks"):
        # Try the device's RSSI property via the WinRT BLEDevice
        ble_device = getattr(client, "_device", None)
        if ble_device and hasattr(ble_device, "rssi"):
            return ble_device.rssi
    return None


async def rssi_loop(
    conn,
    log_panel: LogPanel,
    *,
    device: str = "",
    log_file: Any = None,
) -> None:
    """Periodically read RSSI and log it. Interval adapts to verbosity."""
    # One-time probe to check if RSSI is available
    client = getattr(conn.polar_device, "_client", None) if conn.polar_device else None
    if not client:
        return
    rssi = await _read_rssi(client)
    if rssi is None:
        log_event(
            log_panel,
            "RSSI not available (bleak 3.x — get_rssi removed)",
            "warning",
            device=device,
            log_file=log_file,
        )
        return

    log_event(
        log_panel,
        f"RSSI: {rssi} dBm",
        "info",
        device=device,
        log_file=log_file,
    )
    while True:
        interval = 5.0 if log_panel.level == "verbose" else 30.0
        await asyncio.sleep(interval)
        try:
            rssi = await _read_rssi(client)
            if rssi is not None:
                log_event(
                    log_panel,
                    f"RSSI: {rssi} dBm",
                    "info",
                    device=device,
                    log_file=log_file,
                )
        except Exception:
            pass


# ── Frame count logger (verbose only) ─────────────────────────────────


class FrameCountLogger:
    """Tracks per-stream frame counts and emits verbose log events on delta."""

    def __init__(
        self,
        log_panel: LogPanel,
        *,
        device: str = "",
        log_file: Any = None,
    ) -> None:
        self._log_panel = log_panel
        self._device = device
        self._log_file = log_file
        self._prev: dict[str, int] = {}

    def check(self, state: dict[str, Any], enabled_streams: list[str]) -> None:
        """Compare current counts to previous, log deltas for active streams."""
        stream_count_keys = {
            "ecg": "ecg_count",
            "ppg": "ppg_count",
            "acc": "acc_count",
            "gyro": "gyro_count",
            "mag": "mag_count",
            "ppi": "ppi_count",
            "hr": None,  # HR doesn't have a count key in state
        }
        for stream in enabled_streams:
            key = stream_count_keys.get(stream)
            if key is None:
                continue
            current = state.get(key, 0)
            if stream not in self._prev:
                # Prime the baseline so the first delta is not a huge burst.
                self._prev[stream] = current
                continue
            prev = self._prev[stream]
            delta = current - prev
            if delta > 0:
                log_event(
                    self._log_panel,
                    f"{stream.upper()} +{delta} frames",
                    "info",
                    device=self._device,
                    log_file=self._log_file,
                )
            self._prev[stream] = current
