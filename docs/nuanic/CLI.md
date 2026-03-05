# Nuanic Ring CLI Tools

Clean command-line interface for Nuanic ring operations. All tools provide interactive ring selection and support multiple rings.

## Overview

| Tool | Purpose | Output |
|------|---------|--------|
| `nuanic_monitor_cli.py` | Real-time monitoring | Live display + CSV logs |
| `nuanic_logger_cli.py` | Data logging only | CSV logs (lightweight) |
| `nuanic_analyzer_cli.py` | Analyze CSV files | Statistics & analysis |
| `discover_nuanic_services.py` | BLE debugging | Service details |

## Tools

### `nuanic_monitor_cli.py` - Real-Time Monitoring
Monitor IMU, Stress, and EDA data in real-time with live display and CSV logging.

```bash
python scripts/nuanic_monitor_cli.py                              # Scan & select ring
python scripts/nuanic_monitor_cli.py --duration 60               # Run for 60 seconds
python scripts/nuanic_monitor_cli.py --list-rings                # List available rings
python scripts/nuanic_monitor_cli.py --ring-addr 58:A3:D0:95:DF:2D --duration 30
```

**Options:**
- `--duration SECONDS` - Monitor duration (default: unlimited)
- `--log-dir PATH` - Directory for CSV files (default: data/nuanic_logs)
- `--imu-refresh N` - Refresh display every N IMU packets (default: 5)
- `--no-clear` - Don't clear terminal on refresh
- `--ring-addr ADDR` - Connect to specific ring (skip selection menu)
- `--list-rings` - List available rings and exit

### `nuanic_logger_cli.py` - Data Logging
Log stress and EDA data to CSV without real-time display (lightweight).

```bash
python scripts/nuanic_logger_cli.py                              # Scan & select ring
python scripts/nuanic_logger_cli.py --duration 300              # Log for 5 minutes
python scripts/nuanic_logger_cli.py --list-rings                # List available rings
python scripts/nuanic_logger_cli.py --ring-addr 58:A3:D0:95:DF:2D --duration 60
```

**Options:**
- `--duration SECONDS` - Logging duration (default: unlimited)
- `--log-dir PATH` - Directory for CSV files (default: data/nuanic_logs)
- `--ring-addr ADDR` - Connect to specific ring (skip selection menu)
- `--list-rings` - List available rings and exit

### `nuanic_analyzer_cli.py` - Data Analysis
Analyze logged CSV files with stress statistics, EDA channel detection, and peak analysis.

```bash
python scripts/nuanic_analyzer_cli.py data/nuanic_logs/nuanic_stress_2026-03-05_15-45-19.csv
```

**Output:**
- Session information (duration, timestamps)
- Stress statistics (min/max/mean, peaks)
- EDA channel analysis (active channels, correlations)
- Recommendations for further analysis

### `discover_nuanic_services.py` - Service Discovery
Discover BLE services and characteristics on a connected ring (debugging tool).

```bash
python scripts/discover_nuanic_services.py
```

## Features

✓ **Dynamic Ring Selection** - Interactive menu for multiple rings
✓ **Auto-Select** - Automatically selects if only one ring available
✓ **No Hardcoded Addresses** - Works with any ring, unlimited devices
✓ **Real-Time Monitoring** - Live visualization with IMU + Stress + EDA
✓ **Data Logging** - CSV exports for analysis
✓ **Analysis Tools** - Statistical analysis and peak detection

## Ring Selection Flow

When you run a CLI tool without `--ring-addr`:
1. Scans for available Nuanic rings
2. If 1 ring found → Auto-select (no menu)
3. If 2+ rings found → Show numbered menu
4. Select ring by number or 'q' to cancel
5. Connect and start operation

## Examples

### Monitor two rings sequentially
```bash
# First ring
python scripts/nuanic_monitor_cli.py --duration 60

# Second ring - will prompt to select again
python scripts/nuanic_monitor_cli.py --duration 60
```

### Log from specific ring
```bash
python scripts/nuanic_logger_cli.py --ring-addr 58:A3:D0:95:DF:2D --duration 300
```

### Analyze logged data
```bash
python scripts/nuanic_analyzer_cli.py data/nuanic_logs/nuanic_stress_2026-03-05_15-45-19.csv
```

### Check ring MAC addresses
```python
import asyncio
from src.awe_polar.nuanic_ring.connector import NuanicConnector

async def check_macs():
    c = NuanicConnector()
    result = await c.check_mac_address_dynamic(num_scans=5)
    print(f"Is Dynamic: {result['is_dynamic']}")
    print(f"Addresses: {result['unique_addresses']}")

asyncio.run(check_macs())
```

## Python API

### Using from Code

```python
from src.awe_polar.nuanic_ring.monitor import NuanicMonitor
from src.awe_polar.nuanic_ring.logger import NuanicDataLogger
from src.awe_polar.nuanic_ring.connector import NuanicConnector

# Monitor with interactive ring selection
monitor = NuanicMonitor()
await monitor.run()

# Logger with ring selection
logger = NuanicDataLogger()
await logger.start_logging(duration_seconds=60)

# List all available rings
connector = NuanicConnector()
rings = await connector.list_available_rings()
for ring in rings:
    print(f"{ring['name']} - {ring['address']}")

# Check MAC address stability
result = await connector.check_mac_address_dynamic(num_scans=5)
print(f"MAC is {'DYNAMIC' if result['is_dynamic'] else 'STATIC'}")
```

See [Module Guide](02_module_guide.md) for detailed API documentation.

## Project Structure

```
scripts/
├── nuanic_monitor_cli.py          ← Real-time monitoring CLI
├── nuanic_logger_cli.py           ← Data logging CLI  
├── nuanic_analyzer_cli.py         ← Data analysis CLI
├── discover_nuanic_services.py    ← BLE service discovery

src/awe_polar/nuanic_ring/
├── connector.py                   ← BLE connection & discovery
├── monitor.py                     ← Real-time monitoring
├── logger.py                      ← Data logging
├── data_analysis.py               ← Analysis functions
├── eda_analyzer.py                ← EDA analysis tools
└── examples.py                    ← Python examples
```

## Troubleshooting

**No rings found**
- Ensure all Nuanic rings are powered on
- Check BLE drivers are installed correctly
- Try: `python scripts/discover_nuanic_services.py`

**Connection failures**
- Remove ring from Bluetooth settings and reconnect
- Restart Bluetooth on your system
- Check ring battery level

**MAC address issues**
- Rings with static MACs: Use `--ring-addr` for consistent connection
- Rings with dynamic MACs: Selection menu will show available devices

## See Also

- [Quick Start Guide](01_quick_start.md)
- [Module API Guide](02_module_guide.md)
- [EDA Analysis Guide](03_eda_analysis_guide.md)
- [Hex Decoding Guide](04_hex_decoding_guide.md)
