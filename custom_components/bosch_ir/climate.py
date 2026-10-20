"""Climate entity for a Bosch Climate 3200i driven by a ZHA Zosung IR blaster.

IR codes are generated on the fly by coolix.encode(), so every mode,
temperature (17-30 °C) and fan percentage is available without learning.
The state is assumed (IR is one-way) and restored across restarts.
Set up from the UI: Settings -> Devices & services -> Add integration.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_NAME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_ENDPOINT,
    CONF_FAN_SPEEDS,
    CONF_HUMIDITY_SENSOR,
    CONF_IEEE,
    CONF_TEMP_SENSOR,
    DEFAULT_ENDPOINT,
    DEFAULT_FAN_SPEEDS,
    DOMAIN,
)
from .coolix import TEMP_CODES, encode

_LOGGER = logging.getLogger(__name__)

IR_CONTROL_CLUSTER = 0xE004  # Zosung IR Control
IR_SEND_COMMAND = 2
SEND_GAP_SECONDS = 1.5

# Home Assistant mode -> Coolix mode. Midea's "auto" picks heat or cool
# itself, which is HA's HEAT_COOL.
HVAC_TO_COOLIX = {
    HVACMode.COOL: "cool",
    HVACMode.HEAT: "heat",
    HVACMode.DRY: "dry",
    HVACMode.FAN_ONLY: "fan_only",
    HVACMode.HEAT_COOL: "auto",
}
FAN_AUTO = "auto"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the climate entity for a config entry."""
    async_add_entities([BoschIRClimate(hass, entry)])


class BoschIRClimate(ClimateEntity, RestoreEntity):
    """Bosch Climate 3200i over IR (assumed state)."""

    _attr_should_poll = False
    _attr_assumed_state = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_min_temp = min(TEMP_CODES)
    _attr_max_temp = max(TEMP_CODES)
    _attr_hvac_modes = [HVACMode.OFF, *HVAC_TO_COOLIX]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False
    _attr_has_entity_name = True
    _attr_name = None  # the entity takes the device's name

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        config: dict[str, Any] = {**entry.data, **entry.options}
        self._ieee = config[CONF_IEEE]
        self._endpoint = config.get(CONF_ENDPOINT, DEFAULT_ENDPOINT)
        self._temp_sensor = config.get(CONF_TEMP_SENSOR)
        self._humidity_sensor = config.get(CONF_HUMIDITY_SENSOR)
        speeds = config.get(CONF_FAN_SPEEDS) or DEFAULT_FAN_SPEEDS
        self._attr_fan_modes = [FAN_AUTO, *(f"{p}%" for p in speeds)]
        self._attr_unique_id = f"{self._ieee}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._ieee)},
            name=entry.data.get(CONF_NAME) or entry.title,
            manufacturer="Bosch",
            model="Climate 3200i (IR)",
            via_device=("zha", self._ieee),
        )

        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature = 21
        self._attr_fan_mode = FAN_AUTO
        self._last_on_mode = HVACMode.HEAT
        self._send_lock = asyncio.Lock()

    # ----------------------------------------------------------------- setup

    async def async_added_to_hass(self) -> None:
        """Restore the assumed state and follow the room sensors."""
        await super().async_added_to_hass()

        if (last := await self.async_get_last_state()) is not None:
            if last.state in self._attr_hvac_modes:
                self._attr_hvac_mode = HVACMode(last.state)
            attrs = last.attributes
            if (temp := attrs.get(ATTR_TEMPERATURE)) is not None:
                self._attr_target_temperature = int(float(temp))
            if attrs.get("fan_mode") in self._attr_fan_modes:
                self._attr_fan_mode = attrs["fan_mode"]
            # A fan speed removed in Configure falls back to auto.
            if attrs.get("last_on_mode") in HVAC_TO_COOLIX:
                self._last_on_mode = HVACMode(attrs["last_on_mode"])

        sensors = [s for s in (self._temp_sensor, self._humidity_sensor) if s]
        if sensors:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, sensors, self._async_sensor_changed
                )
            )
        self._update_sensors()

    @callback
    def _async_sensor_changed(self, event: Event) -> None:
        self._update_sensors()
        self.async_write_ha_state()

    @callback
    def _update_sensors(self) -> None:
        self._attr_current_temperature = self._read_sensor(self._temp_sensor)
        self._attr_current_humidity = self._read_sensor(self._humidity_sensor)

    def _read_sensor(self, entity_id: str | None) -> float | None:
        if not entity_id or not (state := self.hass.states.get(entity_id)):
            return None
        if state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict:
        return {"last_on_mode": self._last_on_mode}

    # -------------------------------------------------------------- controls

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode != HVACMode.OFF:
            self._last_on_mode = hvac_mode
        self._attr_hvac_mode = hvac_mode
        await self._async_send_state()

    async def async_set_temperature(self, **kwargs) -> None:
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self._attr_target_temperature = int(
                max(self._attr_min_temp, min(self._attr_max_temp, round(float(temp))))
            )
        if (mode := kwargs.get("hvac_mode")) is not None:
            await self.async_set_hvac_mode(mode)
            return
        if self._attr_hvac_mode != HVACMode.OFF:
            await self._async_send_state()
        else:
            self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._attr_fan_mode = fan_mode
        if self._attr_hvac_mode != HVACMode.OFF:
            await self._async_send_state()
        else:
            self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(self._last_on_mode)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    # ------------------------------------------------------------------ IR

    def _fan_setting(self) -> str | int:
        if self._attr_fan_mode not in self._attr_fan_modes or self._attr_fan_mode == FAN_AUTO:
            return FAN_AUTO
        return int(self._attr_fan_mode.rstrip("%"))

    async def _async_send_state(self) -> None:
        if self._attr_hvac_mode == HVACMode.OFF:
            code = encode("off")
        else:
            code = encode(
                HVAC_TO_COOLIX[self._attr_hvac_mode],
                self._attr_target_temperature,
                self._fan_setting(),
            )
        # One send at a time: the blaster's firmware can only track the most
        # recent outgoing message.
        async with self._send_lock:
            _LOGGER.debug(
                "Sending %s %s %s", self._attr_hvac_mode,
                self._attr_target_temperature, self._attr_fan_mode,
            )
            await self.hass.services.async_call(
                "zha",
                "issue_zigbee_cluster_command",
                {
                    "ieee": self._ieee,
                    "endpoint_id": self._endpoint,
                    "cluster_id": IR_CONTROL_CLUSTER,
                    "cluster_type": "in",
                    "command": IR_SEND_COMMAND,
                    "command_type": "server",
                    "params": {"code": code},
                },
                blocking=True,
            )
            # The code is transferred to the blaster in chunks after the call
            # returns; give it time before the next send.
            await asyncio.sleep(SEND_GAP_SECONDS)
        self.async_write_ha_state()
