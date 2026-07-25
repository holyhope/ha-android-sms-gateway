"""Minimal async client for the Android SMS Gateway local API."""

from __future__ import annotations

import aiohttp


class AndroidSmsGatewayError(Exception):
    """Raised when the gateway API returns an error."""


class AndroidSmsGatewayClient:
    """Thin wrapper around the gateway's local REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        endpoint: str,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._endpoint = endpoint.rstrip("/")
        self._auth = aiohttp.BasicAuth(username, password)

    async def async_send_sms(self, message: str, phone_number: str) -> None:
        """Send a text message."""
        payload = {
            "textMessage": {"text": message},
            "phoneNumbers": [phone_number],
        }
        async with self._session.post(
            f"{self._endpoint}/message",
            json=payload,
            auth=self._auth,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status >= 400:
                body = await response.text()
                raise AndroidSmsGatewayError(
                    f"SMS Gateway returned HTTP {response.status}: {body}"
                )

    async def async_check_auth(self) -> None:
        """Raise if the endpoint is unreachable or credentials are invalid."""
        async with self._session.get(
            f"{self._endpoint}/",
            auth=self._auth,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status == 401:
                raise AndroidSmsGatewayError("invalid_auth")
            if response.status >= 400:
                raise AndroidSmsGatewayError("cannot_connect")

    async def async_ensure_webhook(self, webhook_name: str, event: str, url: str) -> None:
        """Register a device-side webhook, replacing it if url/event drifted.

        The API has no update endpoint (PUT returns 404) — a changed url or
        event requires deleting the existing registration before recreating it.
        """
        async with self._session.get(
            f"{self._endpoint}/webhooks",
            auth=self._auth,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status >= 400:
                raise AndroidSmsGatewayError(
                    f"Failed to list webhooks: HTTP {response.status}"
                )
            existing = await response.json()

        match = next(
            (item for item in existing if item.get("id") == webhook_name), None
        )
        if match is not None:
            if match.get("url") == url and match.get("event") == event:
                return
            async with self._session.delete(
                f"{self._endpoint}/webhooks/{webhook_name}",
                auth=self._auth,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status >= 400 and response.status != 404:
                    raise AndroidSmsGatewayError(
                        f"Failed to delete stale webhook: HTTP {response.status}"
                    )

        async with self._session.post(
            f"{self._endpoint}/webhooks",
            json={"id": webhook_name, "url": url, "event": event},
            auth=self._auth,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status >= 400:
                body = await response.text()
                raise AndroidSmsGatewayError(
                    f"Failed to register webhook: HTTP {response.status}: {body}"
                )
