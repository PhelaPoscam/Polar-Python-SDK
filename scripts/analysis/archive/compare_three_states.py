"""
Compare ring data across three states:
1. Original in dock
2. On finger
3. Back to charger
"""

# Data when ring was in DOCK (first session)
dock1_hex = "880810250a6f0000601d38aa382a2c0f04b2b034ea7f03193d4b404220062082007f3d4e40d3b8a1b80000000000000000000000000000000000000000000000"

# Data when ring was ON FINGER
finger_hex = "880810250A6F0000601D38AA382A2E0F04B2B034EC7F03193D4B404220062081007F3D4E40D3B8A1B80000000000000000000000000000000000000000000000"

# Data when ring BACK IN CHARGER (just now)
dock2_hex = "880810250A6F0000601D38AA382A2E0F04B2B034EC7F03193D4B404220062081007F3D4E40D3B8A1B80000000000000000000000000000000000000000000000"

print("="*80)
print("NUANIC RING: THREE-STATE COMPARISON")
print("="*80)

# Convert to bytes
dock1_bytes = bytes.fromhex(dock1_hex)
finger_bytes = bytes.fromhex(finger_hex)
dock2_bytes = bytes.fromhex(dock2_hex)

print(f"\nState 1 (Dock):       {dock1_hex[:60]}...")
print(f"State 2 (Finger):     {finger_hex[:60]}...")
print(f"State 3 (Back Dock):  {dock2_hex[:60]}...")

# Check if finger and dock2 are identical
if finger_hex.upper() == dock2_hex.upper():
    print("\n⚠️  WARNING: Finger data = Back-to-charger data (IDENTICAL!)")
    print("   This means the changed values PERSISTED after removing from finger")

# Find differences between each state
print(f"\n\n{'='*80}")
print(f"CHANGES: Dock1 → Finger → Dock2")
print("="*80)

print("\nPos  | Dock1 | Finger | Dock2 | Δ1→2 | Δ2→3 | Pattern")
print("-----|-------|--------|-------|------|------|----------------------------")

changed_positions = []
for i in range(40):
    d1 = dock1_bytes[i]
    fn = finger_bytes[i]
    d2 = dock2_bytes[i]
    
    delta_1to2 = fn - d1
    delta_2to3 = d2 - fn
    
    pattern = ""
    if d1 != fn or fn != d2:
        changed_positions.append(i)
        if d1 != fn and fn == d2:
            pattern = "CHANGED & STUCK"
        elif d1 != fn and fn != d2 and d1 == d2:
            pattern = "CHANGED & REVERTED"
        elif d1 != fn and fn != d2:
            pattern = "CONTINUOUS CHANGE"
        else:
            pattern = "???"
    
    # Highlight EDA range values
    eda_marker = ""
    if 0 <= fn <= 100:
        eda_marker = f" ← {fn}µS"
    
    change_marker = " ***" if d1 != fn or fn != d2 else ""
    
    print(f"{i:4d} | {d1:5d} | {fn:6d} | {d2:5d} | {delta_1to2:+4d} | {delta_2to3:+4d} | {pattern}{eda_marker}{change_marker}")

print("\n\n" + "="*80)
print("KEY CHANGED BYTES (positions that changed)")
print("="*80)

for pos in changed_positions:
    d1 = dock1_bytes[pos]
    fn = finger_bytes[pos]
    d2 = dock2_bytes[pos]
    
    print(f"\n[Byte {pos}]")
    print(f"  Dock1:       {d1:3d} (0x{d1:02X})")
    print(f"  Finger:      {fn:3d} (0x{fn:02X}) → Change: {fn-d1:+d}")
    print(f"  Back-Dock:   {d2:3d} (0x{d2:02X}) → Change: {d2-fn:+d}")
    
    # Analyze behavior
    if fn == d2:
        print(f"  ➜ PERSISTENT: Value stayed at {fn} after removing from finger")
        if 0 <= fn <= 100:
            print(f"  ➜ Could be LAST MEASURED EDA: {fn} µS")
    elif d1 == d2:
        print(f"  ➜ REVERTED: Value returned to original {d1}")
        print(f"  ➜ Likely a STATUS flag or LIVE sensor (finger detection)")
    else:
        print(f"  ➜ CONTINUING: Value keeps changing")
        print(f"  ➜ Likely a COUNTER or TIMESTAMP")

print("\n\n" + "="*80)
print("16-BIT VALUES (Little-Endian)")
print("="*80)

print("\nPos  | Dock1 | Finger | Dock2 | Interpretation")
print("-----|-------|--------|-------|----------------------------------------")

for i in range(0, 40, 2):
    d1_val = int.from_bytes(dock1_bytes[i:i+2], 'little')
    fn_val = int.from_bytes(finger_bytes[i:i+2], 'little')
    d2_val = int.from_bytes(dock2_bytes[i:i+2], 'little')
    
    interp = ""
    if d1_val != fn_val or fn_val != d2_val:
        if 3500 <= fn_val <= 4000:
            temp = fn_val / 100
            interp = f"Temperature: {temp:.2f}°C ← CHANGED!"
        elif 0 <= fn_val <= 100:
            interp = f"EDA: {fn_val} µS"
        elif 40 <= fn_val <= 200:
            interp = f"HR?: {fn_val} bpm"
    
    marker = " ***" if d1_val != fn_val or fn_val != d2_val else ""
    
    print(f"{i:4d} | {d1_val:5d} | {fn_val:6d} | {d2_val:5d} | {interp}{marker}")

print("\n\n" + "="*80)
print("HYPOTHESIS & CONCLUSION")
print("="*80)

# Check if values persisted or reverted
persisted = []
reverted = []
continuing = []

for pos in changed_positions:
    d1 = dock1_bytes[pos]
    fn = finger_bytes[pos]
    d2 = dock2_bytes[pos]
    
    if fn == d2 and fn != d1:
        persisted.append(pos)
    elif d1 == d2 and d1 != fn:
        reverted.append(pos)
    else:
        continuing.append(pos)

if persisted:
    print(f"\n✓ PERSISTED VALUES (stayed after removing from finger):")
    print(f"  Positions: {persisted}")
    print(f"  → These likely contain MEASURED DATA that the ring stores")
    print(f"  → Example: Last EDA reading, temperature, etc.")
    
    for pos in persisted:
        val = finger_bytes[pos]
        if 0 <= val <= 100:
            print(f"\n  Byte {pos}: {val} µS ← STRONG EDA CANDIDATE!")

if reverted:
    print(f"\n✓ REVERTED VALUES (changed back to original):")
    print(f"  Positions: {reverted}")
    print(f"  → These are LIVE STATUS indicators")
    print(f"  → Example: 'Ring is being worn' flag")

if continuing:
    print(f"\n✓ CONTINUING CHANGE:")
    print(f"  Positions: {continuing}")
    print(f"  → These are COUNTERS or TIMESTAMPS")

# Overall pattern
print("\n" + "="*80)
print("\n🎯 RING BEHAVIOR:")

if finger_hex.upper() == dock2_hex.upper():
    print("\n  The ring STORES the last measurements!")
    print("  When you wore it, it updated bytes 14, 20, 31")
    print("  When you put it back, the values STAYED (not live sensor)")
    print("\n  This means:")
    print("    • Ring continuously measures & stores data internally")
    print("    • BLE reads show HISTORICAL snapshots, not live data")
    print("    • To see changes, ring needs time to record new measurements")
    print("\n  ⚠️  LIMITATION:")
    print("    You can't get REAL-TIME EDA via BLE like Polar H10")
    print("    Ring provides STORED DATA from recent measurements")
else:
    print("\n  Some values reverted - ring has live status indicators")

print("\n" + "="*80)
print("NEXT STEPS")
print("="*80)
print("\n1. Wear ring for 5-10 minutes (let it collect more data)")
print("2. Check companion app - note the EDA value shown")
print("3. Run extractor again")
print("4. Compare: Does byte 14 match the app's EDA reading?")
print("\nIf byte 14 matches app → We found the EDA position!")
print("Then we can create a parser and read historical EDA data")
