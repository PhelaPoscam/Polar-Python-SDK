"""Test script to decode and display EDA waveform in real-time"""
import asyncio
import struct
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.awe_polar.nuanic_ring.connector import NuanicConnector


def decode_eda_waveform(data):
    """
    Decode 77-byte EDA/PPG waveform from stress characteristic.
    
    Each byte represents a sample in the range 0-100 μS (microsiemens).
    Linear mapping: raw_byte * (100 / 255) = μS value
    """
    if len(data) < 92:
        return None
    
    # Extract stress (byte 14)
    stress_raw = data[14]
    stress_percent = (stress_raw / 255) * 100
    
    # Extract EDA waveform (bytes 15-91)
    eda_bytes = data[15:92]
    if len(eda_bytes) < 77:
        return None
    
    # Convert each byte to microsiemens (0-100 μS range)
    eda_samples = [byte * (100 / 255) for byte in eda_bytes]
    
    return {
        'stress_raw': stress_raw,
        'stress_percent': stress_percent,
        'eda_samples': eda_samples,
        'eda_mean': sum(eda_samples) / len(eda_samples),
        'eda_min': min(eda_samples),
        'eda_max': max(eda_samples),
        'eda_range': max(eda_samples) - min(eda_samples)
    }


class EDAMonitor:
    def __init__(self):
        self.connector = NuanicConnector()
        self.packet_count = 0
        self.start_time = None
    
    async def stress_callback(self, sender, data):
        """Receive and decode stress/EDA data"""
        decoded = decode_eda_waveform(data)
        if not decoded:
            return
        
        self.packet_count += 1
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        # Clear and display
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print("=" * 100)
        print("NUANIC EDA WAVEFORM DECODER - Real-Time Display")
        print("=" * 100)
        print(f"Elapsed: {elapsed:.1f}s | Packets: {self.packet_count}")
        print("=" * 100)
        
        # Stress metric
        print(f"\n📊 STRESS METRIC")
        print(f"  Raw: {decoded['stress_raw']}/255")
        print(f"  %:   {decoded['stress_percent']:.1f}%")
        stress_bar = "█" * int(decoded['stress_percent'] / 3)
        print(f"  Bar: {stress_bar}")
        
        # EDA statistics
        print(f"\n📈 EDA WAVEFORM (77 samples @ ~86 Hz)")
        print(f"  Mean:  {decoded['eda_mean']:.2f} μS (microsiemens)")
        print(f"  Min:   {decoded['eda_min']:.2f} μS")
        print(f"  Max:   {decoded['eda_max']:.2f} μS")
        print(f"  Range: {decoded['eda_range']:.2f} μS")
        
        # Simple visualization of EDA waveform
        print(f"\n🌊 EDA WAVEFORM VISUALIZATION")
        print("  " + "─" * 80)
        
        # Normalize samples to 0-20 range for display
        if decoded['eda_range'] > 0:
            normalized = [int(((s - decoded['eda_min']) / decoded['eda_range']) * 20) 
                         for s in decoded['eda_samples']]
        else:
            normalized = [10] * len(decoded['eda_samples'])
        
        # Create simple bar chart (show every 4th sample to fit in terminal)
        step = 4
        for i in range(0, len(normalized), step):
            sample_idx = i // step
            bar = "█" * normalized[i]
            print(f"  {sample_idx:2d}: {bar}")
        
        print("  " + "─" * 80)
        print(f"\n💡 INTERPRETATION:")
        print(f"  EDA ~40-50 μS = Calm/relaxed baseline")
        print(f"  EDA rise = Emotional response (stress, excitement)")
        print(f"  EDA stable = Consistent emotional state")
        
        print("\n" + "=" * 100)
        print("Press Ctrl+C to stop...")
        print("=" * 100)
    
    async def run(self):
        """Start monitoring"""
        self.start_time = datetime.now()
        
        print("Scanning for Nuanic ring...")
        if not await self.connector.connect():
            print("[FAIL] Could not connect to ring")
            return
        
        print("Connected! Listening to stress/EDA stream...")
        
        if not await self.connector.subscribe_to_stress(self.stress_callback):
            print("[FAIL] Could not subscribe to stress")
            return
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n\nStopping...")
        finally:
            await self.connector.disconnect()


async def main():
    monitor = EDAMonitor()
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
