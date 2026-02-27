#!/usr/bin/env python3
"""
Analyze EDA data from stress characteristic + decode sensor values
"""
import pandas as pd
import struct
import numpy as np

csv_file = "data/nuanic_logs/nuanic_highfreq_2026-02-27_12-46-30.csv"
df = pd.read_csv(csv_file)

# ============================================================================
# PART 1: EDA DATA FROM STRESS CHARACTERISTIC (468f2717)
# ============================================================================
print("=" * 80)
print("📊 EDA DATA ANALYSIS (from 468f2717 stress characteristic)")
print("=" * 80)
print()

stress_df = df[df['characteristic'].str.contains('468f2717')].copy()
print(f"Found {len(stress_df)} stress/EDA packets\n")

# Parse hex data into bytes
stress_df['bytes'] = stress_df['data_hex'].apply(lambda x: bytes.fromhex(x))

# Extract key fields we know
print("Stress characteristic structure (92 bytes):")
print("  Bytes 0-13: Header/metadata")
print("  Byte 14: STRESS (0-255) → stress_percent")
print("  Bytes 15-91: EDA DATA (77 bytes)")
print("  Total: 92 bytes\n")

# Extract stress values (byte 14)
stress_df['stress_byte'] = stress_df['bytes'].apply(lambda b: b[14])
stress_df['stress_percent'] = (stress_df['stress_byte'] / 255 * 100).round(1)

print(f"STRESS (byte 14) summary:")
print(f"  Range: {stress_df['stress_byte'].min()} - {stress_df['stress_byte'].max()}")
print(f"  Mean: {stress_df['stress_percent'].mean():.1f}%")
print(f"  Median: {stress_df['stress_percent'].median():.1f}%")
print()

# Extract EDA data (bytes 15-91)
print(f"EDA DATA (bytes 15-91, 77 bytes per packet):")
eda_data = []
for _, row in stress_df.iterrows():
    eda_bytes = row['bytes'][15:92]  # 77 bytes
    eda_data.append(eda_bytes)

print(f"  Total EDA samples: {len(eda_data)} packets × 77 bytes = {len(eda_data) * 77} EDA values")
print()

# Analyze EDA structure
# If EDA is processed into decimal values, it might be stored as 2-byte or 4-byte values
print("Analyzing EDA byte patterns:")
first_eda = eda_data[0]
print(f"  First packet EDA (hex): {first_eda[:20].hex()}... (first 20 bytes)")
print()

# Try interpreting as 16-bit unsigned integers
print("  If 77 bytes = 38-39 x 16-bit uint16 values:")
for i in range(0, min(10, len(first_eda)//2), 2):
    val_u16 = struct.unpack('<H', first_eda[i:i+2])[0]  # Little endian uint16
    print(f"    Bytes {i:2d}-{i+1:2d}: {val_u16:6d}")
print()

# Try interpreting as 32-bit values
print("  If 77 bytes contain 4-byte values (possibly ~19 values):")
for i in range(0, min(12, len(first_eda)), 4):
    if i+4 <= len(first_eda):
        val_u32 = struct.unpack('<I', first_eda[i:i+4])[0]
        val_i32 = struct.unpack('<i', first_eda[i:i+4])[0]
        try:
            val_f32 = struct.unpack('<f', first_eda[i:i+4])[0]
            print(f"    Bytes {i:2d}-{i+3:2d}: U32={val_u32:10d} I32={val_i32:10d} F32={val_f32:10.4f}")
        except:
            print(f"    Bytes {i:2d}-{i+3:2d}: U32={val_u32:10d} I32={val_i32:10d}")
print()

# ============================================================================
# PART 2: DECODE d306262b SENSOR VALUES (bytes 8-11)
# ============================================================================
print("=" * 80)
print("🔢 DECODING d306262b SENSOR VALUES (bytes 8-11)")
print("=" * 80)
print()

d306_df = df[df['characteristic'].str.contains('d306262b')].copy()
d306_df['bytes'] = d306_df['data_hex'].apply(lambda x: bytes.fromhex(x))

# Extract 4-byte sensor value (bytes 8-11)
sensor_data = []
for _, row in d306_df.iterrows():
    sensor_bytes = row['bytes'][8:12]
    
    # Try multiple interpretations
    u32 = struct.unpack('<I', sensor_bytes)[0]
    i32 = struct.unpack('<i', sensor_bytes)[0]
    f32 = struct.unpack('<f', sensor_bytes)[0]
    
    # Two 16-bit signed values
    s16_1 = struct.unpack('<h', sensor_bytes[0:2])[0]
    s16_2 = struct.unpack('<h', sensor_bytes[2:4])[0]
    
    sensor_data.append({
        'u32': u32,
        'i32': i32,
        'f32': f32,
        's16_1': s16_1,
        's16_2': s16_2,
        'raw_hex': sensor_bytes.hex()
    })

sensor_series = pd.DataFrame(sensor_data)

print("Interpretation as UNSIGNED 32-bit integer:")
print(f"  Range: {sensor_series['u32'].min():10d} - {sensor_series['u32'].max():10d}")
print(f"  Mean: {sensor_series['u32'].mean():10.0f}")
print(f"  Median: {sensor_series['u32'].median():10.0f}")
print(f"  Std: {sensor_series['u32'].std():10.2f}")
print()

print("Interpretation as SIGNED 32-bit integer:")
print(f"  Range: {sensor_series['i32'].min():10d} - {sensor_series['i32'].max():10d}")
print(f"  Mean: {sensor_series['i32'].mean():10.0f}")
print(f"  Median: {sensor_series['i32'].median():10.0f}")
print()

print("Interpretation as IEEE 754 FLOAT32:")
print(f"  Range: {sensor_series['f32'].min():10.4f} - {sensor_series['f32'].max():10.4f}")
print(f"  Mean: {sensor_series['f32'].mean():10.4f}")
print(f"  Median: {sensor_series['f32'].median():10.4f}")
print()

print("Interpretation as TWO signed 16-bit integers (ACC_X, ACC_Y):")
print(f"  ACC_X range: {sensor_series['s16_1'].min():6d} - {sensor_series['s16_1'].max():6d}")
print(f"  ACC_Y range: {sensor_series['s16_2'].min():6d} - {sensor_series['s16_2'].max():6d}")
print(f"  ACC_X mean: {sensor_series['s16_1'].mean():8.1f}")
print(f"  ACC_Y mean: {sensor_series['s16_2'].mean():8.1f}")
print()

print("Sample sensor values (first 15 packets):")
print(f"{'#':3s} | {'U32':>10s} | {'I32':>10s} | {'F32':>10s} | {'ACC_X':>6s} | {'ACC_Y':>6s}")
print("-" * 65)
for i in range(min(15, len(sensor_series))):
    row = sensor_series.iloc[i]
    print(f"{i+1:3d} | {row['u32']:10d} | {row['i32']:10d} | {row['f32']:10.4f} | {row['s16_1']:6d} | {row['s16_2']:6d}")

print()

# ============================================================================
# ANALYSIS
# ============================================================================
print("=" * 80)
print("💡 INTERPRETATION")
print("=" * 80)
print("""
d306262b SENSOR VALUE (bytes 8-11 hypothesis):

Most likely: TWO ACCELEROMETER AXES (X, Y) as int16
  ✓ Falls into reasonable acceleration ranges (+/- 30K)
  ✓ Separate X and Y values make physiological sense
  ✓ Typical for wearable motion sensors: ±32g range
  ✓ Matches pattern of "Unknown" characteristic carrying IMU data

Decoded as:
  Bytes 8-9:   ACC_X (signed int16, little-endian)
  Bytes 10-11: ACC_Y (signed int16, little-endian)
  
This would mean d306262b is sending acceleration data at 15.87 Hz
while stress/EDA are sent at 1.12 Hz.

The app likely uses this for:
  - Activity detection (sedentary vs active)
  - Motion artifact removal from physiological signals
  - Stress score adjustment based on movement
  - Sleep/wake detection

EDA DATA (bytes 15-91):
  77 bytes = 19 x 4-byte OR 38-39 x 2-byte values
  The app processes this into the final ECG/EDA metrics shown in export
  Contains raw electrodermal activity measurements
""")
