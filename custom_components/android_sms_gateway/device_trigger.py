"""Device triggers for Android SMS Gateway.

Thin wrapper around trigger.py: lets an automation pick "SMS received" (etc.)
scoped to a specific gateway device, instead of the generic (device-less)
platform trigger which fires for every configured gateway.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from . import trigger as gateway_trigger
from .const import DOMAIN, EVENT_TYPES

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(EVENT_TYPES),
    }
)


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict]:
    """List device triggers for an Android SMS Gateway device."""
    device_registry = dr.async_get(hass)
    if device_registry.async_get(device_id) is None:
        return []

    return [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: event_type,
        }
        for event_type in EVENT_TYPES
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a device trigger by delegating to the domain's event trigger."""
    platform_config = gateway_trigger.TRIGGER_SCHEMA(
        {
            CONF_PLATFORM: DOMAIN,
            CONF_TYPE: config[CONF_TYPE],
            CONF_DEVICE_ID: config[CONF_DEVICE_ID],
        }
    )
    return await gateway_trigger.async_attach_trigger(
        hass, platform_config, action, trigger_info
    )
