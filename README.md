# AWE Polar Project

[![CI](https://github.com/PhelaPoscam/AWE_Polar_Project/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/PhelaPoscam/AWE_Polar_Project/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%20to%203.11-blue.svg)](https://www.python.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

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
# Real-time monitoring (live display + CSV logs)
python scripts/nuanic_monitor_cli.py --duration 60

# Real-time monitoring without creating CSV logs
python scripts/nuanic_monitor_cli.py --duration 60 --no-log

# Data logging (lightweight, no display)
python scripts/nuanic_logger_cli.py --duration 300

# Analyze captured data
python scripts/nuanic_analyzer_cli.py data/nuanic_logs/nuanic_stress_*.csv

# Live waveform visualization
python scripts/nuanic_monitor_cli.py --waveform --window-seconds 10

# List available rings
python scripts/nuanic_monitor_cli.py --list-rings
```

See [Nuanic Master Guide](docs/nuanic/00_master_guide.md) for all options and examples.

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
│   │   ├── monitor.py          - IMU + stress monitor, display, CSV logging
│   │   ├── logger.py           - CSV data logging
│   │   ├── eda_analyzer.py     - EDA analysis engine
│   │   └── data_analysis.py    - Stress/EDA CSV analysis utilities
│   ├── app_streamlit.py       - Dashboard
│   └── train_model.py         - ML training pipeline
│
├── scripts/                   ← Nuanic tools (production ready)
│   ├── nuanic_monitor_cli.py        - Real-time monitoring CLI
│   ├── nuanic_logger_cli.py         - Lightweight logging CLI
│   ├── nuanic_analyzer_cli.py       - CSV analysis CLI
│   └── discover_nuanic_services.py  - Unified BLE diagnostics (discovery/profile/write-probe/buffer)
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
├── docs/
│   ├── contributing.md
│   ├── nuanic/
│   │   └── 00_master_guide.md
│
└── data/
    ├── raw/                   - Training datasets
    └── nuanic_logs/           - Logged Nuanic sessions
```

## Documentation

**Nuanic Ring Integration:**
- [Nuanic Master Guide](docs/nuanic/00_master_guide.md) - Setup, CLI/API usage, packet decoding, EDA analysis, troubleshooting

**Development:**
- [Contributing Guidelines](docs/contributing.md) - Development standards

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
- **IMU:** Bytes 8-13 of acceleration packet → ACC_X, ACC_Y, ACC_Z signed int16 → ±32,768 range
- **Update Rate:** 16.8 Hz combined (15.87 Hz IMU + 1.12 Hz physiology)
- **Packet Format Details:** See [NUANIC_ANALYSIS_REPORT.md](NUANIC_ANALYSIS_REPORT.md)

## Nuanic Reverse-Engineering Snapshot (2026-03-16)

Latest verified live findings (Windows + Bleak, direct ring connection):

- Ring advertisement uses rotating/private BLE MAC addresses.
- Full GATT table was successfully enumerated on live device.
- Standard services present: Generic Attribute, Generic Access, Battery, Device Information, SMP.
- Proprietary service present: `5491faaf-b0c2-4167-8f3d-bc6b31db69e7` with 12 characteristics.

### Proprietary Service Characteristics (UUID -> properties)

- `516b0fb6-d861-4619-9dd0-0105e8b85128` -> `read, write`
- `dc9c31a7-fbd3-467a-8777-10900c423d3b` -> `read, write`
- `42dcb71b-1817-43bd-8ea3-7272780a1c9f` -> `notify`
- `7c3b82e7-22b7-4cb6-8458-ba325edf6ede` -> `read`
- `2175c13f-60e4-4de5-80af-0d06f1b54880` -> `write`
- `3cce21a7-e602-4e02-8c52-1e0366c1c846` -> `read, write`
- `741f0d15-cc3d-4715-a9fb-a5a6bccebc50` -> `write`
- `d78e5bd8-53d6-4fc3-bc98-03b8cd71684b` -> `read`
- `d306262b-c8c9-4c4b-9050-3a41dea706e5` -> `notify, read`
- `3c180fcc-bfec-4b7c-8e52-1a37f123e449` -> `notify, read`
- `468f2717-6a7d-46f9-9eb7-f92aab208bae` -> `notify`
- `2204a4f6-b92e-4c64-8022-e938dd2a5dc2` -> `read`

### Observed Live Stream Behavior

From recent session captures in `data/nuanic_logs/`:

- State stream (`3c180fcc...`, 1 byte): observed values `01`, `02`, `03`; current hypothesis is this acts as a state/on-finger indicator and gates high-rate streams.
- Core sensor stream (`d306262b...`, 16 bytes): high-rate packets (roughly ~22-25 Hz in latest live run) containing timestamp-like counter, dynamic signal field, and trailing quality/contact-like field.
- Bulk waveform stream (`468f2717...`, 92 bytes): roughly ~1 Hz batched payload likely carrying one-second motion/IMU-like sample block.
- Silent/event stream (`42dcb71b...`): subscribes successfully but can remain silent during normal wear windows; likely asynchronous/event channel.

### Latest Live Interpretation (2026-03-16)

From a clean `--subscribe-core-streams` run, the following behavior was observed:

1. **State / On-Finger indicator** (`3c180fcc-bfec-4b7c-8e52-1a37f123e449`, 1 byte)
    - `01`: idle/off-finger (or polling state)
    - `02`: active/on-finger (high-rate streams begin immediately)
    - `03`: transient poll/check state (observed interleaved with `01`)

2. **Real-time sensor + quality frame** (`d306262b-c8c9-4c4b-9050-3a41dea706e5`, 16 bytes, ~22-25 Hz)
    - Bytes `0-3`: monotonic counter/timestamp-like field (increments nearly constant per packet)
    - Bytes `4-7`: mostly static context field (commonly `9C 01 00 00` in this run)
    - Bytes `8-11`: highly dynamic signal field (EDA/stress-related candidate)
    - Bytes `12-15`: quality/contact-like field (observed around `0x64` then drifting downward in step-like fashion)

3. **Bulk motion stream** (`468f2717-6a7d-46f9-9eb7-f92aab208bae`, 92 bytes, ~1 Hz)
    - First 8 bytes align with counter/timestamp progression.
    - Remaining 84 bytes appear to be packed one-second motion/waveform data.

4. **Silent stream in this session** (`42dcb71b-1817-43bd-8ea3-7272780a1c9f`)
    - No packets during this capture window.
    - Most likely reserved for asynchronous conditions (sync/error/battery/event signaling).

Note: these are reverse-engineered interpretations from live payload behavior and should be treated as current best-fit hypotheses until validated across more sessions.

### Reconnect Stability Note

- Forced unpair-on-disconnect caused unreliable reconnect behavior with rotating MAC addresses.
- Connector behavior now defaults to plain disconnect (no forced OS unpair), improving reconnect reliability.

## Analysis & Validation Tools

**Current Analysis Script** (`scripts/analysis/`)
- `analyze_nuanic_stream.py` - Stream-level analysis for captured Nuanic data

**To run analysis:**
```bash
# Analyze captured stream(s)
python scripts/analysis/analyze_nuanic_stream.py
```

**Legacy BLE Scripts** (`scripts/ble/archive/`)
- Discovery/diagnostic scripts from exploratory phase
- Kept for reference
- Not required for production monitoring

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
- 📄 **See [Nuanic Master Guide](docs/nuanic/00_master_guide.md) for full technical findings and context**

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
python scripts/nuanic_monitor_cli.py --duration 300
# Output: data/nuanic_logs/nuanic_imu_*.csv + nuanic_stress_*.csv
```

**Analyze Logged Data:**
```bash
# Generate statistics report
python scripts/nuanic_analyzer_cli.py data/nuanic_logs/nuanic_stress_2026-02-27_14-23-45.csv
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
