"""Command-line dashboard for real-time monitoring and recording of single Polar devices."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
import time
from pathlib import Path
from typing import Any

from rich.console import Group
from rich.live import Live
from rich.panel import Panel

from polar_ble_sdk.cli_common import (
    LOG_TOGGLE,
    add_common_args,
    apply_rate_overrides,
    build_stream_callbacks,
    run_cli,
    run_dashboard,
    save_on_console_close,
    stream_setting_kwargs,
)
from polar_ble_sdk.connector.adapter import PolarAdapter
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
from polar_ble_sdk.metrics.rate_tracker import RateTracker, print_hz_summary
from polar_ble_sdk.session.session import DeviceMetadata, SessionManager
from polar_ble_sdk.session.state import (
    make_device_state,
    reset_device_state_on_disconnect,
    unwrap_vector,
)
from polar_ble_sdk.storage.summary_logger import CsvLogger
from polar_ble_sdk.ui.components import device_panel, header_bar, info_bar
from polar_ble_sdk.ui.log_panel import LogPanel, log_event

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

_H10_STREAMS = ("hr", "ecg", "acc")
_SENSE_STREAMS = ("ppg", "acc", "gyro", "mag")
KNOWN_STREAMS = {"ecg", "ppg", "acc", "gyro", "mag", "hr", "ppi"}

# Rates the connector asks for, used for the session-end Hz verification.
# ACC differs per device and PPG per SDK mode, so both are patched in below.
_CONFIGURED_RATES = {"ecg": 130, "acc": 52, "gyro": 52, "mag": 20}

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


def _is_h10_name(name: str) -> bool:
    return "h10" in name.lower()


def _default_streams(is_h10: bool, no_sdk_mode: bool) -> list[str]:
    """Stream set for a device when the user did not pass ``--streams``.

    SDK mode (the default) gives the Sense 135 Hz PPG but silences its own
    HR/PPI streams, so those are only enabled with ``--no-sdk-mode``.
    """
    if is_h10:
        return list(_H10_STREAMS)
    streams = list(_SENSE_STREAMS)
    if no_sdk_mode:
        streams += ["hr", "ppi"]
    return streams


def _make_row(state: dict[str, Any], rmssd: float, active_marker: str) -> list[Any]:
    return [
        time.strftime("%Y-%m-%d %H:%M:%S"),
        state["hr"],
        rmssd,
        state.get("battery"),
        state.get("ecg_last_uv"),
        *unwrap_vector(state, "acc_raw"),
        *unwrap_vector(state, "gyro_raw"),
        *unwrap_vector(state, "mag_raw"),
        active_marker,
    ]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live Polar Terminal Dashboard")
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Custom CSV path for the 1 Hz summary log.",
    )
    parser.add_argument(
        "--log-full",
        action="store_true",
        help="Enable full-resolution CSV logs for all active streams.",
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
        help="Record the Sense PPI stream, also with --streams (needs --no-sdk-mode).",
    )
    add_common_args(parser)
    return parser


async def _select_device(args: argparse.Namespace) -> Any:
    """Scan and resolve the single device to record from, or None."""
    if args.device:
        print(f"Scanning for '{args.device}'...")
        return await discover_polar_device(args.device, timeout=20.0)

    print("Scanning for Polar devices...")
    devices = await discover_polar_devices(timeout=5.0)
    if not devices:
        print("No Polar device found.")
        return None

    if args.type:
        devices = [d for d in devices if _is_h10_name(d[0]) == (args.type == "h10")]
        if not devices:
            print(f"No {args.type.upper()} device found.")
            return None
    elif not args.streams:
        # Prefer the H10 when both kinds answer the scan.
        h10s = [d for d in devices if _is_h10_name(d[0])]
        if h10s:
            devices = h10s

    if len(devices) == 1:
        name, _addr, device = devices[0]
        print(f"Found: {name} — {'H10' if _is_h10_name(name) else 'Sense/OH1'}")
        return device

    print(f"\n{len(devices)} Polar devices detected:")
    for i, (name, addr, _) in enumerate(devices):
        kind = "H10" if _is_h10_name(name) else "Sense/OH1"
        print(f"  [{i + 1}] {name} ({addr}) — {kind}")
    while True:
        choice = input("\nSelect device: ").strip()
        if choice.lower() == "q":
            print("Cancelled.")
            return None
        try:
            idx = int(choice) - 1
        except ValueError:
            print("Enter a number or 'q'.")
            continue
        if 0 <= idx < len(devices):
            return devices[idx][2]
        print("Invalid selection.")


async def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.streams:
        requested_streams = [s.strip().lower() for s in args.streams.split(",")]
        for s in requested_streams:
            if s not in KNOWN_STREAMS:
                parser.error(f"Unknown stream: {s}")
    else:
        requested_streams = None
    if args.ppi:
        if args.type == "h10":
            parser.error("--ppi is only supported on Verity Sense devices.")
        if not args.no_sdk_mode:
            parser.error(
                "--ppi is unavailable in SDK mode (SDK mode disables HR/PPI). Use --no-sdk-mode."
            )

    try:
        hotkeys = parse_marker_specs(args.markers)
    except ValueError as e:
        parser.error(str(e))
    hotkeys["L"] = LOG_TOGGLE
    marker_legend = format_marker_legend(
        {k: v for k, v in hotkeys.items() if v != LOG_TOGGLE}
    )
    reader = NonBlockingKeyboardReader(hotkeys)

    log_panel = LogPanel()
    log_panel.set_level(args.log_level)

    device = await _select_device(args)
    if not device:
        print("No Polar device found.")
        return

    # ── Resolve device type and streams ──────────────────────────────
    device_name = getattr(device, "name", "") or ""
    device_address = getattr(device, "address", "") or ""
    is_h10 = args.type == "h10" if args.type else _is_h10_name(device_name)
    enabled_streams = requested_streams or _default_streams(is_h10, args.no_sdk_mode)
    if args.ppi and "ppi" not in enabled_streams:
        enabled_streams.append("ppi")
    device_type = "h10" if is_h10 else "sense"

    # ── Session & Storage Setup ───────────────────────────────────────
    data_root = Path(args.data_dir) if args.data_dir else Path.cwd() / "data"
    session_mgr = SessionManager(
        base_dir=data_root,
        device_type=device_type,
        is_dual=False,
    )
    session_mgr.metadata.participant_id = args.participant
    session_mgr.init_event_log(prefix="monitor")
    pp_dir = session_mgr.get_post_processed_dir()

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

    print(f"Device: {device_type.upper()}  |  Streams: {','.join(enabled_streams)}")
    print(f"Session: {session_mgr.session_dir}")
    if args.log_full:
        print("Full-resolution logs: enabled")

    rate_tracker = RateTracker()
    callbacks = build_stream_callbacks(
        enabled_streams,
        state,
        rate_tracker,
        session_mgr=session_mgr if args.log_full else None,
    )

    custom_kwargs = stream_setting_kwargs(args, enabled_streams)
    if not is_h10:
        custom_kwargs["sdk_mode"] = not args.no_sdk_mode

    def on_link_status(_label: str, msg: str) -> None:
        msg_lower = msg.lower()
        lost = any(
            w in msg_lower for w in ("reconnecting", "lost", "frozen", "still open")
        )
        log_event(
            log_panel,
            msg,
            "warning" if lost else "success",
            device=device_name,
            log_file=session_mgr.log_file,
        )
        state["status"] = msg
        if lost:
            # Don't keep writing the last values as if they were live.
            reset_device_state_on_disconnect(state)

    # The adapter's watchdog reconnects on link loss or a frozen stream; `conn`
    # is the link handle and follows the connector across reconnects.
    adapter = PolarAdapter(
        status_callback=on_link_status,
        enable_watchdog=args.watchdog,
        watchdog_interval=args.watchdog_interval,
        freeze_timeout=args.freeze_timeout,
    )
    conn = adapter.add_link(
        "device",
        device_name or device_type,
        device,
        create_polar_connector,
        callbacks,
        kwargs={
            "log_callback": lambda msg, sev="info": log_event(
                log_panel, msg, sev, device=device_name, log_file=session_mgr.log_file
            ),
            **custom_kwargs,
        },
    )

    frame_count_logger = FrameCountLogger(
        log_panel, device=device_name, log_file=session_mgr.log_file
    )

    configured_rates: dict[str, int] = {
        s: _CONFIGURED_RATES[s] for s in enabled_streams if s in _CONFIGURED_RATES
    }
    if is_h10 and "acc" in configured_rates:
        configured_rates["acc"] = 200
    if "ppg" in enabled_streams:
        configured_rates["ppg"] = 55 if args.no_sdk_mode else 135
    apply_rate_overrides(configured_rates, args)
    save_on_console_close(
        lambda: session_mgr.close_all(
            rate_tracker=rate_tracker, configured_rates=configured_rates
        )
    )

    start = time.time()
    hz_streams = [(s, s) for s in enabled_streams if s != "hr"]

    def build() -> Panel:
        rate_tracker.refresh_state_hz(state, hz_streams)
        header = header_bar(
            device_name=state["device_name"],
            device_addr=state["device_address"],
            status=state["status"],
        )
        info = info_bar(
            time.time() - start,
            battery=state["battery"],
            csv_path=state.get("csv_path", ""),
            csv_rows=state.get("csv_rows_written", 0),
            marker_legend=marker_legend,
            log_level=log_panel.level,
        )
        parts: list[Any] = [device_panel(state, is_h10=is_h10), info]
        if log_panel.level != "minimal":
            parts.append(log_panel.render())
        return Panel(Group(*parts), title=header, border_style="cyan")

    def _log(msg: str, severity: str = "info") -> None:
        log_event(
            log_panel, msg, severity, device=device_name, log_file=session_mgr.log_file
        )

    with Live(build(), refresh_per_second=10) as live:
        battery_task = None
        rssi_task = None

        try:
            _log("Starting connection...")
            if not (await adapter.start())["device"]:
                raise RuntimeError(conn.last_error or "could not start streaming")

            if conn.stream_errors:
                failed = ", ".join(conn.stream_errors.keys())
                state["status"] = f"Connected. Failed: {failed}"
                state["stream_errors"] = conn.stream_errors
                _log(f"Streams failed: {failed}", "warning")
            else:
                state["status"] = "Connected! Streaming live data."

            state["battery"] = await read_battery(conn)
            session_mgr.metadata.devices[device_type].battery_start = state["battery"]
            _log(f"Battery: {state['battery']}")

            csv_logger = None
            if not args.no_log:
                path = Path(args.csv) if args.csv else pp_dir / "summary.csv"
                csv_logger = CsvLogger(path, SUMMARY_CSV_COLUMNS)
                csv_logger.write_header()
                state["csv_path"] = csv_logger.path_str

            def write_rows(active_marker: str) -> None:
                if not csv_logger:
                    return
                intervals = (
                    state["ppi_history"]
                    if (not is_h10 and state["ppi_history"])
                    else state["rr_history"]
                )
                csv_logger.write_row(
                    _make_row(state, calculate_rmssd(intervals), active_marker)
                )
                state["csv_rows_written"] = csv_logger.rows_written

            def on_marker(marker: str) -> None:
                state["marker_log"].append(f"{time.strftime('%H:%M:%S')} - {marker}")
                state["last_marker"] = marker
                session_mgr.register_marker(marker)

            battery_task = asyncio.create_task(update_battery_loop(conn, state))
            rssi_task = asyncio.create_task(
                rssi_loop(
                    conn, log_panel, device=device_name, log_file=session_mgr.log_file
                )
            )

            await run_dashboard(
                live,
                build,
                reader=reader,
                log_panel=log_panel,
                log_file=session_mgr.log_file,
                device=device_name,
                start=start,
                duration=args.duration,
                on_marker=on_marker,
                write_rows=write_rows,
                frame_check=lambda: frame_count_logger.check(state, enabled_streams),
            )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            state["status"] = f"Error: {e}"
            live.update(build())
            await asyncio.sleep(3)
        finally:
            state["status"] = "Disconnecting..."
            _log("Disconnecting...")
            live.update(build())

            for task in (battery_task, rssi_task):
                if task:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

            # Save before the BLE teardown, which can take seconds: a second
            # Ctrl+C during it must not lose the session manifest.
            session_mgr.metadata.devices[device_type].battery_end = state.get(
                "battery", "-"
            )
            session_mgr.close_all(
                rate_tracker=rate_tracker,
                configured_rates=configured_rates,
                keep_log=True,
            )

            try:
                await asyncio.wait_for(adapter.disconnect(), timeout=6.0)
            except Exception as e:
                logger.debug("Error stopping notifications: %s", e)
            _log("Disconnected", "success")
            session_mgr.close_log()

            state["status"] = "Disconnected."
            reset_device_state_on_disconnect(state)
            live.update(build())

    if configured_rates:
        extra = ["ppi"] if "ppi" in enabled_streams else None
        print_hz_summary(configured_rates, rate_tracker, extra_streams=extra)


def _entrypoint() -> None:
    run_cli(main)
