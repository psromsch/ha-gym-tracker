"""Shared helpers for Gym Tracker entities."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, ExerciseDef


def exercise_device_info(exercise: ExerciseDef) -> DeviceInfo:
    """Group all of an exercise's entities under one device.

    With ``_attr_has_entity_name = True`` the device name also drives the
    entity_id stem, so e.g. device "Bench Press" + entity "Weight" yields
    ``number.bench_press_weight`` exactly as the spec (§5) requires.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, exercise.base)},
        name=exercise.name,
        manufacturer="Gym Tracker",
        model=f"Exercise · {exercise.focus}",
    )
