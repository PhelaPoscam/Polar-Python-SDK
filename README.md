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
│   ├── dashboard_utils.py            # Shared dashboard utils (state, Hz tracking, frame CSV logger)
│   └── connector/
│       ├── ble_discovery.py          # BLE scanner and device resolution
│       ├── schemas.py                # SignalPacket data model
│       ├── stream/                   # Device modules (Base, H10, VeritySense, Watch)
│       └── exporters/                # Async queue sink and data exporters
├── scripts/
│   ├── monitor_dual_polar.py         # Dual-device live terminal dashboard
│   ├── monitor_polar_terminal.py     # CLI dashboard wrapper
│   ├── analyze_hz.py                 # Post-session Hz verification from raw CSVs
│   ├── connect_polar.py              # Simple stream testing script
│   ├── scan_ble.py                   # BLE device scanner
│   └── pair_watch.ps1                # Windows WinRT BLE pairing helper
├── data/                             # Session logs (written by dashboards)
│   └── {device_type}/{session_ts}/   # e.g. h10/20260806_120000 or dual/...
│       ├── raw/                      # Full-resolution per-stream CSVs
│       │   ├── ecg.csv               #   (hr.csv, ppg.csv, acc.csv, ...)
│       │   └── ...
│       └── post-processed/           # 1 Hz summary.csv
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
| **Single-Device Dashboard** | `monitor-polar`<br>*(or `python scripts/monitor_polar_terminal.py`)* | Rich live terminal dashboard showing real-time HR, RR intervals, ECG/PPG/IMU streams, and hotkey markers. Slim identity header, compact info bar, and a rolling event log showing connection/stream/RSSI events. Logs 1 Hz summary or full raw streams to CSV plus a session event log file. Prints a session-end Hz verification table and reports failed streams in the status line. |
| **Dual-Device Dashboard** | `python scripts/monitor_dual_polar.py` | Simultaneous live monitoring of both a **Polar H10** and **Verity Sense**. Side-by-side stream panels with a shared rolling event log (device-prefixed `[H10]`/`[Sense]`). Records synchronized 1 Hz summary or full raw CSV logs plus a session event log file. |
| **Session Hz Verifier** | `python scripts/analyze_hz.py <session_dir>` | Real-world verification that a recorded session collected at the configured rates — reports actual average Hz, sample count, and standard deviation per stream from the raw CSVs. Works on single-device (`.../raw/`) and dual-device (`.../h10/raw/`, `.../sense/raw/`) layouts. |
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
| `--markers` | Define custom hotkey event markers (`KEY=LABEL`). Default: `SPACE=Event, S=Start, B=Baseline, R=Recovery`. **`L` is reserved for the log-level toggle.** | `--markers "SPACE=Jump,S=Sprint"` |
| `--log-level` | Terminal log verbosity: `minimal` (errors only), `moderate` (default, connection + stream events + RSSI), `verbose` (adds per-frame counts, frequent RSSI). Press **L** during monitoring to toggle at runtime. | `monitor-polar --log-level verbose` |
| `--<sensor>-rate` | Override specific sensor sampling rate (e.g., `--ecg-rate 130`, `--acc-rate 200`). | `--ecg-rate 130` |

#### `scripts/monitor_dual_polar.py` (Dual-Device Dashboard)
| Flag | Description | Example |
|---|---|---|
| `--h10` | Target MAC address or name for the Polar H10. | `--h10 "Polar H10 12345678"` |
| `--sense` | Target MAC address or name for the Verity Sense. | `--sense "Polar Sense 87654321"` |
| `--log-full` | Enable full-resolution raw CSV logs for both H10 (`data/dual/.../h10/raw/`) and Sense (`data/dual/.../sense/raw/`). | `python scripts/monitor_dual_polar.py --log-full` |
| `--no-log` | Disable summary and full CSV logging. | `python scripts/monitor_dual_polar.py --no-log` |
| `--log-level` | Terminal log verbosity: `minimal`, `moderate` (default), `verbose`. Press **L** during monitoring to toggle at runtime. | `--log-level verbose` |

---

## Session Data & Hz Verification

### Output Layout

Both dashboards write session data under `data/`, with full-resolution raw CSVs, a 1 Hz summary, and an event log:

| Dashboard | Session dir | Raw streams | Post-processed | Event log |
|---|---|---|---|---|
| `monitor-polar` | `data/{h10\|sense}/{timestamp}/` | `raw/<stream>.csv` | `post-processed/summary.csv` | `monitor_<timestamp>.log` |
| `monitor_dual_polar.py` | `data/dual/{timestamp}/` | `h10/raw/<stream>.csv`, `sense/raw/<stream>.csv` | `h10/post-processed/summary.csv`, `sense/post-processed/summary.csv` | `dual_<timestamp>.log` |

The event log file records every terminal log event (connection, stream start/stop, RSSI, errors, markers) as plain text, one line per event. Useful for post-session debugging.

### Terminal Layout

Both dashboards use a Rich Live display with four sections:

```
┌─ Device Name (AA:BB:CC)  ● connected ────────────┐  ← Slim identity header
│  [HR: 72 BPM]  [RR: 420 380 ms]                  │  ← Data panels
│  Stream    Status    Latest                        │
│  ECG       Active    +1234 µV                     │
│  ...                                               │
│  🔋 85%  ⏱ 142s  📄 1420 rows  ⌨ H:C:L:Q       │  ← Info bar
│ ┌─ Log ────────────────────────────────────────┐   │
│ │ 12:34:01 ● Connected (0.8s setup, 7.4s total)│   │  ← Rolling event log
│ │ 12:34:01 ● ECG stream started                 │   │
│ │ 12:34:02 📡 RSSI: -52 dBm                    │   │
│ └───────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘
```

The log panel fills remaining vertical space. Events are color-coded by severity: green (success), yellow (warning), red (error), dim (info). Press **L** at runtime to toggle between moderate and verbose detail.

Raw stream files are per-stream CSVs with session-relative timestamps (seconds since the first frame), e.g. `ecg.csv` (`Timestamp_s, uV_Samples`), `acc.csv` (`Timestamp_s, X_mG, Y_mG, Z_mG`), `hr.csv` (`Timestamp_s, HeartRate_BPM, RR_Intervals_ms`).

### Stream Status & Failures

On connect, the dashboard status shows `Connected! Streaming data.` when all requested streams start. If any stream fails to start (e.g. unsupported sample rate or device rejection), the status reports which ones, e.g. `Connected. Failed: gyro, mag`.

### Session-End Hz Verification

When a session ends (Ctrl+C), both dashboards print a **Hz verification table** comparing each stream's configured sampling rate against the actual observed rate across the whole session:

```
========================================================
  SESSION HZ VERIFICATION
========================================================
  Stream   Configured   Observed     Match
--------------------------------------------------------
  ecg          130 Hz    130.01 Hz       OK
  acc           52 Hz     52.00 Hz       OK
  ppg           55 Hz     55.00 Hz       OK
========================================================
```

Configured rates come from the device's actual settings (e.g. H10 ECG 130 Hz, H10 ACC 200 Hz; Sense PPG 55 Hz, Sense ACC/GYRO 52 Hz, MAG 20 Hz). A mismatch (`X`) flags a stream that did not deliver its configured rate.

### Post-Session Analysis

For a deeper look (average Hz, sample count, standard deviation), run the offline analyzer on a recorded session:

```bash
# Single-device session
python scripts/analyze_hz.py data/h10/20260806_120000

# Dual-device session
python scripts/analyze_hz.py data/dual/20260806_120000
```

---

## Known Issues & TODO

### TODO — Offline PPG-derived HR/RMSSD analysis (paused)

**Status: paused mid-implementation.** We started building a pipeline
(`analysis/ppg_analysis.py`) to derive HR and RMSSD from the raw Verity Sense
PPG signal (bypassing the Sense's internal, occasionally-faulty optical HR
algorithm) and cross-validate against the Polar H10.

**Why it paused:** the raw PPG in the two recorded sessions is too contaminated
to support reliable beat detection. Signal-quality assessment found:
- Non-stationary baseline: 5 s-block std swings ~200× (1,779 → 388,439)
- Poor pulse SNR (~3.9 amplitude/std, clean PPG is typically >10)
- ACC is stable (mean 1537, std 161), so it's likely contact/pressure variation
  on the armband sensor rather than body motion

Every estimator tried (adaptive peak detection, zero-crossing, FFT
fundamental-picking, autocorrelation) failed to recover the H10's HR from these
sessions — a strong signal that the raw optical data itself is poor, not that
the estimators are wrong.

**To resume:**
1. Record a fresh session with **good armband contact/placement** (the existing
   sessions' PPG is unusable).
2. Re-run `analysis/ppg_analysis.py` on the new session and validate the beat
   detector against the H10.
3. If it works, the payoff: distinguish "raw optical signal good but firmware
   locks" (our-PPG-HR tracks H10 while Sense-reported HR deviates) from "signal
   itself bad" (both deviate).

**Related state:**
- `analysis/run_analysis.py` (cross-validation metrics + artifact detector) is
  complete and tested; the artifact detector catches the Sense's half-rate
  lock (exact-constant and staircase variants).
- The Sense PPI→RMSSD fix (`dashboard_utils.py`) is in place and verified.
- `--no-log-full` now defaults full-resolution raw logging **on**; use it for
  any new session so the raw PPG/ECG/PPI streams are captured.

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

