"""Constants for the NotebookLM integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "notebooklm"

# The pinned version of the upstream library this integration is built against.
LIBRARY_VERSION = "0.6.0"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SELECT,
    Platform.TEXT,
    Platform.BUTTON,
]

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

# --- Self-documenting HA (documentation sync) --------------------------------
# Target notebook the HA snapshot is synced into, the enabled sections, and
# whether to scrub free-text values (secrets/coords/emails are ALWAYS removed
# from sensitive keys regardless — this flag only gates the extra value regex).
CONF_DOC_NOTEBOOK = "doc_notebook"
CONF_DOC_CATEGORIES = "doc_categories"
CONF_DOC_SCRUB = "doc_scrub"

# Every synced section becomes one text source titled "<prefix> <Section>". The
# prefix lets a re-sync find and delete the previous version so a section never
# accumulates duplicate sources.
DOC_SOURCE_PREFIX = "🏠 HA ·"

# The export sections the user can toggle (checkboxes in the options flow).
DOC_CATEGORIES: list[str] = [
    "overview",
    "areas",
    "entities",
    "automations",
    "scripts",
    "scenes",
    "helpers",
    "integrations",
]
DEFAULT_DOC_CATEGORIES: list[str] = list(DOC_CATEGORIES)

# Human-readable section title (after the prefix) per category.
DOC_CATEGORY_TITLES: dict[str, str] = {
    "overview": "Overview",
    "areas": "Areas & Devices",
    "entities": "Entities",
    "automations": "Automations",
    "scripts": "Scripts",
    "scenes": "Scenes",
    "helpers": "Helpers",
    "integrations": "Integrations",
}

# How often the schedule select re-runs the sync (seconds). ``manual`` = off.
DOC_SCHEDULE_MANUAL = "manual"
DOC_SCHEDULES: dict[str, int | None] = {
    DOC_SCHEDULE_MANUAL: None,
    "daily": 86400,
    "every_3_days": 259200,
    "weekly": 604800,
    "monthly": 2592000,  # ~30 days
}
DEFAULT_DOC_SCHEDULE = DOC_SCHEDULE_MANUAL

# NotebookLM pasted-text sources have a size ceiling; sections larger than this
# are split into "<title> (part n/m)" sources.
DOC_MAX_SOURCE_CHARS = 480_000

# --- Events ------------------------------------------------------------------
EVENT_ARTIFACT_READY = "notebooklm_artifact_ready"
EVENT_ARTIFACT_FAILED = "notebooklm_artifact_failed"
EVENT_SOURCE_ADDED = "notebooklm_source_added"

# Fired after a documentation sync completes (success or failure).
EVENT_DOC_SYNCED = "notebooklm_documentation_synced"

# Fired on the HA event bus when the stored Google session expires and could not
# be refreshed. Wire an automation to this to push a notification to your phone:
#   trigger: { platform: event, event_type: notebooklm_auth_expired }
EVENT_AUTH_EXPIRED = "notebooklm_auth_expired"

# --- Re-auth notification ----------------------------------------------------
# Persistent-notification id prefix for the "sign-in required" notice. One per
# config entry so multiple accounts don't overwrite each other's notice.
AUTH_NOTIFICATION_PREFIX = "notebooklm_reauth_"
