# Gym Tracker — Home Assistant Custom Integration Spec

Target: replace ~30 YAML package files (~500 KB, 785 helper entities, 116 scripts, 116
automations) with one custom integration. Backend only — the Lovelace dashboard stays
hand-written YAML and consumes the integration's entities.

Domain: `gym_tracker`. Install path during development: `/config/custom_components/gym_tracker/`.
HACS packaging comes later; ignore it for the initial build.

---

## 1. Why this exists (context for design decisions)

The current YAML implementation works correctly but copy-pastes the same four operations
29 times. Two files in it already demonstrate the generic pattern this integration
formalises:

- `exercise_history_tools.yaml` — a parameterised script taking `base` as a field and
  resolving entity IDs dynamically.
- `training_session_control.yaml` → `debug_force_shift` — a `for_each` loop over a list of
  exercise base names.

Set history is currently stored as a pipe-delimited **string** in `input_text`
(`"07:42 60.0x8=480|07:45 60.0x8=480"`) because YAML helpers cannot hold lists. Every
consumer re-parses that string in Jinja. Storing a real list is the single biggest
simplification this integration delivers.

---

## 2. Core design decisions (already settled — do not revisit)

| Decision | Choice |
|---|---|
| History depth | **Unbounded.** Store every finished session forever. The dashboard displays only the most recent 7. |
| Migration | **Start history fresh.** Import lifetime totals only (§8). |
| UI | **No custom card.** Dashboard is user-maintained YAML using existing HACS cards. |
| Storage | HA's `Store` helper (`.storage/gym_tracker`), JSON, one entry per exercise. |
| Config | Exercise list is integration config (§3), not user-editable per-entity YAML. |

---

## 3. Exercise configuration

Single source of truth. Currently this taxonomy is duplicated across four places
(`auto_counter.yaml`, `training_session_control.yaml`, `input_select.day_focus`, and
hardcoded dashboard text) and **they disagree with each other** — collapsing them into
this one list is a primary goal.

Fields per exercise: `base` (slug / entity id), `name` (display), `focus` (day-focus
group), `muscles` (list — drives weekly set counters), `chart_min` (y-axis floor for the
ApexCharts card).

| base | name | focus | muscles | chart_min |
|---|---|---|---|---|
| leg_press | Leg Press | Lower | quads | 50 |
| back_squat | Back Squat | Lower | quads, glutes | 20 |
| belt_squat | Belt Squat | Lower | quads, glutes | 45 |
| bulgarian_split_squat | Bulgarian Split Squat | Lower | quads, glutes | 15 |
| weighted_step_up | Weighted Step Up | Lower | quads, glutes | 25 |
| leg_extension | Leg Extension | Lower | quads | 65 |
| reverse_lunge | Reverse Lunge | Lower | quads | 15 |
| leg_curl | Leg Curl | Lower | hamstrings | 45 |
| hip_raise | Hip Raise | Lower | hamstrings, glutes | 25 |
| gluteus_machine | Gluteus Machine | Lower | glutes | 50 |
| abductor | Abductor | Lower | glutes *(verify)* | 60 |
| adductor | Adductor | Lower | quads *(verify)* | 35 |
| calf_raises | Calf Raises | Lower | calves | 40 |
| bench_press | Bench Press | Chest | chest | 20 |
| incl_bench_press | Incl Bench Press | Chest | chest | 15 |
| peck_back | Peck back | Chest | chest | 40 |
| super_horizontal_bp | Super Horizontal BP | Chest | chest | 30 |
| vertical_chest_pr | Vertical Chest PR | Chest | chest | 65 |
| inclined_chest_pr_machine | Inclined Chest PR Machine | Chest | chest | 70 |
| lat_pulldown | Lat Pulldown | Lats | lats, biceps | 50 |
| pull_up | Pull-up | Lats | lats, biceps | 80 |
| cable_row | Cable Row | Lats | lats, biceps | 40 |
| dips | Dips | Lats | chest, triceps | 70 |
| bicep_curl | Bicep Curl | Biceps | biceps | 10 |
| bicep_scot | Bicep Scot | Biceps | biceps | 10 |
| tricep_down | Tricep Down | Triceps | triceps | 15 |
| tricep_overhead | Tricep Overhead | Triceps | triceps | 15 |
| dumbbell_shoulder_pr | Dumbbell Shoulder PR | Shoulders | shoulders | 15 |
| shoulder_lateral_r | Shoulder Lateral R | Shoulders | shoulders | 8 |

**Verify before building:** `abductor` and `adductor` muscle mappings, and confirm the
full mapping table against the existing `auto_counter.yaml`. Note `dips` is deliberately
`focus: Lats` (it lives in the Lats picker) but `muscles: chest, triceps` — that
mismatch is intentional in the current system and should be preserved.

Muscle groups (weekly counters): `chest, shoulders, lats, biceps, triceps, quads,
hamstrings, glutes, calves, abs`. `abs` has **no exercise** mapped — it is incremented
manually only. Confirm the exact group list against the existing `wt_sets_*` helpers.

Day-focus groups: `Lower, Biceps, Lats, Chest, Triceps, Shoulders`.

---

## 4. Data model

```jsonc
// .storage/gym_tracker
{
  "exercises": {
    "bench_press": {
      "lifetime_total": 128400,          // kg·reps, cumulative, never auto-reset
      "current": {                        // the in-progress session
        "sets": [
          { "time": "07:42", "weight": 60.0, "reps": 8, "volume": 480 }
        ]
      },
      "history": [                        // newest first; UNBOUNDED
        {
          "date": "2026-07-18",
          "sets": [ { "time": "07:40", "weight": 57.5, "reps": 8, "volume": 460 } ],
          "total": 1840,
          "max_weight": 57.5
        }
      ]
    }
  },
  "muscles": {
    "chest":  { "sets": 6, "target": 12 }
  }
}
```

`volume = weight * reps`, stored per set so deletions can subtract exactly.
Session `total` = sum of set volumes. `max_weight` = max set weight in that session.

---

## 5. Entities

Per exercise (29 ×):

| Entity | Domain | Notes |
|---|---|---|
| `number.{base}_weight` | number | User input. min 0, max 500, step 0.5, mode box |
| `number.{base}_reps` | number | User input. min 0, max 100, step 1, mode box |
| `sensor.{base}_session_total` | sensor | Today's volume. `state_class: total` |
| `sensor.{base}_session_max_weight` | sensor | Today's heaviest set (kg) — feeds ApexCharts |
| `sensor.{base}_lifetime_total` | sensor | Cumulative volume |
| `sensor.{base}_history` | sensor | **State** = number of stored sessions. **Attributes** carry the data (below) |
| `button.{base}_add_set` | button | |
| `button.{base}_undo_last_set` | button | |
| `button.{base}_finish_exercise` | button | |

`sensor.{base}_history` attributes — this replaces 21 helpers per exercise
(7 × `_sets_log` + 7 × `_session_total` + 7 × `_session_date`):

```yaml
current_sets: [ {time, weight, reps, volume}, ... ]   # today, live
sessions:                                              # newest first, ALL of them
  - date: "2026-07-18"
    total: 1840
    max_weight: 57.5
    sets: [ {time, weight, reps, volume}, ... ]
```

The dashboard slices `sessions[:7]`. **No string parsing anywhere** — the `wr()` macro,
`split('=')`, and `replace('|','\n')` in the current progress table all disappear.

Per muscle group (10 ×): `sensor.{muscle}_weekly_sets`, `number.{muscle}_weekly_target`,
`button.{muscle}_add_set`, `button.{muscle}_sub_set`.

Global: `select.active_exercise` (options = display names + `None`),
`select.day_focus`, `button.reset_today_training`, `button.reset_lifetime_totals`.

---

## 6. Operations

### `add_set(base)`
1. Read `weight`, `reps`. **Guard: both must be > 0**, else no-op (current behaviour).
2. `volume = weight * reps`.
3. Append `{time: now HH:MM, weight, reps, volume}` to `current.sets`.
4. `lifetime_total += volume`.
5. For each muscle in that exercise's `muscles`: `muscles[m].sets += 1`.
   (Compound lifts increment 2 counters — this is why `add_set` is the hook, not `finish`.)

### `undo_last_set(base)`
1. If `current.sets` non-empty → pop the last set.
2. Else → pop the last set of `history[0]` and adjust that session's `total`/`max_weight`.
   (Preserves the current fallback-to-last-session behaviour.)
3. `lifetime_total -= volume`, clamped at 0.
4. Decrement each mapped muscle counter, clamped at 0.

### `finish_exercise(base)`
1. If `current.sets` is empty → no-op.
2. Prepend to `history`: `{date: today, sets: current.sets, total: sum(volumes),
   max_weight: max(weights)}`.
3. Clear `current.sets`.
4. **Do not** touch `lifetime_total` (already accumulated per set).

> The current YAML shifts 7 fixed slots. With an unbounded list this is a single
> prepend — the whole shift chain vanishes.

### `reset_session(base)` / `reset_today_training()`
Clear `current.sets` for one/all exercises. **Does not** adjust `lifetime_total` —
matches current behaviour. Confirm this is intended (arguably a mistake in the original,
since the volume was never actually lifted if you're resetting a mis-entry — but replicate
first, change later).

### `delete_set(base, session_index, set_index)`
Removes one set from any session (`session_index: -1` = current). Subtract its volume from
that session's `total` **and** from `lifetime_total`, both clamped at 0. Recompute
`max_weight`.

### `delete_session(base, session_index)`
Remove a whole session; subtract its `total` from `lifetime_total`, clamped at 0.

### Weekly muscle reset
Sunday 23:59 local → all `muscles[*].sets = 0`. Targets untouched.
Use a scheduled callback that survives restart (the current YAML silently skips the reset
if HA is down at that minute).

---

## 7. Bugs in the current system — do NOT reproduce

1. **`debug_force_shift` desync.** It shifts only 1 history level while
   `finish_exercise` shifts 7, so running it destroys the T-2 slot and leaves T-3…T-7
   stale. An unbounded list makes this class of bug structurally impossible — there is no
   equivalent operation to port.
2. **Four disagreeing taxonomies.** `dips` is grouped under Lats in one file and
   Chest+Triceps in another; the dashboard's "Weekly Volume Targets" panel hardcodes
   `15 sets` / `21 sets` labels that do not match the live `wt_target_*` helpers. §3 is
   now the only source of truth; the dashboard must read targets from entities.
3. **Amber threshold hardcoded at `>= 10`** in the sport-tracking grid regardless of each
   muscle's real target. Expose the target so the card can compare proportionally.
4. **`reset_lifetime_totals` is a one-tap, no-confirmation wipe.** Keep the capability but
   make it a service requiring an explicit argument rather than a bare button press, or
   leave the button and let the dashboard add a confirmation.

---

## 8. First-run import

On initial setup only, read the existing helper states via the state machine and seed:

- `lifetime_total` ← `input_number.{base}_lifetime_total`
- `muscles[m].target` ← `input_number.wt_target_{m}`
- `muscles[m].sets` ← `input_number.wt_sets_{m}` (current week in progress)

**Do not import** `_sets_log`, `_last_*`, `_prev*` — history starts fresh by design.

Make the import idempotent and skip silently if the source helpers are absent (so a fresh
install on another system still works). After a successful import the old YAML package can
be deleted; the integration never reads those helpers again.

---

## 9. Services

Expose for dashboard/automation use:

```yaml
gym_tracker.add_set:            { base }
gym_tracker.undo_last_set:      { base }
gym_tracker.finish_exercise:    { base }
gym_tracker.reset_session:      { base }
gym_tracker.delete_set:         { base, session_index, set_index }
gym_tracker.delete_session:     { base, session_index }
gym_tracker.adjust_muscle_sets: { muscle, delta }
gym_tracker.reset_week:         {}
```

Buttons are thin wrappers over these.

---

## 10. Dashboard migration notes (user handles this)

The existing `dashboard-sports` view uses two `decluttering-card` templates
(`exercise_block`, `exercise_block_focus`) parameterised on `[[base]]`, so the migration is
mostly a domain-prefix swap in two template definitions:

- `input_number.[[base]]_weight` → `number.[[base]]_weight`
- `input_button.[[base]]_add_set` → `button.[[base]]_add_set`
- The 7-session progress table's 21 `states(...)` lookups → one
  `state_attr('sensor.[[base]]_history', 'sessions')` loop

**Known consequence:** `sensor.{base}_session_max_weight` is a new entity_id, so the
30-day ApexCharts history starts empty. Unavoidable when a value moves from `input_number`
to `sensor`.

**ApexCharts gotcha (existing convention):** for month-spanning graphs use
`graph_span: 6month`, `offset: +1m`, `duration: 1month` — never the `M` / `8M` shorthand,
which leaves the card stuck loading.

---

## 11. Build order

1. Skeleton: `manifest.json`, `__init__.py`, config flow (single instance, no user input
   beyond confirm), `Store` wiring.
2. Exercise config constant (§3) + data coordinator.
3. `number` + `sensor` platforms.
4. Services (§9) + `button` platform.
5. Muscle counters + weekly reset.
6. First-run import (§8).
7. Test against the live dashboard on one exercise before deleting any YAML.

Keep the old YAML package in place until step 7 passes — the integration writes to its own
storage and does not touch the helpers, so both can coexist during testing.
