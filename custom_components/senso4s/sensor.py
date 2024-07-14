"""Support for Senso4s sensors."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfMass,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .senso4s_ble import Senso4sDevice, Senso4sSensor

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS: dict[str, SensorEntityDescription] = {
    "mass": SensorEntityDescription(
        key="mass",
        name="Remaining gas",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-cylinder",
    ),
    "mass_percentage": SensorEntityDescription(
        key="mass_percentage",
        name="Remaining gas %",
        # device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-cylinder",
    ),
    "prediction": SensorEntityDescription(
        key="prediction",
        name="Predicted time left",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_unit_of_measurement=UnitOfTime.DAYS,
        # native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-clock",
    ),
    "battery": SensorEntityDescription(
        key="battery",
        name="Battery level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "cylinder_capacity": SensorEntityDescription(
        key="cylinder_capacity",
        name="Cylinder Capacity",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:gas-cylinder",
    ),
    "cylinder_weight": SensorEntityDescription(
        key="cylinder_weight",
        name="Cylinder Weight",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:gas-cylinder",
    ),
    "setup_time": SensorEntityDescription(
        key="setup_time",
        name="Setup Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        # native_unit_of_measurement=UnitOfTime.SECONDS,
        # state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-clock",
    ),
    "status1": SensorEntityDescription(
        key="status1",
        name="Status 1",
        # device_class=SensorDeviceClass.
        # state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:comment-alert-outline",
    ),
    "status2": SensorEntityDescription(
        key="status2",
        name="Status 2",
        # device_class=SensorDeviceClass.
        # state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:comment-alert-outline",
    ),
    "rssi": SensorEntityDescription(
        key="rssi",
        name="RSSI",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        # entity_registry_enabled_default=False,
        icon="mdi:signal-variant",
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Senso4s BLE sensors."""
    coordinator: DataUpdateCoordinator[Senso4sDevice] = hass.data[DOMAIN][
        entry.entry_id
    ]

    entities = []
    _LOGGER.debug("Got sensors: %s", coordinator.data)
    """ Add sensors entities to the coordinator. """
    for sensor_type in coordinator.data.sensors:
        entity = Senso4sSensorEntity(
            coordinator, coordinator.data, SENSOR_DESCRIPTIONS[sensor_type]
        )
        entities.append(entity)

    async_add_entities(entities)


class Senso4sSensorEntity(
    CoordinatorEntity[DataUpdateCoordinator[Senso4sDevice]], SensorEntity
):
    """Senso4s BLE sensors for the device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[Senso4sDevice],
        senso4s_device: Senso4sDevice,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Populate the Senso4s entity with relevant device data."""
        super().__init__(coordinator)
        self.entity_description = entity_description

        name = senso4s_device.friendly_name()

        self.entity_id = (
            f"sensor.{senso4s_device.address.replace("_","")}_{entity_description.key}"
        )
        self._attr_unique_id = (
            f"{senso4s_device.address.replace("_","")}_{entity_description.key}"
        )

        self._attr_device_info = DeviceInfo(
            connections={
                (
                    CONNECTION_BLUETOOTH,
                    senso4s_device.address,
                )
            },
            name=name,
            manufacturer=senso4s_device.manufacturer,
            hw_version=senso4s_device.hw_version,
            sw_version=senso4s_device.sw_version,
            model=senso4s_device.model,
        )

    @property
    def available(self) -> bool:
        """Check if device and sensor is available in data."""
        return super().available and (
            self.entity_description.key in self.coordinator.data.sensors
        )

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        return self.coordinator.data.sensors[self.entity_description.key]
