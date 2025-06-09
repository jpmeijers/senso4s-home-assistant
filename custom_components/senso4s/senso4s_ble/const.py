class Senso4sBleConstants():
    # Manufacturer ID for checking if it's a Senso4s, equivalent to decimal 2508.
    SENSO4S_MANUFACTURER = 0x09CC  # 2508 Senso4s d.o.o.
    NORDIC_MANUFACTURER = 0x0059  # 89 Nordic Semiconductor ASA

    # Senso4s service and characterisitcs
    BASIC_SERVICE = "00007081-a20b-4d4d-a4de-7f071dbbc1d8"
    MASS_CHARACTERISTIC_UUID_READ = "00007082-a20b-4d4d-a4de-7f071dbbc1d8"
    PARAMS_CHARACTERISTIC_UUID_READWRITE = "00007083-a20b-4d4d-a4de-7f071dbbc1d8"
    HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE = "00007085-a20b-4d4d-a4de-7f071dbbc1d8"
    SETUPTIME_CHARACTERISTIC_UUID_READ = "00007087-a20b-4d4d-a4de-7f071dbbc1d8"


class Senso4sDataFields():
    """Constants used for sensors."""

    PREDICTION = "prediction"
    MASS_KG = "mass"
    MASS_PERCENT = "mass_percentage"

    BATTERY = "battery"
    RSSI = "rssi"
    STATUS = "status"

    CYLINDER_CAPACITY = "cylinder_capacity"
    CYLINDER_WEIGHT = "cylinder_weight"
    SETUP_TIME = "setup_time"
    LAST_MEASUREMENT = "last_measurement"

    STATUS_OK = "ok"
    STATUS_BATTERY_EMPTY = "battery empty"
    STATUS_ERROR_STARTING = "error starting measurement"
    STATUS_NOT_CONFIGURED = "not configured"
    STATUS_UNKNOWN = "unknown"

    # PLUS model only
    WARNING_MOVEMENT = "warning_movement"
    WARNING_INCLINATION = "warning_inclination"
    WARNING_TEMPERATURE = "warning_temperature"


class Senso4sInfoFields():
    """Constants used for device information."""

    MODEL_BASIC = "Basic"
    MODEL_PLUS = "Plus"

    DEVICE_NAME = "name"
    APPEARANCE = "appearance"
    MANUFACTURER_NAME = "manufacturer"
    MODEL_NUMBER = "model"
    HARDWARE_REV = "hw_version"
    FIRMWARE_REV = "sw_version"

    INTENDED_USE = ["Unknown", "BBQ", "Camping", "Caravanning", "Heating", "Household"]
