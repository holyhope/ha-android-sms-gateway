"""Trigger platform for Android SMS Gateway events.

Fires whenever the integration receives a subscribed device webhook (see
`__init__.async_setup_entry`'s `handle_webhook`), regardless of which config
entry / device it came from — filter by device in the automation UI via
device_trigger.py if you have more than one gateway configured.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, Event, HassJob, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, DOMAIN_EVENT, EVENT_TYPES

TRIGGER_SCHEMA = cv.TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_PLATFORM): DOMAIN,
        vol.Required(CONF_TYPE): vol.In(EVENT_TYPES),
        # Not exposed on the platform trigger's own UI form — set internally
        # by device_trigger.py to scope a trigger to a single gateway device.
        vol.Optional(CONF_DEVICE_ID): cv.string,
    }
)


async def async_validate_trigger_config(
    hass: HomeAssistant, config: ConfigType
) -> ConfigType:
    """Validate trigger config."""
    return TRIGGER_SCHEMA(config)


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger that fires when the given gateway event type is received."""
    event_type = config[CONF_TYPE]
    device_id = config.get(CONF_DEVICE_ID)
    job = HassJob(action)

    @callback
    def _handle_event(event: Event) -> None:
        if event.data.get(CONF_TYPE) != event_type:
            return
        if device_id is not None and event.data.get(CONF_DEVICE_ID) != device_id:
            return
        hass.async_run_hass_job(
            job,
            {
                "trigger": {
                    **trigger_info["trigger_data"],
                    "platform": DOMAIN,
                    "type": event_type,
                    "payload": event.data.get("payload", {}),
                }
            },
        )

    return hass.bus.async_listen(DOMAIN_EVENT, _handle_event)
