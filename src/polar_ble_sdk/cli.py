from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections import deque
from pathlib import Path

from rich.live import Live
from rich.panel import Panel

from polar_ble_sdk.connector.ble_discovery import discover_polar_device
from polar_ble_sdk.connector.stream import create_polar_connector
from polar_ble_sdk.dashboard_utils import (
    CsvLogger,
    calculate_rmssd,
    device_panel,
    header_bar,
    make_device_state,
    read_battery,
    feed_hr,
    make_callback,
    update_hz_for_state,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

CSV_COLUMNS = [
    "Timestamp",
    "HeartRate_BPM",
    "HRV_RMSSD_ms",
    "Battery_Percent",
    "ACC_X",
    "ACC_Y",
    "ACC_Z",
    "GYRO_X",
    "GYRO_Y",
    "GYRO_Z",
    "MAG_X",
    "MAG_Y",
    "MAG_Z",
    "Marker",
]

state = make_device_state("Polar Device")

_ppg_ts: deque[tuple[float, int]] = deque(maxlen=20)
_acc_ts: deque[tuple[float, int]] = deque(maxlen=20)
_gyro_ts: deque[tuple[float, int]] = deque(maxlen=20)
_mag_ts: deque[tuple[float, int]] = deque(maxlen=20)


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
            k, v = k.strip().upper(), v.strip()
            if k and v:
                hotkeys[k] = v
    return hotkeys


def _format_marker_legend(hotkeys: dict) -> str:
    return " | ".join(f"{k}={hotkeys[k]}" for k in sorted(hotkeys))


# ── Callbacks (closures created once at module level) ──────────────────

_hr_cb = lambda data: feed_hr(data, state)  # noqa: E731
_ppg_cb = make_callback(state, _ppg_ts, "ppg")
_acc_cb = make_callback(state, _acc_ts, "acc")
_gyro_cb = make_callback(state, _gyro_ts, "gyro")
_mag_cb = make_callback(state, _mag_ts, "mag")


# ── CSV helpers ────────────────────────────────────────────────────────


def _unwrap_triple(raw_key: str, count_key: str) -> list:
    val = state.get(raw_key) if state.get(count_key, 0) > 0 else (None, None, None)
    assert isinstance(val, tuple) and len(val) == 3
    return [val[0], val[1], val[2]]


def _make_row(rmssd: float, active_marker: str) -> list:
    return [
        time.strftime("%Y-%m-%d %H:%M:%S"),
        state["hr"],
        rmssd,
        state.get("battery"),
        *_unwrap_triple("acc_raw", "acc_count"),
        *_unwrap_triple("gyro_raw", "gyro_count"),
        *_unwrap_triple("mag_raw", "mag_count"),
        active_marker,
    ]


# ── Battery loop ──────────────────────────────────────────────────────


async def _battery_loop(conn):
    while True:
        if conn and conn.polar_device and conn.polar_device._client:
            state["battery"] = await read_battery(conn)
        await asyncio.sleep(30)


# ── Main ──────────────────────────────────────────────────────────────


async def main():
    parser = argparse.ArgumentParser(description="Live Polar Terminal Dashboard")
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Custom CSV path. Defaults to auto-generated in data/",
    )
    parser.add_argument("--no-log", action="store_true", help="Disable CSV logging")
    parser.add_argument(
        "--markers",
        type=str,
        default=None,
        help="Custom hotkeys: KEY=LABEL,KEY2=LABEL2",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Name or MAC of a specific Polar device",
    )
    for opt in (
        "acc-rate",
        "acc-range",
        "gyro-rate",
        "gyro-range",
        "mag-rate",
        "ppg-rate",
    ):
        parser.add_argument(
            f"--{opt}", type=int, default=None, help=f"Custom {opt} (Hz)"
        )
    args = parser.parse_args()

    hotkeys = _parse_marker_specs(args.markers)
    marker_legend = _format_marker_legend(hotkeys)
    reader = _NonBlockingLineReader(hotkeys)

    state["status"] = (
        f"Scanning for device matching '{args.device}'..."
        if args.device
        else "Scanning for Polar devices (Sense/H10/OH1)..."
    )

    start = time.time()
    with Live(
        Panel(
            device_panel(state, is_h10=False, marker_legend=marker_legend),
            title="Polar Device Live Terminal Dashboard",
            subtitle=header_bar(
                0.0, status=state["status"], marker_legend=marker_legend
            ),
            border_style="cyan",
        ),
        refresh_per_second=10,
    ) as live:
        device = await discover_polar_device(args.device, timeout=20.0)
        if not device:
            state["status"] = "Error: No Polar device found!"
            live.update(Panel(device_panel(state, is_h10=False), border_style="cyan"))
            await asyncio.sleep(2)
            return

        state["device_name"] = device.name or ""
        state["device_address"] = device.address
        state["status"] = "Connecting..."
        live.update(Panel(device_panel(state, is_h10=False), border_style="cyan"))

        custom_kwargs = {
            k: v
            for k, v in {
                "acc_sample_rate": args.acc_rate,
                "acc_range": args.acc_range,
                "gyro_sample_rate": args.gyro_rate,
                "gyro_range": args.gyro_range,
                "mag_sample_rate": args.mag_rate,
                "ppg_sample_rate": args.ppg_rate,
            }.items()
            if v is not None
        }

        conn = create_polar_connector(
            device,
            callback=_hr_cb,
            ppi_callback=lambda x: None,
            ppg_callback=_ppg_cb,
            acc_callback=_acc_cb,
            gyro_callback=_gyro_cb,
            mag_callback=_mag_cb,
            verbose=False,
            **custom_kwargs,
        )

        last_log = start
        battery_task = None

        def build():
            elapsed = time.time() - start
            update_hz_for_state(
                state,
                ("ppg", _ppg_ts),
                ("acc", _acc_ts),
                ("gyro", _gyro_ts),
                ("mag", _mag_ts),
            )
            return Panel(
                device_panel(state, is_h10=False, marker_legend=marker_legend),
                title="Polar Device Live Terminal Dashboard",
                subtitle=header_bar(
                    elapsed,
                    device_name=state["device_name"],
                    device_addr=state["device_address"],
                    status=state["status"],
                    battery=state["battery"],
                    csv_path=state["csv_path"],
                    csv_rows=state["csv_rows_written"],
                    marker_legend=marker_legend,
                ),
                border_style="cyan",
            )

        try:
            await conn.start_notify()
            state["status"] = "Connected! Streaming live data."
            state["battery"] = await read_battery(conn)

            csv_logger = None
            if not args.no_log:
                log_dir = PROJECT_ROOT / "data"
                log_dir.mkdir(exist_ok=True)
                path = (
                    Path(args.csv)
                    if args.csv
                    else log_dir / f"polar_session_{time.strftime('%Y%m%d_%H%M%S')}.csv"
                )
                csv_logger = CsvLogger(path, CSV_COLUMNS)
                csv_logger.write_header()
                state["csv_path"] = csv_logger.path_str

            battery_task = asyncio.create_task(_battery_loop(conn))

            while True:
                active_marker = ""
                for m in reader.poll_markers():
                    ts = time.strftime("%H:%M:%S")
                    state["marker_log"].append(f"{ts} - {m}")
                    state["last_marker"] = m
                    active_marker = m

                now = time.time()
                if csv_logger and (now - last_log) >= 1.0:
                    last_log = now
                    csv_logger.write_row(
                        _make_row(calculate_rmssd(state["rr_history"]), active_marker)
                    )
                    state["csv_rows_written"] = csv_logger.rows_written

                live.update(build())
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            state["status"] = f"Error: {e}"
            live.update(build())
            await asyncio.sleep(3)
        finally:
            state["status"] = "Disconnecting..."
            live.update(build())
            if battery_task:
                battery_task.cancel()
            await conn.stop_notify()
            state["status"] = "Disconnected."
            live.update(build())
            await asyncio.sleep(1)


def _entrypoint() -> None:
    """Console-script entry point: run async main with a clean KeyboardInterrupt handler."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
