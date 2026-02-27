#!/usr/bin/env python3
"""
HIGH-FREQUENCY Nuanic Ring Monitor
Listens to ALL characteristics (not just stress)
This should capture data at the ring's native rate (~16 Hz or higher)
"""
import asyncio
from bleak import BleakScanner, BleakClient
import csv
from datetime import datetime
import os


class NuanicHighFreqMonitor:
    """Monitor ALL Nuanic ring characteristics for high-frequency data"""
    
    # Try to find all possible characteristics
    KNOWN_CHARACTERISTICS = [
        "468f2717-6a7d-46f9-9eb7-f92aab208bae",  # Stress (we know this works)
        "00002a37-0000-1000-8000-00805f9b34fb",  # Heart Rate Measurement
        "00002a38-0000-1000-8000-00805f9b34fb",  # Body Sensor Location
        "00002a39-0000-1000-8000-00805f9b34fb",  # Heart Rate Control Point
        "00002a19-0000-1000-8000-00805f9b34fb",  # Battery Level
    ]
    
    def __init__(self):
        self.log_file = None
        self.csv_writer = None
        self.packet_count = 0
        self.start_time = None
        self.last_print_time = None
    
    async def find_ring_persistent(self, timeout=60):
        """Persistently scan for ring"""
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
        
        return None
    
    async def notification_handler(self, sender, data):
        """Handle ALL incoming notifications"""
        timestamp = datetime.now()
        if self.start_time is None:
            return
        relative_time = (timestamp - self.start_time).total_seconds()
        
        # Print in real-time
        if self.packet_count < 50:  # Print first 50 packets for visibility
            print(f"  📡 #{self.packet_count+1:3d} | Time: {relative_time:6.2f}s | Char: {str(sender)[:20]:20s} | Len: {len(data):2d} | {data[:8].hex()}...")
        
        # Log the raw data
        if self.csv_writer:
            self.csv_writer.writerow({
                'timestamp': timestamp.isoformat(),
                'relative_time': f'{relative_time:.3f}',
                'characteristic': str(sender),
                'data_length': len(data),
                'data_hex': data.hex(),
                'data_raw': str(list(data))
            })
            self.log_file.flush()
        
        self.packet_count += 1
        
        # Print status every 50 packets
        if self.packet_count % 50 == 0:
            rate = self.packet_count / relative_time if relative_time > 0 else 0
            print(f"\r                                                                                       \r📊 Cumulative: {self.packet_count:4d} packets in {relative_time:6.2f}s | Rate: {rate:5.1f} Hz", end='', flush=True)
    
    async def monitor(self, duration=30):
        """Monitor all characteristics"""
        
        # Find ring
        ring = await self.find_ring_persistent(timeout=60)
        if not ring:
            print("❌ Ring not found")
            return False
        
        # Create log file
        os.makedirs("data/nuanic_logs", exist_ok=True)
        log_path = f"data/nuanic_logs/nuanic_highfreq_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
        self.log_file = open(log_path, 'w', newline='')
        self.csv_writer = csv.DictWriter(self.log_file, fieldnames=[
            'timestamp', 'relative_time', 'characteristic', 'data_length', 'data_hex', 'data_raw'
        ])
        self.csv_writer.writeheader()
        
        print(f"📝 Logging to: {log_path}\n")
        print(f"⏱️  Monitoring ALL characteristics for {duration} seconds...\n")
        print("-" * 80)
        
        try:
            async with BleakClient(ring.address, timeout=10.0) as client:
                print(f"✅ CONNECTED\n")
                
                # Get all services and characteristics
                services = client.services
                notifiable_chars = []
                
                for service in services:
                    for char in service.characteristics:
                        if "notify" in char.properties or "indicate" in char.properties:
                            notifiable_chars.append((char.uuid, char.description))
                            print(f"🔔 Found notifiable characteristic: {char.uuid} ({char.description})")
                
                print(f"\n📡 Enabling {len(notifiable_chars)} characteristics...\n")
                
                # Enable notifications on all notifiable characteristics
                for char_uuid, description in notifiable_chars:
                    try:
                        await client.start_notify(str(char_uuid), self.notification_handler)
                        print(f"  ✓ Enabled: {char_uuid}")
                    except Exception as e:
                        print(f"  ✗ Failed: {char_uuid} - {e}")
                
                print(f"\n{'='*80}")
                print(f"🔔 Listening for ALL notifications...\n")
                print(f"First 50 packets:\n")
                
                self.start_time = datetime.now()
                
                # Monitor for duration
                while (datetime.now() - self.start_time).total_seconds() < duration:
                    await asyncio.sleep(0.1)
                
                # Stop all notifications
                for char_uuid, _ in notifiable_chars:
                    try:
                        await client.stop_notify(str(char_uuid))
                    except:
                        pass
        
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
        elapsed = (datetime.now() - self.start_time).total_seconds()
        rate = self.packet_count / elapsed if elapsed > 0 else 0
        
        print(f"\r{' '*100}\r", end='')
        print(f"\n{'='*80}")
        print(f"\n✅ Monitoring complete!")
        print(f"   Total packets: {self.packet_count}")
        print(f"   Duration: {elapsed:.1f}s")
        print(f"   Rate: {rate:.1f} Hz")
        print(f"   Log file: {log_path}\n")
        
        return True


async def main():
    import sys
    
    duration = 30
    if len(sys.argv) > 1:
        try:
            duration = int(sys.argv[1])
        except ValueError:
            print("Usage: python nuanic_highfreq_monitor.py [duration_seconds]")
            return
    
    monitor = NuanicHighFreqMonitor()
    await monitor.monitor(duration=duration)


if __name__ == "__main__":
    asyncio.run(main())
