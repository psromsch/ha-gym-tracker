"""Data coordinator owning the Gym Tracker storage dict (spec §4)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    ENABLED_EXERCISES,
    EXERCISES,
    MUSCLE_GROUPS,
    NUMBER_REPS,
    NUMBER_WEIGHT,
)

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE_STATES = ("unknown", "unavailable", "none", "")


def _default_exercise() -> dict[str, Any]:
    """Return a fresh, empty per-exercise record (§4)."""
    return {"lifetime_total": 0, "current": {"sets": []}, "history": []}


def _default_muscle() -> dict[str, Any]:
    """Return a fresh, empty per-muscle-group record (§4)."""
    return {"sets": 0, "target": 0}


class GymTrackerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Owns the JSON storage dict and the mutation operations (§6).

    This is push-based: there is no polling. Entities subscribe as
    coordinator listeners and are notified after every mutation. The
    ``add_set`` / ``undo_last_set`` / ``finish_exercise`` services and the
    button entities are all thin wrappers over the async methods here, so the
    operation logic lives in exactly one place.
    """

    def __init__(self, hass: HomeAssistant, store: Store[dict[str, Any]]) -> None:
        """Initialise the coordinator without any update interval (push-only)."""
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self.store = store

    async def async_load(self) -> None:
        """Load persisted data (or seed a fresh dict) and ensure structure."""
        stored = await self.store.async_load()
        if stored is None:
            stored = {"exercises": {}, "muscles": {}}
        stored.setdefault("exercises", {})
        stored.setdefault("muscles", {})

        # Ensure every enabled exercise and every muscle group has a record so
        # the mutation methods and entities never have to special-case a
        # missing key.
        for base in ENABLED_EXERCISES:
            stored["exercises"].setdefault(base, _default_exercise())
        for muscle in MUSCLE_GROUPS:
            stored["muscles"].setdefault(muscle, _default_muscle())

        self.async_set_updated_data(stored)

    async def _async_persist(self) -> None:
        """Persist to storage and notify all subscribed entities."""
        await self.store.async_save(self.data)
        self.async_set_updated_data(self.data)

    def _exercise(self, base: str) -> dict[str, Any]:
        """Return the record for ``base``, creating it on first touch."""
        return self.data["exercises"].setdefault(base, _default_exercise())

    def _read_number_input(self, base: str, kind: str) -> float | None:
        """Read a ``number.{base}_{kind}`` input via the entity registry.

        Resolving through the registry (rather than assuming the entity_id)
        keeps the read correct even if the user renames the entity.
        """
        ent_reg = er.async_get(self.hass)
        entity_id = ent_reg.async_get_entity_id("number", DOMAIN, f"{base}_{kind}")
        if entity_id is None:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in _UNAVAILABLE_STATES:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    # --- Operations (§6) -----------------------------------------------------

    async def async_add_set(self, base: str) -> None:
        """Record a set for ``base`` (§6 add_set)."""
        weight = self._read_number_input(base, NUMBER_WEIGHT)
        reps_raw = self._read_number_input(base, NUMBER_REPS)
        # Guard: both must be > 0, else no-op (preserves current behaviour).
        if not weight or not reps_raw or weight <= 0 or reps_raw <= 0:
            return

        reps = int(reps_raw)
        volume = weight * reps
        exercise = self._exercise(base)
        exercise["current"]["sets"].append(
            {
                "time": dt_util.now().strftime("%H:%M"),
                "weight": weight,
                "reps": reps,
                "volume": volume,
            }
        )
        exercise["lifetime_total"] += volume

        # Compound lifts credit more than one muscle group — this is why the
        # counter hook is add_set, not finish_exercise (§6).
        for muscle in EXERCISES[base].muscles:
            if muscle in self.data["muscles"]:
                self.data["muscles"][muscle]["sets"] += 1

        await self._async_persist()

    async def async_undo_last_set(self, base: str) -> None:
        """Remove the most recent set (§6 undo_last_set)."""
        exercise = self._exercise(base)
        removed: dict[str, Any] | None = None

        if exercise["current"]["sets"]:
            removed = exercise["current"]["sets"].pop()
        elif exercise["history"]:
            # Fallback: undo into the most recent finished session.
            session = exercise["history"][0]
            if session["sets"]:
                removed = session["sets"].pop()
                session["total"] = sum(s["volume"] for s in session["sets"])
                session["max_weight"] = max(
                    (s["weight"] for s in session["sets"]), default=0
                )

        if removed is None:
            return

        exercise["lifetime_total"] = max(0, exercise["lifetime_total"] - removed["volume"])
        for muscle in EXERCISES[base].muscles:
            if muscle in self.data["muscles"]:
                self.data["muscles"][muscle]["sets"] = max(
                    0, self.data["muscles"][muscle]["sets"] - 1
                )

        await self._async_persist()

    async def async_finish_exercise(self, base: str) -> None:
        """Close out the current session into history (§6 finish_exercise)."""
        exercise = self._exercise(base)
        sets = exercise["current"]["sets"]
        if not sets:
            return

        exercise["history"].insert(
            0,
            {
                "date": dt_util.now().date().isoformat(),
                "sets": list(sets),
                "total": sum(s["volume"] for s in sets),
                "max_weight": max(s["weight"] for s in sets),
            },
        )
        # lifetime_total is intentionally untouched — already accumulated per
        # set in add_set.
        exercise["current"]["sets"] = []

        await self._async_persist()
