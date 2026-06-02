"""Sensor platform for the NotebookLM integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import NotebookLMCoordinator
from .entity import notebooklm_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the NotebookLM sensors."""
    coordinator: NotebookLMCoordinator = entry.runtime_data
    async_add_entities(
        [
            NotebookLMAuthSensor(coordinator, entry),
            NotebookLMNotebooksSensor(coordinator, entry),
            NotebookLMLastAnswerSensor(coordinator, entry),
        ]
    )


class _BaseSensor(CoordinatorEntity[NotebookLMCoordinator], SensorEntity):
    """Shared base wiring for NotebookLM sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NotebookLMCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = notebooklm_device_info(entry)


class NotebookLMAuthSensor(_BaseSensor):
    """Reports whether the stored credentials are currently valid."""

    _attr_translation_key = "auth_status"
    _attr_icon = "mdi:shield-key"

    def __init__(self, coordinator: NotebookLMCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_auth_status"

    @property
    def native_value(self) -> str:
        return "ok" if self.coordinator.last_update_success else "expired"


class NotebookLMNotebooksSensor(_BaseSensor):
    """Reports the number of notebooks and their list as an attribute."""

    _attr_translation_key = "notebooks"
    _attr_icon = "mdi:notebook-multiple"
    _attr_native_unit_of_measurement = "notebooks"

    def __init__(self, coordinator: NotebookLMCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_notebooks"

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data:
            return None
        return len(self.coordinator.data.get("notebooks", []))

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        return {"notebooks": data.get("notebooks", [])}


class NotebookLMLastAnswerSensor(_BaseSensor):
    """Holds the most recent answer from the Ask button (full text in attrs)."""

    _attr_translation_key = "last_answer"
    _attr_icon = "mdi:message-text"

    def __init__(self, coordinator: NotebookLMCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_last_answer"

    @property
    def native_value(self) -> str | None:
        answer = self.coordinator.last_answer
        if not answer:
            return None
        # HA caps state strings at 255 chars; keep the full text in attributes.
        return answer[:252] + "…" if len(answer) > 255 else answer

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "answer": self.coordinator.last_answer,
            **(self.coordinator.last_answer_data or {}),
        }
