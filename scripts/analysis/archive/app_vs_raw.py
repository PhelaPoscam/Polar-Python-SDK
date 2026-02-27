#!/usr/bin/env python3
"""
Deep analysis: What is DNE? How does app processing differ from raw capture?
"""
import pandas as pd
import numpy as np

# Read app export
app_export = pd.read_csv('data/Exported Data/Nuanic 2026-02-27T08_48_38.217Z.csv')

# Read my captured data
my_capture = pd.read_csv('data/nuanic_logs/nuanic_2026-02-27_12-32-24.csv')

print("=" * 80)
print("UNDERSTANDING APP PROCESSING vs RAW DATA CAPTURE")
print("=" * 80)

print('\n=== WHAT IS DNE? ===')
print('DNE = Daily Normalized Energy (Nuanic app term)')
print('  - Represents stress/arousal level as percentage (0-100%)')
print('  - Processed/normalized value from raw packet data')
print('  - One value per time sample in app export')
print('  - Range: 28% to 100% in your data')

print('\n=== DO I HAVE DNE? ===')
print('My capture has "stress_percent":')
print('  - This is the RAW stress byte converted to percentage')
print('  - Byte 14 from 92-byte packet: 0-255 → 0-100%')
print('  - NOT the same as DNE (which is app-processed)')
print('  - Direct reading, not normalized/aggregated')

print('\n=== APP EXPORT COLUMNS ===')
print('device  - Ring ID (NR05126)')
print('time    - Timestamp')
print('dne     - Daily Normalized Energy (MAIN STRESS METRIC)')
print('srl     - Skin Resistance Level (raw from EDA electrode)')
print('srrn    - Skin Resistance Rate of Normalized (change indicator)')
print('eda     - Electrodermal Activity (decimal value)')
print('accel   - Acceleration (motion sensor)')

print('\n=== MY CAPTURE COLUMNS ===')
print('timestamp        - ISO timestamp')
print('stress_raw       - Raw byte 14 (0-255)')
print('stress_percent   - Converted stress (0-100%)')
print('eda_hex          - Raw EDA bytes 15-91 (77 bytes in hex)')
print('full_packet_hex  - Full 92-byte packet (hex)')

print('\n' + '=' * 80)
print('KEY DIFFERENCES')
print('=' * 80)

print('\n1. STRESS METRIC:')
print('   App (DNE):')
print('     - Normalized/processed stress value')
print('     - May include baseline subtraction, filtering, temporal smoothing')
print('     - Range: ', f'{app_export["dne"].min():.1f}% - {app_export["dne"].max():.1f}%')
print('   My capture (stress_percent):')
print('     - Raw byte 14 simply scaled: (byte/255)*100')
print('     - No processing, direct from packet')
print('     - Range: ', f'{my_capture["stress_percent"].min():.1f}% - {my_capture["stress_percent"].max():.1f}%')

print('\n2. SAMPLING RATE:')
app_samples = len(app_export)
time_span = pd.to_datetime(app_export['time'].iloc[-1]) - pd.to_datetime(app_export['time'].iloc[0])
hours = time_span.total_seconds() / 3600
app_hz = len(app_export) / time_span.total_seconds()

print(f'   App export:')
print(f'     - {app_samples:,} samples over {hours:.1f} hours')
print(f'     - Equivalent rate: {app_hz:.2f} Hz (roughly 1 sample per minute)')
print(f'   My capture:')
print(f'     - {len(my_capture)} samples in 30 seconds')
print(f'     - Rate: {len(my_capture)/30:.2f} Hz (1 sample per ~0.9 seconds)')

print('\n3. DATA PROCESSING:')
print('   App export appears to:')
print('     - Aggregate/downsample raw data to ~1 sample/minute')
print('     - Process stress byte into DNE (normalized energy)')
print('     - Extract EDA into single decimal value')
print('     - Calculate acceleration')
print('   My capture:')
print('     - Raw packet data, minimal processing')
print('     - Direct byte extraction: stress = byte 14, EDA = bytes 15-91')
print('     - No temporal smoothing or aggregation')

print('\n4. EDA DATA:')
print('   App export:')
print('     - Single decimal EDA value per sample')
print('     - Range: 286K to 2.1B (processed/scaled)')
print('   My capture:')
print('     - 77 raw bytes (hex): individual electrode readings')
print('     - What the app would process to create its EDA value')

print('\n5. DATA LOSS vs DATA DEPTH:')
print('   App export:')
print('     - Processed/cleaner data (good for trends)')
print('     - But loses high-frequency details')
print('     - ~1 sample/minute')
print('   My capture:')
print('     - All raw details preserved')
print('     - Can see rapid fluctuations')
print('     - ~1.1 Hz sampling')

print('\n' + '=' * 80)
print('INTERPRETATION')
print('=' * 80)

print('\nThe APP is a signal processor:')
print('  ┌─ Raw 92-byte BLE packets (1.1 Hz)')
print('  │  Byte 14 = stress, Bytes 15-91 = EDA, etc.')
print('  │')
print('  ├─ Processing:')
print('  │  • Baseline normalization')
print('  │  • Temporal filtering/smoothing')
print('  │  • Stress scaling → DNE (Daily Normalized Energy)')
print('  │  • EDA processing → single value')
print('  │')
print('  └─ Output: CSV with DNE, SRL, SRRN, EDA, Accel')
print('     (1 sample/minute, processed & aggregated)')

print('\nMy CAPTURE is raw data:')
print('  Direct packet → CSV')
print('  No processing, timestamps, hex encoding')
print('  ~1.1 Hz resolution (all details preserved)')

print('\n' + '=' * 80)
print('WHICH IS BETTER?')
print('=' * 80)

print('\nAPP EXPORT (DNE):')
print('  ✓ Easier to interpret')
print('  ✓ Normalized values easier for ML')
print('  ✓ Good for long-term trends')
print('  ✗ Loses high-frequency details')
print('  ✗ Can\'t reverse-engineer the processing')

print('\nMY CAPTURE (Raw packets):')
print('  ✓ Complete raw data preserved')
print('  ✓ Can analyze in any way you want')
print('  ✓ High temporal resolution (1.1 Hz)')
print('  ✗ Requires your own processing')
print('  ✗ Need to normalize/smooth yourself')

print('\n' + '=' * 80)
print('RECOMMENDATION')
print('=' * 80)
print('\nBEST APPROACH: Use BOTH')
print('  1. App export (DNE) = ground truth from official app')
print('  2. My capture (raw) = additional high-res details')
print('  3. Combine them for complete picture:')
print('     - Use DNE for stress state')
print('     - Use raw packets for real-time responsiveness')
print('     - Use EDA for deeper physiological analysis')
