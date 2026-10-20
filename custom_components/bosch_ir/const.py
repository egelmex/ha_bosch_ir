"""Constants for the Bosch IR integration."""

DOMAIN = "bosch_ir"

CONF_DEVICE_ID = "device_id"        # ZHA device registry id of the blaster
CONF_IEEE = "ieee"
CONF_ENDPOINT = "endpoint_id"
CONF_TEMP_SENSOR = "temperature_sensor"
CONF_HUMIDITY_SENSOR = "humidity_sensor"
CONF_FAN_SPEEDS = "fan_speeds"

DEFAULT_NAME = "Bosch AC"
DEFAULT_ENDPOINT = 1
DEFAULT_FAN_SPEEDS = [20, 40, 60, 80, 100]
FAN_SPEED_CHOICES = list(range(10, 101, 10))
