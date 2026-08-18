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
│   ├── __init__.py                   # Public SDK exports (Connection, Metrics, Research)
│   ├── cli.py                        # Console dashboard CLI entrypoint
│   ├── dashboard_utils.py            # Backward-compatibility façade
│   ├── _pmd/                         # Low-level Polar Measurement Data protocol
│   │   ├── device.py                 # PolarDevice Bleak client wrapper
│   │   ├── constants/                # PMD opcodes, error codes, UUIDs, epoch offsets
│   │   ├── models/                   # Strongly typed dataclasses (ECG, PPG, ACC, etc.)
│   │   └── parsers/                  # Bit-level delta compression & SIG HR decoders
│   ├── connector/                    # Device Abstraction Layer
│   │   ├── ble_discovery.py          # Fast BLE scanner & device matcher
│   │   ├── schemas.py                # SignalPacket data contract
│   │   ├── stream/                   # Device modules (Base, H10, VeritySense, Watch)
│   │   └── exporters/                # Async QueueSink and streaming interfaces
│   ├── session/                      # Session Lifecycle & Metadata Management
│   │   ├── session.py                # SessionManager & SessionMetadata (writes session_meta.json)
│   │   └── state.py                  # Thread-safe in-memory device state containers
│   ├── storage/                      # High-Speed Data Logging
│   │   ├── frame_logger.py           # StreamFrameLogger: full-resolution raw CSV logs
│   │   └── summary_logger.py         # CsvLogger: 1 Hz post-processed summary CSV logs
│   ├── metrics/                      # Physiological Signal & Rate Processing
│   │   ├── hrv.py                    # Pure-Python RMSSD, SDNN, pNN50 algorithms
│   │   └── rate_tracker.py           # Real-time sliding-window & session Hz estimators
│   ├── diagnostics/                  # Hardware Telemetry
│   │   ├── battery.py                # Battery reading & periodic update loop
│   │   └── rssi.py                   # BLE RSSI telemetry & frame delta loggers
│   ├── input/                        # User & Experiment Interaction
│   │   └── keyboard.py               # Cross-platform non-blocking hotkey & marker reader
│   ├── ui/                           # Rich Terminal Presentation
│   │   ├── components.py             # Device panels, header strips, and footer info bars
│   │   └── log_panel.py              # Rolling LogPanel & structured severity loggers
│   └── research/                     # Research & Data Science Tools
│       ├── loader.py                 # load_session(): auto-load CSVs + metadata into pandas DataFrames
│       ├── audit.py                  # verify_session_integrity(): dropouts, jitter, rate verification
│       ├── validation.py             # compute_validation_metrics(): Lin's CCC, ICC(2,1), Bland-Altman LoA, WSCV
│       ├── ppg.py                    # Optical PPG filtering, zero-crossing, Welch FFT, and adaptive beat detection
│       └── report.py                 # Automated Markdown cross-validation report and diagnostic Matplotlib figures
├── scripts/
│   ├── monitor_dual_polar.py         # Dual-device live terminal dashboard (H10 + Verity Sense)
│   ├── run_analysis.py               # Cross-device validation & optical waveform analysis CLI
│   ├── monitor_polar_terminal.py     # Single-device CLI dashboard wrapper
│   ├── analyze_hz.py                 # Post-session Hz & signal integrity verifier
│   ├── connect_polar.py              # Simple stream testing script
│   ├── scan_ble.py                   # BLE device scanner
│   └── pair_watch.ps1                # Windows WinRT BLE pairing helper
├── data/                             # Session logs (written by dashboards)
│   └── {device_type}/{session_ts}/   # e.g. h10/20260818_120000 or dual/...
│       ├── session_meta.json         # Standardized session provenance manifest
│       ├── monitor_{ts}.log          # Timestamped plain-text session event log
│       ├── raw/                      # Full-resolution per-stream CSVs (ecg.csv, ppg.csv, ...)
│       └── post-processed/           # 1 Hz summary.csv
└── tests/                            # Verified unit test suite (pytest)
```

---

## SDK Usage

### Live Streaming

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

### Research & Data Analysis

Load an entire recorded session (metadata, 1 Hz summary, and raw high-frequency sensor streams) with one line:

```python
from polar_ble_sdk import load_session, verify_session_integrity

# 1. Load session into structured pandas DataFrames
session = load_session("data/h10/20260818_120000")
print(f"Session: {session.session_id} (Duration: {session.metadata.get('duration_s', 0):.1f}s)")

# 2. Access raw high-frequency streams
ecg_df = session.get_stream("ecg")  # 130 Hz ECG in µV
acc_df = session.get_stream("acc")  # 200 Hz 3-axis Accelerometer + computed ACC_Mag_mG

# 3. Access 1 Hz consolidated summary & markers
summary_df = session.summary
markers = session.markers

# 4. Audit signal integrity and calculate timestamp jitter
audit_report = verify_session_integrity("data/h10/20260818_120000")
print(audit_report)
```

---

## API Reference

### Discovery

| Function | Description |
|---|---|
| `discover_polar_device(target=None, timeout=20.0)` | Find a Polar BLE device. Returns early for known Polar sensors. |
| `discover_dual_polar_devices(h10_target=None, sense_target=None, timeout=10.0)` | Scan for H10 + Verity Sense simultaneously. |
| `discover_polar_devices(timeout=5.0)` | List all nearby Polar BLE devices with (name, MAC, device). |

### Connector & Streaming

| Function | Description |
|---|---|
| `create_polar_connector(device, **callbacks)` | Instantiate the right connector (`PolarH10`, `PolarVeritySense`, `PolarWatch`). |

Supported callbacks: `callback` (HR+RR), `ecg_callback`, `ppg_callback`, `acc_callback`, `gyro_callback`, `mag_callback`, `ppi_callback`.

### Research & Metrics

| Class / Function | Description |
|---|---|
| `load_session(path)` | Load single or dual recording sessions into a `PolarSessionData` container with pandas DataFrames. |
| `verify_session_integrity(path)` | Audit sampling rates, inter-sample standard deviation (jitter), and packet gap statistics. |
| `calculate_rmssd(rr_intervals)` | Calculate Root Mean Square of Successive Differences (in ms) from RR/PPI intervals. |
| `calculate_sdnn(rr_intervals)` | Calculate Standard Deviation of NN intervals (in ms). |
| `calculate_pnn50(rr_intervals)` | Calculate percentage of successive intervals differing by > 50 ms. |
| `SessionManager` | Orchestrate session storage, raw frame logging, and audit manifest (`session_meta.json`) serialization. |

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
| Verity Sense | PPG | **135 Hz** (default, SDK mode; 55 Hz without SDK mode) |
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
| `--no-sdk-mode` | **Disable** SDK mode (now the default): PPG falls back to 55 Hz and the Sense's own HR + PPI streams become available. | `monitor-polar --no-sdk-mode` |
| `--sdk-mode` | Explicitly enable SDK mode (already the default). Required for PPG > 55 Hz. | `monitor-polar --sdk-mode --ppg-rate 135` |
| `--ppi` | Enable the Sense PPI stream (only valid with `--no-sdk-mode`; SDK mode disables HR/PPI). | `monitor-polar --no-sdk-mode --ppi` |
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
| `--duration` | Set recording duration in seconds; automatically disconnects and closes cleanly. | `--duration 180` |
| `--log-full` | Enable full-resolution raw CSV logs for both H10 (`data/dual/.../h10/raw/`) and Sense (`data/dual/.../sense/raw/`). | `python scripts/monitor_dual_polar.py --log-full` |
| `--no-log` | Disable summary and full CSV logging. | `python scripts/monitor_dual_polar.py --no-log` |
| `--no-ppi` | Disable the Sense PPI stream (only relevant with `--no-sdk-mode`; SDK mode disables PPI anyway). | `python scripts/monitor_dual_polar.py --no-ppi` |
| `--no-sdk-mode` | Disable SDK mode: PPG falls back to 55 Hz and the Sense's own HR + PPI streams become available. | `python scripts/monitor_dual_polar.py --no-sdk-mode` |
| `--sdk-mode` | Explicitly enable SDK mode (default). Required for 135 Hz raw 4-channel optical PPG. | `python scripts/monitor_dual_polar.py --sdk-mode --ppg-rate 135` |
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

Raw stream files are per-stream CSVs with session-relative timestamps (seconds since the first frame), e.g. `ecg.csv` (`Timestamp_s, uV_Samples`), `acc.csv` (`Timestamp_s, X_mG, Y_mG, Z_mG`), `hr.csv` (`Timestamp_s, HeartRate_BPM, RR_Intervals_ms`). The `ppi.csv` file carries the device's raw PPI quality flags (`Timestamp_s, PPI_ms, ErrEst_ms, HR_BPM, SkinContact, SkinContactSupported`) so analysis can flag the documented "HR fixed to last reliable value when movement detected" mode.

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

### Post-Session Analysis & Cross-Validation

#### 1. Cross-Device Agreement & Statistical Validation (`run_analysis.py`)
Run the unified research validation CLI to audit packet integrity, compute clinical validation metrics (Lin's CCC, ICC(2,1), Bland-Altman LoA, WSCV, MAE, MAPE), extract optical pulse beats, and generate visual markdown reports + diagnostic figures:

```bash
# Auto-detect latest dual session
python scripts/run_analysis.py

# Analyze a specific session
python scripts/run_analysis.py data/dual/20260818_132922
```

Outputs are automatically saved to `data/dual/<session_id>/reports/`:
- `validation_report.md` (Executive summary, limits of agreement, device distribution)
- `bland_altman.png` (95% Bland-Altman Limits of Agreement)
- `time_series_hr.png` (Time-synchronized ECG vs PPG tracking)
- `scatter_correlation.png` (Identity line scatter correlation)

#### 2. Sampling Rate & Frame Integrity Audit (`analyze_hz.py`)
For a fast summary of packet intervals, mean frequencies, and frame gaps:

```bash
# Single-device session
python scripts/analyze_hz.py data/h10/20260806_120000

# Dual-device session
python scripts/analyze_hz.py data/dual/20260818_132922
```
```

---

## Known Issues & TODO

### TODO — Offline PPG-derived HR/RMSSD analysis (**VALIDATED at 135 Hz**)

**Status: WORKING for HR.** The research pipeline (`polar_ble_sdk.research.ppg` and `scripts/run_analysis.py`) derives HR
from the raw Verity Sense PPG signal and cross-validates against the Polar H10.

**Key finding — 55 Hz sampling was the root cause of earlier failures.** At
55 Hz (the non-SDK-mode default), the raw PPG is dominated by a fixed ~104 BPM
(1.73 Hz) beat artifact and the cardiac pulse is not recoverable — every
estimator (FFT, zero-crossing, autocorrelation, peak detection) failed to track
the H10. At **135 Hz** (requires SDK mode) the artifact disappears and the pulse
is clearly present: **zero-crossing HR matches the H10 ECG to MAE 2.46 BPM,
MAPE 3.57%, bias −0.73 BPM** (session `20260811_150741`, n=29 epochs).

**SDK-mode trade-off (Polar-documented):** 135 Hz PPG requires SDK mode, which
**disables the Sense's own HR and PPI streams**. SDK mode is now the default for
Sense monitoring; use `--no-sdk-mode` to fall back to 55 Hz PPG + the Sense's
HR/PPI (needed for RR-interval/RMSSD from the device).

**Remaining work:**
1. Validate on a session with **HR variation** (light activity) to confirm the
   zero-crossing estimator tracks changing HR, not just rest.
2. Improve the PPG-derived RMSSD (peak-based; currently MAE ~26 BPM vs H10).
3. Distinguish "raw optical signal good but firmware locks" (our-PPG-HR tracks
   H10 while Sense-reported HR deviates) from "signal itself bad" (both deviate)
   using the 135 Hz raw PPG — now that the signal is decodable.

**Related state:**
- `scripts/run_analysis.py` (powered by `polar_ble_sdk.research`) performs
  cross-validation metrics + artifact detection; the artifact detector catches the Sense's half-rate
  lock (exact-constant and staircase variants). It also has a raw-PPG-vs-ECG
  section (FFT/ZC estimators) that flagged the 55 Hz failure.
- The Sense PPI→RMSSD fix is in place and verified.
- Default Sense monitoring now: **135 Hz PPG + ACC/GYRO/MAG via SDK mode**.

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

