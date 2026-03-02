# Nuanic Integration Docs

## Current Status
Nuanic integration is active with a monolithic BLE monitor that captures and displays:
- IMU stream (ACC_X, ACC_Y, ACC_Z)
- Stress metric
- EDA-derived waveform statistics

## Production CLI Flow
Use these scripts in `scripts/ble/`:

1. `nuanic_monitor.py` (primary)
```bash
python scripts/ble/nuanic_monitor.py --duration 60
```

2. `log_nuanic_dual_stream.py` (compatibility wrapper)
```bash
python scripts/ble/log_nuanic_dual_stream.py --duration 60
```

3. `analyze_nuanic_data.py` (post-capture CSV analysis)
```bash
python scripts/ble/analyze_nuanic_data.py data/nuanic_logs/nuanic_stress_*.csv
```

Legacy discovery/test scripts were moved to:
- `scripts/ble/archive/`

## Data Mapping (Current Implementation)
- Stress characteristic UUID: `468f2717-6a7d-46f9-9eb7-f92aab208bae`
- IMU characteristic UUID: `d306262b-c8c9-4c4b-9050-3a41dea706e5`

### Physiology packet (92 bytes)
- Byte 14: stress raw (0-255), scaled to 0-100%
- Bytes 15-91: EDA/PPG waveform payload (77 bytes)

### IMU packet (16 bytes)
- Bytes 8-9: ACC_X (int16)
- Bytes 10-11: ACC_Y (int16)
- Bytes 12-13: ACC_Z (int16)
- Byte 14: signal quality indicator

## Related Docs
- `NUANIC_QUICK_START.md` - quick operational steps
- `NUANIC_ANALYSIS_REPORT.md` - technical findings and validation history
- `MODULE_GUIDE.md` - module-level API and usage details
- `PROJECT_ORGANIZATION.md` - structure and file ownership

## Notes
- BLE address can rotate (private addressing), so discovery is name-based (`Nuanic`) with retry logic.
- If connection is unstable, use the updated connector retry flow in `src/awe_polar/nuanic_ring/connector.py`.
