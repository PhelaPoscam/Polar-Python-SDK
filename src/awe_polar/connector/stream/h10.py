from typing import Callable, Optional
from polar_python.constants import PmdMeasurementType, PmdSettingType
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
        import traceback

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
        if self.ecg_callback and PmdMeasurementType.ECG in features:
            try:
                ecg_settings = await self._get_default_settings(PmdMeasurementType.ECG)
                await self.polar_device.start_ecg_stream(
                    self._ecg_handler,
                    sample_rate=ecg_settings.get(PmdSettingType.SAMPLE_RATE, 130),
                    resolution=ecg_settings.get(PmdSettingType.RESOLUTION, 14),
                )
                print("[DEBUG] ECG stream started OK")
            except Exception:
                print("[DEBUG] ECG stream failed:")
                traceback.print_exc()

        # 3. Start ACC stream
        if self.acc_callback and PmdMeasurementType.ACC in features:
            try:
                acc_settings = await self._get_default_settings(PmdMeasurementType.ACC)
                await self.polar_device.start_acc_stream(
                    self._acc_handler,
                    sample_rate=acc_settings.get(PmdSettingType.SAMPLE_RATE, 200),
                    resolution=acc_settings.get(PmdSettingType.RESOLUTION, 16),
                    range=acc_settings.get(PmdSettingType.RANGE, 8),
                    channels=acc_settings.get(PmdSettingType.CHANNELS, None),
                )
                print("[DEBUG] ACC stream started OK")
            except Exception:
                print("[DEBUG] ACC stream failed:")
                traceback.print_exc()

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
