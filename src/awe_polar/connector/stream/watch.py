from .verity_sense import PolarVeritySense


class PolarWatch(PolarVeritySense):
    """Connection wrapper for Polar Grit, Vantage, and other watches.

    Inherits all streaming logic from :class:`PolarVeritySense`.
    Config flags adjust behaviour to match watch needs:
    * ``_strict_hr = True`` — re-raise HR stream failures.
    * ``_catch_auth_on_features = False`` — let auth errors bubble up.
    * ``_ppg_default_rate = 135`` — watches have a higher default PPG rate.
    """

    def __init__(self, device, **kwargs):
        super().__init__(device, **kwargs)
        self._strict_hr = True
        self._catch_auth_on_features = False
        self._ppg_default_rate = 135
