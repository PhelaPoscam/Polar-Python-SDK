"""Wrapper around polar-python to handle streaming from Polar H10, Grit, and Verity Sense."""

from __future__ import annotations

import asyncio
from typing import Callable, Optional
from polar_python import PolarDevice
from polar_python.constants import PmdMeasurementType


class HeartRate:
    """Wrapper around PolarDevice to receive HR, HRV, ECG, and kinematic streams."""

    def __init__(
        self,
        device,
        callback: Optional[Callable] = None,
        ecg_callback: Optional[Callable] = None,
        ppg_callback: Optional[Callable] = None,
        acc_callback: Optional[Callable] = None,
        ppi_callback: Optional[Callable] = None,
        gyro_callback: Optional[Callable] = None,
        mag_callback: Optional[Callable] = None,
        **kwargs,
    ) -> None:
        self.device = device
        self.callback = callback  # Callback for Heart Rate and RR-Intervals
        self.ecg_callback = ecg_callback
        self.ppg_callback = ppg_callback
        self.acc_callback = acc_callback
        self.ppi_callback = ppi_callback
        self.gyro_callback = gyro_callback
        self.mag_callback = mag_callback

        self.polar_device = None
        self._running = False

    async def start_notify(self) -> None:
        """Connect to device and start all supported/requested notifications."""
        self.polar_device = PolarDevice(self.device)
        await self.polar_device.connect()
        self._running = True

        # Discover available features on this Polar device
        features = await self.polar_device.get_available_features()

        # 1. Start standard Heart Rate stream (always start if callback is set)
        if self.callback:
            await self.polar_device.start_hr_stream(self._hr_handler)

        # 2. Start ECG stream
        if self.ecg_callback and PmdMeasurementType.ECG in features:
            await self.polar_device.start_ecg_stream(self._ecg_handler)

        # 3. Start PPG stream
        if self.ppg_callback and PmdMeasurementType.PPG in features:
            await self.polar_device.start_ppg_stream(self._ppg_handler)

        # 4. Start ACC stream
        if self.acc_callback and PmdMeasurementType.ACC in features:
            await self.polar_device.start_acc_stream(self._acc_handler)

        # 5. Start PPI stream
        if self.ppi_callback and PmdMeasurementType.PPI in features:
            await self.polar_device.start_ppi_stream(self._ppi_handler)

        # 6. Start Gyro stream
        if self.gyro_callback and PmdMeasurementType.GYRO in features:
            await self.polar_device.start_gyro_stream(self._gyro_handler)

        # 7. Start Magnetometer stream
        if self.mag_callback and PmdMeasurementType.MAG in features:
            await self.polar_device.start_mag_stream(self._mag_handler)

    async def stop_notify(self) -> None:
        """Stop all streams and disconnect."""
        if self._running and self.polar_device:
            await self.polar_device.disconnect()
            self._running = False

    def _hr_handler(self, hr_data) -> None:
        if self.callback:
            try:
                self.callback((hr_data.heartrate, hr_data.rr_intervals))
            except Exception:
                pass

    def _ecg_handler(self, ecg_data) -> None:
        if self.ecg_callback:
            try:
                self.ecg_callback((ecg_data.timestamp, ecg_data.data))
            except Exception:
                pass

    def _acc_handler(self, acc_data) -> None:
        if self.acc_callback:
            try:
                self.acc_callback((acc_data.timestamp, acc_data.data))
            except Exception:
                pass

    def _ppg_handler(self, ppg_data) -> None:
        if self.ppg_callback:
            try:
                self.ppg_callback((ppg_data.timestamp, ppg_data.samples))
            except Exception:
                pass

    def _ppi_handler(self, ppi_data) -> None:
        if self.ppi_callback:
            try:
                ppi_vals = [s.ppi for s in ppi_data.samples if not s.invalid_ppi]
                if ppi_vals:
                    self.ppi_callback((ppi_data.timestamp, ppi_vals))
            except Exception:
                pass

    def _gyro_handler(self, gyro_data) -> None:
        if self.gyro_callback:
            try:
                self.gyro_callback((gyro_data.timestamp, gyro_data.data))
            except Exception:
                pass

    def _mag_handler(self, mag_data) -> None:
        if self.mag_callback:
            try:
                mag_vals = [(s.x, s.y, s.z) for s in mag_data.data]
                self.mag_callback((mag_data.timestamp, mag_vals))
            except Exception:
                pass
