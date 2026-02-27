"""Example scripts for using Nuanic ring integration"""
import asyncio
from src.awe_polar.nuanic_ring import NuanicDataLogger, NuanicMonitor
from src.awe_polar.nuanic_ring.eda_analyzer import NuanicEDAAnalyzer


async def example_data_logging(duration=60):
    """Log Nuanic ring data for specified duration"""
    logger = NuanicDataLogger()
    await logger.start_logging(duration_seconds=duration)


async def example_real_time_monitoring():
    """Monitor Nuanic ring stress in real-time"""
    monitor = NuanicMonitor()
    
    if not await monitor.start_monitoring():
        return
    
    try:
        for _ in range(60):  # Monitor for 60 seconds
            stress = monitor.get_current_stress()
            if stress is not None:
                print(f"Stress: {stress:.1f}%")
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        await monitor.stop_monitoring()


def example_eda_analysis():
    """Demonstrate EDA analysis"""
    analyzer = NuanicEDAAnalyzer()
    
    # Simulate EDA readings
    import random
    readings = []
    for i in range(100):
        value = 100 + random.gauss(0, 20)  # Mean 100, std dev 20
        value = max(0, min(4095, value))  # Clamp to valid range
        stats = analyzer.add_reading(value)
        readings.append(stats)
    
    # Print some results
    print("\nEDA Analysis Example:")
    print(f"Current reading: {readings[-1]['current_value']:.1f}")
    print(f"Baseline (tonic): {readings[-1]['baseline']:.1f}")
    print(f"Dynamic (phasic): {readings[-1]['phasic']:.1f}")
    print(f"Is peak: {readings[-1]['is_peak']}")


if __name__ == "__main__":
    print("Nuanic Ring Integration Examples")
    print("=" * 50)
    print("1. Data Logging (60 seconds)")
    print("2. Real-time Monitoring (60 seconds)")
    print("3. EDA Analysis Demo")
    print("=" * 50)
    
    choice = input("Choose example (1-3): ").strip()
    
    if choice == "1":
        asyncio.run(example_data_logging(60))
    elif choice == "2":
        asyncio.run(example_real_time_monitoring())
    elif choice == "3":
        example_eda_analysis()
    else:
        print("Invalid choice")
