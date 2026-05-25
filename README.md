# AWE Polar Project

[![CI](https://github.com/PhelaPoscam/AWE_Polar_Project/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/PhelaPoscam/AWE_Polar_Project/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A real-time stress monitoring and physiological visualization system using **Polar H10, Verity Sense, and Grit X Pro devices**. The project offers real-time monitoring, machine-learning-based stress detection, and a reactive Streamlit dashboard with live waveform charts and LLM-powered insights.

---

## 🚀 Quick Start

### 1. Installation

**Requirements:** Python 3.8+, Windows 10/11 (Bluetooth capable).

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```
_Optional: Add your `OPENAI_API_KEY` to `.env` to enable LLM insights in the dashboard._

### 2. Streamlit Dashboard & Monitoring
Launch the real-time AI dashboard:
```bash
streamlit run src/awe_polar/app_streamlit.py
```
> **Tip:** You can test all dashboard tabs and high-frequency waveforms without hardware using the mock flag: `streamlit run src/awe_polar/app_streamlit.py -- --mock=1`

---

## ✨ Key Features

- **Multi-Device Support**: Captures raw physiological telemetry from the Polar H10 chest strap, Polar Verity Sense optical sensor, and Polar Grit X Pro smartwatch.
- **High-Frequency Waveforms**: Live streaming and rendering of ECG electrical signals (130Hz), PPG optical pulse waves (55Hz), and IMU kinematics (3-axis Accelerometer, Gyroscope, and Magnetometer).
- **Stress & HRV Analysis**: Dynamic calculation of RMSSD from R-R intervals (heart rate variability) and optical PPI data feed.
- **Machine Learning**: Predicts stress levels in real time using Random Forest and Gradient Boosting models.
- **Interactive UI Layout**: Premium dashboard layout featuring tabs for Overview (HR/HRV), Live ECG Waveform, Live PPG Optical Pulse, and 3-axis IMU Kinematics.
- **Asynchronous GUI & LLM**: Streamlit dashboard runs on background worker threads to keep LLM chatboxes and Live gauge charts completely fluid.

---

## 📂 Project Structure

```text
AWE_Polar_Project/
├── src/awe_polar/
│   ├── app_streamlit.py       # Main ML + LLM Dashboard (tabbed waveforms & kinematics)
│   ├── connector/             # BLE Device connection and data streaming layer
│   ├── reader/                # Real-time data reading and ML stress inference logic
│   └── train_model.py         # ML pipeline
├── scripts/                   # CLI Tools (downloading datasets, inference, training)
├── tests/                     # 51 verified unit tests (pytest)
├── data/                      # Dataset files and logs
├── models/                    # Pickled ML models and scalers
└── docs/                      # Project guides
```

---

## 📚 Technical Documentation

*   **Contributing to AWE:** [Development Standards](docs/contributing.md)

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
Built for Python 3.8+ natively on Windows 10/11 environments. ML datasets utilize references from WESAD, SWELL, and UBFC-Phys.
