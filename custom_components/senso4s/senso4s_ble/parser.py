"""Parser for Senso4s Basic and Pro BLE advertisements."""

from __future__ import annotations

import asyncio
import binascii
import datetime
import logging
import struct

from bleak import BleakClient, BleakError, BLEDevice
import bleak_retry_connector
from habluetooth import BluetoothServiceInfoBleak
from sensor_state_data import SensorDeviceClass, Units
from sensor_state_data.enum import StrEnum

from .const import (
    CHARACTERISTIC_DEVICE_NAME,
    CHARACTERISTIC_FIRMWARE_REV,
    CHARACTERISTIC_HARDWARE_REV,
    CHARACTERISTIC_HUMIDITY,
    CHARACTERISTIC_MODEL_NUMBER,
    CHARACTERISTIC_TEMPERATURE,
    HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE,
    MASS_CHARACTERISTIC_UUID_READ,
    PARAMS_CHARACTERISTIC_UUID_READWRITE,
    SETUPTIME_CHARACTERISTIC_UUID_READ,
)
from .models import Senso4sDevice

_LOGGER = logging.getLogger(__name__)


class Senso4sSensor(StrEnum):
    """Environmental sensors."""

    TEMPERATURE_C = "temperature"
    HUMIDITY_PERCENT = "humidity"

    MASS_KG = "mass"
    MASS_PERCENT = "mass_percentage"
    PREDICTION = "prediction"
    BATTERY = "battery"
    CYLINDER_CAPACITY = "cylider_capacity"
    CYLINDER_WEIGHT = "cylinder_weight"
    SETUP_TIME = "setup_time"
    STATUS1 = "status1"
    STATUS2 = "status2"


class Senso4sDeviceInfo(StrEnum):
    """Device information."""

    DEVICE_NAME = "name"
    APPEARANCE = "appearance"
    MANUFACTURER_NAME = "manufacturer"
    MODEL_NUMBER = "model"
    HARDWARE_REV = "hw_version"
    FIRMWARE_REV = "sw_version"


""" Manufacturer ID for checking if it's a Senso4s, equivalent to decimal 71. """
SENSO4S_MANUFACTURER = 0x09CC

""" Characteristics for the Senso4s, how to format the data and what divider to apply. """
THUNDERBOARD_GATT_SENSOR_CHARS = [
    {
        "uuid": CHARACTERISTIC_TEMPERATURE,
        "sensor_key": Senso4sSensor.TEMPERATURE_C,
        "format": "<h",
        "divider": 100,
        "sensor_unit": Units.TEMP_CELSIUS,
        "sensor_class": SensorDeviceClass.TEMPERATURE,
        "sensor_name": "Temperature",
    },
    {
        "uuid": CHARACTERISTIC_HUMIDITY,
        "sensor_key": Senso4sSensor.HUMIDITY_PERCENT,
        "format": "<H",
        "divider": 100,
        "sensor_unit": Units.PERCENTAGE,
        "sensor_class": SensorDeviceClass.HUMIDITY,
        "sensor_name": "Humidity",
    },
]

THUNDERBOARD_GATT_DEVICE_CHARS = [
    {
        "uuid": CHARACTERISTIC_DEVICE_NAME,
        "sensor_key": Senso4sDeviceInfo.DEVICE_NAME,
    },
    {
        "uuid": CHARACTERISTIC_MODEL_NUMBER,
        "sensor_key": Senso4sDeviceInfo.MODEL_NUMBER,
    },
    {
        "uuid": CHARACTERISTIC_HARDWARE_REV,
        "sensor_key": Senso4sDeviceInfo.HARDWARE_REV,
    },
    {
        "uuid": CHARACTERISTIC_FIRMWARE_REV,
        "sensor_key": Senso4sDeviceInfo.FIRMWARE_REV,
    },
]

sensors_characteristics_uuid_str = [
    str(sensor_info["uuid"]) for sensor_info in THUNDERBOARD_GATT_SENSOR_CHARS
]


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
        self._device.sensors["status2"] = "OK"
        value = await self._client.read_gatt_char(MASS_CHARACTERISTIC_UUID_READ)
        if value[0] == 0xFE:
            status = "BATTERY_EMPTY"
            self.logger.error(status)
            self._device.sensors["status2"] = status
            return False
        if value[0] == 0xFC:
            status = "ERROR_STARTING_MEASURE"
            self.logger.error(status)
            self._device.sensors["status2"] = status
            return False
        if value[0] == 0xFF:
            status = "UNUSED"
            self.logger.error(status)
            self._device.sensors["status2"] = status
            return False

        mass_percentage = value[0]
        self._device.sensors["mass_percentage"] = mass_percentage
        return True

    async def _read_parameters(self):
        value = await self._client.read_gatt_char(PARAMS_CHARACTERISTIC_UUID_READWRITE)
        params = struct.unpack("<HHB", value)
        self._device.sensors["cylinder_weight"] = params[0] / 100
        self._device.sensors["cylinder_capacity"] = params[1] / 100

    async def _read_setup_time(self):
        value = await self._client.read_gatt_char(SETUPTIME_CHARACTERISTIC_UUID_READ)
        timeparts = struct.unpack("<HBBBBB", value)
        setup_time = datetime.datetime(
            year=timeparts[0],
            month=timeparts[1],
            day=timeparts[2],
            hour=timeparts[3],
            minute=timeparts[4],
        )
        setup_time = setup_time.replace(tzinfo=datetime.UTC)
        self._device.sensors["setup_time"] = setup_time

    async def _read_history(self):
        try:
            await self._client.start_notify(
                HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE,
                self.history_notification_handler,
            )
        except BleakError as err:
            self.logger.debug("Start notify exception: %s", err)
            return self._device

        await self._client.write_gatt_char(
            HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE, b"\x00\x00"
        )

        # Wait up to 5s for historical data notifications.
        await asyncio.sleep(5.0)

        await self._client.stop_notify(HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE)

        if self._latest_reading is not None:
            self._device.sensors["mass"] = float(self._latest_reading) / 100
        else:
            self._device.sensors["mass"] = None
        self._latest_reading = None

    async def _get_client(self, ble_device: BLEDevice) -> BleakClient:
        """Get the Bleak client knowing the BLEDevice."""
        try:
            client = await bleak_retry_connector.establish_connection(
                client_class=BleakClient,
                device=ble_device,
                name=ble_device.address,
            )
            return client
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
        self._client = await self._get_client(ble_device)
        if self._client is None:
            return None

        self.logger.debug(service_info)
        self.logger.debug(ble_device)
        self.logger.debug(self._device)

        # self._device.name = service_info.name
        self._device.identifier = ble_device.address.replace(":", "").lower()

        adv_data = service_info.manufacturer_data[SENSO4S_MANUFACTURER]
        self.logger.debug("Adv data: %s", binascii.hexlify(adv_data))
        # 854a6b512e00fc8f4704b77d
        self._device.sensors["rssi"] = service_info.rssi

        if len(adv_data) < 12:
            error_msg = "BLE advertising data too short: " + ble_device.address
            self.logger.error(error_msg)
            self._device.sensors["status"] = error_msg
            return self._device

        self._device.sensors["status1"] = "OK"
        if adv_data[0] & 0b11110000 == 0b10000000:
            self._device.model = "Basic"
        if adv_data[0] & 0b10001111 == 0b00000011:
            self._device.model = "Pro"
            movement = adv_data[0] & 0b01000000
            if movement:
                error_msg = ble_device.address + ": Can't measure due to movement"
                self.logger.error(error_msg)
                self._device.sensors["status1"] = error_msg
                return self._device

            inclination = adv_data[0] & 0b00100000
            if inclination:
                error_msg = ble_device.address + ": Can't measure due to inclination"
                self.logger.error(error_msg)
                self._device.sensors["status1"] = error_msg
                return self._device

            temperature_status = adv_data[0] & 0b00010000
            if temperature_status:
                error_msg = ble_device.address + ": Can't measure due to temperature"
                self.logger.error(error_msg)
                self._device.sensors["status1"] = error_msg
                return self._device

        self._device.sensors["status2"] = "OK"
        if adv_data[1] == 0xFE:
            status = "BATTERY_EMPTY"
            self._device.sensors["status2"] = status
            return self._device
        if adv_data[1] == 0xFC:
            status = "ERROR_STARTING_MEASURE"
            self._device.sensors["status2"] = status
            return self._device
        if adv_data[1] == 0xFF:
            status = "UNUSED"
            self._device.sensors["status2"] = status
            return self._device

        mass_percentage = adv_data[1]
        self._device.sensors["mass_percentage"] = mass_percentage

        prediction_minutes = ((adv_data[3] << 8) + adv_data[2]) * 15
        self._device.sensors["prediction"] = prediction_minutes
        battery_percentage = adv_data[4]
        self._device.sensors["battery"] = battery_percentage

        try:
            status = await self._read_mass()
            if status:
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
            await self._client.disconnect()

        return self._device
