import asyncio
import sys
from pathlib import Path

# Dynamically add the 'src' directory to sys.path so 'awe_polar' is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

try:
    from awe_polar.connector.ble_discovery import discover_polar_device
    from awe_polar.connector.stream.polar_h10_ble import HeartRate
except ImportError as e:
    print(
        f"Error: Could not import 'awe_polar'. Make sure the 'src' directory exists. Details: {e}"
    )
    sys.exit(1)


def hr_callback(data):
    if isinstance(data, tuple) and len(data) >= 2:
        hr_val, rr_ints = data
        rr_str = f", RR-intervals: {rr_ints}" if rr_ints else ""
        print(f"\r[HR] Heart Rate: {hr_val} BPM{rr_str}", end="", flush=True)


def ppi_callback(data):
    # data is (timestamp, ppi_values)
    timestamp, ppi_vals = data
    print(f"\n[PPI] Pulse-to-Pulse Intervals: {ppi_vals} ms")


def ppg_callback(data):
    # data is (timestamp, sample_values)
    timestamp, samples = data
    # print a preview of PPG values
    print(f"\n[PPG] Optical Pulse samples: {samples[:3]}...")


def acc_callback(data):
    timestamp, samples = data
    print(f"\n[ACC] Accelerometer: {samples[:2]}...")


def ecg_callback(data):
    timestamp, samples = data
    print(f"\n[ECG] ECG samples: {samples[:3]}...")


async def main():
    print("Scanning for Polar devices...")
    device = await discover_polar_device(timeout=20.0)

    if not device:
        print(
            "Error: No Polar device found. Make sure your sensor is turned on, Flow app is closed, and Bluetooth is active."
        )
        return

    print(f"Found Polar device: {device.name} [{device.address}]")
    print(
        "Connecting... (If this is a watch, make sure you enabled SDK Sharing and are in the 'Exercise wait' view!)"
    )

    # Instantiate HeartRate wrapper
    heartrate = HeartRate(
        device,
        callback=hr_callback,
        ppi_callback=ppi_callback,
        ppg_callback=ppg_callback,
        acc_callback=acc_callback,
        ecg_callback=ecg_callback,
    )

    try:
        await heartrate.start_notify()
        print("\nConnected! Streaming live data. Press Ctrl+C to stop...\n")

        # Keep the connection active
        while True:
            await asyncio.sleep(1)

    except asyncio.CancelledError:
        print("\nStopping stream...")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        print("Disconnecting device...")
        await heartrate.stop_notify()
        print("Disconnected.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExited by user.")
