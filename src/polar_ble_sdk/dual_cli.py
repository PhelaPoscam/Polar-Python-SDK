"""Dual-device terminal dashboard for simultaneous recording of Polar H10 + Verity Sense."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from .cli_common import (
    LOG_TOGGLE,
    add_common_args,
    apply_rate_overrides,
    build_stream_callbacks,
    run_cli,
    run_dashboard,
    save_on_console_close,
    stream_setting_kwargs,
)
from .connector.adapter import PolarAdapter
from .connector.ble_discovery import discover_dual_polar_devices
from .diagnostics.battery import read_battery, update_battery_loop
from .diagnostics.rssi import FrameCountLogger, rssi_loop
from .input.keyboard import NonBlockingKeyboardReader, parse_marker_specs
from .lsl.bridge import HAS_PYLSL, PolarLSLBridge
from .metrics.hrv import calculate_rmssd
from .metrics.rate_tracker import RateTracker, print_hz_summary
from .session.session import DeviceMetadata, SessionManager
from .session.state import (
    make_device_state,
    reset_device_state_on_disconnect,
    unwrap_vector,
)
from .storage.summary_logger import CsvLogger
from .ui.components import device_panel, header_bar, info_bar
from .ui.log_panel import LogPanel, log_event

if sys.platform == "win32":
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

H10_SUMMARY_COLS = [
    "Timestamp",
    "HeartRate_BPM",
    "HRV_RMSSD_ms",
    "Battery",
    "ECG_uV",
    "ACC_X",
    "ACC_Y",
    "ACC_Z",
    "Marker",
]

SENSE_SUMMARY_COLS = [
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
    "Marker",
]

_H10_STREAMS = ("hr", "ecg", "acc")


def _sense_streams(args: argparse.Namespace) -> list[str]:
    """Sense streams for this run: PPG + ACC, plus whatever the flags add."""
    streams = ["ppg", "acc"]
    if args.sense_gyro:
        streams.append("gyro")
    if args.sense_mag:
        streams.append("mag")
    if args.no_sdk_mode and not args.no_ppi:
        streams += ["hr", "ppi"]
    return streams


def _make_grid(
    state_h10: dict[str, Any],
    state_sense: dict[str, Any],
    elapsed: float,
    log_panel: LogPanel,
    lsl_active: bool,
) -> Panel:
    def _column(state: dict[str, Any], label: str, is_h10: bool) -> Panel:
        status = state.get("status", "").lower()
        live = "connected" in status and "disconnect" not in status
        border = "green" if live else "yellow"
        return Panel(
            Group(
                header_bar(
                    device_name=label,
                    device_addr=state.get("address", ""),
                    status=state.get("status", ""),
                ),
                Panel(
                    device_panel(state, is_h10=is_h10),
                    border_style=border,
                    expand=True,
                ),
                info_bar(
                    elapsed,
                    battery=state.get("battery", "-"),
                    csv_path=state.get("csv_path", ""),
                    csv_rows=state.get("csv_rows_written", 0),
                    log_level=log_panel.level,
                ),
            ),
            border_style="cyan",
            expand=True,
        )

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)
    grid.add_row(
        _column(state_h10, "H10", True),
        _column(state_sense, "Sense", False),
    )

    parts: list[Any] = [grid]
    if log_panel.level != "minimal":
        parts.append(log_panel.render())

    return Panel(
        Group(*parts),
        title=(
            "Dual Polar Dashboard (LSL Active)"
            if lsl_active
            else "Dual Polar Dashboard"
        ),
        border_style="cyan",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dual Polar Terminal Dashboard")
    parser.add_argument("--h10", type=str, default=None, help="MAC/Name of H10")
    parser.add_argument(
        "--sense", type=str, default=None, help="MAC/Name of Verity Sense"
    )
    parser.add_argument(
        "--no-ppi",
        action="store_true",
        help="Disable Sense PPI stream (only relevant with --no-sdk-mode).",
    )
    parser.add_argument(
        "--no-log-full",
        action="store_true",
        help="Disable full-resolution CSV logs (default is ON).",
    )
    parser.add_argument(
        "--scan-timeout",
        type=float,
        default=15.0,
        help="Device discovery scan timeout in seconds (default: 15.0).",
    )
    parser.add_argument(
        "--sense-gyro",
        action="store_true",
        default=False,
        help="Enable Polar Verity Sense Gyroscope stream (52 Hz). Runs concurrently with ACC on the shared IMU; neither disables the other.",
    )
    parser.add_argument(
        "--sense-mag",
        action="store_true",
        default=False,
        help="Enable Polar Verity Sense Magnetometer stream (20 Hz). Default: OFF.",
    )
    parser.add_argument(
        "--lsl",
        action="store_true",
        default=False,
        help="Broadcast all active sensor streams and markers over Lab Streaming Layer (LSL).",
    )
    add_common_args(parser)
    return parser


async def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    state_h10 = make_device_state("Polar H10")
    state_sense = make_device_state("Polar Sense")

    log_panel = LogPanel()
    log_panel.set_level(args.log_level)

    try:
        hotkeys = parse_marker_specs(args.markers)
    except ValueError as e:
        parser.error(str(e))
    hotkeys["L"] = LOG_TOGGLE
    reader = NonBlockingKeyboardReader(hotkeys)

    print("Scanning for Polar H10 and Verity Sense...")
    h10_dev, sense_dev = await discover_dual_polar_devices(
        h10_target=args.h10,
        sense_target=args.sense,
        timeout=args.scan_timeout,
    )

    if not h10_dev or not sense_dev:
        missing = [
            label
            for label, dev in (
                ("Polar H10", h10_dev),
                ("Polar Verity Sense", sense_dev),
            )
            if not dev
        ]
        print(f"Error: Missing devices: {', '.join(missing)}")
        return

    # Created only once both devices are found, so a failed scan leaves no
    # empty session folder behind.
    base_dir = Path(args.data_dir) if args.data_dir else Path("./data")
    session_mgr = SessionManager(base_dir=base_dir, device_type="dual", is_dual=True)
    session_mgr.metadata.participant_id = args.participant
    session_mgr.init_event_log(prefix="dual")

    for state, dev, fallback in (
        (state_h10, h10_dev, "Polar H10"),
        (state_sense, sense_dev, "Polar Verity Sense"),
    ):
        state["name"] = getattr(dev, "name", "") or fallback
        state["address"] = getattr(dev, "address", "") or "-"
        state["status"] = "Connecting..."

    session_mgr.metadata.devices["h10"] = DeviceMetadata(
        name=state_h10["name"], address=state_h10["address"], device_type="h10"
    )
    session_mgr.metadata.devices["sense"] = DeviceMetadata(
        name=state_sense["name"], address=state_sense["address"], device_type="sense"
    )

    # ── Streams & callbacks ───────────────────────────────────────────
    h10_streams = list(_H10_STREAMS)
    sense_streams = _sense_streams(args)
    log_full = not args.no_log_full and not args.no_log

    rate_tracker = RateTracker()
    configured_rates: dict[str, int] = {
        "h10_ecg": 130,
        "h10_acc": 200,
        "sense_ppg": 55 if args.no_sdk_mode else 135,
        "sense_acc": 52,
    }
    if args.sense_gyro:
        configured_rates["sense_gyro"] = 52
    if args.sense_mag:
        configured_rates["sense_mag"] = 20
    apply_rate_overrides(configured_rates, args, prefixes=("h10_", "sense_"))

    save_on_console_close(
        lambda: session_mgr.close_all(
            rate_tracker=rate_tracker, configured_rates=configured_rates
        )
    )
    h10_cbs = build_stream_callbacks(
        h10_streams,
        state_h10,
        rate_tracker,
        session_mgr=session_mgr if log_full else None,
        sub_device="h10",
        key_prefix="h10",
    )
    sense_cbs = build_stream_callbacks(
        sense_streams,
        state_sense,
        rate_tracker,
        session_mgr=session_mgr if log_full else None,
        sub_device="sense",
        key_prefix="sense",
    )

    def polar_status_callback(dev_label: str, msg: str) -> None:
        msg_lower = msg.lower()
        sev = (
            "warning"
            if any(
                w in msg_lower
                for w in ("reconnecting", "failed", "stalled", "lost", "disconnect")
            )
            else ("success" if "connected" in msg_lower else "info")
        )
        log_event(log_panel, msg, sev, device=dev_label, log_file=session_mgr.log_file)
        if dev_label in ("H10", "Sense"):
            state = state_h10 if dev_label == "H10" else state_sense
            state["status"] = msg
            if any(w in msg_lower for w in ("disconnected", "reconnecting", "lost")):
                reset_device_state_on_disconnect(state)

    lsl_bridge: PolarLSLBridge | None = None
    if args.lsl:
        if not HAS_PYLSL:
            log_event(
                log_panel,
                "pylsl not installed. Run 'pip install pylsl' to enable LSL.",
                "warning",
                log_file=session_mgr.log_file,
            )
        else:
            try:
                lsl_bridge = PolarLSLBridge(
                    h10_id=args.h10 or "H10",
                    sense_id=args.sense or "Sense",
                    enable_sense_gyro=args.sense_gyro,
                    enable_sense_mag=args.sense_mag,
                    ppg_rate=args.ppg_rate or (55.0 if args.no_sdk_mode else 135.0),
                    acc_rate_h10=args.acc_rate or 200.0,
                    ecg_rate=args.ecg_rate or 130.0,
                    gyro_rate=args.gyro_rate or 52.0,
                    mag_rate=args.mag_rate or 20.0,
                )
                for cbs, prefix in ((h10_cbs, "h10"), (sense_cbs, "sense")):
                    for stream, cb in list(cbs.items()):
                        cbs[stream] = lsl_bridge.wrap_callback(f"{prefix}_{stream}", cb)
                log_event(
                    log_panel,
                    "LSL outlets active and broadcasting.",
                    "success",
                    log_file=session_mgr.log_file,
                )
            except Exception as exc:
                log_event(
                    log_panel,
                    f"LSL initialization error: {exc}",
                    "error",
                    log_file=session_mgr.log_file,
                )

    adapter = PolarAdapter(
        h10_target=args.h10,
        sense_target=args.sense,
        enable_sense_gyro=args.sense_gyro,
        enable_sense_mag=args.sense_mag,
        h10_callbacks=h10_cbs,
        sense_callbacks=sense_cbs,
        status_callback=polar_status_callback,
        enable_watchdog=args.watchdog,
        watchdog_interval=args.watchdog_interval,
        freeze_timeout=args.freeze_timeout,
        h10_kwargs={
            "log_callback": lambda msg, sev="info": log_event(
                log_panel, msg, sev, device="H10", log_file=session_mgr.log_file
            ),
            **stream_setting_kwargs(args, h10_streams),
        },
        sense_kwargs={
            "log_callback": lambda msg, sev="info": log_event(
                log_panel, msg, sev, device="Sense", log_file=session_mgr.log_file
            ),
            "sdk_mode": not args.no_sdk_mode,
            **stream_setting_kwargs(args, sense_streams),
        },
    )
    adapter.h10.dev = h10_dev
    adapter.sense.dev = sense_dev

    h10_frame_counter = FrameCountLogger(
        log_panel, device="H10", log_file=session_mgr.log_file
    )
    sense_frame_counter = FrameCountLogger(
        log_panel, device="Sense", log_file=session_mgr.log_file
    )

    csv_h10 = None
    csv_sense = None
    if not args.no_log:
        csv_h10 = CsvLogger(
            session_mgr.get_post_processed_dir("h10") / "summary.csv", H10_SUMMARY_COLS
        )
        csv_h10.write_header()
        csv_sense = CsvLogger(
            session_mgr.get_post_processed_dir("sense") / "summary.csv",
            SENSE_SUMMARY_COLS,
        )
        csv_sense.write_header()
        state_h10["csv_path"] = csv_h10.path_str
        state_sense["csv_path"] = csv_sense.path_str

    background_tasks: list[asyncio.Task[Any]] = []
    start = time.time()

    h10_hz = [(s, f"h10_{s}") for s in h10_streams if s != "hr"]
    sense_hz = [(s, f"sense_{s}") for s in sense_streams if s != "hr"]

    def build() -> Panel:
        now = time.time()
        rate_tracker.refresh_state_hz(state_h10, h10_hz, now=now)
        rate_tracker.refresh_state_hz(state_sense, sense_hz, now=now)
        return _make_grid(
            state_h10,
            state_sense,
            now - start,
            log_panel,
            lsl_bridge is not None,
        )

    def write_rows(active_marker: str) -> None:
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S")
        if csv_h10:
            csv_h10.write_row(
                [
                    ts_str,
                    state_h10["hr"],
                    calculate_rmssd(state_h10["rr_history"]),
                    state_h10.get("battery"),
                    state_h10.get("ecg_last_uv"),
                    *unwrap_vector(state_h10, "acc_raw"),
                    active_marker,
                ]
            )
            state_h10["csv_rows_written"] = csv_h10.rows_written
        if csv_sense:
            sense_intervals = (
                state_sense["ppi_history"]
                if state_sense["ppi_history"]
                else state_sense["rr_history"]
            )
            csv_sense.write_row(
                [
                    ts_str,
                    state_sense["hr"],
                    calculate_rmssd(sense_intervals),
                    state_sense.get("battery"),
                    state_sense.get("ppg_last_sample"),
                    *unwrap_vector(state_sense, "acc_raw"),
                    *unwrap_vector(state_sense, "gyro_raw"),
                    *unwrap_vector(state_sense, "mag_raw"),
                    active_marker,
                ]
            )
            state_sense["csv_rows_written"] = csv_sense.rows_written

    def on_marker(marker: str) -> None:
        session_mgr.register_marker(marker)
        if lsl_bridge:
            lsl_bridge.push_marker(marker)

    def frame_check() -> None:
        h10_frame_counter.check(state_h10, h10_streams)
        sense_frame_counter.check(state_sense, sense_streams)

    try:
        log_event(
            log_panel,
            "Starting device streams...",
            "info",
            log_file=session_mgr.log_file,
        )
        h10_ok, sense_ok = await adapter.connect_and_start_streams(
            enable_h10=True, enable_sense=True
        )

        if not h10_ok and not sense_ok:
            log_event(
                log_panel,
                "Both devices failed to start. Exiting.",
                "error",
                log_file=session_mgr.log_file,
            )
            return

        if h10_ok:
            state_h10["status"] = "Connected! Streaming."
        if sense_ok:
            state_sense["status"] = (
                "Connected! Streaming."
                if args.no_sdk_mode
                else "Connected! Streaming (SDK Mode: 135Hz PPG, HR disabled)."
            )

        for label, proxy, state in (
            ("H10", adapter.h10, state_h10),
            ("Sense", adapter.sense, state_sense),
        ):
            state["battery"] = await read_battery(proxy)
            log_event(
                log_panel,
                f"{label} battery: {state['battery']}",
                "info",
                device=label,
                log_file=session_mgr.log_file,
            )
            background_tasks.append(
                asyncio.create_task(update_battery_loop(proxy, state))
            )
            background_tasks.append(
                asyncio.create_task(
                    rssi_loop(
                        proxy, log_panel, device=label, log_file=session_mgr.log_file
                    )
                )
            )

        with Live(build(), refresh_per_second=10) as live:
            await run_dashboard(
                live,
                build,
                reader=reader,
                log_panel=log_panel,
                log_file=session_mgr.log_file,
                start=start,
                duration=args.duration,
                on_marker=on_marker,
                write_rows=write_rows,
                frame_check=frame_check,
            )

    except asyncio.CancelledError:
        pass
    except Exception as e:
        log_event(log_panel, f"Error: {e}", "error", log_file=session_mgr.log_file)
    finally:
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)

        if lsl_bridge:
            lsl_bridge.close()

        # Save before the BLE teardown (see cli.py).
        session_mgr.close_all(
            rate_tracker=rate_tracker,
            configured_rates=configured_rates,
            keep_log=True,
        )
        await adapter.disconnect()
        session_mgr.close_log()

        print_hz_summary(
            configured_rates,
            rate_tracker,
            extra_streams=["sense_ppi"] if "ppi" in sense_streams else None,
        )

        for state in (state_h10, state_sense):
            state["status"] = "Disconnected."
            reset_device_state_on_disconnect(state)


def _entrypoint() -> None:
    """Console script entry point handling Ctrl-C cleanly."""
    run_cli(main)
