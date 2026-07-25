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
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.network import get_url
from homeassistant.util import dt as dt_util

from .api import AndroidSmsGatewayClient, AndroidSmsGatewayError
from .const import (
    ATTR_MESSAGE,
    ATTR_PHONE_NUMBER,
    CONF_WEBHOOK_ID,
    DOMAIN,
    SERVICE_SEND_SMS,
    SIGNAL_PING_UPDATE,
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

    ping_data: dict[str, Any] = {"last_ping": None, "status": None, "battery": None}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "ping": ping_data,
    }

    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    if webhook_id is None:
        # Entries created before this field existed don't have one yet —
        # generate it now instead of requiring a remove/re-add.
        webhook_id = secrets.token_hex(16)
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_WEBHOOK_ID: webhook_id}
        )

    async def handle_ping_webhook(
        hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> None:
        try:
            payload = await request.json()
        except ValueError:
            _LOGGER.warning("Received non-JSON ping webhook payload")
            return

        health = payload.get("payload", {}).get("health", {})
        checks = health.get("checks", {})
        ping_data["last_ping"] = dt_util.utcnow()
        ping_data["status"] = health.get("status")
        battery = checks.get("battery:level", {}).get("observedValue")
        if battery is not None:
            ping_data["battery"] = battery

        async_dispatcher_send(hass, SIGNAL_PING_UPDATE)

    webhook.async_register(
        hass, DOMAIN, "Android SMS Gateway Ping", webhook_id, handle_ping_webhook
    )
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))

    try:
        webhook_url = f"{get_url(hass, allow_internal=True, prefer_external=True)}/api/webhook/{webhook_id}"
        webhook_name = f"{WEBHOOK_UNIQUE_PREFIX}-{WEBHOOK_EVENT_PING.replace(':', '-')}"
        await client.async_ensure_webhook(webhook_name, WEBHOOK_EVENT_PING, webhook_url)
    except (AndroidSmsGatewayError, aiohttp.ClientError) as err:
        _LOGGER.warning("Could not register ping webhook with SMS Gateway: %s", err)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.services.async_remove(DOMAIN, SERVICE_SEND_SMS)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
