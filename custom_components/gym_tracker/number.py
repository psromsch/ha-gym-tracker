"""Number platform — weight / reps user inputs (spec §5)."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GymTrackerConfigEntry
from .const import (
    ENABLED_EXERCISES,
    EXERCISES,
    NUMBER_REPS,
    NUMBER_WEIGHT,
    REPS_MAX,
    REPS_MIN,
    REPS_STEP,
    WEIGHT_MAX,
    WEIGHT_MIN,
    WEIGHT_STEP,
    ExerciseDef,
)
from .entity import exercise_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GymTrackerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the weight and reps number entities for enabled exercises."""
    entities: list[GymNumber] = []
    for base in ENABLED_EXERCISES:
        exercise = EXERCISES[base]
        entities.append(
            GymNumber(
                exercise,
                NUMBER_WEIGHT,
                "Weight",
                WEIGHT_MIN,
                WEIGHT_MAX,
                WEIGHT_STEP,
            )
        )
        entities.append(
            GymNumber(exercise, NUMBER_REPS, "Reps", REPS_MIN, REPS_MAX, REPS_STEP)
        )
    async_add_entities(entities)


class GymNumber(RestoreNumber):
    """A user-editable input that survives restart (like the old input_number)."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        exercise: ExerciseDef,
        kind: str,
        name: str,
        minimum: float,
        maximum: float,
        step: float,
    ) -> None:
        """Initialise a weight or reps input."""
        self._attr_unique_id = f"{exercise.base}_{kind}"
        self._attr_name = name
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step
        self._attr_native_value = 0
        self._attr_device_info = exercise_device_info(exercise)

    async def async_added_to_hass(self) -> None:
        """Restore the last entered value."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value

    async def async_set_native_value(self, value: float) -> None:
        """Store a new value entered by the user."""
        self._attr_native_value = value
        self.async_write_ha_state()
