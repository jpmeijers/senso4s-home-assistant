"""Config flow for Senso4s integration."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from bleak import BleakError
import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfo,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN
from .senso4s_ble import Senso4sBluetoothDevice, Senso4sDeviceData

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class Discovery:
    """A discovered bluetooth device."""

    name: str
    discovery_info: BluetoothServiceInfo
    device: Senso4sDeviceData


def get_name(device: Senso4sDeviceData) -> str:
    """Generate name with model and identifier for device."""

    _LOGGER.debug("get_name(%s)", device.address)
    return device.friendly_name()


class Senso4sDeviceUpdateError(Exception):
    """Custom error class for device updates."""


class Senso4sConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Senso4s."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        _LOGGER.debug("__init__()")
        self._discovered_device: Discovery | None = None
        self._discovered_devices: dict[str, Discovery] = {}

    async def _get_device_data(
        self, discovery_info: BluetoothServiceInfo
    ) -> Senso4sDeviceData:
        _LOGGER.debug("_get_device_data(%s)", discovery_info.address)
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, discovery_info.address
        )
        if ble_device is None:
            _LOGGER.debug("no ble_device in _get_device_data")
            raise Senso4sDeviceUpdateError("No ble_device")

        senso4s = Senso4sBluetoothDevice(_LOGGER)

        try:
            device_data = await senso4s.update_device_adv(ble_device, discovery_info)
        except BleakError as err:
            _LOGGER.error(
                "Error connecting to and getting data from %s: %s",
                discovery_info.address,
                err,
            )
            raise Senso4sDeviceUpdateError("Failed getting device data") from err
        except Exception as err:
            _LOGGER.error(
                "Unknown error occurred from %s: %s", discovery_info.address, err
            )
            raise err

        if device_data is None:
            _LOGGER.error("device update data is none")
            raise Senso4sDeviceUpdateError("Failed getting device data")
        return device_data

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfo
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug("async_step_bluetooth(%s)", discovery_info.address)
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        try:
            device = await self._get_device_data(discovery_info)
        except Senso4sDeviceUpdateError:
            return self.async_abort(reason="cannot_connect")
        except Exception:  # pylint: disable=broad-except  # noqa: BLE001
            return self.async_abort(reason="unknown")

        if device.error is not None:
            _LOGGER.debug(device.error)
            return self.async_abort(reason=device.error)

        name = device.friendly_name()
        self.context["title_placeholders"] = {"name": name}
        self._discovered_device = Discovery(name, discovery_info, device)

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        _LOGGER.debug(
            "async_step_bluetooth_confirm(%s)", self.context["title_placeholders"]
        )
        if user_input is not None:
            return self.async_create_entry(
                title=self.context["title_placeholders"]["name"], data={}
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders=self.context["title_placeholders"],
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device."""
        _LOGGER.debug("async_step_user(%s)", user_input)

        # After the user selected the device, this function will be called again with an argument
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            discovery_info = self._discovered_devices[
                address
            ]  # get from cached devices from previous call to this function
            if discovery_info is None:
                _LOGGER.error("address not found in discovered device cache")

            try:
                device = await self._get_device_data(discovery_info)
            except Senso4sDeviceUpdateError:
                return self.async_abort(reason="cannot_connect")
            except Exception:  # pylint: disable=broad-except  # noqa: BLE001
                return self.async_abort(reason="unknown")

            if device.error is not None:
                _LOGGER.debug(device.error)
                return self.async_abort(reason=device.error)

            name = device.friendly_name()
            self.context["title_placeholders"] = {
                "name": name,
            }

            self._discovered_device = discovery_info

            return self.async_create_entry(title=name, data={})

        # The first call to this function is without an argument
        current_addresses = self._async_current_ids()
        _LOGGER.debug("Current IDs: %s", current_addresses)

        discovered_devices = async_discovered_service_info(self.hass)
        _LOGGER.debug("Discovered devices: %s", discovered_devices)

        # Iterate discovered devices, ignoring existing ones, checking if they are compatible
        for discovery_info in discovered_devices:
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue

            try:
                device = await self._get_device_data(discovery_info)
            except Senso4sDeviceUpdateError:
                continue
            except Exception:  # pylint: disable=broad-except  # noqa: BLE001
                continue

            if device.error is not None:
                # Ignore as this is likely not a Senso4s device
                continue

            name = device.friendly_name()
            self._discovered_devices[address] = Discovery(name, discovery_info, None)

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        # Build a list of discovered compatible device addresses
        titles = {
            address: discovery.name
            for (address, discovery) in self._discovered_devices.items()
        }
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(titles),
                },
            ),
        )
