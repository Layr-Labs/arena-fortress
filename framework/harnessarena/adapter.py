"""The environment adapter interface and its registry (docs/TEMPLATE-AGENT-HARNESS.md §3).

The framework's scorer (`runner/dfbenchlib/score.py` today) owns everything environment-agnostic about a game:
the runner's record, the gateway ledger and status, the infra and crash-twice rules, the wall and throttling
accounting, the suite value, the bootstrap and score.json. It asks the adapter only for what depends on the
environment:

  read_episode(artifacts_dir)            -> the episode's end-of-game record (a dict), or None (no record: infra)
  score_episode(artifacts_dir, rec, spec) -> per-episode fields: an outcome task gives {"O", "tier", "s"};
                                           a lab task adds {"partial", "passed", "clauses"}. Raise
                                           EpisodeInfra(reason) when the artifacts can't be scored (infra).
  score_crashed(artifacts_dir, spec, rec) -> the same fields for an episode whose environment crashed twice
                                           (scored at the state reached; never infra)
  episode_fields(rec)                    -> the framework-level fields of an episode from its record: days played,
                                           wall_s, wall_capped, finished_by, actions_used, actions_rejected,
                                           harness_digest, key
  format_task(task, games, value)        -> the one-line per-task summary for score.json
  env_url(spec)                          -> the URL the harness uses to reach the environment

Adapters register under a name; a suite selects its adapter with "environment" (default "dfbench").
"""
_REGISTRY = {}


class EpisodeInfra(Exception):
    """The episode's artifacts can't be scored for a reason outside the harness (infra, re-run)."""


class Adapter:
    name = None
    default_env_url = "http://env:8090"

    def read_episode(self, artifacts_dir):
        raise NotImplementedError

    def score_episode(self, artifacts_dir, rec, spec):
        raise NotImplementedError

    def score_crashed(self, artifacts_dir, spec, rec):
        raise NotImplementedError

    def episode_fields(self, rec):
        raise NotImplementedError

    def format_task(self, task, games, value):
        return f"{value:.2f} (n {len(games)})"

    def env_url(self, spec):
        return (spec or {}).get("env_url") or self.default_env_url


def register(adapter):
    if not adapter.name:
        raise ValueError("adapter needs a name")
    _REGISTRY[adapter.name] = adapter
    return adapter


def get(name):
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"no environment adapter {name!r} (registered: {sorted(_REGISTRY)})") from None


def registered():
    return sorted(_REGISTRY)
