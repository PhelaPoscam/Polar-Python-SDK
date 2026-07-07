"""Dual-device terminal dashboard for Polar H10 + Verity Sense."""

from __future__ import annotations

import argparse
import asyncio
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
    make_device_state,
    read_battery,
    feed_hr,
    make_callback,
    update_hz_for_state,
)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

H10_CSV = [
    "Timestamp",
    "HeartRate_BPM",
    "HRV_RMSSD_ms",
    "Battery",
    "ACC_X",
    "ACC_Y",
    "ACC_Z",
]
SENSE_CSV = [
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

h10_acc_ts: deque[tuple[float, int]] = deque(maxlen=20)
sense_ppg_ts: deque[tuple[float, int]] = deque(maxlen=20)
sense_acc_ts: deque[tuple[float, int]] = deque(maxlen=20)
sense_gyro_ts: deque[tuple[float, int]] = deque(maxlen=20)
sense_mag_ts: deque[tuple[float, int]] = deque(maxlen=20)


# ponytail: closures created once at module level, not per-callback

_h10_hr_cb = lambda data: feed_hr(data, state_h10)  # noqa: E731
_h10_acc_cb = make_callback(state_h10, h10_acc_ts, "acc")
_sense_hr_cb = lambda data: feed_hr(data, state_sense)  # noqa: E731
_sense_ppg_cb = make_callback(state_sense, sense_ppg_ts, "ppg")
_sense_acc_cb = make_callback(state_sense, sense_acc_ts, "acc")
_sense_gyro_cb = make_callback(state_sense, sense_gyro_ts, "gyro")
_sense_mag_cb = make_callback(state_sense, sense_mag_ts, "mag")


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
    update_hz_for_state(state_h10, ("acc", h10_acc_ts), now=now)
    update_hz_for_state(
        state_sense,
        ("ppg", sense_ppg_ts),
        ("acc", sense_acc_ts),
        ("gyro", sense_gyro_ts),
        ("mag", sense_mag_ts),
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
    parser.add_argument("--h10", type=str, default=None, help="MAC/Name of H10 strap")
    parser.add_argument(
        "--sense", type=str, default=None, help="MAC/Name of Verity Sense"
    )
    parser.add_argument("--no-log", action="store_true", help="Disable CSV logging")
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
        else:
            state_h10["status"] = "Not found."
        if sense_dev is not None:
            state_sense["address"] = sense_dev.address  # type: ignore[attr-defined]
            state_sense["status"] = "Found, connecting..."
        else:
            state_sense["status"] = "Not found."

        if h10_dev is None and sense_dev is None:
            state_h10["status"] = "No Polar devices found."
            state_sense["status"] = "No Polar devices found."
            live.update(_make_grid(start))
            await asyncio.sleep(3)
            return

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

        conn_h10 = conn_sense = None
        tasks = []

        if h10_dev is not None:
            conn_h10 = create_polar_connector(
                h10_dev,
                callback=_h10_hr_cb,
                acc_callback=_h10_acc_cb,
                verbose=False,
                **custom_kwargs,
            )
            tasks.append(conn_h10.start_notify())
        if sense_dev is not None:
            conn_sense = create_polar_connector(
                sense_dev,
                callback=_sense_hr_cb,
                ppi_callback=lambda x: None,
                ppg_callback=_sense_ppg_cb,
                acc_callback=_sense_acc_cb,
                gyro_callback=_sense_gyro_cb,
                mag_callback=_sense_mag_cb,
                verbose=False,
                **custom_kwargs,
            )
            tasks.append(conn_sense.start_notify())

        batt_tasks: list[asyncio.Task[None]] = []
        csv_h10 = csv_sense = None
        last_log = start

        try:
            await asyncio.gather(*tasks)

            if conn_h10 is not None:
                state_h10["status"] = "Connected! Streaming data."
                state_h10["battery"] = await read_battery(conn_h10)
            if conn_sense is not None:
                state_sense["status"] = "Connected! Streaming data."
                state_sense["battery"] = await read_battery(conn_sense)

            ts = time.strftime("%Y%m%d_%H%M%S")
            log_dir = PROJECT_ROOT / "data"
            log_dir.mkdir(exist_ok=True)

            if not args.no_log:
                if conn_h10 is not None:
                    csv_h10 = CsvLogger(log_dir / f"dual_session_h10_{ts}.csv", H10_CSV)
                    csv_h10.write_header()
                    state_h10["csv_path"] = csv_h10.path_str
                if conn_sense is not None:
                    csv_sense = CsvLogger(
                        log_dir / f"dual_session_sense_{ts}.csv", SENSE_CSV
                    )
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

            for st in (state_h10, state_sense):
                st["status"] = "Disconnected."
            live.update(_make_grid(start))
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
