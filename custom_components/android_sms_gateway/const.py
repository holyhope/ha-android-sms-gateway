"""Constants for the Android SMS Gateway integration."""

from datetime import timedelta

DOMAIN = "android_sms_gateway"

SERVICE_SEND_SMS = "send_sms"

ATTR_MESSAGE = "message"
ATTR_PHONE_NUMBER = "phone_number"

CONF_WEBHOOK_ID = "webhook_id"

# id/event naming registered with the device's own /webhooks API. The actual
# webhook_id (the secret path component of the inbound HA URL) is generated
# per config entry, not hardcoded here — see config_flow.py.
WEBHOOK_UNIQUE_PREFIX = "home-assistant"
WEBHOOK_EVENT_PING = "system:ping"

SIGNAL_PING_UPDATE = f"{DOMAIN}_ping_update"

PING_STALE_AFTER = timedelta(minutes=15)
