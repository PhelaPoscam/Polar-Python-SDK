# Nuanic EDA Data Capture Analysis

## Issue Summary

Your code is **NOT capturing EDA data correctly**. The EDA section of packets (bytes 15-91) consists entirely of zeros.

## Evidence

### Website Sample (Reference Data)
```
address,time_unix,time,dne,srl,srrn,eda
RP01006,1710921857.700000,2024-03-20 08:04:17.7+00,\N,\N,\N,691471
RP01006,1710921858.033000,2024-03-20 08:04:18.033+00,\N,\N,\N,691471
```

**EDA Column:** Real decimal values (691471, etc.)

### Your Generated Logs
```csv
timestamp,stress_raw,stress_percent,eda_hex,full_packet_hex
2026-03-03T09:35:25.956993,50,19.6,00000000000000...,0000000000000000000000000000320000000000...
```

**EDA Hex Column:** All zeros (00000000000000...)

## Root Cause Analysis

### Packet Structure Breakdown

Your 92-byte packets show this pattern:
```
Position (hex) | Position (byte) | Data
0-27           | 0-13            | Header/unknown = 0x00...
28-29          | 14              | Stress value = 0x32 (50 decimal) ✓
30-181         | 15-90           | EDA section = 0x00... (ALL ZEROS) ✗
```

### Why Bytes 15-91 Are Empty

**Most likely explanation:** EDA data is NOT transmitted on the `STRESS_CHARACTERISTIC`.

Your code defines but never uses: `RAW_EDA_CHARACTERISTIC = "3c180fcc-bfec-4b7c-8e52-1a37f123e449"`

The Nuanic ring likely sends:
- **STRESS_CHARACTERISTIC** → Stress value only (byte 14)
- **RAW_EDA_CHARACTERISTIC** → Actual EDA values (separate stream)

## Solutions

### ✅ Solution 1: Run Diagnostics (RECOMMENDED)

First, determine where the EDA data actually comes from:

```bash
python -m scripts.ble.diagnose_nuanic_characteristics --duration 15
```

This will show:
- Which characteristics return data
- Which has non-zero values
- Packet structure for each

### ✅ Solution 2: Use Dual-Stream Logger

New file created: `src/awe_polar/nuanic_ring/logger_dual_stream.py`

This logger:
- Subscribes to both `STRESS_CHARACTERISTIC` and `RAW_EDA_CHARACTERISTIC`
- Logs stress values from stress characteristic
- Attempts to parse/log EDA from wherever it's available
- Adds new `eda_decimal` column for parsed values

Usage:
```python
from awe_polar.nuanic_ring.logger_dual_stream import NuanicDataLoggerDualStream
import asyncio

logger = NuanicDataLoggerDualStream()
await logger.start_logging(duration_seconds=60)
```

### ✅ Solution 3: Compare with Website Sample Format

The website sample has columns: `address, time_unix, time, dne, srl, srrn, eda`

Your format has: `timestamp, stress_raw, stress_percent, eda_hex, full_packet_hex`

**Mapping:**
- `dne` might correspond to stress
- `eda` is the single decimal value you're missing

The website format appears simpler - one EDA value per row, not hex-encoded bytes.

## Next Steps

1. **Run the diagnostic script** to identify where EDA enters the device
2. **Compare characteristics:**
   - Stress characteristic (current)
   - Raw EDA characteristic (defined but unused)
   - IMU characteristic (also available)
3. **Update subscription logic** based on diagnostic results
4. **Verify data flow** with actual EDA values appearing in logs

## Files Created

- `scripts/ble/diagnose_nuanic_characteristics.py` - Diagnostic tool
- `src/awe_polar/nuanic_ring/logger_dual_stream.py` - Dual-stream logger

## Expected Outcome

Once you run diagnostics and update the subscription:
- EDA column will show real values (not zeros)
- Format should match or closely resemble the website sample
- You'll have both stress and EDA metrics for analysis
