"""Tests for the platform-level trigger."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.const import CONF_DEVICE_ID, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import HomeAssistant

from custom_components.android_sms_gateway import trigger
from custom_components.android_sms_gateway.const import (
    DOMAIN,
    DOMAIN_EVENT,
    EVENT_SMS_RECEIVED,
    EVENT_SMS_SENT,
)


async def _attach(hass: HomeAssistant, config: dict, action):
    validated = await trigger.async_validate_trigger_config(hass, config)
    return await trigger.async_attach_trigger(
        hass,
        validated,
        action,
        {"trigger_data": {"id": "0"}},
    )


async def test_trigger_fires_on_matching_event(hass):
    action = AsyncMock()
    await _attach(
        hass,
        {CONF_PLATFORM: DOMAIN, CONF_TYPE: EVENT_SMS_RECEIVED},
        action,
    )

    hass.bus.async_fire(
        DOMAIN_EVENT,
        {CONF_TYPE: EVENT_SMS_RECEIVED, CONF_DEVICE_ID: "dev-1", "payload": {"a": 1}},
    )
    await hass.async_block_till_done()

    assert action.call_count == 1
    run_variables = action.call_args[0][0]
    assert run_variables["trigger"]["platform"] == DOMAIN
    assert run_variables["trigger"]["type"] == EVENT_SMS_RECEIVED
    assert run_variables["trigger"]["payload"] == {"a": 1}


async def test_trigger_ignores_non_matching_type(hass):
    action = AsyncMock()
    await _attach(
        hass,
        {CONF_PLATFORM: DOMAIN, CONF_TYPE: EVENT_SMS_RECEIVED},
        action,
    )

    hass.bus.async_fire(
        DOMAIN_EVENT,
        {CONF_TYPE: EVENT_SMS_SENT, CONF_DEVICE_ID: "dev-1", "payload": {}},
    )
    await hass.async_block_till_done()

    assert action.call_count == 0


async def test_trigger_respects_device_id_filter(hass):
    action = AsyncMock()
    await _attach(
        hass,
        {
            CONF_PLATFORM: DOMAIN,
            CONF_TYPE: EVENT_SMS_RECEIVED,
            CONF_DEVICE_ID: "dev-1",
        },
        action,
    )

    hass.bus.async_fire(
        DOMAIN_EVENT,
        {CONF_TYPE: EVENT_SMS_RECEIVED, CONF_DEVICE_ID: "dev-2", "payload": {}},
    )
    await hass.async_block_till_done()
    assert action.call_count == 0

    hass.bus.async_fire(
        DOMAIN_EVENT,
        {CONF_TYPE: EVENT_SMS_RECEIVED, CONF_DEVICE_ID: "dev-1", "payload": {}},
    )
    await hass.async_block_till_done()
    assert action.call_count == 1


async def test_trigger_without_device_id_matches_any_device(hass):
    action = AsyncMock()
    await _attach(
        hass,
        {CONF_PLATFORM: DOMAIN, CONF_TYPE: EVENT_SMS_RECEIVED},
        action,
    )

    for device_id in ("dev-1", "dev-2"):
        hass.bus.async_fire(
            DOMAIN_EVENT,
            {CONF_TYPE: EVENT_SMS_RECEIVED, CONF_DEVICE_ID: device_id, "payload": {}},
        )
    await hass.async_block_till_done()

    assert action.call_count == 2


async def test_detach_stops_further_firing(hass):
    action = AsyncMock()
    detach = await _attach(
        hass,
        {CONF_PLATFORM: DOMAIN, CONF_TYPE: EVENT_SMS_RECEIVED},
        action,
    )
    detach()

    hass.bus.async_fire(
        DOMAIN_EVENT,
        {CONF_TYPE: EVENT_SMS_RECEIVED, CONF_DEVICE_ID: "dev-1", "payload": {}},
    )
    await hass.async_block_till_done()

    assert action.call_count == 0
