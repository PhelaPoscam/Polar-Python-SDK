"""Research-grade data loaders for Polar recording sessions.

Loads multi-stream session recordings (raw CSVs, 1 Hz summary, event markers,
and audit manifests) into clean, analyzed pandas DataFrames.
"""

from __future__ import annotations

import ast
import csv
import json
import logging
from dataclasses import dataclass, field
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


def _parse_wide_ppg_csv(path: Path) -> pd.DataFrame:
    """Parse variable-width PPG frames into sample-level DataFrame."""
    rows_ts: list[float] = []
    rows_samples: list[list[int]] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        _header = next(reader, None)
        for line in reader:
            if not line:
                continue
            try:
                ts = float(line[0])
                samples = [ast.literal_eval(c) for c in line[1:]]
                rows_ts.append(ts)
                rows_samples.append(samples)
            except (ValueError, SyntaxError):
                continue

    if not rows_samples:
        return pd.DataFrame(columns=["Timestamp_s", "ch1", "ch2", "ch3", "ch4"])

    n0 = len(rows_samples[0])
    sample_dt = (
        1.0 / (n0 / (rows_ts[1] - rows_ts[0]))
        if len(rows_ts) > 1 and (rows_ts[1] - rows_ts[0]) > 0
        else 1.0 / 135.0
    )

    recs: list[list[Any]] = []
    for ts, samples in zip(rows_ts, rows_samples, strict=False):
        for i, s in enumerate(samples):
            if isinstance(s, list | tuple) and len(s) >= 4:
                recs.append([ts + i * sample_dt, s[0], s[1], s[2], s[3]])
            elif isinstance(s, list | tuple):
                recs.append([ts + i * sample_dt, *s])
    return (
        pd.DataFrame(recs, columns=["Timestamp_s", "ch1", "ch2", "ch3", "ch4"])
        .dropna()
        .reset_index(drop=True)
    )


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
            stream_name = csv_path.stem.lower()
            try:
                if stream_name == "ppg":
                    streams[stream_name] = _parse_wide_ppg_csv(csv_path)
                else:
                    df = pd.read_csv(csv_path)
                    if "Timestamp_s" in df.columns:
                        df["Timestamp_s"] = pd.to_numeric(
                            df["Timestamp_s"], errors="coerce"
                        )
                    # Calculate vector magnitude for 3-axis streams
                    if {"X_mG", "Y_mG", "Z_mG"}.issubset(df.columns):
                        df["ACC_Mag_mG"] = (
                            df["X_mG"] ** 2 + df["Y_mG"] ** 2 + df["Z_mG"] ** 2
                        ) ** 0.5
                    if {"X_dps", "Y_dps", "Z_dps"}.issubset(df.columns):
                        df["GYRO_Mag_dps"] = (
                            df["X_dps"] ** 2 + df["Y_dps"] ** 2 + df["Z_dps"] ** 2
                        ) ** 0.5
                    streams[stream_name] = df
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

        return PolarSessionData(
            session_id=path.name,
            session_dir=path,
            metadata=meta,
            dual_sessions={"h10": h10_data, "sense": sense_data},
            markers=meta.get("markers", []),
        )

    return _load_single_device_dir(path)
