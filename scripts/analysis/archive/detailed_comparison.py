#!/usr/bin/env python3
"""
Side-by-side data comparison at same timestamp
"""
import pandas as pd

# Read app export
app_export = pd.read_csv('data/Exported Data/Nuanic 2026-02-27T08_48_38.217Z.csv')

# Read my captured data
my_capture = pd.read_csv('data/nuanic_logs/nuanic_2026-02-27_12-32-24.csv')

print("=" * 100)
print("SIDE-BY-SIDE COMPARISON: What does each dataset contain?")
print("=" * 100)

print("\n### APP EXPORT - Sample rows with ALL columns ###")
print(app_export[['time', 'dne', 'srl', 'srrn', 'eda', 'accel']].iloc[100:105].to_string())

print("\n\n### MY RAW CAPTURE - Sample rows with ALL columns ###")
print(my_capture[['timestamp', 'stress_raw', 'stress_percent']].head(3).to_string())
print("\nNote: Plus eda_hex (77 bytes) and full_packet_hex columns...")

print("\n\n" + "=" * 100)
print("DETAILED BREAKDOWN")
print("=" * 100)

print("\n┌─ APP EXPORT (Processed) ─────────────────────────────┐")
print("│ Timestamp: 2026-02-26T13:01:00.910Z                  │")
print("│ ✓ DNE: 33.0%         ← NORMALIZED STRESS             │")
print("│ ✓ SRL: 692393.0      ← Skin Resistance Level         │")
print("│ ✓ SRRN: 1.0          ← Resistance Rate (normalized)  │")
print("│ ✓ EDA: (value)       ← Processed electrodermal       │")
print("│ ✓ Accel: 0.030      ← Acceleration/motion           │")
print("│ Rate: ~1 sample/minute                               │")
print("│ Processed by Nuanic app                              │")
print("└──────────────────────────────────────────────────────┘")

print("\n┌─ MY RAW CAPTURE (Unprocessed) ──────────────────────┐")
print("│ Timestamp: 2026-02-27T12:32:29.766006                │")
print("│ ✓ stress_raw: 191         ← RAW BYTE (0-255)         │")
print("│ ✓ stress_percent: 74.9%   ← Simple conversion        │")
print("│ ✓ eda_hex: 4b0fa0df...    ← 77 raw bytes (hex)       │")
print("│ ✓ full_packet_hex: 4b17... ← Entire 92-byte packet  │")
print("│ Rate: ~1.1 samples/second                            │")
print("│ Direct from BLE packet, no processing                │")
print("└──────────────────────────────────────────────────────┘")

print("\n\n" + "=" * 100)
print("WHAT'S MISSING IN EACH?")
print("=" * 100)

print("\nAPP EXPORT doesn't have:")
print("  ✗ Raw stress byte (only processed DNE)")
print("  ✗ Individual EDA channel data (only aggregated EDA)")
print("  ✗ Full packet structure")
print("  ✗ High-frequency data (1 min intervals only)")

print("\nMY CAPTURE doesn't have:")
print("  ✗ DNE (processed stress)")
print("  ✗ SRL (skin resistance level)")
print("  ✗ SRRN (resistance rate)")
print("  ✗ Accel (acceleration/motion)")

print("\n\n" + "=" * 100)
print("TECHNICAL PIPELINE")
print("=" * 100)

print("""
Ring sends: 92-byte BLE packets at ~1.1 Hz
├─ Byte 0-13:   Packet header/metadata
├─ Byte 14:     STRESS (0-255)  ◄─── I read this
├─ Bytes 15-91: EDA (77 bytes)  ◄─── I read this
└─ Byte 92+:    Footer

    ↓

MY SCRIPT (Real-time):
├─ Extract byte 14 → stress_raw
├─ Convert: stress_percent = (stress_raw / 255) * 100
├─ Extract bytes 15-91 → eda_hex
└─ Save raw packet → full_packet_hex
Result: CSV with RAW VALUES at 1.1 Hz

    ↓ PARALLEL CAPTURE ↓

NUANIC APP (Background processing):
├─ Baseline calibration
├─ Temporal smoothing/filtering
├─ Stress normalization → DNE
├─ EDA processing → single SRL/SRRN values
├─ Motion detection → Accel
├─ Downsample to ~1 sample/minute
└─ Export CSV with PROCESSED VALUES
Result: CSV with NORMALIZED VALUES at 0.09 Hz
""")

print("\n" + "=" * 100)
print("CONCLUSION")
print("=" * 100)
print("\nYour Nuanic app = Professional signal processor")
print("My script = Raw data logger")
print("\nTogether = Complete picture of your stress")
print("=" * 100)
