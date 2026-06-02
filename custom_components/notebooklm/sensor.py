"""Sensor platform for the NotebookLM integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NotebookLMCoordinator


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
        ]
    )


class _BaseSensor(CoordinatorEntity[NotebookLMCoordinator], SensorEntity):
    """Shared base wiring for NotebookLM sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NotebookLMCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or "NotebookLM",
            manufacturer="Google (unofficial)",
            model="NotebookLM",
        )


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
