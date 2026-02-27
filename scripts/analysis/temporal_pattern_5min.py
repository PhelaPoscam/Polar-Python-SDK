#!/usr/bin/env python3
"""
Detailed temporal visualization of 5-minute capture
Look for patterns that explain the stress variability
"""
import pandas as pd
import numpy as np
import struct
from pathlib import Path

# Find the latest log file
log_dir = Path("data/nuanic_logs")
csv_files = sorted(log_dir.glob("nuanic_highfreq_*.csv"))
csv_file = str(csv_files[-1])

df = pd.read_csv(csv_file)

# Extract all data
d306_df = df[df['characteristic'].str.contains('d306262b')].copy().reset_index(drop=True)
stress_df = df[df['characteristic'].str.contains('468f2717')].copy().reset_index(drop=True)

# Parse stress and EDA
stress_packets = []
stress_times = []
for idx, row in stress_df.iterrows():
    pkt = bytes.fromhex(row['data_hex'])
    stress_packets.append(pkt)
    # Approximate time based on packet position
    stress_times.append(idx * (1.0 / 1.12))  # ~1.12 Hz

stress_vals = [pkt[14] for pkt in stress_packets]
eda_vals = [np.mean(list(pkt[15:92])) for pkt in stress_packets]

print("=" * 80)
print("⏱️  TEMPORAL STRESS & EDA PATTERNS")
print("=" * 80)
print()

print("TIME SERIES (every 30 seconds):")
print()
print("Time (s) | Stress (%) | EDA Mean | Movement?")
print("---------|-----------|----------|----------")

# Sample every N packets
sample_rate = 30  # Every 30 seconds

for i in range(0, len(stress_vals), max(1, int(len(stress_vals) / 10))):
    time_s = stress_times[i]
    stress_pct = stress_vals[i] * 100 / 255
    eda_mean = eda_vals[i]
    
    # Check if there's movement around this time
    # Movement = acceleration magnitude > mean + 1std
    d306_idx_start = int(time_s * 15.87)
    d306_idx_end = min(d306_idx_start + int(15.87*5), len(d306_df))
    
    movement_count = 0
    for d_idx in range(d306_idx_start, d306_idx_end):
        if d_idx < len(d306_df):
            pkt = bytes.fromhex(d306_df.iloc[d_idx]['data_hex'])
            acc_x = struct.unpack('<h', pkt[8:10])[0]
            acc_y = struct.unpack('<h', pkt[10:12])[0]
            mag = np.sqrt(acc_x**2 + acc_y**2)
            if mag > 20000:  # Threshold from earlier analysis
                movement_count += 1
    
    move_pct = movement_count / max(1, d306_idx_end - d306_idx_start) * 100
    
    print(f"{time_s:7.0f}  | {stress_pct:9.1f} | {eda_mean:8.1f} | {move_pct:6.1f}%")

print()

# Find stress peaks
print("=" * 80)
print("📈 STRESS PEAKS (top 5)")
print("=" * 80)
print()

peaks = sorted(enumerate(stress_vals), key=lambda x: x[1], reverse=True)[:5]
for rank, (idx, stress) in enumerate(peaks, 1):
    time_s = stress_times[idx]
    stress_pct = stress * 100 / 255
    eda_mean = eda_vals[idx]
    print(f"{rank}. Time {time_s:.0f}s: Stress {stress_pct:5.1f}% | EDA {eda_mean:6.1f}")

print()

# Check if stress spikes correlate with movement
print("=" * 80)
print("🔍 MOVEMENT vs STRESS ANALYSIS")
print("=" * 80)
print()

# Calculate rolling statistics
window = 5  # packets
rolling_stress = []
rolling_movement = []
rolling_times = []

for i in range(len(stress_vals) - window):
    # Stress for this window
    window_stress = np.mean(stress_vals[i:i+window])
    rolling_stress.append(window_stress)
    
    # Movement for this window
    time_s = stress_times[i]
    d306_idx_start = int(time_s * 15.87)
    d306_idx_end = min(d306_idx_start + int(15.87 * 5), len(d306_df))
    
    movement_count = 0
    for d_idx in range(d306_idx_start, d306_idx_end):
        if d_idx < len(d306_df):
            pkt = bytes.fromhex(d306_df.iloc[d_idx]['data_hex'])
            acc_x = struct.unpack('<h', pkt[8:10])[0]
            acc_y = struct.unpack('<h', pkt[10:12])[0]
            mag = np.sqrt(acc_x**2 + acc_y**2)
            if mag > 20000:
                movement_count += 1
    
    move_pct = movement_count / max(1, d306_idx_end - d306_idx_start)
    rolling_movement.append(move_pct)
    rolling_times.append(time_s)

print("High stress periods:")
high_stress_idx = [i for i, s in enumerate(rolling_stress) if s > 180]
print(f"  Found {len(high_stress_idx)} high-stress windows (>70%)")

if high_stress_idx:
    print()
    for idx in high_stress_idx[:5]:
        time_s = rolling_times[idx]
        stress = rolling_stress[idx]
        move = rolling_movement[idx]
        stress_pct = stress * 100 / 255
        print(f"  Time {time_s:.0f}s: Stress {stress_pct:5.1f}% | Movement {move*100:5.1f}%")

print()

# Final assessment
print("=" * 80)
print("🎯 INTERPRETATION")
print("=" * 80)
print()

avg_stress = np.mean(stress_vals)
std_stress = np.std(stress_vals)
avg_eda = np.mean(eda_vals)
std_eda = np.std(eda_vals)

print(f"Stress: Mean {avg_stress*100/255:.1f}% ± {std_stress*100/255:.1f}%")
print(f"EDA:    Mean {avg_eda:.1f} ± {std_eda:.1f}")
print()

if std_eda < 15:
    print("✅ EDA is STABLE → You were emotionally calm")
    print()
    if std_stress > 35:
        print("⚠️  But stress varied a LOT")
        print("   This suggests:")
        print("   • Stress metric picked up HRV artifacts")
        print("   • OR physical stress (muscle tension) unrelated to emotion")
        print("   • OR the baseline normalization shifted over time")
        print("   • OR ring sensor drift during long capture")
else:
    print("⚠️  EDA is VARIABLE → You had emotional changes")

print()
