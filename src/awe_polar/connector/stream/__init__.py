from .h10 import PolarH10
from .verity_sense import PolarVeritySense
from .watch import PolarWatch


def create_polar_connector(device, **kwargs):
    """Factory function to instantiate the correct connection class based on the Polar device name."""
    name = getattr(device, "name", "") or ""
    name_lower = name.lower()

    if "sense" in name_lower or "oh1" in name_lower:
        return PolarVeritySense(device, **kwargs)
    elif "h10" in name_lower:
        return PolarH10(device, **kwargs)
    else:
        return PolarWatch(device, **kwargs)


__all__ = [
    "PolarH10",
    "PolarVeritySense",
    "PolarWatch",
    "create_polar_connector",
]
