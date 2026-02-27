#!/usr/bin/env python3
"""
Deep analysis of 468f2717 characteristic structure.
Question: Is this PPG-derived? Is there HRV data here?
"""
import pandas as pd
import struct
import numpy as np

csv_file = "data/nuanic_logs/nuanic_highfreq_2026-02-27_12-46-30.csv"
df = pd.read_csv(csv_file)

print("=" * 80)
print("🔬 ANALYZING 468f2717 PHYSIOLOGICAL CHARACTERISTIC STRUCTURE")
print("=" * 80)
print()

stress_df = df[df['characteristic'].str.contains('468f2717')].copy()
print(f"Total packets: {len(stress_df)}\n")

# Get a few packets for detailed analysis
packets = []
for _, row in stress_df.iterrows():
    hex_data = row['data_hex']
    packets.append(bytes.fromhex(hex_data))

if len(packets) == 0:
    print("ERROR: No 468f2717 packets found!")
else:
    # Analyze packet structure
    packet_len = len(packets[0])
    print(f"📏 Packet size: {packet_len} bytes\n")
    
    print("=" * 80)
    print("BYTE-BY-BYTE ANALYSIS OF FIRST 3 PACKETS")
    print("=" * 80)
    print()
    
    for pkt_idx in range(min(3, len(packets))):
        pkt = packets[pkt_idx]
        print(f"Packet {pkt_idx + 1}:")
        print(f"  Full hex: {pkt.hex()}")
        print(f"  Raw bytes: {' '.join(f'{b:02x}' for b in pkt)}")
        print()
        
        # Byte-by-byte breakdown
        print(f"  Bytes 0-3:   {pkt[0:4].hex()}  (could be timestamp/index)")
        print(f"  Bytes 4-7:   {pkt[4:8].hex()}  (could be timestamp cont.)")
        print(f"  Bytes 8-11:  {pkt[8:12].hex()}  (could be metric/counter)")
        print(f"  Byte 12:     {pkt[12]:02x} ({pkt[12]})  (single value)")
        print(f"  Byte 13:     {pkt[13]:02x} ({pkt[13]})  (single value)")
        print(f"  Byte 14:     {pkt[14]:02x} ({pkt[14]})  ← STRESS (0-255)")
        print(f"  Bytes 15-91: {pkt[15:92].hex()[:40]}... (77 bytes)")
        print()
    
    # Analyze the 77 "EDA/PPG" bytes
    print("=" * 80)
    print("🔍 ANALYZING BYTES 15-91 (77 bytes) - POSSIBLE PPG/HRV DATA")
    print("=" * 80)
    print()
    
    # Extract these 77 bytes from all packets
    eda_blocks = [pkt[15:92] for pkt in packets]
    
    print(f"Total 77-byte blocks: {len(eda_blocks)}")
    print()
    
    # First block detailed analysis
    first_block = eda_blocks[0]
    print("FIRST 77-byte block analysis:")
    print()
    
    # Try different interpretations
    print("1️⃣  As 8-bit uint8 values (77 raw samples):")
    u8_vals = list(first_block)
    print(f"   Range: {min(u8_vals)} - {max(u8_vals)}")
    print(f"   Mean: {np.mean(u8_vals):.1f}")
    print(f"   StdDev: {np.std(u8_vals):.1f}")
    print(f"   First 10 values: {u8_vals[:10]}")
    print()
    
    print("2️⃣  As 16-bit uint16 values (38-39 values):")
    u16_vals = []
    for i in range(0, len(first_block)-1, 2):
        val = struct.unpack('<H', first_block[i:i+2])[0]
        u16_vals.append(val)
    if u16_vals:
        print(f"   Count: {len(u16_vals)} values")
        print(f"   Range: {min(u16_vals)} - {max(u16_vals)}")
        print(f"   Mean: {np.mean(u16_vals):.1f}")
        print(f"   StdDev: {np.std(u16_vals):.1f}")
        print(f"   First 10 values: {u16_vals[:10]}")
    print()
    
    print("3️⃣  As 16-bit signed int16 values (accelerometer-like):")
    i16_vals = []
    for i in range(0, len(first_block)-1, 2):
        val = struct.unpack('<h', first_block[i:i+2])[0]
        i16_vals.append(val)
    if i16_vals:
        print(f"   Count: {len(i16_vals)} values")
        print(f"   Range: {min(i16_vals)} - {max(i16_vals)}")
        print(f"   Mean: {np.mean(i16_vals):.1f}")
        print(f"   StdDev: {np.std(i16_vals):.1f}")
        print(f"   First 10 values: {i16_vals[:10]}")
    print()
    
    print("4️⃣  As 32-bit float values (19-20 values):")
    f32_vals = []
    for i in range(0, len(first_block)-3, 4):
        try:
            val = struct.unpack('<f', first_block[i:i+4])[0]
            f32_vals.append(val)
        except:
            break
    if f32_vals:
        print(f"   Count: {len(f32_vals)} values")
        print(f"   Range: {min(f32_vals):.4f} - {max(f32_vals):.4f}")
        print(f"   Mean: {np.mean(f32_vals):.4f}")
        print(f"   StdDev: {np.std(f32_vals):.4f}")
        print(f"   First 10 values: {[f'{v:.4f}' for v in f32_vals[:10]]}")
    print()
    
    # Statistical analysis across all packets
    print("=" * 80)
    print("📊 STATISTICAL ANALYSIS ACROSS ALL PACKETS")
    print("=" * 80)
    print()
    
    all_u8 = []
    all_u16 = []
    for block in eda_blocks:
        all_u8.extend(list(block))
        for i in range(0, len(block)-1, 2):
            val = struct.unpack('<H', block[i:i+2])[0]
            all_u16.append(val)
    
    print(f"As uint8 (all packets):")
    print(f"  Total samples: {len(all_u8)}")
    print(f"  Range: {min(all_u8)} - {max(all_u8)}")
    print(f"  Mean: {np.mean(all_u8):.1f}, StdDev: {np.std(all_u8):.1f}")
    print()
    
    print(f"As uint16 (all packets):")
    print(f"  Total samples: {len(all_u16)}")
    print(f"  Range: {min(all_u16)} - {max(all_u16)}")
    print(f"  Mean: {np.mean(all_u16):.1f}, StdDev: {np.std(all_u16):.1f}")
    print()
    
    # Check for PPG-like waveform patterns
    print("=" * 80)
    print("🫀 CHECKING FOR PPG WAVEFORM PATTERNS")
    print("=" * 80)
    print()
    
    print("PPG characteristics:")
    print("  • High-frequency data (usually 25-100 Hz)")
    print("  • Shows pulsatile AC waveform (oscillations between heart beats)")
    print("  • Range typically 0-1023 or 0-4095 for 10-12bit signals")
    print()
    
    if all_u8:
        print(f"77 uint8 values per packet @ 1.12 Hz ~= PPG at {77*1.12:.0f} Hz?")
        print(f"  → Too low for typical PPG (would need 25+ Hz)")
    
    if all_u16:
        print(f"38 uint16 values per packet @ 1.12 Hz ~= PPG at {38*1.12:.0f} Hz?")
        print(f"  → Still quite low for PPG")
    print()
    
    # Check if this could be HRV (RR-intervals or similar)
    print("=" * 80)
    print("❤️  CHECKING FOR HRV PATTERNS")
    print("=" * 80)
    print()
    
    print("HRV characteristics:")
    print("  • Lower frequency than PPG (typically 0.5-2 Hz)")
    print("  • RR-intervals: 0.5-2 sec = 500-2000 ms between heartbeats")
    print("  • RMSSD, pNN50: standard HRV metrics")
    print()
    
    if all_u16:
        print(f"uint16 range: {min(all_u16)} - {max(all_u16)}")
        print(f"  → If these are RR-intervals in ms (500-1200 ms normal)")
        print(f"  → {min(all_u16)} ms = {min(all_u16)/1000:.2f} sec")
        print(f"  → {max(all_u16)} ms = {max(all_u16)/1000:.2f} sec")
        
        # Check if values are in RR-interval range
        rr_range = [v for v in all_u16 if 400 < v < 1500]
        print(f"  → Values in typical RR-interval range (400-1500 ms): {len(rr_range)}/{len(all_u16)}")
    print()
    
    # Summary
    print("=" * 80)
    print("🎯 SUMMARY & QUESTIONS")
    print("=" * 80)
    print()
    print("The 468f2717 characteristic contains:")
    print(f"  • Byte 14: Stress metric (0-255) → {packets[0][14]} in first packet")
    print(f"  • Bytes 15-91: 77 bytes of unknown physiological data")
    print()
    print("Possible interpretations:")
    print(f"  1. EDA (Electrodermal Activity) waveform - 77 uint8 samples")
    print(f"  2. PPG (Photoplethysmography) - 38 uint16 samples (too low frequency)")
    print(f"  3. HRV-derived metrics - various statistical measures")
    print(f"  4. Mixed: Stress + EDA + other physiology")
    print()
    print("User's question: 'Stress: PPG-derived. So there is HRV here too?'")
    print("  → Need to know if these 77 bytes contain raw PPG waveform")
    print("  → Or HRV metrics derived from PPG")
    print("  → Or EDA data as labeled")
    print()
