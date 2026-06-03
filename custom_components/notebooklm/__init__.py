"""The NotebookLM integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant

from .api import NotebookLMApi
from .const import DOMAIN, PLATFORMS
from .coordinator import NotebookLMCoordinator
from .documentation import DocSyncManager
from .intent import async_register_intents
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

type NotebookLMConfigEntry = ConfigEntry[NotebookLMCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: NotebookLMConfigEntry) -> bool:
    """Set up NotebookLM from a config entry."""
    api = NotebookLMApi(hass, entry)
    await api.async_setup()

    coordinator = NotebookLMCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    coordinator.doc_sync = DocSyncManager(hass, entry, coordinator)
    entry.async_on_unload(coordinator.doc_sync.async_shutdown)

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_setup_services(hass)
    async_register_intents(hass)

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
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
