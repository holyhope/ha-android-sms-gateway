"""Binary sensor platform for Android SMS Gateway."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import aiohttp
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import AndroidSmsGatewayClient, AndroidSmsGatewayError
from .const import (
    DOMAIN,
    PING_DEFAULT_STALE_AFTER,
    PING_MIN_STALE_AFTER,
    PING_STALE_MULTIPLIER,
    SIGNAL_PING_UPDATE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the connectivity binary sensor from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [AndroidSmsGatewayOnlineSensor(entry, data["ping"], data["client"])]
    )


class AndroidSmsGatewayOnlineSensor(BinarySensorEntity):
    """Whether the device has pinged recently enough to be considered online.

    Driven by the system:ping webhook, but re-evaluated on a timer too — a
    webhook alone can only ever turn this on, never off once pings stop. The
    staleness threshold adapts to the observed gap between real pings
    (PING_STALE_MULTIPLIER x the last observed interval) rather than trusting
    the device's configured ping.interval_seconds, which has been observed in
    practice not to actually govern the real cadence.

    On the on->off transition, probes the device's /settings endpoint once as
    an independent reachability check: if it responds, the device is online
    but failing to deliver webhooks (a background-execution/battery-
    optimization problem on the device, not a connectivity one); if it
    doesn't, the device is genuinely unreachable. Either way the resulting
    warning is logged once per outage, not repeated every minute.
    """

    _attr_has_entity_name = True
    _attr_name = "Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_should_poll = False

    def __init__(
        self, entry: ConfigEntry, ping_data: dict, client: AndroidSmsGatewayClient
    ) -> None:
        self._ping_data = ping_data
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_online"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Android SMS Gateway",
        )
        self._was_online = False
        self._warned_this_outage = False

    def _stale_after(self) -> timedelta:
        observed: timedelta | None = self._ping_data.get("observed_interval")
        if observed is None:
            return PING_DEFAULT_STALE_AFTER
        return max(PING_MIN_STALE_AFTER, observed * PING_STALE_MULTIPLIER)

    @property
    def is_on(self) -> bool:
        last_ping: datetime | None = self._ping_data.get("last_ping")
        if last_ping is None:
            return False
        return dt_util.utcnow() - last_ping < self._stale_after()

    async def async_added_to_hass(self) -> None:
        self._was_online = self.is_on
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_PING_UPDATE, self._handle_ping)
        )
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_check_stale, timedelta(minutes=1)
            )
        )

    def _handle_ping(self) -> None:
        self._was_online = True
        self._warned_this_outage = False
        self.async_write_ha_state()

    async def _async_check_stale(self, now: datetime) -> None:
        currently_online = self.is_on
        if self._was_online and not currently_online and not self._warned_this_outage:
            self._warned_this_outage = True
            await self._async_warn_offline()
        self._was_online = currently_online
        self.async_write_ha_state()

    async def _async_warn_offline(self) -> None:
        stale_minutes = round(self._stale_after().total_seconds() / 60, 1)
        try:
            settings = await self._client.async_get_settings()
        except (AndroidSmsGatewayError, aiohttp.ClientError, TimeoutError):
            _LOGGER.warning(
                "Android SMS Gateway offline: no ping received in over %s minutes, "
                "and the device's API is unreachable (likely off Wi-Fi, or the app "
                "isn't running).",
                stale_minutes,
            )
            return

        configured_interval = settings.get("ping", {}).get("interval_seconds")
        _LOGGER.warning(
            "Android SMS Gateway offline: no ping received in over %s minutes, but "
            "the device's API is still reachable (configured ping.interval_seconds="
            "%s). This points to the device failing to deliver the webhook rather "
            "than being offline — check battery optimization / background activity "
            "restrictions for the app.",
            stale_minutes,
            configured_interval,
        )
