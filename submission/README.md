# Fortress management harness

The Docker entrypoint runs `python -m plain`. The fixed playing model is z-ai/glm-5.3-flash through the supplied gateway. The inherited daily Overseer handles routine actions; the model receives its STATUS digest and action report. All game writes use the served game tools.

This candidate retains the published housing-throughput implementation and its upstream sources. Its additional policies are:

- When observed edible food falls below two units per citizen, request normal butchery early. Prefer an explicitly adult, unowned large livestock animal, and an explicitly male animal within that set; preserve the original bone-material path.
- Stop only the controller's own recorded progression craft orders once the existing 5500 created-wealth target is observed. Never cancel foreign craft orders.
- For a horizon of at least 336 days, start the normal brewing order with a reserve cap of max(600, 30 times the current citizen count). Shorter horizons retain 300. The two-plant and one-empty-barrel conditions remain; the public drink-growth goal retains its ceilingless brewing policy.
- Plan dining work against paired seats and unique in-zone furniture. Place on observed areas or dug rooms that fit the zone API's 20-tile limits. Balance tables and chairs within a small room, exclude occupied farms, and bound alternate attempts after actual no_space.
- Near the end of a non-window game, shorten model-requested advances when observed food is low: at most two days below six food units per citizen, or one day below four. The existing food response then runs sooner. Unknown food counts do not trigger this cap; labs retain their existing window pacing.
- For migrant goals, remember the initial population and reserve beds for max(current population + 12, min(90, three times initial population)). A shortfall above 30 can queue a second batch of at most 30 after the first succeeds. Pending bed work prevents duplicate queues. Migrant dining excavations use 3x3; ordinary forts retain 7x5.

The candidate contains neither the global model farm-request guard, the synthetic query tool, extra farm shafts, nor the one-plant brewing threshold experiment. Development measurements and their limits belong in the public submission note; all local mixed-stack measurements use real DF with a canned gateway rather than the playing GLM.

Run offline checks with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests` from the repository root. Material sources, including inherited validation inspiration, are declared in dependencies.json. This directory contains no benchmark artifacts or credentials.

This candidate retains the 600 early-year reserve and tests food response cadence as a remedy for a missed between-observation food dip in the additional public fort. It is separate from the unmeasured 450-target alternative. Public results and their uncertainty belong in the submission note.
