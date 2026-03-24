# AWE Polar Project

[![CI](https://github.com/PhelaPoscam/AWE_Polar_Project/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/PhelaPoscam/AWE_Polar_Project/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%20to%203.11-blue.svg)](https://www.python.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A multi-modal stress monitoring system merging **Polar H10 heart rate data** with **Ring-device biometric measurements** (Stress, Electrodermal Activity). The project offers real-time monitoring, machine-learning-based stress detection, and a reactive Streamlit dashboard with LLM-powered insights.

---

## 🚀 Quick Start

### 1. Installation

**Requirements:** Python 3.8-3.11, Windows 10/11 (Bluetooth capable).

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```
_Optional: Add your `OPENAI_API_KEY` to `.env` to enable LLM insights in the dashboard._

### 2. Streamlit Dashboard & Monitoring
Launch the real-time AI dashboard (requires Polar H10 connection):
```bash
streamlit run src/awe_polar/app_streamlit.py
```
> **Tip:** You can test the dashboard without hardware using the mock flag: `streamlit run src/awe_polar/app_streamlit.py -- --mock=1`

### 3. Ring Device CLI Tools
Capture real-time stress and Electrodermal Activity (EDA) using the ring CLI. Uses automatic device discovery.

```bash
# Monitor and log data to CSV for 60 seconds
python scripts/ring_monitor_cli.py --duration 60

# Lightweight datalogger (no live display)
python scripts/ring_logger_cli.py --duration 300

# Live waveform visualization
python scripts/ring_monitor_cli.py --waveform --window-seconds 10

# View discovered devices
python scripts/ring_monitor_cli.py --list-rings
```

---

## ✨ Key Features

- **Heart Rate & HRV Tracking**: Real-time RMSSD extraction from Polar H10 telemetry.
- **Machine Learning**: Predicts stress levels using Random Forest and Gradient Boosting algorithms (found in `scripts/train/train_model.py`).
- **Ring Device Integration**: Handles complex protocol reverse-engineering for both **Nuanic** and **Moodmetric** ring profiles. Automatically decodes proprietary BLE streams (including 86 Hz EDA waveforms).
- **Asynchronous GUI**: Dashboard runs purely on Streamlit, auto-refreshing via background threads to keep LLM Chatboxes responsive.
- **Diagnostics**: Rich toolkit for offline CSV analysis and BLE debugging (`scripts/ring_analyzer_cli.py`, `scripts/discover_ring_services.py`).

---

## 📂 Project Structure

```text
AWE_Polar_Project/
├── src/awe_polar/
│   ├── app_streamlit.py       # Main ML + LLM Dashboard (Refactored for async support)
│   ├── train_model.py         # ML pipeline
│   ├── ring_device/           # Ring connection logic (Monitors, BLE Client, parsers)
│   └── nuanic_ring/           # Shims for ring connectivity
├── scripts/                   # CLI Tools (ring monitoring, logging, diagnostics)
├── tests/                     # 33 verified unit tests (pytest)
├── data/                      # Captured CSV logs / Dataset targets
├── models/                    # Pickled ML models and scalers
└── docs/                      # Extensive engineering and reverse-engineering guides
```

---

## 📚 Technical & Reverse-Engineering Documentation

The complex GATT reverse-engineering, specific ring mappings, and low-level CLI diagnostic tools are now fully open-sourced in their own dedicated SDK repository.

- **Ring Integration & Reverse-Engineering:** [Nuanic_Moodmetric_BLE on GitHub](https://github.com/PhelaPoscam/Nuanic_Moodmetric_BLE)
- **Contributing to AWE:** [Development Standards](docs/contributing.md)

<details>
<summary><strong>🔬 Click to expand: Ring Protocol & Byte-Level Payloads</strong></summary>

### Data Formats & Payload Specifications

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

### Nuanic Reverse-Engineering Snapshot (2026-03-16)

Latest verified live findings (Windows + Bleak, direct ring connection):
- Ring advertisement uses rotating/private BLE MAC addresses.
- Proprietary service present: `5491faaf-b0c2-4167-8f3d-bc6b31db69e7` with 12 characteristics.

**Proprietary Service Characteristics:**
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

**Observed Live Stream Behavior:**
1. **State / On-Finger indicator** (`3c180fcc...`, 1 byte): `01` = idle, `02` = active/on-finger.
2. **Real-time sensor + quality frame** (`d306262b...`, 16 bytes, ~22-25 Hz):
    - Bytes `0-3`: monotonic counter/timestamp.
    - Bytes `8-11`: highly dynamic signal field (EDA/stress-related candidate).
    - Bytes `12-15`: quality/contact-like field.
3. **Bulk motion stream** (`468f2717...`, 92 bytes, ~1 Hz): Packed one-second motion/waveform data.

### Ring Profile Matrix (Nuanic vs Moodmetric)
The diagnostics CLI discovers both, but they expose different proprietary profiles.
- **Nuanic Profile:** Target proprietary service `5491faaf...`. Operational implication: `--buffer-only` is meaningful here. 
- **Moodmetric Profile:** Exposes different custom services (e.g. `dd499b70...`). Diagnostics skip Nuanic-only buffer steps here.

**Moodmetric Capture Working Interpretation (2026-03-16):**
- Notifying UUIDs `a095...` (7 bytes) candidate layout:
    - bytes 0-1: rolling counter
    - bytes 2-3: state/quality-like field
    - byte 4: stress-like index candidate
    - bytes 5-6: raw signal/EDA-like value candidate
- UUID `f1b4...` (2 bytes) is likely a high-rate raw ADC channel.
</details>

*(Note: The `ring_device` library handles all the complex byte-shifting, dynamic MAC rotating, and GATT Subscription logic internally.)*

---

## 🧪 Testing

The codebase includes comprehensive unit testing.
```bash
# Test the complete test suite
pytest tests/ -v --cov=.

# Test specifically ring device integration (33 unit tests)
pytest tests/test_ring_integration.py -v
```

---

## 📄 License & Credits

See the [LICENSE](LICENSE) file for details.  
Built for Python 3.8 to 3.11 natively on Windows 10/11 environments. ML datasets utilize references from WESAD, SWELL, and UBFC-Phys.
