# Nuanic Quick Start

## 1) Environment
```bash
cd "c:\TUNI - Projects\Python Project\AWE_Polar_Project"
.\.venv313\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2) Run the monitor (recommended)
```bash
python scripts/ble/nuanic_monitor.py --duration 60
```

What it does in one run:
- Connects to the Nuanic ring with retry recovery
- Subscribes to IMU and stress characteristics
- Shows live Stress + EDA stats + IMU X/Y/Z in terminal
- Saves CSV logs in `data/nuanic_logs/`

## 3) Compatibility command (legacy name)
```bash
python scripts/ble/log_nuanic_dual_stream.py --duration 60
```

## 4) Analyze captured logs
```bash
python scripts/ble/analyze_nuanic_data.py data/nuanic_logs/nuanic_stress_*.csv
```

## Expected Outputs
- `data/nuanic_logs/nuanic_imu_YYYY-MM-DD_HH-MM-SS.csv`
- `data/nuanic_logs/nuanic_stress_YYYY-MM-DD_HH-MM-SS.csv`

## Troubleshooting
- Ring not found:
  - Ensure ring is worn and nearby
  - Ensure Bluetooth is enabled
  - Close other apps that may hold the ring connection
- Connection timeout:
  - Retry command once (connector now performs internal retries)
  - If needed, toggle Bluetooth off/on and run again
- Data seems static on one axis:
  - Normal for orientation-dependent gravity projection; check ACC_X/ACC_Y/ACC_Z during varied movements

## Current Script Layout (`scripts/ble`)
- `nuanic_monitor.py` (primary monolithic flow)
- `log_nuanic_dual_stream.py` (compatibility wrapper)
- `analyze_nuanic_data.py` (analysis)
- `archive/` (legacy discovery/test scripts)
