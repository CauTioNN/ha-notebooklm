"""Text platform: the built-in 'question' box for the active notebook.

Replaces the old ``input_text`` helper — created automatically with the
integration. Pair it with the ``Ask`` button.
"""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import NotebookLMCoordinator
from .entity import notebooklm_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the question text box."""
    async_add_entities([NotebookLMQuestionText(entry.runtime_data, entry)])


class NotebookLMQuestionText(TextEntity):
    """A free-text box holding the question to ask the active notebook.

    Intentionally **not** a ``RestoreEntity``: every reload/restart should hand
    the user a clean slate, so the box starts empty rather than re-showing the
    last thing they typed.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "question"
    _attr_icon = "mdi:comment-question-outline"
    _attr_mode = TextMode.TEXT
    _attr_native_max = 255

    def __init__(self, coordinator: NotebookLMCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_question"
        self._attr_device_info = notebooklm_device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Re-render when the coordinator changes the question.

        The Ask button clears ``coordinator.question`` after sending; listening
        here makes the box empty on screen too (the button has no direct handle
        on this entity).
        """
        await super().async_added_to_hass()
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def native_value(self) -> str:
        return self._coordinator.question

    async def async_set_value(self, value: str) -> None:
        self._coordinator.question = value
        self.async_write_ha_state()
