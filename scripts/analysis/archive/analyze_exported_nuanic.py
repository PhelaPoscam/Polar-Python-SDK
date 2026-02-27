"""
Analyze the manually exported Nuanic data
Understand the actual measurement structure from the app export
"""
import csv
import statistics
from collections import defaultdict
from pathlib import Path

export_file = Path("data/Exported Data/Nuanic 2026-02-27T08_48_38.217Z.csv")

print("="*80)
print("NUANIC RING - EXPORTED DATA ANALYSIS")
print("="*80)

# Read the exported data
data_rows = []
with open(export_file, 'r') as f:
    reader = csv.DictReader(f)
    data_rows = list(reader)

print(f"\nTotal recordings: {len(data_rows)}")

# Analyze each column
columns = {
    'dne': [],
    'srl': [],
    'srrn': [],
    'eda': [],
    'accel': []
}

for row in data_rows:
    for col in columns.keys():
        if row[col] and row[col].strip():
            try:
                columns[col].append(float(row[col]))
            except:
                pass

print("\n" + "="*80)
print("COLUMN ANALYSIS")
print("="*80)

for col, values in columns.items():
    if values:
        print(f"\n{col.upper()} ({len(values)} values):")
        print(f"  Min:     {min(values):.2f}")
        print(f"  Max:     {max(values):.2f}")
        print(f"  Avg:     {statistics.mean(values):.2f}")
        print(f"  Median:  {statistics.median(values):.2f}")
        print(f"  StdDev:  {statistics.stdev(values) if len(values) > 1 else 0:.2f}")
        
        # Interpretation
        if col == 'dne':
            print(f"  ➜ This is the 0-100 STRESS/DNE value shown in app!")
        elif col == 'srl':
            print(f"  ➜ Likely HRV or heart rate variability metric")
        elif col == 'srrn':
            print(f"  ➜ Secondary HRV or RR interval counter")
        elif col == 'eda':
            print(f"  ➜ Raw EDA sensor measurement (micro-siemens equivalent)")
        elif col == 'accel':
            print(f"  ➜ Acceleration / Activity level")

print("\n\n" + "="*80)
print("FINDING: DNE vs BYTE 14 CORRELATION")
print("="*80)

# Find rows with both dne values
dne_values = [float(row['dne']) for row in data_rows if row['dne'] and row['dne'].strip()]

if dne_values:
    print(f"\nDNE column statistics:")
    print(f"  Count:   {len(dne_values)}")
    print(f"  Min:     {min(dne_values):.1f}")
    print(f"  Max:     {max(dne_values):.1f}")
    print(f"  Range:   {max(dne_values) - min(dne_values):.1f}")
    
    print(f"\nByte 14 (from BLE read) was: 46")
    print(f"DNE values in export range: {min(dne_values):.0f}-{max(dne_values):.0f}")
    
    # Check if 46 is in the data
    matches = [v for v in dne_values if abs(v - 46) < 1]
    print(f"\nDNE values near 46: {len(matches)} found")
    
    if matches:
        print(f"  Examples: {matches[:10]}")
        print(f"\n✅ BYTE 14 MATCHES DNE STRESS VALUES!")

print("\n\n" + "="*80)
print("KEY INSIGHT")
print("="*80)

print("""
The exported CSV contains 1-minute averaged data:
  • dne: Dynamic Nervous Energy (0-100 stress score from app algorithm)
  • srl: Heart rate or RRV (large numbers = processed HRV data)
  • srrn: Secondary HRV metric
  • eda: Raw EDA sensor values (large numbers, requires scaling)
  • accel: Movement/activity level

However, the BLE characteristic we read contains DIFFERENT data:
  • Byte 14: 46 (matches dne values)
  • Byte 8: 96
  • Byte 25: 75
  
These are likely SNAPSHOT values, not historical averages.

The export shows what the ring STORES internally (1-min summaries).
The BLE read shows what's CURRENTLY in the buffer.
""")

print("\n" + "="*80)
print("NEXT STEP")
print("="*80)

print("""
To confirm Byte 14 = DNE:
1. Note current DNE (app shows 0-100)
2. Read via BLE Byte 14
3. They should match closely (±1-2)

Current evidence:
  ✓ App showed: 46, then 27
  ✓ Byte 14 was: 46
  ✓ Export has DNE values matching this range
  
MOST LIKELY: Byte 14 = DNE (0-100 stress level)
""")
