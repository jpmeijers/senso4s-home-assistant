"""Parser for Senso4s Basic and Plus BLE advertisements."""

from __future__ import annotations

import asyncio
import binascii
import datetime
import logging
import struct
from typing import Any
from zoneinfo import ZoneInfo

from bleak import BleakClient, BleakError, BLEDevice
import bleak_retry_connector
from habluetooth import BluetoothServiceInfoBleak

import homeassistant.util.dt
from .const import (
    Senso4sDataFields, Senso4sInfoFields, Senso4sBleConstants,
)
from .models import Senso4sDeviceData

_LOGGER = logging.getLogger(__name__)


class Senso4sBluetoothDevice:
    """Data for Senso4s BLE sensors."""

    def __init__(
            self,
            logger: logging.Logger,
    ):
        """Initialise bluetooth device data object."""
        super().__init__()
        self.logger = logger
        self._device = None
        self._latest_reading = None
        self._latest_reading_time = None

    async def update_device_adv(
            self,
            ble_device: BLEDevice,
            service_info: BluetoothServiceInfoBleak,
    ) -> Senso4sDeviceData:

        # Init data device
        self._device = Senso4sDeviceData()

        self.logger.debug("update_device_adv()")
        self.logger.debug("BLE device: %s", ble_device)
        self.logger.debug("Data device: %s", self._device)
        self.logger.debug("Service info: %s", service_info)

        # If the device advertises a name, use it
        if service_info.name is not None:
            self._device.name = service_info.name

        self._device.identifier = ble_device.address.replace(":", "").lower()
        self._device.address = ble_device.address

        # Read manufacturer data from advertisement. e.g. 854a6b512e00fc8f4704b77d - indexed by manufacturer - either Senso4s or nrf
        adv_data = None
        if Senso4sBleConstants.SENSO4S_MANUFACTURER in service_info.manufacturer_data:
            adv_data = service_info.manufacturer_data[Senso4sBleConstants.SENSO4S_MANUFACTURER]
        elif Senso4sBleConstants.NORDIC_MANUFACTURER in service_info.manufacturer_data:
            adv_data = service_info.manufacturer_data[Senso4sBleConstants.NORDIC_MANUFACTURER]
        else:
            error_msg = "Not Senso4s device"
            self.logger.error(error_msg)
            self._device.error = error_msg
            return self._device

        self.logger.debug("Adv data: %s", binascii.hexlify(adv_data))

        # Add RSSI as a sensor
        self._device.sensors[Senso4sDataFields.RSSI] = service_info.rssi

        if len(adv_data) < 12:
            error_msg = "BLE advertising data too short: " + ble_device.address
            self.logger.error(error_msg)
            self._device.error = error_msg
            return self._device

        # 2. Read battery level from advertising data
        battery_percentage = adv_data[4]
        self._device.sensors[Senso4sDataFields.BATTERY] = battery_percentage

        # 3a. Check status
        if adv_data[1] == 0xFE:
            self._device.sensors[Senso4sDataFields.STATUS] = (
                Senso4sDataFields.STATUS_BATTERY_EMPTY
            )
        elif adv_data[1] == 0xFC:
            self._device.sensors[Senso4sDataFields.STATUS] = (
                Senso4sDataFields.STATUS_ERROR_STARTING
            )
        elif adv_data[1] == 0xFF:
            self._device.sensors[Senso4sDataFields.STATUS] = (
                Senso4sDataFields.STATUS_NOT_CONFIGURED
            )
        else:
            self._device.sensors[Senso4sDataFields.STATUS] = Senso4sDataFields.STATUS_OK

        # 3b. Get model and warnings
        if adv_data[0] & 0b11110000 == 0b10000000:
            self.logger.debug("Model BASIC")
            self._device.model = Senso4sInfoFields.MODEL_BASIC

        elif adv_data[0] & 0b10001111 == 0b00000011:
            self.logger.debug("Model PLUS")
            self._device.model = Senso4sInfoFields.MODEL_PLUS

            # The warning entities will only appear for the PLUS model
            self._device.sensors[Senso4sDataFields.WARNING_MOVEMENT] = (
                    adv_data[0] & 0b01000000 > 0
            )
            self._device.sensors[Senso4sDataFields.WARNING_INCLINATION] = (
                    adv_data[0] & 0b00100000 > 0
            )
            self._device.sensors[Senso4sDataFields.WARNING_TEMPERATURE] = (
                    adv_data[0] & 0b00010000 > 0
            )

        else:
            error_msg = "Invalid model"
            self.logger.error(error_msg)
            self._device.error = error_msg
            return self._device

        # 4a. Read Mass from advertising data
        mass_percentage = adv_data[1]
        if mass_percentage > 100:
            self.logger.debug("Mass percentage out of range: 0x%02X", mass_percentage)
            self._device.sensors[Senso4sDataFields.MASS_PERCENT] = None
        else:
            self._device.sensors[Senso4sDataFields.MASS_PERCENT] = mass_percentage

        # 4b. Read Prediction from advertising data
        if adv_data[2] == 0xFF and adv_data[3] == 0xFF:
            self.logger.debug("Prediction is 0xFFFF - unset")
            self._device.sensors[Senso4sDataFields.PREDICTION] = None
        else:
            prediction_minutes = ((adv_data[3] << 8) + adv_data[2]) * 15
            self._device.sensors[Senso4sDataFields.PREDICTION] = prediction_minutes

        return self._device

    async def update_device_full(
            self,
            ble_device: BLEDevice,
            service_info: BluetoothServiceInfoBleak,
    ) -> Senso4sDeviceData:
        """Update device data from advertisement and characteristics."""

        self.logger.debug("update_device_full()")

        # 1-4 from advertising data
        await self.update_device_adv(ble_device, service_info)
        if self._device.error is not None:
            return self._device

        # 5. Establish Bluetooth connection with Senso4s PLUS/BASIC device and read characteristics
        try:
            # _get_client creates a connection with the device
            self.logger.debug("Connecting to device")
            client = await self._get_client(ble_device)
            if client is None:
                error_msg = "BLE client is None"
                self.logger.error(error_msg)
                self._device.error = error_msg
                return self._device

            self.logger.debug("Connected. Reading characteristics")
            # In parallel read data from relevant characteristics
            tasks = [
                self._read_mass(client),
                self._read_parameters(client),
                self._read_history(client),
                self._read_setup_time(client),
            ]
            await asyncio.gather(*tasks)

            # Last measurement time is setup time plus last history point
            if self._device.sensors[Senso4sDataFields.SETUP_TIME] is not None and self._latest_reading_time is not None:
                latest_reading_time = self._device.sensors[Senso4sDataFields.SETUP_TIME] + datetime.timedelta(
                    minutes=(self._latest_reading_time + 1) * 15)
                self._device.sensors[Senso4sDataFields.LAST_MEASUREMENT] = latest_reading_time

        except (BleakError, Exception) as error:
            self.logger.error(
                "Error getting data from device: %s\n%s",
                ble_device.address,
                str(error),
            )
            self._device.error = str(error)
        finally:
            self.logger.debug("Disconnecting client")
            await client.disconnect()

        self.logger.debug("returning device sensors")
        return self._device

    async def _read_mass(self, client):
        mass_percentage = None
        try:
            # NOTE: To read this characteristic, one must first enable the NOTIFY property.
            await client.start_notify(
                Senso4sBleConstants.MASS_CHARACTERISTIC_UUID_READ,
                self.mass_notification_handler,
            )

            value = await client.read_gatt_char(Senso4sBleConstants.MASS_CHARACTERISTIC_UUID_READ)
            self.logger.debug("Mass char bytes: %s", binascii.hexlify(value))
            mass_percentage = value[0]
        except BleakError as err:
            self.logger.debug("Start notify mass exception: %s", err)
            return
        finally:
            await client.stop_notify(Senso4sBleConstants.MASS_CHARACTERISTIC_UUID_READ)

        if mass_percentage > 100:
            # If any of the values below occur, an error occurred during measurement or during starting a new measuring cycle:
            self.logger.debug("Mass percentage out of range")
            self._device.sensors[Senso4sDataFields.MASS_PERCENT] = None

            # 0x[FE] - empty batteries (battery replacement needed),
            # 0x[FC] - error during starting a new measuring cycle,
            # 0x[FF] - the device has not been used yet or batteries were replaced.
            if mass_percentage == 0xFE:
                status = Senso4sDataFields.STATUS_BATTERY_EMPTY
                self.logger.debug(status)
                self._device.sensors[Senso4sDataFields.STATUS] = status
            elif mass_percentage == 0xFC:
                status = Senso4sDataFields.STATUS_ERROR_STARTING
                self.logger.debug(status)
                self._device.sensors[Senso4sDataFields.STATUS] = status
            elif mass_percentage == 0xFF:
                status = Senso4sDataFields.STATUS_NOT_CONFIGURED
                self.logger.debug(status)
                self._device.sensors[Senso4sDataFields.STATUS] = status
            else:
                status = f"{0:02X}".format(mass_percentage)
                self.logger.debug("Unknown status %s", status)
                self._device.sensors[Senso4sDataFields.STATUS] = status

        else:
            # If value of this byte is between 0x[00] and 0x[64], then this byte represents a mass value in percentage [%].
            self._device.sensors[Senso4sDataFields.MASS_PERCENT] = mass_percentage
            self._device.sensors[Senso4sDataFields.STATUS] = Senso4sDataFields.STATUS_OK

    async def _read_parameters(self, client):
        value = await client.read_gatt_char(Senso4sBleConstants.PARAMS_CHARACTERISTIC_UUID_READWRITE)
        self.logger.debug("Param char bytes: %s", binascii.hexlify(value))
        params = struct.unpack("<HHB", value)
        self._device.sensors[Senso4sDataFields.CYLINDER_WEIGHT] = params[0] / 100
        self._device.sensors[Senso4sDataFields.CYLINDER_CAPACITY] = params[1] / 100

    async def _read_history(self, client):
        """Read history.

        NOTE: To read history data, one must first enable NOTIFY property and then WRITE value 0 in uint16
        format to the characteristic. After that the stream of history data will be available on this
        characteristic.
        """

        try:
            await client.start_notify(
                Senso4sBleConstants.HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE,
                self.history_notification_handler,
            )
        except BleakError as err:
            self.logger.debug("Start notify exception: %s", err)
            return

        # Write two zero bytes to char to trigger history dump
        await client.write_gatt_char(
            Senso4sBleConstants.HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE, b"\x00\x00"
        )

        # Wait up to 1s for historical data notifications - todo use a timeout on notify receive
        await asyncio.sleep(1.0)

        await client.stop_notify(Senso4sBleConstants.HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE)

        # History is reported oldest to newest. Last value is latest or current reading.
        if self._latest_reading is not None:
            self._device.sensors[Senso4sDataFields.MASS_KG] = (
                    float(self._latest_reading) / 100
            )
        else:
            self.logger.debug("No measurement history received")
            self._device.sensors[Senso4sDataFields.MASS_KG] = None

        # Clear buffer for next run
        self._latest_reading = None

    async def _read_setup_time(self, client):
        value = await client.read_gatt_char(Senso4sBleConstants.SETUPTIME_CHARACTERISTIC_UUID_READ)
        self.logger.debug("Setup time char bytes: %s", binascii.hexlify(value))
        time_parts = struct.unpack("<HBBBBB", value)
        # year might be zero, making datetime throw an error
        if time_parts[0] == 0:
            self._device.sensors[Senso4sDataFields.SETUP_TIME] = None
        else:
            setup_time = datetime.datetime(
                year=time_parts[0],
                month=time_parts[1],
                day=time_parts[2],
                hour=time_parts[3],
                minute=time_parts[4],
                tzinfo=homeassistant.util.dt.get_default_time_zone(),
            )
            # The scale reports the setup time as local time.
            # Assuming it is the timezone of the app that set it up, and that it aligns with the timezone used by this Home Assistant.
            # setup_time = setup_time.replace(tzinfo=datetime.Local)
            self._device.sensors[Senso4sDataFields.SETUP_TIME] = setup_time

    async def _get_client(self, ble_device: BLEDevice) -> BleakClient:
        """Connect to the BLEDevice."""
        try:
            return await bleak_retry_connector.establish_connection(
                client_class=BleakClient,
                device=ble_device,
                name=ble_device.address,
            )
        except (BleakError, Exception) as e:
            self.logger.error(
                "Error connecting to device: %s\n%s",
                ble_device.address,
                str(e),
            )
        return None

    def mass_notification_handler(self, _: Any, data: bytearray) -> None:
        """Mass data notifications."""
        self.logger.debug("Mass notification bytes: %s", binascii.hexlify(data))

    def history_notification_handler(self, _: Any, data: bytearray) -> None:
        """Parse historical data notifications."""
        self.logger.debug("History notification bytes: %s", binascii.hexlify(data))
        entries = struct.iter_unpack("<HH", data)
        for entry in entries:
            # entry[0] => mass in dag
            # entry[1] => duration in 15m intervals
            # Home Assistant only takes current sensors, so ignore history
            self.logger.debug("  History entry: %04X @ %04X", entry[0], entry[1])
            self._latest_reading = entry[0]
            self._latest_reading_time = entry[1]
