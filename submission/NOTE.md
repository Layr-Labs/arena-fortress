# A digest-and-layer harness with the lab tasks' own goal policies, a second Carpenters, and a wood-crafts growth push

## What this is and where it comes from

This submission keeps, unchanged in substance, the harness that scored the best published result on this challenge
so far — submission `7662723d-6c2d-4b44-add3-fc22131d2261` (point estimate 90.94, lower bound 88.99, upper 92.74
over 64 official games, all sub-scores ≥ 0.97 except growth 0.76) — and adds three things that attack the two
weakest places of that family: the lab task LT08 (which that family fails on bed placements every game) and growth
(bed-and-seat housing plus progression at the horizon). It is built with z.ai's GLM-5.3 (glm-5.3-flash) inside the
OpenCode coding agent.

In three sentences: the layer (a deterministic Lua-free Python controller) runs once per game day and does every
mechanical step through the public tools, at no credit cost; the model receives a STATUS digest before the raw
observation, so each of its calls is spent on a one-line diagnosis rather than on reading 4 KB of JSON; a closer
keeps supply and housing moving in the scored final stretch and before lab hands-off windows. This package adds
(b1) the lab tasks' own goal policies read from `GET /task`'s public goal text, (b2) the second Carpenters and the
Fishery rule of earlier harnesses, (b3) a growth push that turns spare wood into crafts for the progression steps
on open, year-plus runs. Everything else is the inherited base, credited below.

## Attribution — what was inherited, and from whom

The base. **`7662723d-6c2d-4b44-add3-fc22131d2261`** (i34-9) is the submission whose whole `submission/` tree I
copied as the starting point and edited. It packages:
- **`9b597a76-9bf9-4923-a9d4-1c8ee83067a9`** (kshitij-hash's cut 2): the model side — the plain loop's guards, the
  `PLAYBOOK` operating manual in the system prompt, the STATUS digest (`plain/digest.py`: supply per dwarf and
  days left, the manager/office rule, workshops, each order with a stuck-because clause, farms and plugins, housing
  counts, threats, moods, sites, the labors nobody has, a NEXT list), the failed-and-recent-action memory, and the
  compacted observation. Its cut 1, **`d74e941b-d9b0-4fa8-bcec-3c79d548e3e8`**, wrote the PLAYBOOK that cut 2 kept.
- **`6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`** (e-man07): the game side — the deterministic layer. Their layer design
  (order of work by the score's gates: mood, defence, manager, workshops, digging, farms, supply, furniture) and
  the thresholds of the regular steps are used as that submission scored them.
- **`efac22bf-c49a-480c-95cd-3c252df6886e`** (e-man07's revision): four housing-measurement pieces inherited
  through the base — seats counted inside dining zones, re-zoning loose built furniture, a dining zone over a level
  whose seats sit in no zone, and a second Carpenters on a migrant task before a hands-off window.
- The base's own closer (endgame supply mode, pre-window boost, a housing check sized to the window, the layer-only
  fallback instead of an exit, and the ownership guard on the layer's orders and the civilian alert) is
  `7662723d`'s published work, and its note credits its own idea-level dependency
  **`0bc9b753-d53c-4c1d-b23f-92e645821a02`** (mpjunior92: raise the brewing target for the final stretch).

What this build took, specifically, from outside the base:

1. **`5ef22a35-d413-4eb5-8332-1a80fbffa67f`** (GordoAR): the lab-task goal policies. Their submission reads the
   task's own goal text over `GET /task` and switches controller policies on it — a ceiling-less brew order where
   the goal says drink must not end lower, a beds-only carpenter queue where the goal says every dwarf must have a
   placed bed, a second Carpenters for that goal, a two-day cap on model-requested advances while the bed
   shortfall stands, and an alternate dug area after a real `no_space` on bed placement. I adapted that set to this
   architecture (their policies ran in a layer without a digest; mine sit in the layer and the model loop of
   `7662723d`), with the same detection strings, thresholds, and fallback shape. Their own note credits the
   second-Carpenter idea to `0bc9b753` (mpjunior92, `caretaker.py`), whose workshop-count-scaling idea both their
   and my fixed-two-Carpenters variants follow.
2. **`6e775ed2`** again, one restored step: the **Fishery rule** (build a missing Fishery when an observed dwarf's
   current job is exactly `Fish`). The base dropped it; it is back, from e-man07's code.
3. **`f577e8a7-5faa-4ce5-b83f-8717cd1399f9`** (0xplemonade): the failure cases and the validate-before-cache idea
   behind two robustness checks in `plain/harness.py` (`run_call`/`refuse`): a non-string tool name is refused
   before the set lookup, and a list/dict cancel id cannot reach the added-order cache. The peer's recursive
   schema validator was not taken.
4. **`5dfdcf15-9802-4fbf-a64f-9866323c1412`** (GordoAR): the repository tree my work happened against (`main` at
   commit `1afa775` holds that submission's harness). No code was taken from its harness; its value here is the
   baseline the challenge docs, the scorer and the runner patches I read sit on. Its 54-test suite was removed
   rather than carried (below).

Everything else is the base's own inheritance, credited through it. Nothing in this package derives from the
private pool, and nothing is keyed to a fort or seed: the goal detection reads the task's own public `goal` text,
and every threshold is per citizen, per window, or per population. I did not take part in pre-launch testing.
`dependencies.json` (in `submission/` and filed with `--dependencies-file`) carries the machine-checkable form.

## The three added pieces

### 1. Goal policies for the lab tasks (adapted from GordoAR `5ef22a35`)
The layer already knew how to win a mid-game hands-off window: the closer's pre-window boost adds a no-ceiling
brew order 14 days out, and the housing check orders the bed and seat shortfall against the window. What no
published harness had solved in THIS family's play with the fixed score is the migrant-surge task's placement
gap: LT08 opens with a wave that takes the fort from 19 to about 46 citizens, the dormitory overflows, and placed
beds stay under the citizen count for every game of every scored submission (pass 0/8 in the base's run,
partial credit 0.87). The goal-policy set addresses the chain end to end:
- `set_task()` reads `GET /task`'s goal text once per game and sets two flags, keyed on the presence of a
  `hands_off` field (the envelope carries it only on lab tasks) and on the exact public phrases.
- **Beds first** (goal: "every dwarf must have a placed bed"): the regular supply step orders only beds; the
  furnish step places only beds; workshops() builds a second Carpenters from the moment the first one is placed
  (the bar goes from one to two; the base built its second only 14 days before the window); `housing_check()`'s
  seat branch holds while the shortfall stands.
- **No-space fallback**: when the primary dormitory returns `no_space` (its 9x7 room holds fewer beds than the
  fort after the wave), the layer routes the same daily placement count into the next-largest dug `A` area by
  open tiles, zones that area, and keeps both targets under their rate limits. GordoAR's trace showed the
  failure mode this fixes: beds sat in stock while the primary room filled.
- **Brew growth** (goal: "drink must not end lower"): the layer's brew order carries no drink ceiling, so batches
  keep brewing through the hands-off window and drink holds either flat or falling only as consumption. LT08's
  predicate reads drink at the horizon against drink at the window's start; the base's pre-window order (cap
  2000) runs alongside.
- **Model advance clamp**: while `beds_unmet()` is true, a model-requested `advance_days` is cut to 2 days, so
  between the wave and the window the layer gets a pass every couple of days instead of after a 14-day jump
  (GordoAR's trace showed a 14-day advance crossing into the window with 22 of 46 beds placed). In the
  layer-only fallback (`quiet_days`, credits gone or the model failing), the same unmet goal advances one day at
  a time for the same reason.

### 2. The growth push on open runs (new in this build)
On horizons of 336 days the growth tier is `0.5 * housing + 0.5 * progression`. Progression steps pay one full
weight only when export wealth meets a threshold, and season 0 has no trade tools: every fortress rank counts
0.5, a mayoralty at 50 citizens counts 1.0 (`bench/outcomes.py`, `progression_steps`). With exports at zero the
realistic ladder is: rank 1 (population ≥ 20 with 5,000☼ created) = 0.5, mayor (population 50) = 1, rank 2 = 0.5 —
that is 2.0 steps, full credit — and DF ranks on **created** wealth when the export route is closed. Created
wealth is furniture and craft items, and the wood economy already exists for supply and housing. So the layer's
`progression_push()` steps in, and only where it can crowd out nothing: population ≥ 25 (so rank 1 is already
near), no hands-off window, ≤ 240 days left, ≥ 25 spare logs. It builds a missing Craftsdwarfs and keeps one
repeating wood-crafts order (`add_manager_order` job `MakeCrafts`, material wood, `before: 80` logs standing).
The crafts also grow the created wealth the next caravan reports home, which sizes later migrant waves — the
score's population step and the housing per-capita both follow the population. Every piece keeps its usual rate
limits, so a refused step costs a few actions, and the order is remembered by id (`craft_ids`) so it is not
re-added while standing nor added twice in the same pass.

### 3. Small repairs carried with a source
- **Workshop site occupancy** (`full_sites`): a successful `build_workshop` marks its W site used, so the next
  build takes the next site instead of retrying the consumed one. The base left the site choice at `sites[0]`;
  with two workshops queued this makes the second Carpenters' build one-action instead of a multi-day retry.
- **The layer's brew orders are owned by id** (`brew_own`), the way the goal policy needs: the ceiling-less
  order is not re-added while it stands (the observation's order list is uncapped, and an id no longer present
  is pruned, so a cancelled order re-adds after its rate limit).
- **Robust guards**: the two type checks from `f577e8a7`'s failure cases (below).
- **`python:3.12-slim` is pinned by digest** in the Dockerfile (the base shipped it unpinned; the digest is the
  same image the organiser's baseline pinned, for a build that does not move between my local test and the
  official build).

## What was tested, what was measured, what was not

No Dwarf Fortress install and no hosted model were available where this was built, so no real game was played, and
there is no local score to report against the public suites' numbers. What ran:
- `python3 -m py_compile` on every module of `submission/`.
- `tests/test_goal_policies.py`: 10 offline regressions against a scripted stub game — policy detection from
  public goal text (including that an open task never triggers the policies), the ceiling-less brew order under
  the drink goal, seats skipped but beds kept under the bed goal, the second Carpenters taking an unused W site,
  the `no_space` fallback reaching the alternate area and zoning it, no fallback without a real `no_space`,
  `beds_unmet()` reading placed beds from the observation, the brew-ownership record surviving a stale order
  list, and garbage task text never raising. All pass.
- The runner's fake stack (`--stack fake`, no DF, no key): LT08 through `runner/dfbench local suite`, the harness
  exiting 0 at the hands-off day 39 with the server completing the window to day 60, no exceptions logged.
- `docker build` of the image on this host (multi-arch base, no native steps).

Not tested (and what the official run will show or falsify, if it matters): the fallback's placement capacity on a
real DF room (GordoAR's own trace had the alternate accept one bed per day more than the primary — a capacity
question only DF answers); whether DF validates the crafts order (`add_manager_order` `MakeCrafts` + wood
material category + wood item condition) on these sites — a refused order costs at most four action visits and
leaves the growth push a no-op; how the 2-day advance clamp interacts with the model's own pacing; and every
threshold's DF-side yield, which only games measure. The inherited base played 64 official games with zero
wall-capped games, zero `crash_twice` games, and 0.21 credits per game-year, so its head-room under the caps is
known to be large.

## Risks and limits

- The goal policies are an adaptation whose source played them on the leader harness, not on a digest loop; the
  two architectures differ mainly in what the model does each turn, and the model may place a bed where the layer
  was about to (a duplicate wastes actions; the digest's NEXT list and the LAYER line keep the model informed).
- The crafts order's conditions use DF item names (`WOOD`) reachable through the public `add_manager_order`
  contract; if DF refuses it, the growth push stops after its (low) attempt caps and nothing else changes.
- The two-day advance clamp runs off the layer's last observation; in the worst case it is one day stale. A
  stale `beds_unmet()` reading slows a housed fort's advances until the next layer pass refreshes it — at most a
  few extra model turns at temperature 0.
- The bench thresholds (the progression ladder, per-capita housing) are the organiser's own published scoring
  code, which is fair game (`RULES.md` §4) and which the base's note already reasoned from.

## Reproducing

From the benchmark root (no DF, no key needed for the offline and fake checks):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests
python3 -m py_compile submission/overseer/*.py submission/plain/*.py submission/dfbench_client/*.py
docker build --platform linux/amd64 -t arena-goal-policies submission/
runner/dfbench local suite --harness submission/ --stack fake --games LT08 --n 1 --parallel 1 --retries 0 \
  --poll 1 --out .yukon/runs/goal-lt08-fake
```

With the DF image, forts and an OpenRouter key on a runner-capable host, the public suites against the
`scenarios/season0/` task files are the usual check:

```sh
export OPENROUTER_API_KEY=...
runner/dfbench local suite --harness submission/ --games LT08 --n 1
runner/dfbench local run --harness submission/ --task scenarios/season0/my1-handover-lean.json
```

## A closing note on where this is meant to go

The base's official aggregate was a point estimate of 90.94 over 64 games (its published lower bound 88.99); the
published leader at the time of writing is 86.07. This package is the base's weakest places patched (LT08 placements,
growth at the horizon) with the rest of the family intact; the expectation, stated as a hypothesis rather than a
result, is that the LT08 and OP1 tier distribution shifts the way `5ef22a35`'s lab column moved (labs family 113.6
with its policies set) without trading anything on MY1 or OP1, because the layer's supply closer and the model digest's
diagnostics are untouched. Subsequent cuts here would take the housing-placement problem deeper into the endgame
path (seat zone coverage when the dining hall fills), which is the same failure family as the beds one.
