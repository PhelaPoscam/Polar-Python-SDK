"""Command-line dashboard for real-time monitoring and recording of single Polar devices."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.console import Group
from rich.live import Live
from rich.panel import Panel

from polar_ble_sdk.connector.ble_discovery import (
    discover_polar_device,
    discover_polar_devices,
)
from polar_ble_sdk.connector.stream import create_polar_connector
from polar_ble_sdk.diagnostics.battery import read_battery, update_battery_loop
from polar_ble_sdk.diagnostics.rssi import FrameCountLogger, rssi_loop
from polar_ble_sdk.input.keyboard import (
    NonBlockingKeyboardReader,
    format_marker_legend,
    parse_marker_specs,
)
from polar_ble_sdk.metrics.hrv import calculate_rmssd
from polar_ble_sdk.metrics.rate_tracker import (
    RateTracker,
    print_hz_summary,
    update_hz_for_state,
)
from polar_ble_sdk.session.session import DeviceMetadata, SessionManager
from polar_ble_sdk.session.state import (
    feed_hr,
    make_callback,
    make_device_state,
    unwrap_vector,
)
from polar_ble_sdk.storage.frame_logger import (
    StreamFrameLogger,
    make_frame_callback,
    make_hr_callback,
    make_ppi_callback,
)
from polar_ble_sdk.storage.summary_logger import CsvLogger
from polar_ble_sdk.ui.components import device_panel, header_bar, info_bar
from polar_ble_sdk.ui.log_panel import LogPanel, log_event

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if sys.platform == "win32":
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

_H10_STREAMS = ("hr", "ecg", "acc")
_SENSE_STREAMS = ("ppg", "acc", "gyro", "mag")
KNOWN_STREAMS = {"ecg", "ppg", "acc", "gyro", "mag", "hr", "ppi"}

SUMMARY_CSV_COLUMNS = [
    "Timestamp",
    "HeartRate_BPM",
    "HRV_RMSSD_ms",
    "Battery_Percent",
    "ECG_uV",
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


def _sense_streams(no_sdk_mode: bool) -> list[str]:
    """Default Sense stream set based on SDK mode selection."""
    streams = list(_SENSE_STREAMS)
    if no_sdk_mode:
        streams.extend(["hr", "ppi"])
    return streams


def _make_row(state: dict[str, Any], rmssd: float, active_marker: str) -> list[Any]:
    return [
        time.strftime("%Y-%m-%d %H:%M:%S"),
        state["hr"],
        rmssd,
        state.get("battery"),
        state.get("ecg_last_sample"),
        *unwrap_vector(state, "acc_raw", "acc_count"),
        *unwrap_vector(state, "gyro_raw", "gyro_count"),
        *unwrap_vector(state, "mag_raw", "mag_count"),
        active_marker,
    ]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Live Polar Terminal Dashboard")
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Custom CSV path for the 1 Hz summary log.",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Disable the 1 Hz summary CSV log.",
    )
    parser.add_argument(
        "--log-full",
        action="store_true",
        help="Enable full-resolution CSV logs for all active streams.",
    )
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
    parser.add_argument(
        "--type",
        type=str,
        choices=["h10", "sense"],
        default=None,
        help="Device type. Also sets default streams.",
    )
    parser.add_argument(
        "--streams",
        type=str,
        default=None,
        help="Comma-separated streams (hr,ecg,acc,ppg,ppi,gyro,mag).",
    )
    parser.add_argument(
        "--ppi",
        action="store_true",
        help="Enable the PPI stream on the Sense (opt-in; requires --no-sdk-mode).",
    )
    parser.add_argument(
        "--sdk-mode",
        action="store_true",
        help="Enable SDK mode on the Sense (required for PPG > 55 Hz). Default is ON.",
    )
    parser.add_argument(
        "--no-sdk-mode",
        action="store_true",
        help="Disable SDK mode on the Sense: PPG falls back to 55 Hz and HR/PPI become available.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Recording duration in seconds (stops automatically when reached).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["minimal", "moderate", "verbose"],
        default="moderate",
        help="Terminal log verbosity: minimal, moderate (default), verbose.",
    )
    for opt in (
        "acc-rate",
        "acc-range",
        "gyro-rate",
        "gyro-range",
        "mag-rate",
        "ppg-rate",
        "ecg-rate",
    ):
        parser.add_argument(f"--{opt}", type=int, default=None, help=f"Custom {opt}")
    args = parser.parse_args()

    # ── Resolve device type and streams ──────────────────────────────
    if args.streams:
        enabled_streams = [s.strip().lower() for s in args.streams.split(",")]
        for s in enabled_streams:
            if s not in KNOWN_STREAMS:
                parser.error(f"Unknown stream: {s}")
        _is_h10 = False
    elif args.type == "h10":
        if args.ppi:
            parser.error("--ppi is only supported on Verity Sense devices.")
        enabled_streams = list(_H10_STREAMS)
        _is_h10 = True
    elif args.type == "sense":
        enabled_streams = _sense_streams(args.no_sdk_mode)
        if args.ppi:
            if args.no_sdk_mode:
                enabled_streams.append("ppi")
            else:
                parser.error(
                    "--ppi is unavailable in SDK mode (SDK mode disables HR/PPI). Use --no-sdk-mode."
                )
        _is_h10 = False
    else:
        enabled_streams = ["hr"]
        _is_h10 = False

    try:
        hotkeys = parse_marker_specs(args.markers)
    except ValueError as e:
        parser.error(str(e))
    hotkeys["L"] = "__toggle_log__"
    marker_legend = format_marker_legend(
        {k: v for k, v in hotkeys.items() if v != "__toggle_log__"}
    )
    reader = NonBlockingKeyboardReader(hotkeys)

    # ── Log infrastructure ────────────────────────────────────────────
    log_panel = LogPanel()
    log_panel.set_level(args.log_level)

    # ── Discovery ─────────────────────────────────────────────────────
    if args.device:
        print(f"Scanning for '{args.device}'...")
        device = await discover_polar_device(args.device, timeout=20.0)
    else:
        print("Scanning for Polar devices...")
        devices = await discover_polar_devices(timeout=5.0)
        if not devices:
            print("No Polar device found.")
            return

        if not args.streams and not args.type:
            h10s = [(n, a, d) for n, a, d in devices if "h10" in n.lower()]
            senses = [(n, a, d) for n, a, d in devices if "h10" not in n.lower()]
            if h10s:
                devices = h10s
                _is_h10 = True
                enabled_streams = list(_H10_STREAMS)
            elif senses:
                devices = senses
                _is_h10 = False
                enabled_streams = _sense_streams(args.no_sdk_mode)
                if args.ppi and args.no_sdk_mode:
                    enabled_streams.append("ppi")

        if args.type:
            filtered = [
                (n, a, d)
                for n, a, d in devices
                if (args.type == "h10" and "h10" in n.lower())
                or (args.type == "sense" and "h10" not in n.lower())
            ]
            if not filtered:
                print(f"No {args.type.upper()} device found.")
                return
            devices = filtered

        if len(devices) == 1:
            device = devices[0][2]
            name = devices[0][0]
            if not args.streams and not args.type:
                _is_h10 = "h10" in name.lower()
                enabled_streams = (
                    list(_H10_STREAMS) if _is_h10 else _sense_streams(args.no_sdk_mode)
                )
                if not _is_h10 and args.ppi and args.no_sdk_mode:
                    enabled_streams.append("ppi")
            kind = "H10" if _is_h10 else "Sense/OH1"
            print(f"Found: {name} — {kind}")
        else:
            print(f"\n{len(devices)} Polar devices detected:")
            for i, (name, addr, _) in enumerate(devices):
                kind = "H10" if "h10" in name.lower() else "Sense/OH1"
                print(f"  [{i + 1}] {name} ({addr}) — {kind}")
            while True:
                try:
                    choice = input("\nSelect device: ").strip()
                    if choice.lower() == "q":
                        print("Cancelled.")
                        return
                    idx = int(choice) - 1
                    if 0 <= idx < len(devices):
                        break
                    print("Invalid selection.")
                except ValueError:
                    print("Enter a number or 'q'.")
            device = devices[idx][2]
            name = devices[idx][0]
            if not args.streams and not args.type:
                _is_h10 = "h10" in name.lower()
                enabled_streams = (
                    list(_H10_STREAMS) if _is_h10 else _sense_streams(args.no_sdk_mode)
                )
                if not _is_h10 and args.ppi and args.no_sdk_mode:
                    enabled_streams.append("ppi")

    if not device:
        print("No Polar device found.")
        return

    # ── Session & Storage Setup ───────────────────────────────────────
    device_name = getattr(device, "name", "") or ""
    device_address = getattr(device, "address", "") or ""
    _is_h10 = _is_h10 or "h10" in device_name.lower()
    device_type = "h10" if _is_h10 else "sense"

    session_mgr = SessionManager(
        base_dir=PROJECT_ROOT,
        device_type=device_type,
        is_dual=False,
    )
    session_mgr.init_event_log(prefix="monitor")
    pp_dir = session_mgr.get_post_processed_dir()

    # Session metadata population
    session_mgr.metadata.devices[device_type] = DeviceMetadata(
        name=device_name,
        address=device_address,
        device_type=device_type,
        stream_configurations={"enabled_streams": enabled_streams},
    )

    state = make_device_state("Polar Device")
    state["device_name"] = device_name
    state["device_address"] = device_address
    state["status"] = "Connecting..."
    state["csv_path"] = str(session_mgr.session_dir)

    stream_tags = ",".join(enabled_streams)
    print(f"Device: {device_type.upper()}  |  Streams: {stream_tags}")
    print(f"Session: {session_mgr.session_dir}")
    if args.log_full:
        print("Full-resolution logs: enabled")

    # ── Deques for sliding-window rate tracking ───────────────────────
    stream_ts: dict[str, deque[tuple[float, int]]] = {
        "ecg": deque(maxlen=20),
        "ppg": deque(maxlen=20),
        "acc": deque(maxlen=20),
        "gyro": deque(maxlen=20),
        "mag": deque(maxlen=20),
        "ppi": deque(maxlen=20),
    }

    def _hr_cb(data: Any) -> None:
        feed_hr(data, state)

    stream_callbacks: dict[str, Any] = {
        "ecg": make_callback(state, stream_ts["ecg"], "ecg"),
        "ppg": make_callback(state, stream_ts["ppg"], "ppg"),
        "acc": make_callback(state, stream_ts["acc"], "acc"),
        "gyro": make_callback(state, stream_ts["gyro"], "gyro"),
        "mag": make_callback(state, stream_ts["mag"], "mag"),
        "ppi": make_callback(state, stream_ts["ppi"], "ppi"),
    }

    frame_loggers: dict[str, StreamFrameLogger] = {}
    ecg_cb: Callable[[Any], None] | None = (
        stream_callbacks["ecg"] if "ecg" in enabled_streams else None
    )
    ppg_cb: Callable[[Any], None] | None = (
        stream_callbacks["ppg"] if "ppg" in enabled_streams else None
    )
    acc_cb: Callable[[Any], None] | None = (
        stream_callbacks["acc"] if "acc" in enabled_streams else None
    )
    gyro_cb: Callable[[Any], None] | None = (
        stream_callbacks["gyro"] if "gyro" in enabled_streams else None
    )
    mag_cb: Callable[[Any], None] | None = (
        stream_callbacks["mag"] if "mag" in enabled_streams else None
    )
    ppi_cb: Callable[[Any], None] | None = (
        stream_callbacks["ppi"] if "ppi" in enabled_streams else None
    )
    hr_cb: Callable[[Any], None] | None = _hr_cb if "hr" in enabled_streams else None

    if args.log_full:
        for stream in enabled_streams:
            fl = session_mgr.create_frame_logger(stream)
            frame_loggers[stream] = fl
            if stream == "hr":
                hr_cb = make_hr_callback(_hr_cb, fl)
            elif stream == "ppi":
                ppi_cb = make_ppi_callback(stream_callbacks[stream], fl)
            elif stream == "ecg":
                ecg_cb = make_frame_callback(stream_callbacks[stream], fl)
            elif stream == "ppg":
                ppg_cb = make_frame_callback(stream_callbacks[stream], fl)
            elif stream == "acc":
                acc_cb = make_frame_callback(stream_callbacks[stream], fl)
            elif stream == "gyro":
                gyro_cb = make_frame_callback(stream_callbacks[stream], fl)
            elif stream == "mag":
                mag_cb = make_frame_callback(stream_callbacks[stream], fl)

    custom_kwargs: dict[str, Any] = {}
    if "ecg" in enabled_streams and args.ecg_rate:
        custom_kwargs["ecg_sample_rate"] = args.ecg_rate
    if "acc" in enabled_streams:
        if args.acc_rate:
            custom_kwargs["acc_sample_rate"] = args.acc_rate
        if args.acc_range:
            custom_kwargs["acc_range"] = args.acc_range
    if "gyro" in enabled_streams:
        if args.gyro_rate:
            custom_kwargs["gyro_sample_rate"] = args.gyro_rate
        if args.gyro_range:
            custom_kwargs["gyro_range"] = args.gyro_range
    if "mag" in enabled_streams and args.mag_rate:
        custom_kwargs["mag_sample_rate"] = args.mag_rate
    if "ppg" in enabled_streams and args.ppg_rate:
        custom_kwargs["ppg_sample_rate"] = args.ppg_rate
    if not _is_h10:
        custom_kwargs["sdk_mode"] = not args.no_sdk_mode

    conn = create_polar_connector(
        device,
        callback=hr_cb,
        ecg_callback=ecg_cb,
        ppi_callback=ppi_cb,
        ppg_callback=ppg_cb,
        acc_callback=acc_cb,
        gyro_callback=gyro_cb,
        mag_callback=mag_cb,
        verbose=False,
        log_callback=lambda msg, sev="info": log_event(
            log_panel, msg, sev, device=device_name, log_file=session_mgr.log_file
        ),
        **custom_kwargs,
    )

    frame_count_logger = FrameCountLogger(
        log_panel, device=device_name, log_file=session_mgr.log_file
    )

    start = time.time()

    def build() -> Panel:
        elapsed = time.time() - start
        hz_streams: list[tuple[str, deque[tuple[float, int]]]] = [
            (s, stream_ts[s]) for s in enabled_streams if s in stream_ts
        ]
        if hz_streams:
            update_hz_for_state(state, *hz_streams)

        header = header_bar(
            device_name=state["device_name"],
            device_addr=state["device_address"],
            status=state["status"],
        )
        info = info_bar(
            elapsed,
            battery=state["battery"],
            csv_path=state.get("csv_path", ""),
            csv_rows=state.get("csv_rows_written", 0),
            marker_legend=marker_legend,
            log_level=log_panel.level,
        )
        parts: list[Any] = [device_panel(state, is_h10=_is_h10), info]
        if log_panel.level != "minimal":
            parts.append(log_panel.render())
        return Panel(
            Group(*parts),
            title=header,
            border_style="cyan",
        )

    with Live(build(), refresh_per_second=10) as live:
        last_log = start
        last_frame_log = start
        battery_task = None
        rssi_task = None

        try:
            log_event(
                log_panel,
                "Starting connection...",
                device=device_name,
                log_file=session_mgr.log_file,
            )
            await conn.start_notify()

            if conn.stream_errors:
                failed = ", ".join(conn.stream_errors.keys())
                state["status"] = f"Connected. Failed: {failed}"
                state["stream_errors"] = conn.stream_errors
                log_event(
                    log_panel,
                    f"Streams failed: {failed}",
                    "warning",
                    device=device_name,
                    log_file=session_mgr.log_file,
                )
            else:
                state["status"] = "Connected! Streaming live data."

            state["battery"] = await read_battery(conn)
            session_mgr.metadata.devices[device_type].battery_start = state["battery"]
            log_event(
                log_panel,
                f"Battery: {state['battery']}",
                "info",
                device=device_name,
                log_file=session_mgr.log_file,
            )

            csv_logger = None
            if not args.no_log:
                path = Path(args.csv) if args.csv else pp_dir / "summary.csv"
                csv_logger = CsvLogger(path, SUMMARY_CSV_COLUMNS)
                csv_logger.write_header()
                state["csv_path"] = csv_logger.path_str

            battery_task = asyncio.create_task(update_battery_loop(conn, state))
            rssi_task = asyncio.create_task(
                rssi_loop(
                    conn,
                    log_panel,
                    device=device_name,
                    log_file=session_mgr.log_file,
                )
            )

            while True:
                active_marker = ""
                for m in reader.poll_markers():
                    if m == "__toggle_log__":
                        new_level = log_panel.cycle_level()
                        log_event(
                            log_panel,
                            f"Log level: {new_level}",
                            "info",
                            device=device_name,
                            log_file=session_mgr.log_file,
                        )
                        continue
                    ts = time.strftime("%H:%M:%S")
                    state["marker_log"].append(f"{ts} - {m}")
                    state["last_marker"] = m
                    active_marker = m
                    session_mgr.register_marker(m)
                    log_event(
                        log_panel,
                        f"Marker: {m}",
                        "info",
                        device=device_name,
                        log_file=session_mgr.log_file,
                    )

                now = time.time()
                if csv_logger and (now - last_log) >= 1.0:
                    last_log = now
                    csv_logger.write_row(
                        _make_row(
                            state, calculate_rmssd(state["rr_history"]), active_marker
                        )
                    )
                    state["csv_rows_written"] = csv_logger.rows_written

                if log_panel.level == "verbose" and (now - last_frame_log) >= 1.0:
                    last_frame_log = now
                    frame_count_logger.check(state, enabled_streams)

                if args.duration and (now - start) >= args.duration:
                    log_event(
                        log_panel,
                        f"Target duration ({args.duration}s) reached.",
                        "info",
                        device=device_name,
                        log_file=session_mgr.log_file,
                    )
                    break

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
            log_event(
                log_panel,
                "Disconnecting...",
                device=device_name,
                log_file=session_mgr.log_file,
            )
            live.update(build())

            if battery_task:
                battery_task.cancel()
            if rssi_task:
                rssi_task.cancel()

            await conn.stop_notify()
            session_mgr.metadata.devices[device_type].battery_end = state.get(
                "battery", "-"
            )
            log_event(
                log_panel,
                "Disconnected",
                "success",
                device=device_name,
                log_file=session_mgr.log_file,
            )

            # Session-end Hz verification & manifest persistence
            configured_rates: dict[str, int] = {}
            if "ecg" in enabled_streams:
                configured_rates["ecg"] = 130
            if "acc" in enabled_streams:
                configured_rates["acc"] = 200 if _is_h10 else 52
            if "ppg" in enabled_streams:
                configured_rates["ppg"] = 135 if _is_h10 else 55
            if "gyro" in enabled_streams:
                configured_rates["gyro"] = 52
            if "mag" in enabled_streams:
                configured_rates["mag"] = 20

            rate_tracker = RateTracker()
            for s_name, s_acc in state.get("_session_streams", {}).items():
                rate_tracker.track(s_name, s_acc["samples"], timestamp=s_acc["last_ts"])
                if s_name in rate_tracker.accumulators:
                    rate_tracker.accumulators[s_name].first_ts = s_acc["first_ts"]

            session_mgr.close_all(
                rate_tracker=rate_tracker,
                configured_rates=configured_rates,
            )

            state["status"] = "Disconnected."
            live.update(build())

            if configured_rates:
                extra = ["ppi"] if "ppi" in enabled_streams else None
                print_hz_summary(configured_rates, state, extra_streams=extra)
            await asyncio.sleep(1)


def _entrypoint() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
