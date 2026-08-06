"""Post-session Hz analysis: reads full-res CSV files and reports actual Hz per stream.

Usage:
    python scripts/analyze_hz.py <session_dir>
    python scripts/analyze_hz.py data/dual/20260806_120000

For H10 sessions, pass the session dir containing raw/h10/.
For dual sessions, pass the session dir containing raw/h10/ and raw/sense/.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def compute_hz_from_csv(csv_path: Path) -> tuple[float, int, float]:
    """Read timestamps from a full-res CSV and compute Hz.

    Returns (avg_hz, sample_count, std_dev_hz).
    """
    timestamps: list[float] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return 0.0, 0, 0.0

        for row in reader:
            if not row:
                continue
            try:
                ts = float(row[0])
                timestamps.append(ts)
            except (ValueError, IndexError):
                continue

    if len(timestamps) < 2:
        return 0.0, len(timestamps), 0.0

    time_span = timestamps[-1] - timestamps[0]
    if time_span <= 0:
        return 0.0, len(timestamps), 0.0

    avg_hz = len(timestamps) / time_span

    # Compute inter-sample Hz for standard deviation
    if len(timestamps) > 2:
        diffs = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
        hz_values = [1.0 / d for d in diffs if d > 0]
        if hz_values:
            mean_hz = sum(hz_values) / len(hz_values)
            variance = sum((h - mean_hz) ** 2 for h in hz_values) / len(hz_values)
            std_dev = variance**0.5
        else:
            std_dev = 0.0
    else:
        std_dev = 0.0

    return avg_hz, len(timestamps), std_dev


def analyze_directory(raw_dir: Path, label: str) -> None:
    """Analyze all stream CSVs in a raw/ directory."""
    csv_files = sorted(raw_dir.glob("*.csv"))
    if not csv_files:
        print(f"  {label}: no CSV files found in {raw_dir}")
        return

    print(f"\n  {label}")
    print(
        f"  {'Stream':<8} {'Samples':>10} {'Avg Hz':>10} {'Std Dev':>10} {'Duration':>10}"
    )
    print("  " + "-" * 52)

    for csv_path in csv_files:
        stream_name = csv_path.stem
        avg_hz, count, std_dev = compute_hz_from_csv(csv_path)
        duration = count / avg_hz if avg_hz > 0 else 0.0
        print(
            f"  {stream_name:<8} {count:>10d} {avg_hz:>10.2f} Hz "
            f"{std_dev:>10.2f} Hz {duration:>9.1f} s"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-session Hz analysis")
    parser.add_argument("session_dir", type=str, help="Path to session directory")
    args = parser.parse_args()

    session_dir = Path(args.session_dir)
    if not session_dir.exists():
        print(f"Error: {session_dir} does not exist")
        sys.exit(1)

    print(f"Analyzing session: {session_dir}")
    print("=" * 56)

    # Check for dual-device layout
    h10_raw = session_dir / "h10" / "raw"
    sense_raw = session_dir / "sense" / "raw"

    # Check for single-device layout
    raw_dir = session_dir / "raw"

    if h10_raw.exists():
        analyze_directory(h10_raw, "H10 (Raw)")
    if sense_raw.exists():
        analyze_directory(sense_raw, "Verity Sense (Raw)")
    if raw_dir.exists() and not h10_raw.exists():
        analyze_directory(raw_dir, "Raw")

    print()


if __name__ == "__main__":
    main()
