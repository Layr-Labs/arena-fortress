# Migrant-bed capacity, wall and pacing guards (batch 1)

This builds on the promoted leader `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4` (main), which is kept as the base:
the deterministic layer, the digest model loop, the closers, the ownership guard and the test layout are its code
except where this note says otherwise. New work, in two groups:

## Migrant-bed capacity (LT08)

- The bed stock for a migrant task is sized to the wave's peak (`SURGE_BEDS = 20`, the seed forts' waves reach
  42-49 citizens per `docs/SEED-FORTS.md`), not to the census when the order runs. Idea first measured by
  ryan48's `7c3e587`.
- A second Carpentry starts at 10 citizens when the bed stock is short on a surge task (was 15, unconditional
  on beds). The pre-window carpenter bonus is unchanged otherwise.
- When `place_furniture` into the primary dormitory answers `no_space`, the day's free beds go to the next
  biggest dug floor on the same level (farm rooms and their levels stay out of the bedrooms) and, if none, to an
  unused area site on another level; the new floor gets a dormitory zone unless one is already there. One
  attempt a day; a floor once tried is not retried. Idea first measured by pepedesigner's `a9f894e`
  (LT08 pass 0/8 -> 2/8 in its official run).
- The model loop's `advance_days` is capped (1-3 days, by the layer's view: a mood waits, hostiles are visible,
  a surge fort is short of beds, or a hands-off window is within 14 days) so the layer gets daily passes to
  build and place while it matters. Inside 4 days of a window the existing 1-day rule still wins.
- The system prompt tells the model that on a surge task the layer owns the wave's bed chain (ordering, placing,
  overflow), so it does not duplicate `make_bed` work. Pattern from pepedesigner's `1812e71`.

## Robustness and pacing guards (new here)

- **Wall guard**: the harness now tracks `limits.wall_s` (time.monotonic). Under 10% left, the model loop hands
  the run to the deterministic layer; inside layer-only, under 2% left, big advances (up to the horizon) take
  the run to the end. Previously the harness ignored the wall clock entirely.
- **Gateway probe**: the "model failing" handover used to be permanent (five errors = no model to the horizon).
  Layer-only mode now probes the gateway every 7 game days with a minimal call and returns to the normal loop
  on success, message history intact.
- Adaptive advance caps (above) and accounting for them (`adv_clamped`, `probe_ok`, `probe_fails`,
  `wall_sprints` in the harness stats).

## Checks

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests`:
  **57 tests pass** (46 inherited + 11 new: 5 bed-overflow, 6 loop-guard).
- `docker build` of `submission/` (pinned base, `USER nobody`) builds clean.
- Real-model local games (node1, box64 DF, the season's public seeds; official games use the private pool, so
  these are directional, not predictions): LT08 mod 0.92 partial vs the unmodified leader 0.82 on the same seed
  and wall setting; MY1 mod 100.0 = leader 100.0 (tier 4/4); LT01 1.00, LT02 1.00, LT03 1.00 partial each
  (the leader's official per-task means are 1.00/1.00/1.00); no wall-capped game, no credit exhaustion
  (<= 0.09 USD of the 0.50 budget per game).
