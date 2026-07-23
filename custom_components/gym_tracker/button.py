"""Button platform — thin wrappers over the coordinator operations (§5/§9)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GymTrackerConfigEntry
from .const import (
    ENABLED_EXERCISES,
    EXERCISES,
    SERVICE_ADD_SET,
    SERVICE_FINISH_EXERCISE,
    SERVICE_UNDO_LAST_SET,
    ExerciseDef,
)
from .coordinator import GymTrackerCoordinator
from .entity import exercise_device_info

# kind -> (display name, coordinator method)
_BUTTONS: dict[str, tuple[str, str]] = {
    SERVICE_ADD_SET: ("Add Set", "async_add_set"),
    SERVICE_UNDO_LAST_SET: ("Undo Last Set", "async_undo_last_set"),
    SERVICE_FINISH_EXERCISE: ("Finish Exercise", "async_finish_exercise"),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GymTrackerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the action buttons for each enabled exercise."""
    coordinator = entry.runtime_data
    entities = [
        GymButton(coordinator, EXERCISES[base], kind, name, method)
        for base in ENABLED_EXERCISES
        for kind, (name, method) in _BUTTONS.items()
    ]
    async_add_entities(entities)


class GymButton(ButtonEntity):
    """A button that invokes one coordinator operation."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GymTrackerCoordinator,
        exercise: ExerciseDef,
        kind: str,
        name: str,
        method: str,
    ) -> None:
        """Initialise the button."""
        self._coordinator = coordinator
        self._base = exercise.base
        self._method = method
        self._attr_unique_id = f"{exercise.base}_{kind}"
        self._attr_name = name
        self._attr_device_info = exercise_device_info(exercise)

    async def async_press(self) -> None:
        """Run the mapped coordinator operation."""
        await getattr(self._coordinator, self._method)(self._base)
