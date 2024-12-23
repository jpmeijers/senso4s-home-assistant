"""The Senso4s integration."""

from __future__ import annotations

from datetime import timedelta
import logging
import time

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

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .senso4s_ble import Senso4sBluetoothDeviceData

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
    senso4s = Senso4sBluetoothDeviceData(_LOGGER)
    scan_interval = DEFAULT_SCAN_INTERVAL

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
            data = await senso4s.update_device(ble_device, service_info)
        except Exception as err:
            raise UpdateFailed(f"Unable to fetch data: {err}") from err

        return data

    _LOGGER.debug("Polling interval is set to: %s seconds", scan_interval)

    coordinator = hass.data.setdefault(DOMAIN, {})[entry.entry_id] = (
        DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_method=_async_update_method,
            update_interval=timedelta(seconds=scan_interval),
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
