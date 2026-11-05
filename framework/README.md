# harnessarena (framework core)

The environment-agnostic core of an agent-harness competition: competitors write a harness for a fixed hosted
model, the framework plays it in a sandboxed environment through a metered gateway and scores it honestly. Design:
`docs/TEMPLATE-AGENT-HARNESS.md`. dfbench (Dwarf Fortress) is the first environment adapter
(`runner/dfbenchlib/df_adapter.py`).

**Status (extraction steps 1–4 of `docs/TEMPLATE-AGENT-HARNESS.md` §5.2):** the core lives here, inside the dfbench
research repo, and dfbench's runner, scorer, CI helpers and pool tool already use it. It moves to its own repo at
step 6. Name: `harnessarena` is a working name (alternatives: `agentarena`, `harness-bench`, `yukon-harness`);
renaming is a one-line import change while it's still vendored.

| module | what |
|---|---|
| `harnessarena/adapter.py` | the adapter interface (`read_episode`, `episode_fields`, `score_episode`, `score_crashed`, `format_task`, `env_url`) and the registry; `EpisodeInfra` marks unscorable artifacts |
| `harnessarena/episode.py` | the `episode.json` artifacts manifest schema and validator |
| `harnessarena/suite.py` | suite-file accessors: weights, confirmation tasks, stage-2 tasks, anchors, environment; the only place the season-0 defaults survive (for older suite files) |
| `harnessarena/pool.py` | private pools: the salted commitment, the selection rule, deterministic staging |
| `harnessarena/env.py` | configuration names: `HA_<NAME>` first, then the legacy `DFBENCH_<NAME>` |

**Writing an adapter:** subclass `adapter.Adapter`, implement the methods above, `register()` an instance under a
name, and set `"environment": "<name>"` in the suite file. Ship a fake episode server (dfbench's is
`runner/fakes/fake_game.py`) so the whole scoring workflow runs without the environment.

**Naming plan.** The ~450 `DFBENCH_*` references stay for season 0. New framework code reads configuration through
`env.get(NAME)`, which accepts `HA_NAME` or `DFBENCH_NAME`; step 5 renames the rest to `HA_*` with the old names as
aliases for one season, coordinated with the variables on both challenge repos.

Tests: `python3 -m unittest discover -s framework/tests -t .`; the guard that dfbench's results don't change is
`python3 -I runner/tests/golden/make_golden.py --check` (golden scores of stored public-fort runs under three suites).
