from __future__ import annotations

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

from polar_ble_sdk.connector.ble_discovery import discover_dual_polar_devices
from polar_ble_sdk.connector.stream import create_polar_connector
from polar_ble_sdk.dashboard_utils import (
    calculate_rmssd,
    draw_sparkline,
    read_battery,
    update_hz_for_state,
)

# Global stdout encoding fix for Windows to support sparklines
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
    except Exception:
        pass

# CSV column schemas — single source of truth for each device.
H10_CSV_COLUMNS = [
    "Timestamp",
    "HeartRate_BPM",
    "HRV_RMSSD_ms",
    "Battery",
    "ACC_X",
    "ACC_Y",
    "ACC_Z",
]
SENSE_CSV_COLUMNS = [
    "Timestamp",
    "HeartRate_BPM",
    "HRV_RMSSD_ms",
    "Battery",
    "PPG_Last",
    "ACC_X",
    "ACC_Y",
    "ACC_Z",
    "GYRO_X",
    "GYRO_Y",
    "GYRO_Z",
    "MAG_X",
    "MAG_Y",
    "MAG_Z",
]

# Global states
state_h10: dict[str, Any] = {
    "name": "Polar H10",
    "address": "-",
    "status": "Scanning...",
    "hr": 0,
    "rr_intervals": [],
    "hr_history": deque(maxlen=40),
    "rr_history": deque(maxlen=50),
    "acc_count": 0,
    "acc_hz": 0.0,
    "acc_last_sample": "-",
    "acc_raw": (0.0, 0.0, 0.0),
    "battery": "-",
    "csv_path": "-",
    "csv_rows_written": 0,
}

state_sense: dict[str, Any] = {
    "name": "Polar Sense",
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
    "mag_count": 0,
    "mag_hz": 0.0,
    "mag_last_sample": "-",
    "mag_raw": (0.0, 0.0, 0.0),
    "battery": "-",
    "csv_path": "-",
    "csv_rows_written": 0,
}

# Timestamp histories for Hz calculation
h10_acc_ts: deque[tuple[float, int]] = deque(maxlen=20)
sense_ppg_ts: deque[tuple[float, int]] = deque(maxlen=20)
sense_acc_ts: deque[tuple[float, int]] = deque(maxlen=20)
sense_gyro_ts: deque[tuple[float, int]] = deque(maxlen=20)
sense_mag_ts: deque[tuple[float, int]] = deque(maxlen=20)


# calculate_rmssd, draw_sparkline → imported from dashboard_utils


# Callbacks for H10
def hr_callback_h10(data):
    if isinstance(data, tuple) and len(data) >= 2:
        hr_val, rr_ints = data
        if hr_val > 0:
            state_h10["hr"] = hr_val
            state_h10["hr_history"].append(hr_val)
        if rr_ints:
            state_h10["rr_intervals"] = rr_ints
            state_h10["rr_history"].extend(rr_ints)


def acc_callback_h10(data):
    timestamp, samples = data
    state_h10["acc_count"] += len(samples)
    t = time.time()
    h10_acc_ts.append((t, len(samples)))
    last_val = samples[-1]
    state_h10["acc_raw"] = (last_val[0], last_val[1], last_val[2])
    state_h10["acc_last_sample"] = (
        f"({last_val[0]:+4d}, {last_val[1]:+4d}, {last_val[2]:+4d}) mg"
    )


# Callbacks for Verity Sense
def hr_callback_sense(data):
    if isinstance(data, tuple) and len(data) >= 2:
        hr_val, rr_ints = data
        if hr_val > 0:
            state_sense["hr"] = hr_val
            state_sense["hr_history"].append(hr_val)
        if rr_ints:
            state_sense["rr_intervals"] = rr_ints
            state_sense["rr_history"].extend(rr_ints)


def ppg_callback_sense(data):
    timestamp, samples = data
    state_sense["ppg_count"] += len(samples)
    t = time.time()
    sense_ppg_ts.append((t, len(samples)))
    state_sense["ppg_last_sample"] = str(samples[-1])


def acc_callback_sense(data):
    timestamp, samples = data
    state_sense["acc_count"] += len(samples)
    t = time.time()
    sense_acc_ts.append((t, len(samples)))
    last_val = samples[-1]
    state_sense["acc_raw"] = (last_val[0], last_val[1], last_val[2])
    state_sense["acc_last_sample"] = (
        f"({last_val[0]:+4d}, {last_val[1]:+4d}, {last_val[2]:+4d}) mg"
    )


def gyro_callback_sense(data):
    timestamp, samples = data
    state_sense["gyro_count"] += len(samples)
    t = time.time()
    sense_gyro_ts.append((t, len(samples)))
    last_val = samples[-1]
    state_sense["gyro_raw"] = (last_val[0], last_val[1], last_val[2])
    state_sense["gyro_last_sample"] = (
        f"({last_val[0]:+4.1f}, {last_val[1]:+4.1f}, {last_val[2]:+4.1f}) dps"
    )


def mag_callback_sense(data):
    timestamp, samples = data
    state_sense["mag_count"] += len(samples)
    t = time.time()
    sense_mag_ts.append((t, len(samples)))
    last_val = samples[-1]
    state_sense["mag_raw"] = (last_val[0], last_val[1], last_val[2])
    state_sense["mag_last_sample"] = (
        f"({last_val[0]:+3.1f}, {last_val[1]:+3.1f}, {last_val[2]:+3.1f}) uT"
    )


def update_hz():
    now = time.time()
    update_hz_for_state(state_h10, ("acc", h10_acc_ts), now=now)
    update_hz_for_state(
        state_sense,
        ("ppg", sense_ppg_ts),
        ("acc", sense_acc_ts),
        ("gyro", sense_gyro_ts),
        ("mag", sense_mag_ts),
        now=now,
    )


def build_device_panel(state: dict, is_h10: bool) -> Panel:
    # Heart Rate Color
    hr_color = "red"
    if state["hr"] > 90:
        hr_color = "bold red blink"
    elif state["hr"] > 55:
        hr_color = "bold green"

    rmssd = calculate_rmssd(state["rr_history"])

    hr_text = Text()
    if state["address"] == "-":
        hr_text.append("NOT FOUND", style="bold red")
    elif "connected" not in state["status"].lower():
        hr_text.append("WAITING...", style="bold yellow")
    else:
        hr_text.append(f"{state['hr']:3d}", style=hr_color)
        hr_text.append(" BPM", style="dim white")

    hrv_text = Text()
    if state["address"] == "-":
        hrv_text.append("N/A", style="bold red")
    else:
        hrv_text.append(f"{rmssd:5.1f}", style="bold magenta")
        hrv_text.append(" ms", style="dim white")

    metrics_table = Table.grid(expand=True)
    metrics_table.add_column(ratio=1)
    metrics_table.add_column(ratio=1)
    metrics_table.add_row(
        Panel(hr_text, title="Heart Rate", border_style="red", expand=True),
        Panel(hrv_text, title="HRV (RMSSD)", border_style="magenta", expand=True),
    )

    sparkline = draw_sparkline(state["hr_history"], width=30)
    spark_panel = Panel(
        Text(f"Trend: {sparkline}", style="bold red"),
        title="Heart Rate Realtime Trend",
        border_style="red",
        expand=True,
    )

    streams_table = Table(expand=True)
    streams_table.add_column("Stream", style="cyan")
    streams_table.add_column("Status", style="magenta")
    streams_table.add_column("Observed Rate", justify="right")
    streams_table.add_column("Latest Value/Sample", style="green", ratio=1)

    if state["address"] == "-":
        streams_table.add_row("-", "Inactive", "0.0 Hz", "-")
    elif is_h10:
        streams_table.add_row(
            "Standard HR",
            "Active" if state["hr"] > 0 else "Waiting...",
            "~1 Hz",
            f"HR={state['hr']} BPM, RR={list(state['rr_intervals'])[-2:]}",
        )
        acc_status = "Active" if state["acc_hz"] > 0 else "Inactive"
        streams_table.add_row(
            "ACC",
            acc_status,
            f"{state['acc_hz']:.1f} Hz",
            state["acc_last_sample"],
        )
    else:
        streams_table.add_row(
            "Standard HR",
            "Active" if state["hr"] > 0 else "Waiting...",
            "~1 Hz",
            f"HR={state['hr']} BPM, RR={list(state['rr_intervals'])[-2:]}",
        )
        ppg_status = "Active" if state["ppg_hz"] > 0 else "Inactive"
        streams_table.add_row(
            "PPG",
            ppg_status,
            f"{state['ppg_hz']:.1f} Hz",
            state["ppg_last_sample"],
        )
        acc_status = "Active" if state["acc_hz"] > 0 else "Inactive"
        streams_table.add_row(
            "ACC",
            acc_status,
            f"{state['acc_hz']:.1f} Hz",
            state["acc_last_sample"],
        )
        gyro_status = "Active" if state["gyro_hz"] > 0 else "Inactive"
        streams_table.add_row(
            "GYRO",
            gyro_status,
            f"{state['gyro_hz']:.1f} Hz",
            state["gyro_last_sample"],
        )
        mag_status = "Active" if state["mag_hz"] > 0 else "Inactive"
        streams_table.add_row(
            "MAG",
            mag_status,
            f"{state['mag_hz']:.1f} Hz",
            state["mag_last_sample"],
        )

    device_info = Text()
    device_info.append("Status: ", style="bold white")
    status_style = (
        "bold green"
        if "streaming" in state["status"].lower()
        or "connected" in state["status"].lower()
        else "bold yellow"
    )
    device_info.append(f"{state['status']}\n", style=status_style)
    device_info.append("Battery: ", style="bold white")
    device_info.append(f"{state['battery']}  |  ", style="green")
    device_info.append("CSV Rows: ", style="bold white")
    device_info.append(f"{state['csv_rows_written']}", style="cyan")

    group = Group(
        metrics_table,
        spark_panel,
        streams_table,
        Panel(device_info, border_style="dim white"),
    )
    border_color = "green" if "connected" in state["status"].lower() else "yellow"
    if state["address"] == "-":
        border_color = "red"
    return Panel(
        group,
        title=f"{state['name']} Dashboard",
        border_style=border_color,
        expand=True,
    )


def build_dual_dashboard(elapsed: float) -> Panel:
    update_hz()

    # Create side-by-side grid
    side_by_side = Table.grid(expand=True)
    side_by_side.add_column(ratio=1)
    side_by_side.add_column(ratio=1)
    side_by_side.add_row(
        build_device_panel(state_h10, is_h10=True),
        build_device_panel(state_sense, is_h10=False),
    )

    header_text = Text()
    header_text.append("Elapsed: ", style="bold white")
    header_text.append(f"{elapsed:.1f}s", style="bold green")

    return Panel(
        side_by_side,
        title="Dual Polar Device Live Terminal Dashboard",
        subtitle=header_text,
        border_style="cyan",
    )


async def _battery_loop(conn, state_dict):
    """Background battery refresh, updating the given state dict."""
    while True:
        if conn and conn.polar_device and conn.polar_device._client:
            state_dict["battery"] = await read_battery(conn)
        await asyncio.sleep(30)


async def main():
    parser = argparse.ArgumentParser(description="Dual Polar Terminal Dashboard")
    parser.add_argument("--h10", type=str, default=None, help="MAC/Name of H10 strap")
    parser.add_argument(
        "--sense", type=str, default=None, help="MAC/Name of Verity Sense"
    )
    parser.add_argument(
        "--no-log", action="store_true", help="Disable CSV logging completely"
    )
    args = parser.parse_args()

    # Discover devices
    state_h10["status"] = "Scanning for H10..."
    state_sense["status"] = "Scanning for Sense..."

    with Live(build_dual_dashboard(0.0), refresh_per_second=10) as live:
        h10_dev, sense_dev = await discover_dual_polar_devices(
            args.h10, args.sense, timeout=10.0
        )

        # Update address state
        if h10_dev:
            state_h10["address"] = h10_dev.address
            state_h10["status"] = "Device found, connecting..."
        else:
            state_h10["address"] = "-"
            state_h10["status"] = "Not found."

        if sense_dev:
            state_sense["address"] = sense_dev.address
            state_sense["status"] = "Device found, connecting..."
        else:
            state_sense["address"] = "-"
            state_sense["status"] = "Not found."

        live.update(build_dual_dashboard(0.0))

        if not h10_dev and not sense_dev:
            state_h10["status"] = "No Polar devices found."
            state_sense["status"] = "No Polar devices found."
            live.update(build_dual_dashboard(0.0))
            await asyncio.sleep(3)
            return

        conn_h10 = None
        conn_sense = None
        tasks = []

        # Setup H10
        if h10_dev:
            conn_h10 = create_polar_connector(
                h10_dev,
                callback=hr_callback_h10,
                acc_callback=acc_callback_h10,
                verbose=False,
            )
            tasks.append(conn_h10.start_notify())

        # Setup Sense
        if sense_dev:
            conn_sense = create_polar_connector(
                sense_dev,
                callback=hr_callback_sense,
                ppi_callback=lambda x: None,
                ppg_callback=ppg_callback_sense,
                acc_callback=acc_callback_sense,
                gyro_callback=gyro_callback_sense,
                mag_callback=mag_callback_sense,
                verbose=False,
            )
            tasks.append(conn_sense.start_notify())

        try:
            # Connect in parallel
            await asyncio.gather(*tasks)

            if conn_h10:
                state_h10["status"] = "Connected! Streaming data."
                state_h10["battery"] = await read_battery(conn_h10)

            if conn_sense:
                state_sense["status"] = "Connected! Streaming data."
                state_sense["battery"] = await read_battery(conn_sense)

            # Setup CSV loggers
            csv_path_h10 = None
            csv_path_sense = None
            log_dir = PROJECT_ROOT / "data"
            log_dir.mkdir(exist_ok=True)

            timestamp_str = time.strftime("%Y%m%d_%H%M%S")

            if not args.no_log:
                if conn_h10:
                    csv_path_h10 = log_dir / f"dual_session_h10_{timestamp_str}.csv"
                    state_h10["csv_path"] = str(csv_path_h10)
                    with open(
                        csv_path_h10, mode="w", newline="", encoding="utf-8"
                    ) as f:
                        csv.writer(f).writerow(H10_CSV_COLUMNS)

                if conn_sense:
                    csv_path_sense = log_dir / f"dual_session_sense_{timestamp_str}.csv"
                    state_sense["csv_path"] = str(csv_path_sense)
                    with open(
                        csv_path_sense, mode="w", newline="", encoding="utf-8"
                    ) as f:
                        csv.writer(f).writerow(SENSE_CSV_COLUMNS)

            # Battery update tasks
            battery_tasks = []
            if conn_h10:
                battery_tasks.append(
                    asyncio.create_task(_battery_loop(conn_h10, state_h10))
                )
            if conn_sense:
                battery_tasks.append(
                    asyncio.create_task(_battery_loop(conn_sense, state_sense))
                )

            start_time = time.time()
            last_log_time = start_time

            while True:
                elapsed = time.time() - start_time
                now = time.time()

                # Log metrics to CSV at 1 Hz
                if (now - last_log_time) >= 1.0:
                    last_log_time = now

                    # H10 CSV Log
                    if csv_path_h10:
                        ax, ay, az = (
                            state_h10["acc_raw"]
                            if state_h10["acc_count"] > 0
                            else (None, None, None)
                        )
                        try:
                            with open(
                                csv_path_h10, mode="a", newline="", encoding="utf-8"
                            ) as f:
                                writer = csv.writer(f)
                                writer.writerow(
                                    [
                                        time.strftime("%Y-%m-%d %H:%M:%S"),
                                        state_h10["hr"],
                                        calculate_rmssd(state_h10["rr_history"]),
                                        state_h10["battery"],
                                        ax,
                                        ay,
                                        az,
                                    ]
                                )
                            state_h10["csv_rows_written"] += 1
                        except Exception:
                            pass

                    # Sense CSV Log
                    if csv_path_sense:
                        ppg = state_sense["ppg_last_sample"]
                        ax, ay, az = (
                            state_sense["acc_raw"]
                            if state_sense["acc_count"] > 0
                            else (None, None, None)
                        )
                        gx, gy, gz = (
                            state_sense["gyro_raw"]
                            if state_sense["gyro_count"] > 0
                            else (None, None, None)
                        )
                        mx, my, mz = (
                            state_sense["mag_raw"]
                            if state_sense["mag_count"] > 0
                            else (None, None, None)
                        )
                        try:
                            with open(
                                csv_path_sense, mode="a", newline="", encoding="utf-8"
                            ) as f:
                                writer = csv.writer(f)
                                writer.writerow(
                                    [
                                        time.strftime("%Y-%m-%d %H:%M:%S"),
                                        state_sense["hr"],
                                        calculate_rmssd(state_sense["rr_history"]),
                                        state_sense["battery"],
                                        ppg,
                                        ax,
                                        ay,
                                        az,
                                        gx,
                                        gy,
                                        gz,
                                        mx,
                                        my,
                                        mz,
                                    ]
                                )
                            state_sense["csv_rows_written"] += 1
                        except Exception:
                            pass

                live.update(build_dual_dashboard(elapsed))
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            if conn_h10:
                state_h10["status"] = f"Error: {e}"
            if conn_sense:
                state_sense["status"] = f"Error: {e}"
            live.update(build_dual_dashboard(0.0))
            await asyncio.sleep(3)
        finally:
            if conn_h10:
                state_h10["status"] = "Disconnecting..."
            if conn_sense:
                state_sense["status"] = "Disconnecting..."
            live.update(build_dual_dashboard(0.0))

            for bt in battery_tasks:
                bt.cancel()

            cleanup_tasks = []
            if conn_h10:
                cleanup_tasks.append(conn_h10.stop_notify())
            if conn_sense:
                cleanup_tasks.append(conn_sense.stop_notify())

            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks)

            if conn_h10:
                state_h10["status"] = "Disconnected."
            if conn_sense:
                state_sense["status"] = "Disconnected."
            live.update(build_dual_dashboard(0.0))
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
