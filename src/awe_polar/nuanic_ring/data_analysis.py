"""Analysis helpers for Nuanic CSV logs."""

import csv
from datetime import datetime
from pathlib import Path
from typing import Any


def load_nuanic_csv(filepath: str) -> dict[str, list[Any]]:
    """Load CSV file with Nuanic data."""
    data = {
        "timestamps": [],
        "stress_raw": [],
        "stress_percent": [],
        "eda_hex": [],
        "packets": [],
    }

    with open(filepath, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            data["timestamps"].append(row["timestamp"])
            data["stress_raw"].append(int(row["stress_raw"]))
            data["stress_percent"].append(float(row["stress_percent"]))
            data["eda_hex"].append(row["eda_hex"])
            data["packets"].append(row["full_packet_hex"])

    return data


def analyze_stress(data: dict[str, list[Any]]) -> dict[str, float] | None:
    """Analyze stress metrics."""
    stress = data["stress_percent"]

    if not stress:
        return None

    return {
        "min": min(stress),
        "max": max(stress),
        "mean": sum(stress) / len(stress),
        "range": max(stress) - min(stress),
        "count": len(stress),
    }


def analyze_eda_hex(eda_hex_list: list[str]) -> list[dict[str, Any]] | None:
    """Analyze EDA hex data and identify likely channels."""
    if not eda_hex_list:
        return None

    channels = [[] for _ in range(4)]

    for eda_hex in eda_hex_list:
        try:
            for i in range(4):
                offset = i * 4
                if offset + 4 <= len(eda_hex):
                    hex_val = eda_hex[offset : offset + 4]
                    int_val = int(hex_val[2:4] + hex_val[0:2], 16)
                    channels[i].append(int_val)
        except Exception:
            pass

    active_channels = []
    for i, channel in enumerate(channels):
        if channel and any(v != 0 for v in channel):
            active_channels.append(
                {
                    "index": i,
                    "values": channel,
                    "min": min(channel),
                    "max": max(channel),
                    "mean": sum(channel) / len(channel),
                    "range": max(channel) - min(channel),
                }
            )

    return active_channels


def detect_peaks(
    values: list[float] | list[int], threshold_std: float = 1.5
) -> list[dict[str, float | int]]:
    """Detect peaks in stress/EDA data."""
    if len(values) < 3:
        return []

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std_dev = variance**0.5

    threshold = mean + (threshold_std * std_dev)

    peaks = []
    for i, value in enumerate(values):
        if value > threshold:
            peaks.append(
                {
                    "index": i,
                    "value": value,
                    "deviation": value - mean,
                    "std_count": ((value - mean) / std_dev if std_dev > 0 else 0),
                }
            )

    return peaks


def calculate_correlation(
    x: list[float] | list[int], y: list[float] | list[int]
) -> float:
    """Calculate Pearson correlation coefficient."""
    if len(x) != len(y) or len(x) < 2:
        return 0.0

    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)

    numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(len(x)))

    sum_sq_x = sum((xi - mean_x) ** 2 for xi in x)
    sum_sq_y = sum((yi - mean_y) ** 2 for yi in y)

    denominator = (sum_sq_x * sum_sq_y) ** 0.5

    if denominator == 0:
        return 0.0

    return numerator / denominator


def print_report(filepath: str) -> None:
    """Generate analysis report."""
    print("\n" + "=" * 80)
    print("NUANIC RING DATA ANALYSIS REPORT")
    print("=" * 80)
    print(f"File: {filepath}")
    print("=" * 80 + "\n")

    try:
        data = load_nuanic_csv(filepath)
    except Exception as exc:
        print(f"[ERROR] Failed to load file: {exc}")
        return

    if not data["timestamps"]:
        print("[ERROR] No data found in file")
        return

    print("SESSION INFORMATION")
    print("-" * 80)
    print(f"Total readings: {len(data['timestamps'])}")
    print(f"Start: {data['timestamps'][0]}")
    print(f"End: {data['timestamps'][-1]}")

    try:
        start = datetime.fromisoformat(data["timestamps"][0])
        end = datetime.fromisoformat(data["timestamps"][-1])
        duration = (end - start).total_seconds()
        print(f"Duration: {duration:.1f} seconds ({duration / 60:.1f} minutes)")
    except Exception:
        duration = None

    print()

    print("STRESS ANALYSIS")
    print("-" * 80)
    stress_stats = analyze_stress(data)
    if stress_stats:
        print(f"Minimum: {stress_stats['min']:.1f}%")
        print(f"Maximum: {stress_stats['max']:.1f}%")
        print(f"Mean: {stress_stats['mean']:.1f}%")
        print(f"Range: {stress_stats['range']:.1f}%")

        peaks = detect_peaks(data["stress_percent"], threshold_std=1.5)
        print(f"Peak count (> 1.5σ): {len(peaks)}")
        if peaks:
            avg_peak = sum(p["value"] for p in peaks) / len(peaks)
            print(f"Average peak value: {avg_peak:.1f}%")
            print(
                "Peaks per minute: "
                f"{(len(peaks) / (stress_stats['count'] / 60)):.1f}"
            )

    print()

    print("EDA DATA ANALYSIS")
    print("-" * 80)
    eda_channels = analyze_eda_hex(data["eda_hex"])

    if eda_channels:
        print(f"Active channels detected: {len(eda_channels)}\n")
        for channel in eda_channels:
            print(f"Channel {channel['index']}:")
            print(f"  Range: {channel['min']} - {channel['max']}")
            print(f"  Mean: {channel['mean']:.1f}")
            print(f"  Variation: {channel['range']}")

            channel_peaks = detect_peaks(channel["values"], threshold_std=1.5)
            print(f"  Peaks: {len(channel_peaks)}")

            if len(channel["values"]) == len(data["stress_percent"]):
                correlation = calculate_correlation(
                    channel["values"], data["stress_percent"]
                )
                print(f"  Correlation with stress: {correlation:.3f}")
            print()
    else:
        print("Could not parse EDA channels from hex data")
        print("First few EDA hex values:")
        for i, eda in enumerate(data["eda_hex"][:3]):
            print(f"  Reading {i}: {eda[:32]}...")

    print()

    print("RECOMMENDATIONS")
    print("-" * 80)
    if stress_stats and stress_stats["range"] < 20:
        print("• Low stress variation - session was stable")
    elif stress_stats and stress_stats["range"] > 50:
        print("• High stress variation - detected multiple stressors")

    if eda_channels and len(eda_channels) > 0:
        print(f"• Found {len(eda_channels)} EDA channels " "- further analysis needed")
        print("• Study correlations between channels")
        print("• Compare EDA peaks with stress transitions")

    print("\nNext steps:")
    print("1. Plot stress over time to visualize changes")
    print("2. Analyze EDA channels to understand sensor data")
    print("3. Cross-correlate stress with EDA for validation")
    print("4. Compare with simultaneous HR data if available")


def main(args: list[str] | None = None) -> int:
    """CLI entrypoint for analysis."""
    if args is None:
        import sys

        args = sys.argv[1:]

    if len(args) < 1:
        print("Usage: python analyze_nuanic_data.py <csv_file>")
        print()
        print("Examples:")
        print(
            "  python analyze_nuanic_data.py " "data/nuanic_logs/nuanic_2024-01-15.csv"
        )
        print("  python analyze_nuanic_data.py data/nuanic_logs/nuanic_*")
        return 1

    filepath = args[0]

    if not Path(filepath).exists():
        print(f"[ERROR] File not found: {filepath}")
        return 1

    print_report(filepath)
    return 0
