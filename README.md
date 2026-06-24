# Polar BLE Python SDK

[![CI](https://github.com/PhelaPoscam/Polar-Python-SDK/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/PhelaPoscam/Polar-Python-SDK/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/polar-ble-sdk.svg)](https://pypi.org/project/polar-ble-sdk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

An open-source Python SDK for connecting, monitoring, and capturing raw physiological and IMU data from Polar BLE devices (H10, Verity Sense, Vantage/Grit watches). The project offers real-time monitoring, machine-learning-based stress detection, a reactive Streamlit dashboard with live waveform charts, and a premium console terminal dashboard with event logging and hotkey markers.

---

## 🚀 Quick Start

### 1. Installation & Setup
**Requirements:** Python 3.8+, Windows 10/11 (Bluetooth capable).

#### Option A: Package Install from PyPI (Recommended for Library Use)
You can install the core BLE SDK directly from PyPI:
```bash
pip install polar-ble-sdk
```

To install optional features (such as ML predictors or dashboards):
* Install ML training and dependencies: `pip install polar-ble-sdk[ml]`
* Install Streamlit dashboard dependencies: `pip install polar-ble-sdk[dashboard]`
* Install all dependencies: `pip install polar-ble-sdk[ml,dashboard]`

#### Option B: Local Repository Install (Recommended for Dashboard/CLI Apps)
Run the automatic setup script in PowerShell to create the virtual environment and install all dependencies:
```powershell
.\setup.ps1
```
*(Alternatively, configure manually: `python -m venv .venv`, `.\.venv\Scripts\Activate.ps1`, `pip install -r requirements.txt`)*

### 2. Streamlit Dashboard
Verify setup and launch the Streamlit dashboard using:
```powershell
.\start.ps1
```
*(Manual command: `streamlit run src/polar_ble_sdk/app_streamlit.py`)*

### 3. Premium Terminal Dashboard
Launch the premium command-line dashboard with real-time event markers, battery monitoring, and 1 Hz CSV data logging:
```bash
.venv\Scripts\python.exe scripts\monitor_polar_terminal.py
```

*   **Specify Device**: Target a specific device (like a Vantage watch) by passing the name or MAC address:
    ```bash
    .venv\Scripts\python.exe scripts\monitor_polar_terminal.py --device Vantage
    ```
*   **Hotkey Event Markers**: Press `SPACE` (marker), `S` (stimulus_on), `B` (baseline_start), or `R` (rest_start) to log markers on-screen and save them directly in the CSV files under `data/`.

### 4. Dual-Device Terminal Dashboard
If you want to monitor both a Polar H10 chest strap and a Polar Verity Sense optical sensor side-by-side simultaneously:
```bash
.venv\Scripts\python.exe scripts\monitor_dual_polar.py
```
*   **Optional Filters**: Specify target devices:
    ```bash
    .venv\Scripts\python.exe scripts\monitor_dual_polar.py --h10 "H10 EA396220" --sense "Sense 11781835"
    ```
*   **Separate Logging**: Automatically saves independent, conflict-free CSV logs under `data/` for each connected device.

---

## 📊 Sensor Sampling Frequencies & CSV Logging

### 1. Device Capabilities (Maximum Sampling Rates)
Polar devices transmit sensor data at high frequencies via their PMD (Physical Measurement Device) service:
*   **Polar H10:**
    *   **ACC (Accelerometer):** 25, 50, 100, 200 Hz (Resolution: 16-bit, Range: 2, 4, 8 G)
    *   **ECG (Electrocardiogram):** 130 Hz (Resolution: 14-bit)
    *   **Heart Rate / RR-Intervals:** Event-driven (per heartbeat, ~1 Hz)
*   **Polar Verity Sense:**
    *   **PPG (Photoplethysmography):** 55 Hz (Resolution: 22-bit, Channels: 4)
    *   **ACC (Accelerometer):** 52 Hz (Resolution: 16-bit, Range: 8 G, Channels: 3)
    *   **GYRO (Gyroscope):** 52 Hz (Resolution: 16-bit, Range: 2000 dps, Channels: 3)
    *   **MAG (Magnetometer):** 10, 20, 50, 100 Hz (Resolution: 16-bit, Range: 50 Gauss, Channels: 3)
    *   **HR / PPI (Pulse-to-Pulse / HRV):** Event-driven (per pulse, ~1 Hz)
*   **Polar Smartwatches (Grit X, Vantage, etc.):**
    *   **PPG (Photoplethysmography):** Natively configured up to 135 Hz (varies by model)
    *   **ACC / GYRO (Kinematics):** Configurable up to 208 Hz (varies by model)

### 2. CSV Logging Rates & High-Frequency Option
*   **Default 1 Hz Logging:** By default, the terminal dashboards (`monitor_polar_terminal.py` and `monitor_dual_polar.py`) sample and record data to CSV at **1 Hz**. This contains the latest values at each second boundary. This downsampling prevents the creation of extremely sparse CSV files that result from mixing different sampling rates (e.g. 200 Hz ACC vs 1 Hz HR).
*   **High-Frequency Recording:** To record data at the **maximum native rate** (e.g. capturing all 200 Hz accelerometer samples or all 130 Hz ECG samples), you should write samples to the CSV directly within the device callback functions (such as `acc_callback_h10` or `ppg_callback_sense`) in the scripts. To prevent rate mismatch conflicts, it is recommended to write to separate stream-specific files (e.g., `*_acc.csv`, `*_ppg.csv`).

---

## ✨ Key Features

- **Multi-Device Support**: Captures raw physiological telemetry from the Polar H10 chest strap, Polar Verity Sense optical sensor, and Polar smartwatch line (Grit, Vantage).
- **High-Frequency Waveforms**: Live streaming and rendering of ECG electrical signals (130Hz), PPG optical pulse waves (55Hz), and IMU kinematics (3-axis Accelerometer, Gyroscope, and Magnetometer).
- **Stress & HRV Analysis**: Dynamic calculation of RMSSD from R-R intervals (heart rate variability) and optical PPI data feed.
- **Console Terminal Dashboard**: Full-featured interactive terminal view with a heart rate trend sparkline graph, background battery status checking, active stream rate monitor, and live event marker logs.
- **Automated Logging**: Saves session data periodically at 1 Hz directly to CSV files inside the `data/` directory.

---

## 📂 Project Structure

```text
Polar-Python-SDK/
├── setup.ps1                  # PowerShell automatic environment setup
├── start.ps1                  # PowerShell application launcher
├── src/polar_ble_sdk/
│   ├── app_streamlit.py       # Main Streamlit Dashboard (tabbed waveforms & kinematics)
│   ├── connector/             # BLE Device connection and data streaming layer
│   │   └── stream/            # Specialized device modules (Base, H10, VeritySense, Watch)
│   ├── dashboard_utils.py     # Shared helpers (RMSSD, sparkline, battery, CSV logging)
│   ├── reader/                # Real-time data reading and ML stress inference logic
│   └── ml/                    # Machine learning package (sample_data, train_model)
├── scripts/                   # Consolidated CLI Tools
│   ├── monitor_polar_terminal.py # Premium live console dashboard with logging & hotkeys
│   ├── connect_polar.py       # Simple streaming utility
│   ├── download_datasets.py   # Dataset setup helper
│   ├── replicate_tabnet_stress.py # TabNet model training pipeline
│   ├── scan_ble.py            # BLE device discovery scanner
│   ├── pair_watch.ps1         # Windows WinRT device pairing script
│   └── ...                    # Helper and setup utilities
├── tests/                     # 83 verified unit tests (pytest)
├── data/                      # Session log files and datasets
├── models/                    # Pickled ML models and scalers
└── docs/                      # Project guides
```

---

## 🧪 Testing & Code Quality

The codebase includes comprehensive unit testing and static type checking.

```bash
# Run the complete unit test suite
pytest tests/ -v --cov=.

# Run static type analysis checks
mypy src/ scripts/
```

---

## 📄 License & Credits

See the [LICENSE](LICENSE) file for details.  
Built for Python 3.8+ natively on Windows 10/11 environments.
