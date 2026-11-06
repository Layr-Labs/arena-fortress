"""DFBENCH_TASK: the harness's only input besides the network (docs/GAME-API.md §2.1).

    t = load_task()                 # from the DFBENCH_TASK environment variable
    t.game_url, t.model_base_url, t.model_name, t.api_key
    t.credits, t.limits, t.task     # budget (USD at the pinned reference prices, per game), rules, the task itself

DFBENCH_TASK holds the JSON itself. For local use it may also be a path to a JSON file, or "@<path>".
"""
import json
import os

SCHEMA = "dfbench-task/1"


class Task:
    def __init__(self, d):
        if not isinstance(d, dict):
            raise ValueError("DFBENCH_TASK must be a JSON object")
        if d.get("schema") not in (None, SCHEMA):
            raise ValueError(f"DFBENCH_TASK schema {d.get('schema')!r}, expected {SCHEMA!r}")
        self.raw = d
        self.run_id = d.get("run_id")
        self.api = d.get("api", "v0")
        self.game_url = d.get("game_url") or "http://game:8090"
        m = d.get("model") or {}
        self.model = m
        self.model_base_url = m.get("base_url") or "http://gateway:8080/v1"
        self.model_name = m.get("name") or "z-ai/glm-5.3-flash"
        self.model_api = m.get("api", "openai-chat")
        self.api_key = m.get("api_key") or "placeholder"
        self.prices = m.get("prices")   # optional {"input", "cached_input", "output"} USD per million tokens
        b = d.get("budget") or {}
        self.budget = b
        self.credits = float(b["credits"]) if isinstance(b.get("credits"), (int, float)) else None
        self.limits = d.get("limits") or {}
        self.task = d.get("task") or {}

    @property
    def days(self):
        return self.task.get("days")

    @property
    def wall_s(self):
        return self.limits.get("wall_s")

    def __repr__(self):
        return f"Task({self.task.get('name')!r}, days={self.days}, credits={self.credits}, game={self.game_url})"


def load_task(value=None):
    """Parse DFBENCH_TASK (or `value`): JSON text, a path to a JSON file, or '@path'."""
    v = os.environ.get("DFBENCH_TASK") if value is None else value
    if not v:
        raise ValueError("DFBENCH_TASK is not set")
    v = v.strip()
    path = v[1:] if v.startswith("@") else v if not v.startswith("{") and os.path.exists(v) else None
    if path:
        with open(path) as f:
            v = f.read()
    return Task(json.loads(v))
