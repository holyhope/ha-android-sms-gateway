"""The Android SMS Gateway integration."""

from __future__ import annotations

import logging
import re
import secrets
from typing import Any

import aiohttp
import voluptuous as vol
from aiohttp import web

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_PASSWORD,
    CONF_TYPE,
    CONF_URL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.util import dt as dt_util

from .api import AndroidSmsGatewayClient, AndroidSmsGatewayError
from .const import (
    ATTR_MESSAGE,
    ATTR_PHONE_NUMBER,
    CONF_EVENTS,
    CONF_URL_MODE,
    CONF_WEBHOOK_ID,
    DEFAULT_EVENTS,
    DEFAULT_URL_MODE,
    DOMAIN,
    DOMAIN_EVENT,
    SERVICE_SEND_SMS,
    SIGNAL_PING_UPDATE,
    URL_MODE_AUTO,
    URL_MODE_EXTERNAL,
    URL_MODE_INTERNAL,
    WEBHOOK_EVENT_PING,
    WEBHOOK_UNIQUE_PREFIX,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

# The gateway's local API accepts any string as a phone number and returns
# 202 Accepted regardless — malformed numbers only ever fail later, silently,
# on the device. Reject obviously invalid input here instead of letting it
# disappear into a message that will never send.
E164_PATTERN = re.compile(r"^\+[1-9]\d{6,14}$")


def _validate_phone_number(value: str) -> str:
    value = cv.string(value)
    if not E164_PATTERN.match(value):
        raise vol.Invalid(
            f"'{value}' is not a valid phone number in E.164 format (e.g. +33612345678)"
        )
    return value


SEND_SMS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Required(ATTR_PHONE_NUMBER): _validate_phone_number,
    }
)

_URL_MODE_KWARGS = {
    URL_MODE_INTERNAL: {"allow_internal": True, "allow_external": False},
    URL_MODE_EXTERNAL: {"allow_internal": False, "allow_external": True},
    URL_MODE_AUTO: {"allow_internal": True, "allow_external": True},
}


def _webhook_name(event: str) -> str:
    """Id under which `event` is registered with the device's /webhooks API."""
    return f"{WEBHOOK_UNIQUE_PREFIX}-{event.replace(':', '-')}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Android SMS Gateway from a config entry."""
    client = AndroidSmsGatewayClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )

    async def async_send_sms(call: ServiceCall) -> None:
        try:
            await client.async_send_sms(
                call.data[ATTR_MESSAGE], call.data[ATTR_PHONE_NUMBER]
            )
        except AndroidSmsGatewayError as err:
            raise HomeAssistantError(str(err)) from err
        except aiohttp.ClientError as err:
            raise HomeAssistantError(f"Failed to reach SMS Gateway: {err}") from err

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_SMS, async_send_sms, schema=SEND_SMS_SCHEMA
    )

    # Registered unconditionally (independent of which events are selected)
    # so device triggers have a device_id to attach to even before any event
    # webhook is registered.
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Android SMS Gateway",
    )

    ping_data: dict[str, Any] = {"last_ping": None, "status": None, "battery": None}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "ping": ping_data,
        "platforms": [],
    }

    events: list[str] = entry.options.get(CONF_EVENTS, DEFAULT_EVENTS)

    if events:
        webhook_id = entry.data.get(CONF_WEBHOOK_ID)
        if webhook_id is None:
            # Entries created before this field existed don't have one yet —
            # generate it now instead of requiring a remove/re-add.
            webhook_id = secrets.token_hex(16)
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_WEBHOOK_ID: webhook_id}
            )

        async def handle_webhook(
            hass: HomeAssistant, webhook_id: str, request: web.Request
        ) -> None:
            try:
                payload = await request.json()
            except ValueError:
                _LOGGER.warning("Received non-JSON webhook payload")
                return

            event = payload.get("event")

            if event == WEBHOOK_EVENT_PING:
                health = payload.get("payload", {}).get("health", {})
                checks = health.get("checks", {})
                ping_data["last_ping"] = dt_util.utcnow()
                ping_data["status"] = health.get("status")
                battery = checks.get("battery:level", {}).get("observedValue")
                if battery is not None:
                    ping_data["battery"] = battery
                async_dispatcher_send(hass, SIGNAL_PING_UPDATE)

            # Fired for every subscribed event, ping included, so trigger.py
            # can also be used to react to gateway health changes. device_id
            # lets device_trigger.py scope a trigger to this gateway when
            # more than one is configured.
            hass.bus.async_fire(
                DOMAIN_EVENT,
                {
                    CONF_TYPE: event,
                    CONF_DEVICE_ID: device_entry.id,
                    "payload": payload.get("payload", {}),
                },
            )

        webhook.async_register(
            hass, DOMAIN, "Android SMS Gateway", webhook_id, handle_webhook
        )
        entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))

        url_mode = entry.options.get(CONF_URL_MODE, DEFAULT_URL_MODE)
        try:
            # url_mode defaults to "internal": the device is normally on the
            # same LAN, and Home Assistant's external_url here sits behind
            # Teleport's own auth wall — a URL choice isn't verified to
            # actually be reachable, so picking "external" without the
            # gateway able to reach it will register successfully and then
            # silently never deliver.
            base_url = get_url(hass, **_URL_MODE_KWARGS[url_mode])
            webhook_url = f"{base_url}/api/webhook/{webhook_id}"
            for event in events:
                await client.async_ensure_webhook(
                    _webhook_name(event), event, webhook_url
                )
        except (AndroidSmsGatewayError, aiohttp.ClientError, NoURLAvailableError) as err:
            _LOGGER.warning("Could not register webhook(s) with SMS Gateway: %s", err)

        if WEBHOOK_EVENT_PING in events:
            platforms = PLATFORMS
            hass.data[DOMAIN][entry.entry_id]["platforms"] = platforms
            await hass.config_entries.async_forward_entry_setups(entry, platforms)

    # Remove device-side registrations for events no longer selected (or all
    # of them, if `events` is now empty) — async_ensure_webhook only ever
    # adds/replaces, it never cleans up what's no longer wanted.
    try:
        desired_ids = {_webhook_name(event) for event in events}
        for item in await client.async_list_webhooks():
            webhook_name = item.get("id", "")
            if (
                webhook_name.startswith(f"{WEBHOOK_UNIQUE_PREFIX}-")
                and webhook_name not in desired_ids
            ):
                await client.async_delete_webhook(webhook_name)
    except (AndroidSmsGatewayError, aiohttp.ClientError) as err:
        _LOGGER.warning("Could not prune stale webhooks from SMS Gateway: %s", err)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.services.async_remove(DOMAIN, SERVICE_SEND_SMS)
    platforms = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("platforms", [])
    unload_ok = (
        await hass.config_entries.async_unload_platforms(entry, platforms)
        if platforms
        else True
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
