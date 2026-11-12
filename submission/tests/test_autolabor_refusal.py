"""cx autolabor (owner 2026-11-11, A/B test): the model's enable_automation {"name": "autolabor"} is refused locally
with layer_owned and never reaches the game; the other automations still run, and the tool stays offered without
autolabor among its choices."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plain import harness as plain  # noqa: E402


class Game:
    def __init__(self):
        self.actions, self.last = [], {"day": 5, "tick": 5 * plain.DAY}

    def act(self, tool, args):
        self.actions.append((tool, args))
        return {"ok": True, "result": {"enabled": args.get("name")}}

    def __getattr__(self, name):   # any other API call the loop makes is a no-op success
        return lambda *a, **k: {"ok": True}


def runner(game):
    r = plain.Plain.__new__(plain.Plain)
    r.game = game
    r.tool_names = {"enable_automation", "advance_days"}
    r.messages, r.added, r.cancelled = [], {}, []
    r.stats = {"actions": 0, "rejected": 0, "advances": 0, "churn_refused": 0}
    r.memory = SimpleNamespace(record=lambda *a, **k: None)
    r.tick = lambda: 5 * plain.DAY
    r.guard = SimpleNamespace(owned=set(), water_rising_stop=lambda: None)
    return r


def call(r, args):
    r.run_call({"id": "1", "function": {"name": "enable_automation", "arguments": json.dumps(args)}})
    return json.loads(r.messages[-1]["content"])


class Quiet(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)


class AutolaborRefused(Quiet):
    def test_autolabor_is_refused_locally(self):
        game = Game()
        r = runner(game)
        for name in ("autolabor", "AutoLabor", " autolabor "):
            out = call(r, {"name": name})
            self.assertFalse(out["ok"])
            self.assertEqual(out["error_code"], "layer_owned")
            self.assertIn("autolabor", out["error"])
            self.assertIn("felling", out["error"])
        self.assertEqual(game.actions, [])   # nothing reached the game
        self.assertEqual(r.stats["churn_refused"], 3)

    def test_the_other_automations_are_not_refused(self):
        r = runner(Game())
        for name in ("autochop", "autofarm", "seedwatch", "autoclothing"):
            self.assertIsNone(r.refuse("enable_automation", {"name": name}, 5 * plain.DAY))
        self.assertIsNone(r.refuse("enable_automation", {}, 5 * plain.DAY))
        self.assertIsNone(r.refuse("enable_automation", {"name": 3}, None))

    def test_refused_without_a_tick_too(self):
        r = runner(Game())
        out = r.refuse("enable_automation", {"name": "autolabor"}, None)
        self.assertEqual(out["error_code"], "layer_owned")

    def test_enable_automation_itself_is_not_layer_owned(self):
        self.assertNotIn("enable_automation", plain.LAYER_TOOLS)
        self.assertEqual(plain.LAYER_AUTOMATIONS, ("autolabor",))


class Offered(unittest.TestCase):
    def test_tool_stays_offered_without_autolabor_in_its_choices(self):
        schema = {"type": "function", "function": {"name": "enable_automation", "parameters": {
            "type": "object", "required": ["name"], "properties": {"name": {"type": "string", "enum": [
                "autochop", "autoclothing", "autofarm", "autolabor", "seedwatch"]}}}}}
        out = plain.prepare_tools([schema])
        self.assertEqual([t["function"]["name"] for t in out], ["enable_automation"])
        self.assertEqual(out[0]["function"]["parameters"]["properties"]["name"]["enum"],
                         ["autochop", "autoclothing", "autofarm", "seedwatch"])
        self.assertIn("autolabor", schema["function"]["parameters"]["properties"]["name"]["enum"])   # input untouched

    def test_a_schema_without_an_enum_passes_through(self):
        schema = {"type": "function", "function": {"name": "enable_automation",
                                                   "parameters": {"properties": {"name": {"type": "string"}}}}}
        self.assertEqual(plain.prepare_tools([schema]), [schema])


if __name__ == "__main__":
    unittest.main()
