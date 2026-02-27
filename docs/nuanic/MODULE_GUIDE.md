# Nuanic Ring Integration Module

Complete integration for Nuanic smart ring stress and EDA monitoring.

## Module Structure

```
src/awe_polar/nuanic_ring/
├── __init__.py              # Module exports
├── connector.py             # BLE connection management
├── monitor.py               # Real-time stress monitoring
├── logger.py                # Data logging to CSV
├── eda_analyzer.py         # EDA analysis and interpretation
└── examples.py             # Usage examples
```

## Components

### NuanicConnector - BLE Connection Management
Handles device discovery and GATT communication.

```python
from awe_polar.nuanic_ring import NuanicConnector

connector = NuanicConnector()
if await connector.connect():
    battery = await connector.read_battery()
    print(f"Battery: {battery}%")
```

**Key Features:**
- Auto-discovery by device name "Nuanic"
- Automatic pairing/authentication
- Retry logic for unreliable connections
- Clean disconnect handling

### NuanicMonitor - Real-time Monitoring
Subscribes to notifications and provides stress data.

```python
from awe_polar.nuanic_ring import NuanicMonitor

monitor = NuanicMonitor()
await monitor.start_monitoring()
stress = monitor.get_current_stress()  # 0-100%
```

**Key Features:**
- Stress: Byte 14 of 92-byte packet (0-255) → scaled to 0-100%
- EDA: Bytes 15-91 (77 bytes) of 92-byte packet
- Update rate: ~1 Hz (900-950ms between packets)

### NuanicDataLogger - CSV Data Logging
Logs all readings to timestamped CSV files.

```python
from awe_polar.nuanic_ring import NuanicDataLogger

logger = NuanicDataLogger()
await logger.start_logging(duration_seconds=300)
```

**Output Format:**
```
timestamp,stress_raw,stress_percent,eda_hex,full_packet_hex
2024-01-15T14:23:45.123456,127,49.8,a1b2c3d4...
```

### NuanicEDAAnalyzer - EDA Analysis
Analyzes electrodermal activity patterns.

```python
from awe_polar.nuanic_ring.eda_analyzer import NuanicEDAAnalyzer

analyzer = NuanicEDAAnalyzer()
stats = analyzer.add_reading(eda_value)
print(analyzer.get_interpretation(stats))
```

**Metrics:**
- **Tonic (Baseline):** Slow-changing baseline EDA level
- **Phasic (Dynamic):** Quick event-related changes
- **Peaks:** Emotional or stress responses
- **Peak Rate:** Peaks per minute for arousal assessment

## Data Format Reference

### 92-byte Stress Packet Structure
- **Bytes 0-13:** Header/counter data
- **Byte 14:** DNE stress value (0-255) → stress% = (value/255)*100
- **Bytes 15-91:** EDA and other sensor data (77 bytes)

### Expected Data Ranges
- **Stress:** 0-255 (raw) → 0-100% (scaled)
- **Update Rate:** 1 Hz (packets arrive ~1 second apart)
- **EDA:** 16-bit values per channel

## Usage Examples

### Basic Data Logging (60 seconds)
```bash
python scripts/ble/log_nuanic_session.py --duration 60
```

Output:
```
[SCAN] Attempt 1/3...
[✓] Found: Nuanic at 54:EF:C5:C4:02:93
[CONNECT] Connecting to Nuanic...
[✓] Connected!
[✓] Subscribed to stress data

================================================================================
LOGGING NUANIC RING DATA
================================================================================
Duration: 60 seconds
================================================================================

Battery: 96%

[LOG] Logged 10 readings... Latest stress: 45.3%
[LOG] Logged 20 readings... Latest stress: 68.2%
...
[LOG] Session complete!
[LOG] Total readings: 60
[LOG] File: data/nuanic_logs/nuanic_2024-01-15_14-23-45.csv
```

### Real-time Monitoring
```python
import asyncio
from awe_polar.nuanic_ring import NuanicMonitor

async def monitor():
    monitor = NuanicMonitor()
    await monitor.start_monitoring()
    
    for _ in range(30):
        stress = monitor.get_current_stress()
        print(f"Stress: {stress:.1f}%")
        await asyncio.sleep(1)
    
    await monitor.stop_monitoring()

asyncio.run(monitor())
```

### EDA Analysis
```python
from awe_polar.nuanic_ring.eda_analyzer import NuanicEDAAnalyzer

analyzer = NuanicEDAAnalyzer()

# Add readings as they come in
for eda_value in eda_stream:
    stats = analyzer.add_reading(eda_value)
    
    if stats['is_peak']:
        print(f"Peak detected! Value: {eda_value}")
        print(f"  Phasic: {stats['phasic']:.1f}")
        print(f"  Baseline: {stats['baseline']:.1f}")
```

## Byte 15-91 EDA Data Interpretation

The 77-byte EDA section (bytes 15-91) contains electrodermal activity data that reflects:

1. **Tonic Component** (baseline): Slow changes in skin conductance (~1-10 hour time scale)
2. **Phasic Component** (peaks): Event-related changes, typically 0.5-5 second duration
3. **Skin Conductance Response (SCR):** Rising phase (1-3s) + recovery (20-60s)
4. **Emotional Arousal Indicators:**
   - More peaks = higher emotional arousal
   - Larger peaks = stronger emotional response
   - Faster recovery = better emotional regulation

## Integration with Polar H10

Once HR and stress data are synchronized:

```python
# Combine HR + Stress + EDA for comprehensive stress analysis
# Example: HR up + stress up + EDA peaks = confirmed stress response
```

## Troubleshooting

### Connection Issues
```
[✗] Nuanic ring not found
```
- Ensure ring is charged and turned on
- Check Windows Bluetooth settings (pair manually first if needed)
- Increase scan timeout in connector.py

### No Data Logging
```
[✗] Subscription error
```
- Try disconnecting the ring from Windows and re-running
- Check GATT characteristic UUIDs are correct

### EDA Value Interpretation
- Raw values: typically 0-4095 (12-bit ADC) or 0-65535 (16-bit)
- Look for peaks (sudden increases) to identify stress/emotional events
- Baseline drift expected over minutes/hours

## Performance Notes

- **Memory:** Keeps last 60 readings (~1 minute at 1 Hz)
- **File Size:** ~100-200 bytes per reading × reading count
- **CPU:** Minimal (async BLE library)
- **Battery:** Ring can stream for hours without significant drain

## References

- Nuanic documentation (if available)
- Electrodermal Activity research: Cacioppo et al., 2007
- Skin conductance response (SCR) analysis standards
