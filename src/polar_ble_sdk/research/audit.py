"""Signal integrity verification, jitter analysis, and audit reporting for Polar sessions."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class StreamAudit:
    """Audit report for a single sensor data stream."""

    stream: str
    sample_count: int
    duration_s: float
    average_hz: float
    std_dev_hz: float
    max_gap_s: float
    gap_count: int


def audit_csv_stream(csv_path: Path) -> StreamAudit:
    """Analyze timestamps in a raw stream CSV to compute sampling frequency and gap metrics."""
    stream_name = csv_path.stem.lower()
    timestamps: list[float] = []
    total_samples = 0

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        _header = next(reader, None)
        for row in reader:
            if not row:
                continue
            try:
                timestamps.append(float(row[0]))
                if stream_name in {"ecg", "ppg"}:
                    total_samples += len(row) - 1
                else:
                    total_samples += 1
            except (ValueError, IndexError):
                continue

    if len(timestamps) < 2:
        return StreamAudit(
            stream=stream_name,
            sample_count=total_samples,
            duration_s=0.0,
            average_hz=0.0,
            std_dev_hz=0.0,
            max_gap_s=0.0,
            gap_count=0,
        )

    duration = timestamps[-1] - timestamps[0]
    avg_hz = total_samples / duration if duration > 0 else 0.0

    diffs = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
    # Frame packet interval
    packet_dt = duration / (len(timestamps) - 1) if len(timestamps) > 1 else 1.0

    # Gap threshold: inter-packet interval > 2x average packet dt
    gaps = [d for d in diffs if d > 2.0 * packet_dt]
    max_gap = max(diffs) if diffs else 0.0

    hz_values = [1.0 / d for d in diffs if d > 0]
    if len(hz_values) > 1:
        mean_hz = sum(hz_values) / len(hz_values)
        variance = sum((h - mean_hz) ** 2 for h in hz_values) / (len(hz_values) - 1)
        std_dev = variance**0.5
    else:
        std_dev = 0.0

    return StreamAudit(
        stream=stream_name,
        sample_count=len(timestamps),
        duration_s=duration,
        average_hz=avg_hz,
        std_dev_hz=std_dev,
        max_gap_s=max_gap,
        gap_count=len(gaps),
    )


def verify_session_integrity(session_dir: Path | str) -> dict[str, Any]:
    """Audit all recorded streams in a session directory."""
    path = Path(session_dir)
    if not path.exists():
        raise FileNotFoundError(f"Session directory not found: {path}")

    results: dict[str, Any] = {"session_id": path.name, "streams": {}}

    h10_raw = path / "h10" / "raw"
    sense_raw = path / "sense" / "raw"
    raw_dir = path / "raw"

    if h10_raw.exists():
        results["h10"] = {}
        for p in sorted(h10_raw.glob("*.csv")):
            audit = audit_csv_stream(p)
            results["h10"][audit.stream] = asdict(audit)

    if sense_raw.exists():
        results["sense"] = {}
        for p in sorted(sense_raw.glob("*.csv")):
            audit = audit_csv_stream(p)
            results["sense"][audit.stream] = asdict(audit)

    if raw_dir.exists() and not h10_raw.exists():
        for p in sorted(raw_dir.glob("*.csv")):
            audit = audit_csv_stream(p)
            results["streams"][audit.stream] = asdict(audit)

    return results
