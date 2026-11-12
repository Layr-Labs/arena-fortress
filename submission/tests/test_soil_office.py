"""Reserve a valid office before allocating every soil room to crops."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer

class API:
    def __init__(self): self.calls = []
    def act(self, tool, args):
        self.calls.append((tool, args))
        return {"ok": True, "result": {"id": len(self.calls)}}

class SoilOffice(unittest.TestCase):
    def test_first_soil_room_is_not_consumed_by_farms(self):
        api = API()
        layer = Overseer(api)
        layer.count = 0
        rooms = [{"id": f"R{i}", "kind": "R", "soil": True, "dug": False,
                  "free": True, "x": 10*i, "y": 10, "z": 9, "w": 3, "h": 3}
                 for i in (1, 2)]
        layer.load({"tick": 0, "observation": {"administrators": {"citizens": 18},
                    "map": {"surface_z": 10, "sites": rooms}}})
        with contextlib.redirect_stdout(io.StringIO()): layer.digging()
        self.assertEqual(layer.roles, {"R1": "office", "R2": "farm"})
        for r in rooms: r["dug"] = True
        with contextlib.redirect_stdout(io.StringIO()): layer.farms()
        self.assertEqual([a["site"] for t,a in api.calls if t == "build_farm"], ["R2"])

if __name__ == '__main__': unittest.main()
