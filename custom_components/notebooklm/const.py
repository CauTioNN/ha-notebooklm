"""Constants for the NotebookLM integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "notebooklm"

# The pinned version of the upstream library this integration is built against.
LIBRARY_VERSION = "0.6.0"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT]

# --- Config entry / data keys ------------------------------------------------
# ``storage_state`` holds the Playwright ``storage_state.json`` payload (the
# Google auth cookies). It is the ONLY credential this integration stores and it
# is supplied per-user through the config flow — nothing is hardcoded.
CONF_STORAGE_STATE = "storage_state"
CONF_ACCOUNT_EMAIL = "account_email"

# --- Options keys ------------------------------------------------------------
CONF_DEFAULT_NOTEBOOK = "default_notebook"
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 600  # seconds

# --- Auth methods (config-flow menu) -----------------------------------------
AUTH_METHOD_GOOGLE = "google"
AUTH_METHOD_MANUAL = "manual"

# Keepalive interval (seconds) passed to the upstream client so long-lived
# cookies are proactively refreshed while Home Assistant is running.
KEEPALIVE_INTERVAL = 600

# --- Companion add-on (in-HA Google login) -----------------------------------
# The add-on writes the captured storage_state to this file inside the Home
# Assistant config directory; the Google config-flow step reads it back.
ADDON_SLUG = "notebooklm_login"
ADDON_RESULT_FILE = ".notebooklm_login_result.json"

# --- Events ------------------------------------------------------------------
EVENT_ARTIFACT_READY = "notebooklm_artifact_ready"
EVENT_ARTIFACT_FAILED = "notebooklm_artifact_failed"
EVENT_SOURCE_ADDED = "notebooklm_source_added"

# Fired on the HA event bus when the stored Google session expires and could not
# be refreshed. Wire an automation to this to push a notification to your phone:
#   trigger: { platform: event, event_type: notebooklm_auth_expired }
EVENT_AUTH_EXPIRED = "notebooklm_auth_expired"

# --- Re-auth notification ----------------------------------------------------
# Persistent-notification id prefix for the "sign-in required" notice. One per
# config entry so multiple accounts don't overwrite each other's notice.
AUTH_NOTIFICATION_PREFIX = "notebooklm_reauth_"
