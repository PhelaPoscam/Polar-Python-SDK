# Nuanic Ring Integration - Quick Start (2026-02-27)

## What We Built Today

### 1. **Nuanic Ring Exporter** ✅ READY TO RUN
**File**: `scripts/ble/nuanic_ring_exporter.py`

**What it does**: 
- Tests 6 different activation strategies
- Reads all available characteristics
- Monitors all notification channels
- Logs everything for analysis

**How to run**:
```powershell
cd "c:\TUNI - Projects\Python Project\AWE_Polar_Project"
.\venv\Scripts\Activate.ps1
python scripts/ble/nuanic_ring_exporter.py
```

**Prerequisites**:
- ✅ Python virtual environment (venv configured)
- ✅ Bleak library (installed)
- ⚠️ **Bluetooth turned ON on your system** (required)
- ⚠️ **Nuanic ring powered on and nearby** (required)

**Output locations**:
- Data: `data/logs/ring_export/ring_data_*.csv`
- Protocol events: `data/logs/ring_export/export_log_*.json`

---

### 2. **Ring Data Simulator** ✅ TESTED & WORKING
**File**: `scripts/ble/nuanic_ring_simulator.py`

**What it does**:
- Generates realistic physiological data (HR, HRV, EDA, temperature)
- Creates CSV file with 1Hz sampling
- Can be used for testing/development without hardware

**How to run**:
```powershell
python scripts/ble/nuanic_ring_simulator.py
```

**Output**: `data/logs/ring_simulator/simulated_data_*.csv`

**Sample data**:
```
timestamp,heart_rate,hrv_rmssd,eda_level,temperature,activity,notes
2026-02-27T10:02:30,66,95.00,9.02,36.82,25,Resting - Calm
2026-02-27T10:02:31,69,92.50,12.31,36.53,16,Resting - Calm
...
```

---

### 3. **Integration Guide** ✅ READY TO READ
**File**: `docs/NUANIC_RING_INTEGRATION_GUIDE.md`

Complete guide covering:
- Phase 1: Protocol diagnosis (TODAY)
- Phase 2: Data format analysis (AFTER getting results)
- Phase 3: Implementation (AFTER analysis)
- Troubleshooting
- References

---

## NEXT IMMEDIATE ACTIONS

### Option A: Test with Real Hardware
**Requires**: Bluetooth enabled, ring charged/powered

```powershell
# Makes sure Bluetooth is ON first!
python scripts/ble/nuanic_ring_exporter.py
```

Then:
1. Check `data/logs/ring_export/ring_data_*.csv` for any data
2. Check `data/logs/ring_export/export_log_*.json` for protocol events  
3. Document findings and share results

### Option B: Test Pipeline Without Hardware
```powershell
# Generate test data to work with
python scripts/ble/nuanic_ring_simulator.py

# Then analyze/visualize the CSV data
# Can load in Python/Pandas or Streamlit
```

### Option C: Do Both
```powershell
# First, generate test data for pipeline development
python scripts/ble/nuanic_ring_simulator.py

# In parallel, work on with real hardware if available
python scripts/ble/nuanic_ring_exporter.py
```

---

## Project Status Summary

| Component | Status | Next Step |
|-----------|--------|-----------|
| Polar H10 Integration | ✅ Working | Use with real data |
| Nuanic Ring Discovery | ✅ Complete | Run Phase 1 diagnostic |
| TabNet Model Scaffold | ✅ Ready | Wire to real metrics (when data available) |
| Game Bridge Scaffold | ✅ Ready | Implement UATR algorithm |
| Streamlit Dashboard | ✅ Working | Add Nuanic visualization (when data ready) |

---

## Files Changed Today

**New Files**:
- `scripts/ble/nuanic_ring_exporter.py` - Export/diagnosis tool
- `scripts/ble/nuanic_ring_simulator.py` - Test data generator
- `scripts/ble/nuanic_protocol_discovery.py` - Alternative detailed tester
- `docs/NUANIC_RING_INTEGRATION_GUIDE.md` - Full integration guide

**Updated**:
- `README.md` - Added quick start, Phase 1 focus, tool summaries
- `TODO` list - Prioritized Nuanic diagnosis as #1 task

---

## Key Insights

### About the Nuanic Ring

The ring **stores data internally** (based on your feedback). This means:

1. **Real-time streaming** (if supported):
   - Activation command → Data flows via BLE notification → Parse and log

2. **Stored data export** (more likely):
   - Query command → Ring dumps internal measurements → Parse and sync

3. **Hybrid approach**:
   - Use companion app to export → Fetch from external storage → Parse

### What We're Testing

The exporter tests **6 different strategies**:
- `soft_reset` - Basic enable (0x01)
- `hard_reset` - Full reset + enable
- `full_dump` - Export/dump commands
- `streaming_enable` - Real-time mode activation
- `time_sync` - Time synchronization
- `query_status` - Status queries

One of these will likely work. If none work, the ring needs manual export via its app first.

---

## Troubleshooting Quick Reference

| Problem | Solution |
|---------|----------|
| "Bluetooth radio is not powered on" | Settings → Bluetooth → Turn ON |
| "Ring not found" | Power on ring, ensure within 10m, restart Bluetooth |
| No data in CSV after running exporter | Try other activation strategies or check app |
| Simulator data not generating | Check `scripts/ble/nuanic_ring_simulator.py` is executable |

---

## Timeline Estimate

- **Today (Session 1)**: Protocol diagnosis (Phase 1)
  - Run exporter → check outputs
  
- **Tomorrow (Session 2)**: Data analysis (Phase 2)
  - Parse format → create decoder → verify
  
- **Day 3 (Session 3)**: Implementation (Phase 3)
  - Build streaming handler → integrate → test
  
- **Day 4 (Session 4)**: UI integration
  - Add to Streamlit → show alongside Polar H10

---

## Questions to Answer

After running Phase 1, we'll know:

1. ❓ Does the exporter receive any data at all?
2. ❓ If yes, which activation strategy worked?
3. ❓ What's the raw format of the data?
4. ❓ Is it real-time streaming or stored data export?
5. ❓ How frequently does data arrive?

Each answer narrows down the implementation path for Phase 2.

---

**Status**: Ready for Phase 1 execution ✅  
**Date**: 2026-02-27  
**Next**: Turn on Bluetooth and run the exporter!
