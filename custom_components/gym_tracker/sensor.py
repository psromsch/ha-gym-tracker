"""Sensor platform — session/lifetime totals and the history sensor (spec §5)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GymTrackerConfigEntry
from .const import ENABLED_EXERCISES, EXERCISES, UNIT_KG, ExerciseDef
from .coordinator import GymTrackerCoordinator
from .entity import exercise_device_info


def _session_total(record: dict[str, Any]) -> float:
    return sum(s["volume"] for s in record["current"]["sets"])


def _session_max_weight(record: dict[str, Any]) -> float:
    return max((s["weight"] for s in record["current"]["sets"]), default=0)


def _lifetime_total(record: dict[str, Any]) -> float:
    return record["lifetime_total"]


def _history_count(record: dict[str, Any]) -> int:
    return len(record["history"])


@dataclass(frozen=True, kw_only=True)
class GymSensorDescription(SensorEntityDescription):
    """Describes a Gym Tracker sensor and how to derive it from a record."""

    value_fn: Callable[[dict[str, Any]], Any]
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSOR_TYPES: tuple[GymSensorDescription, ...] = (
    GymSensorDescription(
        key="session_total",
        name="Session Total",
        native_unit_of_measurement=UNIT_KG,
        state_class=SensorStateClass.TOTAL,
        value_fn=_session_total,
    ),
    GymSensorDescription(
        key="session_max_weight",
        name="Session Max Weight",
        native_unit_of_measurement=UNIT_KG,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_session_max_weight,
    ),
    GymSensorDescription(
        key="lifetime_total",
        name="Lifetime Total",
        native_unit_of_measurement=UNIT_KG,
        state_class=SensorStateClass.TOTAL,
        value_fn=_lifetime_total,
    ),
    GymSensorDescription(
        key="history",
        name="History",
        value_fn=_history_count,
        attributes_fn=lambda record: {
            "current_sets": record["current"]["sets"],
            "sessions": record["history"],
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GymTrackerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the sensor set for each enabled exercise."""
    coordinator = entry.runtime_data
    entities = [
        GymSensor(coordinator, EXERCISES[base], description)
        for base in ENABLED_EXERCISES
        for description in SENSOR_TYPES
    ]
    async_add_entities(entities)


class GymSensor(CoordinatorEntity[GymTrackerCoordinator], SensorEntity):
    """A sensor derived from one exercise's stored record."""

    _attr_has_entity_name = True
    entity_description: GymSensorDescription

    def __init__(
        self,
        coordinator: GymTrackerCoordinator,
        exercise: ExerciseDef,
        description: GymSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._base = exercise.base
        self._attr_unique_id = f"{exercise.base}_{description.key}"
        self._attr_device_info = exercise_device_info(exercise)

    @property
    def _record(self) -> dict[str, Any]:
        return self.coordinator.data["exercises"][self._base]

    @property
    def native_value(self) -> Any:
        """Return the derived state value."""
        return self.entity_description.value_fn(self._record)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the history payload for the history sensor, else nothing."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self._record)
