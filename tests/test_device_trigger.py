"""Tests for device triggers."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.android_sms_gateway import device_trigger
from custom_components.android_sms_gateway.const import (
    DOMAIN,
    DOMAIN_EVENT,
    EVENT_TYPES,
    EVENT_SMS_RECEIVED,
)


def _make_device(hass):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    return device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Android SMS Gateway",
    )


async def test_async_get_triggers_returns_all_event_types(hass):
    device = _make_device(hass)

    triggers = await device_trigger.async_get_triggers(hass, device.id)

    assert len(triggers) == len(EVENT_TYPES)
    assert {t[CONF_TYPE] for t in triggers} == set(EVENT_TYPES)
    assert all(t[CONF_DOMAIN] == DOMAIN for t in triggers)
    assert all(t[CONF_DEVICE_ID] == device.id for t in triggers)


async def test_async_get_triggers_empty_for_unknown_device(hass):
    triggers = await device_trigger.async_get_triggers(hass, "does-not-exist")
    assert triggers == []


async def test_device_trigger_scopes_to_its_device(hass):
    device_a = _make_device(hass)
    device_b = _make_device(hass)

    action = AsyncMock()
    config = {
        CONF_PLATFORM: "device",
        CONF_DOMAIN: DOMAIN,
        CONF_DEVICE_ID: device_a.id,
        CONF_TYPE: EVENT_SMS_RECEIVED,
    }
    detach = await device_trigger.async_attach_trigger(
        hass, config, action, {"trigger_data": {"id": "0"}}
    )

    hass.bus.async_fire(
        DOMAIN_EVENT,
        {CONF_TYPE: EVENT_SMS_RECEIVED, CONF_DEVICE_ID: device_b.id, "payload": {}},
    )
    await hass.async_block_till_done()
    assert action.call_count == 0

    hass.bus.async_fire(
        DOMAIN_EVENT,
        {CONF_TYPE: EVENT_SMS_RECEIVED, CONF_DEVICE_ID: device_a.id, "payload": {}},
    )
    await hass.async_block_till_done()
    assert action.call_count == 1

    detach()
