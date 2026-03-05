#!/usr/bin/env python3
"""Nuanic Ring Data Analyzer CLI - Analyze logged CSV data."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from awe_polar.nuanic_ring.data_analysis import print_report


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Nuanic ring CSV log files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s data/nuanic_logs/nuanic_2026-03-05_15-45-19.csv
  %(prog)s data/nuanic_logs/nuanic_stress_2026-03-05_15-45-19.csv
  %(prog)s data/nuanic_logs/nuanic_*_stress_*.csv
        """
    )
    
    parser.add_argument(
        "filepath",
        help="Path to CSV log file to analyze",
    )
    
    args = parser.parse_args()
    
    filepath = Path(args.filepath)
    
    if not filepath.exists():
        print(f"[ERROR] File not found: {filepath}")
        return 1
    
    try:
        print_report(str(filepath))
        return 0
    except Exception as e:
        print(f"\n[ERROR] Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
