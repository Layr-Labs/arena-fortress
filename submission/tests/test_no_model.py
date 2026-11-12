"""The zero-credit candidate keeps Plain's task wiring and never calls the gateway."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plain import harness


class NoModel(unittest.TestCase):
    def test_current_candidate_is_deterministic(self):
        self.assertIs(harness.NO_MODEL, True)

    def test_setup_then_layer_with_original_task_and_stats(self):
        obj = object.__new__(harness.Plain)
        obj.stats = {"turns": 0}
        obj.model = SimpleNamespace(usage={"cost_usd": 0})
        obj.stop_reason = None
        calls = []
        def setup():
            calls.append("setup")
        def layer(reason):
            calls.append(("layer", reason))
            obj.stop_reason = "game_over"
        obj.setup = setup
        obj.layer_only = layer
        # Even an explicit turn limit must not lead into the model loop.
        with patch.object(harness, "NO_MODEL", True), redirect_stdout(io.StringIO()):
            stats = obj.run(max_turns=0)
        self.assertEqual(calls, ["setup", ("layer", "no_model")])
        self.assertIs(stats, obj.stats)
        self.assertEqual(obj.model.usage, {"cost_usd": 0})


if __name__ == "__main__":
    unittest.main()
