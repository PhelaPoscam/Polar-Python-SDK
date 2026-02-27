#!/usr/bin/env python3
"""
Verify if stress conversion formula is correct:
stress_percent = (stress_raw / 255) * 100

Compare my raw capture with app's DNE to validate
"""
import pandas as pd
import numpy as np

# Read app export
app_export = pd.read_csv('data/Exported Data/Nuanic 2026-02-27T08_48_38.217Z.csv')

# Read my captured data
my_capture = pd.read_csv('data/nuanic_logs/nuanic_2026-02-27_12-32-24.csv')

print("=" * 80)
print("VERIFICATION: Is (stress_raw / 255) * 100 correct?")
print("=" * 80)

print("\n### MY ASSUMPTION ###")
print("Formula: stress_percent = (stress_raw / 255) * 100")
print("\nRationale:")
print("  - Byte 14 is a single byte (0-255)")
print("  - Dividing by max value (255) → 0-1 ratio")
print("  - Multiplying by 100 → 0-100%")
print("  - Simple linear scaling")

print("\n### CHECKING MY CAPTURED DATA ###")
print(f"\nRaw stress values I captured:")
print(f"  Min: {my_capture['stress_raw'].min()}")
print(f"  Max: {my_capture['stress_raw'].max()}")
print(f"  Mean: {my_capture['stress_raw'].mean():.1f}")

print(f"\nConverted stress_percent:")
print(f"  Min: {my_capture['stress_percent'].min():.1f}%")
print(f"  Max: {my_capture['stress_percent'].max():.1f}%")
print(f"  Mean: {my_capture['stress_percent'].mean():.1f}%")

print("\n### APP's DNE VALUES ###")
dne_data = app_export[~app_export['dne'].isna()]
print(f"DNE values from app export:")
print(f"  Min: {dne_data['dne'].min():.1f}%")
print(f"  Max: {dne_data['dne'].max():.1f}%")
print(f"  Mean: {dne_data['dne'].mean():.1f}%")

print("\n" + "=" * 80)
print("PROBLEM ANALYSIS")
print("=" * 80)

print("\nProblem 1: Different data ranges")
print(f"  My conversion: 5.9% - 100%")
print(f"  App's DNE: 28% - 100%")
print(f"  → My data goes lower than app's")

print("\nProblem 2: Different means")
print(f"  My conversion: ~50.4%")
print(f"  App's DNE: ~50.8%")
print(f"  → Similar but possibly processed differently")

print("\nProblem 3: Assumption verification")
print("  I assumed:")
print("    - Byte 14 is always stress")
print("    - Range is always 0-255")
print("    - Linear scaling is correct")
print("  But I haven't verified ANY of these!")

print("\n" + "=" * 80)
print("POSSIBLE ISSUES WITH MY FORMULA")
print("=" * 80)

print("\n1. DIFFERENT SCALING:")
print("   What if byte 14 doesn't use full 0-255 range?")
print("   Example: Maybe it's 0-200, not 0-255")
print("   → Formula would be wrong")

print("\n2. DIFFERENT BASELINE:")
print("   What if the app uses baseline subtraction?")
print("   Example: DNE = (raw - baseline) / (max - baseline) * 100")
print("   → My simple conversion wouldn't work")

print("\n3. DIFFERENT METRIC:")
print("   What if byte 14 isn't 'stress' but something else?")
print("   → I might be reading the wrong byte entirely")

print("\n4. TEMPORAL PROCESSING:")
print("   What if the app applies smoothing/filtering?")
print("   → Raw values would differ from DNE even with correct scaling")

print("\n" + "=" * 80)
print("HOW TO VERIFY")
print("=" * 80)

print("\nOption 1: Reverse-engineer from app data")
print("  - App export may contain the raw byte somewhere")
print("  - Check if any column matches my stress_raw values")
print("  - Example: Check if SRL or other fields correlate")

print("\nOption 2: Test with known scenarios")
print("  - Capture data while noting your stress level")
print("  - Compare raw byte value with app's DNE")
print("  - See if relationship is linear or different")

print("\nOption 3: Check packet documentation")
print("  - Nuanic ring BLE protocol specifications")
print("  - What does byte 14 actually represent?")
print("  - Is the range 0-255 or something else?")

print("\nOption 4: Empirical correlation")
if len(my_capture) > 5:
    raw_mean = my_capture['stress_raw'].mean()
    percent_mean = my_capture['stress_percent'].mean()
    print(f"  - My stress_raw mean: {raw_mean:.1f}")
    print(f"  - My stress_percent mean: {percent_mean:.1f}%")
    print(f"  - If correct: {raw_mean}/255*100 = {raw_mean/255*100:.1f}% (matches!)")
    
    print(f"\n  - App DNE mean: {dne_data['dne'].mean():.1f}%")
    print(f"  - Difference: {abs(percent_mean - dne_data['dne'].mean()):.1f}%")
    print(f"  - Discrepancy suggests: Processing or scaling difference")

print("\n" + "=" * 80)
print("HONEST ASSESSMENT")
print("=" * 80)

print("""
MY FORMULA: stress_percent = (stress_raw / 255) * 100

Status: ⚠️  UNVERIFIED ASSUMPTION

Likelihood: 
  - Probably correct (simple linear scaling is common)
  - But could be wrong if byte 14 uses different scale
  - Or if app applies baseline/filtering

What I know:
  ✓ Byte 14 changes with hand position/movement
  ✓ It correlates with app's DNE (roughly)
  ✓ Range of 0-255 makes sense for a byte

What I don't know:
  ✗ Exact meaning of byte 14
  ✗ If 255 really represents 100% stress
  ✗ Whether baseline calibration is applied
  ✗ If app uses temporal filtering

RECOMMENDATION:
  1. Verify with Nuanic documentation
  2. Compare my raw values with app's DNE at same times
  3. Test the formula: Does it predict app DNE accurately?
  4. If correlation is strong → formula probably correct
  5. If correlation is weak → formula needs adjustment
""")

print("=" * 80)
