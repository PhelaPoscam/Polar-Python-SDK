"""Research-grade data loaders for Polar recording sessions.

Loads multi-stream session recordings (raw CSVs, 1 Hz summary, event markers,
and audit manifests) into clean, analyzed pandas DataFrames.
"""

from __future__ import annotations

import ast
import csv
import json
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PolarSessionData:
    """Encapsulates all data streams, summary logs, and metadata for a recorded session."""

    session_id: str
    session_dir: Path
    metadata: dict[str, Any] = field(default_factory=dict)
    summary: pd.DataFrame = field(default_factory=pd.DataFrame)
    streams: dict[str, pd.DataFrame] = field(default_factory=dict)
    markers: list[dict[str, Any]] = field(default_factory=list)
    dual_sessions: dict[str, PolarSessionData] = field(default_factory=dict)

    @property
    def is_dual(self) -> bool:
        return bool(self.dual_sessions)

    def get_stream(
        self, stream_name: str, device: str | None = None
    ) -> pd.DataFrame | None:
        """Retrieve a specific sensor stream DataFrame (e.g. 'ecg', 'ppg', 'acc')."""
        if device and device in self.dual_sessions:
            return self.dual_sessions[device].streams.get(stream_name.lower())
        return self.streams.get(stream_name.lower())


def host_zero(meta: dict[str, Any], key: str) -> pd.Timestamp | None:
    """Host local time of a stream's first frame, e.g. ``key="sense_ppg"``.

    Host local time is the clock of the summary CSVs; markers convert to it
    with ``datetime.fromtimestamp(marker["timestamp_epoch_s"])``.
    """
    ns = meta.get("clock_zero_points", {}).get(f"{key}_host_epoch_ns")
    return pd.Timestamp(datetime.fromtimestamp(ns / 1e9)) if ns else None


def _add_host_time(
    streams: dict[str, pd.DataFrame], meta: dict[str, Any], prefix: str = ""
) -> None:
    """Add a ``Host_Time`` column mapping device-relative time onto host time.

    Accuracy is limited by BLE latency (tens of ms, occasionally more): fine
    for windowed analyses, not for event-locked cardiac timing (use LSL or a
    hardware sync for that). Sessions recorded before v1.1 have no zero point.
    """
    for name, df in streams.items():
        anchor = host_zero(meta, f"{prefix}{name}")
        if anchor is not None and "Timestamp_s" in df.columns:
            df["Host_Time"] = anchor + pd.to_timedelta(
                pd.to_numeric(df["Timestamp_s"], errors="coerce"), unit="s"
            )


def _sample_times(
    rows_ts: list[float], rows_samples: list[list[Any]], nominal_hz: float
) -> list[float]:
    """Per-sample times for wide frames whose timestamp marks their *last* sample.

    Frames vary in size (PPG delta compression gives 31-52 samples), so each
    frame's samples are spaced by that frame's own ``dt = Δts / n``, which
    follows the device clock exactly. The first frame, and any frame after a
    gap (lost packets make ``Δts / n`` implausible), use the median ``dt``.
    """
    per_frame = [
        (rows_ts[k] - rows_ts[k - 1]) / len(rows_samples[k])
        for k in range(1, len(rows_ts))
        if rows_samples[k] and rows_ts[k] > rows_ts[k - 1]
    ]
    typical = statistics.median(per_frame) if per_frame else 1.0 / nominal_hz
    times: list[float] = []
    for k, (ts, samples) in enumerate(zip(rows_ts, rows_samples, strict=True)):
        dt = typical
        if k > 0 and samples:
            frame_dt = (ts - rows_ts[k - 1]) / len(samples)
            if abs(frame_dt - typical) <= 0.2 * typical:
                dt = frame_dt
        last = len(samples) - 1
        times.extend(ts - (last - i) * dt for i in range(len(samples)))
    return times


def _read_wide_rows(path: Path, parse: Any) -> tuple[list[float], list[list[Any]]]:
    rows_ts: list[float] = []
    rows_samples: list[list[Any]] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        _header = next(reader, None)
        for line in reader:
            if not line:
                continue
            try:
                ts = float(line[0])
                samples = [parse(c) for c in line[1:] if c.strip() != ""]
            except (ValueError, SyntaxError):
                continue
            rows_ts.append(ts)
            rows_samples.append(samples)
    return rows_ts, rows_samples


def _parse_wide_ppg_csv(path: Path) -> pd.DataFrame:
    """Parse variable-width PPG frames into sample-level DataFrame."""
    rows_ts, rows_samples = _read_wide_rows(Path(path), ast.literal_eval)
    if not rows_samples:
        return pd.DataFrame(columns=["Timestamp_s", "ch1", "ch2", "ch3", "ch4"])
    times = _sample_times(rows_ts, rows_samples, 135.0)
    recs = [
        [t, *s[:4]]
        for t, s in zip(times, (s for row in rows_samples for s in row), strict=True)
        if isinstance(s, list | tuple)
    ]
    return (
        pd.DataFrame(recs, columns=["Timestamp_s", "ch1", "ch2", "ch3", "ch4"])
        .dropna()
        .reset_index(drop=True)
    )


def _parse_wide_ecg_csv(path: Path) -> pd.DataFrame:
    """Parse variable-width or wide ECG frames into a sample-level DataFrame."""
    rows_ts, rows_samples = _read_wide_rows(Path(path), lambda c: int(float(c)))
    if not rows_samples:
        return pd.DataFrame(columns=["Timestamp_s", "uV", "ECG_uV"])
    times = _sample_times(rows_ts, rows_samples, 130.0)
    flat = [s for row in rows_samples for s in row]
    return pd.DataFrame({"Timestamp_s": times, "uV": flat, "ECG_uV": flat}).reset_index(
        drop=True
    )


def _read_stream_csv(csv_path: Path, stream: str | None = None) -> pd.DataFrame:
    """Parse one raw stream CSV, routing wide PPG/ECG frames to their unrollers.

    ``stream`` overrides the name taken from the filename, for callers that know
    the stream but read it from an arbitrarily named file.
    """
    stream_name = (stream or csv_path.stem).lower()
    if stream_name == "ppg":
        return _parse_wide_ppg_csv(csv_path)
    if stream_name == "ecg":
        return _parse_wide_ecg_csv(csv_path)

    df = pd.read_csv(csv_path)
    if "Timestamp_s" in df.columns:
        df["Timestamp_s"] = pd.to_numeric(df["Timestamp_s"], errors="coerce")
    # Vector magnitude for 3-axis streams
    if {"X_mG", "Y_mG", "Z_mG"}.issubset(df.columns):
        df["ACC_Mag_mG"] = (df["X_mG"] ** 2 + df["Y_mG"] ** 2 + df["Z_mG"] ** 2) ** 0.5
    if {"X_dps", "Y_dps", "Z_dps"}.issubset(df.columns):
        df["GYRO_Mag_dps"] = (
            df["X_dps"] ** 2 + df["Y_dps"] ** 2 + df["Z_dps"] ** 2
        ) ** 0.5
    return df


def _load_single_device_dir(device_dir: Path) -> PolarSessionData:
    """Load summary and raw streams from a single device folder."""
    session_id = device_dir.name
    meta: dict[str, Any] = {}
    meta_path = device_dir / "session_meta.json"
    if meta_path.exists():
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:
            logger.warning("Could not read %s: %s", meta_path, e)

    # Load 1 Hz summary
    summary_df = pd.DataFrame()
    summary_path = device_dir / "post-processed" / "summary.csv"
    if summary_path.exists():
        try:
            summary_df = pd.read_csv(summary_path)
            if "Timestamp" in summary_df.columns:
                summary_df["Timestamp"] = pd.to_datetime(
                    summary_df["Timestamp"], errors="coerce"
                )
        except Exception as e:
            logger.warning("Could not load summary CSV %s: %s", summary_path, e)

    # Load raw stream CSVs
    raw_dir = device_dir / "raw"
    streams: dict[str, pd.DataFrame] = {}
    if raw_dir.exists():
        for csv_path in raw_dir.glob("*.csv"):
            try:
                streams[csv_path.stem.lower()] = _read_stream_csv(csv_path)
            except Exception as e:
                logger.warning("Failed to load stream CSV %s: %s", csv_path, e)

    markers = meta.get("markers", [])
    return PolarSessionData(
        session_id=session_id,
        session_dir=device_dir,
        metadata=meta,
        summary=summary_df,
        streams=streams,
        markers=markers,
    )


def load_session(session_path: Path | str) -> PolarSessionData:
    """Load a complete Polar recording session into a structured PolarSessionData container.

    Supports both single-device (`data/{device_type}/{session_ts}/`) and
    dual-device (`data/dual/{session_ts}/`) recording layouts.

    Args:
        session_path: Path to the recording session directory.

    Returns:
        PolarSessionData: Loaded session containing metadata, summary, and raw stream DataFrames.
    """
    path = Path(session_path)
    if not path.exists():
        raise FileNotFoundError(f"Session directory does not exist: {path}")

    h10_dir = path / "h10"
    sense_dir = path / "sense"

    # Check for dual-device session
    if h10_dir.exists() and sense_dir.exists():
        meta: dict[str, Any] = {}
        meta_path = path / "session_meta.json"
        if meta_path.exists():
            try:
                with meta_path.open("r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                pass

        h10_data = _load_single_device_dir(h10_dir)
        sense_data = _load_single_device_dir(sense_dir)
        _add_host_time(h10_data.streams, meta, "h10_")
        _add_host_time(sense_data.streams, meta, "sense_")

        return PolarSessionData(
            session_id=path.name,
            session_dir=path,
            metadata=meta,
            dual_sessions={"h10": h10_data, "sense": sense_data},
            markers=meta.get("markers", []),
        )

    single = _load_single_device_dir(path)
    _add_host_time(single.streams, single.metadata)
    return single


def load_raw_stream(raw_path_or_dir: Path | str, stream_name: str) -> pd.DataFrame:
    """Load and parse an individual raw sensor stream CSV.

    Args:
        raw_path_or_dir: Directory containing stream CSVs or direct path to a CSV file.
        stream_name: Stream name (e.g. 'ecg', 'ppg', 'acc', 'gyro', 'mag').

    Returns:
        pd.DataFrame: Parsed and unrolled stream data.
    """
    raw_path = Path(raw_path_or_dir)
    csv_path = (
        raw_path if raw_path.is_file() else raw_path / f"{stream_name.lower()}.csv"
    )
    if not csv_path.exists():
        raise FileNotFoundError(f"Raw stream file not found: {csv_path}")
    return _read_stream_csv(csv_path, stream_name)
