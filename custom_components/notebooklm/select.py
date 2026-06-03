"""Select platform: pick the active notebook from a dropdown.

This is what lets every service default to a notebook **without typing an ID** —
the user picks a notebook here and `coordinator.active_notebook_id` follows.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_DOC_SCHEDULE, DOC_SCHEDULES
from .coordinator import NotebookLMCoordinator
from .entity import notebooklm_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the active-notebook and documentation-schedule selectors."""
    coordinator: NotebookLMCoordinator = entry.runtime_data
    async_add_entities(
        [
            NotebookLMActiveNotebookSelect(coordinator, entry),
            NotebookLMDocScheduleSelect(coordinator, entry),
        ]
    )


class NotebookLMActiveNotebookSelect(
    CoordinatorEntity[NotebookLMCoordinator], SelectEntity, RestoreEntity
):
    """Dropdown of the account's notebooks; selection drives service defaults."""

    _attr_has_entity_name = True
    _attr_translation_key = "active_notebook"
    _attr_icon = "mdi:notebook-check"

    def __init__(self, coordinator: NotebookLMCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_active_notebook"
        self._attr_device_info = notebooklm_device_info(entry)

    def _notebooks(self) -> list[dict]:
        return (self.coordinator.data or {}).get("notebooks", [])

    @property
    def options(self) -> list[str]:
        return [nb["title"] for nb in self._notebooks()]

    @property
    def current_option(self) -> str | None:
        active = self.coordinator.active_notebook_id
        for nb in self._notebooks():
            if nb["id"] == active:
                return nb["title"]
        return None

    async def async_select_option(self, option: str) -> None:
        for nb in self._notebooks():
            if nb["title"] == option:
                self.coordinator.active_notebook_id = nb["id"]
                self.async_write_ha_state()
                return

    async def async_added_to_hass(self) -> None:
        """Restore the previously selected notebook after a restart."""
        await super().async_added_to_hass()
        if self.coordinator.active_notebook_id is not None:
            return
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in (None, "unknown", "unavailable"):
            return
        for nb in self._notebooks():
            if nb["title"] == last_state.state:
                self.coordinator.active_notebook_id = nb["id"]
                break

    @callback
    def _handle_coordinator_update(self) -> None:
        # If the selected notebook vanished, fall back to the first available.
        active = self.coordinator.active_notebook_id
        ids = [nb["id"] for nb in self._notebooks()]
        if active not in ids:
            self.coordinator.active_notebook_id = ids[0] if ids else None
        super()._handle_coordinator_update()


class NotebookLMDocScheduleSelect(SelectEntity, RestoreEntity):
    """Picks how often the HA documentation snapshot is synced to NotebookLM."""

    _attr_has_entity_name = True
    _attr_translation_key = "doc_schedule"
    _attr_icon = "mdi:calendar-sync"
    _attr_entity_category = None

    def __init__(self, coordinator: NotebookLMCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_doc_schedule"
        self._attr_device_info = notebooklm_device_info(entry)
        self._attr_options = list(DOC_SCHEDULES)

    @property
    def current_option(self) -> str:
        manager = self._coordinator.doc_sync
        return manager.schedule if manager else DEFAULT_DOC_SCHEDULE

    async def async_select_option(self, option: str) -> None:
        if (manager := self._coordinator.doc_sync) is not None:
            manager.set_schedule(option)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the cadence chosen before the last restart and apply it."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        manager = self._coordinator.doc_sync
        if (
            manager is not None
            and last_state is not None
            and last_state.state in DOC_SCHEDULES
        ):
            manager.set_schedule(last_state.state)
