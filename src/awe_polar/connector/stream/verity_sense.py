from typing import Callable, Optional
from polar_python.constants import PmdMeasurementType, PmdSettingType
from .base import BasePolarDevice


class PolarVeritySense(BasePolarDevice):
    """Connection wrapper for Polar Verity Sense / OH1 optical heart rate sensors."""

    def __init__(
        self,
        device,
        callback: Optional[Callable] = None,
        ppi_callback: Optional[Callable] = None,
        ppg_callback: Optional[Callable] = None,
        acc_callback: Optional[Callable] = None,
        gyro_callback: Optional[Callable] = None,
        mag_callback: Optional[Callable] = None,
        **kwargs,
    ) -> None:
        super().__init__(device, **kwargs)
        self.callback = callback  # Callback for Heart Rate and RR-Intervals
        self.ppi_callback = ppi_callback
        self.ppg_callback = ppg_callback
        self.acc_callback = acc_callback
        self.gyro_callback = gyro_callback
        self.mag_callback = mag_callback
        self._ppi_active = False

    async def start_streams(self) -> None:
        """Start the Verity Sense specific streams."""
        import traceback

        try:
            features = await self.polar_device.get_available_features()
            feature_names = [f.name for f in features] if features else []
            print(f"[DEBUG] Available PMD features: {feature_names or '(none)'}")
        except Exception:
            print("[DEBUG] get_available_features() failed:")
            traceback.print_exc()
            features = []

        # 1. Start standard Heart Rate stream
        if self.callback:
            try:
                await self.polar_device.start_hr_stream(self._hr_handler)
                print("[DEBUG] HR stream started OK")
            except Exception:
                print("[DEBUG] HR stream failed:")
                traceback.print_exc()

        # 2. Start PPG stream
        if self.ppg_callback and PmdMeasurementType.PPG in features:
            try:
                ppg_settings = await self._get_default_settings(PmdMeasurementType.PPG)
                await self.polar_device.start_ppg_stream(
                    self._ppg_handler,
                    sample_rate=ppg_settings.get(PmdSettingType.SAMPLE_RATE, 55),
                    resolution=ppg_settings.get(PmdSettingType.RESOLUTION, 22),
                    channels=ppg_settings.get(PmdSettingType.CHANNELS, 4),
                )
                print("[DEBUG] PPG stream started OK")
            except Exception:
                print("[DEBUG] PPG stream failed:")
                traceback.print_exc()
        elif self.ppg_callback:
            print(f"[DEBUG] PPG skipped — not in features: {feature_names}")

        # 3. Start ACC stream
        if self.acc_callback and PmdMeasurementType.ACC in features:
            try:
                acc_settings = await self._get_default_settings(PmdMeasurementType.ACC)
                await self.polar_device.start_acc_stream(
                    self._acc_handler,
                    sample_rate=acc_settings.get(PmdSettingType.SAMPLE_RATE, 52),
                    resolution=acc_settings.get(PmdSettingType.RESOLUTION, 16),
                    range=acc_settings.get(PmdSettingType.RANGE, 8),
                    channels=acc_settings.get(PmdSettingType.CHANNELS, None),
                )
                print("[DEBUG] ACC stream started OK")
            except Exception:
                print("[DEBUG] ACC stream failed:")
                traceback.print_exc()
        elif self.acc_callback:
            print(f"[DEBUG] ACC skipped — not in features: {feature_names}")

        # 4. Start PPI stream
        if self.ppi_callback and PmdMeasurementType.PPI in features:
            try:
                self._ppi_active = True
                await self.polar_device.start_ppi_stream(self._ppi_handler)
                print("[DEBUG] PPI stream started OK")
            except Exception:
                print("[DEBUG] PPI stream failed:")
                traceback.print_exc()

        # 5. Start Gyro stream
        if self.gyro_callback and PmdMeasurementType.GYRO in features:
            try:
                gyro_settings = await self._get_default_settings(PmdMeasurementType.GYRO)
                await self.polar_device.start_gyro_stream(
                    self._gyro_handler,
                    sample_rate=gyro_settings.get(PmdSettingType.SAMPLE_RATE, 52),
                    resolution=gyro_settings.get(PmdSettingType.RESOLUTION, 16),
                    range=gyro_settings.get(PmdSettingType.RANGE, 2),
                    channels=gyro_settings.get(PmdSettingType.CHANNELS, 3),
                )
                print("[DEBUG] GYRO stream started OK")
            except Exception:
                print("[DEBUG] GYRO stream failed:")
                traceback.print_exc()
        elif self.gyro_callback:
            print(f"[DEBUG] GYRO skipped — not in features: {feature_names}")

        # 6. Start Magnetometer stream
        if self.mag_callback and PmdMeasurementType.MAG in features:
            try:
                mag_settings = await self._get_default_settings(PmdMeasurementType.MAG)
                await self.polar_device.start_mag_stream(
                    self._mag_handler,
                    sample_rate=mag_settings.get(PmdSettingType.SAMPLE_RATE, 20),
                    resolution=mag_settings.get(PmdSettingType.RESOLUTION, 16),
                    range=mag_settings.get(PmdSettingType.RANGE, 50),
                    channels=mag_settings.get(PmdSettingType.CHANNELS, 3),
                )
                print("[DEBUG] MAG stream started OK")
            except Exception:
                print("[DEBUG] MAG stream failed:")
                traceback.print_exc()
        elif self.mag_callback:
            print(f"[DEBUG] MAG skipped — not in features: {feature_names}")

    async def stop_notify(self) -> None:
        self._ppi_active = False
        await super().stop_notify()

    def _hr_handler(self, hr_data) -> None:
        if self.callback:
            # If PPI stream is active, the standard HR service reports 0 BPM.
            # In this case, we ignore it and rely on the PPI stream instead.
            if self._ppi_active:
                return
            try:
                self.callback((hr_data.heartrate, hr_data.rr_intervals))
            except Exception:
                pass

    def _ppi_handler(self, ppi_data) -> None:
        ppi_vals = [s.ppi for s in ppi_data.samples if not s.invalid_ppi]
        if self.ppi_callback:
            try:
                if ppi_vals:
                    self.ppi_callback((ppi_data.timestamp, ppi_vals))
            except Exception:
                pass
        # Forward the computed heart rate from the PPI samples to the standard HR callback
        if self.callback and ppi_data.samples:
            try:
                latest_sample = ppi_data.samples[-1]
                self.callback((latest_sample.hr, ppi_vals))
            except Exception:
                pass

    def _ppg_handler(self, ppg_data) -> None:
        if self.ppg_callback:
            try:
                self.ppg_callback((ppg_data.timestamp, ppg_data.samples))
            except Exception:
                import traceback
                traceback.print_exc()

    def _acc_handler(self, acc_data) -> None:
        if self.acc_callback:
            try:
                self.acc_callback((acc_data.timestamp, acc_data.data))
            except Exception:
                import traceback
                traceback.print_exc()

    def _gyro_handler(self, gyro_data) -> None:
        if self.gyro_callback:
            try:
                self.gyro_callback((gyro_data.timestamp, gyro_data.data))
            except Exception:
                import traceback
                traceback.print_exc()

    def _mag_handler(self, mag_data) -> None:
        if self.mag_callback:
            try:
                mag_vals = [(s.x, s.y, s.z) for s in mag_data.data]
                self.mag_callback((mag_data.timestamp, mag_vals))
            except Exception:
                import traceback
                traceback.print_exc()
