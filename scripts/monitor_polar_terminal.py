# ruff: noqa: E402
import argparse
import asyncio
import csv
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

# Add src/ directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from awe_polar.connector.ble_discovery import discover_polar_device
from awe_polar.connector.stream import create_polar_connector
from awe_polar.dashboard_utils import (
    BATTERY_SERVICE_UUID,
    CsvLogger,
    calculate_rmssd,
    draw_sparkline,
    read_battery,
    update_battery_loop,
    update_hz_for_state,
)

# Global stdout encoding fix for Windows to support sparklines and symbols
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
    except Exception:
        pass

# CSV column schema — single source of truth for header and row order.
CSV_COLUMNS = [
    "Timestamp",
    "HeartRate_BPM",
    "HRV_RMSSD_ms",
    "Battery_Percent",
    "ACC_X", "ACC_Y", "ACC_Z",
    "GYRO_X", "GYRO_Y", "GYRO_Z",
    "MAG_X", "MAG_Y", "MAG_Z",
    "Marker",
]

# Global state dictionary
state: dict[str, Any] = {
    "device_name": "Scanning...",
    "device_address": "-",
    "device_type": "-",
    "status": "Scanning for Polar Sense/H10...",
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
    "mag_count": 0,
    "mag_hz": 0.0,
    "mag_last_sample": "-",
    "mag_raw": (0.0, 0.0, 0.0),
    # State fields matching Nuanic design
    "battery": "-",
    "marker_log": deque(maxlen=5),
    "last_marker": "-",
    "csv_path": "-",
    "csv_rows_written": 0,
}

# Statistics counters
ppg_timestamps: deque[tuple[float, int]] = deque(maxlen=20)
acc_timestamps: deque[tuple[float, int]] = deque(maxlen=20)
gyro_timestamps: deque[tuple[float, int]] = deque(maxlen=20)
mag_timestamps: deque[tuple[float, int]] = deque(maxlen=20)


class _NonBlockingLineReader:
    """Non-blocking keyboard reader supporting hotkeys and text markers."""

    def __init__(self, hotkeys: dict) -> None:
        self._buffer = ""
        self._win_msvcrt = None
        self._last_space_ts = 0.0
        self._hotkeys = {key.upper(): value for key, value in hotkeys.items()}
        if sys.platform == "win32":
            import msvcrt

            self._win_msvcrt = msvcrt

    def poll_markers(self) -> list:
        markers = []
        if self._win_msvcrt is not None:
            while self._win_msvcrt.kbhit():
                ch = self._win_msvcrt.getwch()
                if ch == " ":
                    now = time.monotonic()
                    if (now - self._last_space_ts) >= 0.2:
                        marker = self._hotkeys.get("SPACE")
                        if marker:
                            markers.append(marker)
                        self._last_space_ts = now
                    continue
                if len(ch) == 1:
                    ch_upper = ch.upper()
                    marker = self._hotkeys.get(ch_upper)
                    if marker:
                        markers.append(marker)
                        continue
                    if ch in ("\r", "\n"):
                        line = self._buffer.strip()
                        self._buffer = ""
                        if line:
                            markers.append(line)
                    else:
                        self._buffer += ch
        else:
            # Fallback for UNIX-like platforms
            import select

            if select.select([sys.stdin], [], [], 0.0)[0]:
                line = sys.stdin.readline().strip()
                if line:
                    line_upper = line.upper()
                    if line_upper in self._hotkeys:
                        markers.append(self._hotkeys[line_upper])
                    else:
                        markers.append(line)
        return markers


def _parse_marker_specs(specs_str: str) -> dict:
    hotkeys = {
        "SPACE": "marker",
        "S": "stimulus_on",
        "B": "baseline_start",
        "R": "rest_start",
    }
    if not specs_str:
        return hotkeys
    parts = [p.strip() for p in specs_str.split(",") if p.strip()]
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip().upper()
            v = v.strip()
            if k and v:
                hotkeys[k] = v
    return hotkeys


def _format_marker_legend(hotkeys: dict) -> str:
    parts = []
    for key in sorted(hotkeys):
        parts.append(f"{key}={hotkeys[key]}")
    return " | ".join(parts)


# calculate_rmssd, draw_sparkline, update_hz → imported from dashboard_utils


def hr_callback(data):
    if isinstance(data, tuple) and len(data) >= 2:
        hr_val, rr_ints = data
        if hr_val > 0:
            state["hr"] = hr_val
            state["hr_history"].append(hr_val)
        if rr_ints:
            state["rr_intervals"] = rr_ints
            state["rr_history"].extend(rr_ints)


def ppg_callback(data):
    timestamp, samples = data
    state["ppg_count"] += len(samples)
    t = time.time()
    ppg_timestamps.append((t, len(samples)))
    state["ppg_last_sample"] = str(samples[-1])


def acc_callback(data):
    timestamp, samples = data
    state["acc_count"] += len(samples)
    t = time.time()
    acc_timestamps.append((t, len(samples)))
    last_val = samples[-1]
    state["acc_raw"] = (last_val[0], last_val[1], last_val[2])
    state["acc_last_sample"] = (
        f"({last_val[0]:+4d}, {last_val[1]:+4d}, {last_val[2]:+4d}) mg"
    )


def gyro_callback(data):
    timestamp, samples = data
    state["gyro_count"] += len(samples)
    t = time.time()
    gyro_timestamps.append((t, len(samples)))
    last_val = samples[-1]
    state["gyro_raw"] = (last_val[0], last_val[1], last_val[2])
    state["gyro_last_sample"] = (
        f"({last_val[0]:+4.1f}, {last_val[1]:+4.1f}, {last_val[2]:+4.1f}) dps"
    )


def mag_callback(data):
    timestamp, samples = data
    state["mag_count"] += len(samples)
    t = time.time()
    mag_timestamps.append((t, len(samples)))
    last_val = samples[-1]
    state["mag_raw"] = (last_val[0], last_val[1], last_val[2])
    state["mag_last_sample"] = (
        f"({last_val[0]:+3.1f}, {last_val[1]:+3.1f}, {last_val[2]:+3.1f}) uT"
    )


def update_hz():
    update_hz_for_state(
        state,
        ("ppg", ppg_timestamps),
        ("acc", acc_timestamps),
        ("gyro", gyro_timestamps),
        ("mag", mag_timestamps),
    )


def build_dashboard(elapsed_time: float, marker_legend: str = "") -> Panel:
    update_hz()
    rmssd = calculate_rmssd(state["rr_history"])

    # 1. Device Info Header Panel
    device_info = Text()
    device_info.append("Device: ", style="bold white")
    device_info.append(f"{state['device_name']} ", style="bold cyan")
    device_info.append(f"[{state['device_address']}]  |  ", style="dim cyan")

    # Show Battery
    device_info.append("Battery: ", style="bold white")
    bat_style = "bold green" if state["battery"] != "-" else "dim white"
    device_info.append(f"{state['battery']}  |  ", style=bat_style)

    device_info.append("Connection: ", style="bold white")
    status_style = (
        "bold green"
        if "streaming" in state["status"].lower()
        or "connected" in state["status"].lower()
        else "bold yellow"
    )
    device_info.append(f"{state['status']}  |  ", style=status_style)

    device_info.append("Elapsed: ", style="bold white")
    device_info.append(f"{elapsed_time:.1f}s", style="bold green")

    # Add CSV info in device header if active
    if state["csv_path"] != "-":
        device_info.append("\nLog: ", style="bold white")
        device_info.append(f"{Path(state['csv_path']).name} ", style="cyan")
        device_info.append(f"({state['csv_rows_written']} rows written)", style="green")

    # 2. Main Metrics columns
    hr_color = "red"
    if state["hr"] > 90:
        hr_color = "bold red blink"
    elif state["hr"] > 55:
        hr_color = "bold green"

    hr_text = Text()
    hr_text.append(f"{state['hr']:3d}", style=hr_color)
    hr_text.append(" BPM", style="dim white")

    hrv_text = Text()
    hrv_text.append(f"{rmssd:5.1f}", style="bold magenta")
    hrv_text.append(" ms (RMSSD)", style="dim white")

    metrics_table = Table.grid(expand=True)
    metrics_table.add_column(ratio=1)
    metrics_table.add_column(ratio=1)
    metrics_table.add_row(
        Panel(hr_text, title="Heart Rate", border_style="red", expand=True),
        Panel(hrv_text, title="HRV (RMSSD)", border_style="magenta", expand=True),
    )

    # 3. Heart Rate Graph (Sparkline) & Event Markers Side-by-Side
    sparkline = draw_sparkline(state["hr_history"], width=45)
    spark_text = Text(f"Trend: {sparkline}", style="bold red")
    spark_panel = Panel(
        spark_text, title="Heart Rate Realtime Trend", border_style="red", expand=True
    )

    marker_text = Text()
    marker_text.append("Active Legend: ", style="bold white")
    marker_text.append(f"{marker_legend}\n", style="dim yellow")
    marker_text.append("Last Marker: ", style="bold white")
    marker_text.append(
        f"{state['last_marker']}\n",
        style="bold green" if state["last_marker"] != "-" else "dim white",
    )
    marker_text.append("Recent logs:\n", style="bold white")
    for log in list(state["marker_log"])[-3:]:
        marker_text.append(f"  {log}\n", style="dim yellow")

    marker_panel = Panel(
        marker_text, title="Event Markers (Hotkeys)", border_style="yellow", expand=True
    )

    side_by_side = Table.grid(expand=True)
    side_by_side.add_column(ratio=2)
    side_by_side.add_column(ratio=1)
    side_by_side.add_row(spark_panel, marker_panel)

    # 4. Sensor streams details table
    streams_table = Table(expand=True)
    streams_table.add_column("Stream", style="cyan")
    streams_table.add_column("Status", style="magenta")
    streams_table.add_column("Observed Rate", justify="right")
    streams_table.add_column("Latest Value/Sample", style="green", ratio=2)

    # Standard HR Row
    streams_table.add_row(
        "Standard HR",
        "Active" if state["hr"] > 0 else "Waiting...",
        "~1 Hz",
        f"Heart Rate={state['hr']} BPM, RR={list(state['rr_intervals'])[-3:]}",
    )

    # PPG Row
    ppg_status = "Active" if state["ppg_hz"] > 0 else "Inactive"
    streams_table.add_row(
        "Photoplethysmography (PPG)",
        ppg_status,
        f"{state['ppg_hz']:.1f} Hz",
        state["ppg_last_sample"],
    )

    # ACC Row
    acc_status = "Active" if state["acc_hz"] > 0 else "Inactive"
    streams_table.add_row(
        "Accelerometer (ACC)",
        acc_status,
        f"{state['acc_hz']:.1f} Hz",
        state["acc_last_sample"],
    )

    # Gyro Row
    gyro_status = "Active" if state["gyro_hz"] > 0 else "Inactive"
    streams_table.add_row(
        "Gyroscope (GYRO)",
        gyro_status,
        f"{state['gyro_hz']:.1f} Hz",
        state["gyro_last_sample"],
    )

    # Mag Row
    mag_status = "Active" if state["mag_hz"] > 0 else "Inactive"
    streams_table.add_row(
        "Magnetometer (MAG)",
        mag_status,
        f"{state['mag_hz']:.1f} Hz",
        state["mag_last_sample"],
    )

    group = Group(metrics_table, side_by_side, streams_table)

    return Panel(
        group,
        title="Polar Device Live Terminal Dashboard",
        subtitle=device_info,
        border_style="cyan",
    )


async def _battery_loop(conn):
    """Background battery refresh, updating the module-level ``state`` dict."""
    while True:
        if conn and conn.polar_device and conn.polar_device._client:
            state["battery"] = await read_battery(conn)
        await asyncio.sleep(30)


async def main():
    parser = argparse.ArgumentParser(description="Live Polar Terminal Dashboard")
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Custom path to save CSV log file. Defaults to auto-generated path in data/",
    )
    parser.add_argument(
        "--no-log", action="store_true", help="Disable CSV logging completely"
    )
    parser.add_argument(
        "--markers",
        type=str,
        default=None,
        help="Custom markers format: KEY=LABEL,KEY2=LABEL2",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Name or MAC address of a specific Polar device to connect to",
    )
    args = parser.parse_args()

    # Marker configuration
    hotkeys = _parse_marker_specs(args.markers)
    marker_legend = _format_marker_legend(hotkeys)
    input_reader = _NonBlockingLineReader(hotkeys)

    # Scan and find device
    if args.device:
        state["status"] = f"Scanning for device matching '{args.device}'..."
    else:
        state["status"] = "Scanning for Polar devices (Sense/H10/OH1)..."

    with Live(build_dashboard(0.0, marker_legend), refresh_per_second=10) as live:
        device = await discover_polar_device(args.device, timeout=20.0)

        if not device:
            if args.device:
                state["status"] = f"Error: Device matching '{args.device}' not found!"
            else:
                state["status"] = "Error: No Polar device found!"
            live.update(build_dashboard(0.0, marker_legend))
            await asyncio.sleep(2)
            return

        state["device_name"] = device.name
        state["device_address"] = device.address
        state["status"] = "Connecting..."
        live.update(build_dashboard(0.0, marker_legend))

        conn = create_polar_connector(
            device,
            callback=hr_callback,
            ppi_callback=lambda x: None,  # PPI stream active to redirect HR on Sense
            ppg_callback=ppg_callback,
            acc_callback=acc_callback,
            gyro_callback=gyro_callback,
            mag_callback=mag_callback,
        )

        state["device_type"] = conn.__class__.__name__

        battery_task = None
        try:
            await conn.start_notify()
            state["status"] = "Connected! Streaming live data."

            # Read battery once immediately
            state["battery"] = await read_battery(conn)

            # Initialize CSV Logger
            csv_path = None
            if not args.no_log:
                log_dir = PROJECT_ROOT / "data"
                log_dir.mkdir(exist_ok=True)

                if args.csv:
                    csv_path = Path(args.csv)
                else:
                    csv_filename = f"polar_session_{time.strftime('%Y%m%d_%H%M%S')}.csv"
                    csv_path = log_dir / csv_filename

                state["csv_path"] = str(csv_path)
                state["csv_rows_written"] = 0

                # Write header
                with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(CSV_COLUMNS)

            # Start background battery update loop
            battery_task = asyncio.create_task(_battery_loop(conn))

            start_time = time.time()
            last_log_time = start_time

            while True:
                elapsed = time.time() - start_time

                # Poll keyboard input for markers
                pressed_markers = input_reader.poll_markers()
                active_marker = ""
                if pressed_markers:
                    for m in pressed_markers:
                        timestamp_str = time.strftime("%H:%M:%S")
                        state["marker_log"].append(f"{timestamp_str} - {m}")
                        state["last_marker"] = m
                        active_marker = m

                # Log metrics to CSV at 1 Hz
                now = time.time()
                if csv_path and (now - last_log_time) >= 1.0:
                    last_log_time = now

                    acc_x, acc_y, acc_z = (
                        state["acc_raw"]
                        if state["acc_count"] > 0
                        else (None, None, None)
                    )
                    gyro_x, gyro_y, gyro_z = (
                        state["gyro_raw"]
                        if state["gyro_count"] > 0
                        else (None, None, None)
                    )
                    mag_x, mag_y, mag_z = (
                        state["mag_raw"]
                        if state["mag_count"] > 0
                        else (None, None, None)
                    )

                    try:
                        with open(
                            csv_path, mode="a", newline="", encoding="utf-8"
                        ) as f:
                            writer = csv.writer(f)
                            writer.writerow(
                                [
                                    time.strftime("%Y-%m-%d %H:%M:%S"),
                                    state["hr"],
                                    calculate_rmssd(state["rr_history"]),
                                    state["battery"],
                                    acc_x,
                                    acc_y,
                                    acc_z,
                                    gyro_x,
                                    gyro_y,
                                    gyro_z,
                                    mag_x,
                                    mag_y,
                                    mag_z,
                                    active_marker,
                                ]
                            )
                        state["csv_rows_written"] += 1
                    except Exception:
                        pass

                live.update(build_dashboard(elapsed, marker_legend))
                await asyncio.sleep(0.1)  # Refresh dashboard at 10 Hz

        except asyncio.CancelledError:
            pass
        except Exception as e:
            state["status"] = f"Error: {e}"
            live.update(build_dashboard(0.0, marker_legend))
            await asyncio.sleep(3)
        finally:
            state["status"] = "Disconnecting..."
            live.update(build_dashboard(0.0, marker_legend))
            if battery_task:
                battery_task.cancel()
            await conn.stop_notify()
            state["status"] = "Disconnected."
            live.update(build_dashboard(0.0, marker_legend))
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
