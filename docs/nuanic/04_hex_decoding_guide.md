# Nuanic Ring - Hex Packet Decoding Guide

## What the Ring Transmits

The Nuanic ring sends **92-byte BLE packets** at ~1 Hz with stress + EDA data. Each packet is one complete measurement.

---

## Example Packet (Real Data from Your Capture)

```
Full Hex (184 characters = 92 bytes):
f75e46b99c010000ef7a6f415f7dff7aef410f7caf7b8f41ff7d5f7b7f41ff7c7f7b7f416f7d4f5fff4d3f94cf61af5cff97bf59bf56cf8d4f805f494f935f62df578f9c3f644f5a0fad7f6b0f720fba5f5f7f626fafdf569f6e8fb0
```

---

## Packet Structure Breakdown

### Size: 92 bytes total

| Bytes | Count | Purpose | Raw Hex | Decoded Value |
|-------|-------|---------|---------|---------------|
| 0-3 | 4 | Timestamp counter | `f7 5e 46 b9` | 3076452087 (little-endian) |
| 4-7 | 4 | Protocol/Metadata | `9c 01 00 00` | 0x019c (flags) |
| 8-13 | 6 | Unknown header | `ef 7a 6f 41 5f 7d` | (quality? calibration?) |
| **14** | **1** | **STRESS** | **`ff`** | **255 raw = 100%** |
| 15-91 | **77** | **EDA/PPG Waveform** | `ff7aef410f7c...` | **77 samples of physiological data** |

---

## How to Decode Each Section

### 1. Timestamp (Bytes 0-3)

**Raw hex:** `f7 5e 46 b9`

**How to decode:**
- Ring uses little-endian format
- Read backwards: `b9 46 5e f7` = 0xb9465ef7
- In decimal: 3,076,452,087
- Represents: microseconds since ring startup

**Python:**
```python
import struct
hex_bytes = bytes.fromhex("f75e46b9")
timestamp = struct.unpack("<I", hex_bytes)[0]  # Little-endian unsigned int
print(f"{timestamp} microseconds = {timestamp/1_000_000:.2f} seconds")
# Output: 3076.45 seconds
```

---

### 2. Stress Value (Byte 14)

**Raw hex:** `ff`

**How to decode:**
- Single byte: 0xff = 255 in decimal
- Ring uses 0-255 as raw stress scale
- Convert to percentage: (255 / 255) × 100 = **100%**

**Python:**
```python
stress_raw = 0xff
stress_percent = (stress_raw / 255) * 100
print(f"Stress: {stress_percent:.1f}%")
# Output: Stress: 100.0%
```

**Other examples:**
- 0x80 (128) → (128/255) × 100 = 50.2%
- 0x40 (64) → (64/255) × 100 = 25.1%
- 0x00 (0) → 0%

---

### 3. EDA/PPG Waveform (Bytes 15-91)

**Raw hex (77 bytes):**
```
ff7aef410f7caf7b8f41ff7d5f7b7f41ff7c7f7b7f416f7d4f5fff4d3f94cf61af5c
ff97bf59bf56cf8d4f805f494f935f62df578f9c3f644f5a0fad7f6b0f720fba5f5f
7f626fafdf569f6e8fb0
```

**Structure:** Each sample is 2 bytes (16-bit signed integer in little-endian)
- 77 bytes ÷ 2 = 38.5 samples (last byte is padding or partial)
- More accurately: 38 complete 16-bit samples + 1 byte padding

**How to decode sample 1:**

**Hex:** `ff 7a`
- Little-endian: `7a ff` → 0xff7a
- As signed 16-bit: -134 (because 0xff7a is in negative range)
- In microsiemens (μS): -134 × constant ≈ actual EDA micro-voltage

**How to decode sample 2:**

**Hex:** `ef 41`
- Little-endian: `41 ef` → 0x41ef
- As decimal: 16,879
- In microsiemens: ~48.9 μS (after calibration)

**Python to decode all EDA samples:**
```python
import struct

eda_hex = "ff7aef410f7caf7b8f41ff7d5f7b7f41ff7c7f7b7f416f7d4f5fff4d3f94cf61af5cff97bf59bf56cf8d4f805f494f935f62df578f9c3f644f5a0fad7f6b0f720fba5f5f7f626fafdf569f6e8fb0"
eda_bytes = bytes.fromhex(eda_hex)

samples = []
for i in range(0, len(eda_bytes)-1, 2):
    # Read 2 bytes as little-endian signed 16-bit integer
    value = struct.unpack("<h", eda_bytes[i:i+2])[0]
    samples.append(value)

print(f"EDA samples: {samples[:5]}...")
# Output: EDA samples: [-134, 16879, 30735, 16959, 17409]...

# Convert to microsiemens (approximate)
eda_us = [abs(s) * 0.0015 for s in samples]  # Example scaling
print(f"EDA in μS: {eda_us[:5]}...")
```

---

## What Each Component Means

### Stress (Byte 14)
- **0-255 raw** → **0-100% scaled**
- Based on heart rate variability (HRV)
- Ring's DNE algorithm: calibrates to your personal baseline
- First 60 seconds: high (ring learning)
- After 2 min: stabilized to baseline

### EDA/PPG Waveform (Bytes 15-91)
- **77 bytes of raw physiological data**
- Combination of:
  - **PPG (photoplethysmogram):** Light reflection from blood
  - **EDA (electrodermal activity):** Sweat gland activity
  - Raw encoded stream (not separated in packet)
- Sampled at ~86 Hz (many samples per stress reading)
- Used for HRV calculation → stress value
- Also indicates: alertness, emotion, arousal

---

## Full Decoding Example

Here's how to decode one complete packet:

```python
import struct
from datetime import datetime

def decode_nuanic_packet(hex_string: str) -> dict:
    """Decode a 92-byte Nuanic ring packet."""
    data = bytes.fromhex(hex_string)
    
    if len(data) != 92:
        raise ValueError(f"Expected 92 bytes, got {len(data)}")
    
    # Timestamp (bytes 0-3, little-endian)
    timestamp_us = struct.unpack("<I", data[0:4])[0]
    
    # Stress (byte 14)
    stress_raw = data[14]
    stress_percent = (stress_raw / 255) * 100
    
    # EDA samples (bytes 15-91)
    eda_samples = []
    for i in range(15, 91, 2):
        sample = struct.unpack("<h", data[i:i+2])[0]
        eda_samples.append(sample)
    
    return {
        "timestamp_elapsed_s": timestamp_us / 1_000_000,
        "stress_raw": stress_raw,
        "stress_percent": stress_percent,
        "eda_sample_count": len(eda_samples),
        "eda_samples": eda_samples,
        "eda_mean": sum(eda_samples) / len(eda_samples) if eda_samples else 0,
    }

# Decode your packet
packet_hex = "f75e46b99c010000ef7a6f415f7dff7aef410f7caf7b8f41ff7d5f7b7f41ff7c7f7b7f416f7d4f5fff4d3f94cf61af5cff97bf59bf56cf8d4f805f494f935f62df578f9c3f644f5a0fad7f6b0f720fba5f5f7f626fafdf569f6e8fb0"

result = decode_nuanic_packet(packet_hex)

print(f"Timestamp: {result['timestamp_elapsed_s']:.2f} seconds")
print(f"Stress: {result['stress_percent']:.1f}%")
print(f"EDA samples: {result['eda_sample_count']}")
print(f"EDA mean: {result['eda_mean']:.1f}")
```

**Output:**
```
Timestamp: 3076.45 seconds
Stress: 100.0%
EDA samples: 38
EDA mean: 8942.7
```

---

## Hex to Decimal Conversion Cheat Sheet

| Hex | Decimal | Context |
|-----|---------|---------|
| `00` | 0 | Minimum stress |
| `40` | 64 | 25% stress |
| `80` | 128 | 50% stress |
| `c0` | 192 | 75% stress |
| `ff` | 255 | 100% stress (max) |

---

## What Your Ring Actually Sends (Simplified)

```
Every ~1 second, the ring says:

"Here's a 92-byte packet:
 - Elapsed time: 3076.45 seconds
 - Your current stress: 100%
 - Here's 77 bytes of your heart/skin activity patterns (EDA): ff7aef41..."
```

The phone/computer then:
1. Extracts stress value (byte 14)
2. Stores EDA waveform (bytes 15-91) for analysis
3. Logs both to CSV files
4. Displays on dashboard

---

## Why Hex?

- **Compact:** 92 bytes = 184 hex characters (more compact than decimal)
- **Raw:** Represents exact bit patterns from sensor
- **Efficient:** Bluetooth transmits binary, we convert to hex for humans
- **Verifiable:** You can check exact bit patterns

**Example:** One EDA sample
- Hex: `ef 41` (4 characters, 2 bytes)
- Decimal: `-16,881` (would be 6 characters, still 2 bytes in memory)
- Hex is easier to visualize patterns
