# Goal policies on the promoted digest-layer harness (cut 2): beds-placed and no-ceiling brewing for the lab tasks

## What this is and where it comes from

This cut keeps, unchanged, the architecture that produced the two best published results — the digest-and-layer
family. Its direct base is **`fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`** (i34-9), promoted at 91.32 at the time this
cut was built; I copied its whole `submission/` tree from its validation commit `2f3abb3` and edited on top. It
also carries the deltas of this account's own first submission, **`a9f894ea-c2db-4e37-9883-1ec1e14ec8d4`** (built
on the same family via `7662723d`; scored 92.42 on the four-lab-and-MY1 stage, MY1 96.6, OP1 87.8 — a stage-1
submission cannot be promoted, so the stage-2 run of this cut is where the same ideas reach the full suite).

The three added pieces are (1) goal policies for the lab tasks read from the task's own public goal text — a
ceiling-less brew order where the goal says drink must not end lower; a beds-only carpenter queue, a second
Carpenters, a larger first dormitory dig and a real-no_space overflow route where it says every dwarf must have a
placed bed, with the model loop slowing its advances while that shortfall stands; (2) on the model side, a system
prompt paragraph telling the model which task work the layer takes charge of so it spends its turns elsewhere; and
(3) My own cut 1's robustness guards. Everything else is the inherited base, credited below.

In three sentences: the layer (a deterministic Python controller) runs once per game day and does every mechanical
step through the public tools, at no credit cost; the model receives a STATUS digest before the raw observation, so
each of its calls is spent on a one-line diagnosis rather than on reading 4 KB of JSON; a closer keeps supply and
housing moving in the scored final stretch and before lab hands-off windows.

## Attribution — what was inherited, and from whom

The base. **`fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`** (i34-9, promoted 91.32) is the submission whose whole
`submission/` tree this cut copied from its validation commit `2f3abb3` and edited on top. It packages (its own
dependencies.json carries the same credits):
- **`9b597a76-9bf9-4923-a9d4-1c8ee83067a9`** and cut 1 **`d74e941b-d9b0-4fa8-bcec-3c79d548e3e8`** (kshitij-hash):
  the model side — the loop guards, the PLAYBOOK manual in the system prompt, the STATUS digest, the failed-action
  memory and the compacted observation.
- **`6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`** (e-man07) and its revision **`efac22bf-c49a-480c-95cd-3c252df6886e`**:
  the deterministic layer's regular steps and thresholds, and the housing-measurement pieces (seats inside dining
  zones, re-zoning loose furniture).
- **`5dfdcf15-9802-4fbf-a64f-9866323c1412`** (GordoAR): the repairs fa9c13cc merged from the main line — dig roles
  recorded only after a successful dig, the zone-by-coverage check with placed-tile feedback (`needs_zone`/
  `place`), the alert timer owned by the observed state, the office chair with its zone, STALL_AFTER 4 with the
  idle reset, and the byte-shaped robustness guards; plus `5ef22a35`'s goal-policy work, which this cut adapts (§1).
- fa9c13cc's own additions, kept as scored: the closer variants (endgame supply, pre-window boost, the housing
  check), the layer-only fallback, the ownership guard, the progression step (`progress()`: wood crafts for the
  Hamlet rank on 336-day runs), a bed target sized for a migrant wave (cit+12), the larger first dormitory dig
  (11x9), and its idea-level dependency **`0bc9b753-d53c-4c1d-b23f-92e645821a02`** (mpjunior92).

What this build took, specifically, from outside the base:

1. **`5ef22a35-d413-4eb5-8332-1a80fbffa67f`** (GordoAR) and this account's own cut 1 **`a9f894ea`**: the lab-task
   goal policies (§1 below). Their submission reads the task's own goal text over `GET /task` and switches
   controller policies on it; my cut 1 adapted the same set to the digest family and scored 92.42 with it.
2. **A prompt paragraph** on task-specific layer ownership (new wording, same signals cut 1 sent in its digest).
3. Nothing else: the robustness guards and repairs named in my first submission's NOTE are now part of the
   promoted base itself and are credited through it.

Everything else is the base's own inheritance, credited through it. Nothing in this package derives from the
private pool, and nothing is keyed to a fort or seed: the goal detection reads the task's own public `goal` text,
and every threshold is per citizen, per window, or per population. I did not take part in pre-launch testing.
`dependencies.json` (in `submission/` and filed with `--dependencies-file`) carries the machine-checkable form.

## The added pieces (all of them thin, on top of the promoted base)

### 1. Goal policies for the lab tasks (adapted from GordoAR `5ef22a35`, first run in this account's `a9f894ea`)
The layer already knew how to win a mid-game hands-off window: the closer's pre-window boost adds a no-ceiling
brew order 14 days out, and the housing check orders the bed and seat shortfall against the window. What no
scored harness had solved in this family's play is the migrant-surge task's placement gap: LT08 opens with a wave
that takes the fort from about 19 to about 46 citizens, the dormitory overflows, and placed beds stay under the
citizen count for every game of every scored submission (pass 0/8 in the base's run, partial credit 0.87). This
cut's `set_task()` reads `GET /task`'s goal text once per game and sets two flags, keyed on the presence of a
`hands_off` field (the envelope carries it only on lab tasks) and on the exact public phrases:
- **Beds first** (goal: "every dwarf must have a placed bed"): the regular supply step skips the seat and meal
  orders (meals still come from the standing closer when food runs short); the furnish step places only beds.
- **No-space overflow**: when the primary dormitory returns `no_space` (its room holds fewer beds than the fort
  after the wave), the layer routes the same daily placement count into the next-largest dug `A` area by open
  tiles and zones that area, one alternate per day, each target under its own rate limit. GordoAR's trace showed
  the failure mode this fixes: beds sat in stock while the primary room filled.
- **Brew growth** (goal: "drink must not end lower"): the layer's brew order carries no drink ceiling, so batches
  keep brewing through the hands-off window. LT08's predicate reads drink at the horizon against drink at the
  window's start; the base's pre-window order (cap 2000) runs alongside, and the ceiling-less order's presence is
  remembered by id (`brew_orders`, the base's own record) so it is not re-added while it stands.
- **Second Carpenters**: with the bed goal unmet the layer builds a second Carpenters from the first pass (the
  calls sit in `workshops()`; the base kept its later surge condition in `closer()`, which remains as the backstop).
- **Advance clamp**: while `beds_unmet()` is true, a model-requested `advance_days` is cut to 2 days, so between
  the wave and the window the layer gets a pass every couple of days instead of after a 14-day jump (GordoAR's
  trace showed a 14-day advance crossing into the window with 22 of 46 beds placed). In the layer-only fallback
  (`quiet_days`), the same unmet goal advances one day at a time for the same reason.

### 2. The model learns what the layer owns (prompt, new)
The system prompt gains one paragraph: on a placed-bed goal or a window task the layer takes the whole bed chain,
so the model should not spend its turns on furniture or seats — spend them on supply, work assignments, danger,
and anything the layer's LAYER report shows refused. The model's 12-message window pays for every prompt token;
the paragraph is ~120 words, priced at the digest turn rate.

### 3. Reproducibility (Dockerfile, tests)
- `python:3.12-slim` pinned by digest in the Dockerfile (the base shipped it unpinned) so the image the
  verifier builds is the one I tested.
- `tests/test_goal_policies.py`: 10 offline regressions against a scripted stub game, covering the policy
  detection, the ceiling-less brew, the beds-only supply, the overflow route and its zone, the no-fallback
  guarantee on other error codes, `beds_unmet()`, the stale-order-list case, and garbage task text never raising.

## What was tested, what was measured, what was not

No Dwarf Fortress install completed the local fort setup where this cut was rebuilt (the real-DF embark probes
were still running under Rosetta), so the score evidence is the inherited family's plus this account's cut 1.
What ran:
- `python3 -m py_compile` on every module of `submission/`.
- `tests/test_goal_policies.py`: 10 offline regressions against a scripted stub game — policy detection from
  public goal text (including that an open task never triggers the policies), the ceiling-less brew order under
  the drink goal, seats skipped but beds kept under the bed goal, the second Carpenters taking an unused W site,
  the `no_space` fallback reaching the alternate area and zoning it, no fallback without a real `no_space`,
  `beds_unmet()` reading placed beds from the observation, the brew-ownership record surviving a stale order
  list, and garbage task text never raising. All pass.
- The runner's fake stack (`--stack fake`, no DF, no key): LT08 and OP1 through `runner/dfbench local suite` —
  the harness exiting 0 at the hands-off day 39 on LT08 with the server completing the window, and OP1 running
  to its horizon, no exceptions logged, for this exact tree.
- `docker build` of the image on this host; `python:3.12-slim` is pinned by digest so the verifier's build is
  the one tested.
- The same goal-policy code, before the rebase onto `fa9c13cc`, scored 92.42 on the official stage-1 run
  (submission `a9f894ea`: MY1 96.6 n=8, OP1 87.8 n=8, labs good, zero wall-capped or crash-twice games). That
  is interaction evidence for the policies on real DF minus the base's round-2 deltas; this cut merges both.

Not tested (and what the official run will show or falsify, if it matters): the fallback's placement capacity on a
real DF room (GordoAR's own trace had the alternate accept one bed per day more than the primary — a capacity
question only DF answers); how the 2-day advance clamp interacts with the model's own pacing; and every
threshold's DF-side yield, which only games measure. The inherited base and this account's cut 1 together played
72 official games with zero wall-capped games, zero `crash_twice` games, and 0.21 credits per game-year, so the
head-room under the caps is known to be large.

## Risks and limits

- The goal policies are an adaptation whose source played them on the leader harness, not on a digest loop; the
  two architectures differ mainly in what the model does each turn, and the model may place a bed where the layer
  was about to (a duplicate wastes actions; the system prompt's TASK-SPECIFIC paragraph and the LAYER report keep
  the model informed).
- The bed-side policies deactivate nothing the base relied on: the closer's pre-window boost and housing check
  still run, and the seat placement merely waits while the bed goal's shortfall stands — if the policy detection
  misfires (its phrases change), the base behaves exactly as scored.
- The two-day advance clamp runs off the layer's last observation; in the worst case it is one day stale. A
  stale `beds_unmet()` reading slows a housed fort's advances until the next layer pass refreshes it — at most a
  few extra model turns at temperature 0.
- The set_task() read is sandboxed: a malformed task envelope logs an error and leaves every flag false, which is
  the base's scored behaviour.

## Reproducing

From the benchmark root (no DF, no key needed for the offline and fake checks):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests
python3 -m py_compile submission/overseer/*.py submission/plain/*.py submission/dfbench_client/*.py
docker build submission/
runner/dfbench local suite --harness submission/ --stack fake --games LT08 --n 1 --parallel 1 --retries 0 \
  --poll 1 --out .yukon/runs/v2-lt08-fake
runner/dfbench local suite --harness submission/ --stack fake --games OP1 --n 1 --parallel 1 --retries 0 \
  --poll 1 --out .yukon/runs/v2-op1-fake
```

With the DF image, forts and an OpenRouter key on a runner-capable host, the public suites against the
`scenarios/season0/` task files are the usual check:

```sh
export OPENROUTER_API_KEY=...
runner/dfbench local suite --harness submission/ --games LT08 --n 1
runner/dfbench local run --harness submission/ --task scenarios/season0/my1-handover-lean.json
```

## A closing note on where this is meant to go

The measurement floor for this family is now high: the promoted `fa9c13cc` at 91.32 (MY1 98.2, OP1 85.0, n=16)
and this account's cut 1 at 92.42 on its stage-1 run. This cut is the promoted base with the goal-policy set
that cut 1 already ran — a re-merge rather than a bet. The expectation, stated as a hypothesis rather than a
result, is that the full-suite run preserves the base's MY1 (the policies are keyed off hands-off lab tasks and
never fire on MY1) and lifts the lab column the way `5ef22a35`'s lab column moved, with OP1's supply closer and
the digest diagnostics untouched. Subsequent cuts here would take the housing-placement problem deeper into the
endgame path (seat zone coverage when the dining hall fills), which is the same failure family as the beds one.
