from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
import time
from collections import deque
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
from polar_ble_sdk.dashboard_utils import (
    CsvLogger,
    FrameCountLogger,
    LogPanel,
    StreamFrameLogger,
    calculate_rmssd,
    device_panel,
    feed_hr,
    header_bar,
    info_bar,
    log_event,
    make_callback,
    make_device_state,
    make_frame_callback,
    make_ppi_callback,
    print_hz_summary,
    read_battery,
    rssi_loop,
    update_hz_for_state,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if sys.platform == "win32":
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

_H10_STREAMS = ("hr", "ecg", "acc")
# Sense defaults: 135 Hz PPG via SDK mode (SDK mode disables the Sense's own
# HR/PPI streams, so they are NOT in the default set — our own PPG->HR
# pipeline replaces them). Use --no-sdk-mode to fall back to 55 Hz PPG with
# the Sense's HR/PPI streams.
_SENSE_STREAMS = ("ppg", "acc", "gyro", "mag")
KNOWN_STREAMS = {"ecg", "ppg", "acc", "gyro", "mag", "hr", "ppi"}


def _sense_streams(no_sdk_mode: bool) -> list[str]:
    """Default Sense stream set.

    With SDK mode (default) the Sense's own HR/PPI are disabled, so the set is
    the raw PPG + IMU (our own PPG->HR pipeline covers HR). Without SDK mode,
    add the Sense's HR + PPI streams.
    """
    streams = list(_SENSE_STREAMS)
    if no_sdk_mode:
        streams.extend(["hr", "ppi"])
    return streams


state = make_device_state("Polar Device")

_ecg_ts: deque[tuple[float, int]] = deque(maxlen=20)
_ppg_ts: deque[tuple[float, int]] = deque(maxlen=20)
_acc_ts: deque[tuple[float, int]] = deque(maxlen=20)
_gyro_ts: deque[tuple[float, int]] = deque(maxlen=20)
_mag_ts: deque[tuple[float, int]] = deque(maxlen=20)
_ppi_ts: deque[tuple[float, int]] = deque(maxlen=20)


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
            if k == "L":
                raise ValueError("'L' is reserved for the log-level toggle.")
            if k and v:
                hotkeys[k] = v
    return hotkeys


def _format_marker_legend(hotkeys: dict) -> str:
    return " | ".join(f"{k}={hotkeys[k]}" for k in sorted(hotkeys))


# ── Callbacks ──────────────────────────────────────────────────────────

_hr_cb = lambda data: feed_hr(data, state)  # noqa: E731
_ecg_cb = make_callback(state, _ecg_ts, "ecg")
_ppg_cb = make_callback(state, _ppg_ts, "ppg")
_acc_cb = make_callback(state, _acc_ts, "acc")
_gyro_cb = make_callback(state, _gyro_ts, "gyro")
_mag_cb = make_callback(state, _mag_ts, "mag")
_ppi_cb = make_callback(state, _ppi_ts, "ppi")


# ── Summary CSV helpers ─────────────────────────────────────────────────


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


def _unwrap_triple(raw_key: str, count_key: str) -> list:
    val = state.get(raw_key) if state.get(count_key, 0) > 0 else None
    if isinstance(val, tuple) and len(val) == 3:
        return [val[0], val[1], val[2]]
    return [None, None, None]


def _make_row(rmssd: float, active_marker: str) -> list:
    return [
        time.strftime("%Y-%m-%d %H:%M:%S"),
        state["hr"],
        rmssd,
        state.get("battery"),
        state.get("ecg_last_sample"),
        *_unwrap_triple("acc_raw", "acc_count"),
        *_unwrap_triple("gyro_raw", "gyro_count"),
        *_unwrap_triple("mag_raw", "mag_count"),
        active_marker,
    ]


def _make_hr_logger(hr_logger: StreamFrameLogger):
    def cb(data):
        _hr_cb(data)
        hr_logger.write_frame(int(time.time() * 1e9), data)

    return cb


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
        help="Enable the PPI stream on the Sense (opt-in; requires --no-sdk-mode; "
        "SDK mode disables HR/PPI).",
    )
    parser.add_argument(
        "--sdk-mode",
        action="store_true",
        help="Enable SDK mode on the Sense (required for PPG > 55 Hz, e.g. 135/176 Hz). "
        "Now the default; use --no-sdk-mode to disable.",
    )
    parser.add_argument(
        "--no-sdk-mode",
        action="store_true",
        help="Disable SDK mode on the Sense: PPG falls back to 55 Hz and the Sense's "
        "own HR + PPI streams become available.",
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
        _is_h10 = False  # determined later by device name
    elif args.type == "h10":
        if args.ppi:
            parser.error("--ppi is only supported on Verity Sense devices.")
        enabled_streams = list(_H10_STREAMS)
        _is_h10 = True
    elif args.type == "sense":
        enabled_streams = _sense_streams(args.no_sdk_mode)
        if args.ppi:
            # only valid without SDK mode
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
        hotkeys = _parse_marker_specs(args.markers)
    except ValueError as e:
        parser.error(str(e))
    hotkeys["L"] = "__toggle_log__"
    marker_legend = _format_marker_legend(
        {k: v for k, v in hotkeys.items() if v != "__toggle_log__"}
    )
    reader = _NonBlockingLineReader(hotkeys)

    # ── Log infrastructure ────────────────────────────────────────────
    log_panel = LogPanel()
    log_panel.set_level(args.log_level)
    log_file = None  # opened after session_dir is created below

    # ── Phase 1: find device ────────────────────────────────────────

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
                if args.ppi:
                    if args.no_sdk_mode:
                        enabled_streams.append("ppi")
                    else:
                        parser.error(
                            "--ppi requires --no-sdk-mode (SDK mode disables HR/PPI)"
                        )

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
                if not _is_h10 and args.ppi:
                    if args.no_sdk_mode:
                        enabled_streams.append("ppi")
                    else:
                        parser.error(
                            "--ppi requires --no-sdk-mode (SDK mode disables HR/PPI)"
                        )
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
                if not _is_h10 and args.ppi:
                    if args.no_sdk_mode:
                        enabled_streams.append("ppi")
                    else:
                        parser.error(
                            "--ppi requires --no-sdk-mode (SDK mode disables HR/PPI)"
                        )

    if not device:
        print("No Polar device found.")
        return

    # ── Settle device type and session directory ─────────────────────

    _is_h10 = _is_h10 or "h10" in (device.name or "").lower()
    device_type = "h10" if _is_h10 else "sense"
    session_ts = time.strftime("%Y%m%d_%H%M%S")
    session_dir = PROJECT_ROOT / "data" / device_type / session_ts
    raw_dir = session_dir / "raw"
    pp_dir = session_dir / "post-processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    pp_dir.mkdir(parents=True, exist_ok=True)

    # Open event log file
    log_path = session_dir / f"monitor_{session_ts}.log"
    try:
        log_file = log_path.open("w", encoding="utf-8")
    except OSError:
        log_file = None

    state["device_name"] = device.name or ""
    state["device_address"] = device.address
    state["status"] = "Connecting..."
    state["csv_path"] = str(session_dir)

    stream_tags = ",".join(enabled_streams)
    print(f"Device: {device_type.upper()}  |  Streams: {stream_tags}")
    print(f"Session: {session_dir}")
    if args.log_full:
        print("Full-resolution logs: enabled")

    start = time.time()

    def build():
        elapsed = time.time() - start
        hz_streams: list = []
        stream_ts_map = {
            "ecg": ("ecg", _ecg_ts),
            "ppg": ("ppg", _ppg_ts),
            "acc": ("acc", _acc_ts),
            "gyro": ("gyro", _gyro_ts),
            "mag": ("mag", _mag_ts),
            "ppi": ("ppi", _ppi_ts),
        }
        for s in enabled_streams:
            if s in stream_ts_map:
                hz_streams.append(stream_ts_map[s])
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
        parts: list = [device_panel(state, is_h10=_is_h10), info]
        if log_panel.level != "minimal":
            parts.append(log_panel.render())
        return Panel(
            Group(*parts),
            title=header,
            border_style="cyan",
        )

    with Live(build(), refresh_per_second=10) as live:
        custom_kwargs = {}
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
        # SDK mode is ON by default for the Sense; --no-sdk-mode disables it.
        if not _is_h10:
            custom_kwargs["sdk_mode"] = not args.no_sdk_mode

        stream_callbacks: dict[str, Any] = {
            "ecg": _ecg_cb,
            "ppg": _ppg_cb,
            "acc": _acc_cb,
            "gyro": _gyro_cb,
            "mag": _mag_cb,
            "ppi": _ppi_cb,
        }
        frame_loggers: dict[str, StreamFrameLogger] = {}
        ecg_cb = stream_callbacks["ecg"] if "ecg" in enabled_streams else None
        ppg_cb = stream_callbacks["ppg"] if "ppg" in enabled_streams else None
        acc_cb = stream_callbacks["acc"] if "acc" in enabled_streams else None
        gyro_cb = stream_callbacks["gyro"] if "gyro" in enabled_streams else None
        mag_cb = stream_callbacks["mag"] if "mag" in enabled_streams else None
        ppi_cb = stream_callbacks["ppi"] if "ppi" in enabled_streams else None
        hr_cb = _hr_cb if "hr" in enabled_streams else None

        if args.log_full:
            for stream in enabled_streams:
                file_name = f"{stream}.csv"
                if stream == "hr":
                    hr_logger = StreamFrameLogger(raw_dir / file_name, stream)
                    hr_logger.open()
                    frame_loggers[stream] = hr_logger
                    hr_cb = _make_hr_logger(hr_logger)
                elif stream not in stream_callbacks:
                    continue
                else:
                    logger = StreamFrameLogger(raw_dir / file_name, stream)
                    logger.open()
                    frame_loggers[stream] = logger
                    if stream == "ppi":
                        wrapped = make_ppi_callback(stream_callbacks[stream], logger)
                        ppi_cb = wrapped
                    else:
                        wrapped = make_frame_callback(stream_callbacks[stream], logger)
                        if stream == "ecg":
                            ecg_cb = wrapped
                        elif stream == "ppg":
                            ppg_cb = wrapped
                        elif stream == "acc":
                            acc_cb = wrapped
                        elif stream == "gyro":
                            gyro_cb = wrapped
                        elif stream == "mag":
                            mag_cb = wrapped

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
                log_panel, msg, sev, device=device.name or "", log_file=log_file
            ),
            **custom_kwargs,
        )

        frame_count_logger = FrameCountLogger(
            log_panel, device=device.name or "", log_file=log_file
        )

        last_log = start
        last_frame_log = start
        battery_task = None
        rssi_task = None

        try:
            log_event(
                log_panel,
                "Starting connection...",
                device=device.name or "",
                log_file=log_file,
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
                    device=device.name or "",
                    log_file=log_file,
                )
            else:
                state["status"] = "Connected! Streaming live data."
            state["battery"] = await read_battery(conn)
            log_event(
                log_panel,
                f"Battery: {state['battery']}",
                "info",
                device=device.name or "",
                log_file=log_file,
            )

            csv_logger = None
            if not args.no_log:
                path = Path(args.csv) if args.csv else pp_dir / "summary.csv"
                csv_logger = CsvLogger(path, SUMMARY_CSV_COLUMNS)
                csv_logger.write_header()
                state["csv_path"] = csv_logger.path_str

            battery_task = asyncio.create_task(_battery_loop(conn))
            rssi_task = asyncio.create_task(
                rssi_loop(
                    conn,
                    log_panel,
                    device=device.name or "",
                    log_file=log_file,
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
                            device=device.name or "",
                            log_file=log_file,
                        )
                        continue
                    ts = time.strftime("%H:%M:%S")
                    state["marker_log"].append(f"{ts} - {m}")
                    state["last_marker"] = m
                    active_marker = m
                    log_event(
                        log_panel,
                        f"Marker: {m}",
                        "info",
                        device=device.name or "",
                        log_file=log_file,
                    )

                now = time.time()
                if csv_logger and (now - last_log) >= 1.0:
                    last_log = now
                    csv_logger.write_row(
                        _make_row(calculate_rmssd(state["rr_history"]), active_marker)
                    )
                    state["csv_rows_written"] = csv_logger.rows_written

                # Verbose: log frame count deltas every second
                if log_panel.level == "verbose" and (now - last_frame_log) >= 1.0:
                    last_frame_log = now
                    frame_count_logger.check(state, enabled_streams)

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
                device=device.name or "",
                log_file=log_file,
            )
            live.update(build())
            if battery_task:
                battery_task.cancel()
            if rssi_task:
                rssi_task.cancel()
            await conn.stop_notify()
            log_event(
                log_panel,
                "Disconnected",
                "success",
                device=device.name or "",
                log_file=log_file,
            )
            for logger in frame_loggers.values():
                logger.close()
            state["status"] = "Disconnected."
            live.update(build())
            if log_file:
                log_file.close()

            # Session-end Hz verification
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
            if configured_rates:
                extra = ["ppi"] if "ppi" in enabled_streams else None
                print_hz_summary(configured_rates, state, extra_streams=extra)
            await asyncio.sleep(1)


def _entrypoint() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
