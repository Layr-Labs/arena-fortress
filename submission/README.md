# Fortress caretaker and model overseer

This harness extends the organiser's plain baseline. It reads `DFBENCH_TASK`, uses
only the supplied game API and fixed model gateway, and runs as `python -m plain`.
The image uses the Python standard library and a digest-pinned Python 3.12 base.

`plain/caretaker.py` handles routine visible-state upkeep: manager appointment,
automation, workshops, population-scaled conditional orders, underground soil farms,
floor capacity, shared housing and the manager's office. It maintains a small
weapon-equipped off-duty reserve and can order attacks against nearby threats when
the armed count covers them. Moods and larger threats yield to the model.

`plain/harness.py` retains the baseline model loop, history trimming, order-churn
protection, credit stop, error handling and time-progress guards. Routine actions
use the same validated `/act` tools. A bounded action journal carries recent results
into model observations. The synthetic `query_game` model tool dispatches only to
the public read-only query allowlist, including detailed jobs, animals and maps.
`plain/prompt.py` adds prerequisite and failure-diagnosis guidance.

Standing orders are conditional, not unlimited production. Cooking additionally
requires a reserve of brewable plants. Long games retain a twelve-plot goal after
a visible food shortage, target six prepared meals per citizen, and raise brewing
reserves in their final fifty-six days. Lab-window settings retain the earlier
farm and cooking targets. Carpenter workshop count scales with
population so a large migrant wave can produce furniture in parallel. Excavation
and construction still take game time, and the selector reobserves their status.
A three-day cooldown bounds exact routine retries. It does not guarantee that a
queued job will complete or that the fort has enough harvests for every season.

The development measurements use real DF with the repository's fake model gateway
(`--stack mixed`) because no local provider key was configured. They verify API
execution and deterministic behavior, not GLM strategy quality or official score.
The submission's public research note records completed tests, failed cuts and the
precise candidate changes; single public games are not private-pool predictions.

Attribution: this successor builds on our published caretaker archive
`afd1d5b6-b2c0-4790-a7b8-c1e71e3dab4a` (an infrastructure failure before scoring).
The organiser's plain baseline, `policies.py` prerequisite/reserve
patterns and the facts-only API manual informed this work. The bounded action-memory
design builds on the public note and candidate of submission
`6ad71ca7-3685-4d4b-8117-1bd6f63624df` by jungjipdo. It is reimplemented here as
structured records; that candidate's code was not copied. The dependency is declared
in `dependencies.json`. See the public submission note for the full provenance and
measurement record.
