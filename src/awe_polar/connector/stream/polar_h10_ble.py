"""Backwards compatibility layer for Polar connection wrappers."""

from . import create_polar_connector


def HeartRate(device, **kwargs):
    """Backwards compatibility alias for create_polar_connector."""
    return create_polar_connector(device, **kwargs)
