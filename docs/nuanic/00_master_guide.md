# Nuanic Integration Master Guide

Unified reference for Nuanic ring setup, CLI usage, packet decoding, EDA analysis, troubleshooting, and historical investigation notes.

This document consolidates content from:
- `01_quick_start.md`
- `CLI.md`
- `02_module_guide.md`
- `03_eda_analysis_guide.md`
- `04_hex_decoding_guide.md`
- `05_analysis_report.md`
- `troubleshooting/README.md`
- `troubleshooting/action_plan.md`
- `troubleshooting/eda_analysis.md`
- `troubleshooting/eda_quick_fix.md`
- `troubleshooting/cleanup_summary.md`

## 1. Current Operational Baseline

Nuanic integration captures and displays:
- IMU stream (ACC_X, ACC_Y, ACC_Z)
- Stress metric (DNE-derived)
- EDA-derived payload and waveform statistics

### Core data mapping
- Stress characteristic UUID: `468f2717-6a7d-46f9-9eb7-f92aab208bae`
- IMU characteristic UUID: `d306262b-c8c9-4c4b-9050-3a41dea706e5`
- 92-byte physiology packet:
  - Byte 14: stress raw (`0-255`) -> scaled to `0-100%`
  - Bytes 15-91: 77-byte physiology payload (EDA/PPG-related waveform bytes)
- 16-byte IMU packet:
  - Bytes 8-9: ACC_X (int16)
  - Bytes 10-11: ACC_Y (int16)
  - Bytes 12-13: ACC_Z (int16)
  - Byte 14: signal quality indicator

### BLE/discovery notes
- Device discovery is name-based (`Nuanic`) due to rotating/private BLE addresses.
- Pairwise/docked workflows can have short advertising windows.
- Connection stability depends on retry logic in connector flow.

## 2. Quick Start

## 2.1 Environment setup
```bash
cd "c:\TUNI - Projects\Python Project\AWE_Polar_Project"
.\.venv313\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2.2 Recommended monitor run
```bash
python scripts/nuanic_monitor_cli.py --duration 60
```

What one run does:
- Connects to a Nuanic ring (interactive selection or direct address)
- Subscribes to streaming data
- Shows live monitoring output
- Writes CSV logs in `data/nuanic_logs/`

## 2.3 Logging-focused run
```bash
python scripts/nuanic_logger_cli.py --duration 300
```

## 2.4 CSV analysis run
```bash
python scripts/nuanic_analyzer_cli.py data/nuanic_logs/nuanic_stress_YYYY-MM-DD_HH-MM-SS.csv
```

## 2.5 BLE diagnostics (discovery + profiling)
```bash
python scripts/discover_nuanic_services.py --ring-addr <MAC>
```

## 2.6 Legacy compatibility command path (historical)
Earlier docs also reference:
```bash
python scripts/ble/nuanic_monitor.py --duration 60
python scripts/ble/log_nuanic_dual_stream.py --duration 60
python scripts/ble/analyze_nuanic_data.py data/nuanic_logs/nuanic_stress_*.csv
```
Use these only if your local tree still contains `scripts/ble/` equivalents.

## 3. CLI Reference

## 3.1 `nuanic_monitor_cli.py` (real-time monitoring)
```bash
python scripts/nuanic_monitor_cli.py
python scripts/nuanic_monitor_cli.py --duration 60
python scripts/nuanic_monitor_cli.py --list-rings
python scripts/nuanic_monitor_cli.py --ring-addr 58:A3:D0:95:DF:2D --duration 30
```

Options:
- `--duration SECONDS` (default: unlimited)
- `--log-dir PATH` (default: `data/nuanic_logs`)
- `--imu-refresh N` (default: 5)
- `--no-clear`
- `--ring-addr ADDR`
- `--list-rings`

## 3.2 `nuanic_logger_cli.py` (lightweight logging)
```bash
python scripts/nuanic_logger_cli.py
python scripts/nuanic_logger_cli.py --duration 300
python scripts/nuanic_logger_cli.py --list-rings
python scripts/nuanic_logger_cli.py --ring-addr 58:A3:D0:95:DF:2D --duration 60
```

Options:
- `--duration SECONDS`
- `--log-dir PATH`
- `--ring-addr ADDR`
- `--list-rings`

## 3.3 `nuanic_analyzer_cli.py` (file analysis)
```bash
python scripts/nuanic_analyzer_cli.py data/nuanic_logs/nuanic_stress_2026-03-05_15-45-19.csv
```

Typical output includes:
- Session duration and timestamps
- Stress min/max/mean and peaks
- EDA channel activity and simple correlation indicators
- Follow-up analysis recommendations

## 3.4 Ring selection behavior
Without `--ring-addr`:
1. Scan available Nuanic rings
2. Auto-select if exactly one is found
3. Show menu if multiple rings are found
4. Select by index or quit

## 4. Python API Reference

## 4.1 Module layout
`src/awe_polar/nuanic_ring/`
- `connector.py`: BLE discovery and connection
- `monitor.py`: multi-stream monitoring
- `logger.py`: data logging
- `data_analysis.py`: analysis utilities (project-dependent)
- `eda_analyzer.py`: EDA-specific analysis

## 4.2 Connector example
```python
from awe_polar.nuanic_ring import NuanicConnector

connector = NuanicConnector()
if await connector.connect():
    battery = await connector.read_battery()
    print(f"Battery: {battery}%")
```

## 4.3 Monitor example
```python
from awe_polar.nuanic_ring import NuanicMonitor

monitor = NuanicMonitor()
await monitor.start_monitoring()
stress = monitor.get_current_stress()  # 0-100%
```

## 4.4 Logger example
```python
from awe_polar.nuanic_ring import NuanicDataLogger

logger = NuanicDataLogger()
await logger.start_logging(duration_seconds=300)
```

## 4.5 EDA analyzer example
```python
from awe_polar.nuanic_ring.eda_analyzer import NuanicEDAAnalyzer

analyzer = NuanicEDAAnalyzer()
stats = analyzer.add_reading(eda_value)
print(analyzer.get_interpretation(stats))
```

## 4.6 MAC dynamics check
```python
import asyncio
from awe_polar.nuanic_ring import NuanicConnector

async def check_macs():
    c = NuanicConnector()
    result = await c.check_mac_address_dynamic(num_scans=5)
    print(f"Is Dynamic: {result['is_dynamic']}")
    print(f"Addresses: {result['unique_addresses']}")

asyncio.run(check_macs())
```

## 5. Packet and Hex Decoding

## 5.1 Packet overview
Ring transmits 92-byte physiology packets around ~1 Hz.

### Example packet (real capture)
```text
f75e46b99c010000ef7a6f415f7dff7aef410f7caf7b8f41ff7d5f7b7f41ff7c7f7b7f416f7d4f5fff4d3f94cf61af5cff97bf59bf56cf8d4f805f494f935f62df578f9c3f644f5a0fad7f6b0f720fba5f5f7f626fafdf569f6e8fb0
```

### Breakdown
- Bytes 0-3: timestamp/counter (`<I`, little-endian)
- Bytes 4-7: protocol/metadata flags
- Bytes 8-13: unknown header block
- Byte 14: stress raw (`0-255`)
- Bytes 15-91: 77-byte waveform block (EDA/PPG encoded stream)

## 5.2 Stress conversion
```python
stress_percent = (stress_raw / 255) * 100
```

Examples:
- `0x00` -> 0%
- `0x40` -> 25.1%
- `0x80` -> 50.2%
- `0xC0` -> 75.3%
- `0xFF` -> 100%

## 5.3 Timestamp decoding
```python
import struct
hex_bytes = bytes.fromhex("f75e46b9")
timestamp = struct.unpack("<I", hex_bytes)[0]
```

## 5.4 Decoding bytes 15-91 as 16-bit samples
```python
import struct

eda_bytes = bytes.fromhex(eda_hex)
samples = []
for i in range(0, len(eda_bytes) - 1, 2):
    value = struct.unpack("<h", eda_bytes[i:i+2])[0]
    samples.append(value)
```

Note:
- 77 bytes corresponds to 38 complete 16-bit samples plus 1 trailing byte.
- Some docs label this block as EDA; other notes describe combined EDA/PPG payload.
- Treat exact channel semantics as implementation-specific until validated per firmware/revision.

## 5.5 Full packet decoder example
```python
import struct

def decode_nuanic_packet(hex_string: str) -> dict:
    data = bytes.fromhex(hex_string)
    if len(data) != 92:
        raise ValueError(f"Expected 92 bytes, got {len(data)}")

    timestamp_us = struct.unpack("<I", data[0:4])[0]
    stress_raw = data[14]
    stress_percent = (stress_raw / 255) * 100

    eda_samples = []
    for i in range(15, 91, 2):
        sample = struct.unpack("<h", data[i:i+2])[0]
        eda_samples.append(sample)

    return {
        "timestamp_elapsed_s": timestamp_us / 1_000_000,
        "stress_raw": stress_raw,
        "stress_percent": stress_percent,
        "eda_sample_count": len(eda_samples),
        "eda_samples": eda_samples,
        "eda_mean": sum(eda_samples) / len(eda_samples) if eda_samples else 0,
    }
```

## 6. EDA Interpretation and Analysis

## 6.1 EDA fundamentals
- EDA (GSR) tracks skin conductance changes linked to sympathetic activation.
- Stress/arousal can appear within 1-3 seconds after triggers.

## 6.2 Components
- Tonic (baseline): slow drift over minutes/hours
- Phasic: event-driven short changes
- SCR: rise + recovery pattern

## 6.3 Metric guidance
- Peak rate (peaks/min):
  - `<1`: very low arousal
  - `1-2`: low
  - `2-5`: moderate
  - `5-10`: high
  - `>10`: very high
- Amplitude (example heuristics):
  - `<0.5 uS`: minimal
  - `0.5-2 uS`: mild
  - `2-5 uS`: moderate
  - `>5 uS`: strong

## 6.4 Workflow
1. Capture raw logs.
2. Parse `eda_hex` bytes.
3. Compute baseline and phasic signal.
4. Detect peaks from baseline+threshold.
5. Assess rise/recovery timing.
6. Correlate against stress and context (movement, task events).

### Example snippets
```python
# baseline EMA
analyzer.baseline = alpha * current_value + (1 - alpha) * analyzer.baseline

# phasic component
phasic = current_eda - baseline

# simple peak test
is_peak = current_value > (mean + std_dev)
```

## 6.5 Data fusion concept
Use joint interpretation of HR/HRV, stress %, EDA peaks, and IMU context.

Example table (illustrative):
- 14:23, HR 72, stress 45, no EDA peak -> relaxed
- 14:24, HR 78, stress 62, EDA peak -> mild engagement
- 14:25, HR 85, stress 78, EDA peak -> elevated stress
- 14:26, HR 92, stress 91, EDA peak -> high stress moment
- 14:27, HR 88, stress 72, recovering -> resolution phase

## 6.6 Artifacts and caveats
- Motion artifacts can create false spikes.
- Baseline drift may be physiological or sensor/environmental.
- Packet dropouts indicate transport instability.
- Saturation/clipping can hide true peak amplitudes.

## 7. Session Findings and Reports (Consolidated)

## 7.1 Dual-stream architecture findings
A major report identified two simultaneous streams:
- `d306262b`: ~15.87 Hz, 16-byte IMU packets
- `468f2717`: ~1.12 Hz, 92-byte physiology packets
- Effective interleaving near 16.8 Hz total

## 7.2 IMU verification findings
- ACC fields in bytes 8-13 behaved as expected (signed int16).
- Stationary vs movement variance showed large spread increase under motion.

## 7.3 Stress calibration behavior (DNE)
Observed behavior in session report:
- Initial 30-120 seconds can fluctuate strongly.
- Values settle after baseline calibration period.
- Recommendation: ignore early warm-up interval for interpretation.

## 7.4 Correlation findings (report-specific)
Reported low linear correlation magnitudes among movement, stress, and EDA in calm-session data, suggesting partial independence and context dependence.

## 7.5 Data quality references
- EDA present in most packets in successful sessions.
- Typical logged columns include:
  - `timestamp`
  - `stress_raw`
  - `stress_percent`
  - `eda_hex`
  - `full_packet_hex`

## 8. Troubleshooting and Contradictory Historical Notes

The source docs include two contradictory troubleshooting narratives. Both are preserved here for context.

## 8.1 Narrative A: Connection blocked on real ring (historical)
- Claimed wrong-ring testing and timeout on actual target ring.
- Claimed uncertainty about actual stress characteristic.
- Action plan focused on fixing connection and performing service discovery first.

## 8.2 Narrative B: EDA capture works with monitor (historical)
- Claimed issue was logger choice (`NuanicDataLogger`) vs full monitor.
- Claimed monitor path successfully captured non-zero EDA payloads.
- Recommended using monitor workflow for reliable logging.

## 8.3 Practical reconciliation
When these conflicts appear in legacy logs/docs:
1. Validate against current code paths and scripts present in repository.
2. Re-run one controlled capture with current monitor CLI.
3. Confirm whether `eda_hex` is non-zero across session packets.
4. If zero-only payloads persist, perform characteristic-level diagnostics.

## 8.4 Common troubleshooting checklist
- Ring not found:
  - Ensure ring is active and nearby.
  - Ensure Bluetooth is enabled.
  - Close competing Bluetooth apps.
- Connection timeout:
  - Retry once.
  - Toggle Bluetooth adapter and retry.
  - Re-pair in OS Bluetooth settings if needed.
- Static axis values:
  - Orientation can make one axis appear stable.
  - Validate under varied motion.
- EDA all zeros:
  - Confirm script path (monitor vs minimal logger).
  - Confirm packet source characteristic(s).
  - Capture diagnostics before changing parser assumptions.

## 9. File/Script Evolution Notes

Historical docs mention moved or archived scripts (`scripts/ble/archive/`) and removed experiments. Treat those references as historical unless files exist in current workspace.

Current known script set (from present tree):
- `scripts/nuanic_monitor_cli.py`
- `scripts/nuanic_logger_cli.py`
- `scripts/nuanic_analyzer_cli.py`
- `scripts/discover_nuanic_services.py` (unified diagnostics)
- `scripts/analysis/analyze_nuanic_stream.py`

## 10. Testing and Quality Notes (Historical Claims)

One cleanup summary reports:
- 33/33 tests passing for Nuanic-related module tests.
- coverage across connector, monitor, logger, analyzer, and integration checks.

Because the test inventory in that summary does not fully match current filenames, re-run current test suite to validate present status.

## 11. Recommended Next Steps

1. Keep a single source of truth for operational docs (this file).
2. Keep a short top-level `README.md` as an index into this guide.
3. Re-verify one fresh capture and one fresh analysis run.
4. Record validated script paths and packet assumptions in this guide only.
5. Keep contradictory historical claims in an explicit "Historical Notes" section instead of separate troubleshooting files.

## Appendix A: CSV Output Patterns

Historical and current docs mention these output shapes:

### Stress-centric CSV
```text
timestamp,stress_raw,stress_percent,eda_hex,full_packet_hex
2024-01-15T14:23:45.123456,127,49.8,a1b2c3d4...,<full packet hex>
```

### Extended stress CSV variant
```text
timestamp,elapsed_ms,stress_raw,stress_percent,eda_hex,full_packet_hex
2026-03-04T16:20:53.946234,17036,111,43.5,747fb47fa06f...,607139b99c010000...
```

### Additional files sometimes produced
- `nuanic_imu_TIMESTAMP.csv`
- `nuanic_raw_eda_TIMESTAMP.csv` (if separate stream is available)

## Appendix B: Minimal Operational Commands

```bash
# List rings
python scripts/nuanic_monitor_cli.py --list-rings

# Monitor for 60 seconds
python scripts/nuanic_monitor_cli.py --duration 60

# Monitor without creating CSV files
python scripts/nuanic_monitor_cli.py --duration 60 --no-log

# Live waveform visualization (stress payload + raw EDA)
python scripts/nuanic_monitor_cli.py --waveform --window-seconds 10

# Lightweight logging
python scripts/nuanic_logger_cli.py --duration 300

# Analyze a captured session
python scripts/nuanic_analyzer_cli.py data/nuanic_logs/nuanic_stress_YYYY-MM-DD_HH-MM-SS.csv

# BLE diagnostics and service inspection
python scripts/discover_nuanic_services.py --ring-addr <MAC>
```
