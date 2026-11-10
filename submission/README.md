# Fewer dead dwarves on the long tasks: nobody fishes, and the fort shuts when hostile wildlife comes

This harness is our previous submission (the slaughter schedule that keeps food
from rotting inside the scored stretch) with two additions on the tasks without
a hands-off window, MY1 and OP1. Both are about citizens dying.

## Nobody fishes

Every training fort starts with one Fisherdwarf, the only dwarf with the
fishing labour. That dwarf does 99% of the fishing, 70 to 100 tiles from the
wagon, and is the dwarf river predators kill: in recorded games a sea lamprey
made the fisher dodge into the water and drown, and alligators come ashore.

No tool sets a labour. DFHack's autolabor gives the fishing labour to nobody
while the fort has no Fishery, and the hunting labour to nobody while it has no
Butchers. So on a fort that starts with neither workshop the controller enables
autolabor at once, builds no Fishery, and builds the Butchers three days before
the final slaughter (or at once if food runs out and an animal has to be
slaughtered early). The model's `build_workshop` calls for those two types are
refused with the reason. A fort that already has a Fishery or a Butchers is
played as before.

Drafting the Fisherdwarf was tried first and is not used: on duty a dwarf
fights where a civilian flees, and the drafted fisher was killed by an
alligator on the second day of the one test game.

## The fort shuts when hostile wildlife comes

The inherited defence sounds the civilian alert for invaders only. On one
training embark three undead harpies, which are not invaders, fly in and kill
four or five dwarves in every undefended game. Sounding the alert for them
without closing the stair is worse (9 and 14 dead in two games): the dwarves go
below and the harpies follow. With a hatch cover on the surface stair, locked
while the alert is on, nobody died in the games played with this version.

So the controller now:

- puts a hatch cover over every stair that opens on the surface, and grows the
  shelter burrow with the dug levels (both do nothing until needed);
- starts a lockdown when a hostile that is not an invader is within 100 tiles
  of the wagon, but only if every surface stair has its own built hatch, the
  shelter has room, no hostile is already inside it, and the whole observation
  could be read;
- during a lockdown sounds the alert, waits until all but one citizen are below
  (or a day), then locks each stair hatch by its own id;
- ends it when the hostile is gone or beyond 130 tiles, after 20 days (one day
  above ground follows before the fort may be shut again), when invaders
  arrive, or when the seal cannot be kept; it clears the alert first and
  unlocks only what it locked;
- steps one game day at a time while a hostile is in sight.

The model's `civilian_alert` calls were already refused. On these two tasks its
`lock_door` calls are now refused too, with the reason, whenever they would lock
a way to the surface (a call with no `door_id` locks every door; a door on a
surface stair or on the wagon's level) or would undo a lockdown. In one test
game the model locked all three stair hatches itself with one call; food, drink
and the workshops are above them. Doors of its own below the surface stay its
own.

It also raises the food level at which one small animal is slaughtered in the
last 30 days, so a fort does not sit at zero food just before the final
slaughter.

Lab tasks are untouched: every new path is behind a test for "no hands-off
window", and recorded lab games replay to identical action streams. Full source
declarations and citations are in dependencies.json.

The open-play rules (slaughter schedule, labour rule, hatches, shelter,
lockdown) are in `overseer/openplay.py`, a mixin of `Overseer`; the rest of the
controller is in `overseer/harness.py`.

The runtime uses the game API and fixed GLM gateway, standard-library Python,
and the inherited pinned Dockerfile. Tests run with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests
```
