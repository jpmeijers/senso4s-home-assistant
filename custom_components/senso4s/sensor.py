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

SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key=Senso4sSensor.PREDICTION,
        name="Predicted time left",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_unit_of_measurement=UnitOfTime.DAYS,
        # native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key=Senso4sSensor.MASS_KG,
        name="Remaining gas",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-cylinder",
    ),
    SensorEntityDescription(
        key=Senso4sSensor.MASS_PERCENT,
        name="Remaining gas %",
        # device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-cylinder",
    ),
    SensorEntityDescription(
        key=Senso4sSensor.BATTERY,
        name="Battery level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=Senso4sSensor.RSSI,
        name="RSSI",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        # entity_registry_enabled_default=False,
        icon="mdi:signal-variant",
    ),
    SensorEntityDescription(
        key=Senso4sSensor.WARNINGS,
        name="Warnings",
        # device_class=SensorDeviceClass.ENUM,
        # options=[
        #     Senso4sSensor.WARNING_NONE,
        #     Senso4sSensor.WARNING_MOVEMENT,
        #     Senso4sSensor.WARNING_INCLINATION,
        #     Senso4sSensor.WARNING_TEMPERATURE,
        # ],
        # state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:alert-circle-outline",
    ),
    SensorEntityDescription(
        key=Senso4sSensor.STATUS,
        name="Status",
        device_class=SensorDeviceClass.ENUM,
        options=[
            Senso4sSensor.STATUS_OK,
            Senso4sSensor.STATUS_BATTERY_EMPTY,
            Senso4sSensor.STATUS_ERROR_STARTING,
            Senso4sSensor.STATUS_NOT_CONFIGURED,
        ],
        # state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:check-circle-outline",
    ),
    SensorEntityDescription(
        key=Senso4sSensor.CYLINDER_CAPACITY,
        name="Cylinder Capacity",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:gas-cylinder",
    ),
    SensorEntityDescription(
        key=Senso4sSensor.CYLINDER_WEIGHT,
        name="Cylinder Weight",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:gas-cylinder",
    ),
    SensorEntityDescription(
        key=Senso4sSensor.SETUP_TIME,
        name="Setup Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        # native_unit_of_measurement=UnitOfTime.SECONDS,
        # state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-clock",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    _LOGGER.debug("async_setup_entry()")

    """Set up the Senso4s BLE sensors."""
    coordinator: DataUpdateCoordinator[Senso4sDevice] = hass.data[DOMAIN][
        entry.entry_id
    ]

    entities = []
    _LOGGER.debug("Got sensors: %s", coordinator.data)
    """ Add sensors entities to the coordinator. """
    for sensor_type in coordinator.data.sensors:
        _LOGGER.debug(f"Adding entity {sensor_type}")

        description = None
        for i in SENSOR_DESCRIPTIONS:
            if i.key == sensor_type:
                description = i

        if description is None:
            _LOGGER.error(
                "%s not found in descriptions, not adding to entities", sensor_type
            )
            continue

        entity = Senso4sSensorEntity(
            coordinator,
            coordinator.data,
            description,
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
        _LOGGER.debug(f"__init__({entity_description.key})")

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
        _LOGGER.debug(
            f"available({self.entity_description.key}) => {self.entity_description.key in self.coordinator.data.sensors}"
        )
        return super().available and (
            self.entity_description.key in self.coordinator.data.sensors
        )

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        _LOGGER.debug(
            f"native_value({self.entity_description.key}) => {self.coordinator.data.sensors[self.entity_description.key]}"
        )
        return self.coordinator.data.sensors[self.entity_description.key]
