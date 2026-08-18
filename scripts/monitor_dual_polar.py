"""Dual-device terminal dashboard for simultaneous recording of Polar H10 + Verity Sense."""

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
from polar_ble_sdk.diagnostics.battery import (  # noqa: E402
    read_battery,
    update_battery_loop,
)
from polar_ble_sdk.diagnostics.rssi import (  # noqa: E402
    FrameCountLogger,
    rssi_loop,
)
from polar_ble_sdk.input.keyboard import (  # noqa: E402
    NonBlockingKeyboardReader,
    parse_marker_specs,
)
from polar_ble_sdk.metrics.hrv import calculate_rmssd  # noqa: E402
from polar_ble_sdk.metrics.rate_tracker import (  # noqa: E402
    RateTracker,
    print_hz_summary,
    update_hz_for_state,
)
from polar_ble_sdk.session.session import (  # noqa: E402
    DeviceMetadata,
    SessionManager,
)
from polar_ble_sdk.session.state import (  # noqa: E402
    feed_hr,
    make_callback,
    make_device_state,
    unwrap_vector,
)
from polar_ble_sdk.storage.frame_logger import (  # noqa: E402
    make_frame_callback,
    make_hr_callback,
    make_ppi_callback,
)
from polar_ble_sdk.storage.summary_logger import CsvLogger  # noqa: E402
from polar_ble_sdk.ui.components import (  # noqa: E402
    device_panel,
    header_bar,
    info_bar,
)
from polar_ble_sdk.ui.log_panel import (  # noqa: E402
    LogPanel,
    log_event,
)

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

state_h10 = make_device_state("Polar H10")
state_sense = make_device_state("Polar Sense")


def _make_grid(
    start: float,
    h10_ts: tuple[deque, deque],
    sense_ts: tuple[deque, deque, deque, deque, deque],
    log_panel: LogPanel | None = None,
) -> Panel:
    now = time.time()
    elapsed = now - start
    update_hz_for_state(state_h10, ("acc", h10_ts[0]), ("ecg", h10_ts[1]), now=now)
    update_hz_for_state(
        state_sense,
        ("ppg", sense_ts[0]),
        ("acc", sense_ts[1]),
        ("gyro", sense_ts[2]),
        ("mag", sense_ts[3]),
        ("ppi", sense_ts[4]),
        now=now,
    )

    def _styled_panel(st: dict[str, Any], is_h10: bool) -> Panel:
        border = "green" if "connected" in st.get("status", "").lower() else "yellow"
        return Panel(
            device_panel(st, is_h10=is_h10),
            border_style=border,
            expand=True,
        )

    def _info(st: dict[str, Any]) -> Panel:
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
                _styled_panel(state_h10, True),
                _info(state_h10),
            ),
            border_style="cyan",
            expand=True,
        ),
        Panel(
            Group(
                sense_header,
                _styled_panel(state_sense, False),
                _info(state_sense),
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
        help="Disable Sense PPI stream (only relevant with --no-sdk-mode).",
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
        "--no-log-full",
        action="store_true",
        help="Disable full-resolution CSV logs (default is ON).",
    )
    parser.add_argument(
        "--markers",
        type=str,
        default=None,
        help="Custom hotkeys: KEY=LABEL,KEY2=LABEL2",
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

    # ── Session & Logging Infrastructure ──────────────────────────────
    session_mgr = SessionManager(
        base_dir=PROJECT_ROOT,
        device_type="dual",
        is_dual=True,
    )
    session_mgr.init_event_log(prefix="dual")
    log_panel = LogPanel()
    log_panel.set_level(args.log_level)

    try:
        hotkeys = parse_marker_specs(args.markers)
    except ValueError as e:
        parser.error(str(e))
    hotkeys["L"] = "__toggle_log__"
    reader = NonBlockingKeyboardReader(hotkeys)

    print("Scanning for Polar H10 and Verity Sense...")
    h10_dev, sense_dev = await discover_dual_polar_devices(
        h10_target=args.h10,
        sense_target=args.sense,
        timeout=10.0,
    )

    if not h10_dev or not sense_dev:
        missing = []
        if not h10_dev:
            missing.append("Polar H10")
        if not sense_dev:
            missing.append("Polar Verity Sense")
        print(f"Error: Missing devices: {', '.join(missing)}")
        return

    h10_name = getattr(h10_dev, "name", "") or "Polar H10"
    h10_addr = getattr(h10_dev, "address", "") or "-"
    sense_name = getattr(sense_dev, "name", "") or "Polar Verity Sense"
    sense_addr = getattr(sense_dev, "address", "") or "-"

    state_h10["name"] = h10_name
    state_h10["address"] = h10_addr
    state_h10["status"] = "Connecting..."

    state_sense["name"] = sense_name
    state_sense["address"] = sense_addr
    state_sense["status"] = "Connecting..."

    session_mgr.metadata.devices["h10"] = DeviceMetadata(
        name=h10_name, address=h10_addr, device_type="h10"
    )
    session_mgr.metadata.devices["sense"] = DeviceMetadata(
        name=sense_name, address=sense_addr, device_type="sense"
    )

    # ── Deques for Hz tracking ────────────────────────────────────────
    h10_acc_ts: deque[tuple[float, int]] = deque(maxlen=20)
    h10_ecg_ts: deque[tuple[float, int]] = deque(maxlen=20)
    sense_ppg_ts: deque[tuple[float, int]] = deque(maxlen=20)
    sense_acc_ts: deque[tuple[float, int]] = deque(maxlen=20)
    sense_gyro_ts: deque[tuple[float, int]] = deque(maxlen=20)
    sense_mag_ts: deque[tuple[float, int]] = deque(maxlen=20)
    sense_ppi_ts: deque[tuple[float, int]] = deque(maxlen=20)

    # ── Callbacks ─────────────────────────────────────────────────────
    def _raw_h10_hr_cb(data: Any) -> None:
        feed_hr(data, state_h10)

    _h10_hr_cb: Callable[[Any], None] = _raw_h10_hr_cb
    _h10_acc_cb = make_callback(state_h10, h10_acc_ts, "acc")
    _h10_ecg_cb = make_callback(state_h10, h10_ecg_ts, "ecg")

    def _raw_sense_hr_cb(data: Any) -> None:
        feed_hr(data, state_sense)

    _sense_hr_cb: Callable[[Any], None] = _raw_sense_hr_cb
    _sense_ppg_cb = make_callback(state_sense, sense_ppg_ts, "ppg")
    _sense_acc_cb = make_callback(state_sense, sense_acc_ts, "acc")
    _sense_gyro_cb = make_callback(state_sense, sense_gyro_ts, "gyro")
    _sense_mag_cb = make_callback(state_sense, sense_mag_ts, "mag")
    _sense_ppi_cb = make_callback(state_sense, sense_ppi_ts, "ppi")

    if not args.no_log_full and not args.no_log:
        fl_h10_hr = session_mgr.create_frame_logger("hr", sub_device="h10")
        fl_h10_ecg = session_mgr.create_frame_logger("ecg", sub_device="h10")
        fl_h10_acc = session_mgr.create_frame_logger("acc", sub_device="h10")

        _h10_hr_cb = make_hr_callback(_h10_hr_cb, fl_h10_hr)
        _h10_ecg_cb = make_frame_callback(_h10_ecg_cb, fl_h10_ecg)
        _h10_acc_cb = make_frame_callback(_h10_acc_cb, fl_h10_acc)

        fl_sense_ppg = session_mgr.create_frame_logger("ppg", sub_device="sense")
        fl_sense_acc = session_mgr.create_frame_logger("acc", sub_device="sense")
        fl_sense_gyro = session_mgr.create_frame_logger("gyro", sub_device="sense")
        fl_sense_mag = session_mgr.create_frame_logger("mag", sub_device="sense")

        _sense_ppg_cb = make_frame_callback(_sense_ppg_cb, fl_sense_ppg)
        _sense_acc_cb = make_frame_callback(_sense_acc_cb, fl_sense_acc)
        _sense_gyro_cb = make_frame_callback(_sense_gyro_cb, fl_sense_gyro)
        _sense_mag_cb = make_frame_callback(_sense_mag_cb, fl_sense_mag)

        if args.no_sdk_mode and not args.no_ppi:
            fl_sense_hr = session_mgr.create_frame_logger("hr", sub_device="sense")
            fl_sense_ppi = session_mgr.create_frame_logger("ppi", sub_device="sense")
            _sense_hr_cb = make_hr_callback(_sense_hr_cb, fl_sense_hr)
            _sense_ppi_cb = make_ppi_callback(_sense_ppi_cb, fl_sense_ppi)

    conn_h10 = create_polar_connector(
        h10_dev,
        callback=_h10_hr_cb,
        ecg_callback=_h10_ecg_cb,
        acc_callback=_h10_acc_cb,
        verbose=False,
        log_callback=lambda msg, sev="info": log_event(
            log_panel, msg, sev, device="H10", log_file=session_mgr.log_file
        ),
    )

    sense_kwargs: dict[str, Any] = {"sdk_mode": not args.no_sdk_mode}
    if args.ppg_rate:
        sense_kwargs["ppg_sample_rate"] = args.ppg_rate

    conn_sense = create_polar_connector(
        sense_dev,
        callback=_sense_hr_cb if args.no_sdk_mode else None,
        ppi_callback=_sense_ppi_cb if (args.no_sdk_mode and not args.no_ppi) else None,
        ppg_callback=_sense_ppg_cb,
        acc_callback=_sense_acc_cb,
        gyro_callback=_sense_gyro_cb,
        mag_callback=_sense_mag_cb,
        verbose=False,
        log_callback=lambda msg, sev="info": log_event(
            log_panel, msg, sev, device="Sense", log_file=session_mgr.log_file
        ),
        **sense_kwargs,
    )

    start = time.time()

    def build() -> Panel:
        return _make_grid(
            start,
            (h10_acc_ts, h10_ecg_ts),
            (sense_ppg_ts, sense_acc_ts, sense_gyro_ts, sense_mag_ts, sense_ppi_ts),
            log_panel=log_panel,
        )

    with Live(build(), refresh_per_second=10) as live:
        last_log = start
        last_frame_log = start
        csv_h10 = None
        csv_sense = None

        if not args.no_log:
            pp_h10 = session_mgr.get_post_processed_dir("h10")
            pp_sense = session_mgr.get_post_processed_dir("sense")
            csv_h10 = CsvLogger(pp_h10 / "summary.csv", H10_SUMMARY_COLS)
            csv_h10.write_header()
            csv_sense = CsvLogger(pp_sense / "summary.csv", SENSE_SUMMARY_COLS)
            csv_sense.write_header()
            state_h10["csv_path"] = csv_h10.path_str
            state_sense["csv_path"] = csv_sense.path_str

        batt_h10_task = None
        batt_sense_task = None
        rssi_h10_task = None
        rssi_sense_task = None

        h10_frame_counter = FrameCountLogger(
            log_panel, device="H10", log_file=session_mgr.log_file
        )
        sense_frame_counter = FrameCountLogger(
            log_panel, device="Sense", log_file=session_mgr.log_file
        )

        try:
            log_event(
                log_panel,
                "Connecting H10...",
                device="H10",
                log_file=session_mgr.log_file,
            )
            await conn_h10.start_notify()
            if conn_h10.stream_errors:
                failed = ", ".join(conn_h10.stream_errors.keys())
                state_h10["status"] = f"Connected. Failed: {failed}"
                log_event(
                    log_panel,
                    f"H10 streams failed: {failed}",
                    "warning",
                    device="H10",
                    log_file=session_mgr.log_file,
                )
            else:
                state_h10["status"] = "Connected! Streaming."
            state_h10["battery"] = await read_battery(conn_h10)
            log_event(
                log_panel,
                f"H10 battery: {state_h10['battery']}",
                "info",
                device="H10",
                log_file=session_mgr.log_file,
            )

            log_event(
                log_panel,
                "Connecting Sense...",
                device="Sense",
                log_file=session_mgr.log_file,
            )
            await conn_sense.start_notify()
            if conn_sense.stream_errors:
                failed = ", ".join(conn_sense.stream_errors.keys())
                state_sense["status"] = f"Connected. Failed: {failed}"
                log_event(
                    log_panel,
                    f"Sense streams failed: {failed}",
                    "warning",
                    device="Sense",
                    log_file=session_mgr.log_file,
                )
            else:
                state_sense["status"] = "Connected! Streaming."
            state_sense["battery"] = await read_battery(conn_sense)
            log_event(
                log_panel,
                f"Sense battery: {state_sense['battery']}",
                "info",
                device="Sense",
                log_file=session_mgr.log_file,
            )

            batt_h10_task = asyncio.create_task(
                update_battery_loop(conn_h10, state_h10)
            )
            batt_sense_task = asyncio.create_task(
                update_battery_loop(conn_sense, state_sense)
            )

            rssi_h10_task = asyncio.create_task(
                rssi_loop(
                    conn_h10, log_panel, device="H10", log_file=session_mgr.log_file
                )
            )
            rssi_sense_task = asyncio.create_task(
                rssi_loop(
                    conn_sense, log_panel, device="Sense", log_file=session_mgr.log_file
                )
            )

            while True:
                for m in reader.poll_markers():
                    if m == "__toggle_log__":
                        lvl = log_panel.cycle_level()
                        log_event(
                            log_panel,
                            f"Log level: {lvl}",
                            "info",
                            log_file=session_mgr.log_file,
                        )
                        continue
                    session_mgr.register_marker(m)
                    log_event(
                        log_panel, f"Marker: {m}", "info", log_file=session_mgr.log_file
                    )

                now = time.time()
                if not args.no_log and (now - last_log) >= 1.0:
                    last_log = now
                    ts_str = time.strftime("%Y-%m-%d %H:%M:%S")
                    if csv_h10:
                        h10_rmssd = calculate_rmssd(state_h10["rr_history"])
                        ax, ay, az = unwrap_vector(state_h10, "acc_raw", "acc_count")
                        csv_h10.write_row(
                            [
                                ts_str,
                                state_h10["hr"],
                                h10_rmssd,
                                state_h10.get("battery"),
                                state_h10.get("ecg_last_sample"),
                                ax,
                                ay,
                                az,
                            ]
                        )
                        state_h10["csv_rows_written"] = csv_h10.rows_written

                    if csv_sense:
                        sense_rmssd = calculate_rmssd(state_sense["rr_history"])
                        sax, say, saz = unwrap_vector(
                            state_sense, "acc_raw", "acc_count"
                        )
                        gx, gy, gz = unwrap_vector(
                            state_sense, "gyro_raw", "gyro_count"
                        )
                        mx, my, mz = unwrap_vector(state_sense, "mag_raw", "mag_count")
                        csv_sense.write_row(
                            [
                                ts_str,
                                state_sense["hr"],
                                sense_rmssd,
                                state_sense.get("battery"),
                                state_sense.get("ppg_last_sample"),
                                sax,
                                say,
                                saz,
                                gx,
                                gy,
                                gz,
                                mx,
                                my,
                                mz,
                            ]
                        )
                        state_sense["csv_rows_written"] = csv_sense.rows_written

                if log_panel.level == "verbose" and (now - last_frame_log) >= 1.0:
                    last_frame_log = now
                    h10_frame_counter.check(state_h10, ["ecg", "acc"])
                    sense_streams = ["ppg", "acc", "gyro", "mag"]
                    if args.no_sdk_mode and not args.no_ppi:
                        sense_streams.append("ppi")
                    sense_frame_counter.check(state_sense, sense_streams)

                if args.duration and (now - start) >= args.duration:
                    log_event(
                        log_panel,
                        f"Target duration ({args.duration}s) reached.",
                        "info",
                        log_file=session_mgr.log_file,
                    )
                    break

                live.update(build())
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            state_h10["status"] = f"Error: {e}"
            state_sense["status"] = f"Error: {e}"
            live.update(build())
            await asyncio.sleep(3)
        finally:
            if batt_h10_task:
                batt_h10_task.cancel()
            if batt_sense_task:
                batt_sense_task.cancel()
            if rssi_h10_task:
                rssi_h10_task.cancel()
            if rssi_sense_task:
                rssi_sense_task.cancel()

            await conn_h10.stop_notify()
            await conn_sense.stop_notify()

            rate_tracker = RateTracker()

            def _accumulate(st: dict[str, Any], prefix: str) -> None:
                for s_name, s_acc in st.get("_session_streams", {}).items():
                    key = f"{prefix}_{s_name}"
                    rate_tracker.track(
                        key, s_acc["samples"], timestamp=s_acc["last_ts"]
                    )
                    if key in rate_tracker.accumulators:
                        rate_tracker.accumulators[key].first_ts = s_acc["first_ts"]

            _accumulate(state_h10, "h10")
            _accumulate(state_sense, "sense")

            session_mgr.close_all(
                rate_tracker=rate_tracker,
                configured_rates={
                    "h10_ecg": 130,
                    "h10_acc": 200,
                    "sense_ppg": 55,
                    "sense_acc": 52,
                    "sense_gyro": 52,
                    "sense_mag": 20,
                },
            )

            print_hz_summary({"ecg": 130, "acc": 200}, state_h10)
            print_hz_summary(
                {"ppg": 55, "acc": 52, "gyro": 52, "mag": 20},
                state_sense,
                extra_streams=(
                    ["ppi"] if (args.no_sdk_mode and not args.no_ppi) else None
                ),
            )
            state_h10["status"] = "Disconnected."
            state_sense["status"] = "Disconnected."
            live.update(build())
            await asyncio.sleep(1)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
