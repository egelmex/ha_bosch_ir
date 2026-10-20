"""UI configuration for the Bosch IR integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.selector import (
    DeviceSelector,
    DeviceSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_DEVICE_ID,
    CONF_ENDPOINT,
    CONF_FAN_SPEEDS,
    CONF_HUMIDITY_SENSOR,
    CONF_IEEE,
    CONF_TEMP_SENSOR,
    DEFAULT_ENDPOINT,
    DEFAULT_FAN_SPEEDS,
    DEFAULT_NAME,
    DOMAIN,
    FAN_SPEED_CHOICES,
)


def zha_ieee(hass: HomeAssistant, device_id: str) -> str | None:
    """Return the IEEE address of a ZHA device registry entry."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    for domain, ident in device.identifiers:
        if domain == "zha":
            return str(ident)
    return None


def device_sensor(hass: HomeAssistant, device_id: str, device_class: str) -> str | None:
    """Find the blaster's own sensor of a device class, to pre-fill the form."""
    registry = er.async_get(hass)
    for entry in er.async_entries_for_device(registry, device_id):
        if entry.domain != "sensor" or entry.disabled:
            continue
        cls = entry.device_class or entry.original_device_class
        if cls == device_class:
            return entry.entity_id
    return None


def sensors_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Sensor and fan-speed fields, shared by setup and Configure."""

    def opt(key: str) -> vol.Optional:
        value = defaults.get(key)
        return vol.Optional(key, description={"suggested_value": value} if value else None)

    return vol.Schema(
        {
            opt(CONF_TEMP_SENSOR): EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
            opt(CONF_HUMIDITY_SENSOR): EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class="humidity")
            ),
            vol.Required(
                CONF_FAN_SPEEDS,
                default=[str(s) for s in defaults.get(CONF_FAN_SPEEDS, DEFAULT_FAN_SPEEDS)],
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=str(p), label=f"{p}%")
                        for p in FAN_SPEED_CHOICES
                    ],
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
        }
    )


def clean_sensors(user_input: dict[str, Any]) -> dict[str, Any] | None:
    """Normalise the sensors step; None if no fan speed was picked."""
    speeds = sorted({int(s) for s in user_input.get(CONF_FAN_SPEEDS, [])})
    if not speeds:
        return None
    return {
        CONF_TEMP_SENSOR: user_input.get(CONF_TEMP_SENSOR) or None,
        CONF_HUMIDITY_SENSOR: user_input.get(CONF_HUMIDITY_SENSOR) or None,
        CONF_FAN_SPEEDS: speeds,
    }


class BoschIRConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a Bosch AC controlled through a ZHA IR blaster."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: name the AC and pick the ZHA IR blaster."""
        errors: dict[str, str] = {}
        if user_input is not None:
            ieee = zha_ieee(self.hass, user_input[CONF_DEVICE_ID])
            if ieee is None:
                errors[CONF_DEVICE_ID] = "not_zha"
            else:
                await self.async_set_unique_id(ieee)
                self._abort_if_unique_id_configured()
                self._data = {
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_DEVICE_ID: user_input[CONF_DEVICE_ID],
                    CONF_IEEE: ieee,
                    CONF_ENDPOINT: DEFAULT_ENDPOINT,
                }
                return await self.async_step_sensors()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): TextSelector(),
                vol.Required(CONF_DEVICE_ID): DeviceSelector(
                    DeviceSelectorConfig(integration="zha")
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: room sensors and fan speeds."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if (options := clean_sensors(user_input)) is None:
                errors[CONF_FAN_SPEEDS] = "no_fan_speeds"
            else:
                return self.async_create_entry(
                    title=self._data[CONF_NAME], data=self._data, options=options
                )

        device_id = self._data[CONF_DEVICE_ID]
        defaults = {
            CONF_TEMP_SENSOR: device_sensor(self.hass, device_id, "temperature"),
            CONF_HUMIDITY_SENSOR: device_sensor(self.hass, device_id, "humidity"),
            CONF_FAN_SPEEDS: DEFAULT_FAN_SPEEDS,
        }
        return self.async_show_form(
            step_id="sensors", data_schema=sensors_schema(defaults), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BoschIROptionsFlow()


class BoschIROptionsFlow(OptionsFlow):
    """Change sensors and fan speeds after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if (options := clean_sensors(user_input)) is None:
                errors[CONF_FAN_SPEEDS] = "no_fan_speeds"
            else:
                return self.async_create_entry(data=options)
        return self.async_show_form(
            step_id="init",
            data_schema=sensors_schema(dict(self.config_entry.options)),
            errors=errors,
        )
