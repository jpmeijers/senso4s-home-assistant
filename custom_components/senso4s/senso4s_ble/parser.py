"""Parser for Senso4s Basic and Plus BLE advertisements."""

from __future__ import annotations

import asyncio
import binascii
import datetime
import logging
import struct
from typing import Any

import bleak_retry_connector
from bleak import BleakClient, BleakError, BLEDevice
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
        self._last_history_reading = None
        self._history_periods = 0

    def update_device_adv_sync(
            self,
            ble_device: BLEDevice,
            service_info: BluetoothServiceInfoBleak,
    ) -> Senso4sDeviceData:
        """Update device data from advertisement (synchronous)."""

        # If we already have a device data object, reuse it
        if self._device is None:
            self._device = Senso4sDeviceData()

        self.logger.debug("update_device_adv_sync()")
        # self.logger.debug("BLE device: %s", ble_device)
        # self.logger.debug("Service info: %s", service_info)

        # If the device advertises a name, use it
        if hasattr(service_info, 'name') and service_info.name is not None:
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
            # Not an error if it's just an irrelevant advertisement
            self._device.error = "Not a Senso4s device"
            return self._device

        # self.logger.debug("Adv data: %s", binascii.hexlify(adv_data))

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
            # self.logger.debug("Model BASIC")
            self._device.model = Senso4sInfoFields.MODEL_BASIC

        else:
            # self.logger.debug("Model PLUS")
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

        # Intended use - byte 0, last 4 bits
        intended_use_num = adv_data[0] & 0b00001111
        intended_use = "Unknown"
        if intended_use_num < len(Senso4sInfoFields.INTENDED_USE):
            intended_use = Senso4sInfoFields.INTENDED_USE[intended_use_num]
        self._device.sensors[Senso4sDataFields.INTENDED_USE] = intended_use

        # 4a. Read Mass from advertising data
        mass_percentage = adv_data[1]
        if mass_percentage > 100:
            # self.logger.debug("Mass percentage out of range: 0x%02X", mass_percentage)
            self._device.sensors[Senso4sDataFields.MASS_PERCENT] = None
        else:
            self._device.sensors[Senso4sDataFields.MASS_PERCENT] = mass_percentage

        # 4b. Read Prediction from advertising data
        if adv_data[2] == 0xFF and adv_data[3] == 0xFF:
            # self.logger.debug("Prediction is 0xFFFF - unset")
            self._device.sensors[Senso4sDataFields.PREDICTION] = None
        else:
            prediction_minutes = ((adv_data[3] << 8) + adv_data[2]) * 15
            self._device.sensors[Senso4sDataFields.PREDICTION] = prediction_minutes

        return self._device

    async def update_device_adv(
            self,
            ble_device: BLEDevice,
            service_info: BluetoothServiceInfoBleak,
    ) -> Senso4sDeviceData:
        """Update device data from advertisement (async)."""
        return self.update_device_adv_sync(ble_device, service_info)

    async def update_device_full(
            self,
            ble_device: BLEDevice,
            service_info: BluetoothServiceInfoBleak,
    ) -> Senso4sDeviceData:
        """Update device data from advertisement and characteristics."""

        self.logger.debug("update_device_full()")

        # 1-4 from advertising data
        await self.update_device_adv(ble_device, service_info)
        # Even if there was an error in advertisement, we still try characteristics
        # unless it was a fatal error in advertisement parsing.
        # But update_device_adv_sync only returns error for short data.

        # 5. Establish Bluetooth connection with Senso4s PLUS/BASIC device and read characteristics
        client = None
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
            if self._device.sensors[Senso4sDataFields.SETUP_TIME] is not None and self._history_periods is not None:
                self.logger.debug("Setup time: %s, periods: %d", self._device.sensors[Senso4sDataFields.SETUP_TIME],
                                  self._history_periods)
                latest_reading_time = self._device.sensors[Senso4sDataFields.SETUP_TIME] + datetime.timedelta(
                    minutes=self._history_periods * 15)
                self._device.sensors[Senso4sDataFields.LAST_MEASUREMENT] = latest_reading_time

        except (BleakError, Exception) as error:
            self.logger.warning(
                "Error getting data from device: %s\n%s",
                ble_device.address,
                str(error),
            )
            # Only set the error if we don't have any sensor data yet
            if not self._device.sensors:
                self._device.error = str(error)
            else:
                # Clear any previous error if we have sensors
                self._device.error = None
        finally:
            if client is not None:
                self.logger.debug("Disconnecting client")
                await client.disconnect()

        self.logger.debug("returning device sensors")
        return self._device

    async def _read_mass(self, client):
        mass_percentage = None
        try:
            value = await client.read_gatt_char(Senso4sBleConstants.MASS_CHARACTERISTIC_UUID_READ)
            self.logger.debug("Mass char bytes: %s", binascii.hexlify(value))
            mass_percentage = value[0]
        except BleakError as err:
            self.logger.debug("Read mass exception: %s", err)
            return

        if mass_percentage > 100:
            # If any of the values below occur, an error occurred during measurement or during starting a new measuring cycle:
            self.logger.debug("Mass percentage out of range")
            self._device.sensors[Senso4sDataFields.MASS_PERCENT] = None

            # 0x[FE] - empty batteries (battery replacement needed),
            # 0x[FC] - error during starting a new measuring cycle,
            # 0x[FF] - the device has not been used yet or batteries were replaced.
            # 0x[FD] - unknown error - seen when total weight was below canister weight
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
                status = hex(mass_percentage)
                self.logger.debug("Unknown status %s", status)
                self._device.sensors[Senso4sDataFields.STATUS] = Senso4sDataFields.STATUS_UNKNOWN

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

        self._history_periods = 0
        self._last_history_reading = None
        self._history_event = asyncio.Event()

        try:
            await client.start_notify(
                Senso4sBleConstants.HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE,
                self.history_notification_handler,
            )
            # Write two zero bytes to char to trigger history dump
            await client.write_gatt_char(
                Senso4sBleConstants.HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE, b"\x00\x00"
            )

            # Wait up to 5s for historical data notifications
            try:
                await asyncio.wait_for(self._history_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.debug("Timeout waiting for history notifications")

        except BleakError as err:
            self.logger.debug("History read exception: %s", err)
            return
        finally:
            self._history_event = None
            try:
                await client.stop_notify(Senso4sBleConstants.HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE)
            except BleakError:
                pass

        # History is reported oldest to newest. Last value is latest or current reading.
        if self._last_history_reading is not None:
            self._device.sensors[Senso4sDataFields.MASS_KG] = (
                    float(self._last_history_reading) / 100
            )
        else:
            self.logger.debug("No measurement history received")
            self._device.sensors[Senso4sDataFields.MASS_KG] = None

        # Clear buffer for next run
        self._last_history_reading = None

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
            self.logger.debug("  History entry: %04X @ %04X", entry[0], entry[1])
            self._last_history_reading = entry[0]
            self._history_periods = self._history_periods + entry[1]
        if hasattr(self, "_history_event") and self._history_event:
            self._history_event.set()
