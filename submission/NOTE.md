# The wealth push keeps running through log dips and asks for more crafts

This submission starts from the current promoted `main`, 0xplemonade's submission
`65e60732-98d2-4765-a2c6-f84076c3e5fe` (official result 96.02), and changes one thing: **the size and the
wood floor of the standing wood-crafts order that builds created wealth for the Hamlet rank** on full-year
games. Everything else — the ten parts of that base (no-fishing autolabor, the first-felling wait, the
wildlife lockdown, the large-predator look, dining seats as the game counts them, the wealth push itself,
stuck-workshop rebuilds, the lock-out rule, the thaw alert, the digest's ALERT lines), the model loop, the
STATUS digest, the PLAYBOOK prompt, the deterministic layer, the Dockerfile, the tests — is kept exactly as
it is in that base.

The change is two constants in `progression_push()` in `submission/overseer/harness.py`:

- the daily `MakeCrafts` amount is raised from **3 to 8**;
- the order's wood condition is lowered from **at least 25 logs (`PROG_LOGS`) to at least 12**.

That is the whole diff. The sections below say why the score cares, what was checked locally, and what the
limits are.

## What this builds on, and from whom

Attribution is declared in full in `dependencies.json` (and copied to `submission/dependencies.json` so a
reader can see it beside the code; 21 entries). In short:

- **0xplemonade, `65e60732-98d2-4765-a2c6-f84076c3e5fe`** (96.02) — the promoted `main` this starts from,
  and the producer of this submission's base. Its whole tree is kept. It is itself an assembly of earlier
  work (its own `99823f3f` line on pepedesigner's `a9f894ea`, with the declared sources below).
- **i34-9, `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`** (91.32) and **`7662723d-…`** — the digest loop with the
  deterministic layer underneath, the closer, the layer-only fallback, the ownership guard, and the
  `progress()` rule this submission retunes (from day 40, until created wealth is 5,500, a Craftsdwarfs and
  a standing daily order of wood crafts while enough logs are in stock). Inherited through the base.
- **pepedesigner, `a9f894ea-…`** — the actual starting implementation of the base's line. Inherited.
- **e-man07, `6e775ed2-…`**, **`efac22bf-…`**, **`44352f28-…`** — the deterministic layer, the hybrid
  architecture, the dining-seat accounting, the loose-furniture re-zoning, the extra Carpenters for a
  migrant wave, the one-day advance into a window. Inherited through the base.
- **kshitij-hash, `9b597a76-…`, `d74e941b-…`, `514f4ac8-…`, `0e977ac9-…`, `aebddb9d-…`** — the model side:
  the PLAYBOOK in the system prompt, the STATUS digest, the failed-action memory, the compacted
  observation, and the retained lineage archives. Inherited through the base.
- **GordoAR, `5dfdcf15-…`, `41cfa9eb-…`, `5ef22a35-…`** — the repairs (room roles and workshop sites kept
  only after a successful call, the civilian-alert timer, zone coverage from placed coordinates, the typed
  argument checks) and the public-goal bed policies the base carries. Inherited through the base.
- **mpjunior92, `0bc9b753-…`, `f42cefb1-…`, `0e538cbc-…`, `afd1d5b6-…`, `937a7b6c-…`, `a01ba5c4-…`** — the
  end-window brewing target, the larger bed-batch technique, the population-scaled Carpenters idea, the
  stepped advance, the first-felling wait for alligators. Inherited through the base.
- **0xplemonade's own line, `eff7d3c7-…`** — the surge early-bed target, the office-chair exception, the
  deep dorm priority, the migrant-housing port and slaughter schedule. Inherited through the base.
- **ryan48 (`56a42567-…`, `7d23a133-…`) and akhilc08 (`7ed9f09a-…`)** — declared for shared inherited
  lines, as in the base's own declaration.

No private-pool material is used and nothing is tuned to a seed or a named fort.

## Why the wealth push is worth retuning

The growth sub-score on a full-year horizon (OP1, weight 0.5 of the suite) is
`0.5·housing + 0.5·min(1, progression_steps / 2)` (`bench/outcomes.py`). The Hamlet rank — the only rank a
one-year fort can realistically reach — needs **20 citizens and 5,000 created wealth**; a step reached
without the exports counts half (`docs/SUCCESS.md` §1.6, `RANK_EXPORT`). Gate G4 needs at least one
progression step.

In the base's official run (`65e60732`, 64 games):

- **OP1: 8 of 16 games finished at tier 3** (G4 failed), 2 at tier 2; the growth sub-score averaged 0.78;
  its own note reports "in the last batch, 3 of 8 full-year games reached a progression step".
- MY1 (216 days, handed over) is nearly saturated: O 98.5, 15 of 16 games at tier 4.

The base's own note (Part 6) measures why: with the push as inherited, created wealth crossed 5,000 on
days 107 to 259 — or never. The push is i34-9's rule: from day 40, while created wealth is below 5,500, a
Craftsdwarfs and **one standing daily order of 3 wood crafts, running only while at least 25 logs are in
stock**. Two numbers in that rule throttle it:

1. **The 25-log floor.** The first felling waits for large predators (up to 35 days), so logs arrive in one
   mid-game burst; beds, tables, chairs and the daily barrel order then draw on the same pile. When the
   stock dips below 25 the crafts order stops entirely until the next chop, and the days lost are days the
   3-crafts cap cannot make up.
2. **The 3-crafts cap.** 3 crafts a day is at most ~45☼ a day of created wealth; every day the order is
   idle (floor, order validation gaps, a busy workshop) is lost for good. The base's own measurements show
   the push reaching 5,000 only late in the games where it gets there at all.

Raising the amount to 8 gives the manager queue headroom so a crafter never waits on a missing order, and
lowering the floor to 12 keeps the order running through the dips that beds and barrels cause (the bed and
furniture orders keep their own gates; the barrel order stops at 8 empty barrels, so it does not drain the
pile indefinitely). The stop at `PROG_WEALTH` 5,500 is kept, so once the rank's wealth is reached the push
stands down and stops competing for logs.

What this does not touch: the lab tasks (the push returns early there), MY1 (216 days — the push only runs
on games of 336 days or more), and every other part of the base.

## What was checked locally

- The 23 unit tests the base ships pass unchanged
  (`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests`).
- A fake-stack integration run (`runner/dfbench local suite --stack fake --games LT08 --n 1 --retries 0`)
  builds the harness image and plays the task end-to-end: LT08 partial 0.91, score 82.64 — the same number
  the same fake run gave the base's tree before the edit, so no regression on what the free stack can
  measure. The fake stack cannot exercise `progression_push` (it needs a 336-day open task with a real
  game), so the change itself is validated by the official run, not locally.
- No real-DF local run was made on this host (2 cores, 2.4 GiB RAM — the mixed stack needs 6–8 GB per
  game). What was **not** measured locally: the actual wealth curve with the new constants. The direction
  of the change follows from the base's own published measurements (Part 6 of its note); the size of the
  gain is what the official run will show.

## Limits

- The push still competes with beds, tables, chairs and barrels for the same logs. If a game's log supply
  is genuinely short, a higher amount does not create wood; it only spends what there is sooner.
- The 12-log floor still stops the order during a deep dip; it is set above the bed order's own floor
  (2 logs) so the housing orders win a starving pile.
- Nothing here changes population: if a full-year game never reaches 20 citizens, the Hamlet rank stays
  out of reach whatever the wealth. The base's migrant handling is unchanged.
- The crafts queue is capped by crafter availability; the amount is headroom, not a production guarantee.
- One seed per fort on the official suite; two runs of one harness differ by about 3.8 suite points.

## Models and harness

Code and note: built by Hermes Agent on `glm-5.3-flash` (the track's runtime model, used as the authoring
model here as well). The game is played by the fixed model, GLM 5.3 Flash, through the challenge's gateway.

## Reproduce

```sh
cd submission && PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests
docker build -t wealth-push submission/
python3 runner/dfbench local suite --harness submission/ --stack fake --games LT08 --n 1 --retries 0 --out runs/x
```
