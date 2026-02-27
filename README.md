# AWE Polar Project

**Status:** ✅ Production Ready  
**Python:** 3.8-3.11 | **OS:** Windows 10/11

Multi-modal stress monitoring system combining Polar H10 heart rate data with Nuanic smart ring biometric measurements (stress, EDA). Features ML-based stress detection, real-time monitoring, and Streamlit dashboard.

## Quick Start

### 1. Setup
```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Polar H10 - Heart Rate Monitoring
```bash
python scripts/train/train_model.py          # Train ML model
streamlit run scripts/app/app_streamlit.py   # Run dashboard
```

### 3. Nuanic Ring - Stress & EDA Monitoring
```bash
# Log stress + EDA data (60 seconds)
python scripts/ble/log_nuanic_session.py --duration 60

# Analyze captured data
python scripts/ble/analyze_nuanic_data.py data/nuanic_logs/nuanic_*.csv

# Verify modules
python scripts/ble/test_nuanic_modules.py
```

## Features

**Polar H10 Integration**
- Real-time heart rate monitoring via Bluetooth
- HRV analysis (RMSSD)
- ML-based stress detection (Random Forest, Gradient Boosting)
- Streamlit dashboard with live gauges and visualization
- LLM-based insights (OpenAI, optional)
- Hyperparameter tuning via GridSearchCV
- Model versioning with timestamped artifacts

**Nuanic Ring Integration**
- Real-time stress measurement (0-100%)
- EDA (electrodermal activity) data capture
- CSV logging with timestamp, stress, and sensor data
- Data analysis tools with statistical reporting
- 33 comprehensive unit tests (100% passing)
- Production-ready Python modules with clean API

## Project Structure

```
AWE_Polar_Project/
├── src/awe_polar/
│   ├── nuanic_ring/           ← Nuanic integration modules
│   │   ├── connector.py        - BLE connection & discovery
│   │   ├── monitor.py          - Stress packet parsing
│   │   ├── logger.py           - CSV data logging
│   │   └── eda_analyzer.py    - EDA analysis engine
│   ├── app_streamlit.py       - Dashboard
│   └── train_model.py         - ML training pipeline
│
├── scripts/ble/               ← Nuanic tools (production ready)
│   ├── log_nuanic_session.py
│   └── analyze_nuanic_data.py
│
├── scripts/train/             ← ML pipeline
│   └── train_model.py
│
├── scripts/data/              ← Data utilities
│   └── download_datasets.py
│
├── tests/
│   ├── test_nuanic_integration.py     ← 33 tests, 100% passing
│   └── [other tests]
│
├── docs/nuanic/               ← Detailed reference guides
│   ├── MODULE_GUIDE.md        - Complete API reference
│   └── EDA_ANALYSIS_GUIDE.md  - EDA data interpretation
│
└── data/
    ├── raw/                   - Training datasets
    └── nuanic_logs/           - Logged Nuanic sessions
```

## Documentation

**Nuanic Ring Integration:**
- [Module API Guide](docs/nuanic/MODULE_GUIDE.md) - Complete API reference with examples
- [EDA Analysis Guide](docs/nuanic/EDA_ANALYSIS_GUIDE.md) - Data interpretation and analysis methods
- [Project Organization](docs/nuanic/PROJECT_ORGANIZATION.md) - Architecture and design

**Development:**
- [Contributing Guidelines](CONTRIBUTING.md) - Development standards

## Configuration

1. **Environment Setup:**
   ```bash
   cp .env.example .env
   # Add your OpenAI API key (optional, for LLM features)
   ```

2. **Polar H10:** Pairs via system Bluetooth settings

3. **Nuanic Ring:** Auto-discovered by device name in software

## Data Formats

**Nuanic Ring CSV Logging**
```
timestamp,stress_raw,stress_percent,eda_hex,full_packet_hex
2024-01-15T14:23:45.123456,127,49.8,a1b2c3d4...,full_hex...
```

**Data Specifications**
- **Stress:** Byte 14 of physiology packet → 0-255 raw → 0-100% scaled
- **EDA:** Bytes 15-91 (77 samples) → ~86 Hz PPG/EDA waveform → 0-100 μS range
- **IMU:** Bytes 8-11 of acceleration packet → ACC_X, ACC_Y signed int16 → ±32,768 range
- **Update Rate:** 16.8 Hz combined (15.87 Hz IMU + 1.12 Hz physiology)
- **Packet Format Details:** See [NUANIC_ANALYSIS_REPORT.md](NUANIC_ANALYSIS_REPORT.md)

## Analysis & Validation Tools

**Core Analysis Scripts** (`scripts/analysis/`)
- `extract_eda_data.py` - Extract and analyze EDA waveform data
- `verify_accelerometer.py` - Validate IMU with stationary vs movement test
- `investigate_dne_algorithm.py` - Analyze stress/EDA algorithm behavior
- `analyze_5min_capture.py` - Extended capture temporal analysis
- `baseline_calibration_analysis.py` - Study baseline learning/calibration
- `temporal_pattern_5min.py` - Time-series pattern identification

**To run analysis:**
```bash
# Analyze EDA extraction
python scripts/analysis/extract_eda_data.py

# Validate IMU acceleration
python scripts/analysis/verify_accelerometer.py

# Investigate DNE baseline calibration
python scripts/analysis/baseline_calibration_analysis.py

# Full 5-minute capture analysis
python scripts/analysis/analyze_5min_capture.py
```

**Legacy Scripts** (`scripts/analysis/archive/`)
- 18 hardware reverse-engineering scripts from exploratory phase
- Kept for reference and methodology documentation
- Not required for production use

## Datasets for ML Training

For WESAD, SWELL, and UBFC-Phys datasets:

```bash
# Verify local availability
python scripts/data/download_datasets.py --verify-only

# Extract from ZIP files (if you have them locally)
python scripts/data/download_datasets.py --extract
```

**Official Sources:**
- WESAD: https://archive.ics.uci.edu/ml/datasets/WESAD
- SWELL: https://cs.ru.nl/~skoldijk/SWELL-KW/Dataset.html
- UBFC-Phys: https://ieee-dataport.org/open-access/ubfc-phys

**Expected Layout:**
```
datasets/
├── WESAD/
├── SWELL/
└── UBFC-Phys/
```

## Testing

```bash
# Run all tests with coverage
pytest tests/ -v --cov=.

# Test Nuanic integration (33 unit tests)
pytest tests/test_nuanic_integration.py -v

# Verify Nuanic modules are healthy
python scripts/ble/test_nuanic_modules.py
```

**Test Status:**
- ✅ 33/33 unit tests passing
- ✅ All modules verified and functional
- ✅ 100% success rate

## What's New (Feb 27, 2026)

**Hardware Analysis & Reverse Engineering:**
- ✅ Decoded dual-stream BLE architecture (15.87 Hz IMU + 1.12 Hz physiology = 16.8 Hz combined)
- ✅ Verified IMU acceleration data (bytes 8-11, ±32K range, 6× stationary/movement variance)
- ✅ Extracted EDA waveform (bytes 15-91, 77 samples @ 86 Hz, 0-100 μS)
- ✅ Analyzed stress algorithm behavior (DNE baseline calibration, +10.7% initial drift)
- ✅ Validated sensor independence (stress ↔ EDA correlation = -0.12)
- ✅ Tested with 5-minute extended capture (4,799 IMU + 325 physiology packets)
- 📄 **See [NUANIC_ANALYSIS_REPORT.md](NUANIC_ANALYSIS_REPORT.md) for full technical findings**

**Code & Documentation:**
- ✅ 6 core analysis scripts for sensor validation
- ✅ 18 legacy exploratory scripts archived for reference
- ✅ Comprehensive technical report with experimental validation
- ✅ Cleaned codebase (organized analysis folder structure)
- ✅ Production-ready data logging and analysis tools

## Usage Examples

**Log Nuanic Ring Data:**
```bash
# Record for 5 minutes
python scripts/ble/log_nuanic_session.py --duration 300
# Output: data/nuanic_logs/nuanic_2026-02-27_14-23-45.csv
```

**Analyze Logged Data:**
```bash
# Generate statistics report
python scripts/ble/analyze_nuanic_data.py data/nuanic_logs/nuanic_2026-02-27_14-23-45.csv
# Shows: stress range, peaks, EDA analysis
```

**Use in Python Code:**
```python
from awe_polar.nuanic_ring import NuanicDataLogger
from awe_polar.nuanic_ring.eda_analyzer import NuanicEDAAnalyzer

# Log stress + EDA data
logger = NuanicDataLogger()
await logger.start_logging(duration_seconds=300)

# Analyze EDA patterns
analyzer = NuanicEDAAnalyzer()
for eda_value in eda_stream:
    stats = analyzer.add_reading(eda_value)
    if stats['is_peak']:
        print(f"Stress response detected")
```

## System Requirements

- Python 3.8-3.11
- Windows 10/11 (Bluetooth capable)
- Polar H10 heart rate monitor (optional)
- Nuanic smart ring (optional)
- 2 GB RAM minimum
- Virtual environment recommended

## License

See [LICENSE](LICENSE) file for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.
