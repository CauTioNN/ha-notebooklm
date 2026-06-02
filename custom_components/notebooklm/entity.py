"""Shared helpers for NotebookLM entities."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def notebooklm_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the shared device that groups all NotebookLM entities."""
    # Constant device name keeps entity_ids predictable (e.g.
    # ``text.notebooklm_question``) instead of embedding the account email.
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="NotebookLM",
        manufacturer="Google (unofficial)",
        model="NotebookLM",
    )
