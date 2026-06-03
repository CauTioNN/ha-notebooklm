"""Data update coordinator for the NotebookLM integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NotebookLMApi
from .const import (
    AUTH_NOTIFICATION_PREFIX,
    CONF_ACCOUNT_EMAIL,
    CONF_DEFAULT_NOTEBOOK,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_AUTH_EXPIRED,
)

if TYPE_CHECKING:
    from .documentation import DocSyncManager

_LOGGER = logging.getLogger(__name__)

# gRPC status code 16 == UNAUTHENTICATED; the upstream RPCError carries it when
# the session is dead and a refresh did not rescue the call.
_GRPC_UNAUTHENTICATED = 16


def _is_unauthenticated(err: Exception) -> bool:
    """True if an RPCError represents an expired/unauthenticated session."""
    code = getattr(err, "status_code", None)
    if code == _GRPC_UNAUTHENTICATED:
        return True
    text = str(err).lower()
    return "unauthenticated" in text or "status code 16" in text


class NotebookLMCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the NotebookLM account for notebooks and auth status."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: NotebookLMApi
    ) -> None:
        """Initialise the coordinator."""
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            config_entry=entry,
        )
        self.api = api
        # The notebook the services default to (driven by the select entity);
        # seeded from the configured default option.
        self.active_notebook_id: str | None = entry.options.get(CONF_DEFAULT_NOTEBOOK)
        # Backing state for the built-in question box / ask button / answer
        # sensor (these replace the old example helpers + script).
        self.question: str = ""
        self.last_answer: str | None = None
        self.last_answer_data: dict[str, Any] | None = None
        # Whether the "sign-in required" notice is currently raised, so we alert
        # once per failure episode rather than on every poll.
        self._auth_expired_notified = False
        # Self-documenting-HA sync manager (wired up in async_setup_entry).
        self.doc_sync: DocSyncManager | None = None

    def default_notebook(self) -> str | None:
        """Resolve the notebook services/buttons act on when none is given."""
        return self.active_notebook_id or self.config_entry.options.get(
            CONF_DEFAULT_NOTEBOOK
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the current notebook list; surface auth failures for reauth."""
        from notebooklm.exceptions import (
            AuthError,
            AuthExtractionError,
            NetworkError,
            RateLimitError,
            RPCError,
            ServerError,
        )

        try:
            notebooks = await self.api.client.notebooks.list()
        except (AuthError, AuthExtractionError) as err:
            self._notify_auth_expired(str(err))
            raise ConfigEntryAuthFailed(str(err)) from err
        except RPCError as err:
            # A dead session surfaces here (not as AuthError): the client tries
            # to refresh, Google rejects it, and the original "Unauthenticated"
            # RPC error is re-raised. Map that to reauth; anything else is a
            # genuine transient RPC failure.
            if _is_unauthenticated(err):
                self._notify_auth_expired(str(err))
                raise ConfigEntryAuthFailed(str(err)) from err
            raise UpdateFailed(str(err)) from err
        except ValueError as err:
            # The refresh path raises a bare ValueError("Authentication
            # expired. Run 'notebooklm login' ...") when the stored cookies can
            # no longer be renewed.
            self._notify_auth_expired(str(err))
            raise ConfigEntryAuthFailed(str(err)) from err
        except (NetworkError, RateLimitError, ServerError) as err:
            raise UpdateFailed(str(err)) from err

        # A healthy fetch means any earlier expiry has been resolved.
        self._clear_auth_notification()
        return {
            "auth_status": "ok",
            "notebooks": [
                {
                    "id": nb.id,
                    "title": nb.title,
                    "sources_count": nb.sources_count,
                    "is_owner": nb.is_owner,
                }
                for nb in notebooks
            ],
        }

    @property
    def _auth_notification_id(self) -> str:
        return f"{AUTH_NOTIFICATION_PREFIX}{self.config_entry.entry_id}"

    def _notify_auth_expired(self, detail: str) -> None:
        """Alert the user the first time a failure episode expires the session.

        Raises a persistent notification with a one-tap path back to the login
        add-on, and fires :data:`EVENT_AUTH_EXPIRED` so users can wire their own
        push (e.g. ``notify.mobile_app_*``) off it. HA still triggers its native
        reauth flow in parallel; this just makes the prompt impossible to miss.
        """
        if self._auth_expired_notified:
            return
        self._auth_expired_notified = True

        account = self.config_entry.data.get(CONF_ACCOUNT_EMAIL) or "your account"
        persistent_notification.async_create(
            self.hass,
            (
                f"The Google session for **{account}** has expired and could not "
                "be refreshed automatically.\n\n"
                "To reconnect:\n"
                "1. Open the **NotebookLM Login** add-on and sign in to Google "
                "again.\n"
                "2. Return to the NotebookLM integration and finish the "
                "re-authentication prompt.\n\n"
                "[Open Add-ons](/hassio/dashboard) · "
                "[Open NotebookLM](/config/integrations/integration/notebooklm)"
            ),
            title="NotebookLM: sign-in required",
            notification_id=self._auth_notification_id,
        )
        self.hass.bus.async_fire(
            EVENT_AUTH_EXPIRED,
            {
                "entry_id": self.config_entry.entry_id,
                "account": account,
                "detail": detail,
            },
        )

    def _clear_auth_notification(self) -> None:
        """Dismiss the sign-in notice once credentials are healthy again."""
        if not self._auth_expired_notified:
            return
        self._auth_expired_notified = False
        persistent_notification.async_dismiss(self.hass, self._auth_notification_id)
