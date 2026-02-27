"""
Compare ring data from dock vs on finger to identify differences
"""

# Data when ring was in DOCK (from previous session)
dock_hex = "880810250a6f0000601d38aa382a2c0f04b2b034ea7f03193d4b404220062082007f3d4e40d3b8a1b80000000000000000000000000000000000000000000000"

# Data when ring was ON FINGER (from current session)  
finger_hex = "880810250A6F0000601D38AA382A2E0F04B2B034EC7F03193D4B404220062081007F3D4E40D3B8A1B80000000000000000000000000000000000000000000000"

print("="*80)
print("NUANIC RING: DOCK vs FINGER DATA COMPARISON")
print("="*80)

# Convert to bytes
dock_bytes = bytes.fromhex(dock_hex)
finger_bytes = bytes.fromhex(finger_hex)

print(f"\nDock data:   {dock_hex}")
print(f"Finger data: {finger_hex}")

# Find differences
differences = []
for i in range(len(dock_bytes)):
    if dock_bytes[i] != finger_bytes[i]:
        differences.append({
            'position': i,
            'dock_value': dock_bytes[i],
            'finger_value': finger_bytes[i],
            'change': finger_bytes[i] - dock_bytes[i]
        })

print(f"\n\n{'='*80}")
print(f"FOUND {len(differences)} CHANGED BYTES")
print("="*80)

if differences:
    for diff in differences:
        print(f"\nByte {diff['position']:2d}:")
        print(f"  Dock:   {diff['dock_value']:3d} (0x{diff['dock_value']:02X})")
        print(f"  Finger: {diff['finger_value']:3d} (0x{diff['finger_value']:02X})")
        print(f"  Change: {diff['change']:+4d}")
        
        # Check if in EDA range
        if 0 <= diff['dock_value'] <= 100:
            print(f"  ↳ Dock value in EDA range: {diff['dock_value']} µS")
        if 0 <= diff['finger_value'] <= 100:
            print(f"  ↳ Finger value in EDA range: {diff['finger_value']} µS")
else:
    print("\n⚠️  NO CHANGES DETECTED")
    print("\nPossible reasons:")
    print("  1. Ring stores historical data, not live measurements")
    print("  2. Ring needs activation via companion app first")
    print("  3. Ring updates data only at specific intervals")
    print("  4. Need to trigger measurement mode with specific BLE command")

print("\n\n" + "="*80)
print("BYTE-BY-BYTE VIEW (first 40 bytes)")
print("="*80)
print("\nPos  | Dock | Finger | Δ    | EDA? | Notes")
print("-----|------|--------|------|------|------------------------")

for i in range(40):
    dock_val = dock_bytes[i]
    finger_val = finger_bytes[i]
    delta = finger_val - dock_val
    
    eda_dock = f"{dock_val:3d}µS" if 0 <= dock_val <= 100 else "  -  "
    eda_finger = f"{finger_val:3d}µS" if 0 <= finger_val <= 100 else "  -  "
    
    change_marker = "***" if dock_val != finger_val else ""
    
    print(f"{i:4d} | {dock_val:4d} | {finger_val:6d} | {delta:+4d} | {eda_dock} → {eda_finger} | {change_marker}")

print("\n" + "="*80)
print("INTERPRETATION")
print("="*80)

# Interpret as 16-bit little-endian
print("\nAs 16-bit Little-Endian values:")
print("\nPos  | Dock  | Finger | Δ     | Could be?")
print("-----|-------|--------|-------|---------------------------")

for i in range(0, 40, 2):
    dock_val = int.from_bytes(dock_bytes[i:i+2], 'little')
    finger_val = int.from_bytes(finger_bytes[i:i+2], 'little')
    delta = finger_val - dock_val
    
    interpretation = ""
    if 0 <= finger_val <= 100:
        interpretation = f"EDA: {finger_val}µS"
    elif 35 <= finger_val/100 <= 40:
        interpretation = f"Temp: {finger_val/100:.1f}°C"
    elif 40 <= finger_val <= 200:
        interpretation = f"HR?: {finger_val}bpm"
    
    change_marker = " ***" if delta != 0 else ""
    
    print(f"{i:4d} | {dock_val:5d} | {finger_val:6d} | {delta:+6d} | {interpretation}{change_marker}")

print("\n" + "="*80)
print("CONCLUSION")
print("="*80)

if differences:
    print(f"\n✓ Ring data CHANGED when moved from dock to finger!")
    print(f"✓ {len(differences)} bytes show different values")
    print(f"\nThese bytes likely contain:")
    print("  - EDA measurement updates")
    print("  - Temperature changes (finger warmth)")
    print("  - Activity/wearing status")
    print("\nNext step: Identify which byte = current EDA reading")
else:
    print("\n⚠️  Ring data remained IDENTICAL")
    print("\nThis suggests:")
    print("  - Ring stores HISTORICAL data (not live)")
    print("  - Data updates only when synced with app")
    print("  - BLE provides access to STORED logs, not active sensor")
    print("\nRecommendation:")
    print("  1. Open the Nuanic companion app")
    print("  2. Trigger a sync/measurement")
    print("  3. Re-run extraction to see if data updates")
