"""cx fight odds (2026-11-10): defend()'s attack used to go out on any visible hostile once one squad member carried a
weapon (armed >= 1). squad_order moves the whole squad, unarmed members included. Now the attack goes when the
squad's strength reaches FIGHT_RATIO x the hostiles' (FIGHT_ENDGAME_RATIO in the last FIGHT_ENDGAME_DAYS before H or a
hands-off window: raiders alive at H halve s1), never with no member armed, never with more unarmed than armed members
against armed foes, never at a DANGER_BIG beast; a standing attack is called off below FIGHT_RETREAT_RATIO; a squad
made with invaders in sight is sized to them; members without weapons get the template again while weapons lie free.
Fixture: the MY1-1 layout of test_invader_drink (stores on the surface z142, hatches on E1/E2). No game or network."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness  # noqa: E402

SURFACE = 142
WAGON = {"present": True, "x": 96, "y": 96, "z": SURFACE}
E1 = {"id": "E1", "kind": "E", "x": 93, "y": 88, "z": SURFACE}
E2 = {"id": "E2", "kind": "E", "x": 96, "y": 92, "z": SURFACE}


def goblins(n, weapon=None, x=60, start=900):
    out = []
    for i in range(n):
        h = {"id": start + i, "race": "GOBLIN", "invader": True, "x": x + i, "y": 88, "z": SURFACE}
        if weapon:
            h["weapon"] = weapon
        out.append(h)
    return out


def dwarf(i):
    return {"id": i, "job": "idle", "x": 98, "y": 88, "z": 141, "adult": True, "profession": "Stonecrafter"}


def squad_of(orders=(), armed=4, n=4, uniform="weapon+armor"):
    return {"id": 1, "members": [{"id": k} for k in range(1, n + 1)], "armed": armed, "uniform": uniform,
            "orders": [dict(o) for o in orders]}


def fort(day, hostiles=(), squads=(), cit=22, alert=True, days_left=None, hands_off=None, weapons_free=0):
    dwarves = [dwarf(200 + i) for i in range(cit)]
    obs = {"date": {"abs_tick": int(day * harness.DAY)}, "administrators": {"citizens": cit},
           "stocks": {"drink": 388, "food_edible": 131},
           "map": {"sites": [dict(E1), dict(E2)], "wagon": dict(WAGON), "surface_z": SURFACE},
           "dwarves": dwarves, "recent_cancellations": [], "recent_events": [],
           "military": {"squads": [dict(q) for q in squads], "weapons_free": weapons_free},
           "threats": {"visible_hostiles": len(hostiles), "hostiles": [dict(h) for h in hostiles],
                       **({"nearest_hostile_dist_to_wagon": 30} if hostiles else {})},
           "doors": {"list": [], "hatch_cover_items_free": 0},
           "burrows": {"civilian_alert": alert, "list": [{"id": 0, "name": "Shelter", "civ_alert_burrow": True,
                                                          "citizens_inside": cit}]}}
    resp = {"tick": int(day * harness.DAY), "day": int(day), "observation": obs,
            "days_left": 216 - int(day) if days_left is None else days_left}
    if hands_off is not None:
        resp["hands_off_in_days"] = hands_off
    return resp


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {}}

    def query(self, *a, **kw):
        return {"result": {"units": []}}


ATTACK = ("squad_order", {"order": "attack"})
STAND_DOWN = ("squad_order", {"order": "stand_down"})


class Base(unittest.TestCase):
    def setUp(self):
        self.out = io.StringIO()
        self.output = redirect_stdout(self.out)
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def logs(self, kind):
        out = []
        for line in self.out.getvalue().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("kind") == kind:
                out.append(rec)
        return out

    def run_pass(self, day=100, duty_seen=True, **kw):
        """duty_seen: the squad has been on duty since its uniform and nobody more is armable (cx arming) — the odds
        alone decide; False: nothing known yet, invaders muster it to find out."""
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        ov.duty_seen = duty_seen
        ov.count = 0
        ov.load(fort(day, **kw))
        ov.count = 0
        ov.defend()
        return ov, game.calls

    def squad_size(self, calls):
        """create_squad's member count (cx squad pick: dwarf_ids; size when the pick had nobody)."""
        a = next((a for t, a in calls if t == "create_squad"), None)
        return None if a is None else len(a.get("dwarf_ids") or []) or a.get("size")

    def attacks(self, calls):
        return [a for t, a in calls if t == "squad_order" and a.get("order") == "attack"]


class Odds(Base):
    def test_one_pick_and_three_bare_hands_hold_against_armed_goblins(self):
        ov, calls = self.run_pass(hostiles=goblins(3, "iron spear"), squads=[squad_of(armed=1)])
        self.assertFalse(self.attacks(calls))     # was: attack (armed >= 1)
        self.assertEqual(self.logs("fight_hold")[-1]["why"], "unarmed_majority")

    def test_armed_squad_attacks_unarmed_goblins(self):
        ov, calls = self.run_pass(hostiles=goblins(3), squads=[squad_of(armed=4)])
        self.assertIn(ATTACK, calls)
        self.assertTrue(self.logs("fight_go"))

    def test_even_numbers_against_armed_goblins_hold_until_the_endgame(self):
        ov, calls = self.run_pass(hostiles=goblins(3, "iron spear"), squads=[squad_of(armed=4)])
        self.assertFalse(self.attacks(calls))     # 4 < 1.5 x 3
        self.assertEqual(self.logs("fight_hold")[-1]["why"], "outmatched")
        ov, calls = self.run_pass(day=205, hostiles=goblins(3, "iron spear"), squads=[squad_of(armed=4)])
        self.assertIn(ATTACK, calls)              # 11 days to H: raiders alive at H halve s1
        self.assertTrue(self.logs("fight_go")[-1]["endgame"])

    def test_hands_off_window_counts_as_the_end(self):
        ov, calls = self.run_pass(hostiles=goblins(3, "iron spear"), squads=[squad_of(armed=4)], hands_off=6)
        self.assertIn(ATTACK, calls)

    def test_mixed_squad_goes_when_weapons_are_the_majority(self):
        ov, calls = self.run_pass(hostiles=goblins(1, "iron spear"), squads=[squad_of(armed=2)])
        self.assertIn(ATTACK, calls)              # 2 + 2 x 0.25 = 2.5 >= 1.5

    def test_unarmed_majority_never_goes_into_armed_foes_even_at_the_end(self):
        ov, calls = self.run_pass(day=210, hostiles=goblins(1, "iron spear"), squads=[squad_of(armed=1)])
        self.assertFalse(self.attacks(calls))

    def test_unarmed_squad_never_attacks(self):
        ov, calls = self.run_pass(hostiles=goblins(1), squads=[squad_of(armed=0)])
        self.assertFalse(self.attacks(calls))
        self.assertEqual(self.logs("fight_hold")[-1]["why"], "unarmed")

    def test_unknown_squad_musters_below_before_any_attack(self):
        # cx arming (probe p4): off duty nobody carries a weapon; stationed, the assigned ones do two days later
        ov, calls = self.run_pass(hostiles=goblins(3, "iron spear"), squads=[squad_of(armed=0)], duty_seen=False)
        self.assertFalse(self.attacks(calls))
        st = [a for t, a in calls if t == "squad_order" and a.get("order") == "station"]
        self.assertTrue(st)
        self.assertLess(st[0]["z"], 142)
        self.assertEqual(self.logs("guard_muster")[-1]["need"], "invaders")

    def test_armable_members_muster_then_attack_once_carried(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        ov.duty_seen = True
        ov.armed_seen = {1: 99, 2: 99, 3: 99, 4: 99}   # all four seen armable
        ov.load(fort(100, hostiles=goblins(3), squads=[squad_of(armed=0)]))
        ov.count = 0
        ov.defend()
        st = [a for t, a in game.calls if t == "squad_order" and a.get("order") == "station"]
        self.assertTrue(st)                        # 4 armable vs 3 unarmed goblins: arm first
        game.calls.clear()
        ov.load(fort(102, hostiles=goblins(3), squads=[squad_of([dict(st[0], order="station")], armed=4)]))
        ov.count = 0
        ov.defend()
        self.assertIn(ATTACK, game.calls)          # carried: the attack replaces the muster
        self.assertIsNone(ov.muster)

    def test_unlisted_hostiles_count_as_unknown_strength(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        resp = fort(100, hostiles=goblins(2), squads=[squad_of(armed=4)])
        resp["observation"]["threats"]["visible_hostiles"] = 30   # the list stops at 20
        ov.load(resp)
        ov.count = 0
        ov.defend()
        self.assertFalse(self.attacks(game.calls))


class Retreat(Base):
    def test_standing_attack_called_off_when_the_party_grows(self):
        ov, calls = self.run_pass(hostiles=goblins(6, "iron spear"), squads=[squad_of([{"order": "attack"}], armed=4)])
        self.assertIn(STAND_DOWN, calls)
        self.assertTrue(self.logs("fight_retreat"))

    def test_standing_attack_kept_between_retreat_and_go_ratios(self):
        ov, calls = self.run_pass(hostiles=goblins(3, "iron spear"), squads=[squad_of([{"order": "attack"}], armed=4)])
        self.assertNotIn(STAND_DOWN, calls)       # 4 >= 1.0 x 3: hysteresis, no flapping
        self.assertFalse(self.attacks(calls))

    def test_surface_guard_outliving_its_window_comes_back_down(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        st = {"order": "station", "x": E1["x"], "y": E1["y"], "z": SURFACE}
        ov.load(fort(100, hostiles=goblins(6, "iron spear"), squads=[squad_of([st], armed=4)]))
        ov.invader_guard = (E1["x"], E1["y"], SURFACE)
        ov.invader_window = 99 * harness.DAY   # over
        ov.count = 0
        ov.defend()
        self.assertIn(STAND_DOWN, game.calls)
        self.assertIsNone(ov.invader_guard)


class Beasts(Base):
    def test_big_beast_alone_gets_no_soldiers(self):
        beast = {"id": 50, "race": "CARNOTAURUS", "invader": False, "x": 80, "y": 90, "z": SURFACE}
        ov, calls = self.run_pass(hostiles=[beast], squads=[squad_of(armed=4)])
        self.assertFalse(self.attacks(calls))
        self.assertEqual(self.logs("fight_hold")[-1]["why"], "big_only")

    def test_invaders_with_a_big_beast_are_attacked_by_id(self):
        beast = {"id": 50, "race": "CARNOTAURUS", "invader": False, "x": 80, "y": 90, "z": SURFACE}
        ov, calls = self.run_pass(hostiles=[beast] + goblins(2), squads=[squad_of(armed=4)])
        self.assertIn(("squad_order", {"order": "attack", "target_ids": [900, 901]}), calls)


class Recruit(Base):
    def test_squad_made_under_invaders_is_sized_to_them(self):
        ov, calls = self.run_pass(hostiles=goblins(6, "iron spear"), cit=30)
        self.assertEqual(self.squad_size(calls), 9)   # 1.5 x 6, within a third of 30

    def test_size_capped_at_a_third_of_the_citizens(self):
        ov, calls = self.run_pass(hostiles=goblins(6, "iron spear"), cit=18)
        self.assertEqual(self.squad_size(calls), 6)

    def test_small_fort_makes_the_default_squad(self):
        ov, calls = self.run_pass(hostiles=goblins(1), cit=10)   # cx squad pick: SQUAD_MIN_CIT (was 12 here)
        self.assertEqual(self.squad_size(calls), 4)
        ov, calls = self.run_pass(hostiles=goblins(1), cit=9)
        self.assertFalse([c for c in calls if c[0] == "create_squad"])

    def test_no_invaders_keeps_the_old_rule(self):
        ov, calls = self.run_pass(cit=20, alert=False)
        self.assertEqual(self.squad_size(calls), 4)

    def test_no_re_equip_under_invaders(self):
        # cx equip once: a second equip_squad clears the weapon assignments for good (16 hint runs)
        ov, calls = self.run_pass(hostiles=goblins(3, "iron spear"), squads=[squad_of(armed=1)], weapons_free=3)
        self.assertFalse([c for c in calls if c[0] == "equip_squad"])


if __name__ == "__main__":
    unittest.main()
