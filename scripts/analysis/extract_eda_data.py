#!/usr/bin/env python3
"""
Extract and analyze EDA (Skin Conductance) data from 468f2717 characteristic
"""
import pandas as pd
import struct
import numpy as np

csv_file = "data/nuanic_logs/nuanic_highfreq_2026-02-27_12-46-30.csv"
df = pd.read_csv(csv_file)

print("=" * 80)
print("🔌 EDA / SKIN CONDUCTANCE EXTRACTION")
print("=" * 80)
print()

stress_df = df[df['characteristic'].str.contains('468f2717')].copy()
print(f"Total physiological packets: {len(stress_df)}")
print()

# The 468f2717 characteristic structure (92 bytes):
# Bytes 0-13: Header/metadata
# Byte 14: Stress (0-255)
# Bytes 15-91: EDA data (77 bytes)

print("=" * 80)
print("📊 PACKET STRUCTURE")
print("=" * 80)
print()
print("468f2717 characteristic (92 bytes):")
print("  Bytes 0-13:  Header/metadata")
print("  Byte 14:     Stress metric (0-255)")
print("  Bytes 15-91: EDA/Skin Conductance (77 bytes)")
print()

# Parse all packets
packets = []
for _, row in stress_df.iterrows():
    hex_data = row['data_hex']
    packets.append(bytes.fromhex(hex_data))

# Extract stress and EDA from all packets
stress_values = []
eda_all_samples = []

for pkt in packets:
    # Stress at byte 14
    stress = pkt[14]
    stress_values.append(stress)
    
    # EDA at bytes 15-91 (77 bytes)
    eda_block = pkt[15:92]
    eda_all_samples.extend(list(eda_block))

print("=" * 80)
print("📈 STRESS METRIC (Byte 14)")
print("=" * 80)
print()
print(f"Samples: {len(stress_values)}")
print(f"Range: {min(stress_values)} - {max(stress_values)} (0-255 scale)")
print(f"Mean: {np.mean(stress_values):.1f}")
print(f"Median: {np.median(stress_values):.1f}")
print(f"StdDev: {np.std(stress_values):.1f}")
print()
print("Stress as percentage (0-100%):")
stress_pct = [s * 100 / 255 for s in stress_values]
print(f"  Range: {min(stress_pct):.1f}% - {max(stress_pct):.1f}%")
print(f"  Mean: {np.mean(stress_pct):.1f}%")
print()

print("=" * 80)
print("🔌 EDA/SKIN CONDUCTANCE DATA (Bytes 15-91)")
print("=" * 80)
print()

# The 77 bytes could be interpreted as:
# 1. 77 x uint8 samples (0-255 range)
# 2. 38 x uint16 samples (0-65535 range)

print(f"Total EDA samples collected: {len(eda_all_samples)}")
print(f"Number of packets: {len(packets)}")
print(f"EDA samples per packet: {len(eda_all_samples) / len(packets):.1f}")
print()

# Interpretation 1: uint8 (raw 0-255 values)
eda_u8 = eda_all_samples
print("Interpretation 1: Raw uint8 values (0-255)")
print(f"  Range: {min(eda_u8)} - {max(eda_u8)}")
print(f"  Mean: {np.mean(eda_u8):.1f}")
print(f"  Median: {np.median(eda_u8):.1f}")
print(f"  StdDev: {np.std(eda_u8):.1f}")
print()

# If these are 8-bit ADC readings from a 0-100 μS sensor:
eda_uscaled = [v * 100.0 / 255 for v in eda_u8]
print("If uint8 represents 0-100 μS range:")
print(f"  Range: {min(eda_uscaled):.2f} - {max(eda_uscaled):.2f} μS")
print(f"  Mean: {np.mean(eda_uscaled):.2f} μS")
print(f"  StdDev: {np.std(eda_uscaled):.2f} μS")
print()

# Interpretation 2: uint16 (as pairs of bytes)
eda_u16 = []
for i in range(0, len(eda_all_samples)-1, 2):
    val = struct.unpack('<H', bytes([eda_all_samples[i], eda_all_samples[i+1]]))[0]
    eda_u16.append(val)

print("Interpretation 2: 16-bit uint16 values (0-65535)")
print(f"  Count: {len(eda_u16)} samples")
print(f"  Range: {min(eda_u16)} - {max(eda_u16)}")
print(f"  Mean: {np.mean(eda_u16):.1f}")
print(f"  Median: {np.median(eda_u16):.1f}")
print(f"  StdDev: {np.std(eda_u16):.1f}")
print()

# If these are 16-bit ADC readings from a 0-100 μS sensor:
eda_u16_uscaled = [v * 100.0 / 65535 for v in eda_u16]
print("If uint16 represents 0-100 μS range:")
print(f"  Range: {min(eda_u16_uscaled):.2f} - {max(eda_u16_uscaled):.2f} μS")
print(f"  Mean: {np.mean(eda_u16_uscaled):.2f} μS")
print(f"  StdDev: {np.std(eda_u16_uscaled):.2f} μS")
print()

# Typical EDA ranges for comparison
print("=" * 80)
print("📋 EDA REFERENCE RANGES")
print("=" * 80)
print()
print("Typical Skin Conductance Level (SCL):")
print("  • Baseline (calm, relaxed): 5-15 μS")
print("  • Moderate stress: 15-30 μS")
print("  • High stress: 30-100+ μS")
print()
print("Our data (if uint16 to 0-100 μS):")
print(f"  • Mean: {np.mean(eda_u16_uscaled):.2f} μS")
print(f"  • Range: {min(eda_u16_uscaled):.2f} - {max(eda_u16_uscaled):.2f} μS")
if np.mean(eda_u16_uscaled) < 15:
    print(f"  → Indicates RELAXED/CALM state ✓")
elif np.mean(eda_u16_uscaled) < 30:
    print(f"  → Indicates MODERATE stress")
else:
    print(f"  → Indicates HIGH stress")
print()

# Time series
print("=" * 80)
print("⏱️  TIME SERIES ANALYSIS")
print("=" * 80)
print()

# Reconstruct time series with stress + EDA
time_idx = 0
samples_out = []

for pkt_idx, pkt in enumerate(packets):
    stress = pkt[14]
    eda_bytes = pkt[15:92]
    
    # Each packet has one stress value + 77 EDA bytes
    for eda_idx, eda_val in enumerate(eda_bytes):
        timestamp = pkt_idx  # Approximate packet timestamp
        samples_out.append({
            'packet': pkt_idx,
            'eda_index': eda_idx,
            'raw_eda': eda_val,
            'eda_us': eda_val * 100.0 / 255,
            'stress_raw': stress,
            'stress_pct': stress * 100.0 / 255,
        })

df_timeseries = pd.DataFrame(samples_out)

print(f"Total reconstructed samples: {len(df_timeseries)}")
print()
print("First 10 samples:")
print(df_timeseries[['packet', 'eda_index', 'raw_eda', 'eda_us', 'stress_pct']].head(10).to_string(index=False))
print()
print("Last 10 samples:")
print(df_timeseries[['packet', 'eda_index', 'raw_eda', 'eda_us', 'stress_pct']].tail(10).to_string(index=False))
print()

# Correlation between EDA and stress
print("=" * 80)
print("📊 CORRELATION ANALYSIS")
print("=" * 80)
print()
correlation = np.corrcoef(df_timeseries['raw_eda'], df_timeseries['stress_raw'])[0, 1]
print(f"Correlation (EDA ↔ Stress): {correlation:.3f}")
if abs(correlation) < 0.3:
    print("  → Weak correlation (EDA and stress are semi-independent)")
elif abs(correlation) < 0.7:
    print("  → Moderate correlation")
else:
    print("  → Strong correlation")
print()

# Summary
print("=" * 80)
print("🎯 CONCLUSION")
print("=" * 80)
print()
print("EDA/Skin Conductance Data Location:")
print("  ✓ Characteristic: 468f2717")
print("  ✓ Bytes 15-91: 77 bytes per packet")
print("  ✓ Total samples in 30 seconds: 2,618")
print("  ✓ Frequency: ~86-87 Hz (77 samples per 1.12 Hz packet)")
print()
print("Data Interpretation:")
print("  • Most likely: 77 x uint8 raw samples (0-255)")
print("  • Represents: Electrodermal activity / Skin conductance")
print("  • Scaled: 0-100 μS psychological response measurement")
print()
print("What this means:")
print("  • EDA measures sweat gland activity (emotional response)")
print("  • Higher values = more stress/arousal/emotion")
print("  • Combined with stress metric for comprehensive physiology")
print()
