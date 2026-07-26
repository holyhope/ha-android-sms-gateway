"""Tests for AndroidSmsGatewayClient.

Uses Home Assistant's own aioclient_mock (rather than aioresponses) since it
mocks at the same _request seam Home Assistant's aiohttp session uses, and
stays in lockstep with whatever aiohttp version core currently pins.
"""

from __future__ import annotations

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.android_sms_gateway.api import (
    AndroidSmsGatewayClient,
    AndroidSmsGatewayError,
)

ENDPOINT = "http://192.168.1.12:8080"


@pytest.fixture
async def client(hass, aioclient_mock):
    return AndroidSmsGatewayClient(
        async_get_clientsession(hass), ENDPOINT, "user", "pass"
    )


async def test_async_send_sms_success(client, aioclient_mock):
    aioclient_mock.post(f"{ENDPOINT}/message", status=202)
    await client.async_send_sms("hello", "+33612345678")


async def test_async_send_sms_error_raises(client, aioclient_mock):
    aioclient_mock.post(f"{ENDPOINT}/message", status=500, text="boom")
    with pytest.raises(AndroidSmsGatewayError, match="500"):
        await client.async_send_sms("hello", "+33612345678")


async def test_async_check_auth_invalid(client, aioclient_mock):
    aioclient_mock.get(f"{ENDPOINT}/", status=401)
    with pytest.raises(AndroidSmsGatewayError, match="invalid_auth"):
        await client.async_check_auth()


async def test_async_check_auth_cannot_connect(client, aioclient_mock):
    aioclient_mock.get(f"{ENDPOINT}/", status=500)
    with pytest.raises(AndroidSmsGatewayError, match="cannot_connect"):
        await client.async_check_auth()


async def test_async_check_auth_ok(client, aioclient_mock):
    aioclient_mock.get(f"{ENDPOINT}/", status=200)
    await client.async_check_auth()


async def test_async_ensure_webhook_creates_when_absent(client, aioclient_mock):
    aioclient_mock.get(f"{ENDPOINT}/webhooks", json=[])
    aioclient_mock.post(f"{ENDPOINT}/webhooks", status=201)

    await client.async_ensure_webhook(
        "home-assistant-sms-received", "sms:received", "http://ha/webhook"
    )

    post_calls = [c for c in aioclient_mock.mock_calls if c[0].lower() == "post"]
    assert len(post_calls) == 1
    assert post_calls[0][2] == {
        "id": "home-assistant-sms-received",
        "url": "http://ha/webhook",
        "event": "sms:received",
    }


async def test_async_ensure_webhook_noop_when_unchanged(client, aioclient_mock):
    aioclient_mock.get(
        f"{ENDPOINT}/webhooks",
        json=[
            {
                "id": "home-assistant-sms-received",
                "url": "http://ha/webhook",
                "event": "sms:received",
            }
        ],
    )

    await client.async_ensure_webhook(
        "home-assistant-sms-received", "sms:received", "http://ha/webhook"
    )

    # The existing registration already matches url and event — no
    # post/delete calls should have been made.
    assert not [c for c in aioclient_mock.mock_calls if c[0].lower() in ("post", "delete")]


async def test_async_ensure_webhook_replaces_when_drifted(client, aioclient_mock):
    aioclient_mock.get(
        f"{ENDPOINT}/webhooks",
        json=[
            {
                "id": "home-assistant-sms-received",
                "url": "http://old-ha/webhook",
                "event": "sms:received",
            }
        ],
    )
    aioclient_mock.delete(f"{ENDPOINT}/webhooks/home-assistant-sms-received", status=200)
    aioclient_mock.post(f"{ENDPOINT}/webhooks", status=201)

    await client.async_ensure_webhook(
        "home-assistant-sms-received", "sms:received", "http://new-ha/webhook"
    )

    assert any(c[0].lower() == "delete" for c in aioclient_mock.mock_calls)
    assert any(c[0].lower() == "post" for c in aioclient_mock.mock_calls)


async def test_async_list_webhooks(client, aioclient_mock):
    aioclient_mock.get(f"{ENDPOINT}/webhooks", json=[{"id": "a"}, {"id": "b"}])
    result = await client.async_list_webhooks()
    assert result == [{"id": "a"}, {"id": "b"}]


async def test_async_list_webhooks_raises_on_error(client, aioclient_mock):
    aioclient_mock.get(f"{ENDPOINT}/webhooks", status=500)
    with pytest.raises(AndroidSmsGatewayError):
        await client.async_list_webhooks()


async def test_async_delete_webhook_ignores_404(client, aioclient_mock):
    aioclient_mock.delete(f"{ENDPOINT}/webhooks/gone", status=404)
    await client.async_delete_webhook("gone")


async def test_async_delete_webhook_raises_on_error(client, aioclient_mock):
    aioclient_mock.delete(f"{ENDPOINT}/webhooks/oops", status=500)
    with pytest.raises(AndroidSmsGatewayError):
        await client.async_delete_webhook("oops")
