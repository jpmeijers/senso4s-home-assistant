"""The Senso4s integration."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from bleak import BleakClient
from bleak_retry_connector import establish_connection

from homeassistant.components.bluetooth import (
    async_ble_device_from_address,
    async_last_service_info,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import UPDATE_INTERVAL_S, DOMAIN
from .senso4s_ble import Senso4sBluetoothDevice

PLATFORMS: list[Platform] = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)

last_event_time = time.time()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Senso4s BLE device from a config entry."""
    _LOGGER.debug("async_setup_entry()")

    hass.data.setdefault(DOMAIN, {})
    address = entry.unique_id
    assert address is not None

    _LOGGER.debug("Senso4s device address %s", address)
    senso4s_device = Senso4sBluetoothDevice(_LOGGER)

    async def _async_update_method():
        """Get data from Senso4s BLE."""
        _LOGGER.debug("_async_update_method()")

        service_info = async_last_service_info(hass, address, connectable=True)
        ble_device = async_ble_device_from_address(hass, address)
        if not ble_device:
            raise ConfigEntryNotReady(
                f"Could not find Senso4s device with address {address}"
            )
        _LOGGER.debug("Senso4s BLE device is %s", ble_device)

        try:
            # TODO do fast adv updates and slow full updates
            data = await senso4s_device.update_device_full(ble_device, service_info)
        except Exception as err:
            raise UpdateFailed(f"Unable to fetch data: {err}") from err

        if data is None:
            _LOGGER.debug("full update returned None")
            raise UpdateFailed(
                f"Updated returned None {address}"
            )

        if data.error is not None:
            _LOGGER.debug("Updated returned error: {data.error}")
            raise ConfigEntryNotReady(
                f"Updated returned error: {data.error}"
            )

        return data

    _LOGGER.debug("Polling interval is set to: %s seconds", UPDATE_INTERVAL_S)

    coordinator = hass.data.setdefault(DOMAIN, {})[entry.entry_id] = (
        DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_method=_async_update_method,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_S),
            always_update=False,
        )
    )

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("async_unload_entry()")

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    _LOGGER.debug("async_remove_entry()")

    address = entry.unique_id
    assert address is not None
    ble_device = async_ble_device_from_address(hass, address)
    client = await establish_connection(BleakClient, ble_device, ble_device.address)
    await client.disconnect()
