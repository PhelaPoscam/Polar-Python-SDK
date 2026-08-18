"""In-memory device state models and sensor feed callbacks for Polar streams."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from typing import Any


def make_device_state(name: str = "Polar Device") -> dict[str, Any]:
    """Build a standardized default state dict for a Polar device dashboard."""
    return {
        "name": name,
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
        "ecg_count": 0,
        "ecg_hz": 0.0,
        "ecg_last_sample": "-",
        "mag_count": 0,
        "mag_hz": 0.0,
        "mag_last_sample": "-",
        "mag_raw": (0.0, 0.0, 0.0),
        "ppi_count": 0,
        "ppi_hz": 0.0,
        "ppi_last_sample": "-",
        "ppi_err_est": 0,
        "ppi_contact_pct": 100,
        "battery": "-",
        "marker_log": deque(maxlen=5),
        "last_marker": "-",
        "csv_path": "-",
        "csv_rows_written": 0,
        # Session-level accumulators for Hz verification
        "_session_streams": {},
    }


def _track_session(state: dict[str, Any], stream: str, sample_count: int) -> None:
    """Increment session-level accumulators for post-session Hz verification."""
    now = time.time()
    acc = state["_session_streams"].setdefault(
        stream, {"samples": 0, "first_ts": now, "last_ts": now}
    )
    acc["samples"] += sample_count
    acc["last_ts"] = now


def feed_hr(data: Any, state: dict[str, Any]) -> None:
    """Update state from a standard Bluetooth Heart Rate (hr, rr_intervals) tuple."""
    if isinstance(data, tuple) and len(data) >= 2:
        hr_val, rr_ints = data
        if hr_val > 0:
            state["hr"] = hr_val
            state["hr_history"].append(hr_val)
        if rr_ints:
            state["rr_intervals"] = rr_ints
            state["rr_history"].extend(rr_ints)


def feed_ppg(data: Any, state: dict[str, Any], ts: deque) -> None:
    """Update state and timestamp deque from optical PPG callback data."""
    _timestamp, samples = data
    state["ppg_count"] += len(samples)
    ts.append((time.time(), len(samples)))
    state["ppg_last_sample"] = str(samples[-1] if samples else "")
    _track_session(state, "ppg", len(samples))


def feed_acc(data: Any, state: dict[str, Any], ts: deque) -> None:
    """Update state and timestamp deque from 3D Accelerometer callback data."""
    _timestamp, samples = data
    state["acc_count"] += len(samples)
    ts.append((time.time(), len(samples)))
    if samples:
        last_val = samples[-1]
        state["acc_raw"] = (last_val[0], last_val[1], last_val[2])
        state["acc_last_sample"] = (
            f"({last_val[0]:+4d}, {last_val[1]:+4d}, {last_val[2]:+4d}) mg"
        )
    _track_session(state, "acc", len(samples))


def feed_gyro(data: Any, state: dict[str, Any], ts: deque) -> None:
    """Update state and timestamp deque from 3D Gyroscope callback data."""
    _timestamp, samples = data
    state["gyro_count"] += len(samples)
    ts.append((time.time(), len(samples)))
    if samples:
        last_val = samples[-1]
        state["gyro_raw"] = (last_val[0], last_val[1], last_val[2])
        state["gyro_last_sample"] = (
            f"({last_val[0]:+4.1f}, {last_val[1]:+4.1f}, {last_val[2]:+4.1f}) dps"
        )
    _track_session(state, "gyro", len(samples))


def feed_mag(data: Any, state: dict[str, Any], ts: deque) -> None:
    """Update state and timestamp deque from 3D Magnetometer callback data."""
    _timestamp, samples = data
    state["mag_count"] += len(samples)
    ts.append((time.time(), len(samples)))
    if samples:
        last_val = samples[-1]
        state["mag_raw"] = (last_val[0], last_val[1], last_val[2])
        state["mag_last_sample"] = (
            f"({last_val[0]:+3.1f}, {last_val[1]:+3.1f}, {last_val[2]:+3.1f}) uT"
        )
    _track_session(state, "mag", len(samples))


def feed_ecg(data: Any, state: dict[str, Any], ts: deque) -> None:
    """Update state and timestamp deque from ECG callback data."""
    _timestamp, samples = data
    state["ecg_count"] += len(samples)
    ts.append((time.time(), len(samples)))
    if samples:
        last_val = samples[-1]
        state["ecg_last_sample"] = f"{last_val:+5d} µV"
    _track_session(state, "ecg", len(samples))


def feed_ppi(data: Any, state: dict[str, Any], ts: deque) -> None:
    """Update state and timestamp deque from Peak-to-Peak Interval (PPI) callback data."""
    if not data:
        return
    state["ppi_count"] += len(data)
    ts.append((time.time(), len(data)))
    last = data[-1]
    if len(last) >= 4:
        last_ppi, last_err, last_hr = last[1], last[2], last[3]
        last_contact = last[4] if len(last) >= 5 else None
        state["ppi_last_sample"] = (
            f"PPI={last_ppi} ms (err~{last_err}, hr={last_hr}"
            f"{', no-contact' if last_contact is False else ''})"
        )
        errs = [s[2] for s in data if len(s) >= 3]
        contacts = [s[4] for s in data if len(s) >= 5]
        if errs:
            state["ppi_err_est"] = int(sum(errs) / len(errs))
        if contacts:
            state["ppi_contact_pct"] = int(
                100.0 * sum(bool(c) for c in contacts) / len(contacts)
            )
    else:
        state["ppi_last_sample"] = f"PPI={last[1]} ms"

    _track_session(state, "ppi", len(data))
    ppi_ms = [float(s[1]) for s in data if len(s) > 1 and s[1] is not None and s[1] > 0]
    if ppi_ms:
        state["rr_intervals"] = ppi_ms
        state["rr_history"].extend(ppi_ms)


def make_callback(
    state: dict[str, Any],
    ts_deque: deque,
    kind: str,
) -> Callable[[Any], None]:
    """Create a unified callback closure to route sensor frames to state."""
    feeders: dict[str, Callable] = {
        "ecg": feed_ecg,
        "ppg": feed_ppg,
        "acc": feed_acc,
        "gyro": feed_gyro,
        "mag": feed_mag,
        "ppi": feed_ppi,
    }
    fn = feeders[kind]

    def cb(data: Any) -> None:
        fn(data, state, ts_deque)

    return cb


def unwrap_vector(
    state: dict[str, Any], raw_key: str, count_key: str
) -> tuple[Any, Any, Any]:
    """Unpack a 3-axis tuple (x, y, z) if samples are present, otherwise return (None, None, None)."""
    val = state.get(raw_key) if state.get(count_key, 0) > 0 else None
    if isinstance(val, tuple | list) and len(val) >= 3:
        return val[0], val[1], val[2]
    return None, None, None
