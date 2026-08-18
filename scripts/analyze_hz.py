"""Post-session Hz and signal integrity analysis: reads full-res CSV files and reports metrics.

Usage:
    python scripts/analyze_hz.py <session_dir>
    python scripts/analyze_hz.py data/dual/20260806_120000
    python scripts/analyze_hz.py data/h10/20260818_120000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from polar_ble_sdk.research.audit import audit_csv_stream  # noqa: E402


def analyze_directory(raw_dir: Path, label: str) -> None:
    """Analyze all stream CSVs in a raw/ directory."""
    csv_files = sorted(raw_dir.glob("*.csv"))
    if not csv_files:
        print(f"  {label}: no CSV files found in {raw_dir}")
        return

    print(f"\n  {label}")
    print(
        f"  {'Stream':<8} {'Samples':>10} {'Avg Hz':>10} {'Std Dev':>10} {'Duration':>10} {'Gaps (>2x)':>11}"
    )
    print("  " + "-" * 65)

    for csv_path in csv_files:
        audit = audit_csv_stream(csv_path)
        print(
            f"  {audit.stream:<8} {audit.sample_count:>10d} {audit.average_hz:>10.2f} Hz "
            f"{audit.std_dev_hz:>10.2f} Hz {audit.duration_s:>9.1f} s {audit.gap_count:>11d}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post-session Hz and signal integrity analysis"
    )
    parser.add_argument("session_dir", type=str, help="Path to session directory")
    args = parser.parse_args()

    session_dir = Path(args.session_dir)
    if not session_dir.exists():
        print(f"Error: {session_dir} does not exist")
        sys.exit(1)

    print(f"Analyzing session: {session_dir}")
    print("=" * 68)

    # Check for dual-device layout
    h10_raw = session_dir / "h10" / "raw"
    sense_raw = session_dir / "sense" / "raw"
    raw_dir = session_dir / "raw"

    if h10_raw.exists():
        analyze_directory(h10_raw, "H10 (Raw)")
    if sense_raw.exists():
        analyze_directory(sense_raw, "Verity Sense (Raw)")
    if raw_dir.exists() and not h10_raw.exists():
        analyze_directory(raw_dir, "Raw Streams")

    print()


if __name__ == "__main__":
    main()
