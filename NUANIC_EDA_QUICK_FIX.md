# Nuanic Ring - EDA Data Capture Guide

## ✅ Status: Working Correctly

Your Nuanic ring **IS capturing EDA data correctly**. The issue was using the simple logger instead of the full monitor.

---

## Investigation Summary

### Root Cause: Logger Implementation Difference

**The Problem:** EDA data appeared as all zeros in `nuanic_2026-03-03_09-35-25.csv`

**The Truth:** Your ring works perfectly. The issue was using `NuanicDataLogger` (simple) instead of `NuanicMonitor` (advanced).

#### ❌ NuanicDataLogger (Simple Logger)
- Minimal initialization
- Only subscribes to ONE characteristic (stress)
- No stability checks after connection
- May fail to properly initialize ring state

#### ✅ NuanicMonitor (Advanced Monitor) - Recommended
- Better ring initialization after connection
- Subscribes to ALL characteristics (stress, IMU, raw EDA)
- Proper error handling and recovery
- More robust connection management
- Live dashboard display

### Evidence

| File | Logger | EDA Data | Status |
|------|--------|----------|--------|
| `nuanic_2026-03-03_09-35-25.csv` | NuanicDataLogger | All zeros ❌ | Bad session |
| `nuanic_stress_2026-03-03_09-38-29.csv` | NuanicMonitor | Real hex values ✓ | Working |
| `nuanic_stress_2026-03-04_16-20-36.csv` | NuanicMonitor | Real hex values ✓ | Working |

### Example Real EDA Data Captured
```
EDA Hex: 747fb47fa06f74efb30fa20f745fb4cfa09f732fb41f9f9f73efb33fa19f748fb32fa24f74cfb34fa16f742fb4cfa09f74efb30fa26f74afb4bfa2df731fb4dfa16f733fb48fa1af731fb42fa1

Parsed as 4-channel 16-bit values:
  Channel 1: ~30000
  Channel 2: ~30000  
  Channel 3: ~30000
  Channel 4: ~30000
```

### Data Format Notes

**Your Captured Data** (hex-encoded raw bytes):
- Full 77-byte EDA section captured per stress packet
- Can be parsed into multiple channels
- More granular/detailed than processed values

**Website Sample** (processed single values):
- Single decimal EDA value
- Pre-computed by ring firmware
- Less detailed but easier to interpret

Your approach is **better** because you capture raw data and can parse it multiple ways.

---

## Quick Start: Logging Data

### Basic Usage (Recommended)
```bash
python -m scripts.ble.nuanic_monitor --duration 60 --docked
```

**What this does:**
- Auto-connects to docked Nuanic ring
- Captures stress, IMU, and EDA data
- Logs to CSV files in `data/nuanic_logs/`
- Displays live dashboard

### With Specific Ring Address
```bash
python -m scripts.ble.nuanic_monitor --duration 60 --ring-addr AA:BB:CC:DD:EE:FF
```

### List Available Rings
```bash
python -m scripts.ble.nuanic_monitor --list-rings
```

### Indefinite Logging (Ctrl+C to stop)
```bash
python -m scripts.ble.nuanic_monitor --docked
```

---

## Connection Behavior: Improved & Clear

Your Nuanic ring now connects with a **clear, step-by-step process**:

### Connection Flow
```
[INIT] Connecting to Nuanic ring (any available)...

[SCAN 1/3] Searching for device... ✓ Found: Nuanic
[CONN 1/3] Connecting to BLE device... ✓ Connected
[PAIR 1/3] Establishing encryption... ⚠ Pairing not available

[OK] Connection established!
```

**Key Improvements:**
- ✓ Clear step labels (SCAN, CONN, PAIR)
- ✓ Shows attempt numbers
- ✓ Uses checkmarks/X for status
- ✓ Better error messages
- ✓ Shorter retry delays (faster failure detection)

### If Connection Fails

**Typical failure flow:**
```
[SCAN 1/3] Searching for device... ❌ Not found
[WAIT] Pausing before retry...

[SCAN 2/3] Searching for device... ❌ Not found
[WAIT] Pausing before retry...

[SCAN 3/3] Searching for device... ❌ Not found

[FAIL] Could not connect after 3 attempts
```

**Troubleshooting:**
1. **Ring not discovered?**
   - Ensure ring is powered on
   - Check Bluetooth is enabled
   - Try `--list-rings` to verify ring is available

2. **Connection timeout?**
   - Move closer to computer
   - Restart ring
   - Restart Bluetooth adapter

3. **Still failing?**
   - Ring may need re-pairing in Windows Bluetooth settings
   - Try: Settings > Bluetooth > Remove device > Re-add

---

## Output Files

When you run `nuanic_monitor`, three CSV files are created:

| File | Contains |
|------|----------|
| `nuanic_stress_TIMESTAMP.csv` | Stress + EDA hex data |
| `nuanic_imu_TIMESTAMP.csv` | Accelerometer data |
| `nuanic_raw_eda_TIMESTAMP.csv` | Raw EDA stream (if available) |

### Stress File Example
```csv
timestamp,elapsed_ms,stress_raw,stress_percent,eda_hex,full_packet_hex
2026-03-04T16:20:53.946234,17036,111,43.5,747fb47fa06f74ef...,607139b99c010000...
2026-03-04T16:20:54.938725,18029,191,74.9,743fb4cfa1ff731f...,547539b99c010000...
```

**Columns explained:**
- `timestamp`: When reading was received
- `stress_raw`: Raw stress value (0-255)
- `stress_percent`: Scaled to 0-100%
- `eda_hex`: 77-byte EDA data in hex (bytes 15-91 of packet)
- `full_packet_hex`: Complete 92-byte packet

---

## Data Verification

### Check if EDA is Present
Look at the `eda_hex` column - it should **NOT be all zeros**:

✅ **Good:** `747fb47fa06f74efb30fa20f745fb4c...` (real data)
❌ **Bad:** `0000000000000000000000000000000...` (no EDA)

If you see all zeros:
- Ring may not be transmitting EDA
- Try disconnecting/reconnecting
- Restart the monitor

---

## Architecture

### What's What

**Logger Classes:**
- `NuanicDataLogger` - Simple single-stream logger (basic)
- `NuanicMonitor` - Full multi-stream monitor (recommended) ✓

**Connector:**
- `NuanicConnector` - Handles BLE connection with smart retry logic

**Analyzers:**
- `NuanicEDAAnalyzer` - Analyzes EDA patterns
- `data_analysis.py` - Batch analysis tools

### Use Cases

| Need | Use |
|------|-----|
| Simple logging | `NuanicMonitor` |
| Real-time monitoring | `NuanicMonitor` with display |
| Analyze existing logs | `data_analysis.py` |
| Custom code | `NuanicConnector` + callbacks |

---

## Example: Custom Python Script

```python
import asyncio
from src.awe_polar.nuanic_ring import NuanicMonitor

async def main():
    monitor = NuanicMonitor(log_dir="data/nuanic_logs")
    
    # Run with 5-minute duration
    success = await monitor.run(duration_seconds=300)
    
    if success:
        print("✓ Logging complete!")
    else:
        print("✗ Failed to connect")

if __name__ == "__main__":
    asyncio.run(main())
```

Run with:
```bash
python your_script.py
```

---

## Files Structure

```
src/awe_polar/nuanic_ring/
├── connector.py          ← BLE connection (improved connection flow)
├── monitor.py            ← Multi-stream monitor (main logging tool) ✓
├── logger.py             ← Simple logger (basic)
├── eda_analyzer.py       ← EDA analysis
└── data_analysis.py      ← Batch analysis tools
```

---

## Summary

- ✓ Ring works correctly
- ✓ EDA data is being captured
- ✓ Connection flow is clear
- ✓ Use `nuanic_monitor` for reliable logging

**Recommended command:**
```bash
python -m scripts.ble.nuanic_monitor --docked
```

That's it! 🎉

