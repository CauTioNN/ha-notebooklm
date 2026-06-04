"""The NotebookLM integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import persistent_notification
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant

from .api import NotebookLMApi
from .const import BRAND_ICON_URL, CHAT_CARD_URL, DOMAIN, PLATFORMS
from .coordinator import NotebookLMCoordinator
from .documentation import DocSyncManager
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

type NotebookLMConfigEntry = ConfigEntry[NotebookLMCoordinator]


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the bundled logo and the custom chat card, once per HA run.

    - The logo is served at :data:`BRAND_ICON_URL` so the chat card's avatar
      (and anything else) can point at it directly — no copying into
      ``config/www`` first.
    - The chat card JS is served at :data:`CHAT_CARD_URL` and injected into the
      frontend via ``add_extra_js_url``, so ``notebooklm-chat-card`` shows up
      under "Add card → Community cards" with no manual resource setup.
    """
    flag = f"{DOMAIN}_frontend_registered"
    if hass.data.get(flag):
        return
    hass.data[flag] = True
    base = Path(__file__).parent
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(BRAND_ICON_URL, str(base / "brand" / "icon.png"), True),
            StaticPathConfig(
                CHAT_CARD_URL, str(base / "www" / "notebooklm-chat-card.js"), True
            ),
        ]
    )
    # The ?v token busts the browser cache when the card JS changes.
    add_extra_js_url(hass, f"{CHAT_CARD_URL}?v=6")


async def async_setup_entry(hass: HomeAssistant, entry: NotebookLMConfigEntry) -> bool:
    """Set up NotebookLM from a config entry."""
    # Serve the bundled logo + custom chat card and register them with the
    # frontend (the card then appears in the card picker).
    await _async_register_frontend(hass)

    # Start each load with a clean slate: drop the previous "last answer"
    # notification so a reload/restart doesn't leave a stale answer on screen
    # (the question box and last-answer sensor reset to empty on their own).
    persistent_notification.async_dismiss(hass, f"{DOMAIN}_answer_{entry.entry_id}")

    api = NotebookLMApi(hass, entry)
    await api.async_setup()

    coordinator = NotebookLMCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    coordinator.doc_sync = DocSyncManager(hass, entry, coordinator)
    # Restore the persisted "last synced" date (survives restart and a
    # delete + re-add of the integration) before entities report their state.
    await coordinator.doc_sync.async_load()
    entry.async_on_unload(coordinator.doc_sync.async_shutdown)

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_setup_services(hass)
    # Note: the Assist intent is registered by HA's ``intent`` platform, which
    # auto-discovers ``intent.async_setup_intents`` — no manual call needed here.

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NotebookLMConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.api.async_unload()
        remaining = [
            other
            for other in hass.config_entries.async_entries(DOMAIN)
            if other.entry_id != entry.entry_id and other.state is ConfigEntryState.LOADED
        ]
        if not remaining:
            async_unload_services(hass)
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: NotebookLMConfigEntry) -> None:
    """Reload the entry only when its user-facing options change.

    The API persists rotated Google cookies back into ``entry.data`` via
    ``async_update_entry`` (see ``api._async_sync_cookies_to_entry``); that write
    also fires this update listener. Reloading on those data-only changes creates
    an endless setup/teardown loop — each unload rotates the cookies again, which
    writes again, which reloads again. So reload solely when ``entry.options``
    actually changed, and ignore cookie/data refreshes.
    """
    coordinator = entry.runtime_data
    if entry.options == coordinator.last_options:
        return
    coordinator.last_options = dict(entry.options)
    await hass.config_entries.async_reload(entry.entry_id)
