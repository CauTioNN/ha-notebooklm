"""Self-documenting Home Assistant → NotebookLM.

This module exports a **scrubbed Markdown snapshot** of the running Home
Assistant instance (areas, entities, automations, scripts, scenes, helpers,
integrations) and syncs it into a NotebookLM notebook as text sources. The
point is grounded Q&A: once your own config lives in a notebook, the existing
``notebooklm.ask`` service answers questions about *your* home with citations.

No AI runs here — the export is purely mechanical (it reads HA's in-memory
registries and states). NotebookLM itself is the AI; this just feeds it.

Update-without-duplicates contract
-----------------------------------
NotebookLM has no in-place content update for a text source, so a naive re-sync
would pile up duplicates. Instead, each section is written as a source titled
``"<DOC_SOURCE_PREFIX> <Section>"`` (e.g. ``"🏠 HA · Automations"``). Before
re-adding a section, :meth:`DocSyncManager.async_sync` lists the notebook's
sources and deletes any whose title matches that section (including split
``"... (part n/m)"`` variants). Result: exactly one current source per section,
never an accumulating pile.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime, timedelta
import logging
import re
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_DOC_CATEGORIES,
    DEFAULT_DOC_SCHEDULE,
    DOC_CATEGORY_TITLES,
    DOC_MAX_SOURCE_CHARS,
    DOC_SCHEDULES,
    DOC_SOURCE_PREFIX,
    CONF_DOC_CATEGORIES,
    CONF_DOC_NOTEBOOK,
    CONF_DOC_SCRUB,
    EVENT_DOC_SYNCED,
)

if TYPE_CHECKING:
    from .coordinator import NotebookLMCoordinator

_LOGGER = logging.getLogger(__name__)

# Helper domains grouped under the "helpers" section.
_HELPER_DOMAINS = (
    "input_boolean",
    "input_number",
    "input_text",
    "input_select",
    "input_datetime",
    "input_button",
    "counter",
    "timer",
    "schedule",
)


# =============================================================================
# Secret scrubbing
# =============================================================================
# Keys whose VALUE is always redacted (privacy floor — cannot be disabled). The
# config is uploaded to Google's cloud, so coordinates, tokens and passwords
# must never leave the building.
_SENSITIVE_KEY_TOKENS = (
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "client_secret",
    "credential",
    "latitude",
    "longitude",
    "gps_accuracy",
    "cookie",
    "authorization",
    "private_key",
    "psk",
    "ssid",
    "passcode",
    "bearer",
)

_REDACTED = "‹redacted›"

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# Long opaque token (API key / JWT): 32+ chars containing both a letter and a
# digit, so ordinary words and entity_ids are left alone.
_TOKEN_RE = re.compile(
    r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,}\b"
)


def _is_sensitive_key(key: str) -> bool:
    lowered = str(key).lower()
    return any(token in lowered for token in _SENSITIVE_KEY_TOKENS)


def _scrub_text(text: str) -> str:
    """Redact emails, IPs and long opaque tokens from a free-text value."""
    text = _EMAIL_RE.sub(_REDACTED, text)
    text = _IPV4_RE.sub(_REDACTED, text)
    return _TOKEN_RE.sub(_REDACTED, text)


def _scrub_value(value: Any, *, deep: bool) -> Any:
    if isinstance(value, str):
        return _scrub_text(value) if deep else value
    if isinstance(value, (list, tuple)):
        return [_scrub_value(item, deep=deep) for item in value]
    if isinstance(value, dict):
        return {k: _scrub_value(v, deep=deep) for k, v in value.items()}
    return value


def _scrub_attrs(attrs: Mapping[str, Any], *, deep: bool) -> dict[str, Any]:
    """Return a copy of ``attrs`` with sensitive keys/values removed.

    ``deep`` toggles the value-regex pass (emails/IPs/tokens). Sensitive *keys*
    (coordinates, passwords, tokens) are always redacted regardless.
    """
    out: dict[str, Any] = {}
    for key, value in attrs.items():
        if _is_sensitive_key(key):
            out[key] = _REDACTED
        else:
            out[key] = _scrub_value(value, deep=deep)
    return out


# =============================================================================
# Markdown helpers
# =============================================================================
def _fmt(value: Any, limit: int = 200) -> str:
    """Render a value as a single-line table cell, truncated."""
    text = str(value).replace("\n", " ").replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    if not rows:
        return ["_None._", ""]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(_fmt(c) for c in row) + " |" for row in rows)
    lines.append("")
    return lines


def _friendly(state: State | None, entity_id: str, reg_name: str | None) -> str:
    if state is not None:
        name = state.attributes.get("friendly_name")
        if name:
            return str(name)
    return reg_name or entity_id


def _attrs_summary(state: State | None, *, deep: bool, skip: tuple[str, ...] = ()) -> str:
    """One-line ``key=value; …`` summary of a state's attributes (scrubbed)."""
    if state is None:
        return ""
    attrs = _scrub_attrs(state.attributes, deep=deep)
    parts = [
        f"{key}={_fmt(value, 120)}"
        for key, value in attrs.items()
        if key not in skip and key != "friendly_name"
    ]
    return _fmt("; ".join(parts), 600)


# =============================================================================
# Section builders — each returns the Markdown body for one category.
# =============================================================================
def _states_by_domain(hass: HomeAssistant, domain: str) -> list[State]:
    return sorted(
        (s for s in hass.states.async_all() if s.domain == domain),
        key=lambda s: s.entity_id,
    )


def _build_overview(hass: HomeAssistant, deep: bool) -> str:
    cfg = hass.config
    states = hass.states.async_all()
    domains: dict[str, int] = {}
    for state in states:
        domains[state.domain] = domains.get(state.domain, 0) + 1

    area_reg = ar.async_get(hass)
    dev_reg = dr.async_get(hass)

    units = getattr(cfg.units, "_name", None) or type(cfg.units).__name__
    lines = [
        "# Home Assistant — Overview",
        "",
        f"- **Home Assistant version:** {HA_VERSION}",
        f"- **Location name:** {cfg.location_name}",
        f"- **Time zone:** {cfg.time_zone}",
        f"- **Unit system:** {units}",
    ]
    if cfg.currency:
        lines.append(f"- **Currency:** {cfg.currency}")
    if cfg.country:
        lines.append(f"- **Country:** {cfg.country}")
    lines += [
        f"- **Total entities:** {len(states)}",
        f"- **Areas:** {len(area_reg.async_list_areas())}",
        f"- **Devices:** {len(dev_reg.devices)}",
        "",
        "## Entities per domain",
        "",
    ]
    lines += _table(
        ["Domain", "Count"],
        [[d, domains[d]] for d in sorted(domains)],
    )
    return "\n".join(lines)


def _build_areas(hass: HomeAssistant, deep: bool) -> str:
    area_reg = ar.async_get(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    # Map devices and entities to their effective area.
    device_area = {dev.id: dev.area_id for dev in dev_reg.devices.values()}
    entities_by_area: dict[str | None, list[Any]] = {}
    for ent in ent_reg.entities.values():
        area_id = ent.area_id or device_area.get(ent.device_id)
        entities_by_area.setdefault(area_id, []).append(ent)
    devices_by_area: dict[str | None, list[Any]] = {}
    for dev in dev_reg.devices.values():
        devices_by_area.setdefault(dev.area_id, []).append(dev)

    lines = ["# Home Assistant — Areas & Devices", ""]
    areas = sorted(area_reg.async_list_areas(), key=lambda a: a.name or "")
    for area in areas:
        lines.append(f"## {area.name}")
        if area.aliases:
            lines.append(f"_Aliases: {', '.join(sorted(area.aliases))}_")
        lines.append("")
        devices = devices_by_area.get(area.id, [])
        lines.append("**Devices**")
        lines += _table(
            ["Device", "Manufacturer", "Model"],
            [
                [d.name_by_user or d.name or d.id, d.manufacturer or "", d.model or ""]
                for d in sorted(devices, key=lambda d: d.name_by_user or d.name or "")
            ],
        )
        ents = entities_by_area.get(area.id, [])
        lines.append("**Entities**")
        lines += _table(
            ["Entity ID", "Name", "State"],
            [
                [
                    e.entity_id,
                    e.name or e.original_name or "",
                    _fmt((st.state if (st := hass.states.get(e.entity_id)) else "—"), 60),
                ]
                for e in sorted(ents, key=lambda e: e.entity_id)
            ],
        )

    orphan = entities_by_area.get(None, [])
    if orphan:
        lines.append("## (No area)")
        lines += _table(
            ["Entity ID", "Name"],
            [[e.entity_id, e.name or e.original_name or ""] for e in sorted(orphan, key=lambda e: e.entity_id)],
        )
    return "\n".join(lines)


def _build_entities(hass: HomeAssistant, deep: bool) -> str:
    ent_reg = er.async_get(hass)
    reg_names = {e.entity_id: (e.name or e.original_name) for e in ent_reg.entities.values()}

    by_domain: dict[str, list[State]] = {}
    for state in hass.states.async_all():
        by_domain.setdefault(state.domain, []).append(state)

    lines = ["# Home Assistant — Entities", ""]
    for domain in sorted(by_domain):
        states = sorted(by_domain[domain], key=lambda s: s.entity_id)
        lines.append(f"## {domain} ({len(states)})")
        lines += _table(
            ["Entity ID", "Name", "State", "Attributes"],
            [
                [
                    s.entity_id,
                    _friendly(s, s.entity_id, reg_names.get(s.entity_id)),
                    _fmt(s.state, 60),
                    _attrs_summary(s, deep=deep),
                ]
                for s in states
            ],
        )
    return "\n".join(lines)


def _build_simple_domain(
    hass: HomeAssistant, deep: bool, *, title: str, domain: str, extra_attrs: tuple[str, ...]
) -> str:
    states = _states_by_domain(hass, domain)
    rows = []
    for s in states:
        row = [s.entity_id, _friendly(s, s.entity_id, None), _fmt(s.state, 40)]
        for attr in extra_attrs:
            row.append(_fmt(s.attributes.get(attr, ""), 120))
        rows.append(row)
    headers = ["Entity ID", "Name", "State", *extra_attrs]
    return "\n".join([f"# Home Assistant — {title}", "", *_table(headers, rows)])


def _build_automations(hass: HomeAssistant, deep: bool) -> str:
    return _build_simple_domain(
        hass, deep, title="Automations", domain="automation",
        extra_attrs=("last_triggered", "mode", "current", "id"),
    )


def _build_scripts(hass: HomeAssistant, deep: bool) -> str:
    return _build_simple_domain(
        hass, deep, title="Scripts", domain="script",
        extra_attrs=("last_triggered", "mode", "current"),
    )


def _build_scenes(hass: HomeAssistant, deep: bool) -> str:
    states = _states_by_domain(hass, "scene")
    rows = [
        [
            s.entity_id,
            _friendly(s, s.entity_id, None),
            _fmt(", ".join(s.attributes.get("entity_id", []) or []), 400),
        ]
        for s in states
    ]
    return "\n".join(
        ["# Home Assistant — Scenes", "", *_table(["Entity ID", "Name", "Affected entities"], rows)]
    )


def _build_helpers(hass: HomeAssistant, deep: bool) -> str:
    lines = ["# Home Assistant — Helpers", ""]
    for domain in _HELPER_DOMAINS:
        states = _states_by_domain(hass, domain)
        if not states:
            continue
        lines.append(f"## {domain} ({len(states)})")
        lines += _table(
            ["Entity ID", "Name", "State", "Attributes"],
            [
                [
                    s.entity_id,
                    _friendly(s, s.entity_id, None),
                    _fmt(s.state, 60),
                    _attrs_summary(s, deep=deep, skip=("editable", "icon")),
                ]
                for s in states
            ],
        )
    if len(lines) == 2:
        lines.append("_No helpers configured._")
    return "\n".join(lines)


def _build_integrations(hass: HomeAssistant, deep: bool) -> str:
    rows = []
    for entry in sorted(
        hass.config_entries.async_entries(),
        key=lambda e: (e.domain, e.title or ""),
    ):
        # Titles can carry account emails (e.g. this integration's own entry);
        # always scrub them before upload.
        rows.append(
            [
                entry.domain,
                _scrub_text(entry.title or ""),
                getattr(entry.state, "name", str(entry.state)),
                entry.source,
            ]
        )
    return "\n".join(
        [
            "# Home Assistant — Integrations",
            "",
            *_table(["Domain", "Title", "State", "Added via"], rows),
        ]
    )


_BUILDERS = {
    "overview": _build_overview,
    "areas": _build_areas,
    "entities": _build_entities,
    "automations": _build_automations,
    "scripts": _build_scripts,
    "scenes": _build_scenes,
    "helpers": _build_helpers,
    "integrations": _build_integrations,
}


def section_title(category: str) -> str:
    """Managed source title for a category, e.g. ``🏠 HA · Automations``."""
    return f"{DOC_SOURCE_PREFIX} {DOC_CATEGORY_TITLES.get(category, category.title())}"


def build_documents(
    hass: HomeAssistant, categories: list[str], *, scrub: bool
) -> dict[str, tuple[str, str]]:
    """Build ``{category: (source_title, markdown)}`` for the enabled sections."""
    docs: dict[str, tuple[str, str]] = {}
    stamp = dt_util.now().strftime("%Y-%m-%d %H:%M %Z")
    for category in categories:
        builder = _BUILDERS.get(category)
        if builder is None:
            continue
        body = builder(hass, scrub)
        footer = f"\n\n---\n_Exported from Home Assistant on {stamp} by the NotebookLM integration._\n"
        docs[category] = (section_title(category), body + footer)
    return docs


def _split(content: str, limit: int) -> list[str]:
    """Split content on line boundaries so each chunk stays under ``limit``."""
    if len(content) <= limit:
        return [content]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in content.splitlines(keepends=True):
        if size + len(line) > limit and current:
            chunks.append("".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


# =============================================================================
# Sync manager
# =============================================================================
class DocSyncManager:
    """Owns the documentation export schedule and the sync-to-notebook run."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: NotebookLMCoordinator,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.schedule: str = DEFAULT_DOC_SCHEDULE
        self.last_sync: datetime | None = None
        self.last_status: str | None = None
        self.last_error: str | None = None
        self.last_categories: list[str] = []
        self.last_source_count: int = 0
        self._unsub: Any = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------- config read
    def configured_notebook(self) -> str | None:
        return self.entry.options.get(CONF_DOC_NOTEBOOK)

    def configured_categories(self) -> list[str]:
        return self.entry.options.get(CONF_DOC_CATEGORIES) or DEFAULT_DOC_CATEGORIES

    def scrub_enabled(self) -> bool:
        return bool(self.entry.options.get(CONF_DOC_SCRUB, True))

    # -------------------------------------------------------------- scheduling
    @callback
    def set_schedule(self, schedule: str) -> None:
        """Switch the recurring-sync cadence (driven by the schedule select)."""
        self.schedule = schedule
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        interval = DOC_SCHEDULES.get(schedule)
        if interval:
            self._unsub = async_track_time_interval(
                self.hass, self._scheduled_run, timedelta(seconds=interval)
            )

    async def _scheduled_run(self, _now: datetime) -> None:
        if not self.configured_notebook():
            _LOGGER.debug("Skipping scheduled doc sync: no notebook configured")
            return
        try:
            await self.async_sync()
        except Exception as err:  # noqa: BLE001 - background task must not crash
            _LOGGER.warning("Scheduled documentation sync failed: %s", err)

    @callback
    def async_shutdown(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    # --------------------------------------------------------------- the sync
    async def async_sync(
        self,
        *,
        notebook_id: str | None = None,
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """Export the snapshot and replace each section's source in the notebook."""
        async with self._lock:
            return await self._run(notebook_id, categories)

    async def _run(
        self, notebook_id: str | None, categories: list[str] | None
    ) -> dict[str, Any]:
        notebook_id = notebook_id or self.configured_notebook()
        if not notebook_id:
            raise HomeAssistantError(
                "No documentation notebook configured. Set it in the NotebookLM "
                "integration options → Documentation."
            )
        cats = categories or self.configured_categories()
        client = self.coordinator.api.client

        self.last_status = "running"
        self.coordinator.async_update_listeners()

        try:
            docs = build_documents(self.hass, cats, scrub=self.scrub_enabled())
            existing = await client.sources.list(notebook_id)
            count = 0
            for category in cats:
                if category not in docs:
                    continue
                title, content = docs[category]
                # Drop the previous version of this section (incl. split parts).
                for source in existing:
                    stitle = getattr(source, "title", "") or ""
                    if stitle == title or stitle.startswith(f"{title} ("):
                        await client.sources.delete(notebook_id, source.id)
                parts = _split(content, DOC_MAX_SOURCE_CHARS)
                total = len(parts)
                for index, part in enumerate(parts, start=1):
                    part_title = title if total == 1 else f"{title} (part {index}/{total})"
                    await client.sources.add_text(notebook_id, part_title, part)
                    count += 1
        except HomeAssistantError:
            self.last_status = "error"
            self.coordinator.async_update_listeners()
            raise
        except Exception as err:  # noqa: BLE001 - record and re-raise as HA error
            self.last_status = "error"
            self.last_error = str(err)
            self.coordinator.async_update_listeners()
            self._fire_event(notebook_id, cats, 0, ok=False, error=str(err))
            raise HomeAssistantError(f"Documentation sync failed: {err}") from err

        self.last_sync = dt_util.utcnow()
        self.last_status = "ok"
        self.last_error = None
        self.last_categories = cats
        self.last_source_count = count
        self.coordinator.async_update_listeners()
        self._fire_event(notebook_id, cats, count, ok=True, error=None)
        return {
            "notebook_id": notebook_id,
            "categories": cats,
            "sources_written": count,
        }

    def _fire_event(
        self,
        notebook_id: str,
        categories: list[str],
        count: int,
        *,
        ok: bool,
        error: str | None,
    ) -> None:
        self.hass.bus.async_fire(
            EVENT_DOC_SYNCED,
            {
                "entry_id": self.entry.entry_id,
                "notebook_id": notebook_id,
                "categories": categories,
                "sources_written": count,
                "status": "ok" if ok else "error",
                "error": error,
            },
        )
