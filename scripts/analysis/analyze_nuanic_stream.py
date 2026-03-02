"""Analyze Nuanic ring data stream characteristics"""

import pandas as pd
from datetime import datetime
import numpy as np

# Load the data
csv_path = r"data\nuanic_logs\nuanic_2026-03-02_13-55-37.csv"
df = pd.read_csv(csv_path)

# Parse timestamps
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Calculate time differences between readings
df['time_diff'] = df['timestamp'].diff().dt.total_seconds()

# Basic statistics
print("=" * 60)
print("NUANIC RING DATA STREAM ANALYSIS")
print("=" * 60)
print()

print(f"📊 BASIC STATISTICS")
print(f"   Total readings: {len(df)}")
print(f"   Start time: {df['timestamp'].iloc[0]}")
print(f"   End time: {df['timestamp'].iloc[-1]}")
print(f"   Total duration: {(df['timestamp'].iloc[-1] - df['timestamp'].iloc[0]).total_seconds():.2f} seconds")
print()

print(f"⏱️  TIMING ANALYSIS")
print(f"   Mean sampling interval: {df['time_diff'].mean():.3f} seconds")
print(f"   Median sampling interval: {df['time_diff'].median():.3f} seconds")
print(f"   Min sampling interval: {df['time_diff'].min():.3f} seconds")
print(f"   Max sampling interval: {df['time_diff'].max():.3f} seconds")
print(f"   Estimated sampling rate: {1 / df['time_diff'].mean():.2f} Hz")
print()

print(f"📈 STRESS DATA ANALYSIS")
print(f"   Raw stress range: {df['stress_raw'].min()} - {df['stress_raw'].max()} (0-255 scale)")
print(f"   Stress % range: {df['stress_percent'].min():.1f}% - {df['stress_percent'].max():.1f}%")
print(f"   Mean stress: {df['stress_percent'].mean():.1f}%")
print(f"   Median stress: {df['stress_percent'].median():.1f}%")
print(f"   Std dev: {df['stress_percent'].std():.1f}%")
print()

print(f"🎯 STRESS DISTRIBUTION")
stress_bins = [0, 25, 50, 75, 100]
stress_labels = ['Low (0-25%)', 'Medium (25-50%)', 'High (50-75%)', 'Very High (75-100%)']
df['stress_category'] = pd.cut(df['stress_percent'], bins=stress_bins, labels=stress_labels, include_lowest=True)
print(df['stress_category'].value_counts().sort_index())
print()

print(f"📦 DATA STRUCTURE")
print(f"   EDA hex data length: {df['eda_hex'].str.len().mean():.0f} chars (avg)")
print(f"   Full packet hex length: {df['full_packet_hex'].str.len().mean():.0f} chars (avg)")
print(f"   EDA data bytes: ~{df['eda_hex'].str.len().mean() / 2:.0f} bytes")
print()

print(f"🔍 SAMPLE READINGS")
print(df[['timestamp', 'stress_raw', 'stress_percent']].head(10).to_string(index=False))
print()

print(f"🌊 STRESS VARIABILITY (consecutive differences)")
df['stress_change'] = df['stress_percent'].diff().abs()
print(f"   Mean absolute change: {df['stress_change'].mean():.1f}%")
print(f"   Max jump: {df['stress_change'].max():.1f}%")
print(f"   Changes > 50%: {(df['stress_change'] > 50).sum()} occurrences")
print()

# Time gaps analysis
print(f"⏸️  GAP ANALYSIS (>2 seconds)")
gaps = df[df['time_diff'] > 2.0]
if len(gaps) > 0:
    for idx in gaps.index:
        gap_time = df.loc[idx, 'time_diff']
        gap_ts = df.loc[idx, 'timestamp']
        print(f"   Gap of {gap_time:.2f}s at {gap_ts}")
else:
    print(f"   No significant gaps detected!")
print()

print("=" * 60)
