"""cx stair wait (hint std OP1-2 on 0bd4308): house_floor's floor_stair sent dig_stairs S2 z_bottom 161 on d17, 22, 26,
30, 37 and 44 — every SURGE_FLOOR_STAIR_DAYS — while the observation read dig_pending_by_z {161: 1, 162: 6}: the first
designation stood undug (the fort's one miner dug it on d48), so each resend changed nothing. The step now waits
while the stair it sent still has designations standing on its bottom level; a cleared designation (dug or
cancelled) or a new bottom level lets it send again. No game or network."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_housing_boxes import A6, Base, harness  # noqa: E402

S2 = {"id": "S2", "kind": "S", "x": 130, "y": 120, "z": 160, "w": 1, "h": 1, "soil": True}


class StairWait(Base):
    def stair(self, o, game, day, pending):
        o.day, o.now = day, day * harness.DAY
        o.o["dig_pending_by_z"] = pending
        o.floor_stair("stairs_house", "house_floor_stair")
        return [a for a in self.calls(game, "dig_stairs")]

    def test_the_0bd4308_resends_stop_while_the_designation_stands(self):
        o, game = self.ov(sites=[A6], stairs_s=[S2], free={"bed": 5, "table": 0, "chair": 0}, cit=16)
        self.assertEqual(self.stair(o, game, 17, {}), [{"site": "S2", "z_bottom": 158}])
        self.assertEqual(o.floor_stair_sent["stairs_house"][:2], ("S2", 158))
        for day in (22, 26, 30):
            self.assertEqual(len(self.stair(o, game, day, {"158": 1, "159": 6})), 1)   # no resend
        self.assertIn('"floor_stair_wait"', self.output._new_target.getvalue())

    def test_a_cleared_designation_lets_it_send_again(self):
        o, game = self.ov(sites=[A6], stairs_s=[S2], free={"bed": 5, "table": 0, "chair": 0}, cit=16)
        self.stair(o, game, 17, {})
        self.assertEqual(len(self.stair(o, game, 22, {"158": 1})), 1)
        self.assertEqual(len(self.stair(o, game, 26, {"159": 2})), 2)   # nothing left at 158: cancelled or lost

    def test_the_time_gate_still_holds_the_first_days(self):
        o, game = self.ov(sites=[A6], stairs_s=[S2], free={"bed": 5, "table": 0, "chair": 0}, cit=16)
        self.stair(o, game, 17, {})
        self.assertEqual(len(self.stair(o, game, 18, {})), 1)   # SURGE_FLOOR_STAIR_DAYS not passed

    def test_the_wait_is_capped_at_14_days_then_one_resend(self):
        # a designation DF never digs (the R1 tiles beside the 0bd4308 river: "Dig: Dangerous terrain") on the bottom
        # level would hold the step for good: after STAIR_WAIT_CAP_DAYS the stair is sent once more, and only once
        self.assertEqual(harness.STAIR_WAIT_CAP_DAYS, 14)
        o, game = self.ov(sites=[A6], stairs_s=[S2], free={"bed": 5, "table": 0, "chair": 0}, cit=16)
        stuck = {"158": 3}
        self.stair(o, game, 17, {})
        self.assertEqual(len(self.stair(o, game, 30, stuck)), 1)    # 13 days: still waiting
        self.assertEqual(len(self.stair(o, game, 31, stuck)), 2)    # 14 days: the one resend
        self.assertIn('"floor_stair_wait_cap"', self.output._new_target.getvalue())
        for day in (36, 45, 60, 90):
            self.assertEqual(len(self.stair(o, game, day, stuck)), 2)   # never again for this stair


if __name__ == "__main__":
    unittest.main()
