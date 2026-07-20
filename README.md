# Polar BLE Python SDK

[![CI](https://github.com/PhelaPoscam/Polar-Python-SDK/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/PhelaPoscam/Polar-Python-SDK/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/polar-ble-sdk.svg)](https://pypi.org/project/polar-ble-sdk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)

An open-source Python SDK for connecting, monitoring, and capturing raw physiological and IMU data from Polar BLE devices (H10, Verity Sense, Vantage/Grit watches).

---

## Quick Start

**Requirements:** Python 3.10+, Windows 10/11 (Bluetooth capable).

### Install from PyPI
```bash
pip install polar-ble-sdk
```

### Local install (for CLI tools)
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

### CLI Dashboard
```bash
monitor-polar
```

Monitor a specific device:
```bash
monitor-polar --device "Vantage"
```

Dual-device dashboard (H10 + Sense):
```bash
python scripts/monitor_dual_polar.py
```

---

## Project Structure

```text
Polar-Python-SDK/
├── src/polar_ble_sdk/
│   ├── cli.py                        # Console dashboard CLI entrypoint
│   ├── dashboard_utils.py            # Shared metrics (RMSSD, battery, sparkline, CSV logger)
│   └── connector/
│       ├── ble_discovery.py          # BLE scanner and device resolution
│       ├── schemas.py                # SignalPacket data model
│       ├── stream/                   # Device modules (Base, H10, VeritySense, Watch)
│       └── exporters/                # Async queue sink and data exporters
├── scripts/
│   ├── monitor_dual_polar.py         # Dual-device live terminal dashboard
│   ├── monitor_polar_terminal.py     # CLI dashboard wrapper
│   ├── connect_polar.py              # Simple stream testing script
│   ├── scan_ble.py                   # BLE device scanner
│   └── pair_watch.ps1                # Windows WinRT BLE pairing helper
└── tests/                            # Verified unit test suite (pytest)
```

---

## SDK Usage

```python
import asyncio
from polar_ble_sdk import discover_polar_device, create_polar_connector


def hr_callback(data):
    hr, rr_intervals = data
    print(f"HR: {hr} BPM, RR: {rr_intervals}")


async def main():
    device = await discover_polar_device(timeout=20.0)
    conn = create_polar_connector(device, callback=hr_callback)
    await conn.start_notify()
    await asyncio.sleep(60)  # stream for 60 seconds
    await conn.stop_notify()


asyncio.run(main())
```

---

## API Reference

### Discovery

| Function | Description |
|----------|-------------|
| `discover_polar_device(target=None, timeout=20.0)` | Find a Polar BLE device. Returns early for known Polar sensors. |
| `discover_dual_polar_devices(h10_target=None, sense_target=None, timeout=10.0)` | Scan for H10 + Verity Sense simultaneously. |

### Connector

| Function | Description |
|----------|-------------|
| `create_polar_connector(device, **callbacks)` | Create the right connector class based on device name. |

Callbacks: `callback` (HR+RR), `ecg_callback`, `ppg_callback`, `acc_callback`, `gyro_callback`, `mag_callback`, `ppi_callback`.

### Data Model

```python
@dataclass
class SignalPacket:
    timestamp: float
    source: str
    subject_id: str | None
    signals: dict
    features: dict
```

---

## Sensor Sampling Frequencies

| Device | Stream | Max Rate |
|--------|--------|----------|
| H10 | ECG | 130 Hz |
| H10 | ACC | 25–200 Hz |
| Verity Sense | PPG | 55 Hz |
| Verity Sense | ACC/GYRO | 52 Hz |
| Verity Sense | MAG | 10–100 Hz |
| Watches | PPG | up to 135 Hz |
| Watches | ACC/GYRO | up to 208 Hz |

---

## CLI Tools & Commands

This SDK provides several command-line tools for real-time monitoring, protocol inspection, and raw CSV data logging.

### Available Tools

| Tool / Script | Command | Description |
|---|---|---|
| **Single-Device Dashboard** | `monitor-polar`<br>*(or `python scripts/monitor_polar_terminal.py`)* | Rich live terminal dashboard showing real-time HR, RR intervals, ECG/PPG/IMU streams, sparkline trends, and hotkey markers. Logs 1 Hz summary or full raw streams to CSV. |
| **Dual-Device Dashboard** | `python scripts/monitor_dual_polar.py` | Simultaneous live monitoring of both a **Polar H10** and **Verity Sense**. Shows side-by-side stream status and records synchronized 1 Hz summary or full raw CSV logs. |
| **Low-Level PMD Utility** | `python -m polar_ble_sdk._pmd <subcommand>` | Direct protocol interaction tool. Supports subcommands:<br>• `scan`: Scan for nearby Polar devices<br>• `inspect --address <MAC>`: Query available GATT PMD features and stream settings<br>• `stream --address <MAC> -s <hr/ecg/acc/...>`: Stream raw PMD packets |
| **BLE Scanner** | `python scripts/scan_ble.py` | Quick discovery utility to scan for all nearby Bluetooth Low Energy devices and display MAC addresses/names. |
| **Simple Stream Tester** | `python scripts/connect_polar.py` | Minimal testing script demonstrating basic connection and raw callback stream printing. |
| **Windows Pairing Helper** | `.\scripts\pair_watch.ps1` | PowerShell helper script to assist with Windows WinRT Bluetooth pairing for Polar watches. |

---

### Common Command-Line Flags

#### `monitor-polar` (Single-Device Dashboard)
| Flag | Description | Example |
|---|---|---|
| `--device` | Target device name substring or exact MAC address. | `monitor-polar --device "H10"` |
| `--type` | Force device type (`h10` or `sense`) and default stream sets. | `monitor-polar --type h10` |
| `--streams` | Comma-separated list of streams to enable (`hr,ecg,acc,ppg,ppi,gyro,mag`). | `--streams hr,ecg,acc` |
| `--log-full` | Enable high-speed, full-resolution raw CSV logs for all active sensor streams. | `monitor-polar --log-full` |
| `--csv` | Custom file path for the 1 Hz summary CSV log. | `--csv data/my_session.csv` |
| `--no-log` | Disable all CSV logging completely. | `monitor-polar --no-log` |
| `--markers` | Define custom hotkey event markers (`KEY=LABEL`). Default: `SPACE=Event, S=Start, B=Baseline, R=Recovery`. | `--markers "SPACE=Jump,S=Sprint"` |
| `--<sensor>-rate` | Override specific sensor sampling rate (e.g., `--ecg-rate 130`, `--acc-rate 200`). | `--ecg-rate 130` |

#### `scripts/monitor_dual_polar.py` (Dual-Device Dashboard)
| Flag | Description | Example |
|---|---|---|
| `--h10` | Target MAC address or name for the Polar H10. | `--h10 "Polar H10 12345678"` |
| `--sense` | Target MAC address or name for the Verity Sense. | `--sense "Polar Sense 87654321"` |
| `--log-full` | Enable full-resolution raw CSV logs for both H10 (`data/dual/.../h10/raw/`) and Sense (`data/dual/.../sense/raw/`). | `python scripts/monitor_dual_polar.py --log-full` |
| `--no-log` | Disable summary and full CSV logging. | `python scripts/monitor_dual_polar.py --no-log` |

---

## Testing

```bash
pytest tests/ -v
```

---

## Acknowledgements & Disclaimer

This project builds upon and draws inspiration from the following open-source resources:
- [zHElEARN/polar-python](https://github.com/zHElEARN/polar-python)
- [polarofficial/polar-ble-sdk](https://github.com/polarofficial/polar-ble-sdk)

> [!IMPORTANT]
> **Trademark Disclaimer:** This project is an unofficial, third-party open-source library. It is not affiliated with, endorsed by, or certified by Polar Electro Oy.

