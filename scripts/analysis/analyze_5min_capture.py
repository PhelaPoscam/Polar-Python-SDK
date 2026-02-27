#!/usr/bin/env python3
"""
Analyze 5-minute measurement: calm but with hand movement
Compare stress, EDA, and acceleration patterns over time
"""
import pandas as pd
import numpy as np
import struct
from pathlib import Path

# Find the latest log file (5 minute capture)
log_dir = Path("data/nuanic_logs")
csv_files = sorted(log_dir.glob("nuanic_highfreq_*.csv"))
csv_file = str(csv_files[-1])  # Latest file

print("=" * 80)
print("📊 5-MINUTE CAPTURE ANALYSIS")
print("=" * 80)
print()
print(f"📁 Loading: {Path(csv_file).name}")
print()

df = pd.read_csv(csv_file)

print(f"Total packets: {len(df)}")
d306_count = len(df[df['characteristic'].str.contains('d306262b')])
stress_count = len(df[df['characteristic'].str.contains('468f2717')])

print(f"  d306262b (IMU): {d306_count} packets @ ~15.87 Hz = {d306_count/15.87:.1f}s")
print(f"  468f2717 (Physio): {stress_count} packets @ ~1.12 Hz = {stress_count/1.12:.1f}s")
print(f"  Total duration: ~{max(d306_count/15.87, stress_count/1.12):.1f} seconds")
print()

# Extract d306262b (IMU) data
d306_df = df[df['characteristic'].str.contains('d306262b')].copy()
d306_packets = []
for _, row in d306_df.iterrows():
    d306_packets.append(bytes.fromhex(row['data_hex']))

acc_x_vals = []
acc_y_vals = []
for pkt in d306_packets:
    acc_x = struct.unpack('<h', pkt[8:10])[0]
    acc_y = struct.unpack('<h', pkt[10:12])[0]
    acc_x_vals.append(acc_x)
    acc_y_vals.append(acc_y)

# Extract stress and EDA
stress_df = df[df['characteristic'].str.contains('468f2717')].copy()
stress_packets = []
for _, row in stress_df.iterrows():
    stress_packets.append(bytes.fromhex(row['data_hex']))

stress_vals = []
eda_means = []
for pkt in stress_packets:
    stress = pkt[14]
    eda_block = list(pkt[15:92])
    stress_vals.append(stress)
    eda_means.append(np.mean(eda_block))

print("=" * 80)
print("📈 TIME SERIES STATISTICS")
print("=" * 80)
print()

print("ACCELEROMETER (d306262b):")
print(f"  ACC_X Range: {min(acc_x_vals):+7d} to {max(acc_x_vals):+7d}")
print(f"  ACC_X Mean:  {np.mean(acc_x_vals):+10.1f}")
print(f"  ACC_X StdDev: {np.std(acc_x_vals):10.1f}")
print(f"  ACC_Y Range: {min(acc_y_vals):+7d} to {max(acc_y_vals):+7d}")
print(f"  ACC_Y Mean:  {np.mean(acc_y_vals):+10.1f}")
print(f"  ACC_Y StdDev: {np.std(acc_y_vals):10.1f}")
print()

# Calculate magnitude
acc_mag = np.sqrt(np.array(acc_x_vals)**2 + np.array(acc_y_vals)**2)
print(f"  Magnitude Range: {min(acc_mag):.0f} to {max(acc_mag):.0f}")
print(f"  Magnitude Mean:  {np.mean(acc_mag):.0f}")
print(f"  Magnitude StdDev: {np.std(acc_mag):.0f}")
print()

print("STRESS (468f2717 byte 14):")
print(f"  Range: {min(stress_vals)} - {max(stress_vals)} (0-255)")
print(f"  Mean:  {np.mean(stress_vals):.1f}")
print(f"  StdDev: {np.std(stress_vals):.1f}")
print(f"  Mean %: {np.mean(stress_vals) * 100 / 255:.1f}%")
print()

print("EDA MEAN (from 77 bytes per packet):")
print(f"  Range: {min(eda_means):.1f} - {max(eda_means):.1f}")
print(f"  Mean:  {np.mean(eda_means):.1f}")
print(f"  StdDev: {np.std(eda_means):.1f}")
print()

# Decompose acceleration movement into sections
print("=" * 80)
print("🎯 DETECT MOVEMENT PERIODS")
print("=" * 80)
print()

# Use acceleration magnitude to detect movement
threshold = np.mean(acc_mag) + np.std(acc_mag)
moving = acc_mag > threshold

print(f"Movement detection threshold: {threshold:.0f} units")
print(f"Movement periods detected: {int(np.sum(moving))} / {len(acc_x_vals)} packets")
print(f"Percentage moving: {np.sum(moving) / len(acc_x_vals) * 100:.1f}%")
print()

# Split into movement and stationary
mov_acc_x = [acc_x_vals[i] for i in range(len(acc_x_vals)) if moving[i]]
stat_acc_x = [acc_x_vals[i] for i in range(len(acc_x_vals)) if not moving[i]]

if mov_acc_x:
    print("DURING MOVEMENT:")
    print(f"  ACC_X StdDev: {np.std(mov_acc_x):.1f}")
    print(f"  Count: {len(mov_acc_x)} packets")
else:
    print("DURING MOVEMENT: No movement detected")

if stat_acc_x:
    print()
    print("DURING STATIONARY:")
    print(f"  ACC_X StdDev: {np.std(stat_acc_x):.1f}")
    print(f"  Count: {len(stat_acc_x)} packets")
print()

# Divide into time chunks
print("=" * 80)
print("⏱️  TEMPORAL BREAKDOWN (by minute)")
print("=" * 80)
print()

# Assuming ~15.87 Hz for d306262b
packets_per_minute = int(15.87 * 60)

for minute in range(0, int(len(acc_x_vals) / packets_per_minute) + 1):
    start_idx = minute * packets_per_minute
    end_idx = min((minute + 1) * packets_per_minute, len(acc_x_vals))
    
    if start_idx >= len(acc_x_vals):
        break
    
    chunk_acc_x = acc_x_vals[start_idx:end_idx]
    chunk_mag = acc_mag[start_idx:end_idx]
    
    # Find corresponding stress (at ~1.12 Hz, every ~14th IMU packet)
    stress_idx = int(minute * 1.12)
    if stress_idx < len(stress_vals):
        chunk_stress = stress_vals[stress_idx]
        chunk_eda = eda_means[stress_idx]
    else:
        chunk_stress = None
        chunk_eda = None
    
    print(f"Minute {minute} ({start_idx/15.87:.0f}s - {end_idx/15.87:.0f}s):")
    print(f"  ACC_X StdDev: {np.std(chunk_acc_x):10.1f}")
    print(f"  ACC Mag Avg:  {np.mean(chunk_mag):10.0f}")
    if chunk_stress is not None:
        print(f"  Stress:       {chunk_stress:3d} ({chunk_stress*100/255:5.1f}%)")
        print(f"  EDA Mean:     {chunk_eda:6.1f} (raw 0-255)")
    print()

# Correlation analysis over time
print("=" * 80)
print("📊 CORRELATION ANALYSIS")
print("=" * 80)
print()

# Resample stress/EDA to match IMU frequency
# Interpolate stress values to match d306262b packet rate
stress_interp = np.interp(np.linspace(0, len(acc_x_vals)-1, len(stress_vals)), 
                          np.arange(len(stress_vals)) * (len(acc_x_vals) / len(stress_vals)),
                          stress_vals)

eda_interp = np.interp(np.linspace(0, len(acc_x_vals)-1, len(eda_means)),
                       np.arange(len(eda_means)) * (len(acc_x_vals) / len(eda_means)),
                       eda_means)

# Truncate to same length
min_len = min(len(acc_mag), len(stress_interp), len(eda_interp))
acc_mag_trunc = acc_mag[:min_len]
stress_interp = stress_interp[:min_len]
eda_interp = eda_interp[:min_len]

corr_mag_stress = np.corrcoef(acc_mag_trunc, stress_interp)[0, 1]
corr_mag_eda = np.corrcoef(acc_mag_trunc, eda_interp)[0, 1]
corr_stress_eda = np.corrcoef(stress_interp, eda_interp)[0, 1]

print(f"Acceleration ↔ Stress:  {corr_mag_stress:+.3f}")
print(f"Acceleration ↔ EDA:     {corr_mag_eda:+.3f}")
print(f"Stress ↔ EDA:           {corr_stress_eda:+.3f}")
print()

# Summary
print("=" * 80)
print("🎯 OBSERVATIONS")
print("=" * 80)
print()

if np.std(stress_vals) < 30:
    print("✓ Stress stayed LOW and STABLE")
    print(f"  → Good calm state (StdDev: {np.std(stress_vals):.1f})")
else:
    print("⚠ Stress varied significantly")
    print(f"  → May have gotten stressed (StdDev: {np.std(stress_vals):.1f})")
print()

if np.std(acc_x_vals) > 5000:
    print("✓ Significant hand MOVEMENT detected")
    print(f"  → ACC_X variance: {np.std(acc_x_vals):.1f}")
else:
    print("⚠ Limited hand movement")
    print(f"  → ACC_X variance: {np.std(acc_x_vals):.1f}")
print()

if abs(corr_mag_stress) < 0.3:
    print("✓ Movement and stress are INDEPENDENT")
    print(f"  → Confirms different physiological inputs")
else:
    print("⚠ Movement affects stress readings")
    print(f"  → May indicate motion artifacts")
print()

print(f"EDA stability: StdDev = {np.std(eda_means):.1f}")
print(f"  → Sweat gland activity {'STABLE (calm)' if np.std(eda_means) < 15 else 'VARIABLE (aroused)'}")
print()
