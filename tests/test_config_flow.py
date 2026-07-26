"""Tests for the config and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.android_sms_gateway.api import AndroidSmsGatewayError
from custom_components.android_sms_gateway.const import (
    CONF_EVENTS,
    CONF_URL_MODE,
    CONF_WEBHOOK_ID,
    DOMAIN,
    EVENT_SMS_RECEIVED,
    URL_MODE_EXTERNAL,
    WEBHOOK_EVENT_PING,
)

USER_INPUT = {
    CONF_URL: "http://192.168.1.12:8080",
    CONF_USERNAME: "user",
    CONF_PASSWORD: "pass",
}


async def test_user_flow_success(hass, aioclient_mock):
    # A successful CREATE_ENTRY triggers real entry setup, which lists the
    # gateway's webhooks (both to register events and to prune stale ones).
    aioclient_mock.get(f"{USER_INPUT[CONF_URL]}/webhooks", json=[])

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM

    with patch(
        "custom_components.android_sms_gateway.config_flow._validate_input",
        new=AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_URL] == USER_INPUT[CONF_URL]
    assert CONF_WEBHOOK_ID in result["data"]


async def test_user_flow_invalid_auth(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.android_sms_gateway.config_flow.AndroidSmsGatewayClient.async_check_auth",
        new=AsyncMock(side_effect=AndroidSmsGatewayError("invalid_auth")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.android_sms_gateway.config_flow.AndroidSmsGatewayClient.async_check_auth",
        new=AsyncMock(side_effect=AndroidSmsGatewayError("cannot_connect")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_aborts_on_duplicate_url(hass):
    MockConfigEntry(
        domain=DOMAIN, unique_id=USER_INPUT[CONF_URL], data=USER_INPUT
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.android_sms_gateway.config_flow._validate_input",
        new=AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_defaults(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=USER_INPUT[CONF_URL],
        data={**USER_INPUT, CONF_WEBHOOK_ID: "abc123"},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_EVENTS: [EVENT_SMS_RECEIVED, WEBHOOK_EVENT_PING],
            CONF_URL_MODE: URL_MODE_EXTERNAL,
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_EVENTS: [EVENT_SMS_RECEIVED, WEBHOOK_EVENT_PING],
        CONF_URL_MODE: URL_MODE_EXTERNAL,
    }
