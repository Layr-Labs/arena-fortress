# Seed-cycle protection, staged progression and rejection repairs (wave 2)

This builds on the promoted leader `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4` (main) through our own first submission
(the migrant-bed cluster and the robustness guards; its README described those, and they are still here). The
architecture is unchanged: a deterministic layer (`overseer/`) runs once per game day, the model loop (`plain/`)
reacts to a STATUS digest before the raw observation, and the ownership guard keeps the model from cancelling the
layer's orders. New in this tree:

## Farm-to-drink-and-food supply protection

All four mechanisms come from one analysis: in the measured OP1 runs the fort died of production, not consumption —
the plump-helmet seed line went extinct (day 131-141), `plants_brewable` then sat at 0 for the final 112+ days, the
standing brew order stayed inactive on its `plants_brewable >= 2` condition, and the fort drank its stockpile to
the horizon (final drink 174/138 vs the base's 271 on the same seed).

- **Cook reserve** (`COOK_PLANTS_RESERVE = 6` in `overseer/harness.py`): both cook standings (`o_cook`,
  `o_cook_end`) require 6 brewable plants, because cooking eats them without returning seeds. `0` restores the bare
  cook `when`s. Restored OP1 s0 to 87.5 / supply 1.00 after the unfixed tree sagged to 0.66-0.75
  (`runs/w2c-op1-s0`).
- **Endgame food gate lowered** (`o_cook_end`: `food_edible at_least max(30, cit)`, was `4 * cit`): the plenty gate
  paused cooking exactly while food sagged (measured −1.08 food/day over the final month, ~81 days of food, supply
  0.62 on `runs/w2c-op1-s1`; 70.9 → 87.5 on the same seed after the change, `runs/w2d-op1-s1`,
  `runs/w2e-op1-s1-r2`).
- **Farm target raised** (`farm_target()`: `max(6, min(12, ceil(cit/3)))`, was `max(4, min(10, ceil(cit/5)))`):
  the measured failures all sat at 4-5 plots for a population of 18-23, pinned at the old minimum, and plots feed
  both supply legs. First run on the final tree: OP1 s0 90.6, tier 4/4 (`runs/w2e-op1-s0-r3`).
- **SEED_GUARD digest hint** (`plain/digest.py`, `SEED_GUARD = True`): when a built farm has plants 0 and seeds ≤ 5,
  one advice line tells the model the farm cycle is dead and to protect the seed stock (raise the cook floor on the
  food side). Advice only — no orders are issued or cancelled by it.

## Staged settlement-rank push

- The leader's `progress()` stops at the Hamlet rank (5000 created wealth). Stage 2 continues to Village
  (`WEALTH_TARGET2 = 25000`, per `docs/SUCCESS.md`): a wider log reserve for the crafts standing
  (`LOG_RESERVE2`, swapped in only after the replacement order is accepted, owned orders only) and — behind the
  `MEALS_FOR_WEALTH` toggle — a high-cap cook standing. `absorb_days()` fixes the standalone constructor losing the
  task length; the digest shows the distance to Village.
- `MEALS_FOR_WEALTH` ships **False**, on a measured reversal: with it on, the push's cook order ate the brewable
  plants and the drink trajectory sagged (day 288+: 223→174 vs the base's 285→271, supply 1.00→0.75 on
  `runs/w2-op1-s0`) while wealth was already past the Hamlet target from crafts alone. Whether DF counts prepared
  meals in created wealth is unmeasured here; flip the toggle on only if a run shows it.
- The system prompt tells the model the layer owns the settlement-rank wealth chain, extending the layer-ownership
  declaration pattern.

## Dining-seat overflow and rejection repairs

From a census of the recorded games (103 refused API actions over 5 runs: 87.4% `no_space` on `place_furniture`,
6.8% `site_used` on `build_farm`; base and modified refusal rates were equal at 21.8%, so these target waste):

- A dining floor that answers `no_space` sends that day's free tables **and chairs** together to the next candidate
  floor (same level first, then another level; farm rooms and levels excluded) and zones it `dining_hall` — the
  pair travels as one because a dining zone seats `min(tables, chairs)`. It works on regular tasks, not only surge.
  `overflow_site()` is generalised (anchor + per-purpose tried-set); the beds' behaviour is unchanged.
- `seat_block` remembers a floor's openness signature when it refuses a seat: the same refusal is not knocked again
  while the floor looks unchanged, and the block releases when the floor changes.
- Farm candidates already covering a plot are skipped, and a `site_used` answer marks the site done permanently (a
  plot does not vanish; measured 7 of 103 refusals were exactly this).
- The model loop refuses a repeat of the same `(tool, args)` in `place_furniture` / `build_farm` /
  `build_workshop` locally for the rest of the game day (original error text plus "change the target"), freed the
  next day (`REPEAT_TOOLS` / `failed_today` / `refuse()`).
- The digest's housing advice moves sites that answered `no_space` in the last 2 game days to the end
  (`failed_sites()`), warning only when no alternative floor exists.

## Model-side additions

- **Fruit fallback brewing**: a standing `brew_drink_from_fruit` (regular supply `o_fruit` and window supply
  `o_brew_fruit_win`) gated only on the drink cap and an empty barrel, because `add_order`'s `when` has no
  fruit/growth stock name — DF finds the fruit itself, and the window predicate no longer dies with the
  brewable-plant stock.
- **Wealth in the digest** (`_wealth()`): created wealth against the Hamlet target, with a gap and an advice line;
  the base's `compact_observation()` deleted the field and left the model blind to the score component the
  progression tier reads. The layer's own observation copy is the fallback.
- **Mood danger window**: the layer records when a strange mood starts waiting; the digest prints the waiting age
  and past 20 days (`MOOD_WAIT_DANGER`, half the manual's ~40-day path to insanity) raises a `MOOD DANGER` hint. A
  mood needing logs enables `autochop`.
- **Hostiles advance clamp removed**: the first submission's 2-day clamp while hostiles were visible doubled the
  call count for no score change (156 vs 76 calls/game-year, 6893 vs 3793 s wall, both 87.5 on OP1 s0,
  `runs/cmp-mod-op1-s0` vs `runs/cmp-base-op1-s0`); the `hostile_visible` advance tripwire already stops advances.
  OP1 call counts on the final tree are down to 84-110/game-year vs the base's 64-80.

## Checks

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests`:
  **113 tests, 0 failures** (16 files; 57 were inherited from the first submission's tree, seven files are new:
  digest wealth, mood danger, supply fallback, dining overflow, rejection repairs, staged progression, cook
  reserve).
- `python3 -m py_compile` on `overseer/harness.py`, `plain/harness.py`, `plain/digest.py`, `plain/prompt.py`: clean.
- The `Dockerfile` and `dfbench_client` are unchanged from the first submission's tree; no docker build was re-run
  for this branch.
- Real-model local games (node1, box64 DF, the season's public seeds; official games use the private pool, so these
  are directional, not predictions; wall caps locally extended with the runner's `--wall-s`; every recorded run
  reached the horizon, `wall_capped 0`, `credits_usd` 0.05-0.22 per game by its `score.json`):
  - OP1: this tree 90.6 (s0, tier 4/4, survival/supply/wellbeing 1.00, growth 0.62), 87.5 (s0 second run), 87.5
    (s1, all sub-scores 1.00) — `runs/w2e-op1-s0-r3`, `-r4`, `runs/w2e-op1-s1-r2`; base 87.5 / 87.5 / 46.2
    (`runs/cmp-base-op1-s0`, `-r2`, `runs/cmp-base-op1-s1`). Same-seed s1 pair 87.5 vs 46.2. Intermediate trees
    before the supply fixes: 71.8 / 66.9 / 70.4 (`runs/w2-op1-s0`, `runs/w2b-op1-s0`, `runs/w2d-op1-s0-r2`).
  - MY1: 100.0 tier 4/4 on s0 and s1 (`runs/w2-my1-s0`, `runs/w2-my1-s1`); base 100.0 on s0.
  - LT08: s0 0.88 / 0.90 / 0.90 partial (n3), s1 0.86 (`runs/w2-lt08-*`), vs the first submission's 0.92 on the
    same s0 seed (n2) and the base's 0.82 / 0.82 s0 + 0.92 s1. The 0.02-0.04 gap to the first submission's pair
    sits inside the base's own cross-seed spread; call counts run 252-291/game-year vs the first submission's
    207-230.
  - LT03 1.00 / z 1.00 and LT01 1.00 / z 1.03 (`runs/w2-lt03-s0`, `runs/w2-lt01-s0`), equal to the first
    submission's runs. LT02: run started, score not yet produced — unmeasured on this tree.
