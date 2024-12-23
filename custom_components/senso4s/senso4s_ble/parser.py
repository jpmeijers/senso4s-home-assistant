"""Parser for Senso4s Basic and Plus BLE advertisements."""

from __future__ import annotations

import asyncio
import binascii
import datetime
import logging
import struct
from zoneinfo import ZoneInfo

from bleak import BleakClient, BleakError, BLEDevice
import bleak_retry_connector
from habluetooth import BluetoothServiceInfoBleak
from sensor_state_data.enum import StrEnum

from .const import (
    HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE,
    MASS_CHARACTERISTIC_UUID_READ,
    PARAMS_CHARACTERISTIC_UUID_READWRITE,
    SENSO4S_MANUFACTURER,
    SETUPTIME_CHARACTERISTIC_UUID_READ,
)
from .models import Senso4sDevice

_LOGGER = logging.getLogger(__name__)


class Senso4sSensor(StrEnum):
    MODEL_BASIC = "Basic"
    MODEL_PLUS = "Plus"

    PREDICTION = "prediction"
    MASS_KG = "mass"
    MASS_PERCENT = "mass_percentage"

    BATTERY = "battery"
    RSSI = "rssi"
    WARNINGS = "warnings"
    STATUS = "status"

    CYLINDER_CAPACITY = "cylider_capacity"
    CYLINDER_WEIGHT = "cylinder_weight"
    SETUP_TIME = "setup_time"

    STATUS_OK = "ok"
    STATUS_BATTERY_EMPTY = "battery empty"
    STATUS_ERROR_STARTING = "error starting measurement"
    STATUS_NOT_CONFIGURED = "not configured"

    WARNING_NONE = "none"
    WARNING_MOVEMENT = "movement"
    WARNING_INCLINATION = "inclination"
    WARNING_TEMPERATURE = "temperature"


class Senso4sDeviceInfo(StrEnum):
    """Device information."""

    DEVICE_NAME = "name"
    APPEARANCE = "appearance"
    MANUFACTURER_NAME = "manufacturer"
    MODEL_NUMBER = "model"
    HARDWARE_REV = "hw_version"
    FIRMWARE_REV = "sw_version"


class Senso4sBluetoothDeviceData:
    """Data for Senso4s BLE sensors."""

    def __init__(
        self,
        logger: logging.Logger,
    ):
        super().__init__()
        self.logger = logger
        self._client = None
        self._device = None
        self._latest_reading = None

    def history_notification_handler(self, _: Any, data: bytearray) -> None:
        """Parse hitorical data notifications."""
        entries = struct.iter_unpack("<HH", data)
        for entry in entries:
            # entry[0] => mass in dag
            # entry[1] => duration in 15m intervals
            self._latest_reading = entry[0]

    async def _read_mass(self) -> bool:
        self._device.sensors[Senso4sSensor.STATUS] = Senso4sSensor.STATUS_OK
        value = await self._client.read_gatt_char(MASS_CHARACTERISTIC_UUID_READ)
        if value[0] == 0xFE:
            status = Senso4sSensor.STATUS_BATTERY_EMPTY
            self.logger.debug(status)
            self._device.sensors[Senso4sSensor.STATUS] = status
            return False
        if value[0] == 0xFC:
            status = Senso4sSensor.STATUS_ERROR_STARTING
            self.logger.debug(status)
            self._device.sensors[Senso4sSensor.STATUS] = status
            return False
        if value[0] == 0xFF:
            status = Senso4sSensor.STATUS_NOT_CONFIGURED
            self.logger.debug(status)
            self._device.sensors[Senso4sSensor.STATUS] = status
            # return False

        mass_percentage = value[0]
        if mass_percentage == 0xFF:
            self.logger.debug("Mass percentage is 0xFF")
            self._device.sensors[Senso4sSensor.MASS_PERCENT] = None
        else:
            self._device.sensors[Senso4sSensor.MASS_PERCENT] = mass_percentage
        return True

    async def _read_parameters(self):
        value = await self._client.read_gatt_char(PARAMS_CHARACTERISTIC_UUID_READWRITE)
        params = struct.unpack("<HHB", value)
        self._device.sensors[Senso4sSensor.CYLINDER_WEIGHT] = params[0] / 100
        self._device.sensors[Senso4sSensor.CYLINDER_CAPACITY] = params[1] / 100

    async def _read_setup_time(self):
        value = await self._client.read_gatt_char(SETUPTIME_CHARACTERISTIC_UUID_READ)
        timeparts = struct.unpack("<HBBBBB", value)
        setup_time = datetime.datetime(
            year=timeparts[0],
            month=timeparts[1],
            day=timeparts[2],
            hour=timeparts[3],
            minute=timeparts[4],
            tzinfo=ZoneInfo("localtime"),
        )
        # setup_time = setup_time.replace(tzinfo=datetime.Local) # The scale reports the setup time as local time - assuming the timezone of the app that set it up
        self._device.sensors[Senso4sSensor.SETUP_TIME] = setup_time

    async def _read_history(self):
        try:
            await self._client.start_notify(
                HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE,
                self.history_notification_handler,
            )
        except BleakError as err:
            self.logger.debug("Start notify exception: %s", err)
            return False

        await self._client.write_gatt_char(
            HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE, b"\x00\x00"
        )

        # Wait up to 5s for historical data notifications.
        await asyncio.sleep(5.0)

        await self._client.stop_notify(HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE)

        if self._latest_reading is not None:
            self._device.sensors[Senso4sSensor.MASS_KG] = (
                float(self._latest_reading) / 100
            )
        else:
            self.logger.debug("No measurement history received")
            self._device.sensors[Senso4sSensor.MASS_KG] = None
        self._latest_reading = None

        return True

    async def _get_client(self, ble_device: BLEDevice) -> BleakClient:
        """Get the Bleak client knowing the BLEDevice."""
        try:
            return await bleak_retry_connector.establish_connection(
                client_class=BleakClient,
                device=ble_device,
                name=ble_device.address,
            )
        except Exception as e:
            self.logger.error(
                "Error when connecting to Senso4s BLE device, address: %s\n%s",
                ble_device.address,
                str(e),
            )

    async def update_device(
        self,
        ble_device: BLEDevice,
        service_info: BluetoothServiceInfoBleak,
    ) -> Senso4sDevice:
        """Connect to the device through BLE and retrieves relevant device data."""
        self.logger.debug("update_device()")
        self._device = Senso4sDevice()

        self.logger.debug(ble_device)
        self.logger.debug(self._device)

        self.logger.debug("Service info")
        self.logger.debug(service_info)
        if service_info.name is not None:
            self._device.name = service_info.name

        self._device.identifier = ble_device.address.replace(":", "").lower()
        self._device.address = ble_device.address

        adv_data = service_info.manufacturer_data[SENSO4S_MANUFACTURER]
        self.logger.debug("Adv data: %s", binascii.hexlify(adv_data))
        # 854a6b512e00fc8f4704b77d
        self._device.sensors[Senso4sSensor.RSSI] = service_info.rssi

        if len(adv_data) < 12:
            error_msg = "BLE advertising data too short: " + ble_device.address
            self.logger.error(error_msg)
            self._device.sensors[Senso4sSensor.WARNINGS] = error_msg
            return self._device

        # 2. Read battery level from advertising data
        battery_percentage = adv_data[4]
        self._device.sensors[Senso4sSensor.BATTERY] = battery_percentage

        # 3a. Check status
        self._device.sensors[Senso4sSensor.STATUS] = Senso4sSensor.STATUS_OK
        if adv_data[1] == 0xFE:
            self._device.sensors[Senso4sSensor.STATUS] = (
                Senso4sSensor.STATUS_BATTERY_EMPTY
            )
        if adv_data[1] == 0xFC:
            self._device.sensors[Senso4sSensor.STATUS] = (
                Senso4sSensor.STATUS_ERROR_STARTING
            )
        if adv_data[1] == 0xFF:
            self._device.sensors[Senso4sSensor.STATUS] = (
                Senso4sSensor.STATUS_NOT_CONFIGURED
            )

        # 3b. Check warnings
        if adv_data[0] & 0b11110000 == 0b10000000:
            self.logger.debug("Model BASIC")
            self._device.model = Senso4sSensor.MODEL_BASIC
            self._device.sensors[Senso4sSensor.WARNINGS] = Senso4sSensor.WARNING_NONE

        elif adv_data[0] & 0b10001111 == 0b00000011:
            self.logger.debug("Model PLUS")
            self._device.model = Senso4sSensor.MODEL_PLUS

            warnings = []

            movement = adv_data[0] & 0b01000000
            if movement:
                warnings.append(Senso4sSensor.WARNING_MOVEMENT)

            inclination = adv_data[0] & 0b00100000
            if inclination:
                warnings.append(Senso4sSensor.WARNING_INCLINATION)

            temperature_status = adv_data[0] & 0b00010000
            if temperature_status:
                warnings.append(Senso4sSensor.WARNING_TEMPERATURE)

            if len(warnings) != 0:
                self._device.sensors[Senso4sSensor.WARNINGS] = ",".join(warnings)
            else:
                self._device.sensors[Senso4sSensor.WARNINGS] = (
                    Senso4sSensor.WARNING_NONE
                )

        else:
            self.logger.error("Device not supported")
            return self._device

        # 3c. If statuses are not OK, stop reading further
        if self._device.sensors[Senso4sSensor.STATUS] != Senso4sSensor.STATUS_OK:
            self.logger.debug("Status not OK")
            self.logger.debug(self._device.sensors[Senso4sSensor.STATUS])
            # return self._device

        if (
            Senso4sSensor.WARNINGS in self._device.sensors
            and self._device.sensors[Senso4sSensor.WARNINGS]
            != Senso4sSensor.WARNING_NONE
        ):
            self.logger.debug("Warnings are present")
            self.logger.debug(self._device.sensors[Senso4sSensor.WARNINGS])
            # return self._device

        # 4. Read Mass and Prediction from advertising data
        mass_percentage = adv_data[1]
        if mass_percentage == 0xFF:
            self.logger.debug("Mass percentage is 0xFF")
            self._device.sensors[Senso4sSensor.MASS_PERCENT] = None
        else:
            self._device.sensors[Senso4sSensor.MASS_PERCENT] = mass_percentage

        if adv_data[2] == 0xFF and adv_data[3] == 0xFF:
            self.logger.debug("Prediction is 0xFFFF")
            self._device.sensors[Senso4sSensor.PREDICTION] = None
        else:
            prediction_minutes = ((adv_data[3] << 8) + adv_data[2]) * 15
            self._device.sensors[Senso4sSensor.PREDICTION] = prediction_minutes

        # 5. Establish Bluetooth connection with Senso4s PLUS/BASIC device
        try:
            # _get_client creates a connection with the device
            self.logger.debug("Connecting to device")
            self._client = await self._get_client(ble_device)
            if self._client is None:
                self.logger.debug("self._client is None")
                return self._device

            self.logger.debug("Connected. Reading characteristics")
            # Read any data from relevant characteristics (e.g. Empty gas cylinder weight, Total gas
            # capacity, History, Setup datetime)
            tasks = [
                self._read_mass(),
                self._read_parameters(),
                self._read_history(),
                self._read_setup_time(),
            ]
            await asyncio.gather(*tasks)

        except BleakError as error:
            self.logger.error(
                "Error when getting data from Senso4s BLE device, address: %s\n%s",
                ble_device.address,
                str(error),
            )
            self._device.error = str(error)
        except Exception as error:
            self.logger.error(
                "Other error when getting data from Senso4s BLE device, address: %s\n%s",
                ble_device.address,
                str(error),
            )
            self._device.error = str(error)
        finally:
            self.logger.debug("Disconnecting client")
            await self._client.disconnect()

        self.logger.debug("returning device sensors")
        return self._device
