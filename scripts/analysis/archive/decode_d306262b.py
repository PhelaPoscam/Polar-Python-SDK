#!/usr/bin/env python3
"""
Properly decode d306262b 16-byte packets
"""
import pandas as pd
import struct

csv_file = "data/nuanic_logs/nuanic_highfreq_2026-02-27_12-46-30.csv"
df = pd.read_csv(csv_file)

# Get d306262b packets only
d306_df = df[df['characteristic'].str.contains('d306262b')].copy()

print("=" * 80)
print("🔍 DECODING d306262b (16-byte packets)")
print("=" * 80)
print()

# Parse each packet hex string into bytes
d306_df['bytes'] = d306_df['data_hex'].apply(
    lambda x: bytes.fromhex(x)
)

print("First 20 packets with byte-by-byte breakdown:\n")
print(f"{'#':3s} | {'Hex':<37s} | Byte breakdown")
print("-" * 80)

for idx, (i, row) in enumerate(d306_df.head(20).iterrows()):
    hex_str = row['data_hex']
    raw_bytes = row['bytes']
    
    # Print each byte
    byte_str = " ".join([f"{b:02x}" for b in raw_bytes])
    
    # Analyze positions
    # Bytes 0-7: Likely timestamp (little endian or counter)
    ts_bytes = raw_bytes[0:8]
    ts_val = struct.unpack('<Q', ts_bytes)[0]  # Unsigned long long, little endian
    
    # Bytes 8-11: Some 4-byte value
    val_bytes = raw_bytes[8:12]
    val_u32 = struct.unpack('<I', val_bytes)[0]  # Unsigned int, little endian
    
    # Bytes 12: Standalone byte?
    byte_12 = raw_bytes[12]
    
    # Bytes 13-15: Padding?
    padding = raw_bytes[13:16]
    
    print(f"{idx+1:3d} | {hex_str:<37s} | [TS:{ts_val:>12d}] [{val_u32:>10d}] B12:{byte_12:3d} Pad:{padding.hex()}")

print("\n" + "=" * 80)
print("📊 BYTE 12 ANALYSIS (appears to be a metric)")
print("=" * 80)

byte_12_vals = d306_df['bytes'].apply(lambda b: b[12])
print(f"\nByte 12 statistics:")
print(f"  Range: {byte_12_vals.min()} - {byte_12_vals.max()}")
print(f"  Mean:  {byte_12_vals.mean():.1f}")
print(f"  Unique values: {len(byte_12_vals.unique())}")
print(f"\nFrequency distribution:")
value_counts = byte_12_vals.value_counts().sort_index()
for val, count in value_counts.items():
    pct = (count / len(byte_12_vals)) * 100
    bar = "█" * int(pct/2)
    print(f"    {val:3d} | {bar:<50s} {count:4d} ({pct:5.1f}%)")

print("\n" + "=" * 80)
print("🔢 BYTES 8-11 ANALYSIS (4-byte values)")
print("=" * 80)

val_8_11 = d306_df['bytes'].apply(lambda b: struct.unpack('<I', b[8:12])[0])
print(f"\nValue (bytes 8-11) statistics:")
print(f"  Range: {val_8_11.min()} - {val_8_11.max()}")
print(f"  Mean:  {val_8_11.mean():.0f}")
print(f"  Median: {val_8_11.median():.0f}")
print(f"  Unique values: {len(val_8_11.unique())}")

# Show the min/max/median values
print(f"\n  Top 10 most common values:")
for val, count in val_8_11.value_counts().head(10).iterrows():
    pct = (count / len(val_8_11)) * 100
    print(f"    {val:10d} | {count:3d} times ({pct:5.1f}%) | hex: {val:08x}")

print("\n" + "=" * 80)
print("💡 HYPOTHESIS")
print("=" * 80)
print("""
d306262b appears to be:
- Bytes 0-7:   Timestamp counter (incrementing value)
- Bytes 8-11:  Sensor readout (varies widely, possibly ACC data)
- Byte 12:     Quality/RSSI metric (~50-100 range)
- Bytes 13-15: Padding/reserved

This looks like high-frequency sensor data (accelerometer or motion sensor)
sent at ~16 Hz to complement the slower stress/EDA readings!
""")
