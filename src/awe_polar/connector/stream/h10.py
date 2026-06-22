from typing import Callable, Optional
from polar_python.constants import PmdMeasurementType
from .base import BasePolarDevice


class PolarH10(BasePolarDevice):
    """Connection wrapper for Polar H10 chest strap sensor."""

    def __init__(
        self,
        device,
        callback: Optional[Callable] = None,
        ecg_callback: Optional[Callable] = None,
        acc_callback: Optional[Callable] = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("reconnect_before_streaming", True)
        super().__init__(device, **kwargs)
        self.callback = callback  # Callback for Heart Rate and RR-Intervals
        self.ecg_callback = ecg_callback
        self.acc_callback = acc_callback

    async def start_streams(self) -> None:
        """Start the H10 specific streams (HR, ECG, ACC)."""
        features = await self.polar_device.get_available_features()

        # 1. Start standard Heart Rate stream
        if self.callback:
            try:
                await self.polar_device.start_hr_stream(self._hr_handler)
                print("[DEBUG] HR stream started OK")
            except Exception as e:
                print(f"[DEBUG] HR stream failed: {e}")
                raise

        # 2. Start ECG stream
        await self._start_pmd_stream(
            self.ecg_callback, PmdMeasurementType.ECG, "start_ecg_stream",
            self._ecg_handler, features,
            {"sample_rate": 130, "resolution": 14}, "ECG",
        )

        # 3. Start ACC stream
        await self._start_pmd_stream(
            self.acc_callback, PmdMeasurementType.ACC, "start_acc_stream",
            self._acc_handler, features,
            {"sample_rate": 200, "resolution": 16, "range": 8, "channels": None},
            "ACC",
        )

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
