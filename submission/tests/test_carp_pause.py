"""cx carpentry pause (owner-approved option A): hint std OP1-2 on 0bd4308 — the fort's one MINE citizen (unit 92)
spent 22 of 32 looks d10-47 in carpentry while the layer's stairs stood pending 30 days. While one of the layer's own
dig batches has waited CARP_PAUSE_WAIT_DAYS, the MINE citizen is in a carpentry job and no alert stands, the layer's
own bed/table/chair/crafts orders are cancelled; barrels only at BARREL_SAFE_FLOOR+ empty barrels and no recent
want-of-barrel brew cancel (0bd4308: 0 empty, 3 such cancels); everything comes back when the batch clears or after
CARP_PAUSE_MAX_DAYS; tiles near a "Dig: Dangerous terrain" cancel leave the batch. No game or network."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness  # noqa: E402

S2 = {"id": "S2", "kind": "S", "x": 95, "y": 99, "z": 163, "w": 1, "h": 1}
R7 = {"id": "R7", "kind": "R", "x": 100, "y": 94, "z": 162, "w": 3, "h": 3, "dug": False, "designated": False,
      "free": True}


class Game:
    def __init__(self):
        self.calls, self.next_id = [], 500
        self.des = set()                 # standing dig designations (x, y, z)
        self.miners = [(92, "ConstructBed")]

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool in ("add_order", "add_manager_order"):
            self.next_id += 1
            return {"ok": True, "result": {"order_id": self.next_id}}
        return {"ok": True, "result": {}}

    def query(self, name, **p):
        if name == "units":
            us = [{"id": i, "job": j, "labors": ["MINE", "CARPENTER"]} for i, j in self.miners]
            us.append({"id": 93, "job": "idle", "labors": ["CARPENTER"]})
            return {"result": {"ok": True, "units": us}}
        if name == "map":
            return {"result": {"ok": True, "x1": 0, "y1": 0, "x2": 200, "y2": 200, "levels": [],
                               "designations": [{"x": x, "y": y, "z": z, "dig": "Default"} for x, y, z in self.des]}}
        return {"result": {}}


ORDERS = [
    {"id": 5, "job": "ConstructBed", "left": 3, "recipe": "make_bed", "material_category": ["wood"]},
    {"id": 6, "job": "ConstructTable", "left": 2, "recipe": "make_table"},
    {"id": 7, "job": "ConstructThrone", "left": 4, "recipe": "make_chair"},
    {"id": 19, "job": "MakeCrafts", "left": 12, "repeat": "daily", "material_category": ["wood"]},
    {"id": 1, "job": "MakeBarrel", "left": 2, "repeat": "daily", "material_category": ["wood"]},
    {"id": 0, "job": "CustomReaction", "left": 9, "reaction": "BREW_DRINK_FROM_PLANT", "repeat": "daily"},
    {"id": 40, "job": "ConstructBed", "left": 2, "recipe": "make_bed"},   # the model's own: never touched
]


def look(day, empty=0, alert=False, orders=ORDERS, cancels=()):
    return {"tick": day * harness.DAY, "day": day, "days_left": 336 - day, "observation": {
        "date": {"abs_tick": day * harness.DAY}, "administrators": {"citizens": 7},
        "stocks": {"barrels_empty": empty, "drink": 150, "logs_usable": 100},
        "map": {"sites": [S2, R7], "surface_z": 163}, "zones": [], "furniture": [], "farm_plots": [],
        "orders": [dict(o) for o in orders], "dwarves": [], "recent_cancellations": list(cancels),
        "burrows": {"civilian_alert": alert, "list": []}, "dig_designations_pending": 2}}


class CarpPause(unittest.TestCase):
    def setUp(self):
        self.out = io.StringIO()
        self.output = redirect_stdout(self.out)
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def fort(self, day=17, **kw):
        game = Game()
        ov = harness.Overseer(game, goal="Run the fortress for a year.", days=336)
        ov.count = 0
        ov.load(look(day, **kw))
        ov.owned |= {5, 6, 7, 19, 1, 0}
        ov.order_src[5] = ("o_make_bed", "add_order", {"recipe": "make_bed", "amount": 8})
        ov.order_src[19] = ("o_crafts_prog", "add_manager_order", {"job": "MakeCrafts", "amount": 12,
                                                                    "repeat": "daily"})
        ov.act("stairs_house", "dig_stairs", {"site": "S2", "z_bottom": 161})
        game.des = {(95, 99, 162), (95, 99, 161)}
        return ov, game

    def at(self, ov, day, **kw):
        ov.load(look(day, **kw))
        ov.carp_pause_step()

    def cancelled(self, game):
        return sorted(a["order_id"] for t, a in game.calls if t == "cancel_order")

    def test_the_0bd4308_wait_pauses_furniture_but_not_barrels_at_zero_empty(self):
        ov, game = self.fort()
        self.at(ov, 19)
        self.assertEqual(self.cancelled(game), [])            # 2 days: not yet
        self.at(ov, 20)
        self.assertEqual(self.cancelled(game), [5, 6, 7, 19])  # bed, table, chair, crafts; barrel 1 and brew 0 kept
        self.assertFalse(ov.carp_pause["barrels"])
        self.assertIn('"barrels_why": "empty_barrels_0_below_4"', self.out.getvalue())
        n = len(game.calls)
        self.assertEqual(ov.act("o_bed_close", "add_order", {"recipe": "make_bed", "amount": 2})["error_code"],
                         "carp_pause")
        ov.act("o_barrel_need", "add_order", {"recipe": "make_barrel", "amount": 3})
        self.assertEqual([t for t, _ in game.calls[n:]], ["add_order"])   # only the barrel reached the game

    def test_barrels_pause_with_a_safe_floor_and_come_back_when_it_falls(self):
        ov, game = self.fort(empty=12)
        self.at(ov, 20, empty=12)
        self.assertIn(1, self.cancelled(game))
        self.assertTrue(ov.carp_pause["barrels"])
        self.at(ov, 22, empty=3)
        readd = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "make_barrel"]
        self.assertEqual(len(readd), 1)
        self.assertFalse(ov.carp_pause["barrels"])
        self.assertIsNotNone(ov.carp_pause)                    # furniture still held

    def test_a_recent_want_of_barrel_brew_cancel_keeps_barrels(self):
        ov, game = self.fort(empty=12)
        self.at(ov, 19, empty=12, cancels=["Mosus, manager cancels Brew drink from plant: Needs empty food storage item."])
        self.at(ov, 20, empty=12)
        self.assertNotIn(1, self.cancelled(game))

    def test_the_batch_clearing_re_adds_everything_as_first_added(self):
        ov, game = self.fort()
        self.at(ov, 20)
        game.des = set()
        n = len(game.calls)
        self.at(ov, 23)
        back = game.calls[n:]
        self.assertIn(("add_order", {"recipe": "make_bed", "amount": 3}), back)        # one-shot: what was left
        self.assertIn(("add_order", {"recipe": "make_table", "amount": 2}), back)
        self.assertIn(("add_order", {"recipe": "make_chair", "amount": 4}), back)
        self.assertIn(("add_manager_order", {"job": "MakeCrafts", "amount": 12, "repeat": "daily"}), back)
        self.assertIsNone(ov.carp_pause)
        self.assertIn('"why": "batch_clear"', self.out.getvalue())

    def test_the_cap_resumes_and_a_cooldown_follows(self):
        ov, game = self.fort()
        self.at(ov, 20)
        self.at(ov, 34)
        self.assertIsNotNone(ov.carp_pause)
        self.at(ov, 35)
        self.assertIsNone(ov.carp_pause)
        self.assertIn('"why": "cap_15_days"', self.out.getvalue())
        ov.act("stairs_house2", "dig_stairs", {"site": "S2", "z_bottom": 160})
        game.des.add((95, 99, 160))
        n = len(game.calls)
        self.at(ov, 40)
        self.assertEqual([t for t, _ in game.calls[n:] if t == "cancel_order"], [])   # cooldown
        ov.owned |= {5, 6, 7, 19}   # the re-added orders (the fixture's look keeps the old ids)
        self.at(ov, 50)
        self.assertNotEqual([t for t, _ in game.calls[n:] if t == "cancel_order"], [])

    def test_dangerous_terrain_tiles_leave_the_batch(self):
        ov, game = self.fort()
        ov.act("dig_R7", "dig_room", {"site": "R7"})
        game.des = {(102, 94, 162), (102, 95, 162), (101, 96, 162)}   # the river-side tiles DF never digs
        ov.dig_unsafe.add((99, 95, 162))
        self.at(ov, 20)
        self.at(ov, 21)
        self.assertEqual(self.cancelled(game), [])

    def test_no_pause_in_an_alert_with_two_miners_or_a_miner_not_in_carpentry(self):
        for setup in ("alert", "two", "digging"):
            ov, game = self.fort()
            if setup == "two":
                game.miners.append((94, "ConstructTable"))
            if setup == "digging":
                game.miners = [(92, "Dig")]
            self.at(ov, 20, alert=(setup == "alert"))
            self.assertEqual(self.cancelled(game), [], setup)


if __name__ == "__main__":
    unittest.main()
