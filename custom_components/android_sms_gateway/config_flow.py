"""Config flow for Android SMS Gateway."""

from __future__ import annotations

import logging
import secrets
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import AndroidSmsGatewayClient, AndroidSmsGatewayError
from .const import (
    CONF_EVENTS,
    CONF_URL_MODE,
    CONF_WEBHOOK_ID,
    DEFAULT_EVENTS,
    DEFAULT_URL_MODE,
    DOMAIN,
    EVENT_TYPES,
    URL_MODES,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(),
        vol.Required(CONF_USERNAME): TextSelector(),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


async def _validate_input(hass: Any, data: dict[str, Any]) -> None:
    """Check the gateway is reachable with the given credentials.

    The app's /health endpoint isn't reliable in Local Server mode (returns
    500 regardless of auth on some builds), so we check the auth-gated root
    endpoint instead, which correctly returns 401 on bad credentials and 200
    otherwise.
    """
    client = AndroidSmsGatewayClient(
        async_get_clientsession(hass),
        data[CONF_URL],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
    )
    try:
        await client.async_check_auth()
    except AndroidSmsGatewayError as err:
        if str(err) == "invalid_auth":
            raise InvalidAuth from err
        raise CannotConnect from err
    except aiohttp.ClientError as err:
        raise CannotConnect from err


class AndroidSmsGatewayConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Android SMS Gateway."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _validate_input(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_URL])
                self._abort_if_unique_id_configured()
                # Generated once per install and never displayed or logged —
                # it's the secret path component of this entry's inbound
                # webhook URL (see __init__.py's ping webhook registration).
                data = {**user_input, CONF_WEBHOOK_ID: secrets.token_hex(16)}
                return self.async_create_entry(title="Android SMS Gateway", data=data)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> AndroidSmsGatewayOptionsFlow:
        """Get the options flow for this handler."""
        return AndroidSmsGatewayOptionsFlow()


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EVENTS, default=DEFAULT_EVENTS): SelectSelector(
            SelectSelectorConfig(options=EVENT_TYPES, multiple=True)
        ),
        vol.Required(CONF_URL_MODE, default=DEFAULT_URL_MODE): SelectSelector(
            SelectSelectorConfig(options=URL_MODES)
        ),
    }
)


class AndroidSmsGatewayOptionsFlow(OptionsFlow):
    """Handle options for Android SMS Gateway.

    events selects which android-sms-gateway events get a webhook registered
    with the device and become available as triggers; system:ping also
    drives the Online/Battery device entities. url_mode controls which Home
    Assistant URL is registered with the gateway as the webhook target:
    internal (default — the device is normally on the same LAN), external
    (needed if the device reaches Home Assistant only through a public URL),
    or auto (internal if configured, else external). No connectivity check
    is done on this choice — an external URL that requires auth upstream
    (e.g. behind Teleport) will still "successfully" register and then
    silently never deliver.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
