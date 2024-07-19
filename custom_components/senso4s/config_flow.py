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

from .const import DOMAIN, MANUFACTURER_ID
from .senso4s_ble import Senso4sBluetoothDeviceData, Senso4sDevice

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class Discovery:
    """A discovered bluetooth device."""

    name: str
    discovery_info: BluetoothServiceInfo
    device: Senso4sDevice


def get_name(device: Senso4sDevice) -> str:
    """Generate name with model and identifier for device."""

    _LOGGER.debug("Setup Get Name: %s", device.address)
    return device.friendly_name()


class Senso4sDeviceUpdateError(Exception):
    """Custom error class for device updates."""


class Senso4sConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Senso4s."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        _LOGGER.debug("Init config flow")
        self._discovered_device: Discovery | None = None
        self._discovered_devices: dict[str, Discovery] = {}

    async def _get_device_data(
        self, discovery_info: BluetoothServiceInfo
    ) -> Senso4sDevice:
        _LOGGER.debug("_get_device_data: %s", discovery_info.address)
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, discovery_info.address
        )
        if ble_device is None:
            _LOGGER.debug("no ble_device in _get_device_data")
            raise Senso4sDeviceUpdateError("No ble_device")

        senso4s = Senso4sBluetoothDeviceData(_LOGGER)

        try:
            data = await senso4s.update_device(ble_device)
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
        return data

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfo
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug("async_step_bluetooth: %s", discovery_info.address)
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        try:
            device = await self._get_device_data(discovery_info)
        except Senso4sDeviceUpdateError:
            return self.async_abort(reason="cannot_connect")
        except Exception:  # pylint: disable=broad-except
            return self.async_abort(reason="unknown")

        # name = get_name(device)
        name = device.friendly_name()
        self.context["title_placeholders"] = {"name": name}
        self._discovered_device = Discovery(name, discovery_info, device)

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        _LOGGER.debug("async_step_bluetooth_confirm")
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
        _LOGGER.debug("async_step_user")
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            discovery = self._discovered_devices[address]

            adv_data = discovery.discovery_info.manufacturer_data[MANUFACTURER_ID]
            model = "Unknown"
            if adv_data[0] & 0b11110000 == 0b10000000:
                model = "Basic"
            if adv_data[0] & 0b10001111 == 0b00000011:
                model = "Plus"
            name = f"Senso4s {model} ({address})"
            self.context["title_placeholders"] = {
                "name": name,
            }

            self._discovered_device = discovery

            return self.async_create_entry(title=name, data={})

        current_addresses = self._async_current_ids()
        discovered_devices = async_discovered_service_info(self.hass)
        for discovery_info in discovered_devices:
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue
            if MANUFACTURER_ID not in discovery_info.manufacturer_data:
                continue
            # try:
            #     device = await self._get_device_data(discovery_info)
            # except Senso4sDeviceUpdateError:
            #     return self.async_abort(reason="cannot_connect")
            # except Exception:  # pylint: disable=broad-except
            #     return self.async_abort(reason="unknown")
            adv_data = discovery_info.manufacturer_data[MANUFACTURER_ID]
            model = "Unknown"
            if adv_data[0] & 0b11110000 == 0b10000000:
                model = "Basic"
            if adv_data[0] & 0b10001111 == 0b00000011:
                model = "Plus"
            name = f"Senso4s {model} ({address})"
            self._discovered_devices[address] = Discovery(name, discovery_info, None)

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

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
