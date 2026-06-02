"""Thin async wrapper around the ``notebooklm-py`` client for Home Assistant.

The integration stores the Google ``storage_state.json`` payload in the config
entry. At runtime that payload is materialised to a small per-entry file inside
``<config>/.storage`` (the upstream client rotates cookies back into that file),
and a single long-lived :class:`NotebookLMClient` is kept open for the lifetime
of the entry.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import CONF_STORAGE_STATE, KEEPALIVE_INTERVAL

_LOGGER = logging.getLogger(__name__)

STORAGE_SUBDIR = ".storage"


def _import_notebooklm() -> None:
    """Import the (httpx-backed) library in an executor to avoid loop blocking."""
    import notebooklm  # noqa: F401
    import notebooklm.exceptions  # noqa: F401
    import notebooklm.types  # noqa: F401


async def async_import_client(hass: HomeAssistant) -> None:
    """Preload the notebooklm package off the event loop (idempotent)."""
    await hass.async_add_executor_job(_import_notebooklm)


class NotebookLMApi:
    """Owns one authenticated NotebookLM client bound to a config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the wrapper (no I/O happens here)."""
        self._hass = hass
        self._entry = entry
        self._ctx: Any = None
        self._client: Any = None
        self._path = hass.config.path(
            STORAGE_SUBDIR, f"notebooklm_{entry.entry_id}.json"
        )

    @property
    def client(self) -> Any:
        """Return the live ``NotebookLMClient`` (open after ``async_setup``)."""
        return self._client

    async def async_setup(self) -> None:
        """Materialise credentials and open the client, translating failures.

        Raises:
            ConfigEntryAuthFailed: credentials are missing/expired (triggers reauth).
            ConfigEntryNotReady: a transient network/server error occurred.
        """
        await async_import_client(self._hass)
        from notebooklm import NotebookLMClient
        from notebooklm.exceptions import (
            AuthError,
            AuthExtractionError,
            ConfigurationError,
            NetworkError,
            RateLimitError,
            ServerError,
        )

        await self._hass.async_add_executor_job(
            _write_storage_state, self._path, self._entry.data[CONF_STORAGE_STATE]
        )

        try:
            self._ctx = NotebookLMClient.from_storage(
                path=self._path, keepalive=KEEPALIVE_INTERVAL
            )
            self._client = await self._ctx.__aenter__()
            # Truth check: a stale cookie file parses fine but fails here.
            await self._client.notebooks.list()
        except (AuthError, AuthExtractionError, ConfigurationError, ValueError) as err:
            await self._async_close_quietly()
            raise ConfigEntryAuthFailed(str(err)) from err
        except (NetworkError, RateLimitError, ServerError, OSError) as err:
            await self._async_close_quietly()
            raise ConfigEntryNotReady(str(err)) from err

    async def async_unload(self) -> None:
        """Close the client and persist any rotated cookies back to the entry."""
        await self._async_close_quietly()
        await self._async_sync_cookies_to_entry()

    async def _async_close_quietly(self) -> None:
        if self._ctx is not None:
            try:
                await self._ctx.__aexit__(None, None, None)
            except Exception as err:  # noqa: BLE001 - best-effort teardown
                _LOGGER.debug("Error while closing NotebookLM client: %s", err)
            finally:
                self._ctx = None
                self._client = None

    async def _async_sync_cookies_to_entry(self) -> None:
        """Read the (possibly rotated) storage file back into the config entry."""
        try:
            data = await self._hass.async_add_executor_job(
                _read_storage_state, self._path
            )
        except (OSError, ValueError) as err:
            _LOGGER.debug("Could not re-read storage state for sync: %s", err)
            return
        if data and data != self._entry.data.get(CONF_STORAGE_STATE):
            self._hass.config_entries.async_update_entry(
                self._entry,
                data={**self._entry.data, CONF_STORAGE_STATE: data},
            )


def _write_storage_state(path: str, payload: Any) -> None:
    """Write the storage_state payload to ``path`` (executor context)."""
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    file.write_text(text, encoding="utf-8")


def _read_storage_state(path: str) -> Any:
    """Read and parse the storage_state file (executor context)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


async def async_validate_storage_state(
    hass: HomeAssistant, raw: str
) -> dict[str, Any]:
    """Validate a pasted storage_state JSON by opening a one-shot client.

    Returns a dict with ``storage_state`` (parsed) and ``account_email`` (or
    ``None``). Raises :class:`InvalidStorageState` / :class:`AuthFailed` /
    :class:`CannotConnect` for the config flow to map to form errors.
    """
    await async_import_client(hass)
    from notebooklm import NotebookLMClient
    from notebooklm.exceptions import (
        AuthError,
        AuthExtractionError,
        ConfigurationError,
        NetworkError,
        RateLimitError,
        ServerError,
    )

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as err:
        raise InvalidStorageState(str(err)) from err
    if not isinstance(parsed, dict) or "cookies" not in parsed:
        raise InvalidStorageState("missing 'cookies' key")

    tmp = hass.config.path(STORAGE_SUBDIR, "notebooklm_validate.json")
    await hass.async_add_executor_job(_write_storage_state, tmp, parsed)
    try:
        async with NotebookLMClient.from_storage(path=tmp) as client:
            await client.notebooks.list()
    except (AuthError, AuthExtractionError, ConfigurationError, ValueError) as err:
        raise AuthFailed(str(err)) from err
    except (NetworkError, RateLimitError, ServerError, OSError) as err:
        raise CannotConnect(str(err)) from err
    finally:
        await hass.async_add_executor_job(_remove_file, tmp)

    account_email = None
    meta = parsed.get("notebooklm")
    if isinstance(meta, dict):
        account = meta.get("account")
        if isinstance(account, dict):
            account_email = account.get("email")

    return {"storage_state": parsed, "account_email": account_email}


def _remove_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)


class InvalidStorageState(Exception):
    """The pasted storage_state JSON is malformed."""


class AuthFailed(Exception):
    """The credentials are not valid / expired."""


class CannotConnect(Exception):
    """A transient connection error occurred during validation."""
