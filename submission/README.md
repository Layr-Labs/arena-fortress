# Migrant-surge housing and window brewing on the current leader

This package is i34-9's current leader `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4` (PR #40), with six changes that apply
only when the task's goal mentions migrants: the leader's own `surge` flag (`"migrant" in goal`), which in season 0
is the LT08 migrant-surge task. On every other task the code path is the leader's, unchanged. Credits, local
measurements and limits are in the submission note; the formal declaration is `dependencies.json`.

## What changed (`overseer/harness.py`, surge only)

- **Bed batches and target.** Regular bed orders take up to 30 beds per batch (the idea of mpjunior92's
  `f42cefb1` and its port source `0e538cbc`), toward a target of `max(citizens + 12, 50)` from day 0, so the
  whole migrant wave's beds are made before the hands-off window, when placement is still allowed.
- **Beds before seats.** While placed beds are fewer than citizens, no table or chair orders or placements. The
  task scores beds, not seats; on the public forts tables and chairs had taken a third of the only dormitory level
  and every later bed placement failed with `no_space`. The manager's office chair is exempt (a chair is still
  ordered if the office has none and none is free). Seats resume once beds cover the citizens.
- **Dormitory first.** The first undug room at least three levels below the surface (two from day 8) is dug as the
  9x7 dormitory before any further farm rooms. The leader digs farm rooms first, up to a target that grows with the
  population, and on fast waves every room became a farm: no dormitory, so no bed was ever placed (seen in 2 of 8
  public fort-2001 games across versions). Farms still have the fort's pre-dug soil floor (F sites).
- **Overflow placement.** When the dormitory level takes fewer beds than asked, the rest go to the other dug
  levels, largest open area first; the inherited `rezone()` then zones loose built beds. It runs only after the
  day's dormitory placement actually ran (not when a later same-day pass is rate-limited).
- **Carpenters.** Up to three Carpenters' workshops while beds are short (a narrow variant of the population-scaled
  Carpenters in mpjunior92's `afd1d5b6`; the inherited rule that adds a second shop stays as a floor).
- **Window brewing.** The hands-off window's standing brew order runs whenever two brewable plants exist, instead of
  half a plant per citizen. Brewable plants were the binding input (0 to 7 all game on the public forts while logs
  and empty barrels were plentiful), so the old reserve kept the order idle through the whole window.

## Operation (inherited)

The runtime is the leader's: a deterministic overseer (`overseer/harness.py`) runs on each observed game day ahead
of the model loop (`plain/harness.py`, `plain/digest.py`, `plain/prompt.py`), which calls `z-ai/glm-5.3-flash`
through the gateway. Both share the day's action allowance. See the leader's note (PR #40) for the model loop.

## Checks

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s submission/tests
docker build --platform linux/amd64 -t fortress-surge-housing submission/
```

54 tests pass: the 46 inherited and 8 new in `tests/test_surge_beds.py` (day-0 bed target, beds before seats, the
office-chair exemption, overflow to another level, no overflow on a rate-limited same-day pass, dormitory first
below the shallow levels, and unchanged seats and farm ordering outside the migrant task).
