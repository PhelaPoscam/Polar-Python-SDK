#!/usr/bin/env python3
"""
Nuanic Ring Real-time Monitor
Listens for notifications from the ring and displays data in real-time
"""
import asyncio
from bleak import BleakScanner, BleakClient
import csv
from datetime import datetime
import os


class NuanicMonitor:
    """Monitor Nuanic ring in real-time"""
    
    STRESS_CHAR = "468f2717-6a7d-46f9-9eb7-f92aab208bae"
    
    def __init__(self):
        self.log_file = None
        self.csv_writer = None
        self.data_count = 0
        self.start_time = None
    
    async def find_ring_persistent(self, timeout=60):
        """Persistently scan for ring with multiple attempts"""
        print(f"🔍 Scanning for Nuanic ring (max {timeout}s)...\n")
        
        start = datetime.now()
        while (datetime.now() - start).total_seconds() < timeout:
            devices = await BleakScanner.discover(timeout=5.0)
            
            for device in devices:
                if device.name and device.name.lower() == "nuanic":
                    print(f"✅ FOUND NUANIC: {device.address}\n")
                    return device
            
            print(".", end="", flush=True)
            await asyncio.sleep(1)
        
        print(f"\n❌ Ring not found after {timeout}s")
        return None
    
    async def notification_handler(self, sender, data):
        """Handle incoming notifications from ring"""
        if len(data) < 92:
            return
        
        # Parse data (92-byte packet)
        stress_raw = data[14]  # Byte 14 is stress (0-255)
        stress_percent = round((stress_raw / 255) * 100, 1)
        eda_hex = data[15:92].hex()  # Bytes 15-91 are EDA data
        full_hex = data.hex()
        
        # Display
        timestamp = datetime.now().isoformat()
        print(f"\n📊 Data #{self.data_count + 1}")
        print(f"   Timestamp: {timestamp}")
        print(f"   Stress: {stress_raw}/255 ({stress_percent}%)")
        print(f"   EDA: {len(eda_hex)//2} bytes")
        print(f"   Full packet: {len(full_hex)//2} bytes")
        
        # Log
        if self.csv_writer:
            self.csv_writer.writerow({
                'timestamp': timestamp,
                'stress_raw': stress_raw,
                'stress_percent': stress_percent,
                'eda_hex': eda_hex,
                'full_packet_hex': full_hex
            })
            self.log_file.flush()
        
        self.data_count += 1
    
    async def monitor(self, duration=30):
        """Start monitoring ring"""
        
        # Find ring
        ring = await self.find_ring_persistent(timeout=60)
        if not ring:
            return False
        
        # Create log file
        os.makedirs("data/nuanic_logs", exist_ok=True)
        log_path = f"data/nuanic_logs/nuanic_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
        self.log_file = open(log_path, 'w', newline='')
        self.csv_writer = csv.DictWriter(self.log_file, fieldnames=[
            'timestamp', 'stress_raw', 'stress_percent', 'eda_hex', 'full_packet_hex'
        ])
        self.csv_writer.writeheader()
        
        print(f"📝 Logging to: {log_path}\n")
        print(f"⏱️  Monitoring for {duration} seconds...\n")
        print("-" * 60)
        
        # Connect
        try:
            async with BleakClient(ring.address, timeout=10.0) as client:
                print(f"✅ CONNECTED\n")
                
                # Enable notifications
                await client.start_notify(self.STRESS_CHAR, self.notification_handler)
                print(f"🔔 Listening for notifications...\n")
                
                self.start_time = datetime.now()
                
                # Monitor for duration
                while (datetime.now() - self.start_time).total_seconds() < duration:
                    await asyncio.sleep(0.5)
                
                await client.stop_notify(self.STRESS_CHAR)
        
        except asyncio.TimeoutError:
            print("❌ Connection timeout")
            return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
        finally:
            if self.log_file:
                self.log_file.close()
        
        # Summary
        print("\n" + "-" * 60)
        print(f"\n✅ Monitoring complete!")
        print(f"   Data packets: {self.data_count}")
        print(f"   Duration: {(datetime.now() - self.start_time).total_seconds():.1f}s")
        print(f"   Log file: {log_path}\n")
        
        return True


async def main():
    import sys
    
    duration = 30
    if len(sys.argv) > 1:
        try:
            duration = int(sys.argv[1])
        except ValueError:
            print("Usage: python nuanic_realtime_monitor.py [duration_seconds]")
            return
    
    monitor = NuanicMonitor()
    await monitor.monitor(duration=duration)


if __name__ == "__main__":
    asyncio.run(main())
