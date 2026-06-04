"""Assist (voice) intent: ask the active notebook a question.

The intent handler is registered in code, so voice works without copying a
script. Sentences still come from ``examples/custom_sentences`` (HA does not let
a custom integration inject sentences into the default agent), or from an
LLM-based Assist agent that can call this intent.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, intent

from .const import DOMAIN
from .coordinator import NotebookLMCoordinator

INTENT_ASK = "NotebookLMAsk"


def _first_loaded_coordinator(hass: HomeAssistant) -> NotebookLMCoordinator | None:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry.runtime_data
    return None


class AskNotebookIntentHandler(intent.IntentHandler):
    """Handle the NotebookLMAsk intent by querying the active notebook."""

    intent_type = INTENT_ASK
    description = "Ask the active Google NotebookLM notebook a question"
    slot_schema = {vol.Required("question"): cv.string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        from notebooklm.exceptions import NotebookLMError

        slots = self.async_validate_slots(intent_obj.slots)
        question = slots["question"]["value"]
        response = intent_obj.create_response()

        coordinator = _first_loaded_coordinator(intent_obj.hass)
        if coordinator is None:
            response.async_set_speech("NotebookLM is not set up.")
            return response

        notebook_id = coordinator.default_notebook()
        if not notebook_id:
            response.async_set_speech("No NotebookLM notebook is selected.")
            return response

        try:
            result = await coordinator.api.client.chat.ask(notebook_id, question)
        except NotebookLMError as err:
            response.async_set_speech(f"Sorry, NotebookLM returned an error: {err}")
            return response

        coordinator.last_answer = result.answer
        coordinator.last_answer_data = {
            "question": question,
            "conversation_id": result.conversation_id,
        }
        coordinator.async_update_listeners()
        response.async_set_speech(result.answer)
        return response


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Register the NotebookLM intent handler.

    This is the entry point Home Assistant's ``intent`` platform discovers and
    calls automatically for ``notebooklm/intent.py``; it must be named exactly
    ``async_setup_intents``. Registration is idempotent — re-registering simply
    replaces the existing handler with an equivalent instance.
    """
    intent.async_register(hass, AskNotebookIntentHandler())
