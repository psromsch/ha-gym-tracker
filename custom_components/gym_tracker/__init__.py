"""The Gym Tracker integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.storage import Store

from .const import (
    ATTR_BASE,
    ATTR_SESSION_INDEX,
    ATTR_SET_INDEX,
    DOMAIN,
    ENABLED_EXERCISES,
    PLATFORMS,
    SERVICE_ADD_SET,
    SERVICE_DELETE_SESSION,
    SERVICE_DELETE_SET,
    SERVICE_FINISH_EXERCISE,
    SERVICE_UNDO_LAST_SET,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .coordinator import GymTrackerCoordinator

type GymTrackerConfigEntry = ConfigEntry[GymTrackerCoordinator]

# base is validated against the enabled set so the one ENABLED_EXERCISES knob
# widens services and entities together.
_BASE_SCHEMA = vol.Schema({vol.Required(ATTR_BASE): vol.In(ENABLED_EXERCISES)})
_DELETE_SET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_BASE): vol.In(ENABLED_EXERCISES),
        vol.Required(ATTR_SESSION_INDEX): vol.All(vol.Coerce(int), vol.Range(min=-1)),
        vol.Required(ATTR_SET_INDEX): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)
_DELETE_SESSION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_BASE): vol.In(ENABLED_EXERCISES),
        vol.Required(ATTR_SESSION_INDEX): vol.All(vol.Coerce(int), vol.Range(min=-1)),
    }
)

# (service name, coordinator method, schema, ordered param names)
_SERVICES: tuple[tuple[str, str, vol.Schema, tuple[str, ...]], ...] = (
    (SERVICE_ADD_SET, "async_add_set", _BASE_SCHEMA, (ATTR_BASE,)),
    (SERVICE_UNDO_LAST_SET, "async_undo_last_set", _BASE_SCHEMA, (ATTR_BASE,)),
    (SERVICE_FINISH_EXERCISE, "async_finish_exercise", _BASE_SCHEMA, (ATTR_BASE,)),
    (
        SERVICE_DELETE_SET,
        "async_delete_set",
        _DELETE_SET_SCHEMA,
        (ATTR_BASE, ATTR_SESSION_INDEX, ATTR_SET_INDEX),
    ),
    (
        SERVICE_DELETE_SESSION,
        "async_delete_session",
        _DELETE_SESSION_SCHEMA,
        (ATTR_BASE, ATTR_SESSION_INDEX),
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: GymTrackerConfigEntry) -> bool:
    """Set up Gym Tracker from a config entry."""
    store: Store[dict] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    coordinator = GymTrackerCoordinator(hass, store)
    await coordinator.async_load()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GymTrackerConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Single-instance integration: once the last entry is gone, drop the
        # domain services too.
        remaining = [
            other
            for other in hass.config_entries.async_entries(DOMAIN)
            if other.entry_id != entry.entry_id
        ]
        if not remaining:
            for service, _method, _schema, _params in _SERVICES:
                hass.services.async_remove(DOMAIN, service)
    return unload_ok


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the domain services (idempotent)."""

    def _coordinator() -> GymTrackerCoordinator | None:
        entries = hass.config_entries.async_entries(DOMAIN)
        return entries[0].runtime_data if entries else None

    def _make_handler(method_name: str, params: tuple[str, ...]):
        async def _handler(call: ServiceCall) -> None:
            coordinator = _coordinator()
            if coordinator is None:
                return
            await getattr(coordinator, method_name)(
                *(call.data[p] for p in params)
            )

        return _handler

    for service, method_name, schema, params in _SERVICES:
        if hass.services.has_service(DOMAIN, service):
            continue
        hass.services.async_register(
            DOMAIN, service, _make_handler(method_name, params), schema=schema
        )
