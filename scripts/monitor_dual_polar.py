"""Dual-device terminal dashboard for Polar H10 + Verity Sense."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import logging
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from rich.live import Live  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

from polar_ble_sdk.connector.ble_discovery import (  # noqa: E402
    discover_dual_polar_devices,
)
from polar_ble_sdk.connector.stream import create_polar_connector  # noqa: E402
from polar_ble_sdk.dashboard_utils import (  # noqa: E402
    CsvLogger,
    calculate_rmssd,
    device_panel,
    feed_hr,
    make_callback,
    make_device_state,
    read_battery,
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

# ── Full-resolution logger ─────────────────────────────────────────────


class _StreamFrameLogger:
    _COLUMNS: dict[str, list[str]] = {
        "ecg": ["Timestamp_s", "uV_Samples"],
        "ppg": ["Timestamp_s", "Sample_Channels"],
        "acc": ["Timestamp_s", "X_mG", "Y_mG", "Z_mG"],
        "gyro": ["Timestamp_s", "X_dps", "Y_dps", "Z_dps"],
        "mag": ["Timestamp_s", "X_G", "Y_G", "Z_G"],
        "hr": ["Timestamp_s", "HeartRate_BPM", "RR_Intervals_ms"],
        "ppi": ["Timestamp_s", "PPI_ms"],
    }
    _WIDE_COLUMS: set[str] = {"ecg", "ppg"}

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
        elif self._stream in self._WIDE_COLUMS:
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


def _make_frame_callback(dashboard_cb, frame_logger: _StreamFrameLogger):
    def cb(data):
        dashboard_cb(data)
        timestamp, samples = data
        frame_logger.write_frame(timestamp, samples)

    return cb


def _make_ppi_callback(dashboard_cb, frame_logger: _StreamFrameLogger):
    def cb(data):
        dashboard_cb(data)
        frame_logger.write_ppi_frames(data)

    return cb


def _make_hr_logger(hr_cb, hr_logger: _StreamFrameLogger):
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
    val = state.get(raw_key) if state.get(count_key, 0) > 0 else (None, None, None)
    assert isinstance(val, tuple) and len(val) == 3
    return val[0], val[1], val[2]


def _make_grid(start: float) -> Panel:
    now = time.time()
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
            title=f"{name}  |  Battery: {st.get('battery', '-')}  |  CSV: {st.get('csv_rows_written', 0)}",
            border_style=border,
            expand=True,
        )

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)
    grid.add_row(
        _styled_panel(state_h10, True, "H10"),
        _styled_panel(state_sense, False, "Sense"),
    )
    return Panel(
        grid,
        title=f"Dual Polar Dashboard  |  Elapsed: {now - start:.1f}s",
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
        "--log-full",
        action="store_true",
        help="Enable full-resolution CSV logs for all streams on both devices.",
    )
    parser.add_argument("--log-file", type=str, default=None)
    parser.add_argument("--log-console", action="store_true")
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

    start = time.time()
    with Live(_make_grid(start), refresh_per_second=10) as live:
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
            live.update(_make_grid(start))
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

        # ── Build callbacks, optionally wrapping with full-res loggers ──
        h10_loggers: dict[str, _StreamFrameLogger] = {}
        sense_loggers: dict[str, _StreamFrameLogger] = {}

        h10_hr_cb = _h10_hr_cb
        h10_ecg_cb = _h10_ecg_cb
        h10_acc_cb = _h10_acc_cb
        sense_hr_cb = _sense_hr_cb
        sense_ppg_cb = _sense_ppg_cb
        sense_acc_cb = _sense_acc_cb
        sense_gyro_cb = _sense_gyro_cb
        sense_mag_cb = _sense_mag_cb
        sense_ppi_cb = _sense_ppi_cb

        if args.log_full:
            if h10_raw:
                for stream_name, bare_cb in [
                    ("ecg", _h10_ecg_cb),
                    ("acc", _h10_acc_cb),
                ]:
                    logger = _StreamFrameLogger(
                        h10_raw / f"{stream_name}.csv", stream_name
                    )
                    logger.open()
                    h10_loggers[stream_name] = logger
                    if stream_name == "ecg":
                        h10_ecg_cb = _make_frame_callback(bare_cb, logger)
                    elif stream_name == "acc":
                        h10_acc_cb = _make_frame_callback(bare_cb, logger)
                # HR is special — use _make_hr_logger
                logger = _StreamFrameLogger(h10_raw / "hr.csv", "hr")
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
                    ("ppi", _sense_ppi_cb),
                ]:
                    logger = _StreamFrameLogger(
                        sense_raw / f"{stream_name}.csv", stream_name
                    )
                    logger.open()
                    sense_loggers[stream_name] = logger
                    if stream_name == "ppi":
                        sense_ppi_cb = _make_ppi_callback(bare_cb, logger)
                    else:
                        wrapped = _make_frame_callback(bare_cb, logger)
                        if stream_name == "ppg":
                            sense_ppg_cb = wrapped
                        elif stream_name == "acc":
                            sense_acc_cb = wrapped
                        elif stream_name == "gyro":
                            sense_gyro_cb = wrapped
                        elif stream_name == "mag":
                            sense_mag_cb = wrapped
                logger = _StreamFrameLogger(sense_raw / "hr.csv", "hr")
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

        if h10_dev is not None:
            conn_h10 = create_polar_connector(
                h10_dev,
                callback=h10_hr_cb,
                ecg_callback=h10_ecg_cb,
                acc_callback=h10_acc_cb,
                verbose=False,
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
                **custom_kwargs,
            )
            tasks.append(conn_sense.start_notify())

        batt_tasks: list[asyncio.Task[None]] = []
        csv_h10 = csv_sense = None
        last_log = start

        try:
            await asyncio.gather(*tasks)
            log.info(
                "connections established (h10=%s, sense=%s)",
                conn_h10 is not None,
                conn_sense is not None,
            )

            if conn_h10 is not None:
                state_h10["status"] = "Connected! Streaming data."
                state_h10["battery"] = await read_battery(conn_h10)
                log.info("H10 battery: %s", state_h10["battery"])
            if conn_sense is not None:
                state_sense["status"] = "Connected! Streaming data."
                state_sense["battery"] = await read_battery(conn_sense)
                log.info("Sense battery: %s", state_sense["battery"])

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

                live.update(_make_grid(start))
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            if conn_h10:
                state_h10["status"] = f"Error: {e}"
            if conn_sense:
                state_sense["status"] = f"Error: {e}"
            live.update(_make_grid(start))
            await asyncio.sleep(3)
        finally:
            for st in (state_h10, state_sense):
                st["status"] = "Disconnecting..."
            live.update(_make_grid(start))
            for bt in batt_tasks:
                bt.cancel()
            await asyncio.gather(
                *(c.stop_notify() for c in (conn_h10, conn_sense) if c)
            )
            for logger in {**h10_loggers, **sense_loggers}.values():
                logger.close()
            for st in (state_h10, state_sense):
                st["status"] = "Disconnected."
            live.update(_make_grid(start))
            await asyncio.sleep(1)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
