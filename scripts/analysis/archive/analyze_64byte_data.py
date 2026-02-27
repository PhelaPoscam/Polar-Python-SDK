"""
Analyze the 64-byte Nuanic characteristic data

Raw hex from our first extraction:
880810250a6f0000601d38aa382a2c0f04b2b034ea7f03193d4b404220062082007f3d4e40d3b8a1b8
"""

import struct

# The raw hex data we captured (full 64 bytes from CSV)
hex_data = "880810250a6f0000601d38aa382a2c0f04b2b034ea7f03193d4b404220062082007f3d4e40d3b8a1b80000000000000000000000000000000000000000000000"
data = bytes.fromhex(hex_data)

print("=" * 80)
print("NUANIC 64-BYTE CHARACTERISTIC ANALYSIS")
print("=" * 80)
print(f"\nRaw Hex: {hex_data}")
print(f"Length: {len(data)} bytes\n")

# Try multiple interpretations
print("[INTERPRETATION 1] As Little-Endian 16-bit Values")
print("-" * 80)
shorts = []
for i in range(0, len(data), 2):
    val = struct.unpack('<H', data[i:i+2])[0]
    shorts.append(val)
    print(f"Bytes {i:2d}-{i+1:2d}: 0x{val:04X} = {val:5d}")

print(f"\nAs list: {shorts}\n")

# Try to identify HR, HRV, EDA range
print("[INTERPRETATION 2] Identifying Potential Measurements")
print("-" * 80)
potential_measurements = {}

for i, val in enumerate(shorts):
    if 40 <= val <= 180:
        print(f"Position {i:2d}: {val:5d} ← Could be HEART RATE")
        potential_measurements.setdefault('hr', []).append((i, val))
    elif 10 <= val <= 150:
        print(f"Position {i:2d}: {val:5d} ← Could be HRV/EDA")
        potential_measurements.setdefault('hrv_or_eda', []).append((i, val))
    elif val < 10:
        print(f"Position {i:2d}: {val:5d} ← Small value (flags?)")
    elif val > 1000:
        print(f"Position {i:2d}: {val:5d} ← Large value (timestamp?)")
    else:
        print(f"Position {i:2d}: {val:5d}")

print("\n[INTERPRETATION 3] As 32-bit Float Values")
print("-" * 80)
if len(data) >= 16:
    floats = []
    for i in range(0, min(16, len(data)), 4):
        try:
            val = struct.unpack('<f', data[i:i+4])[0]
            floats.append(val)
            print(f"Bytes {i:2d}-{i+3:2d}: {val:12.6f}")
        except:
            break
    print(f"\nAs list: {floats}\n")

print("[HYPOTHESIS] Most Likely Interpretation")
print("-" * 80)
print("Given that the ring stores physiological data:")
print()
print(f"Position 0 ({shorts[0]}): Likely a flag or mode indicator")
print(f"Position 1 ({shorts[1]}): Could be HEART RATE (reasonable range)")
print(f"Position 2 ({shorts[2]}): Large value - timestamp component?")
print(f"Position 3 ({shorts[3]}): Zero - padding?")
print(f"Position 4 ({shorts[4]}): Small-medium value")
print(f"Position 5 ({shorts[5]}): Large value - could be divided into HR components?")
print()

print("[NEXT STEPS]")
print("-" * 80)
print("1. Compare with what the Nuanic app shows on your wrist/phone")
print("2. Look for patterns: if you see HR=75 on app, find 75 in the data")
print("3. Document the exact mapping of bytes to measurements")
print("4. Create a proper parser once pattern is identified")
print()

# Try to find 75, 150, 72, etc (common HR values)
print("[PATTERN MATCHING] Looking for Common Values")
print("-" * 80)
test_values = [72, 75, 100, 150, 60, 80, 90, 45, 50, 95]
for test_val in test_values:
    if test_val in shorts:
        idx = shorts.index(test_val)
        print(f"Found {test_val} at position {idx}")

print("\n" + "=" * 80)
print("OUTPUT: Check your ring's companion app and compare HR/HRV values!")
print("=" * 80)
