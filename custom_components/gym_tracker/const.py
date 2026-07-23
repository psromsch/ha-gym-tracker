"""Constants and the single source-of-truth exercise configuration for Gym Tracker."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.const import Platform

DOMAIN = "gym_tracker"

PLATFORMS: list[Platform] = [Platform.NUMBER, Platform.SENSOR, Platform.BUTTON]

# HA Store (.storage/gym_tracker)
STORAGE_VERSION = 1
STORAGE_KEY = DOMAIN

# --- Services (§9) -----------------------------------------------------------
SERVICE_ADD_SET = "add_set"
SERVICE_UNDO_LAST_SET = "undo_last_set"
SERVICE_FINISH_EXERCISE = "finish_exercise"
SERVICE_DELETE_SET = "delete_set"
SERVICE_DELETE_SESSION = "delete_session"
SERVICE_ADD_EXERCISE = "add_exercise"
SERVICE_REMOVE_EXERCISE = "remove_exercise"

ATTR_BASE = "base"
ATTR_SESSION_INDEX = "session_index"
ATTR_SET_INDEX = "set_index"
ATTR_NAME = "name"
ATTR_FOCUS = "focus"
ATTR_MUSCLES = "muscles"
ATTR_CHART_MIN = "chart_min"

# Default y-axis floor for a newly added exercise's ApexCharts card.
CHART_MIN_DEFAULT = 20

# --- Number entity input ranges (§5) -----------------------------------------
NUMBER_WEIGHT = "weight"
NUMBER_REPS = "reps"
WEIGHT_MIN = 0
WEIGHT_MAX = 500
WEIGHT_STEP = 0.5
REPS_MIN = 0
REPS_MAX = 100
REPS_STEP = 1

UNIT_KG = "kg"


@dataclass(frozen=True)
class ExerciseDef:
    """One row of the exercise taxonomy (§3).

    ``base``      slug / entity-id stem
    ``name``      display name (also drives the device name)
    ``focus``     day-focus group the exercise lives under
    ``muscles``   muscle groups this exercise credits on every add_set
    ``chart_min`` y-axis floor for the ApexCharts card
    """

    base: str
    name: str
    focus: str
    muscles: tuple[str, ...]
    chart_min: float


# -----------------------------------------------------------------------------
# Exercise taxonomy — the single source of truth (spec §3).
#
# This collapses four previously-disagreeing taxonomies into one list. The
# muscle mappings below were cross-checked against the live
# `wt_auto_add_set` automation (the old `auto_counter` logic) on 2026-07-23,
# not taken on faith from the spec:
#
#   * `abductor`  -> ("glutes",)    CONFIRMED (spec guessed glutes; correct).
#   * `adductor`  -> ("adductor",)  CORRECTED. The spec §3 guessed `quads`,
#                                    but the live system credits a dedicated
#                                    `adductor` muscle group (script
#                                    `wt_add_adductor`, helpers
#                                    `wt_sets_adductor` / `wt_target_adductor`).
#                                    This also means the muscle-group list is
#                                    11 groups, not the 10 named in §3.
#   * `dips` is deliberately focus=Lats but muscles=(chest, triceps) — the
#     intentional mismatch called out in §3, preserved here.
# -----------------------------------------------------------------------------
EXERCISES: dict[str, ExerciseDef] = {
    ex.base: ex
    for ex in (
        ExerciseDef("leg_press", "Leg Press", "Lower", ("quads",), 50),
        ExerciseDef("back_squat", "Back Squat", "Lower", ("quads", "glutes"), 20),
        ExerciseDef("belt_squat", "Belt Squat", "Lower", ("quads", "glutes"), 45),
        ExerciseDef(
            "bulgarian_split_squat",
            "Bulgarian Split Squat",
            "Lower",
            ("quads", "glutes"),
            15,
        ),
        ExerciseDef(
            "weighted_step_up", "Weighted Step Up", "Lower", ("quads", "glutes"), 25
        ),
        ExerciseDef("leg_extension", "Leg Extension", "Lower", ("quads",), 65),
        ExerciseDef("reverse_lunge", "Reverse Lunge", "Lower", ("quads",), 15),
        ExerciseDef("leg_curl", "Leg Curl", "Lower", ("hamstrings",), 45),
        ExerciseDef("hip_raise", "Hip Raise", "Lower", ("hamstrings", "glutes"), 25),
        ExerciseDef("gluteus_machine", "Gluteus Machine", "Lower", ("glutes",), 50),
        # abductor: verified against live auto_counter -> glutes (spec confirmed).
        ExerciseDef("abductor", "Abductor", "Lower", ("glutes",), 60),
        # adductor: verified -> own `adductor` group, NOT quads as §3 guessed.
        ExerciseDef("adductor", "Adductor", "Lower", ("adductor",), 35),
        ExerciseDef("calf_raises", "Calf Raises", "Lower", ("calves",), 40),
        ExerciseDef("bench_press", "Bench Press", "Chest", ("chest",), 20),
        ExerciseDef("incl_bench_press", "Incl Bench Press", "Chest", ("chest",), 15),
        ExerciseDef("peck_back", "Peck back", "Chest", ("chest",), 40),
        ExerciseDef(
            "super_horizontal_bp", "Super Horizontal BP", "Chest", ("chest",), 30
        ),
        ExerciseDef("vertical_chest_pr", "Vertical Chest PR", "Chest", ("chest",), 65),
        ExerciseDef(
            "inclined_chest_pr_machine",
            "Inclined Chest PR Machine",
            "Chest",
            ("chest",),
            70,
        ),
        ExerciseDef("lat_pulldown", "Lat Pulldown", "Lats", ("lats", "biceps"), 50),
        ExerciseDef("pull_up", "Pull-up", "Lats", ("lats", "biceps"), 80),
        ExerciseDef("cable_row", "Cable Row", "Lats", ("lats", "biceps"), 40),
        # dips: intentional focus/muscle mismatch (§3) — preserved.
        ExerciseDef("dips", "Dips", "Lats", ("chest", "triceps"), 70),
        ExerciseDef("bicep_curl", "Bicep Curl", "Biceps", ("biceps",), 10),
        ExerciseDef("bicep_scot", "Bicep Scot", "Biceps", ("biceps",), 10),
        ExerciseDef("tricep_down", "Tricep Down", "Triceps", ("triceps",), 15),
        ExerciseDef("tricep_overhead", "Tricep Overhead", "Triceps", ("triceps",), 15),
        ExerciseDef(
            "dumbbell_shoulder_pr",
            "Dumbbell Shoulder PR",
            "Shoulders",
            ("shoulders",),
            15,
        ),
        ExerciseDef(
            "shoulder_lateral_r", "Shoulder Lateral R", "Shoulders", ("shoulders",), 8
        ),
    )
}

# Muscle groups that own a weekly counter (§3). Verified against the live
# `wt_sets_*` / `wt_target_*` helpers on 2026-07-23 — 11 groups. `adductor`
# is present (see EXERCISES note); `abs` has no exercise mapped and is
# incremented manually only.
MUSCLE_GROUPS: tuple[str, ...] = (
    "chest",
    "shoulders",
    "lats",
    "biceps",
    "triceps",
    "quads",
    "hamstrings",
    "glutes",
    "calves",
    "adductor",
    "abs",
)

# Day-focus groups (§3).
DAY_FOCUS_GROUPS: tuple[str, ...] = (
    "Lower",
    "Biceps",
    "Lats",
    "Chest",
    "Triceps",
    "Shoulders",
)

# -----------------------------------------------------------------------------
# EXERCISES above are the built-in defaults (all enabled). User-added exercises
# are stored at runtime by the coordinator (Store key "custom_exercises") and
# merged on top — see GymTrackerCoordinator.exercises. There is no static
# enabled-list any more: every built-in plus every user-added exercise gets
# entities. Platforms and services read the coordinator's merged taxonomy.
# -----------------------------------------------------------------------------
