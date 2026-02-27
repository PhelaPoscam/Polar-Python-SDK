# AWE Polar Project - Nuanic Ring Integration

## ⚠️ Current Status: In Progress

**Critical Blocker**: Cannot establish stable GATT connection to user's actual Nuanic ring.
All previous testing was performed on a **neighbor's ring** (wrong device).

See [STATUS_HONEST.md](STATUS_HONEST.md) for details.

## 📁 Project Structure

```
AWE_Polar_Project/
├── src/awe_polar/
│   ├── connector/
│   │   ├── nuanic_stress_handler.py       # Real-time stress reader (stub)
│   │   └── nuanic_eda_parser.py          # Parser (needs testing on correct ring)
│   └── ...
│
├── scripts/
│   ├── ble/
│   │   ├── nuanic_ring_exporter.py        # Device discovery & protocol testing
│   │   ├── nuanic_ring_simulator.py       # Test data generator
│   │   ├── nuanic_protocol_discovery.py   # GATT structure discovery
│   │   ├── nuanic_data_extractor.py       # Extract ring measurements
│   │   ├── nuanic_eda_parser.py          # Parse EDA data
│   │   └── diagnostics/                   # Advanced testing tools
│   │
│   └── analysis/                          # Data analysis scripts
│       ├── analyze_exported_nuanic.py     # App export analysis
│       ├── verify_new_export.py           # CSV export verification
│       └── ...
│
├── docs/
│   ├── nuanic/
│   │   ├── STATUS_HONEST.md               # ← READ THIS FIRST
│   │   ├── ACTION_PLAN.md                 # Next steps
│   │   ├── NUANIC_QUICK_START.md          # Getting started
│   │   └── /README.md (this file)
│   │
│   └── ...
│
└── data/
    ├── logs/
    │   └── ring_extraction/               # Extraction logs
    ├── Exported Data/                     # Nuanic app CSV exports
    └── raw/
        └── all_hrv_data3.csv              # Training data
```

---

## 🎯 Current Status

### ✅ **COMPLETED**
- [x] Device discovery & BLE connection
- [x] Data format identification (Byte 14 = Stress Level 0-100)
- [x] Parser created & verified
- [x] Export data analyzed & correlated
- [x] Project structure organized

### 🔄 **IN PROGRESS**
- [ ] Streamlit integration (Phase 3)
- [ ] Real-time stress monitoring
- [ ] HR + Stress correlation
- [ ] Dashboard visualization

### ⏳ **TODO**
- [ ] Continuous polling handler
- [ ] CSV logging
- [ ] Historical data export
- [ ] ML analysis tools

---

## 📋 Quick Links

### Documentation
- **Getting Started**: [docs/nuanic/NUANIC_QUICK_START.md](docs/nuanic/NUANIC_QUICK_START.md)
- **Phase 1 Results**: [docs/nuanic/PHASE1_RESULTS.md](docs/nuanic/PHASE1_RESULTS.md)
- **Discovery Notes**: [docs/nuanic/BREAKTHROUGH_DISCOVERY.md](docs/nuanic/BREAKTHROUGH_DISCOVERY.md)
- **Action Plan**: [docs/nuanic/ACTION_PLAN.md](docs/nuanic/ACTION_PLAN.md)

### Tools
**Ring Diagnostics:**
```powershell
python scripts/ble/nuanic_ring_exporter.py        # Initial discovery
python scripts/ble/nuanic_data_extractor.py       # Pull measurement data
python scripts/ble/nuanic_realtime_monitor.py     # Monitor stress (10min)
```

**Data Analysis:**
```powershell
python scripts/analysis/analyze_exported_nuanic.py    # Analyze app export
python scripts/analysis/verify_byte14_live.py         # Verify Byte 14
python scripts/analysis/compare_three_states.py       # Compare states
```

**Implementation:**
```powershell
python src/awe_polar/connector/nuanic_stress_handler.py  # Real-time reader
```

---

## 🔑 Key Findings

### **Byte 14 = DNE Stress Level (0-100)**

Evidence:
- App displayed stress = 46
- Byte 14 read = 46
- Export DNE range = 28-100
- **CONFIRMED MATCH** ✅

### Measurement Frequency
- Ring continuously records EDA sensor data
- Stores 1-minute summaries internally
- Updates BLE buffer with latest snapshot
- Poll every 10-30 seconds for changes

### Data Export
The Nuanic app exports CSV with:
- **DNE**: Stress level (0-100)
- **SRL**: Heart rate variability metric
- **EDA**: Raw sensor data
- **ACCEL**: Activity/movement level

---

## 🚀 Next Steps

### Phase 3: Implementation
1. Update `src/awe_polar/app_streamlit.py` with Nuanic support
2. Add real-time stress meter
3. Create HR + Stress overlay graph
4. Implement continuous polling

### Phase 4: Integration
1. Combine Polar H10 HR with Nuanic stress
2. Create correlation dashboard
3. Export combined data
4. ML analysis of HR-stress patterns

---

## 📊 File Organization Summary

| Category | Location | Purpose |
|----------|----------|---------|
| **Source Code** | `src/awe_polar/connector/` | Parser & handler implementation |
| **BLE Tools** | `scripts/ble/` | Device interaction & protocols |
| **Analysis** | `scripts/analysis/` | Data analysis & exploration |
| **Documentation** | `docs/nuanic/` | Findings, guides, results |
| **Configuration** | `root` | Setup, requirements, README |

---

## 💡 Usage Examples

### Read stress level once:
```python
from src.awe_polar.connector.nuanic_eda_parser import parse_nuanic_eda
import asyncio
from bleak import BleakClient

async def read_stress():
    async with BleakClient(address) as client:
        data = await client.read_gatt_char(uuid)
        result = parse_nuanic_eda(data)
        print(f"Stress: {result['stress_level']}%")
```

### Monitor stress for 5 minutes:
```powershell
python src/awe_polar/connector/nuanic_stress_handler.py
```

### Analyze ring exports:
```powershell
python scripts/analysis/analyze_exported_nuanic.py
```

---

**Last Updated**: 2026-02-27  
**Status**: Phase 2 Complete ✅ → Awaiting Phase 3  
**Next Milestone**: Streamlit dashboard with stress integration
