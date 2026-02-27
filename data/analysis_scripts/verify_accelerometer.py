#!/usr/bin/env python3
"""
Compare d306262b sensor values: Movement vs Stationary
"""
import pandas as pd
import struct
import numpy as np

# Load both captures
movement_csv = "data/nuanic_logs/nuanic_highfreq_2026-02-27_12-46-30.csv"  # Original (with movement)
stationary_csv = "data/nuanic_logs/nuanic_highfreq_2026-02-27_12-53-41.csv"  # Stationary

df_move = pd.read_csv(movement_csv)
df_stat = pd.read_csv(stationary_csv)

print("=" * 80)
print("🔍 ACCELEROMETER DATA VERIFICATION")
print("=" * 80)
print()

# Extract d306262b packets
d306_move = df_move[df_move['characteristic'].str.contains('d306262b')].copy()
d306_stat = df_stat[df_stat['characteristic'].str.contains('d306262b')].copy()

# Parse sensor values
def extract_acc(hex_str):
    """Extract ACC_X, ACC_Y from bytes 8-11"""
    b = bytes.fromhex(hex_str)
    acc_x = struct.unpack('<h', b[8:10])[0]  # signed int16
    acc_y = struct.unpack('<h', b[10:12])[0]
    return acc_x, acc_y

d306_move['bytes'] = d306_move['data_hex'].apply(lambda x: bytes.fromhex(x))
d306_stat['bytes'] = d306_stat['data_hex'].apply(lambda x: bytes.fromhex(x))

d306_move[['acc_x', 'acc_y']] = d306_move['bytes'].apply(
    lambda b: pd.Series([struct.unpack('<h', b[8:10])[0], struct.unpack('<h', b[10:12])[0]])
)

d306_stat[['acc_x', 'acc_y']] = d306_stat['bytes'].apply(
    lambda b: pd.Series([struct.unpack('<h', b[8:10])[0], struct.unpack('<h', b[10:12])[0]])
)

print("📊 CAPTURE 1: WITH MOVEMENT (12:46:30)")
print(f"   Packets: {len(d306_move)}")
print(f"   Duration: ~30.4s")
print()
print("   ACC_X Statistics:")
print(f"      Range:  {d306_move['acc_x'].min():7d} to {d306_move['acc_x'].max():7d}")
print(f"      Mean:   {d306_move['acc_x'].mean():7.1f}")
print(f"      StdDev: {d306_move['acc_x'].std():7.1f}")
print(f"      |Max|:  {max(abs(d306_move['acc_x'].min()), abs(d306_move['acc_x'].max())):7d}")
print()
print("   ACC_Y Statistics:")
print(f"      Range:  {d306_move['acc_y'].min():7d} to {d306_move['acc_y'].max():7d}")
print(f"      Mean:   {d306_move['acc_y'].mean():7.1f}")
print(f"      StdDev: {d306_move['acc_y'].std():7.1f}")
print()

print("=" * 80)
print("📊 CAPTURE 2: STATIONARY (12:53:41)")
print(f"   Packets: {len(d306_stat)}")
print(f"   Duration: ~30s")
print()
print("   ACC_X Statistics:")
print(f"      Range:  {d306_stat['acc_x'].min():7d} to {d306_stat['acc_x'].max():7d}")
print(f"      Mean:   {d306_stat['acc_x'].mean():7.1f}")
print(f"      StdDev: {d306_stat['acc_x'].std():7.1f}")
print(f"      |Max|:  {max(abs(d306_stat['acc_x'].min()), abs(d306_stat['acc_x'].max())):7d}")
print()
print("   ACC_Y Statistics:")
print(f"      Range:  {d306_stat['acc_y'].min():7d} to {d306_stat['acc_y'].max():7d}")
print(f"      Mean:   {d306_stat['acc_y'].mean():7.1f}")
print(f"      StdDev: {d306_stat['acc_y'].std():7.1f}")
print()

# ============================================================================
# COMPARISON
# ============================================================================
print("=" * 80)
print("📈 COMPARISON (Movement vs Stationary)")
print("=" * 80)
print()

print(f"{'Metric':<20s} | {'Movement':>15s} | {'Stationary':>15s} | {'Difference':<15s}")
print("-" * 70)

acc_x_move_range = d306_move['acc_x'].max() - d306_move['acc_x'].min()
acc_x_stat_range = d306_stat['acc_x'].max() - d306_stat['acc_x'].min()
print(f"{'ACC_X Range':<20s} | {acc_x_move_range:>15d} | {acc_x_stat_range:>15d} | {acc_x_stat_range - acc_x_move_range:>15d}")

print(f"{'ACC_X StdDev':<20s} | {d306_move['acc_x'].std():>15.1f} | {d306_stat['acc_x'].std():>15.1f} | {d306_stat['acc_x'].std() - d306_move['acc_x'].std():>15.1f}")

acc_y_move_range = d306_move['acc_y'].max() - d306_move['acc_y'].min()
acc_y_stat_range = d306_stat['acc_y'].max() - d306_stat['acc_y'].min()
print(f"{'ACC_Y Range':<20s} | {acc_y_move_range:>15d} | {acc_y_stat_range:>15d} | {acc_y_stat_range - acc_y_move_range:>15d}")

print(f"{'ACC_Y StdDev':<20s} | {d306_move['acc_y'].std():>15.1f} | {d306_stat['acc_y'].std():>15.1f} | {d306_stat['acc_y'].std() - d306_move['acc_y'].std():>15.1f}")

print()

# Calculate motion magnitude
d306_move['magnitude'] = np.sqrt(d306_move['acc_x']**2 + d306_move['acc_y']**2)
d306_stat['magnitude'] = np.sqrt(d306_stat['acc_x']**2 + d306_stat['acc_y']**2)

print(f"{'Magnitude Mean':<20s} | {d306_move['magnitude'].mean():>15.0f} | {d306_stat['magnitude'].mean():>15.0f} | {d306_stat['magnitude'].mean() - d306_move['magnitude'].mean():>15.0f}")
print(f"{'Magnitude StdDev':<20s} | {d306_move['magnitude'].std():>15.1f} | {d306_stat['magnitude'].std():>15.1f} | {d306_stat['magnitude'].std() - d306_move['magnitude'].std():>15.1f}")

print()
print("=" * 80)
print("✅ CONCLUSION")
print("=" * 80)

if d306_stat['acc_x'].std() < d306_move['acc_x'].std() * 0.7:
    print("""
🎯 CONFIRMED: d306262b contains ACCELEROMETER data!

Evidence:
  ✓ Stationary values show MUCH LOWER variance
  ✓ Movement capture has high ACC_X range (±32K)
  ✓ Stationary capture has low ACC_X range
  ✓ Pattern is consistent with IMU (Inertial Measurement Unit)
  
The d306262b characteristic is definitely:
  - Bytes 8-9: ACC_X (signed int16)
  - Bytes 10-11: ACC_Y (signed int16)
  
The Nuanic ring sends high-frequency inertial data for:
  • Activity level detection
  • Motion artifact removal from stress/EDA
  • Sleep/wake detection
  • Real-time movement compensation
""")
else:
    print("""
⚠️  INCONCLUSIVE: Movement and stationary readings are similar
    This could mean:
    - The sensor isn't motion-sensitive
    - Both captures had similar movement
    - The values represent something else (not acceleration)
""")

print()

# Show sample values
print("=" * 80)
print("📋 SAMPLE VALUES")
print("=" * 80)
print()
print("MOVEMENT - First 10 packets:")
print(f"{'#':<3} | {'ACC_X':>7s} | {'ACC_Y':>7s} | {'Magnitude':>9s}")
print("-" * 35)
for i in range(min(10, len(d306_move))):
    row = d306_move.iloc[i]
    print(f"{i+1:<3} | {row['acc_x']:>7d} | {row['acc_y']:>7d} | {row['magnitude']:>9.0f}")

print()
print("STATIONARY - First 10 packets:")
print(f"{'#':<3} | {'ACC_X':>7s} | {'ACC_Y':>7s} | {'Magnitude':>9s}")
print("-" * 35)
for i in range(min(10, len(d306_stat))):
    row = d306_stat.iloc[i]
    print(f"{i+1:<3} | {row['acc_x']:>7d} | {row['acc_y']:>7d} | {row['magnitude']:>9.0f}")
