"""Sensor platform for Android SMS Gateway."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_PING_UPDATE


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the battery sensor from a config entry."""
    ping_data = hass.data[DOMAIN][entry.entry_id]["ping"]
    async_add_entities([AndroidSmsGatewayBatterySensor(entry, ping_data)])


class AndroidSmsGatewayBatterySensor(SensorEntity):
    """Battery level as last reported by the system:ping webhook."""

    _attr_has_entity_name = True
    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, ping_data: dict) -> None:
        self._ping_data = ping_data
        self._attr_unique_id = f"{entry.entry_id}_battery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Android SMS Gateway",
        )

    @property
    def native_value(self) -> int | None:
        return self._ping_data.get("battery")

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_PING_UPDATE, self.async_write_ha_state
            )
        )
