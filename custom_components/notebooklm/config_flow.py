"""Config and options flow for the NotebookLM integration."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    AuthFailed,
    CannotConnect,
    InvalidStorageState,
    async_validate_storage_state,
)
from .const import (
    ADDON_RESULT_FILE,
    AUTH_METHOD_GOOGLE,
    AUTH_METHOD_MANUAL,
    CONF_ACCOUNT_EMAIL,
    CONF_DEFAULT_NOTEBOOK,
    CONF_DOC_CATEGORIES,
    CONF_DOC_NOTEBOOK,
    CONF_DOC_SCRUB,
    CONF_SCAN_INTERVAL,
    CONF_STORAGE_STATE,
    DEFAULT_DOC_CATEGORIES,
    DEFAULT_SCAN_INTERVAL,
    DOC_CATEGORIES,
    DOC_CATEGORY_TITLES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_STORAGE_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.TEXT, multiline=True)
)


class NotebookLMConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the NotebookLM config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Entry point: choose how to authenticate."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[AUTH_METHOD_GOOGLE, AUTH_METHOD_MANUAL],
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Authenticate by pasting a storage_state.json payload."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                validated = await async_validate_storage_state(
                    self.hass, user_input[CONF_STORAGE_STATE]
                )
            except InvalidStorageState:
                errors["base"] = "invalid_storage_state"
            except AuthFailed:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                return await self._async_finish(validated)

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({vol.Required(CONF_STORAGE_STATE): _STORAGE_SELECTOR}),
            errors=errors,
        )

    async def async_step_google(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Authenticate via the companion add-on (Google login inside HA).

        The add-on performs the interactive Google login and writes the
        captured credentials to ``<config>/.notebooklm_login_result.json``.
        After completing login in the add-on UI, the user confirms here and we
        read that file back.
        """
        errors: dict[str, str] = {}
        result_path = self.hass.config.path(ADDON_RESULT_FILE)

        if user_input is not None:
            raw = await self.hass.async_add_executor_job(_read_addon_result, result_path)
            if raw is None:
                errors["base"] = "addon_result_missing"
            else:
                try:
                    validated = await async_validate_storage_state(self.hass, raw)
                except InvalidStorageState:
                    errors["base"] = "invalid_storage_state"
                except AuthFailed:
                    errors["base"] = "invalid_auth"
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                else:
                    await self.hass.async_add_executor_job(_remove, result_path)
                    return await self._async_finish(validated)

        return self.async_show_form(
            step_id="google",
            data_schema=vol.Schema({}),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication when credentials expire."""
        return await self.async_step_user()

    async def _async_finish(self, validated: dict[str, Any]) -> ConfigFlowResult:
        """Create the entry (or update it during reauth)."""
        account_email = validated.get("account_email")
        data = {
            CONF_STORAGE_STATE: validated["storage_state"],
            CONF_ACCOUNT_EMAIL: account_email,
        }

        if account_email:
            await self.async_set_unique_id(account_email)

        if self.source == SOURCE_REAUTH:
            reauth_entry = self._get_reauth_entry()
            if account_email:
                self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(reauth_entry, data=data)

        if account_email:
            self._abort_if_unique_id_configured()
        title = account_email or "NotebookLM"
        return self.async_create_entry(title=title, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return NotebookLMOptionsFlow()


class NotebookLMOptionsFlow(OptionsFlow):
    """Handle NotebookLM options (general settings + documentation sync)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Top-level options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "documentation"],
        )

    def _notebook_choices(self) -> list[SelectOptionDict]:
        coordinator = getattr(self.config_entry, "runtime_data", None)
        notebooks = (coordinator.data or {}).get("notebooks", []) if coordinator else []
        return [
            SelectOptionDict(value=nb["id"], label=f"{nb['title']} ({nb['id'][:8]})")
            for nb in notebooks
        ]

    def _save(self, updates: dict[str, Any]) -> ConfigFlowResult:
        """Persist option updates, preserving the keys other steps own."""
        return self.async_create_entry(
            data={**self.config_entry.options, **updates}
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Default notebook + poll interval."""
        if user_input is not None:
            return self._save(user_input)

        options = self._notebook_choices()
        if options:
            notebook_selector: Any = SelectSelector(
                SelectSelectorConfig(
                    options=options, mode=SelectSelectorMode.DROPDOWN, custom_value=True
                )
            )
        else:
            notebook_selector = cv.string

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DEFAULT_NOTEBOOK,
                    default=current.get(CONF_DEFAULT_NOTEBOOK, vol.UNDEFINED),
                ): notebook_selector,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=60, max=86400)),
            }
        )
        return self.async_show_form(step_id="general", data_schema=schema)

    async def async_step_documentation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the documentation notebook + which HA sections to export."""
        errors: dict[str, str] = {}
        current = self.config_entry.options

        if user_input is not None:
            notebook_id = user_input.get(CONF_DOC_NOTEBOOK)
            new_title = (user_input.get("create_notebook") or "").strip()
            if new_title:
                coordinator = getattr(self.config_entry, "runtime_data", None)
                if coordinator is None:
                    errors["base"] = "not_loaded"
                else:
                    try:
                        nb = await coordinator.api.client.notebooks.create(new_title)
                        notebook_id = nb.id
                        await coordinator.async_request_refresh()
                    except Exception:  # noqa: BLE001 - surface as a form error
                        errors["base"] = "create_failed"
            if not errors:
                return self._save(
                    {
                        CONF_DOC_NOTEBOOK: notebook_id,
                        CONF_DOC_CATEGORIES: user_input.get(
                            CONF_DOC_CATEGORIES, DEFAULT_DOC_CATEGORIES
                        ),
                        CONF_DOC_SCRUB: user_input.get(CONF_DOC_SCRUB, True),
                    }
                )

        notebook_choices = self._notebook_choices()
        category_selector = SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=cat, label=DOC_CATEGORY_TITLES[cat])
                    for cat in DOC_CATEGORIES
                ],
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        )
        schema_dict: dict[Any, Any] = {}
        if notebook_choices:
            schema_dict[
                vol.Optional(
                    CONF_DOC_NOTEBOOK,
                    default=current.get(CONF_DOC_NOTEBOOK, vol.UNDEFINED),
                )
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=notebook_choices,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            )
        else:
            schema_dict[
                vol.Optional(
                    CONF_DOC_NOTEBOOK,
                    default=current.get(CONF_DOC_NOTEBOOK, vol.UNDEFINED),
                )
            ] = cv.string
        schema_dict[vol.Optional("create_notebook")] = cv.string
        schema_dict[
            vol.Optional(
                CONF_DOC_CATEGORIES,
                default=current.get(CONF_DOC_CATEGORIES, DEFAULT_DOC_CATEGORIES),
            )
        ] = category_selector
        schema_dict[
            vol.Optional(CONF_DOC_SCRUB, default=current.get(CONF_DOC_SCRUB, True))
        ] = BooleanSelector()

        return self.async_show_form(
            step_id="documentation",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )


def _read_addon_result(path: str) -> str | None:
    """Read the add-on's login result file, returning its raw text or None."""
    file = Path(path)
    if not file.exists():
        return None
    try:
        text = file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    # Accept either a bare storage_state JSON or a wrapper {"storage_state": {...}}.
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and "cookies" not in parsed and "storage_state" in parsed:
        return json.dumps(parsed["storage_state"])
    return text


def _remove(path: str) -> None:
    Path(path).unlink(missing_ok=True)
