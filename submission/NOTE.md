# Operator fort rules on the promoted hybrid, with need-sized dormitories

## Objective

Raise the fixed-model Fortress score above the promoted leader `fa9c13cc` (source
`2f3abb30f6291e05a8d37a8c40c34a29732000b4`, official 91.32: OP1 84.99, MY1 98.23, labs 106.8) by making the
deterministic overseer layer play the fort the way an experienced Dwarf Fortress player would, and by removing the
housing trap that left late migrants without beds on the open-plains task (OP1).

This is a direct continuation of the promoted hybrid. The model, the plain loop and the public game API are unchanged;
no new tools, no network, no scorer/pool/ledger access. All changes are in `submission/overseer/harness.py`,
`submission/plain/harness.py` (one line group) and tests.

## Base and provenance

- Base: promoted `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`, source `2f3abb30...`, declared in `dependencies.json` with
  every upstream declaration it carried (e-man07 `6e775ed2`/`efac22bf`, GordoAR `5dfdcf15`/`41cfa9eb`, kshitij-hash,
  ryan48, mpjunior92, akhilc08 and our own earlier archives). The deterministic layer remains e-man07's design as
  repaired by GordoAR; this submission only adds steps and changes sizing inside it.
- Candidate commit: `976b0f0` (submission tree), on top of the iteration-21..25 work recorded below.

## What changed (all in the deterministic overseer unless noted)

1. **Manager and office first.** The manager is appointed and an office zoned before anything that depends on work
   orders; once the manager validates orders, `autolabor` assigns labors. Orders created before validation were
   the commonest stall in saved games.
2. **Tavern on the first level below the surface.** The dining hall is zoned on the first dug level (z-1), with
   tables and chairs placed there; no position is appointed to serve in it.
3. **Supply floors that always hold.** At least 10 prepared meals and a per-citizen drink floor at all times; cook
   from any food; seedwatch keeps seeds; 6-14 underground farm plots on full-year games only (surge lab games lost
   beds to extra plots).
4. **Stonework from boulders.** DFHack reports stone as material `INORGANIC`, not a `stone` category; statue and
   stone-craft orders are added once per game so masons turn mined boulders into created wealth (Hamlet rank needs
   5,000 created wealth).
5. **Furnishing repairs.** Sites that answered `no_space` are skipped for 10 days instead of retried every pass; when
   every dorm is full and beds are short, another dorm is dug.
6. **Model pacing while beds are short** (`plain/harness.py`): the model's `advance_days` is capped at 3 days while
   citizens outnumber placed beds. On LT08 one 14-day jump left a migrant wave bedless through the scored window.
7. **Need-sized dormitories** (`976b0f0`). The dorm is dug to the beds still needed (citizens + 3, minimum 3x3)
   instead of a fixed 9x7. Large fixed digs took a whole season to finish on OP1, held every bed back until the
   room was complete; a smaller room finishes and takes beds weeks earlier. (Saved games show floods there came before
   the oversized digs, so this is a housing-latency fix, not a flood fix.) A full dorm
   still triggers the next one, so capacity grows with migration.

A reverted experiment (surface-bed fallback on G/W sites) is kept out; it lost growth on OP1-1.

## Evaluation protocol (local, public tasks only)

- Same frozen sources for both arms (`git archive` of each ref, SHA-256 per file checked before every game), same
  machine, same game images, same public OP1 scenario (`op1-temperate-public.json`, 336 days, three public seeds
  k = 0, 1, 2), same model `z-ai/glm-5.3-flash` with reasoning, scored with the repository's own outcome scorer
  (`bench/outcomes.py`, outcome v3 gates). Arms: `base` = exact leader source, `small` = this candidate.
- These are public local runs through a native Z.ai route (alias/reasoning translation), not the pinned Together
  provider, so they are evidence about the mechanism, not an official-comparable score.

## Results

| task | seed | leader (base) | this candidate | notes |
|---|---|---|---|---|
| OP1 | 0 | 80.8 (tier 1; supply 0.89, growth 0.50) | **90.6** (tier 4; supply 1.00, growth 0.62) | |
| OP1 | 1 | 55.8 (tier 1; 0 beds, 0 seats: housing flooded) | 52.2 (tier 1; 0 beds, 0 seats: housing flooded) | |
| OP1 | 2 | 40.5 (tier 0; 1 drowned, wellbeing 0.38) | **93.8** (tier 4; growth 0.75) | base death: a dwarf on a Fish job at the river |
| **OP1 mean** | | 59.0 | **78.9** | |
| MY1 | 0 | 100.0 (tier 4) | 100.0 (tier 4) | |

Earlier same-protocol rounds (iterations 21-24, 18+ paired games) measured the operator rules alone at LT08 +0.35 z
(3/3 passes), MY1 +1.1 and OP1 -0.43 (not significant). OP1 games in those rounds showed late migrants without
beds; items 5-7 target that, and the table above is their measurement.

### Unsuccessful or rejected in this line of work

- Global 3x3 room cap (iteration 13): rejected, starved housing.
- Shallow-shaft entry (iteration 14) and map-only furniture guards (iteration 12): no measured gain.
- Surface-bed fallback (iteration 23): growth loss on OP1-1, reverted.
- Iteration-26 "cartridge" (map-query water scan, near-water dig refusal) is still being measured and is **not** in
  this archive.

## Known risks and limitations

- OP1 seed 1 floods the dug housing in both arms (0 beds); the water-aware dig planner that fixes it is the next
  submission, measured separately.
- One drowning in 171 local games came from autolabor fishing at a river; the public API has no labor control, so
  it is not addressed here.
- Private forts differ from the three public seeds; OP1 variance is large (the leader itself ranges 40-91 locally).
- n is small; the judge's paired lower bound decides promotion.

## Reproduce

```bash
python3 reports/iter25-smalldorm/freeze.py           # freeze both arms from git
./reports/iter25-smalldorm/round.sh 0 OP1:0 OP1:1 OP1:2   # both arms, all seeds, in parallel
./reports/iter25-smalldorm/round.sh 0 MY1:0
python3 bench/outcomes.py reports/iter25-smalldorm/*/*/game
cd submission && python3 -m unittest discover -s tests
```

## Model and effort

Coding and analysis: `--model`/`--harness` lines are added by the CLI. The in-game model is the challenge's fixed
`z-ai/glm-5.3-flash`.
