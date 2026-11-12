"""cx guard equip (owner 2026-11-10): on MY1-4-shaped maps the shaft E1 takes no hatch or door, so the closure is the
squad at the shaft foot (mark_gate), which needs MARK_RESCUE_ARMED armed members; the alert-only defence stays (no
unarmed guard) and the squad is armed earlier instead — and picks stay with the workers. equip_squad names no item
(gameapi act.lua: the template's weapon spec, any melee weapon of any material; DF assigns, picks included), so the
layer sends it only when free NON-pick weapons (stocks query, item_type WEAPON) cover every member that wants one:
the members with nothing in hand, and those holding a uniform-assigned pick (a swap). Without invaders the first
uniform waits for that cover too; with invaders in sight it goes at once. No game or network."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness  # noqa: E402

SURFACE = 168
WAGON = {"present": True, "x": 100, "y": 100, "z": SURFACE}


def site_e1(building=True):
    return {"id": "E1", "kind": "E", "x": 104, "y": 98, "z": SURFACE, "building": building}


def member(i, weapon=None, assigned=False):
    m = {"id": i, "weapon_assigned": assigned}
    if weapon:
        m["weapon"] = weapon
    return m


def my14_squad(uniform="weapon+armor", assigned=True):
    """d769d66 std MY1-4 after its equip: three members assigned but empty-handed, the miner with his own pick."""
    return {"id": 1, "uniform": uniform, "orders": [], "armed": 1,
            "members": [member(238, assigned=assigned), member(99, assigned=assigned),
                        member(241, assigned=assigned), member(95, "(iron pick)")]}


def group(sub, items, in_inventory=0, in_job=0, forbidden=0, in_building=0):
    return {"item_type": "WEAPON", "item_subtype": sub, "material": "COPPER", "items": items, "count": items,
            "rotten": 0, "forbidden": forbidden, "in_job": in_job, "in_building": in_building,
            "in_inventory": in_inventory, "construction": 0}


AXE, SPEAR, PICK, TRAIN = "ITEM_WEAPON_AXE_BATTLE", "ITEM_WEAPON_SPEAR", "ITEM_WEAPON_PICK", "ITEM_WEAPON_AXE_TRAINING"
MACE, SWORD = "ITEM_WEAPON_MACE", "ITEM_WEAPON_SWORD_SHORT"


def fort(day, squads, weapons_free, building=True, alert=False, cit=16, hostiles=(), hatch=False):
    e1 = site_e1(building)
    doors = [{"id": 7, "kind": "hatch", "x": e1["x"], "y": e1["y"], "z": SURFACE, "built": True,
              "locked": False}] if hatch else []
    obs = {"date": {"abs_tick": int(day * harness.DAY)}, "administrators": {"citizens": cit},
           "stocks": {"drink": 300, "food_edible": 200},
           "map": {"sites": [e1], "wagon": dict(WAGON), "surface_z": SURFACE},
           "dwarves": [{"id": 300 + i, "job": "idle", "x": 100, "y": 100, "z": SURFACE - 1, "adult": True,
                        "profession": "Miner" if i == 0 else "Farmer"} for i in range(cit)],
           "dig_designations_pending": 12, "recent_cancellations": [], "recent_events": [],
           "military": {"squads": [dict(q) for q in squads], "weapons_free": weapons_free},
           "threats": {"visible_hostiles": len(hostiles), "hostiles": [dict(h) for h in hostiles]},
           "doors": {"list": doors, "hatch_cover_items_free": 0},
           "burrows": {"civilian_alert": alert, "list": [{"id": 0, "name": "Shelter", "civ_alert_burrow": True,
                                                          "citizens_inside": 0}]}}
    return {"tick": int(day * harness.DAY), "day": int(day), "observation": obs, "days_left": 216 - int(day)}


class FakeGame:
    def __init__(self, groups=(), lost=False):
        self.calls, self.queries, self.groups, self.lost = [], [], list(groups), lost

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {}}

    def query(self, name, **kw):
        self.queries.append((name, kw))
        if name == "stocks":
            if self.lost:
                return {"ok": False, "error_code": "bad_arguments"}
            return {"day": 0, "result": {"ok": True, "groups": [dict(g) for g in self.groups],
                                         "total": len(self.groups)}}
        return {"result": {"units": []}}


EQUIP = ("equip_squad", {"uniform": "leather"})


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

    def ov(self, groups=(), lost=False):
        game = FakeGame(groups, lost)
        return harness.Overseer(game, days=216), game

    def pass_(self, ov, game, day, **kw):
        ov.load(fort(day, **kw))
        ov.count = 0
        game.calls.clear()
        ov.defend()
        return list(game.calls)


def fresh():
    """The squad before its first uniform: nobody assigned, the miner with his own pick."""
    return my14_squad(uniform="none", assigned=False)


class EquipOnce(Base):
    """hint hard MY1-4 on 72587ab: the day-44 uniform assigned 3 members by day 46; the layer's re-send on day 51 (and
    51-72) cleared them, and weapon_assigned stayed false to day 200 — as in all 16 hint runs with two equip_squad."""

    def test_no_re_send_once_a_uniform_stands(self):
        ov, game = self.ov([group(SPEAR, 6), group(MACE, 4)])
        for sq in (my14_squad(), my14_squad(assigned=False)):
            ov.wild_alert_since = 18 * harness.DAY
            calls = self.pass_(ov, game, 51, squads=[sq], weapons_free=10, alert=True)
            self.assertFalse([c for c in calls if c[0] == "equip_squad"])

    def test_no_re_send_under_invaders_either(self):
        gob = [{"id": 900, "race": "GOBLIN", "invader": True, "x": 60, "y": 98, "z": SURFACE}]
        ov, game = self.ov([group(AXE, 2, in_inventory=2), group(PICK, 1)])
        calls = self.pass_(ov, game, 20, squads=[my14_squad()], weapons_free=3, hostiles=gob, alert=True)
        self.assertFalse([c for c in calls if c[0] == "equip_squad"])

    def test_equip_squad_is_layer_owned(self):
        from plain import harness as plain   # noqa: E402
        self.assertIn("equip_squad", plain.LAYER_TOOLS)
        self.assertIn("equip_squad", plain.LAYER_REFUSAL)


class FirstUniform(Base):
    """probe p6: the single equip_squad goes as soon as the squad stands (DF fills empty melee slots later itself)."""

    def test_first_uniform_goes_at_once_even_with_only_picks(self):
        ov, game = self.ov([group(PICK, 3)])
        calls = self.pass_(ov, game, 3, squads=[fresh()], weapons_free=0)
        self.assertIn(EQUIP, calls)
        self.assertEqual(ov.equip_day, 3)
        self.assertTrue(self.logs("equip_once"))

    def test_never_a_second_call_even_if_the_uniform_still_reads_none(self):
        ov, game = self.ov()
        self.assertIn(EQUIP, self.pass_(ov, game, 3, squads=[fresh()], weapons_free=0))
        for day in (4, 10, 30):
            calls = self.pass_(ov, game, day, squads=[fresh()], weapons_free=0)
            self.assertFalse([c for c in calls if c[0] == "equip_squad"])


class EarlySquad(Base):
    def test_squad_made_at_ten_citizens_by_ids(self):
        # cx squad pick: create_squad is layer-owned (plain LAYER_TOOLS); the layer makes it at SQUAD_MIN_CIT
        ov, game = self.ov()
        self.assertIn(("create_squad", {"dwarf_ids": [301, 302, 303, 304]}),   # the Miner (300) left out
                      self.pass_(ov, game, 5, squads=[], weapons_free=0, cit=10))
        ov, game = self.ov()
        calls = self.pass_(ov, game, 5, squads=[], weapons_free=0, cit=9)
        self.assertFalse([c for c in calls if c[0] == "create_squad"])

    def test_create_squad_is_layer_owned(self):
        sys.path.insert(0, str(VARIANT))
        from plain import harness as plain   # noqa: E402
        self.assertIn("create_squad", plain.LAYER_TOOLS)
        self.assertIn("create_squad", plain.LAYER_REFUSAL)


class Muster(Base):
    """Hint std MY1-4 on d769d66: weapons assigned from day 5, carried only after a station order (day 58 -> 59)."""

    def sheltered(self, ov):
        return [c for c in ov.citizen_spots() if c["z"] < SURFACE]

    def test_wild_alert_musters_the_assigned_squad_below_away_from_the_stair(self):
        ov, game = self.ov()
        ov.wild_alert_since = 18 * harness.DAY
        calls = self.pass_(ov, game, 20, squads=[my14_squad()], weapons_free=0, alert=True)
        st = [a for t, a in calls if t == "squad_order" and a.get("order") == "station"]
        self.assertEqual(len(st), 1)
        self.assertLess(st[0]["z"], SURFACE)               # below: no surface post
        self.assertEqual(ov.muster, (st[0]["x"], st[0]["y"], st[0]["z"]))
        self.assertTrue(self.logs("guard_muster"))
        # the next pass, the alert still standing: the order stands (defend's own stand_down leaves it alone)
        ov.wild_alert_since = 18 * harness.DAY   # (the fixture names no animal: the pass above lifted it)
        sq = dict(my14_squad(), orders=[dict(st[0])])
        calls = self.pass_(ov, game, 21, squads=[sq], weapons_free=0, alert=True)
        self.assertNotIn(("squad_order", {"order": "stand_down"}), calls)

    def test_muster_stands_down_when_the_need_is_gone(self):
        ov, game = self.ov()
        ov.wild_alert_since = 18 * harness.DAY
        st = self.pass_(ov, game, 20, squads=[my14_squad()], weapons_free=0, alert=True)
        order = next(a for t, a in st if t == "squad_order")
        ov.wild_alert_since = None
        sq = dict(my14_squad(), orders=[dict(order)], armed=4)
        calls = self.pass_(ov, game, 25, squads=[sq], weapons_free=0)
        self.assertIn(("squad_order", {"order": "stand_down"}), calls)
        self.assertIsNone(ov.muster)
        self.assertTrue(self.logs("guard_muster_end"))

    def test_no_muster_for_an_open_entrance_alone(self):
        ov, game = self.ov()
        calls = self.pass_(ov, game, 20, squads=[my14_squad()], weapons_free=0)
        self.assertFalse([c for c in calls if c[0] == "squad_order"])   # need is open_entrance: no duty

    def test_no_muster_without_assigned_weapons_or_when_armed_enough(self):
        ov, game = self.ov()
        ov.wild_alert_since = 18 * harness.DAY
        calls = self.pass_(ov, game, 20, squads=[my14_squad(assigned=False)], weapons_free=0, alert=True)
        self.assertFalse([c for c in calls if c[0] == "squad_order"])
        ov, game = self.ov()
        ov.wild_alert_since = 18 * harness.DAY
        calls = self.pass_(ov, game, 20, squads=[dict(my14_squad(), armed=harness.MARK_RESCUE_ARMED)],
                           weapons_free=0, alert=True)
        self.assertFalse([c for c in calls if c[0] == "squad_order"])

    def test_mark_station_replaces_the_muster(self):
        ov, game = self.ov()
        ov.wild_alert_since = 18 * harness.DAY
        self.pass_(ov, game, 20, squads=[my14_squad()], weapons_free=0, alert=True)
        ov.mark_station = ov.now
        self.pass_(ov, game, 21, squads=[dict(my14_squad(), orders=[{"order": "station", "x": 1, "y": 1,
                                                                     "z": SURFACE}])], weapons_free=0, alert=True)
        self.assertIsNone(ov.muster)

    def test_invaders_replace_the_muster_with_the_attack(self):
        ov, game = self.ov()
        ov.wild_alert_since = 18 * harness.DAY
        st = self.pass_(ov, game, 20, squads=[my14_squad()], weapons_free=0, alert=True)
        order = next(a for t, a in st if t == "squad_order")
        gob = [{"id": 900, "race": "GOBLIN", "invader": True, "x": 60, "y": 98, "z": SURFACE}]
        sq = dict(my14_squad(), orders=[dict(order)], armed=4,
                  members=[member(i, "(copper battle axe)", True) for i in (238, 99, 241, 95)])
        calls = self.pass_(ov, game, 21, squads=[sq], weapons_free=0, alert=True, hostiles=gob)
        self.assertIn(("squad_order", {"order": "attack"}), calls)
        self.assertIsNone(ov.muster)


def cit(i, prof="Peasant", labors=(), skills=None, **kw):
    u = {"id": i, "profession": prof, "adult": True, "positions": [], "labors": list(labors),
         "skills": dict(skills or {}), "job": "idle"}
    u.update(kw)
    return u


class PickGame(FakeGame):
    def __init__(self, citizens=None):
        super().__init__()
        self.citizens = citizens

    def query(self, name, **kw):
        self.queries.append((name, kw))
        if name == "units" and kw.get("kind") == "citizens":
            if self.citizens is None:
                return {"ok": False, "error_code": "bad_arguments"}
            return {"result": {"units": [dict(u) for u in self.citizens]}}
        return {"result": {"units": []}}


class SquadPick(Base):
    def pick(self, citizens, n=4, obs_dwarves=None):
        game = PickGame(citizens)
        ov = harness.Overseer(game, days=216)
        resp = fort(5, squads=[], weapons_free=0, cit=20, building=False, hatch=True)
        if obs_dwarves is not None:
            resp["observation"]["dwarves"] = obs_dwarves
        ov.load(resp)
        return ov.squad_pick(n), ov

    def test_tiers_military_then_plain_then_essential_never_tool_workers(self):
        cs = [cit(1, "Miner", ["MINE"]), cit(2, "Carpenter", ["CARPENTER", "CUTWOOD"]),
              cit(3, "Brewer", ["BREWER"]), cit(4, "Stonecrafter"), cit(5, "Recruit"),
              cit(6, "Bone Carver", skills={"WRESTLING": 3}), cit(7, "Planter"), cit(8, "Engraver")]
        ids, _ = self.pick(cs)
        self.assertEqual(ids, [5, 6, 4, 8])   # Recruit; then by combat skill (6 wrestles), then id
        self.assertNotIn(1, ids)
        self.assertNotIn(2, ids)               # the CUTWOOD labor marks a carpenter-woodcutter

    def test_fisher_is_essential(self):
        # hint hard OP1-0 on c44c96b: the Fisherdwarf (MELEE_COMBAT 5, the only FISH labor) was picked as tier 2 on
        # day 111; a kea crippled him on duty and prepared fish stood at 0 for days 168-307
        cs = [cit(1, "Fisherdwarf", ["FISH"], skills={"MELEE_COMBAT": 5}), cit(2, "Stonecrafter"),
              cit(3, "Engraver"), cit(4, "Jeweler"), cit(5, "Gem Cutter")]
        ids, _ = self.pick(cs)
        self.assertEqual(ids, [2, 3, 4, 5])
        ids, _ = self.pick(cs[:3])
        self.assertEqual(ids, [2, 3, 1])       # still drafted only when tiers 1-2 can't fill the squad

    def test_sole_fish_labor_holder_is_essential(self):
        cs = [cit(1, "Peasant", ["FISH"], skills={"AXE": 4}), cit(2, "Stonecrafter"), cit(3, "Engraver"),
              cit(4, "Jeweler"), cit(5, "Gem Cutter")]
        ids, _ = self.pick(cs)
        self.assertNotIn(1, ids)
        cs.append(cit(6, "Peasant", ["FISH"]))   # two holders: neither is the fort's only fisher
        ids, _ = self.pick(cs)
        self.assertEqual(ids[0], 1)

    def test_essential_fill_before_tool_workers(self):
        cs = [cit(1, "Miner", ["MINE"]), cit(2, "Woodcutter"), cit(3, "Brewer"), cit(4, "Cook"),
              cit(5, "Mason"), cit(6, "Peasant")]
        ids, _ = self.pick(cs)
        self.assertEqual(ids, [6, 3, 4, 5])

    def test_tool_workers_only_to_reach_the_guard_minimum(self):
        cs = [cit(1, "Miner", ["MINE"], skills={"AXE": 2}), cit(2, "Woodcutter", ["CUTWOOD"]),
              cit(3, "Miner", ["MINE"]), cit(4, "Peasant"), cit(5, "Brewer")]
        ids, ov = self.pick(cs, n=6)
        self.assertEqual(ids, [4, 5, 1, 2])   # 2 non-tool, filled to MARK_SQUAD_MIN (4) and no further
        self.assertEqual(self.logs("squad_pick")[-1]["tool_workers"], [1, 2])

    def test_ineligible_left_out(self):
        cs = [cit(1, positions=["MANAGER"]), cit(2, adult=False), cit(3, squad_id=5), cit(4, mood="Fey"),
              cit(5), cit(6), cit(7), cit(8)]
        ids, _ = self.pick(cs)
        self.assertEqual(ids, [5, 6, 7, 8])

    def test_lost_query_falls_back_to_the_observation(self):
        obs = [{"id": 10, "profession": "Miner", "adult": True, "positions": [], "x": 1, "y": 1, "z": 1},
               {"id": 11, "profession": "Peasant", "adult": True, "positions": [], "x": 1, "y": 1, "z": 1},
               {"id": 12, "profession": "expedition leader", "adult": True, "positions": ["EXPEDITION_LEADER"],
                "x": 1, "y": 1, "z": 1}]
        ids, _ = self.pick(None, obs_dwarves=obs)
        self.assertEqual(ids, [11, 10])
        self.assertEqual(self.logs("squad_pick")[-1]["source"], "observe")

    def test_nobody_eligible_sends_the_size(self):
        game = PickGame([])
        ov = harness.Overseer(game, days=216)
        resp = fort(5, squads=[], weapons_free=0, cit=16)
        resp["observation"]["dwarves"] = []
        resp["observation"]["administrators"] = {"citizens": 16}
        ov.load(resp)
        ov.count = 0
        ov.defend()
        self.assertIn(("create_squad", {"size": 4}), game.calls)


class ArmGame(FakeGame):
    def __init__(self, groups=(), armour=(), refuse_metal=False):
        super().__init__(groups)
        self.armour, self.refuse_metal = list(armour), refuse_metal

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool == "equip_squad" and args.get("uniform") == "metal" and self.refuse_metal:
            return {"ok": False, "error_code": "game_refused"}
        return {"ok": True, "result": {}}

    def query(self, name, **kw):
        if name == "stocks" and kw.get("item_type") == "ARMOR":
            self.queries.append((name, kw))
            return {"result": {"ok": True, "groups": [dict(g) for g in self.armour]}}
        return super().query(name, **kw)


def armour(material, items):
    return {"item_type": "ARMOR", "item_subtype": "ITEM_ARMOR_MAIL_SHIRT", "material": material, "items": items,
            "count": items, "forbidden": 0, "in_job": 0, "in_building": 0, "in_inventory": 0}


class UniformChoice(Base):
    def go(self, game):
        ov = harness.Overseer(game, days=216)
        return ov, self.pass_(ov, game, 20, squads=[fresh()], weapons_free=0)

    def test_metal_when_metal_armour_lies_free(self):
        ov, calls = self.go(ArmGame([group(SPEAR, 3)], [armour("INORGANIC:COPPER", 2)]))
        self.assertIn(("equip_squad", {"uniform": "metal"}), calls)
        self.assertEqual(self.logs("equip_once")[-1]["uniform"], "metal")

    def test_leather_otherwise(self):
        ov, calls = self.go(ArmGame([group(SPEAR, 3)], [armour("PLANT:PIG_TAIL:THREAD", 5)]))
        self.assertIn(EQUIP, calls)

    def test_refused_metal_falls_back_to_leather_next_pass(self):
        game = ArmGame([group(SPEAR, 3)], [armour("INORGANIC:IRON", 1)], refuse_metal=True)
        ov, calls = self.go(game)
        self.assertIn(("equip_squad", {"uniform": "metal"}), calls)
        self.assertTrue(ov.metal_refused)
        calls = self.pass_(ov, game, 20.5, squads=[fresh()], weapons_free=0)
        self.assertIn(EQUIP, calls)


class Armable(Base):
    """probe p4: a second equip_squad left weapon_assigned false for good, yet the members fetched their weapons on
    duty (stationed: armed 3) — armable comes from that, not from weapon_assigned alone."""

    def test_on_duty_weapons_make_members_armable_after_assignment_reads_false(self):
        ov, game = self.ov()
        cleared = my14_squad(assigned=False)
        st = {"order": "station", "x": 100, "y": 100, "z": SURFACE - 1}
        on = dict(cleared, orders=[st], members=[member(238, "(copper battle axe)"), member(99, "(copper spear)"),
                                                 member(241), member(95, "(iron pick)")])
        self.pass_(ov, game, 30, squads=[on], weapons_free=0, building=False, hatch=True)
        self.pass_(ov, game, 31.5, squads=[on], weapons_free=0, building=False, hatch=True)
        self.assertEqual(ov.armable_ids(on), [99, 238])   # the miner's own pick is no evidence
        self.assertTrue(ov.duty_seen)
        # later, off duty (armed 0 is normal) with a weak-animal threat: the muster goes, though assigned reads false
        ov.wild_alert_since = 39 * harness.DAY
        off = dict(cleared, armed=0)
        calls = self.pass_(ov, game, 40, squads=[off], weapons_free=0, alert=True)
        self.assertTrue([a for t, a in calls if t == "squad_order" and a.get("order") == "station"])

    def test_wildlife_never_musters_a_squad_with_nothing_known(self):
        ov, game = self.ov()
        ov.wild_alert_since = 18 * harness.DAY
        calls = self.pass_(ov, game, 20, squads=[dict(my14_squad(assigned=False), armed=0)], weapons_free=0,
                           alert=True)
        self.assertFalse([c for c in calls if c[0] == "squad_order"])

    def test_muster_ends_after_a_day_on_duty_with_nobody_armable(self):
        ov, game = self.ov()
        gob = [{"id": 900, "race": "GOBLIN", "invader": True, "x": 60, "y": 98, "z": SURFACE}]
        sq = dict(my14_squad(assigned=False), armed=0)
        calls = self.pass_(ov, game, 20, squads=[sq], weapons_free=0, alert=True, hostiles=gob)
        order = next(a for t, a in calls if t == "squad_order" and a.get("order") == "station")
        on = dict(sq, orders=[dict(order)])
        self.pass_(ov, game, 20.5, squads=[on], weapons_free=0, alert=True, hostiles=gob)
        calls = self.pass_(ov, game, 21.6, squads=[on], weapons_free=0, alert=True, hostiles=gob)
        self.assertIn(("squad_order", {"order": "stand_down"}), calls)
        self.assertEqual(self.logs("guard_muster_end")[-1]["why"], "no_weapons")


SPEAR = ("add_manager_order", {"job": "MakeWeapon", "material_category": ["wood"],
                               "item_subtype": "ITEM_WEAPON_SPEAR", "amount": 3})


def wood_fort(day, squads, logs=200, carpenters=True, **kw):
    resp = fort(day, squads=squads, weapons_free=0, **kw)
    o = resp["observation"]
    o["stocks"].update({"logs_usable": logs, "beds": 40, "tables": 40, "chairs": 40, "barrels_empty": 40})
    o["workshops"] = [{"id": 1, "type": "Carpenters"}] if carpenters else []
    return resp


class SpearSupply(Base):
    """probe p6: a wooden spear (MakeWeapon, wood, ITEM_WEAPON_SPEAR) is made at the Carpenters within a day and DF
    fills the empty melee slot with it — no equip_squad re-call."""

    def run_days(self, ov, game, days, squads, **kw):
        out = []
        for day in days:
            ov.load(wood_fort(day, squads, **kw))
            ov.count = 0
            game.calls.clear()
            ov.defend()
            out.append(list(game.calls))
        return out

    def assigned_one(self):
        sq = my14_squad(assigned=False)
        sq["members"][0] = member(238, assigned=True)   # the day-after snapshot: one weapon assigned
        return sq

    def test_shortfall_ordered_the_day_after_the_uniform(self):
        ov, game = self.ov()
        ov.equip_day = 10
        first, second = self.run_days(ov, game, (10, 11), [self.assigned_one()])
        self.assertNotIn(SPEAR, first)                 # the snapshot comes the day after
        self.assertIn(SPEAR, second)                   # 4 members - 1 armable
        self.assertEqual(self.logs("spear_order")[-1]["short"], 3)
        self.assertEqual(ov.spears_ordered, 3)

    def test_not_while_the_order_is_on_the_book_nor_within_the_retry(self):
        ov, game = self.ov()
        ov.equip_day = 10
        self.run_days(ov, game, (11,), [self.assigned_one()])
        ov.key_order["spear"] = 77
        resp = wood_fort(20, [self.assigned_one()])
        resp["observation"]["orders"] = [{"id": 77, "job": "MakeWeapon", "left": 3}]
        ov.load(resp)
        ov.count = 0
        game.calls.clear()
        ov.defend()
        self.assertNotIn("add_manager_order", [t for t, _ in game.calls])
        calls = self.run_days(ov, game, (13,), [self.assigned_one()])[0]
        self.assertNotIn("add_manager_order", [t for t, _ in calls])   # within SPEAR_RETRY_DAYS of day 11

    def test_logs_and_barrels_first(self):
        ov, game = self.ov()
        ov.equip_day = 10
        calls = self.run_days(ov, game, (11,), [self.assigned_one()], logs=20)[0]
        self.assertNotIn("add_manager_order", [t for t, _ in calls])
        self.assertEqual(self.logs("spear_wait")[-1]["why"], "logs")
        ov, game = self.ov()
        ov.equip_day = 10
        calls = self.run_days(ov, game, (11,), [self.assigned_one()], carpenters=False)[0]
        self.assertEqual(self.logs("spear_wait")[-1]["why"], "no_carpenters")

    def test_barrel_press_waits(self):
        ov, game = self.ov()
        ov.equip_day = 10
        ov.barrel_press = lambda: True   # brewable plants waiting on barrels
        ov.press_stand = True
        calls = self.run_days(ov, game, (11,), [self.assigned_one()])[0]
        self.assertNotIn("add_manager_order", [t for t, _ in calls])
        self.assertEqual(self.logs("spear_wait")[-1]["why"], "barrel_press")

    def test_the_harvest_press_alone_does_not_hold_the_spears(self):
        ov, game = self.ov()
        ov.equip_day = 10
        ov.barrel_press = lambda: True   # pressed on the crops in the plots only (press_stand False)
        calls = self.run_days(ov, game, (11,), [self.assigned_one()])[0]
        self.assertIn("add_manager_order", [t for t, _ in calls])

    def test_no_order_when_every_member_is_armable(self):
        ov, game = self.ov()
        ov.equip_day = 10
        full = my14_squad()
        full["members"][3] = member(95, assigned=True)
        calls = self.run_days(ov, game, (11,), [full])[0]
        self.assertNotIn("add_manager_order", [t for t, _ in calls])

    def test_lifetime_cap(self):
        ov, game = self.ov()
        ov.equip_day = 10
        ov.spears_ordered = harness.SPEAR_LIFETIME - 1
        calls = self.run_days(ov, game, (11,), [self.assigned_one()])[0]
        self.assertIn(("add_manager_order", dict(SPEAR[1], amount=1)), calls)


if __name__ == "__main__":
    unittest.main()
