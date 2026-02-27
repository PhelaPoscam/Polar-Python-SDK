"""
Alternative analysis - look for patterns, text, or well-known formats in the 64-byte data
"""

import struct

hex_data = "880810250a6f0000601d38aa382a2c0f04b2b034ea7f03193d4b404220062082007f3d4e40d3b8a1b80000000000000000000000000000000000000000000000"
data = bytes.fromhex(hex_data)

print("=" * 80)
print("NUANIC 64-BYTE DATA  - ALTERNATIVE ANALYSIS")
print("=" * 80)
print()

# 1. Look for readable text
print("[1] ASCII/Text Search")
print("-" * 80)
ascii_str = ""
for byte in data:
    if 32 <= byte <= 126:
        ascii_str += chr(byte)
    else:
        if ascii_str:
            print(f"  Found text: '{ascii_str}'")
            ascii_str = ""
if ascii_str:
    print(f"  Found text: '{ascii_str}'")
print()

# 2. Interpret as individual bytes
print("[2] As Individual Bytes")
print("-" * 80)
bytes_list = list(data)
print(f"First 20 bytes: {bytes_list[:20]}")
print(f"Last 20 bytes: {bytes_list[-20:]}")
print()

# Check for patterns
non_zero = [b for b in bytes_list if b != 0]
print(f"Non-zero bytes: {len(non_zero)} out of {len(bytes_list)}")
print(f"Byte range: {min(non_zero)} to {max(non_zero)}")
print()

# 3. Try as (8-bit, 8-bit) pairs for HR ranges
print("[3] HR Value Hypothesis - Two-byte Encoding")
print("-" * 80)
print("If bytes are: [MSB, LSB] or [0, HR]...")
for i in range(0, min(40, len(data)-1), 2):
    b1, b2 = data[i], data[i+1]
    print(f"Bytes {i:2d}-{i+1:2d}: 0x{b1:02X} 0x{b2:02X} | As pair: {b1}{b2:02d} | As individual: {b1}, {b2}")
print()

# 4. Check if data might be stored differently
print("[4] 4-byte Chunks (Potential DWORD storage)")
print("-" * 80)
for i in range(0, min(40, len(data)-3), 4):
    val_le = struct.unpack('<I', data[i:i+4])[0]
    val_be = struct.unpack('>I', data[i:i+4])[0]
    print(f"Bytes {i:2d}-{i+3:2d}: LE={val_le:10d} (0x{val_le:08X}) | BE={val_be:10d} (0x{val_be:08X})")
print()

# 5. Check what we know: the ring showed HR data, so find HR-like ranges
print("[5] Smart Search for Physiological Ranges")
print("-" * 80)
# Look for bytes in specific ranges
hr_candidates = []
for i in range(len(data)-1):
    b = data[i]
    # HR is typically 40-200 for adults
    if 40 <=b <= 200:
        hr_candidates.append((i, b))

if hr_candidates:
    print(f"Found {len(hr_candidates)} bytes in HR range (40-200):")
    for pos, val in hr_candidates[:10]:
        context_before = data[max(0, pos-2):pos]
        context_after = data[pos+1:min(len(data), pos+3)]
        print(f"  Position {pos:2d}: {val:3d} (context: ...{context_before.hex()  }[{val:02X}]{context_after.hex()}...)")
else:
    print("No bytes found in typical HR range (40-200)")
print()

print("[6] Possible Encodings for First Chunk")
print("-" * 80)
first_40_bytes = data[:40]
print("Raw bytes:", first_40_bytes.hex())
print()

# What if it's encoded in a specific format?
# Try: split into 5-byte chunks (10 values of 5 bytes each = 50 bits each)
print("Interpretation: Key measurement data might be in first 20-40 bytes")
print("Remaining 24 bytes appear to be zeros (padding)")
print()
print("HYPOTHESIS: Characteristic contains BINARY MEASUREMENT DATA")
print("  - Likely compressed or custom-encoded")
print("  - Need ring's documentation or reverse-engineer from app comparison")
print()

print("=" * 80)
print("NEXT ACTION: Compare with Nuanic App")
print("=" * 80)
print()
print("Steps:")
print("1. Open Nuanic companion app on your phone")
print("2. Note current measurements: HR, HRV, etc.")
print("3. Run the extractor again")
print("4. With new data + app values, we can identify the mapping")
print()
