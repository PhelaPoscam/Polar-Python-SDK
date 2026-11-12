from .h10 import PolarH10
from .verity_sense import PolarVeritySense


def create_polar_connector(device, **kwargs):
    """Factory function to instantiate the correct connection class based on the Polar device name."""
    name_lower = (getattr(device, "name", "") or "").lower()

    if "h10" in name_lower:
        return PolarH10(device, **kwargs)
    if "sense" in name_lower or "oh1" in name_lower:
        return PolarVeritySense(device, **kwargs)
    # Watches (Grit, Vantage): same streams, but HR/auth failures must surface.
    kwargs.setdefault("strict_hr", True)
    kwargs.setdefault("catch_auth_on_features", False)
    return PolarVeritySense(device, **kwargs)


__all__ = [
    "PolarH10",
    "PolarVeritySense",
    "create_polar_connector",
]
