# EDA Analysis Guide

Comprehensive guide to understanding and analyzing Electrodermal Activity (EDA) data from the Nuanic ring.

## What is EDA?

**Electrodermal Activity (EDA)**, also called Galvanic Skin Response (GSR), measures the electrical conductance of the skin. It's a physiological indicator of emotional arousal and autonomic nervous system activation.

### Why EDA Matters for Stress
- **Sweat gland activation:** Emotional and mental stress increases sweat production
- **Conductivity increase:** Sweat is conductive, increasing skin conductance
- **Autonomic marker:** Directly reflects sympathetic nervous system activity
- **Fast response:** Changes occur within 1-3 seconds of stress trigger

## EDA Components

### 1. Tonic Component (Baseline)
The slowly-changing baseline level of skin conductance.

**Characteristics:**
- Changes over minutes to hours
- Reflects overall arousal state
- Increases during anxiety or stress
- Typically 2-20 µS (microsiemens)

**In our data:**
- Extracted using exponential moving average
- Slow adaptation (alpha=0.02)

```python
analyzer.baseline = alpha * current_value + (1-alpha) * analyzer.baseline
```

### 2. Phasic Component (Dynamic Response)
Rapid changes in skin conductance in response to specific events.

**Characteristics:**
- Duration: 0.5 - 5 seconds (rise) + 20-60 seconds (recovery)
- Amplitude: varies with emotional intensity
- Multiple peaks during high stress

**In our data:**
```python
phasic = current_eda - baseline
```

### 3. Skin Conductance Response (SCR)
The characteristic spike-recovery pattern following a stress event.

```
EDA
  |     ___  (Recovery phase, 20-60s)
  |    /   \
  |   /     \___
  |  /  ↑ Rise time (1-3s)
  |_/___\________ (Baseline)
   Event
```

## Important EDA Metrics

### Peak Detection
```python
peak_threshold = mean + standard_deviation
is_peak = current_value > threshold
```

| Peaks/min | Interpretation |
|-----------|---|
| < 1 | Very low arousal |
| 1-2 | Low arousal |
| 2-5 | Moderate arousal |
| 5-10 | High arousal/stress |
| > 10 | Very high stress |

### Amplitude Analysis
```python
amplitude = peak_value - baseline
```

| Amplitude | Meaning |
|-----------|---------|
| < 0.5 µS | Minimal emotional response |
| 0.5-2 µS | Mild response |
| 2-5 µS | Moderate response |
| > 5 µS | Strong emotional response |

### Rise Time & Recovery
- **Fast rise (< 1s) + fast recovery:** Quick, controlled response
- **Slow rise (> 2s) + slow recovery (> 60s):** Intense or prolonged stress
- **Multiple peaks:** Sustained or repeated stress stimuli

## Parsing Byte 15-91 EDA Data

The 77-byte EDA section in each 92-byte packet contains:

### Likely Structure (to be verified with real data)
```
Offset  Size  Description
------  ----  -----------
0-1     2     EDA Channel 1 (likely main stress indicator)
2-3     2     EDA Channel 2 (potential secondary measurement)
4-5     2     EDA Channel 3 (potential filter/processed data)
6-7     2     EDA Channel 4 (potential metadata)
8-77    70    Additional sensor data or processed features
```

### To Determine Exact Format
1. **Capture raw data** and export to CSV
2. **Analyze distributions:**
   - What's the typical range?
   - Do channels correlate?
   - Which channel matches stress values?
3. **Time-sync with stress:**
   - When stress spikes, do EDA channels spike?
   - Which channel responds first?
   - What's the magnitude relationship?

## EDA Analysis Workflow

### Step 1: Raw Data Capture
```python
logger = NuanicDataLogger()
await logger.start_logging(duration_seconds=300)
# Generates: data/nuanic_logs/nuanic_TIMESTAMP.csv
```

### Step 2: Parse EDA Bytes
```python
# Each row has 'eda_hex' column (bytes 15-91 in hex)
eda_bytes = bytes.fromhex(row['eda_hex'])

# Parse into channels (example for 4 × 16-bit channels)
import struct
ch1, ch2, ch3, ch4 = struct.unpack('<HHHH', eda_bytes[0:8])
```

### Step 3: Calculate Baseline
```python
analyzer = NuanicEDAAnalyzer()
baseline = sum(values[:30]) / 30  # First 30 seconds
```

### Step 4: Detect Peaks
```python
std_dev = calculate_std_dev(values)
peaks = [v for v in values if v > baseline + std_dev]
```

### Step 5: Evaluate Phasic Response
```python
for peak in peaks:
    phasic = peak - baseline
    rise_time = time_to_peak - time_at_baseline
    recovery_time = time_to_recovery - time_at_peak
    print(f"Peak: {phasic:.2f} µS, Rise: {rise_time:.1f}s, Recovery: {recovery_time:.1f}s")
```

## Expected Patterns

### Resting State (Low Stress)
```
EDA: Stable near baseline
Peaks: < 1 per minute
ΔEDAstress baseline: ±0.5 µS
```

### Active Engagement (Moderate Stress)
```
EDA: Elevated baseline
Peaks: 2-5 per minute
ΔEDAstress: +2-3 µS per peak
Recovery: 30-45 seconds
```

### High Stress State
```
EDA: Much higher baseline
Peaks: > 5 per minute, sometimes overlapping
ΔEDAstress: > 3 µS per peak
Recovery: May not fully recover before next peak
```

## EDA + Stress Correlation Analysis

### Expected Relationships
1. **EDA spikes correlate with stress increases**
   - When stress raw value jumps 50+ points, expect EDA peak
   - 1-2 second lag is normal (neural transmission)

2. **Baseline drift correlates with sustained stress**
   - Long sessions: baseline creeps upward (fatigue)
   - Multiple stressors: combined baseline elevation

3. **Peak frequency reflects emotional intensity**
   - More peaks = more stressors or lower stress tolerance
   - Larger peaks = stronger individual stressor events

### Data Fusion Example
```
Time    HR     Stress   EDA_Peak    Interpretation
14:23   72     45       No          Relaxed
14:24   78     62       Yes         Engaged task/mild stress
14:25   85     78       Yes         Performance peak
14:26   92     91       Yes         High stress moment
14:27   88     72       Recovering  Stress resolving
```

## Analysis Tips

### Use Python Data Science Stack
```python
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Load data
df = pd.read_csv('nuanic_TIMESTAMP.csv')

# Parse EDA
eda_data = df['eda_hex'].apply(lambda x: int(x[0:4], 16))

# Plot
plt.figure(figsize=(12, 6))
plt.subplot(2,1,1)
plt.plot(df['stress_percent'], label='Stress')
plt.ylabel('Stress %')
plt.legend()

plt.subplot(2,1,2)
plt.plot(eda_data, label='EDA')
plt.ylabel('EDA (µS)')
plt.xlabel('Time (samples)')
plt.legend()
plt.tight_layout()
plt.show()
```

### Common Artifacts to Watch For
1. **Baseline drift:** Normal (fatigue) vs. sensor drift (check calibration)
2. **Movement artifacts:** Watch for sudden spikes without stress correlation
3. **Data dropouts:** Missing packets indicate connection issues
4. **Saturation:** Clipped peaks suggest sensor overload

## Nuanic Ring Specific Notes

The Nuanic ring's EDA sensor provides:
- High temporal resolution (~1 Hz stress, possibly 16 Hz for raw EDA)
- Wearable form factor (better comfort than traditional GSR electrode pads)
- Possible multi-channel EDA measurement
- Integration with stress measurement in same device

### Limitations
- Smaller electrode surface area than lab equipment = noisier signal
- Motion artifacts from ring movement on finger
- Possible cross-talk with other sensors
- Baseline drift due to sweat accumulation during ring wear

## Debugging Your EDA Data

### "EDA values seem too stable/high/low"
1. Check byte offsets (might not be bytes 15-91)
2. Verify parsing logic (endianness, data type)
3. Compare against known reference values
4. Check if sensor was properly calibrated at start

### "No peaks detected"
1. Review peak detection threshold
2. Check if capturing during low-stress baseline
3. Verify EDA channel identification
4. Try different statistical methods (percentile vs. std dev)

### "EDA spikes but stress doesn't"
1. Stress value might update slower than EDA
2. Check time alignment between measurements
3. Verify Byte 14 is actually the stress value
4. Look for sensor-specific artifacts

## Next Steps

1. **Capture 10-15 minutes of real data**
2. **Parse and visualize the EDA bytes**
3. **Identify which bytes correlate with stress changes**
4. **Create correlation matrix (Stress vs. EDA channels)**
5. **Build visualization dashboard**
