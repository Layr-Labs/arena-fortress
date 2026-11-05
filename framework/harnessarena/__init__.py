"""harnessarena: the environment-agnostic core of an agent-harness competition (docs/TEMPLATE-AGENT-HARNESS.md §3).

A competition = this framework + one environment adapter. The framework fixes what makes a harness competition
honest (the harness contract, the metered gateway, the sandboxed runner, the scoring workflow, the statistics,
integrity and ops); the adapter supplies the environment: its episode server, scorer, suite, pool builder and
reference arms. dfbench (Dwarf Fortress) is the first adapter (`runner/dfbenchlib/df_adapter.py`).

stdlib only. Modules:
  adapter  the adapter interface and registry (score_episode, format_task, crashed scoring, env URL)
  episode  the episode.json artifacts manifest (§3.3)
  suite    suite-file accessors: weights, confirmation tasks, stage-2 tasks, anchors (§3.4), one source of defaults
  env      configuration names: generic HA_* with DFBENCH_* fallbacks (the naming compatibility layer)
  pool     commit/reveal and the selection rule for private instance pools (§3.5)
"""
__version__ = "0.1.0"
