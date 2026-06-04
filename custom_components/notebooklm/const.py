"""Constants for the NotebookLM integration."""

from __future__ import annotations

import re

from homeassistant.const import Platform

DOMAIN = "notebooklm"

# The pinned version of the upstream library this integration is built against.
LIBRARY_VERSION = "0.6.0"

# URL where the integration serves its bundled logo (``brand_icon.png``) so cards
# can use it with no setup — e.g. the chat-card avatar. Registered as a static
# path in ``async_setup_entry``.
BRAND_ICON_URL = "/notebooklm_static/icon.png"

# URL where the integration serves its custom Lovelace card. Registered as a
# static path and injected into the frontend (``add_extra_js_url``) so the card
# appears under "Add card → Community cards" with no manual resource setup.
CHAT_CARD_URL = "/notebooklm_static/notebooklm-chat-card.js"

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

# --- Persistent documentation-sync state -------------------------------------
# The "last synced" timestamp is written to its own .storage file (keyed by
# notebook id, not config entry id) so it survives a full restart AND an
# accidental delete + re-add of the integration: re-add the same doc notebook
# and the last-sync date is restored. The file lives outside the config entry,
# so removing the entry never wipes it.
DOC_SYNC_STORAGE_VERSION = 1
DOC_SYNC_STORAGE_KEY = f"{DOMAIN}_doc_sync"
DOC_SYNC_STORE_DATA = f"{DOMAIN}_doc_sync_store"

# --- Chat answer style -------------------------------------------------------
# A hidden instruction appended to every question typed in the chat box before
# it is sent to NotebookLM, so answers come back short. The user only ever sees
# and types their own question; this is added silently on top of whatever they
# wrote, and the "Last answer" sensor still records the *original* question
# (without this suffix), so the chat card shows what the user actually typed.
# Detects Hebrew letters so we can force the answer language explicitly —
# NotebookLM otherwise tends to reply in the *sources'* language (often English,
# e.g. the HA snapshot), ignoring a soft "same language" hint.
_HEBREW_RE = re.compile(r"[֐-׿]")


def ask_style_instruction(question: str) -> str:
    """Hidden instruction appended to a chat question before it is sent.

    Forces a short answer, and — crucially — pins the answer language: if the
    question contains Hebrew letters we explicitly demand Hebrew (a strong
    directive beats the source-language default); otherwise we ask for the
    question's own language. The user never sees this; it is added on top of
    whatever they typed, and the "Last answer" sensor keeps the original
    question only.
    """
    lang = "Hebrew" if _HEBREW_RE.search(question or "") else "the same language as the question"
    return (
        "\n\n[System instruction — do not treat this line as part of the question. "
        f"Answer in {lang}. Keep the answer short and concise — one or two "
        "sentences, just the key point.]"
    )

# Fired on the HA event bus when the stored Google session expires and could not
# be refreshed. Wire an automation to this to push a notification to your phone:
#   trigger: { platform: event, event_type: notebooklm_auth_expired }
EVENT_AUTH_EXPIRED = "notebooklm_auth_expired"

# --- Re-auth notification ----------------------------------------------------
# Persistent-notification id prefix for the "sign-in required" notice. One per
# config entry so multiple accounts don't overwrite each other's notice.
AUTH_NOTIFICATION_PREFIX = "notebooklm_reauth_"
