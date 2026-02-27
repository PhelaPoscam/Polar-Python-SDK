# Nuanic Ring Integration - Project Organization

## Overview
Complete rewrite of Nuanic ring integration into production-ready modules with data logging and EDA analysis.

**Status:** ✅ Ready for testing and real-world data capture

**Key Achievement:** Successfully captured Nuanic ring stress data and identified EDA data structure

## What Was Created

### 1. Production Modules (`src/awe_polar/nuanic_ring/`)
Proper Python package structure for Nuanic integration:

- **`connector.py`:** BLE connection management
  - Auto-discovery by device name
  - Automatic pairing/authentication
  - Retry logic for reliability
  
- **`monitor.py`:** Real-time stress monitoring
  - Subscribes to stress notifications
  - Decodes stress values (Byte 14 → 0-100%)
  - Extracts EDA raw data (Bytes 15-91)

- **`logger.py`:** CSV data logging
  - Timestamped CSV output
  - Logs: timestamp, stress_raw, stress_percent, eda_hex, full_packet_hex
  - Automatic file creation in data/nuanic_logs/

- **`eda_analyzer.py`:** EDA analysis engine
  - Baseline (tonic) component tracking
  - Peak detection
  - Phasic (dynamic) analysis
  - Session statistics and interpretation

- **`examples.py`:** Usage examples for all modules

### 2. Command-Line Scripts (`scripts/ble/`)
Ready-to-run scripts:

- **`log_nuanic_session.py`:** Data logging with duration control
  ```bash
  python scripts/ble/log_nuanic_session.py --duration 60
  ```

- **`analyze_nuanic_data.py`:** CSV analysis and reporting
  ```bash
  python scripts/ble/analyze_nuanic_data.py data/nuanic_logs/nuanic_*.csv
  ```

### 3. Documentation (`docs/nuanic/`)
Comprehensive guides:

- **`MODULE_GUIDE.md`:** Complete API reference and usage examples
- **`EDA_ANALYSIS_GUIDE.md`:** Deep dive into EDA interpretation
- **`STATUS_HONEST.md`:** Previous honest status assessment

### 4. Data Directory (`data/nuanic_logs/`)
Persistent storage for logged sessions:
- Format: `nuanic_YYYY-MM-DD_HH-MM-SS.csv`
- Contains all readings with stress and EDA data

## Project Structure

```
AWE_Polar_Project/
├── src/awe_polar/nuanic_ring/
│   ├── __init__.py              [✓] Module exports
│   ├── connector.py             [✓] BLE connection
│   ├── monitor.py               [✓] Real-time monitoring
│   ├── logger.py                [✓] CSV logging
│   ├── eda_analyzer.py          [✓] EDA analysis
│   └── examples.py              [✓] Usage examples
│
├── scripts/ble/
│   ├── log_nuanic_session.py     [✓] Data logger
│   ├── analyze_nuanic_data.py    [✓] Data analyzer
│   └── [old scripts to clean]    [ ] TBD
│
├── data/nuanic_logs/
│   └── [CSV files created here]  [✓] Auto-created on logging
│
├── docs/nuanic/
│   ├── MODULE_GUIDE.md           [✓] API reference
│   ├── EDA_ANALYSIS_GUIDE.md     [✓] EDA deep dive
│   └── STATUS_HONEST.md          [✓] Status report
│
└── README.md                       [ ] Needs update
```

## Data Format

### Stress Data
- **Source:** Byte 14 of 92-byte characteristic (468f2717-6a7d-46f9-9eb7-f92aab208bae)
- **Raw:** 0-255 integer
- **Scaled:** (raw / 255) × 100 = 0-100%
- **Update Rate:** ~1 Hz (900-950ms between packets)

### EDA Data
- **Source:** Bytes 15-91 of 92-byte characteristic (77 bytes)
- **Likely Format:** Multiple 16-bit channels
- **Update Rate:** Same as stress (1 Hz for logged packets)
- **Interpretation:** Electrodermal activity (autonomic arousal indicator)

### CSV Output Format
```
timestamp,stress_raw,stress_percent,eda_hex,full_packet_hex
2024-01-15T14:23:45.123456,127,49.8,a1b2c3d4...,full_packet_bytes...
```

## Quick Start

### 1. Log Data (60 seconds)
```bash
cd c:\TUNI - Projects\Python Project\AWE_Polar_Project
python scripts/ble/log_nuanic_session.py --duration 60
```

Output: `data/nuanic_logs/nuanic_2024-01-15_14-23-45.csv`

### 2. Analyze Logged Data
```bash
python scripts/ble/analyze_nuanic_data.py data/nuanic_logs/nuanic_2024-01-15_14-23-45.csv
```

Output: Console report with stress/EDA statistics

### 3. Use in Your Code
```python
from awe_polar.nuanic_ring import NuanicDataLogger

logger = NuanicDataLogger()
await logger.start_logging(duration_seconds=300)
```

## Next Steps

### Immediate (This Session)
- [ ] Test data logging with real ring
- [ ] Verify EDA byte parsing
- [ ] Create sample analysis plots
- [ ] Document actual EDA channel structure

### Short-term (Next Session)
- [ ] Build visualization dashboard (Streamlit)
- [ ] Validate EDA channels with stress correlation
- [ ] Compare EDA patterns with stress values
- [ ] Create peak detection examples

### Medium-term (Integration)
- [ ] Combine with Polar H10 HR data
- [ ] Create HR + Stress + EDA dashboard
- [ ] Build correlation analysis tools
- [ ] Extract historical data from ring storage

### Long-term (Analysis)
- [ ] Machine learning for stress prediction
- [ ] Individual baseline calibration
- [ ] Stress response pattern classification
- [ ] Real-world context integration

## Known Issues & Limitations

### Connection
- ✅ Resolved: Windows pairing no longer needed, Bleak handles it
- Connection timeout on first attempt: Try again, usually works second time
- Ring may go idle after 10+ minutes: Reconnect required

### Data
- EDA byte parsing: Still need to verify exact channel mapping
- Data rate: Logging at 1 Hz, but EDA characteristic may have higher sample rate
- Battery impact: Unknown, will test with extended logging

### Analysis
- EDA interpretation: Needs correlation validation with stress
- Baseline drift: Expected over long sessions (sweat accumulation)
- Movement artifacts: Possible from ring movement on finger

## File Cleanup Status

### Keep (Production)
- [✓] connector.py
- [✓] monitor.py
- [✓] logger.py
- [✓] eda_analyzer.py
- [✓] log_nuanic_session.py
- [✓] analyze_nuanic_data.py

### Review for Keeping
- `scripts/ble/aggressive_connect.py` - baseline connection test
- `scripts/ble/listen_nuanic_notifications.py` - raw data capture
- `scripts/ble/monitor_stress_realtime.py` - simple monitoring

### Can Delete (Redundant)
- `scripts/ble/find_nuanic_mac.py` - scanner (replaced by connector.py)
- `scripts/ble/connect_my_nuanic.py` - basic connection (replaced by connector.py)
- Test scripts in root (moved to tests/)

## Integration with AWE Polar Project

The Nuanic ring provides:
1. **Stress measurement** - DNE stress value (0-100%)
2. **EDA data** - Autonomic arousal indicator
3. **Complementary metrics** - Fills HR data with emotional context

**Future architecture:**
```
Polar H10 (HR, HRV) → Stress Analysis ← Nuanic Ring (Stress, EDA)
                            ↓
                    Dashboard & Reporting
```

## Documentation

All guides available in `docs/nuanic/`:

1. **MODULE_GUIDE.md** - API reference and examples
2. **EDA_ANALYSIS_GUIDE.md** - EDA interpretation and analysis
3. **STATUS_HONEST.md** - Current honest status

## Testing Checklist

Before production use:
- [ ] Test connection with your actual ring (MAC: 54:EF:C5:C4:02:93 or variant)
- [ ] Verify 60-second logging session completes successfully
- [ ] Check that CSV file is created and populated
- [ ] Run data analyzer on CSV output
- [ ] Inspect EDA hex values for patterns
- [ ] Correlate stress changes with physical activity
- [ ] Test battery impact of 1-hour continuous logging
- [ ] Verify no data loss or corruption

## Questions to Answer Next

1. **EDA Channel Identification**
   - Which of the 77 bytes contain the main EDA channels?
   - Are there 2, 4, or 8 channels?
   - What resolution (µS, arbitrary units)?

2. **Data Validation**
   - Does EDA correlate with stress peaks?
   - How much lag between stress spike and EDA response?
   - Are the values reasonable for wearable EDA?

3. **Feature Extraction**
   - How to identify stress response vs baseline?
   - What's the best peak detection threshold?
   - Can we estimate stress from EDA alone?

4. **Real-world Performance**
   - Battery drain during continuous logging?
   - Data quality over 1+ hour sessions?
   - Accuracy degradation due to ring movement?
