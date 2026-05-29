# AWE Polar Project

[![CI](https://github.com/PhelaPoscam/AWE_Polar_Project/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/PhelaPoscam/AWE_Polar_Project/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A real-time stress monitoring and physiological visualization system using **Polar H10, Verity Sense, and Vantage/Grit watches**. The project offers real-time monitoring, machine-learning-based stress detection, a reactive Streamlit dashboard with live waveform charts, and a premium console terminal dashboard with event logging and hotkey markers.

---

## 🚀 Quick Start

### 1. Installation & Setup
**Requirements:** Python 3.8+, Windows 10/11 (Bluetooth capable).

You can run the automatic setup script in PowerShell to create the virtual environment and install all dependencies:
```powershell
.\setup.ps1
```
*(Alternatively, configure manually: `python -m venv .venv`, `.\.venv\Scripts\Activate.ps1`, `pip install -r requirements.txt`)*

### 2. Streamlit Dashboard
Verify setup and launch the Streamlit dashboard using:
```powershell
.\start.ps1
```
*(Manual command: `streamlit run src/awe_polar/app_streamlit.py`)*

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
AWE_Polar_Project/
├── setup.ps1                  # PowerShell automatic environment setup
├── start.ps1                  # PowerShell application launcher
├── src/awe_polar/
│   ├── app_streamlit.py       # Main Streamlit Dashboard (tabbed waveforms & kinematics)
│   ├── connector/             # BLE Device connection and data streaming layer
│   │   └── stream/            # Specialized device modules (Base, H10, VeritySense, Watch)
│   ├── reader/                # Real-time data reading and ML stress inference logic
│   └── train_model.py         # ML pipeline training script
├── scripts/                   # Consolidated CLI Tools
│   ├── monitor_polar_terminal.py # Premium live console dashboard with logging & hotkeys
│   ├── connect_polar.py       # Simple streaming utility
│   ├── download_datasets.py   # Dataset setup helper
│   ├── replicate_tabnet_stress.py # TabNet model training pipeline
│   ├── scan_ble.py            # BLE device discovery scanner
│   ├── pair_watch.ps1         # Windows WinRT device pairing script
│   └── ...                    # Helper and setup utilities
├── tests/                     # 51 verified unit tests (pytest)
├── data/                      # Session log files and datasets
├── models/                    # Pickled ML models and scalers
└── docs/                      # Project guides
```

---

## 🧪 Testing

The codebase includes comprehensive unit testing.
```bash
# Test the complete test suite
pytest tests/ -v --cov=.
```

---

## 📄 License & Credits

See the [LICENSE](LICENSE) file for details.  
Built for Python 3.8+ natively on Windows 10/11 environments.
