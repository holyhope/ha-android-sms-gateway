"""Tests for async_setup_entry/async_unload_entry."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import Event
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.android_sms_gateway.const import (
    CONF_EVENTS,
    CONF_WEBHOOK_ID,
    DOMAIN,
    DOMAIN_EVENT,
    EVENT_SMS_RECEIVED,
    WEBHOOK_EVENT_PING,
)

ENDPOINT = "http://192.168.1.12:8080"
DATA = {
    CONF_URL: ENDPOINT,
    CONF_USERNAME: "user",
    CONF_PASSWORD: "pass",
    CONF_WEBHOOK_ID: "test-webhook-id",
}


def _make_entry(hass, events=None):
    options = {} if events is None else {CONF_EVENTS: events}
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ENDPOINT, data=DATA, options=options)
    entry.add_to_hass(hass)
    return entry


async def test_setup_registers_device_unconditionally(hass, aioclient_mock):
    aioclient_mock.get(f"{ENDPOINT}/webhooks", json=[])
    entry = _make_entry(hass, events=[])

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None


async def test_setup_registers_webhook_for_each_selected_event(hass, aioclient_mock):
    aioclient_mock.get(f"{ENDPOINT}/webhooks", json=[])
    aioclient_mock.post(f"{ENDPOINT}/webhooks", status=201)
    entry = _make_entry(hass, events=[EVENT_SMS_RECEIVED, WEBHOOK_EVENT_PING])

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    post_bodies = [
        c[2] for c in aioclient_mock.mock_calls if c[0].lower() == "post"
    ]
    registered_events = {body["event"] for body in post_bodies}
    assert registered_events == {EVENT_SMS_RECEIVED, WEBHOOK_EVENT_PING}
    # Every registration must reuse the same inbound webhook URL/id.
    assert len({body["url"] for body in post_bodies}) == 1


async def test_setup_prunes_deselected_event_webhooks(hass, aioclient_mock):
    aioclient_mock.get(
        f"{ENDPOINT}/webhooks",
        json=[
            {"id": "home-assistant-sms-sent", "url": "x", "event": "sms:sent"},
            {"id": "some-other-app-webhook", "url": "y", "event": "sms:received"},
        ],
    )
    aioclient_mock.post(f"{ENDPOINT}/webhooks", status=201)
    aioclient_mock.delete(f"{ENDPOINT}/webhooks/home-assistant-sms-sent", status=200)
    entry = _make_entry(hass, events=[EVENT_SMS_RECEIVED])

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    deleted = [
        c[1].path
        for c in aioclient_mock.mock_calls
        if c[0].lower() == "delete"
    ]
    # Only the deselected home-assistant-prefixed webhook is pruned — a
    # same-named-prefix-unrelated third-party webhook is left untouched.
    assert deleted == ["/webhooks/home-assistant-sms-sent"]


async def test_setup_skips_platforms_without_ping(hass, aioclient_mock):
    aioclient_mock.get(f"{ENDPOINT}/webhooks", json=[])
    aioclient_mock.post(f"{ENDPOINT}/webhooks", status=201)
    entry = _make_entry(hass, events=[EVENT_SMS_RECEIVED])

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.android_sms_gateway_online") is None


async def test_setup_sets_up_platforms_with_ping(hass, aioclient_mock):
    aioclient_mock.get(f"{ENDPOINT}/webhooks", json=[])
    aioclient_mock.post(f"{ENDPOINT}/webhooks", status=201)
    entry = _make_entry(hass, events=[WEBHOOK_EVENT_PING])

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    states = [s.entity_id for s in hass.states.async_all()]
    assert any(e.startswith("binary_sensor.") for e in states)
    assert any(e.startswith("sensor.") for e in states)


async def test_webhook_fires_bus_event_and_ignores_bad_json(hass, aioclient_mock, hass_client_no_auth):
    aioclient_mock.get(f"{ENDPOINT}/webhooks", json=[])
    aioclient_mock.post(f"{ENDPOINT}/webhooks", status=201)
    entry = _make_entry(hass, events=[EVENT_SMS_RECEIVED])
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    events: list[Event] = []
    hass.bus.async_listen(DOMAIN_EVENT, events.append)

    client = await hass_client_no_auth()
    resp = await client.post(
        f"/api/webhook/{DATA[CONF_WEBHOOK_ID]}",
        json={"event": "sms:received", "payload": {"phoneNumber": "+33612345678"}},
    )
    assert resp.status == 200
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["type"] == "sms:received"
    assert events[0].data["payload"] == {"phoneNumber": "+33612345678"}

    # Malformed JSON must not crash the webhook handler or fire an event.
    resp = await client.post(
        f"/api/webhook/{DATA[CONF_WEBHOOK_ID]}",
        data="not json",
        headers={"content-type": "application/json"},
    )
    assert resp.status == 200
    await hass.async_block_till_done()
    assert len(events) == 1


async def test_ping_webhook_updates_ping_entities(hass, aioclient_mock, hass_client_no_auth):
    aioclient_mock.get(f"{ENDPOINT}/webhooks", json=[])
    aioclient_mock.post(f"{ENDPOINT}/webhooks", status=201)
    entry = _make_entry(hass, events=[WEBHOOK_EVENT_PING])
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    client = await hass_client_no_auth()
    resp = await client.post(
        f"/api/webhook/{DATA[CONF_WEBHOOK_ID]}",
        json={
            "event": "system:ping",
            "payload": {
                "health": {
                    "status": "pass",
                    "checks": {"battery:level": {"observedValue": 42}},
                }
            },
        },
    )
    assert resp.status == 200
    await hass.async_block_till_done()

    battery = hass.states.get("sensor.android_sms_gateway_battery")
    online = hass.states.get("binary_sensor.android_sms_gateway_online")
    assert battery is not None and battery.state == "42"
    assert online is not None and online.state == "on"


async def test_unload_entry(hass, aioclient_mock):
    aioclient_mock.get(f"{ENDPOINT}/webhooks", json=[])
    aioclient_mock.post(f"{ENDPOINT}/webhooks", status=201)
    entry = _make_entry(hass, events=[WEBHOOK_EVENT_PING])
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert not hass.services.has_service(DOMAIN, "send_sms")
