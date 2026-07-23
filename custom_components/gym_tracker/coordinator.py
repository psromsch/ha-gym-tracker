"""Data coordinator owning the Gym Tracker storage dict (spec §4)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EXERCISES,
    MUSCLE_GROUPS,
    NUMBER_REPS,
    NUMBER_WEIGHT,
    ExerciseDef,
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
    """Owns the JSON storage dict, the taxonomy, and the operations (§6).

    Push-based: no polling. Entities subscribe as coordinator listeners and
    are notified after every mutation.

    The exercise taxonomy is the built-in :data:`EXERCISES` defaults merged
    with any user-added exercises stored under ``custom_exercises``. Adding or
    removing an exercise rewrites that stored map and reloads the config entry,
    which recreates the platform entities from the new taxonomy.
    """

    def __init__(self, hass: HomeAssistant, store: Store[dict[str, Any]]) -> None:
        """Initialise the coordinator without any update interval (push-only)."""
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self.store = store
        self.config_entry: ConfigEntry | None = None

    # --- Taxonomy ------------------------------------------------------------

    @property
    def exercises(self) -> dict[str, ExerciseDef]:
        """The live taxonomy: built-in defaults + user-added, merged."""
        result: dict[str, ExerciseDef] = dict(EXERCISES)
        for base, cfg in (self.data or {}).get("custom_exercises", {}).items():
            result[base] = ExerciseDef(
                base=base,
                name=cfg.get("name", base),
                focus=cfg.get("focus", "Chest"),
                muscles=tuple(cfg.get("muscles", ())),
                chart_min=cfg.get("chart_min", 20),
            )
        return result

    def _all_bases(self, stored: dict[str, Any]) -> list[str]:
        """Every base in the taxonomy for the given stored dict."""
        return [*EXERCISES, *stored.get("custom_exercises", {})]

    async def async_load(self) -> None:
        """Load persisted data (or seed a fresh dict) and ensure structure."""
        stored = await self.store.async_load()
        if stored is None:
            stored = {}
        stored.setdefault("exercises", {})
        stored.setdefault("muscles", {})
        stored.setdefault("custom_exercises", {})

        # Ensure every taxonomy exercise and every muscle group has a data
        # record so mutations and entities never special-case a missing key.
        for base in self._all_bases(stored):
            stored["exercises"].setdefault(base, _default_exercise())
        for muscle in MUSCLE_GROUPS:
            stored["muscles"].setdefault(muscle, _default_muscle())

        self.async_set_updated_data(stored)

    async def _async_persist(self) -> None:
        """Persist to storage and notify all subscribed entities."""
        await self.store.async_save(self.data)
        self.async_set_updated_data(self.data)

    def _schedule_reload(self) -> None:
        """Reload the config entry so platforms rebuild from the new taxonomy."""
        if self.config_entry is None:
            return
        entry_id = self.config_entry.entry_id
        self.hass.async_create_task(
            self.hass.config_entries.async_reload(entry_id)
        )

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
        for muscle in self.exercises[base].muscles:
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
        for muscle in self.exercises[base].muscles:
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

    def _session_ref(self, exercise: dict[str, Any], session_index: int):
        """Resolve a session dict from an index.

        ``session_index == -1`` -> the in-progress ``current`` session;
        ``0`` -> most recent finished session (T-1), ``1`` -> T-2, ... into
        the newest-first ``history`` list. Returns ``None`` for a bad index.
        """
        if session_index == -1:
            return exercise["current"]
        if 0 <= session_index < len(exercise["history"]):
            return exercise["history"][session_index]
        return None

    async def async_delete_set(
        self, base: str, session_index: int, set_index: int
    ) -> None:
        """Delete one set from any session (§6 delete_set).

        Subtracts the set's volume from the session total (history sessions
        only — the current session's total is sensor-derived) and from
        ``lifetime_total``, both clamped at 0, then recomputes ``max_weight``.
        Muscle counters are deliberately NOT adjusted (see module note / §6):
        an old set may belong to a previous week, and the weekly counters must
        not be retroactively rewritten.
        """
        exercise = self._exercise(base)
        session = self._session_ref(exercise, session_index)
        if session is None:
            return
        sets = session["sets"]
        if not 0 <= set_index < len(sets):
            return

        removed = sets.pop(set_index)
        exercise["lifetime_total"] = max(
            0, exercise["lifetime_total"] - removed["volume"]
        )
        # Finished sessions carry a stored total/max_weight; recompute them.
        # The current session has neither (its sensors derive them live).
        if session_index != -1:
            session["total"] = sum(s["volume"] for s in sets)
            session["max_weight"] = max((s["weight"] for s in sets), default=0)

        await self._async_persist()

    async def async_delete_session(self, base: str, session_index: int) -> None:
        """Delete a whole session (§6 delete_session).

        Subtracts the session's total from ``lifetime_total``, clamped at 0.
        ``session_index == -1`` clears the in-progress session. Muscle counters
        are not adjusted (same rationale as delete_set).
        """
        exercise = self._exercise(base)
        if session_index == -1:
            sets = exercise["current"]["sets"]
            total = sum(s["volume"] for s in sets)
            exercise["current"]["sets"] = []
        elif 0 <= session_index < len(exercise["history"]):
            removed = exercise["history"].pop(session_index)
            total = removed.get("total", 0)
        else:
            return

        exercise["lifetime_total"] = max(0, exercise["lifetime_total"] - total)

        await self._async_persist()

    # --- Taxonomy editing ----------------------------------------------------

    async def async_add_exercise(
        self,
        base: str,
        name: str,
        focus: str,
        muscles: list[str],
        chart_min: float,
    ) -> None:
        """Add (or update) a user-defined exercise, then reload to build it.

        Built-in defaults cannot be shadowed by a custom entry with the same
        base — that would fork the single source of truth. History is
        preserved: a data record is created (or kept if the base was removed
        and re-added).
        """
        if base in EXERCISES:
            raise ServiceValidationError(
                f"'{base}' is a built-in exercise and cannot be redefined."
            )

        self.data.setdefault("custom_exercises", {})[base] = {
            "name": name,
            "focus": focus,
            "muscles": list(muscles),
            "chart_min": chart_min,
        }
        self.data["exercises"].setdefault(base, _default_exercise())
        await self.store.async_save(self.data)
        self._schedule_reload()

    async def async_remove_exercise(self, base: str) -> None:
        """Remove a user-added exercise and its entities, then reload.

        Only user-added exercises can be removed; built-ins are code-defined.
        The stored history record is kept (orphaned) so re-adding the same
        base restores it. The device and its entities are removed from the
        registries so they don't linger as unavailable.
        """
        custom = self.data.get("custom_exercises", {})
        if base not in custom:
            raise ServiceValidationError(
                f"'{base}' is not a user-added exercise (nothing to remove)."
            )

        del custom[base]
        await self.store.async_save(self.data)

        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_device(identifiers={(DOMAIN, base)})
        if device is not None:
            dev_reg.async_remove_device(device.id)

        self._schedule_reload()
