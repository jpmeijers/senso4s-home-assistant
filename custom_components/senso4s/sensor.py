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
from .senso4s_ble import Senso4sDeviceData, Senso4sDataFields

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key=Senso4sDataFields.PREDICTION,
        name="Predicted time left",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_unit_of_measurement=UnitOfTime.DAYS,  # To render as days on UI
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key=Senso4sDataFields.MASS_KG,
        name="Remaining gas",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:propane-tank",
    ),
    SensorEntityDescription(
        key=Senso4sDataFields.MASS_PERCENT,
        name="Remaining gas %",
        # device_class=SensorDeviceClass.,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:propane-tank",
    ),
    SensorEntityDescription(
        key=Senso4sDataFields.BATTERY,
        name="Battery level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Default icon is good
    ),
    SensorEntityDescription(
        key=Senso4sDataFields.RSSI,
        name="RSSI",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        # entity_registry_visible_default=False,  # Hide from UI by default
        # icon="mdi:signal-variant",
    ),
    SensorEntityDescription(
        key=Senso4sDataFields.WARNING_MOVEMENT,
        name="Movement warning",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:alert-circle-outline",
    ),
    SensorEntityDescription(
        key=Senso4sDataFields.WARNING_INCLINATION,
        name="Inclination warning",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:alert-circle-outline",
    ),
    SensorEntityDescription(
        key=Senso4sDataFields.WARNING_TEMPERATURE,
        name="Temperature warning",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:alert-circle-outline",
    ),
    SensorEntityDescription(
        key=Senso4sDataFields.STATUS,
        name="Status",
        device_class=SensorDeviceClass.ENUM,
        options=[
            Senso4sDataFields.STATUS_OK,
            Senso4sDataFields.STATUS_BATTERY_EMPTY,
            Senso4sDataFields.STATUS_ERROR_STARTING,
            Senso4sDataFields.STATUS_NOT_CONFIGURED,
        ],
        # state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:check-circle-outline",
    ),
    SensorEntityDescription(
        key=Senso4sDataFields.CYLINDER_CAPACITY,
        name="Cylinder Capacity",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:propane-tank",
    ),
    SensorEntityDescription(
        key=Senso4sDataFields.CYLINDER_WEIGHT,
        name="Cylinder Weight",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:propane-tank-outline",
    ),
    SensorEntityDescription(
        key=Senso4sDataFields.SETUP_TIME,
        name="Setup Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        # state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key=Senso4sDataFields.LAST_MEASUREMENT,
        name="Last Measurement",
        device_class=SensorDeviceClass.TIMESTAMP,
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
    """Set up the Senso4s BLE sensors."""

    _LOGGER.debug("async_setup_entry()")

    coordinator: DataUpdateCoordinator[Senso4sDeviceData] = hass.data[DOMAIN][
        entry.entry_id
    ]

    entities = []
    _LOGGER.debug("Got sensors: %s", coordinator.data)

    # Add entities for sensors received by the coordinator
    for sensor_type in coordinator.data.sensors:
        # Find description for this sensor type (data key)
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
        _LOGGER.debug("Adding entity for %s", sensor_type)
        entities.append(entity)

    async_add_entities(entities)


class Senso4sSensorEntity(
    CoordinatorEntity[DataUpdateCoordinator[Senso4sDeviceData]], SensorEntity
):
    """Senso4s BLE sensors for the device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[Senso4sDeviceData],
        senso4s_device: Senso4sDeviceData,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Populate the Senso4s entity with relevant device data."""
        _LOGGER.debug("__init__(%s)", entity_description.key)

        super().__init__(coordinator)
        self.entity_description = entity_description

        self.entity_id = (
            f"sensor.{senso4s_device.address.replace("_","")}_{entity_description.key}"
        )
        self._attr_unique_id = (
            f"{senso4s_device.address.replace("_","")}_{entity_description.key}"
        )

        friendly_name = senso4s_device.friendly_name()
        self._attr_device_info = DeviceInfo(
            connections={
                (
                    CONNECTION_BLUETOOTH,
                    senso4s_device.address,
                )
            },
            name=friendly_name,
            manufacturer=senso4s_device.manufacturer,
            hw_version=senso4s_device.hw_version,
            sw_version=senso4s_device.sw_version,
            model=senso4s_device.model,
        )

    @property
    def available(self) -> bool:
        """Check if device and sensor is available in data."""
        _LOGGER.debug(
            "available(%s) => %s",
            self.entity_description.key,
            self.entity_description.key in self.coordinator.data.sensors,
        )
        return super().available and (
            self.entity_description.key in self.coordinator.data.sensors
        )

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        _LOGGER.debug(
            "native_value(%s) => %s",
            self.entity_description.key,
            self.coordinator.data.sensors[self.entity_description.key],
        )
        return self.coordinator.data.sensors[self.entity_description.key]
