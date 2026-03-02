"""Simple IMU test - shows real acc_x values over time"""
import asyncio
import struct
from bleak import BleakClient, BleakScanner
from datetime import datetime
import numpy as np

async def test_imu_stationary():
    print("Scanning for Nuanic ring...")
    devices = await BleakScanner.discover(timeout=3.0)
    
    nuanic = [d for d in devices if d.name and 'Nuanic' in d.name]
    if not nuanic:
        print("Nuanic ring not found!")
        return
    
    print(f"Found: {nuanic[0].name}\n")
    
    client = BleakClient(nuanic[0])
    await client.connect()
    await client.pair()
    
    IMU_CHAR = "d306262b-c8c9-4c4b-9050-3a41dea706e5"
    
    print("=" * 80)
    print("IMU TEST - KEEP YOUR HAND STATIONARY")
    print("=" * 80)
    print("Time      ACC_X      ACC_Y   StdDev(last 10)   Analysis")
    print("-" * 80)
    
    acc_x_values = []
    start_time = datetime.now()
    packet_count = 0
    
    def imu_callback(sender, data):
        nonlocal packet_count, acc_x_values
        
        if len(data) < 12:
            return
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Parse acceleration
        acc_x = struct.unpack('<h', data[8:10])[0]
        acc_y = struct.unpack('<h', data[10:12])[0]
        
        acc_x_values.append(acc_x)
        packet_count += 1
        
        # Calculate stddev of last 10 values
        recent = acc_x_values[-10:]
        stddev = np.std(recent) if len(recent) > 1 else 0
        
        # Determine if stationary
        if stddev < 500:
            status = "✓ STATIONARY"
        elif stddev < 2000:
            status = "~ SLIGHT MOVEMENT"
        else:
            status = "✗ MOVING"
        
        print(f"{elapsed:6.1f}s  {acc_x:7d}   {acc_y:6d}   {stddev:8.1f}       {status}")
    
    try:
        await client.start_notify(IMU_CHAR, imu_callback)
        print(f"\n✓ Listening to IMU...\n")
        
        # Capture for 15 seconds
        await asyncio.sleep(15)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.disconnect()
    
    # Final analysis
    print("\n" + "=" * 80)
    print("FINAL ANALYSIS")
    print("=" * 80)
    
    if acc_x_values:
        print(f"Total packets: {packet_count}")
        print(f"Sampling rate: {packet_count / 15:.1f} Hz")
        print(f"\nACC_X Statistics:")
        print(f"  Min: {min(acc_x_values)}")
        print(f"  Max: {max(acc_x_values)}")
        print(f"  Range: {max(acc_x_values) - min(acc_x_values)}")
        print(f"  Mean: {np.mean(acc_x_values):.1f}")
        print(f"  StdDev: {np.std(acc_x_values):.1f}")
        
        print(f"\nInterpretation:")
        overall_stddev = np.std(acc_x_values)
        
        if overall_stddev < 800:
            print(f"  ✓ HAND WAS STATIONARY (very low variance: {overall_stddev:.0f})")
        elif overall_stddev < 3000:
            print(f"  ~ SOME MOVEMENT (moderate variance: {overall_stddev:.0f})")
        else:
            print(f"  ✗ SIGNIFICANT MOVEMENT (high variance: {overall_stddev:.0f})")
            print(f"  Range of {max(acc_x_values) - min(acc_x_values)} indicates strong motion")

asyncio.run(test_imu_stationary())
