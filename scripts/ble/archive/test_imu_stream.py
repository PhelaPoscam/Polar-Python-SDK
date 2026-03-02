"""Diagnostic script to verify IMU stream is working"""
import asyncio
import struct
from bleak import BleakClient, BleakScanner
from datetime import datetime
from collections import deque

async def run_imu():
    print("Scanning for Nuanic ring...")
    devices = await BleakScanner.discover(timeout=3.0)
    
    nuanic = [d for d in devices if d.name and 'Nuanic' in d.name]
    if not nuanic:
        print("Nuanic ring not found!")
        return
    
    print(f"Found: {nuanic[0].name}")
    
    client = BleakClient(nuanic[0])
    await client.connect()
    await client.pair()
    
    # Check both characteristics
    STRESS_CHAR = "468f2717-6a7d-46f9-9eb7-f92aab208bae"
    IMU_CHAR = "d306262b-c8c9-4c4b-9050-3a41dea706e5"
    
    print("\n" + "=" * 80)
    print("TESTING IMU STREAM")
    print("=" * 80)
    
    imu_packets = deque(maxlen=20)
    stress_packets = deque(maxlen=10)
    start_time = datetime.now()
    
    def imu_callback(sender, data):
        """Parse IMU packet"""
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Debug: print full packet
        packet_hex = data.hex()
        packet_len = len(data)
        
        if packet_len >= 12:
            # Parse acceleration (bytes 8-11)
            acc_x = struct.unpack('<h', data[8:10])[0]
            acc_y = struct.unpack('<h', data[10:12])[0]
            
            # Signal quality (byte 12)
            quality = data[12] if len(data) > 12 else 0
            
            imu_packets.append({
                'time': elapsed,
                'acc_x': acc_x,
                'acc_y': acc_y,
                'quality': quality,
                'len': packet_len,
                'hex': packet_hex[:40] + "..."
            })
            
            print(f"[IMU #{len(imu_packets)} @ {elapsed:5.1f}s] ACC_X={acc_x:7d} ACC_Y={acc_y:7d} Q={quality:3d} (len={packet_len})")
        else:
            print(f"[IMU SHORT PACKET] len={packet_len}")
    
    def stress_callback(sender, data):
        """Parse stress packet"""
        elapsed = (datetime.now() - start_time).total_seconds()
        stress_raw = data[14]
        stress_pct = (stress_raw / 255) * 100
        
        stress_packets.append({
            'time': elapsed,
            'stress': stress_pct
        })
        
        print(f"[STRESS #{len(stress_packets)} @ {elapsed:5.1f}s] Stress={stress_pct:5.1f}%")
    
    # Subscribe to both
    try:
        await client.start_notify(IMU_CHAR, imu_callback)
        print(f"✓ Subscribed to IMU: {IMU_CHAR}")
    except Exception as e:
        print(f"✗ IMU subscribe failed: {e}")
    
    try:
        await client.start_notify(STRESS_CHAR, stress_callback)
        print(f"✓ Subscribed to Stress: {STRESS_CHAR}")
    except Exception as e:
        print(f"✗ Stress subscribe failed: {e}")
    
    print("\nCapturing for 10 seconds... MOVE YOUR HAND AROUND!")
    print("=" * 80)
    
    await asyncio.sleep(10)
    
    # Analysis
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)
    print(f"Duration: {elapsed:.2f}s")
    print(f"IMU packets: {len(imu_packets)} ({len(imu_packets)/elapsed:.2f} Hz)")
    print(f"Stress packets: {len(stress_packets)} ({len(stress_packets)/elapsed:.2f} Hz)")
    
    if imu_packets:
        acc_xs = [p['acc_x'] for p in imu_packets]
        acc_ys = [p['acc_y'] for p in imu_packets]
        qualities = [p['quality'] for p in imu_packets]
        
        print(f"\nIMU Stats:")
        print(f"  ACC_X: min={min(acc_xs)} max={max(acc_xs)} range={max(acc_xs)-min(acc_xs)}")
        print(f"  ACC_Y: {acc_ys[0]} (should be constant ~15)")
        print(f"  Quality: min={min(qualities)} max={max(qualities)}")
        
        if max(acc_xs) - min(acc_xs) < 500:
            print("  ⚠️  WARNING: ACC_X range is very small - movement not detected!")
        else:
            print("  ✓ ACC_X varies with movement")
    else:
        print("⚠️ No IMU packets received!")
    
    # Cleanup
    await client.disconnect()


def main():
    """Main entry point for direct execution"""
    asyncio.run(run_imu())


if __name__ == "__main__":
    main()
