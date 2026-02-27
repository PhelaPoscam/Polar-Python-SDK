"""
Nuanic Ring 64-Byte Analysis - CORRECTED FOR EDA

Ring measures EDA (Electrodermal Activity), NOT heart rate!

EDA typical ranges:
  - Low (relaxed): 0-20 µS
  - Normal: 20-50 µS  
  - Elevated (stressed): 50-100 µS
  - Very high: 100+ µS

Also likely contains:
  - Temperature: 35-40°C
  - Activity level: 0-100%
  - Other stress indicators
"""

import struct

hex_data = "880810250a6f0000601d38aa382a2c0f04b2b034ea7f03193d4b404220062082007f3d4e40d3b8a1b80000000000000000000000000000000000000000000000"
data = bytes.fromhex(hex_data)

print("=" * 80)
print("NUANIC RING 64-BYTE ANALYSIS - CORRECTED FOR EDA")
print("=" * 80)
print()

# Parse as individual bytes
bytes_list = list(data)

print("[1] LOOKING FOR EDA VALUES (0-100)")
print("-" * 80)
eda_candidates = []
for i in range(len(data)):
    b = data[i]
    if 0 <= b <= 100:  # EDA range
        eda_candidates.append((i, b))
        print(f"Position {i:2d}: {b:3d} µS ← Potential EDA value")

print(f"\nTotal EDA-range bytes: {len(eda_candidates)}\n")

# Parse as 16-bit shorts (might be scaled EDA, like EDA*10 or similar)
print("[2] LOOKING FOR SCALED VALUES (0-1000 = 0-100 EDA×10)")
print("-" * 80)
shorts = []
for i in range(0, len(data)-1, 2):
    val = struct.unpack('<H', data[i:i+2])[0]
    shorts.append(val)
    if 0 <= val <= 1000:
        print(f"Bytes {i:2d}-{i+1:2d}: {val:4d} ← Could be EDA×10")

print()

print("[3] TEMPERATURE RANGES (3500-4000 = 35-40°C)")
print("-" * 80)
# Temperature might be stored as value * 100, so 3700 = 37.0°C
for i in range(0, len(data)-3, 4):
    val_le = struct.unpack('<I', data[i:i+4])[0]
    temp_c = val_le / 100.0
    if 20 <= temp_c <= 45:  # Reasonable body temp range
        print(f"Bytes {i:2d}-{i+3:2d}: {val_le:5d} → {temp_c:5.1f}°C")

print()

print("[4] SMART SEARCH - EDA + Temperature + Activity")
print("-" * 80)
print("Hypothesis: First 20-30 bytes contain the measurements")
print("  - Bytes 0-1: EDA main reading")
print("  - Bytes 2-3: EDA secondary/trend")
print("  - Bytes 4-5: Temperature")
print("  - Bytes 6-7: Activity level")
print("  - Bytes 8+: Other sensor data")
print()

# Show first 20 bytes in different formats
print("[5] FIRST 20 BYTES - MULTIPLE INTERPRETATIONS")
print("-" * 80)
for i in range(0, 20, 2):
    b1, b2 = data[i], data[i+1]
    as_bytes = [b1, b2]
    as_u16_le = struct.unpack('<H', data[i:i+2])[0]
    as_u16_be = struct.unpack('>H', data[i:i+2])[0]
    
    print(f"Pos {i:2d}: Bytes=[{b1:3d},{b2:3d}] | "
          f"LE_u16={as_u16_le:5d} | BE_u16={as_u16_be:5d}")
    
    # Add interpretation
    if 0 <= as_u16_le <= 100:
        print(f"         ↳ LE could be EDA:{as_u16_le}")
    if 0 <= b1 <= 100:
        print(f"         ↳ Byte1 could be EDA:{b1}")
    if 0 <= b2 <= 100:
        print(f"         ↳ Byte2 could be EDA:{b2}")

print()
print("=" * 80)
print("NEXT STEP: Put ring on finger and monitor for changes!")
print("=" * 80)
print()
print("When ring is active:")
print("  1. Run: python scripts/ble/nuanic_data_extractor.py")
print("  2. Check which bytes CHANGE")
print("  3. Changed bytes = measurement values!")
print("  4. Stationary bytes = config/padding")
print()
