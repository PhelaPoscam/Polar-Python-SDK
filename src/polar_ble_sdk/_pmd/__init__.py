"""Low-level Polar Measurement Data (PMD) protocol client.

Derived from polar-python (MIT, Copyright (c) 2024 Zachary Liu) and following
Polar's official BLE SDK (Polar SDK License). Those parts keep their own
licences; see NOTICE and licenses/ at the repository root.
"""

from .device import PolarDevice

__all__ = ["PolarDevice"]
