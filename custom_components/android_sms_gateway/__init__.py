"""The Android SMS Gateway integration."""

from __future__ import annotations

import logging
import re

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import ATTR_MESSAGE, ATTR_PHONE_NUMBER, DOMAIN, SERVICE_SEND_SMS

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = []

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
    session = async_get_clientsession(hass)
    auth = aiohttp.BasicAuth(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    endpoint = entry.data[CONF_URL].rstrip("/")

    async def async_send_sms(call: ServiceCall) -> None:
        payload = {
            "textMessage": {"text": call.data[ATTR_MESSAGE]},
            "phoneNumbers": [call.data[ATTR_PHONE_NUMBER]],
        }
        try:
            async with session.post(
                f"{endpoint}/message",
                json=payload,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status >= 400:
                    body = await response.text()
                    raise HomeAssistantError(
                        f"SMS Gateway returned HTTP {response.status}: {body}"
                    )
        except aiohttp.ClientError as err:
            raise HomeAssistantError(f"Failed to reach SMS Gateway: {err}") from err

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_SMS, async_send_sms, schema=SEND_SMS_SCHEMA
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"endpoint": endpoint}

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.services.async_remove(DOMAIN, SERVICE_SEND_SMS)
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
