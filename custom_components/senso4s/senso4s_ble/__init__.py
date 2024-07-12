"""Parser for Senso4s BLE advertisements."""

from __future__ import annotations

from sensor_state_data import (
    DeviceKey,
    SensorDescription,
    SensorDeviceClass,
    SensorDeviceInfo,
    SensorUpdate,
    SensorValue,
    Units,
)

from .models import Senso4sDevice
from .parser import Senso4sBluetoothDeviceData, Senso4sDeviceInfo, Senso4sSensor

__version__ = "0.1.0"

__all__ = [
    "Senso4sDevice",
    "Senso4sSensor",
    "Senso4sBluetoothDeviceData",
    "Senso4sDeviceInfo",
    "SensorDescription",
    "SensorDeviceInfo",
    "DeviceKey",
    "SensorUpdate",
    "SensorDeviceClass",
    "SensorValue",
    "Units",
]
