"""Test for Senso4s BLE parser and control."""

import asyncio
import logging
import sys

from bleak import BleakScanner
from senso4s_ble import Senso4sBluetoothDevice, Senso4sBleConstants

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

SCAN_FOR_DEVICE = True


async def scan_for_device():
    """Scan for devices and return a device if the manufacturer matches."""
    while True:
        devices = await BleakScanner.discover(return_adv=True)
        print("Devices:", devices.values())

        # Check if the desired device is in the list
        for device, adv in devices.values():
            print("ADV:", adv.manufacturer_data)
            if Senso4sBleConstants.SENSO4S_MANUFACTURER in adv.manufacturer_data or Senso4sBleConstants.NORDIC_MANUFACTURER in adv.manufacturer_data:
                return device, adv


if __name__ == "__main__":
    parser = Senso4sBluetoothDevice(_LOGGER)


    async def test_data_update():
        """Activate scan mode for the Bluetooth interface."""

        print(f"Waiting for a Senso4s device")
        device, adv = await scan_for_device()

        print(f"Found device\n{device}")
        # Connect and get the data from the sensors.
        polled_device = await parser.update_device_full(device, adv)
        print(f"---- Senso4s Device Data ---- \n{polled_device}")


    try:
        print("Looking for manufacturer", Senso4sBleConstants.SENSO4S_MANUFACTURER)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(test_data_update())
    except KeyboardInterrupt:
        print("Scan interrupted by user.")
