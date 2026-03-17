"""Live waveform viewer for Nuanic ring data streams.

REVERSE-ENGINEERING FINDINGS:
 - Stress Characteristic (1 Hz): Contains byte[14] = stress % and bytes[15:92] = waveform payload (77 bytes)
     This waveform IS the actual physiological data (stress/EDA equivalent).
 - Raw EDA Characteristic: BROKEN - only sends 1-byte junk packets (0x01)
 - IMU Characteristic (15.94 Hz): Accelerometer 3-axis data (16 bytes per packet)
 - All other characteristics: Config/write-only registers, mysterious notify never sends data

DATA DISPLAY:
 - Plot 1 (top): Stress waveform payload (0-255 scaled) - THIS IS THE REAL PHYSIOLOGICAL DATA
 - Plot 2 (bottom): IMU acceleration (motion data)
"""

import asyncio
import struct
import threading
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import numpy as np

from .connector import NuanicConnector


def smooth_data(data: list, window: int) -> list:
    """Apply moving average smoothing to data.

    Args:
        data: Input data points
        window: Smoothing window size (1 = no smoothing)

    Returns:
        Smoothed data as list
    """
    if not data or window <= 1:
        return data

    if len(data) < window:
        return data

    # Use numpy convolve for efficient moving average
    kernel = np.ones(window) / window
    smoothed = np.convolve(data, kernel, mode="valid")

    # Pad the beginning to keep same length
    pad_length = len(data) - len(smoothed)
    padded = np.pad(smoothed, (pad_length, 0), mode="edge")

    return padded.tolist()


class WaveformState:
    """Thread-safe container for live waveform buffers."""

    def __init__(self, history_points: int = 600):
        self.lock = threading.Lock()

        self.sample_index = 0
        self.stress_index = deque(maxlen=history_points)
        self.stress_wave = deque(maxlen=history_points)

        self.raw_index = deque(maxlen=history_points)
        self.raw_wave = deque(maxlen=history_points)

        self.latest_stress_percent = None
        self.stress_packets = 0
        self.raw_packets = 0


class NuanicWaveformViewer:
    """Connects to ring, subscribes to streams, and exposes data for plotting."""

    def __init__(self, ring_addr: str | None = None):
        self.connector = NuanicConnector(target_address=ring_addr)
        self.state = WaveformState()
        self._running = False

    def _stress_callback(self, sender, data):
        if len(data) < 15:
            return

        stress_raw = data[14]
        stress_percent = (stress_raw / 255) * 100

        # Treat bytes 15-91 as waveform bytes and scale to 0..100 for display.
        payload = data[15:92] if len(data) >= 92 else data[15:]
        if not payload:
            return

        with self.state.lock:
            self.state.latest_stress_percent = stress_percent
            self.state.stress_packets += 1

            # Debug: print every 10th packet
            if self.state.stress_packets % 10 == 1:
                print(
                    f"[DEBUG] Stress packet #{self.state.stress_packets}: {len(payload)} samples, stress={stress_percent:.1f}%"
                )

            for byte_val in payload:
                self.state.sample_index += 1
                self.state.stress_index.append(self.state.sample_index)
                self.state.stress_wave.append((byte_val / 255.0) * 100.0)

    def _raw_eda_callback(self, sender, data):
        if len(data) < 2:
            return

        with self.state.lock:
            self.state.raw_packets += 1

            # Debug: print every 10th packet
            num_samples = len(data) // 2
            if self.state.raw_packets % 10 == 1:
                # Peek at first sample value for debugging
                first_val = struct.unpack("<h", data[0:2])[0] if len(data) >= 2 else 0
                print(
                    f"[DEBUG] Raw EDA packet #{self.state.raw_packets}: {num_samples} samples, first={first_val}"
                )

            # Decode as little-endian int16 sample stream.
            for i in range(0, len(data) - 1, 2):
                val = struct.unpack("<h", data[i : i + 2])[0]
                self.state.sample_index += 1
                self.state.raw_index.append(self.state.sample_index)
                self.state.raw_wave.append(val)

    async def connect_and_subscribe(self) -> bool:
        if not await self.connector.connect():
            return False

        stress_ok = await self.connector.subscribe_to_stress(self._stress_callback)
        raw_ok = await self.connector.subscribe_to_raw_eda(self._raw_eda_callback)

        if not (stress_ok and raw_ok):
            await self.connector.unsubscribe_from_stress()
            await self.connector.unsubscribe_from_raw_eda()
            await self.connector.disconnect()
            return False

        self._running = True
        return True

    async def run_until_stopped(self):
        try:
            while self._running:
                await asyncio.sleep(0.1)
        finally:
            await self.stop()

    async def stop(self):
        self._running = False
        await self.connector.unsubscribe_from_stress()
        await self.connector.unsubscribe_from_raw_eda()
        await self.connector.disconnect()


async def run_plot_async(
    viewer: NuanicWaveformViewer,
    window_seconds: int,
    refresh_ms: int,
    smooth_window: int = 1,
):
    """Run the plot in non-blocking mode, allowing asyncio event loop to continue.

    Args:
        viewer: The waveform viewer instance
        window_seconds: Time window to display
        refresh_ms: Plot refresh interval in milliseconds
        smooth_window: Moving average window size (1 = no smoothing, 5-20 = smooth)
    """
    plt.ion()  # Turn on interactive mode

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=False)
    smooth_text = f" (smoothed {smooth_window}x)" if smooth_window > 1 else ""
    fig.suptitle(f"Nuanic Ring: Stress Waveform + IMU{smooth_text}")

    (line1,) = ax1.plot([], [], lw=1.5)
    (line2,) = ax2.plot([], [], lw=1.2, color="tab:orange")

    ax1.set_ylabel("Stress Waveform\n(Physiological Signal)")
    ax2.set_ylabel("IMU Acceleration\n(Motion Data)")
    ax2.set_xlabel("Sample Index")

    status_text = fig.text(0.02, 0.96, "Waiting for data...", fontsize=10)

    # Rough point budget for visible x window (adapts if payload density changes).
    max_points = max(200, window_seconds * 100)

    plt.tight_layout()
    plt.show(block=False)

    try:
        while viewer._running and plt.fignum_exists(fig.number):
            # Update plot
            with viewer.state.lock:
                x1 = list(viewer.state.stress_index)[-max_points:]
                y1 = list(viewer.state.stress_wave)[-max_points:]
                x2 = list(viewer.state.raw_index)[-max_points:]
                y2 = list(viewer.state.raw_wave)[-max_points:]

                stress_packets = viewer.state.stress_packets
                raw_packets = viewer.state.raw_packets
                latest_stress = viewer.state.latest_stress_percent

            if x1 and y1:
                # Apply smoothing if requested
                y1_smooth = smooth_data(y1, smooth_window)
                line1.set_data(x1, y1_smooth)
                ax1.set_xlim(min(x1), max(x1))
                ax1.set_ylim(0, 105)

            if x2 and y2:
                # Apply smoothing if requested
                y2_smooth = smooth_data(y2, smooth_window)
                line2.set_data(x2, y2_smooth)
                ax2.set_xlim(min(x2), max(x2))
                ymin, ymax = min(y2_smooth), max(y2_smooth)
                pad = max(50, int((ymax - ymin) * 0.1))
                ax2.set_ylim(ymin - pad, ymax + pad)

            stress_display = "n/a" if latest_stress is None else f"{latest_stress:.1f}%"
            status_text.set_text(
                f"Stress packets: {stress_packets} | Raw EDA packets: {raw_packets} | Latest stress: {stress_display}"
            )

            fig.canvas.draw_idle()
            fig.canvas.flush_events()

            # Sleep to allow asyncio to process BLE notifications
            await asyncio.sleep(refresh_ms / 1000.0)

    except KeyboardInterrupt:
        pass
    finally:
        plt.ioff()
        plt.close(fig)


async def run_waveform_viewer(
    ring_addr: str | None = None,
    window_seconds: int = 10,
    refresh_ms: int = 120,
    smooth_window: int = 1,
) -> int:
    """Run live waveform viewer and block until plot window closes.

    Args:
        ring_addr: MAC address of ring (None for interactive selection)
        window_seconds: Time window to display
        refresh_ms: Plot refresh interval in milliseconds
        smooth_window: Moving average window (1=raw, 5-10=light, 15-30=heavy smoothing)
    """
    viewer = NuanicWaveformViewer(ring_addr=ring_addr)

    if not await viewer.connect_and_subscribe():
        print("[FAIL] Could not connect and subscribe to waveform streams")
        return 1

    print("[OK] Connected. Opening live plot window...")
    if smooth_window > 1:
        print(f"[SMOOTH] Applying {smooth_window}-point moving average filter")

    # Run BLE loop in background
    worker = asyncio.create_task(viewer.run_until_stopped())

    try:
        # Run plot in async mode so event loop can process BLE notifications
        await run_plot_async(
            viewer,
            window_seconds=window_seconds,
            refresh_ms=refresh_ms,
            smooth_window=smooth_window,
        )
    except KeyboardInterrupt:
        print("\n[STOP] Interrupted by user")
    finally:
        viewer._running = False  # Signal viewer to stop
        await viewer.stop()
        try:
            await asyncio.wait_for(worker, timeout=2.0)
        except asyncio.TimeoutError:
            worker.cancel()

    print("[STOP] Waveform viewer stopped")
    return 0
