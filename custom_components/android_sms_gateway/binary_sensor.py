"""Binary sensor platform for Android SMS Gateway."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN, PING_STALE_AFTER, SIGNAL_PING_UPDATE


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the connectivity binary sensor from a config entry."""
    ping_data = hass.data[DOMAIN][entry.entry_id]["ping"]
    async_add_entities([AndroidSmsGatewayOnlineSensor(entry, ping_data)])


class AndroidSmsGatewayOnlineSensor(BinarySensorEntity):
    """Whether the device has pinged recently enough to be considered online.

    Driven by the system:ping webhook, but re-evaluated on a timer too —
    a webhook alone can only ever turn this on, never off once pings stop.
    """

    _attr_has_entity_name = True
    _attr_name = "Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, ping_data: dict) -> None:
        self._ping_data = ping_data
        self._attr_unique_id = f"{entry.entry_id}_online"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Android SMS Gateway",
        )

    @property
    def is_on(self) -> bool:
        last_ping: datetime | None = self._ping_data.get("last_ping")
        if last_ping is None:
            return False
        return dt_util.utcnow() - last_ping < PING_STALE_AFTER

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_PING_UPDATE, self.async_write_ha_state
            )
        )
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_check_stale, timedelta(minutes=1)
            )
        )

    @callback
    def _async_check_stale(self, now: datetime) -> None:
        self.async_write_ha_state()
