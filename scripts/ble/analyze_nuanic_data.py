#!/usr/bin/env python3
"""
Analyze and visualize Nuanic ring logged data

Usage:
    python analyze_nuanic_data.py <csv_file>

Example:
    python analyze_nuanic_data.py data/nuanic_logs/nuanic_2024-01-15_14-23-45.csv
"""
import sys
import csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict


def load_nuanic_csv(filepath):
    """Load CSV file with Nuanic data"""
    data = {
        'timestamps': [],
        'stress_raw': [],
        'stress_percent': [],
        'eda_hex': [],
        'packets': []
    }
    
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data['timestamps'].append(row['timestamp'])
            data['stress_raw'].append(int(row['stress_raw']))
            data['stress_percent'].append(float(row['stress_percent']))
            data['eda_hex'].append(row['eda_hex'])
            data['packets'].append(row['full_packet_hex'])
    
    return data


def analyze_stress(data):
    """Analyze stress metrics"""
    stress = data['stress_percent']
    
    if not stress:
        return None
    
    return {
        'min': min(stress),
        'max': max(stress),
        'mean': sum(stress) / len(stress),
        'range': max(stress) - min(stress),
        'count': len(stress),
    }


def analyze_eda_hex(eda_hex_list):
    """Analyze EDA hex data - identify likely channels"""
    
    if not eda_hex_list:
        return None
    
    # Parse first 16 bytes (8 hex pairs) as potential channels
    channels = [[] for _ in range(4)]
    
    for eda_hex in eda_hex_list:
        try:
            # Parse as 4 x 16-bit values
            for i in range(4):
                offset = i * 4  # 4 hex chars = 2 bytes
                if offset + 4 <= len(eda_hex):
                    hex_val = eda_hex[offset:offset+4]
                    # Try little-endian
                    int_val = int(hex_val[2:4] + hex_val[0:2], 16)
                    channels[i].append(int_val)
        except:
            pass
    
    # Filter channels with actual data
    active_channels = []
    for i, channel in enumerate(channels):
        if channel and any(v != 0 for v in channel):
            active_channels.append({
                'index': i,
                'values': channel,
                'min': min(channel),
                'max': max(channel),
                'mean': sum(channel) / len(channel),
                'range': max(channel) - min(channel),
            })
    
    return active_channels


def detect_peaks(values, threshold_std=1.5):
    """Detect peaks in stress/EDA data"""
    if len(values) < 3:
        return []
    
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std_dev = variance ** 0.5
    
    threshold = mean + (threshold_std * std_dev)
    
    peaks = []
    for i, v in enumerate(values):
        if v > threshold:
            peaks.append({
                'index': i,
                'value': v,
                'deviation': v - mean,
                'std_count': (v - mean) / std_dev if std_dev > 0 else 0
            })
    
    return peaks


def print_report(filepath):
    """Generate analysis report"""
    print("\n" + "=" * 80)
    print("NUANIC RING DATA ANALYSIS REPORT")
    print("=" * 80)
    print(f"File: {filepath}")
    print("=" * 80 + "\n")
    
    # Load data
    try:
        data = load_nuanic_csv(filepath)
    except Exception as e:
        print(f"[ERROR] Failed to load file: {e}")
        return
    
    if not data['timestamps']:
        print("[ERROR] No data found in file")
        return
    
    # Basic statistics
    print("SESSION INFORMATION")
    print("-" * 80)
    print(f"Total readings: {len(data['timestamps'])}")
    print(f"Start: {data['timestamps'][0]}")
    print(f"End: {data['timestamps'][-1]}")
    
    # Calculate duration
    try:
        start = datetime.fromisoformat(data['timestamps'][0])
        end = datetime.fromisoformat(data['timestamps'][-1])
        duration = (end - start).total_seconds()
        print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
    except:
        pass
    
    print()
    
    # Stress analysis
    print("STRESS ANALYSIS")
    print("-" * 80)
    stress_stats = analyze_stress(data)
    if stress_stats:
        print(f"Minimum: {stress_stats['min']:.1f}%")
        print(f"Maximum: {stress_stats['max']:.1f}%")
        print(f"Mean: {stress_stats['mean']:.1f}%")
        print(f"Range: {stress_stats['range']:.1f}%")
        
        # Identify stress peaks
        peaks = detect_peaks(data['stress_percent'], threshold_std=1.5)
        print(f"Peak count (> 1.5σ): {len(peaks)}")
        if peaks:
            avg_peak = sum(p['value'] for p in peaks) / len(peaks)
            print(f"Average peak value: {avg_peak:.1f}%")
            print(f"Peaks per minute: {(len(peaks) / (stress_stats['count'] / 60)):.1f}")
    
    print()
    
    # EDA analysis
    print("EDA DATA ANALYSIS")
    print("-" * 80)
    eda_channels = analyze_eda_hex(data['eda_hex'])
    
    if eda_channels:
        print(f"Active channels detected: {len(eda_channels)}\n")
        for ch in eda_channels:
            print(f"Channel {ch['index']}:")
            print(f"  Range: {ch['min']} - {ch['max']}")
            print(f"  Mean: {ch['mean']:.1f}")
            print(f"  Variation: {ch['range']}")
            
            # Peak detection
            ch_peaks = detect_peaks(ch['values'], threshold_std=1.5)
            print(f"  Peaks: {len(ch_peaks)}")
            
            # Correlation with stress
            if len(ch['values']) == len(data['stress_percent']):
                correlation = calculate_correlation(ch['values'], data['stress_percent'])
                print(f"  Correlation with stress: {correlation:.3f}")
            print()
    else:
        print("Could not parse EDA channels from hex data")
        print("First few EDA hex values:")
        for i, eda in enumerate(data['eda_hex'][:3]):
            print(f"  Reading {i}: {eda[:32]}...")
    
    print()
    
    # Recommendations
    print("RECOMMENDATIONS")
    print("-" * 80)
    if stress_stats and stress_stats['range'] < 20:
        print("• Low stress variation - session was stable")
    elif stress_stats and stress_stats['range'] > 50:
        print("• High stress variation - detected multiple stressors")
    
    if eda_channels and len(eda_channels) > 0:
        print(f"• Found {len(eda_channels)} EDA channels - further analysis needed")
        print("• Study correlations between channels")
        print("• Compare EDA peaks with stress transitions")
    
    print("\nNext steps:")
    print("1. Plot stress over time to visualize changes")
    print("2. Analyze EDA channels to understand sensor data")
    print("3. Cross-correlate stress with EDA for validation")
    print("4. Compare with simultaneous HR data if available")


def calculate_correlation(x, y):
    """Calculate Pearson correlation coefficient"""
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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_nuanic_data.py <csv_file>")
        print()
        print("Examples:")
        print("  python analyze_nuanic_data.py data/nuanic_logs/nuanic_2024-01-15.csv")
        print("  python analyze_nuanic_data.py data/nuanic_logs/nuanic_*")
        sys.exit(1)
    
    filepath = sys.argv[1]
    
    if not Path(filepath).exists():
        print(f"[ERROR] File not found: {filepath}")
        sys.exit(1)
    
    print_report(filepath)
