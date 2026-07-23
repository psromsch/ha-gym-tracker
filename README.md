# Gym Tracker — Home Assistant custom integration

A Home Assistant integration that replaces a large hand-written YAML package
(hundreds of `input_*` helpers, scripts and automations) with proper Python
entities. Set history is stored as a **real list** in HA's `Store`, not as a
pipe-delimited string re-parsed in Jinja on every read.

Backend only — the Lovelace dashboard stays hand-written YAML and consumes the
integration's entities.

> **Build status:** steps 1–3 of the build plan (skeleton, exercise config +
> coordinator, and one exercise end-to-end). Entities are registered for
> **`bench_press` only** so the data model can be validated against the live
> dashboard before generating all 29× exercises. Muscle-group counters, the
> weekly reset, first-run import and the delete/reset services are **not yet
> built**.

## Installation

### HACS (custom repository)

1. HACS → ⋮ → **Custom repositories**.
2. Add `https://github.com/psromsch/ha-gym-tracker` as an **Integration**.
3. Install **Gym Tracker**, then restart Home Assistant.

### Manual

Copy `custom_components/gym_tracker/` into your HA `config/custom_components/`
directory and restart.

### Setup

**Settings → Devices & Services → Add Integration → Gym Tracker.** It is a
single-instance, confirm-only flow — there is nothing to configure. No YAML
`configuration.yaml` entry is used or supported.

## Entities (current build)

For each enabled exercise (`bench_press` today), grouped under a device named
after the exercise:

| Entity | Purpose |
|---|---|
| `number.bench_press_weight` | Weight input (0–500, step 0.5, box mode) |
| `number.bench_press_reps` | Reps input (0–100, step 1, box mode) |
| `sensor.bench_press_session_total` | Today's volume (kg) |
| `sensor.bench_press_session_max_weight` | Today's heaviest set (kg) |
| `sensor.bench_press_lifetime_total` | Cumulative volume (kg) |
| `sensor.bench_press_history` | State = number of stored sessions; attributes carry `current_sets` and the full `sessions` list (newest first) |
| `button.bench_press_add_set` | Record a set |
| `button.bench_press_undo_last_set` | Undo the last set |
| `button.bench_press_finish_exercise` | Close out the current session |

### Widening beyond one exercise

The set of exercises that get entities is controlled by a single constant,
`ENABLED_EXERCISES` in `custom_components/gym_tracker/const.py`. Add bases to
that tuple (or set it to `tuple(EXERCISES)` for all 29). Platforms **and**
services both read it — there is no hardcoded filter anywhere else.

## Services

| Service | Data | Notes |
|---|---|---|
| `gym_tracker.add_set` | `base` | Reads the exercise's weight/reps; both must be > 0 |
| `gym_tracker.undo_last_set` | `base` | Falls back to the last finished session when the current one is empty |
| `gym_tracker.finish_exercise` | `base` | Prepends the current session to history |

The buttons are thin wrappers over these operations.

## Data model

Stored in `.storage/gym_tracker` (JSON), one entry per exercise plus per-muscle
weekly counters:

```jsonc
{
  "exercises": {
    "bench_press": {
      "lifetime_total": 128400,
      "current": { "sets": [ { "time": "07:42", "weight": 60.0, "reps": 8, "volume": 480 } ] },
      "history": [
        { "date": "2026-07-18", "sets": [ /* ... */ ], "total": 1840, "max_weight": 57.5 }
      ]
    }
  },
  "muscles": { "chest": { "sets": 6, "target": 12 } }
}
```

`volume = weight * reps`, stored per set so deletions can subtract exactly.
