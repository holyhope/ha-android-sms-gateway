# Android SMS Gateway for Home Assistant

A Home Assistant custom integration for sending SMS messages through
[capcom6/android-sms-gateway](https://github.com/capcom6/android-sms-gateway) —
an Android app that turns a phone into an SMS gateway reachable over a local
network (Local Server mode) or the cloud.

## Features

- UI-based setup (`Settings` → `Devices & Services` → `Add Integration`).
- Exposes an `android_sms_gateway.send_sms` action with a proper UI form
  (multiline message field, phone number field), usable directly from
  Developer Tools or in automations/scripts.

## Installation

### HACS

1. Go to HACS → Integrations → the `⋮` menu → **Custom repositories**.
2. Add this repository URL with category **Integration**.
3. Install "Android SMS Gateway" and restart Home Assistant.

### Manual

Copy `custom_components/android_sms_gateway` into your Home Assistant
`config/custom_components` directory and restart.

## Setup

1. On the Android phone, open the SMS Gateway app, enable **Local Server**,
   and start it. Note the local IP, port, username, and password shown.
2. In Home Assistant: `Settings` → `Devices & Services` → `Add Integration`
   → **Android SMS Gateway**.
3. Enter the local server URL (e.g. `http://192.168.1.12:8080`) and the
   username/password from step 1.

## Usage

Call the `android_sms_gateway.send_sms` action with a `message` and a
`phone_number` (E.164 format), e.g.:

```yaml
action: android_sms_gateway.send_sms
data:
  message: "Garage door left open"
  phone_number: "+33612345678"
```
