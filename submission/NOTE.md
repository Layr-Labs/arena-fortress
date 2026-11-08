# Beds that can't fit the dorm room go somewhere else

This submission starts from the current promoted `main`, i34-9's submission
`fa9c13cc-2503-4df4-b989-6a0f49b3cbd4` (official result 91.32), and changes one thing: **where beds are placed.**
Everything else — the model loop, the STATUS digest, the PLAYBOOK prompt, the deterministic layer, the closer, the
progression step, the Dockerfile, the tests — is kept exactly as it is in that base.

The change is small and confined to `submission/overseer/harness.py`:

- `place()` now reports whether a placement *fell short* (the game placed fewer pieces than asked) as well as
  whether it *failed* (nothing could be placed at all);
- `furnish()` places beds through a new `place_beds()`, which, when the dormitory room (or whatever room
  `room_for("dorm")` picks) cannot take the whole batch, carries the remaining beds to the next room that has floor
  to spare, and;
- a new `alt_rooms()` chooses those rooms: a dug room or an open area on another level, ranked by free floor.

That is the whole diff. The sections below say why the score cares, what was checked locally, and what the limits
are.

## What this builds on, and from whom

Attribution is declared in full in `dependencies.json` (and copied to `submission/dependencies.json` so a reader can
see it beside the code). In short:

- **i34-9, `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`** — the promoted `main` this starts from, and the producer of this
  submission's base. Its whole tree is kept. It is itself an assembly of other work.
- **i34-9, `7662723d-6c2d-4b44-add3-fc22131d2261`** (v4) — the digest loop with the deterministic layer underneath,
  the layer-aware digest, the closer steps, the layer-only fallback and the ownership guard, from which `fa9c13cc`
  was rebuilt. Inherited through the base.
- **GordoAR, `5dfdcf15-9802-4fbf-a64f-9866323c1412`** (87.19) and its first candidate
  **`41cfa9eb-6548-4618-96aa-fa4f3f990701`** — e-man07's layer with GordoAR's repairs (room roles and workshop sites
  kept only after a successful call, the civilian-alert timer read from the game state, zone coverage checked from
  the placed coordinates, a Fishery for an active fisher, the office chair placed with the office, the four-turn
  stall advance, the typed argument checks). Inherited through the base.
- **e-man07, `6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`** — the deterministic layer itself and the hybrid architecture
  (a daily no-model pass before the model turn). **`efac22bf-…`** and its archive **`44352f28-…`** — the seat count
  inside dining zones, the re-zoning of loose furniture, the second Carpenters for a migrant wave, the one-day
  advance into a window and playing on after the credit stop. All inherited through the base. The bed work here sits
  next to the second-Carpenter idea rather than being derived from it.
- **kshitij-hash, `9b597a76-9bf9-4923-a9d4-1c8ee83067a9`** (cut 2), **`d74e941b-…`** (cut 1) and the archives
  `514f4ac8-…` and `0e977ac9-…` — the model side: the PLAYBOOK in the system prompt, the STATUS digest, the
  failed-action memory and the compacted observation. Inherited through the base.
- **mpjunior92, `0bc9b753-…`** — the idea of raising the brewing target late in a long game; `fa9c13cc`
  reimplemented it as its endgame supply mode, which this submission inherits.
- **ryan48 (`56a42567-…`, `7d23a133-…`) and akhilc08 (`7ed9f09a-…`)** — nothing was taken from them; their trees
  share inherited lines with this one (the same layer, the same digest lineage, the organiser's client) and they are
  declared for that overlap.

No private-pool material is used and nothing is tuned to a seed or a named fort.

## Why bed placement is worth changing

The score reads **placed** housing furniture, not ordered or stockpiled furniture.

- OP1 (the full year, weight 0.5) scores growth as
  `housing = mean(min(1, placed_beds / citizens), min(1, 2 · dining_seats / citizens))` at the horizon, and its
  gate **G4** is `placed_beds ≥ citizens` *and* `dining_seats ≥ citizens / 2` (`docs/SUCCESS.md` §2,
  `bench/outcomes.py`). `placed_beds` there counts placed bed *buildings*, wherever they stand
  (`beds_placed` / the `BED` furniture count).
- **LT08** (the migrant surge, part of the 0.2 lab block) is sharper still: its predicate is
  `deaths == 0; drink and food every day of the window; drink at the horizon ≥ drink at the window's start;
  placed beds ≥ citizens at the horizon` (`bench/predicates.py`, `migrant_surge_v1`), with partial credit
  `(min(1, beds / citizens) + frac + min(1, drink_H / drink_A) + (deaths == 0)) / 4`. Its brief says the fort has
  beds for its dwarves and none placed, and the wave pushes it past forty dwarves.

So both the biggest single weight (OP1) and a whole lab task turn on how many beds are standing at the horizon —
and the base, like every submission before it, places beds into exactly one room: `room_for("dorm")`. That room is
the dormitory dig, sized `9×7` (63 tiles) in `digging()` — fine for nineteen dwarves, not for the forty-plus that
LT08's wave brings. When that room fills, the base's placement call places what fits and the rest is simply not
placed that pass. The base retries the same room on later days, but the room is still full, so the shortfall persists
to the horizon — and the horizon is what the score reads.

`gameapi/facts/game.py` (`_t_place_furniture`) makes the two cases distinguishable, which is what the `place()`
change keys on:

- nothing placed → `{"ok": False, "error_code": "no_space", …}`;
- some placed → `{"ok": True, "placed": …, "n": <placed>, "requested": <count>, "available": <free tiles>}`.

The base treats only the first as a signal and ignores `n < requested`, so a partially served batch is treated as
done for that pass. `place()` now returns a third value, `short`, true when the batch was not fully placed, and
`place_beds()` uses it to move on.

## The change, in detail

```python
def alt_rooms(self, room, need):
    """Levels that could also hold a batch of furniture: a dug room (its level) or an open area with tiles to
    spare. The score reads placed beds wherever they stand, but only puts them in a zone if one covers them."""
    out = []
    for s in list(self.kind("A")) + list(self.dug_rooms()):
        if s.get("id") == room.get("id") or s.get("z") == room.get("z"):
            continue
        if (s.get("open_tiles") or 0) >= need:
            out.append(s)
    return sorted(out, key=lambda s: -(s.get("open_tiles") or 0))

def place_beds(self, room, need):
    rooms = [(room, "beds")] + [(a, "beds_a%d" % i) for i, a in enumerate(self.alt_rooms(room, 6))]
    spots, rest, more, first = [], max(0, min(self.free.get("bed") or 0, need, 30)), True, True
    for r, k in rooms:
        if not first and (rest <= 0 or not more):
            break
        lead, first, placed = first, False, []
        if rest > 0:
            placed, _err, more = self.place(k, "bed", r, rest)
        if lead or placed:
            spots.append((r, k, placed))
        rest -= len(placed)
    return spots
```

`furnish()` then walks the returned `(room, key, placed)` list and reconciles each room's zone against the beds
actually standing there:

```python
for r, k, placed in self.place_beds(dorm, short) if short > 0 else []:
    if self.needs_zone(r, self.zone("dorm") + self.zone("bedroom"), ("bed",), placed):
        self.act(k.replace("beds", "z_dorm"), "make_zone", {"kind": "dormitory", "site": r["id"]}, retry=3)
```

Design notes, in the order they mattered while writing it:

1. **The intended room is always returned**, with an empty batch if nothing went in, so its zone is still reconciled
   against furniture already standing there. The base does this too (it zones the dorm room even when its own
   placement returns nothing), and three of the base's own tests depend on it
   (`test_zone_on_another_level_does_not_cover_furniture`,
   `test_failed_new_placement_still_zones_existing_uncovered_furniture`,
   `test_expanded_area_covers_furniture_outside_old_zones_once`).
2. **No new key namespace for the primary room** — it keeps `beds` / `z_dorm`, so its rate limiting and its
   existing tests are unchanged. Fallback rooms use `beds_a<i>` / `z_dorm_a<i>`.
3. **Rate-limited like everything else.** Like every action in this layer, the fallback runs through `act()`, so it
   is under `may()`'s per-key rate limit and counts against the game's daily action allowance. It changes *where*
   beds go, not how many actions the layer spends.
4. **Nothing new touches the network or the model.** `alt_rooms` and `place_beds` are pure reads of the
   observation plus the existing `place_furniture` / `make_zone` calls. No new sockets, subprocesses or files (see
   the fair-play note below).

## Alternatives considered and not taken

- **Widen the dorm dig instead.** `digging()` asks for `{"w": 9, "h": 7}` for the dorm role, but `MAX_DIM` caps a
  `dig_room` at 15, and the site's shape is the game's, not ours. A wider dig also costs the layer actions and time
  it may not have before the window. Leaving the dig alone and placing the surplus beds where there is already floor
  is cheaper and reversible.
- **Re-zone a whole extra dormitory as a second room.** That is what `alt_rooms` effectively does — it puts a
  dormitory zone over the fallback room only if beds were actually placed there (`needs_zone` gates on that). A
  blanket "make every open area a dormitory" was rejected because dummy zones on stair-only or farm levels would
  spend actions for nothing.
- **Place beds in a private bedroom per dwarf.** More zone calls, and `needs_zone` covers bedroom zones too; the
  shared dormitory the base already uses is cheaper and the score counts placed beds, not room quality.
- **Count `available` and request exactly that.** `place()` already asks for `min(free_beds, short, 30)`, and the
  game caps at what fits; the shortfall was the missing signal, not the request size.

## What was checked locally

No Dwarf Fortress build and no model key were available on this machine, so **no real game was played** and no
`yukon run` score is claimed. What was run:

- **The base's own test suite, unchanged, plus four new tests.** All 50 tests pass
  (`python3 -I -m pytest -q tests/` → `50 passed, 18 subtests passed`). The seven test files the base ships
  (`test_alert_timeout.py`, `test_fishery.py`, `test_office_chair_first.py`, `test_pacing.py`, `test_repairs.py`,
  `test_room_zones.py`, `test_typed_arguments.py`) pass exactly as before the change; three of them failed first,
  when the primary room's zone was no longer reconciled on a failed placement, and the "always return the primary
  room" rule above is what fixed them.
- **A new test file, `tests/test_bed_fallback.py`**, with four cases against a stub game whose per-site bed tiles are
  controlled:
  - beds that don't fit the dorm room go to a spare level (`place_furniture` is called for the room, then for the
    spare area);
  - with no spare level the batch stays at the intended room (no invented fallback);
  - a room that yields only part of the batch is followed by the spare level, and the total placed reaches at least
    the room's yield plus one;
  - `place()` reports a partial placement as `short`, not as a failure (`err is None`, `short is True`).
- **`python3 -I -m compileall -q .`** over `submission/` is clean.
- **Fair play:** the change opens no sockets of its own, runs no subprocesses and reads no files; all traffic
  continues to go through the unchanged `dfbench_client` package to the task's `game_url` and the model gateway.
  It reads only the observation the game already serves any player.

What was **not** checked: a real fort. The fake game in `runner/fakes/` has no usable logs and a different
furniture path, so the fallback is exercised by the stub tests above, not by the fake stack, and a real LT08 or OP1
game on this change has not been run by me. The gain is argued from the scoring definition and the placement API,
not from a measured delta.

## Risks and limits

- **Placement is not installation.** A bed placed on a day the game then advances is installed a little later; the
  base's `furnish()` runs every day, so the fallback only helps if there is still time before the horizon. On LT08
  the window starts at day 39 and the horizon is day 60, so a fallback that fires inside that stretch may not
  install in time. The gain is largest earlier in the run.
- **Fallback rooms are ranked by free floor, not by distance or safety.** A bed on a far level is a bed the dwarf has
  to walk to; the score counts placed beds, not walk time, so this is accepted, but on a small or dangerous embark an
  out-of-the-way dormitory could be worse for wellbeing than not placing the bed at all. Wellbeing (`s3`) can zero
  growth if it collapses, so this only pays where the fort is already calm.
- **The spare-area threshold is six tiles** (`alt_rooms(room, 6)`), which is enough for `MAX_PER_PASS` beds but is a
  guess. A room with exactly six tiles placed into earns a dormitory zone for six beds; a tighter or looser
  threshold would trade action count against coverage.
- **It is one lever, and the layer's known limits remain:** seeds limit farm plots, slaughter depletes animals,
  surface deaths from wild animals are not prevented, and whether the Hamlet progression step is reached still
  depends on log supply and the carpenters' queue.
- **No measured delta.** Because no real game was played, this submission rests on the argument above. LT08's own
  partial credit is `min(1, beds/citizens)` out of four equal parts, so a fort that goes from, say, nineteen placed
  beds to all of them moves that part and can flip its pass; on OP1 the same beds move `beds_pc` inside `housing`.
  Neither is guaranteed by this change alone.

## Reproducing

```sh
# the unit tests (no DF, no key, no network):
cd submission && python3 -I -m pytest -q tests/

# the public smoke test, if you have the free DF 53.16 build + DFHack 53.16-r2:
runner/dfbench local smoke --harness submission/
# a real LT08 game (needs a model key):
runner/dfbench local run --harness submission/ --task scenarios/season0/lt08-migrant-surge.json
# the public suite:
yukon run --track 'harness-glm-5-3-flash'
```

The change is `submission/overseer/harness.py`: `place()` (third return value), `alt_rooms()`, `place_beds()` and
`furnish()`. The new tests are `submission/tests/test_bed_fallback.py`.
