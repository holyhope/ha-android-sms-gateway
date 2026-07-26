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

# https://github.com/capcom6/android-sms-gateway#supported-events
EVENT_SMS_RECEIVED = "sms:received"
EVENT_SMS_SENT = "sms:sent"
EVENT_SMS_DELIVERED = "sms:delivered"
EVENT_SMS_FAILED = "sms:failed"
EVENT_SMS_DATA_RECEIVED = "sms:data-received"
EVENT_MMS_RECEIVED = "mms:received"
EVENT_MMS_DOWNLOADED = "mms:downloaded"
WEBHOOK_EVENT_PING = "system:ping"

EVENT_TYPES = [
    EVENT_SMS_RECEIVED,
    EVENT_SMS_SENT,
    EVENT_SMS_DELIVERED,
    EVENT_SMS_FAILED,
    EVENT_SMS_DATA_RECEIVED,
    EVENT_MMS_RECEIVED,
    EVENT_MMS_DOWNLOADED,
    WEBHOOK_EVENT_PING,
]

# Event bus event type fired for every inbound gateway webhook, regardless of
# which of EVENT_TYPES it carries — trigger.py filters by the "type" field.
DOMAIN_EVENT = f"{DOMAIN}_event"

SIGNAL_PING_UPDATE = f"{DOMAIN}_ping_update"

# The "Online" binary_sensor's staleness threshold adapts to the observed gap
# between real pings (PING_STALE_MULTIPLIER x the last observed interval)
# instead of trusting the device's configured ping.interval_seconds, which
# has been observed in practice to not actually govern the real cadence.
# PING_DEFAULT_STALE_AFTER is the bootstrap value used until a second ping
# has been received and a real interval can be computed.
PING_DEFAULT_STALE_AFTER = timedelta(minutes=15)
PING_MIN_STALE_AFTER = timedelta(minutes=2)
PING_STALE_MULTIPLIER = 3

CONF_EVENTS = "events"
CONF_URL_MODE = "url_mode"

URL_MODE_AUTO = "auto"
URL_MODE_INTERNAL = "internal"
URL_MODE_EXTERNAL = "external"
URL_MODES = [URL_MODE_AUTO, URL_MODE_INTERNAL, URL_MODE_EXTERNAL]

# Matches what this repo's Terraform sms-gateway module already registers by
# default — sms:data-received (binary/machine SMS) and the other sms:*
# delivery-status events are opt-in, not on by default.
DEFAULT_EVENTS = [EVENT_SMS_RECEIVED, EVENT_MMS_RECEIVED, WEBHOOK_EVENT_PING]
DEFAULT_URL_MODE = URL_MODE_INTERNAL
