"""
Nuanic Ring Real-Time Handler
Continuous polling of Byte 14 (Stress Level) with periodic updates
"""

import asyncio
from bleak import BleakScanner, BleakClient
from datetime import datetime
import csv
import os
import json

TARGET_NAME = "LHB-6F0A2510"
PRIMARY_DATA_UUID = "00000010-0060-7990-5544-1cce81af42f0"
POLL_INTERVAL = 10  # Read every 10 seconds
OUTPUT_DIR = "data/logs/ring_stress"

os.makedirs(OUTPUT_DIR, exist_ok=True)

async def nuanic_stress_reader(duration_seconds=300):
    """
    Continuously read Byte 14 (Stress Level) from Nuanic ring
    
    Args:
        duration_seconds: How long to monitor (default 5 minutes)
    """
    
    print("="*70)
    print("NUANIC RING - STRESS LEVEL MONITOR")
    print("="*70)
    print(f"\nMonitoring duration: {duration_seconds}s ({duration_seconds//60}m)")
    print(f"Poll frequency: Every {POLL_INTERVAL}s")
    
    # Find device
    print(f"\n[SCAN] Looking for {TARGET_NAME}...")
    devices = await BleakScanner.discover(timeout=10.0)
    target = None
    for device in devices:
        if device.name and TARGET_NAME in device.name:
            target = device
            break
    
    if not target:
        print(f"❌ Ring not found")
        return
    
    print(f"✓ Found: {target.name}")
    
    # Connect
    async with BleakClient(target.address, timeout=20.0) as client:
        print(f"✓ Connected\n")
        
        start_time = datetime.now()
        timestamp = start_time.strftime("%Y%m%d_%H%M%S")
        
        # Create CSV file for logging
        csv_file = os.path.join(OUTPUT_DIR, f"stress_log_{timestamp}.csv")
        json_file = os.path.join(OUTPUT_DIR, f"stress_summary_{timestamp}.json")
        
        readings = []
        last_stress = None
        min_stress = 100
        max_stress = 0
        
        print("Time     | Stress | Change | Status")
        print("---------|--------|--------|------------------")
        
        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'timestamp', 'elapsed_seconds', 'stress_level', 'change'
            ])
            writer.writeheader()
            
            try:
                while True:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    
                    if elapsed >= duration_seconds:
                        break
                    
                    try:
                        # Read data
                        data = await client.read_gatt_char(PRIMARY_DATA_UUID)
                        
                        # Extract Byte 14
                        stress = data[14]
                        
                        # Track changes
                        change = 0
                        if last_stress is not None:
                            change = stress - last_stress
                        
                        # Update stats
                        min_stress = min(min_stress, stress)
                        max_stress = max(max_stress, stress)
                        
                        # Display
                        status = ""
                        if last_stress is not None:
                            if change > 0:
                                status = f"📈 +{change}"
                            elif change < 0:
                                status = f"📉 {change}"
                            else:
                                status = "━ stable"
                        
                        now = datetime.now()
                        time_str = now.strftime("%H:%M:%S")
                        print(f"{time_str} | {stress:6d} | {change:+6d} | {status}")
                        
                        # Log to CSV
                        writer.writerow({
                            'timestamp': now.isoformat(),
                            'elapsed_seconds': elapsed,
                            'stress_level': stress,
                            'change': change if last_stress else 0
                        })
                        f.flush()
                        
                        # Save to reading history
                        readings.append({
                            'timestamp': now.isoformat(),
                            'stress': stress,
                            'change': change
                        })
                        
                        last_stress = stress
                        
                    except Exception as e:
                        print(f"{datetime.now().strftime('%H:%M:%S')} | ERROR: {e}")
                    
                    # Wait before next read
                    await asyncio.sleep(POLL_INTERVAL)
        
        # Save summary
        summary = {
            'start_time': start_time.isoformat(),
            'duration_seconds': duration_seconds,
            'readings_count': len(readings),
            'stress_min': min_stress,
            'stress_max': max_stress,
            'stress_avg': sum(r['stress'] for r in readings) / len(readings) if readings else 0,
            'stress_range': max_stress - min_stress,
            'readings': readings
        }
        
        with open(json_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Print summary
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"\nReadings collected: {len(readings)}")
        print(f"\nStress Level Statistics:")
        print(f"  Min:     {min_stress}")
        print(f"  Max:     {max_stress}")
        print(f"  Average: {summary['stress_avg']:.1f}")
        print(f"  Range:   {max_stress - min_stress}")
        
        print(f"\nFiles saved:")
        print(f"  • {csv_file}")
        print(f"  • {json_file}")
        
        print("\n" + "="*70)


if __name__ == "__main__":
    print("\n🔴 STRESS MONITOR READY\n")
    print("This will continuously read your stress level from the ring")
    print("and compare it with your Nuanic app.\n")
    
    input("Press ENTER to start (duration: 5 minutes)...")
    
    # Run for 5 minutes
    asyncio.run(nuanic_stress_reader(duration_seconds=300))
    
    print("\n✓ Complete!")
