"""Dual-device terminal dashboard for Polar H10 + Verity Sense."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from rich.console import Group  # noqa: E402
from rich.live import Live  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

from polar_ble_sdk.connector.ble_discovery import (  # noqa: E402
    discover_dual_polar_devices,
)
from polar_ble_sdk.connector.stream import create_polar_connector  # noqa: E402
from polar_ble_sdk.dashboard_utils import (  # noqa: E402
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

if sys.platform == "win32":
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# ── Summary CSV schemas ────────────────────────────────────────────────

H10_SUMMARY_COLS = [
    "Timestamp",
    "HeartRate_BPM",
    "HRV_RMSSD_ms",
    "Battery",
    "ECG_uV",
    "ACC_X",
    "ACC_Y",
    "ACC_Z",
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
]


def _make_hr_logger(hr_cb, hr_logger: StreamFrameLogger):
    def cb(data):
        hr_cb(data)
        hr_logger.write_frame(int(time.time() * 1e9), data)

    return cb


# ── State and callbacks ────────────────────────────────────────────────

state_h10 = make_device_state("Polar H10")
state_sense = make_device_state("Polar Sense")

log = logging.getLogger("polar_dual")

h10_acc_ts: deque[tuple[float, int]] = deque(maxlen=20)
h10_ecg_ts: deque[tuple[float, int]] = deque(maxlen=20)
sense_ppg_ts: deque[tuple[float, int]] = deque(maxlen=20)
sense_acc_ts: deque[tuple[float, int]] = deque(maxlen=20)
sense_gyro_ts: deque[tuple[float, int]] = deque(maxlen=20)
sense_mag_ts: deque[tuple[float, int]] = deque(maxlen=20)
sense_ppi_ts: deque[tuple[float, int]] = deque(maxlen=20)

_h10_hr_cb = lambda data: feed_hr(data, state_h10)  # noqa: E731
_h10_acc_cb = make_callback(state_h10, h10_acc_ts, "acc")
_h10_ecg_cb = make_callback(state_h10, h10_ecg_ts, "ecg")
_sense_hr_cb = lambda data: feed_hr(data, state_sense)  # noqa: E731
_sense_ppg_cb = make_callback(state_sense, sense_ppg_ts, "ppg")
_sense_acc_cb = make_callback(state_sense, sense_acc_ts, "acc")
_sense_gyro_cb = make_callback(state_sense, sense_gyro_ts, "gyro")
_sense_mag_cb = make_callback(state_sense, sense_mag_ts, "mag")
_sense_ppi_cb = make_callback(state_sense, sense_ppi_ts, "ppi")


async def _battery_loop(conn: Any, state_dict: dict) -> None:
    while True:
        if conn and conn.polar_device and conn.polar_device._client:
            state_dict["battery"] = await read_battery(conn)
        await asyncio.sleep(30)


def _unwrap(state: dict, raw_key: str, count_key: str) -> tuple:
    val = state.get(raw_key) if state.get(count_key, 0) > 0 else None
    if isinstance(val, tuple) and len(val) == 3:
        return val[0], val[1], val[2]
    return None, None, None


def _make_grid(start: float, log_panel: LogPanel | None = None) -> Panel:
    now = time.time()
    elapsed = now - start
    update_hz_for_state(state_h10, ("acc", h10_acc_ts), ("ecg", h10_ecg_ts), now=now)
    update_hz_for_state(
        state_sense,
        ("ppg", sense_ppg_ts),
        ("acc", sense_acc_ts),
        ("gyro", sense_gyro_ts),
        ("mag", sense_mag_ts),
        ("ppi", sense_ppi_ts),
        now=now,
    )

    def _styled_panel(st: dict, is_h10: bool, name: str) -> Panel:
        border = "green" if "connected" in st.get("status", "").lower() else "yellow"
        return Panel(
            device_panel(st, is_h10=is_h10),
            border_style=border,
            expand=True,
        )

    def _info(st: dict, name: str) -> Panel:
        return info_bar(
            elapsed,
            battery=st.get("battery", "-"),
            csv_path=st.get("csv_path", ""),
            csv_rows=st.get("csv_rows_written", 0),
            log_level=log_panel.level if log_panel else "moderate",
        )

    h10_header = header_bar(
        device_name="H10",
        device_addr=state_h10.get("address", ""),
        status=state_h10.get("status", ""),
    )
    sense_header = header_bar(
        device_name="Sense",
        device_addr=state_sense.get("address", ""),
        status=state_sense.get("status", ""),
    )

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)
    grid.add_row(
        Panel(
            Group(
                h10_header,
                _styled_panel(state_h10, True, "H10"),
                _info(state_h10, "H10"),
            ),
            border_style="cyan",
            expand=True,
        ),
        Panel(
            Group(
                sense_header,
                _styled_panel(state_sense, False, "Sense"),
                _info(state_sense, "Sense"),
            ),
            border_style="cyan",
            expand=True,
        ),
    )

    parts: list[Any] = [grid]
    if log_panel and log_panel.level != "minimal":
        parts.append(log_panel.render())

    return Panel(
        Group(*parts),
        title="Dual Polar Dashboard",
        border_style="cyan",
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Dual Polar Terminal Dashboard")
    parser.add_argument("--h10", type=str, default=None, help="MAC/Name of H10")
    parser.add_argument(
        "--sense", type=str, default=None, help="MAC/Name of Verity Sense"
    )
    parser.add_argument("--no-log", action="store_true", help="Disable all CSV logging")
    parser.add_argument(
        "--no-ppi",
        action="store_true",
        help="Only relevant with --no-sdk-mode. Disable the Sense PPI stream "
        "(PPI is unavailable in SDK mode; SDK mode disables HR/PPI).",
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
        "--no-log-full",
        action="store_true",
        help="Disable full-resolution CSV logs for all streams (default: full-res logging ON).",
    )
    parser.add_argument("--log-file", type=str, default=None)
    parser.add_argument("--log-console", action="store_true")
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
    ):
        parser.add_argument(f"--{opt}", type=int, default=None)
    args = parser.parse_args()

    handlers: list[logging.Handler] = []
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    if args.log_console:
        handlers.append(logging.StreamHandler())
    if handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(message)s",
            handlers=handlers,
            force=True,
        )
        log.info("dual dashboard starting (h10=%s, sense=%s)", args.h10, args.sense)

    state_h10["status"] = "Scanning for H10..."
    state_sense["status"] = "Scanning for Sense..."

    # ── Log infrastructure ────────────────────────────────────────────
    log_panel = LogPanel()
    log_panel.set_level(args.log_level)
    log_file = None

    # ── Keyboard reader (L key toggle) ───────────────────────────────
    _win_msvcrt = None
    if sys.platform == "win32":
        import msvcrt as _msvcrt

        _win_msvcrt = _msvcrt

    def _poll_key() -> str | None:
        if _win_msvcrt is not None and _win_msvcrt.kbhit():
            ch = _win_msvcrt.getwch()
            if ch.upper() == "L":
                return "L"
        return None

    start = time.time()
    with Live(_make_grid(start, log_panel), refresh_per_second=10) as live:
        h10_dev, sense_dev = await discover_dual_polar_devices(
            args.h10, args.sense, timeout=10.0
        )

        if h10_dev is not None:
            state_h10["address"] = h10_dev.address  # type: ignore[attr-defined]
            state_h10["status"] = "Found, connecting..."
            log.info("H10 found: %s [%s]", h10_dev.name, h10_dev.address)  # type: ignore[attr-defined]
        else:
            state_h10["status"] = "Not found."
            log.warning("H10 not found")
        if sense_dev is not None:
            state_sense["address"] = sense_dev.address  # type: ignore[attr-defined]
            state_sense["status"] = "Found, connecting..."
            log.info("Sense found: %s [%s]", sense_dev.name, sense_dev.address)  # type: ignore[attr-defined]
        else:
            state_sense["status"] = "Not found."
            log.warning("Sense not found")

        if h10_dev is None and sense_dev is None:
            state_h10["status"] = "No Polar devices found."
            state_sense["status"] = "No Polar devices found."
            live.update(_make_grid(start, log_panel))
            await asyncio.sleep(3)
            return

        # ── Session directory ──────────────────────────────────────────
        session_ts = time.strftime("%Y%m%d_%H%M%S")
        session_dir = PROJECT_ROOT / "data" / "dual" / session_ts
        h10_raw = session_dir / "h10" / "raw" if h10_dev else None
        h10_pp = session_dir / "h10" / "post-processed" if h10_dev else None
        sense_raw = session_dir / "sense" / "raw" if sense_dev else None
        sense_pp = session_dir / "sense" / "post-processed" if sense_dev else None
        for d in (h10_raw, h10_pp, sense_raw, sense_pp):
            if d:
                d.mkdir(parents=True, exist_ok=True)

        # Open event log file
        log_path = session_dir / f"dual_{session_ts}.log"
        try:
            log_file = log_path.open("w", encoding="utf-8")
        except OSError:
            log_file = None

        custom_kwargs = {
            k: v
            for k, v in {
                "acc_sample_rate": args.acc_rate,
                "acc_range": args.acc_range,
                "gyro_sample_rate": args.gyro_rate,
                "gyro_range": args.gyro_range,
                "mag_sample_rate": args.mag_rate,
                "ppg_sample_rate": args.ppg_rate,
                # SDK mode ON by default for the Sense (135 Hz PPG);
                # --no-sdk-mode disables it.
                "sdk_mode": not args.no_sdk_mode,
            }.items()
            if v is not None
        }

        # ── Build callbacks, optionally wrapping with full-res loggers ──
        h10_loggers: dict[str, StreamFrameLogger] = {}
        sense_loggers: dict[str, StreamFrameLogger] = {}

        h10_hr_cb = _h10_hr_cb
        h10_ecg_cb = _h10_ecg_cb
        h10_acc_cb = _h10_acc_cb
        sense_ppg_cb = _sense_ppg_cb
        sense_acc_cb = _sense_acc_cb
        sense_gyro_cb = _sense_gyro_cb
        sense_mag_cb = _sense_mag_cb
        # SDK mode (default) disables the Sense's HR + PPI streams; only start
        # them when SDK mode is off (--no-sdk-mode) and PPI not disabled.
        sdk_off = args.no_sdk_mode
        sense_hr_cb = _sense_hr_cb if sdk_off else None
        sense_ppi_cb = _sense_ppi_cb if (sdk_off and not args.no_ppi) else None

        # Full-resolution logging is ON by default; --no-log-full or --no-log disables it.
        if not args.no_log_full and not args.no_log:
            if h10_raw:
                for stream_name, bare_cb in [
                    ("ecg", _h10_ecg_cb),
                    ("acc", _h10_acc_cb),
                ]:
                    logger = StreamFrameLogger(
                        h10_raw / f"{stream_name}.csv", stream_name
                    )
                    logger.open()
                    h10_loggers[stream_name] = logger
                    if stream_name == "ecg":
                        h10_ecg_cb = make_frame_callback(bare_cb, logger)
                    elif stream_name == "acc":
                        h10_acc_cb = make_frame_callback(bare_cb, logger)
                # HR is special — use _make_hr_logger
                logger = StreamFrameLogger(h10_raw / "hr.csv", "hr")
                logger.open()
                h10_loggers["hr"] = logger
                h10_hr_cb = _make_hr_logger(_h10_hr_cb, logger)
            else:
                h10_hr_cb = _h10_hr_cb
                h10_ecg_cb = _h10_ecg_cb
                h10_acc_cb = _h10_acc_cb

            if sense_raw:
                for stream_name, bare_cb in [
                    ("ppg", _sense_ppg_cb),
                    ("acc", _sense_acc_cb),
                    ("gyro", _sense_gyro_cb),
                    ("mag", _sense_mag_cb),
                    *([] if (args.no_ppi or not sdk_off) else [("ppi", _sense_ppi_cb)]),
                ]:
                    logger = StreamFrameLogger(
                        sense_raw / f"{stream_name}.csv", stream_name
                    )
                    logger.open()
                    sense_loggers[stream_name] = logger
                    if stream_name == "ppi":
                        sense_ppi_cb = make_ppi_callback(bare_cb, logger)
                    else:
                        wrapped = make_frame_callback(bare_cb, logger)
                        if stream_name == "ppg":
                            sense_ppg_cb = wrapped
                        elif stream_name == "acc":
                            sense_acc_cb = wrapped
                        elif stream_name == "gyro":
                            sense_gyro_cb = wrapped
                        elif stream_name == "mag":
                            sense_mag_cb = wrapped
                if sdk_off:
                    logger = StreamFrameLogger(sense_raw / "hr.csv", "hr")
                    logger.open()
                    sense_loggers["hr"] = logger
                    sense_hr_cb = _make_hr_logger(_sense_hr_cb, logger)
            else:
                sense_hr_cb = _sense_hr_cb
                sense_ppg_cb = _sense_ppg_cb
                sense_acc_cb = _sense_acc_cb
                sense_gyro_cb = _sense_gyro_cb
                sense_mag_cb = _sense_mag_cb
                sense_ppi_cb = _sense_ppi_cb

        conn_h10 = conn_sense = None
        tasks = []
        rssi_tasks: list[asyncio.Task[None]] = []

        def _h10_log(msg, sev="info"):
            log_event(log_panel, msg, sev, device="H10", log_file=log_file)

        def _sense_log(msg, sev="info"):
            log_event(log_panel, msg, sev, device="Sense", log_file=log_file)

        if h10_dev is not None:
            conn_h10 = create_polar_connector(
                h10_dev,
                callback=h10_hr_cb,
                ecg_callback=h10_ecg_cb,
                acc_callback=h10_acc_cb,
                verbose=False,
                log_callback=_h10_log,
                **custom_kwargs,
            )
            tasks.append(conn_h10.start_notify())
        if sense_dev is not None:
            conn_sense = create_polar_connector(
                sense_dev,
                callback=sense_hr_cb,
                ppi_callback=sense_ppi_cb,
                ppg_callback=sense_ppg_cb,
                acc_callback=sense_acc_cb,
                gyro_callback=sense_gyro_cb,
                mag_callback=sense_mag_cb,
                verbose=False,
                log_callback=_sense_log,
                **custom_kwargs,
            )
            tasks.append(conn_sense.start_notify())

        batt_tasks: list[asyncio.Task[None]] = []
        csv_h10 = csv_sense = None
        last_log = start
        last_frame_log = start
        h10_frame_counter = FrameCountLogger(log_panel, device="H10", log_file=log_file)
        sense_frame_counter = FrameCountLogger(
            log_panel, device="Sense", log_file=log_file
        )

        try:
            log_event(log_panel, "Starting connections...")
            await asyncio.gather(*tasks)
            log.info(
                "connections established (h10=%s, sense=%s)",
                conn_h10 is not None,
                conn_sense is not None,
            )

            if conn_h10 is not None:
                if conn_h10.stream_errors:
                    failed = ", ".join(conn_h10.stream_errors.keys())
                    state_h10["status"] = f"Connected. Failed: {failed}"
                    log_event(
                        log_panel,
                        f"H10 streams failed: {failed}",
                        "warning",
                        device="H10",
                        log_file=log_file,
                    )
                else:
                    state_h10["status"] = "Connected! Streaming data."
                state_h10["battery"] = await read_battery(conn_h10)
                log_event(
                    log_panel,
                    f"H10 battery: {state_h10['battery']}",
                    device="H10",
                    log_file=log_file,
                )
                rssi_tasks.append(
                    asyncio.create_task(
                        rssi_loop(conn_h10, log_panel, device="H10", log_file=log_file)
                    )
                )
            if conn_sense is not None:
                if conn_sense.stream_errors:
                    failed = ", ".join(conn_sense.stream_errors.keys())
                    state_sense["status"] = f"Connected. Failed: {failed}"
                    log_event(
                        log_panel,
                        f"Sense streams failed: {failed}",
                        "warning",
                        device="Sense",
                        log_file=log_file,
                    )
                else:
                    state_sense["status"] = "Connected! Streaming data."
                state_sense["battery"] = await read_battery(conn_sense)
                log_event(
                    log_panel,
                    f"Sense battery: {state_sense['battery']}",
                    device="Sense",
                    log_file=log_file,
                )
                rssi_tasks.append(
                    asyncio.create_task(
                        rssi_loop(
                            conn_sense, log_panel, device="Sense", log_file=log_file
                        )
                    )
                )

            if not args.no_log:
                if conn_h10 is not None and h10_pp:
                    csv_h10 = CsvLogger(h10_pp / "summary.csv", H10_SUMMARY_COLS)
                    csv_h10.write_header()
                    state_h10["csv_path"] = csv_h10.path_str
                if conn_sense is not None and sense_pp:
                    csv_sense = CsvLogger(sense_pp / "summary.csv", SENSE_SUMMARY_COLS)
                    csv_sense.write_header()
                    state_sense["csv_path"] = csv_sense.path_str

            if conn_h10 is not None:
                batt_tasks.append(
                    asyncio.create_task(_battery_loop(conn_h10, state_h10))
                )
            if conn_sense is not None:
                batt_tasks.append(
                    asyncio.create_task(_battery_loop(conn_sense, state_sense))
                )

            while True:
                # Poll L key
                key = _poll_key()
                if key == "L":
                    new_level = log_panel.cycle_level()
                    log_event(log_panel, f"Log level: {new_level}", log_file=log_file)

                now = time.time()
                if (now - last_log) >= 1.0:
                    last_log = now
                    ts_str = time.strftime("%Y-%m-%d %H:%M:%S")

                    if csv_h10:
                        ax, ay, az = _unwrap(state_h10, "acc_raw", "acc_count")
                        csv_h10.write_row(
                            [
                                ts_str,
                                state_h10["hr"],
                                calculate_rmssd(state_h10["rr_history"]),
                                state_h10.get("battery"),
                                state_h10.get("ecg_last_sample"),
                                ax,
                                ay,
                                az,
                            ]
                        )
                        state_h10["csv_rows_written"] = csv_h10.rows_written

                    if csv_sense:
                        ax, ay, az = _unwrap(state_sense, "acc_raw", "acc_count")
                        gx, gy, gz = _unwrap(state_sense, "gyro_raw", "gyro_count")
                        mx, my, mz = _unwrap(state_sense, "mag_raw", "mag_count")
                        csv_sense.write_row(
                            [
                                ts_str,
                                state_sense["hr"],
                                calculate_rmssd(state_sense["rr_history"]),
                                state_sense.get("battery"),
                                state_sense.get("ppg_last_sample"),
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
                        state_sense["csv_rows_written"] = csv_sense.rows_written

                # Verbose: log frame count deltas every second
                if log_panel.level == "verbose" and (now - last_frame_log) >= 1.0:
                    last_frame_log = now
                    if conn_h10 is not None:
                        h10_frame_counter.check(state_h10, ["ecg", "acc"])
                    if conn_sense is not None:
                        sense_streams = ["ppg", "acc", "gyro", "mag"]
                        if sdk_off and not args.no_ppi:
                            sense_streams.append("ppi")
                        sense_frame_counter.check(state_sense, sense_streams)

                live.update(_make_grid(start, log_panel))
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            if conn_h10:
                state_h10["status"] = f"Error: {e}"
            if conn_sense:
                state_sense["status"] = f"Error: {e}"
            log_event(log_panel, f"Error: {e}", "error", log_file=log_file)
            live.update(_make_grid(start, log_panel))
            await asyncio.sleep(3)
        finally:
            for st in (state_h10, state_sense):
                st["status"] = "Disconnecting..."
            live.update(_make_grid(start, log_panel))
            for bt in batt_tasks:
                bt.cancel()
            for rt in rssi_tasks:
                rt.cancel()
            await asyncio.gather(
                *(c.stop_notify() for c in (conn_h10, conn_sense) if c)
            )
            for logger in {**h10_loggers, **sense_loggers}.values():
                logger.close()
            for st in (state_h10, state_sense):
                st["status"] = "Disconnected."
            live.update(_make_grid(start, log_panel))
            if log_file:
                log_file.close()

            # Session-end Hz verification
            if conn_h10 is not None:
                print_hz_summary({"ecg": 130, "acc": 200}, state_h10)
            if conn_sense is not None:
                extra = ["ppi"] if sdk_off and not args.no_ppi else []
                print_hz_summary(
                    {"ppg": 55, "acc": 52, "gyro": 52, "mag": 20},
                    state_sense,
                    extra_streams=extra,
                )
            await asyncio.sleep(1)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
