"""The Gym Tracker integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .const import (
    ATTR_BASE,
    ATTR_CHART_MIN,
    ATTR_FOCUS,
    ATTR_MUSCLES,
    ATTR_NAME,
    ATTR_SESSION_INDEX,
    ATTR_SET_INDEX,
    CHART_MIN_DEFAULT,
    DAY_FOCUS_GROUPS,
    DOMAIN,
    MUSCLE_GROUPS,
    PLATFORMS,
    SERVICE_ADD_EXERCISE,
    SERVICE_ADD_SET,
    SERVICE_DELETE_SESSION,
    SERVICE_DELETE_SET,
    SERVICE_FINISH_EXERCISE,
    SERVICE_REMOVE_EXERCISE,
    SERVICE_UNDO_LAST_SET,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .coordinator import GymTrackerCoordinator

type GymTrackerConfigEntry = ConfigEntry[GymTrackerCoordinator]

# `base` is validated at call time against the live taxonomy (which now
# changes at runtime), so the schema only enforces the type here.
_BASE_SCHEMA = vol.Schema({vol.Required(ATTR_BASE): cv.string})
_DELETE_SET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_BASE): cv.string,
        vol.Required(ATTR_SESSION_INDEX): vol.All(vol.Coerce(int), vol.Range(min=-1)),
        vol.Required(ATTR_SET_INDEX): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)
_DELETE_SESSION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_BASE): cv.string,
        vol.Required(ATTR_SESSION_INDEX): vol.All(vol.Coerce(int), vol.Range(min=-1)),
    }
)
_ADD_EXERCISE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_BASE): cv.slug,
        vol.Required(ATTR_NAME): cv.string,
        vol.Optional(ATTR_FOCUS, default="Chest"): vol.In(DAY_FOCUS_GROUPS),
        vol.Required(ATTR_MUSCLES): vol.All(
            cv.ensure_list, [vol.In(MUSCLE_GROUPS)], vol.Length(min=1)
        ),
        vol.Optional(ATTR_CHART_MIN, default=CHART_MIN_DEFAULT): vol.Coerce(float),
    }
)
_REMOVE_EXERCISE_SCHEMA = vol.Schema({vol.Required(ATTR_BASE): cv.string})

# Operation services that act on an existing exercise (base validated at call).
# (service name, coordinator method, schema, ordered param names)
_OP_SERVICES: tuple[tuple[str, str, vol.Schema, tuple[str, ...]], ...] = (
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

_ALL_SERVICES = (
    *(name for name, *_ in _OP_SERVICES),
    SERVICE_ADD_EXERCISE,
    SERVICE_REMOVE_EXERCISE,
)


async def async_setup_entry(hass: HomeAssistant, entry: GymTrackerConfigEntry) -> bool:
    """Set up Gym Tracker from a config entry."""
    store: Store[dict] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    coordinator = GymTrackerCoordinator(hass, store)
    coordinator.config_entry = entry
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
            for service in _ALL_SERVICES:
                hass.services.async_remove(DOMAIN, service)
    return unload_ok


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the domain services (idempotent)."""

    def _coordinator() -> GymTrackerCoordinator | None:
        entries = hass.config_entries.async_entries(DOMAIN)
        return entries[0].runtime_data if entries else None

    def _make_op_handler(method_name: str, params: tuple[str, ...]):
        async def _handler(call: ServiceCall) -> None:
            coordinator = _coordinator()
            if coordinator is None:
                return
            base = call.data[ATTR_BASE]
            if base not in coordinator.exercises:
                raise ServiceValidationError(f"Unknown exercise: {base}")
            await getattr(coordinator, method_name)(
                *(call.data[p] for p in params)
            )

        return _handler

    async def _handle_add_exercise(call: ServiceCall) -> None:
        coordinator = _coordinator()
        if coordinator is None:
            return
        await coordinator.async_add_exercise(
            call.data[ATTR_BASE],
            call.data[ATTR_NAME],
            call.data[ATTR_FOCUS],
            call.data[ATTR_MUSCLES],
            call.data[ATTR_CHART_MIN],
        )

    async def _handle_remove_exercise(call: ServiceCall) -> None:
        coordinator = _coordinator()
        if coordinator is None:
            return
        await coordinator.async_remove_exercise(call.data[ATTR_BASE])

    for service, method_name, schema, params in _OP_SERVICES:
        if not hass.services.has_service(DOMAIN, service):
            hass.services.async_register(
                DOMAIN, service, _make_op_handler(method_name, params), schema=schema
            )

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_EXERCISE):
        hass.services.async_register(
            DOMAIN, SERVICE_ADD_EXERCISE, _handle_add_exercise, schema=_ADD_EXERCISE_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, SERVICE_REMOVE_EXERCISE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REMOVE_EXERCISE,
            _handle_remove_exercise,
            schema=_REMOVE_EXERCISE_SCHEMA,
        )
