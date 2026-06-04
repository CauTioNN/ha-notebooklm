"""Button platform: ask the active notebook the question in the text box.

Replaces the old example script — created automatically with the integration.
On press it asks the active notebook the current question, stores the answer on
the 'Last answer' sensor, raises a persistent notification, and fires
``notebooklm_artifact_ready`` is NOT used here (that's for generations).
"""

from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ask_style_instruction
from .coordinator import NotebookLMCoordinator
from .entity import notebooklm_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ask and documentation-sync buttons."""
    async_add_entities(
        [
            NotebookLMAskButton(entry.runtime_data, entry),
            NotebookLMSyncDocsButton(entry.runtime_data, entry),
        ]
    )


class NotebookLMAskButton(ButtonEntity):
    """Ask the active notebook the question currently in the text box."""

    _attr_has_entity_name = True
    _attr_translation_key = "ask"
    _attr_icon = "mdi:send"

    def __init__(self, coordinator: NotebookLMCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_ask"
        self._attr_device_info = notebooklm_device_info(entry)

    async def async_press(self) -> None:
        from notebooklm.exceptions import NotebookLMError

        question = (self._coordinator.question or "").strip()
        if not question:
            raise ServiceValidationError("Type a question in the question box first")

        notebook_id = self._coordinator.default_notebook()
        if not notebook_id:
            raise ServiceValidationError(
                "No notebook selected. Pick one in the 'Active notebook' dropdown."
            )

        # Silently append the brevity + language instruction. The user only
        # typed `question`; this suffix is never shown back to them (the sensor
        # below records the original question, not this).
        ask_text = f"{question}{ask_style_instruction(question)}"

        try:
            result = await self._coordinator.api.client.chat.ask(notebook_id, ask_text)
        except NotebookLMError as err:
            raise HomeAssistantError(f"NotebookLM error: {err}") from err

        self._coordinator.last_answer = result.answer
        self._coordinator.last_answer_data = {
            "question": question,
            "conversation_id": result.conversation_id,
            "references": [
                {
                    "source_id": getattr(ref, "source_id", None),
                    "cited_text": getattr(ref, "cited_text", None),
                }
                for ref in getattr(result, "references", []) or []
            ],
        }
        # Empty the question box once the question has been asked, so it never
        # lingers (and never leaks into the doc export). The text entity listens
        # to the coordinator, so this clears it on screen too.
        self._coordinator.question = ""
        # Refresh the "Last answer" sensor (a coordinator entity). The answer
        # shows in the chat card and the sensor — we deliberately do NOT raise a
        # persistent notification per answer (it was noisy on every question).
        self._coordinator.async_update_listeners()


class NotebookLMSyncDocsButton(ButtonEntity):
    """Export the HA snapshot and sync it into the documentation notebook now."""

    _attr_has_entity_name = True
    _attr_translation_key = "sync_documentation"
    _attr_icon = "mdi:home-sync"

    def __init__(self, coordinator: NotebookLMCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_sync_documentation"
        self._attr_device_info = notebooklm_device_info(entry)

    async def async_press(self) -> None:
        manager = self._coordinator.doc_sync
        if manager is None:
            raise HomeAssistantError("Documentation sync is not ready yet")

        result = await manager.async_sync()
        persistent_notification.async_create(
            self._coordinator.hass,
            (
                f"Synced {result['sources_written']} section(s) "
                f"({', '.join(result['categories'])}) into your documentation notebook."
            ),
            title="NotebookLM: documentation synced",
            notification_id=f"{DOMAIN}_docsync_{self._coordinator.config_entry.entry_id}",
        )
