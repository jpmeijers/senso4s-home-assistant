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

from .models import Senso4sDeviceData
from .parser import Senso4sBluetoothDevice
from .const import Senso4sDataFields, Senso4sInfoFields, Senso4sBleConstants

import json
import os

# Get the version from manifest.json to keep them in sync
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "..", "manifest.json")
with open(MANIFEST_PATH, encoding="utf-8") as f:
    __version__ = json.load(f)["version"]

__all__ = [
    "Senso4sDeviceData",
    "Senso4sBluetoothDevice",
    "Senso4sDataFields",
    "Senso4sInfoFields",
    "Senso4sBleConstants",
    "SensorDescription",
    "SensorDeviceInfo",
    "DeviceKey",
    "SensorUpdate",
    "SensorDeviceClass",
    "SensorValue",
    "Units",
]
