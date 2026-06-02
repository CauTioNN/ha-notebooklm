"""Home Assistant services (actions) for NotebookLM.

Every service accepts an optional ``notebook_id`` that falls back to the
default notebook configured in the integration options, so automations can stay
terse. Long-running generation services start the job, fire a
``notebook_id`` event when it finishes, and return the ``task_id`` immediately
(pass ``wait: true`` to block until completion and receive the download URL).
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_DEFAULT_NOTEBOOK,
    DOMAIN,
    EVENT_ARTIFACT_FAILED,
    EVENT_ARTIFACT_READY,
    EVENT_SOURCE_ADDED,
)
from .coordinator import NotebookLMCoordinator

_LOGGER = logging.getLogger(__name__)

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_NOTEBOOK_ID = "notebook_id"

DEFAULT_GENERATION_TIMEOUT = 1800  # seconds (videos can take a while)

# kind -> (client method name, artifact-type label, {service_field: (kwarg, EnumName)})
_GENERATE_SPECS: dict[str, tuple[str, str, dict[str, tuple[str, str]]]] = {
    "generate_audio": (
        "generate_audio",
        "audio",
        {"format": ("audio_format", "AudioFormat"), "length": ("audio_length", "AudioLength")},
    ),
    "generate_video": (
        "generate_video",
        "video",
        {"format": ("video_format", "VideoFormat"), "style": ("video_style", "VideoStyle")},
    ),
    "generate_quiz": (
        "generate_quiz",
        "quiz",
        {"difficulty": ("difficulty", "QuizDifficulty"), "quantity": ("quantity", "QuizQuantity")},
    ),
    "generate_flashcards": (
        "generate_flashcards",
        "flashcards",
        {"difficulty": ("difficulty", "QuizDifficulty"), "quantity": ("quantity", "QuizQuantity")},
    ),
    "generate_report": (
        "generate_report",
        "report",
        {"format": ("report_format", "ReportFormat")},
    ),
    "generate_slide_deck": (
        "generate_slide_deck",
        "slide_deck",
        {"format": ("slide_format", "SlideDeckFormat"), "length": ("slide_length", "SlideDeckLength")},
    ),
    "generate_infographic": (
        "generate_infographic",
        "infographic",
        {
            "orientation": ("orientation", "InfographicOrientation"),
            "detail": ("detail_level", "InfographicDetail"),
            "style": ("style", "InfographicStyle"),
        },
    ),
    "generate_data_table": ("generate_data_table", "data_table", {}),
}

_DOWNLOAD_METHODS = {
    "audio": "download_audio",
    "video": "download_video",
    "report": "download_report",
    "quiz": "download_quiz",
    "flashcards": "download_flashcards",
    "slide_deck": "download_slide_deck",
    "infographic": "download_infographic",
    "mind_map": "download_mind_map",
    "data_table": "download_data_table",
}

_BASE = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}
_NB = {**_BASE, vol.Optional(ATTR_NOTEBOOK_ID): cv.string}


# Friendly option -> actual enum member name, where they differ from the
# upper-snake of the option string.
_ENUM_ALIASES: dict[str, dict[str, str]] = {
    "QuizQuantity": {"MORE": "STANDARD"},  # API treats MORE as STANDARD
    "SlideDeckFormat": {"DETAILED": "DETAILED_DECK", "PRESENTER": "PRESENTER_SLIDES"},
}


def _enum(enum_name: str, value: str) -> Any:
    """Map an automation-friendly string (e.g. ``deep-dive``) to a library enum."""
    from notebooklm import types as nb_types

    enum_cls = getattr(nb_types, enum_name)
    key = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    key = _ENUM_ALIASES.get(enum_name, {}).get(key, key)
    try:
        return enum_cls[key]
    except KeyError as err:
        valid = ", ".join(m.name.lower() for m in enum_cls)
        raise ServiceValidationError(
            f"Invalid value '{value}'. Valid options: {valid}"
        ) from err


def _resolve_coordinator(hass: HomeAssistant, call: ServiceCall) -> NotebookLMCoordinator:
    """Pick the target config entry's coordinator."""
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id:
        for entry in entries:
            if entry.entry_id == entry_id:
                return entry.runtime_data
        raise ServiceValidationError(f"NotebookLM entry '{entry_id}' not found or not loaded")
    if not entries:
        raise ServiceValidationError("No loaded NotebookLM integration found")
    if len(entries) > 1:
        raise ServiceValidationError(
            "Multiple NotebookLM accounts configured; set 'config_entry_id'"
        )
    return entries[0].runtime_data


def _resolve_notebook(coordinator: NotebookLMCoordinator, call: ServiceCall) -> str:
    notebook_id = (
        call.data.get(ATTR_NOTEBOOK_ID)
        or coordinator.active_notebook_id
        or coordinator.config_entry.options.get(CONF_DEFAULT_NOTEBOOK)
    )
    if not notebook_id:
        raise ServiceValidationError(
            "No notebook selected. Pick one in the 'Active notebook' dropdown, "
            "set a default in the integration options, or pass 'notebook_id'."
        )
    return notebook_id


def _wrap_errors(func):
    """Translate library exceptions into HomeAssistantError for clean UX."""

    async def wrapper(call: ServiceCall) -> ServiceResponse:
        from notebooklm.exceptions import NotebookLMError

        try:
            return await func(call)
        except (ServiceValidationError, HomeAssistantError):
            raise
        except NotebookLMError as err:
            raise HomeAssistantError(f"NotebookLM error: {err}") from err

    return wrapper


def async_setup_services(hass: HomeAssistant) -> None:
    """Register all NotebookLM services (idempotent)."""
    if hass.services.has_service(DOMAIN, "ask"):
        return

    # ------------------------------------------------------------------ notebooks
    @_wrap_errors
    async def create_notebook(call: ServiceCall) -> ServiceResponse:
        coordinator = _resolve_coordinator(hass, call)
        nb = await coordinator.api.client.notebooks.create(call.data["title"])
        await coordinator.async_request_refresh()
        return {"notebook_id": nb.id, "title": nb.title}

    @_wrap_errors
    async def delete_notebook(call: ServiceCall) -> ServiceResponse:
        coordinator = _resolve_coordinator(hass, call)
        notebook_id = _resolve_notebook(coordinator, call)
        await coordinator.api.client.notebooks.delete(notebook_id)
        await coordinator.async_request_refresh()
        return None

    @_wrap_errors
    async def list_notebooks(call: ServiceCall) -> ServiceResponse:
        coordinator = _resolve_coordinator(hass, call)
        notebooks = await coordinator.api.client.notebooks.list()
        return {
            "notebooks": [
                {"id": nb.id, "title": nb.title, "sources_count": nb.sources_count}
                for nb in notebooks
            ]
        }

    # -------------------------------------------------------------------- sources
    @_wrap_errors
    async def add_url(call: ServiceCall) -> ServiceResponse:
        coordinator = _resolve_coordinator(hass, call)
        notebook_id = _resolve_notebook(coordinator, call)
        source = await coordinator.api.client.sources.add_url(
            notebook_id, call.data["url"], wait=call.data.get("wait", False)
        )
        hass.bus.async_fire(
            EVENT_SOURCE_ADDED,
            {"notebook_id": notebook_id, "source_id": source.id, "title": source.title},
        )
        return {"source_id": source.id, "title": source.title}

    @_wrap_errors
    async def add_text(call: ServiceCall) -> ServiceResponse:
        coordinator = _resolve_coordinator(hass, call)
        notebook_id = _resolve_notebook(coordinator, call)
        source = await coordinator.api.client.sources.add_text(
            notebook_id, call.data["title"], call.data["content"]
        )
        return {"source_id": source.id}

    @_wrap_errors
    async def add_file(call: ServiceCall) -> ServiceResponse:
        coordinator = _resolve_coordinator(hass, call)
        notebook_id = _resolve_notebook(coordinator, call)
        file_path = call.data["file_path"]
        if not hass.config.is_allowed_path(file_path):
            raise ServiceValidationError(f"Path '{file_path}' is not allowed")
        source = await coordinator.api.client.sources.add_file(notebook_id, file_path)
        return {"source_id": source.id}

    @_wrap_errors
    async def add_research(call: ServiceCall) -> ServiceResponse:
        coordinator = _resolve_coordinator(hass, call)
        notebook_id = _resolve_notebook(coordinator, call)
        result = await coordinator.api.client.research.start(
            notebook_id,
            call.data["query"],
            source=call.data.get("source", "web"),
            mode=call.data.get("mode", "fast"),
        )
        return {"task_id": getattr(result, "task_id", None)}

    # ----------------------------------------------------------------------- chat
    @_wrap_errors
    async def ask(call: ServiceCall) -> ServiceResponse:
        coordinator = _resolve_coordinator(hass, call)
        notebook_id = _resolve_notebook(coordinator, call)
        result = await coordinator.api.client.chat.ask(
            notebook_id,
            call.data["question"],
            conversation_id=call.data.get("conversation_id"),
        )
        return {
            "answer": result.answer,
            "conversation_id": result.conversation_id,
            "references": [
                {"source_id": getattr(r, "source_id", None), "cited_text": getattr(r, "cited_text", None)}
                for r in getattr(result, "references", []) or []
            ],
        }

    # ------------------------------------------------------------------- generate
    def _make_generate(kind: str):
        method_name, artifact_type, opt_map = _GENERATE_SPECS[kind]

        @_wrap_errors
        async def handler(call: ServiceCall) -> ServiceResponse:
            coordinator = _resolve_coordinator(hass, call)
            notebook_id = _resolve_notebook(coordinator, call)
            client = coordinator.api.client

            kwargs: dict[str, Any] = {}
            if (instructions := call.data.get("instructions")) is not None:
                kwargs["instructions"] = instructions
            if (language := call.data.get("language")) is not None:
                kwargs["language"] = language
            for field, (arg_name, enum_name) in opt_map.items():
                if (value := call.data.get(field)) is not None:
                    kwargs[arg_name] = _enum(enum_name, value)

            status = await getattr(client.artifacts, method_name)(notebook_id, **kwargs)
            task_id = status.task_id

            if call.data.get("wait", False):
                final = await client.artifacts.wait_for_completion(
                    notebook_id, task_id, timeout=DEFAULT_GENERATION_TIMEOUT
                )
                _fire_ready(hass, notebook_id, artifact_type, final)
                return {"task_id": task_id, "status": final.status, "url": final.url}

            hass.async_create_background_task(
                _await_and_fire(hass, client, notebook_id, artifact_type, task_id),
                name=f"notebooklm_{kind}_{task_id}",
            )
            return {"task_id": task_id, "status": status.status}

        return handler

    @_wrap_errors
    async def generate_mind_map(call: ServiceCall) -> ServiceResponse:
        coordinator = _resolve_coordinator(hass, call)
        notebook_id = _resolve_notebook(coordinator, call)
        kwargs: dict[str, Any] = {}
        if (instructions := call.data.get("instructions")) is not None:
            kwargs["instructions"] = instructions
        if (language := call.data.get("language")) is not None:
            kwargs["language"] = language
        result = await coordinator.api.client.artifacts.generate_mind_map(
            notebook_id, **kwargs
        )
        note_id = getattr(result, "note_id", None)
        hass.bus.async_fire(
            EVENT_ARTIFACT_READY,
            {
                "notebook_id": notebook_id,
                "artifact_type": "mind_map",
                "artifact_id": note_id,
                "url": None,
            },
        )
        return {"note_id": note_id}

    # ------------------------------------------------------------------- download
    @_wrap_errors
    async def download(call: ServiceCall) -> ServiceResponse:
        coordinator = _resolve_coordinator(hass, call)
        notebook_id = _resolve_notebook(coordinator, call)
        artifact_type = call.data["artifact_type"]
        output_path = call.data["output_path"]
        if not hass.config.is_allowed_path(output_path):
            raise ServiceValidationError(f"Path '{output_path}' is not allowed")
        method = getattr(coordinator.api.client.artifacts, _DOWNLOAD_METHODS[artifact_type])
        kwargs: dict[str, Any] = {}
        if artifact_id := call.data.get("artifact_id"):
            kwargs["artifact_id"] = artifact_id
        if output_format := call.data.get("format"):
            kwargs["output_format"] = output_format
        path = await method(notebook_id, output_path, **kwargs)
        return {"path": path}

    # ------------------------------------------------------------------ register
    hass.services.async_register(
        DOMAIN, "create_notebook", create_notebook,
        schema=vol.Schema({**_BASE, vol.Required("title"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, "delete_notebook", delete_notebook, schema=vol.Schema(_NB)
    )
    hass.services.async_register(
        DOMAIN, "list_notebooks", list_notebooks, schema=vol.Schema(_BASE),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "add_url", add_url,
        schema=vol.Schema({**_NB, vol.Required("url"): cv.string, vol.Optional("wait"): cv.boolean}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, "add_text", add_text,
        schema=vol.Schema({**_NB, vol.Required("title"): cv.string, vol.Required("content"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, "add_file", add_file,
        schema=vol.Schema({**_NB, vol.Required("file_path"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, "add_research", add_research,
        schema=vol.Schema(
            {
                **_NB,
                vol.Required("query"): cv.string,
                vol.Optional("source"): vol.In(["web", "drive"]),
                vol.Optional("mode"): vol.In(["fast", "deep"]),
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, "ask", ask,
        schema=vol.Schema(
            {**_NB, vol.Required("question"): cv.string, vol.Optional("conversation_id"): cv.string}
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )

    _gen_schema = vol.Schema(
        {
            **_NB,
            vol.Optional("instructions"): cv.string,
            vol.Optional("language"): cv.string,
            vol.Optional("wait"): cv.boolean,
            vol.Optional("format"): cv.string,
            vol.Optional("length"): cv.string,
            vol.Optional("style"): cv.string,
            vol.Optional("difficulty"): cv.string,
            vol.Optional("quantity"): cv.string,
            vol.Optional("orientation"): cv.string,
            vol.Optional("detail"): cv.string,
        }
    )
    for kind in _GENERATE_SPECS:
        hass.services.async_register(
            DOMAIN, kind, _make_generate(kind), schema=_gen_schema,
            supports_response=SupportsResponse.OPTIONAL,
        )
    hass.services.async_register(
        DOMAIN, "generate_mind_map", generate_mind_map,
        schema=vol.Schema(
            {**_NB, vol.Optional("instructions"): cv.string, vol.Optional("language"): cv.string}
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, "download", download,
        schema=vol.Schema(
            {
                **_NB,
                vol.Required("artifact_type"): vol.In(sorted(_DOWNLOAD_METHODS)),
                vol.Required("output_path"): cv.string,
                vol.Optional("artifact_id"): cv.string,
                vol.Optional("format"): cv.string,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """Remove all NotebookLM services."""
    services = [
        "create_notebook", "delete_notebook", "list_notebooks", "add_url",
        "add_text", "add_file", "add_research", "ask", "generate_mind_map",
        "download", *_GENERATE_SPECS,
    ]
    for service in services:
        hass.services.async_remove(DOMAIN, service)


def _fire_ready(hass: HomeAssistant, notebook_id: str, artifact_type: str, status: Any) -> None:
    event = EVENT_ARTIFACT_READY if status.status == "completed" else EVENT_ARTIFACT_FAILED
    hass.bus.async_fire(
        event,
        {
            "notebook_id": notebook_id,
            "artifact_type": artifact_type,
            "artifact_id": status.task_id,
            "status": status.status,
            "url": getattr(status, "url", None),
            "error": getattr(status, "error", None),
        },
    )


async def _await_and_fire(
    hass: HomeAssistant, client: Any, notebook_id: str, artifact_type: str, task_id: str
) -> None:
    """Background-wait for a generation task and fire the completion event."""
    from notebooklm.exceptions import NotebookLMError

    try:
        status = await client.artifacts.wait_for_completion(
            notebook_id, task_id, timeout=DEFAULT_GENERATION_TIMEOUT
        )
        _fire_ready(hass, notebook_id, artifact_type, status)
    except NotebookLMError as err:
        _LOGGER.warning("NotebookLM %s generation failed: %s", artifact_type, err)
        hass.bus.async_fire(
            EVENT_ARTIFACT_FAILED,
            {
                "notebook_id": notebook_id,
                "artifact_type": artifact_type,
                "artifact_id": task_id,
                "error": str(err),
            },
        )
