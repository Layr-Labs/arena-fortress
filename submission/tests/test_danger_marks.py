"""cx danger marks and the chunked advance (owner 2026-11-10: zero deaths). DF's isDanger flag (the units query's
`hostile`, the only one the advance tripwires and squad_order attack read) cannot be set by any tool, so the harness
keeps its own mark list: species seeded from the death census (gray langur, kea, carnotaurus, kingsnake, sea
lamprey, carp, the monkeys) and learned in play from interrupts and citizen combat reports. A marked animal near the
wagon or a citizen sounds the alert like an enemy; an armed 4+ squad is stationed on a weak (monkey/kea) one only;
the model's advance runs in short pieces with a danger look between them. No game or network."""
import io
import json
import sys
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness  # noqa: E402
from plain import harness as plain  # noqa: E402

WAGON = {"present": True, "x": 95, "y": 95, "z": 169}
MASON = {"id": 7, "name": "Catten", "profession": "Mason", "x": 150, "y": 40, "z": 169}
SQUAD_READY = {"id": 0, "armed": 4, "uniform": "leather", "orders": [],
               "members": [{"id": i} for i in range(4)]}
SQUAD_WEAK = {"id": 0, "armed": 1, "uniform": "leather", "orders": [], "members": [{"id": i} for i in range(4)]}


class FakeGame:
    def __init__(self, units=()):
        self.calls, self.units, self.queries = [], list(units), 0

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {}}

    def query(self, *a, **kw):
        self.queries += 1
        return {"result": {"units": list(self.units)}}


def fort(day, alert=False, cancels=(), events=(), dwarves=(MASON,), squads=(), hostiles=0):
    obs = {"date": {"abs_tick": day * harness.DAY}, "administrators": {"citizens": 18},
           "stocks": {"drink": 500, "food_edible": 150}, "map": {"sites": [], "wagon": dict(WAGON)},
           "dwarves": [dict(x) for x in dwarves], "recent_cancellations": list(cancels),
           "recent_events": list(events), "military": {"squads": [dict(s) for s in squads]},
           "threats": {"visible_hostiles": hostiles, "hostiles": []},
           "burrows": {"civilian_alert": alert, "list": [{"id": 0, "civ_alert_burrow": True}]}}
    return {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": 216 - day}


class Quiet(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)


class Marks(Quiet):
    def test_the_seed_holds_every_species_in_the_death_census(self):
        for s in ("gray langur", "kea", "carnotaurus", "kingsnake", "sea lamprey", "rhesus macaque"):
            self.assertIn(s, harness.DANGER_SEED)
        # CX_REVIEW §3-8: no record shows a carp attacking a citizen (its fights are with other animals)
        self.assertNotIn("carp", harness.DANGER_SEED)
        self.assertNotIn("carnotaurus", harness.DANGER_WEAK)   # no soldiers against the big ones

    def test_race_matching_by_words(self):
        self.assertTrue(harness.race_matches("GRAY_LANGUR", "langur"))
        self.assertTrue(harness.race_matches("GRAY_LANGUR", "gray langur"))
        self.assertTrue(harness.race_matches("BIRD_KEA", "kea"))
        self.assertFalse(harness.race_matches("BIRD_RAVEN", "kea"))
        self.assertFalse(harness.race_matches("CARPENTER_BEE", "carpenter ant"))

    def test_mark_names_drop_sex_words_and_the_forts_own_animals(self):
        self.assertEqual(harness.mark_name("badger boar"), "badger")
        self.assertIsNone(harness.mark_name("stray dog"))
        self.assertIsNone(harness.mark_name("combat"))

    def test_learning_from_interrupts_and_citizen_combat(self):
        ov = harness.Overseer(FakeGame(), days=216)
        ov.load(fort(40, cancels=["Urist cancels Fish: Interrupted by a giant buzzard."],
                     events=["The stonecrafter punches the mantis man in the head with his right hand!",
                             "The puppy shakes the platypus around by the head!",   # no citizen in it
                             "The water buffalo charges at the mason!"],
                     dwarves=[MASON, dict(MASON, id=8, profession="Stonecrafter")]))
        self.assertNotIn("giant buzzard", ov.marked)   # one interrupt is a nuisance, not a mark
        ov.load(fort(41, cancels=["Urist cancels Fish: Interrupted by a giant buzzard.",
                                  "Bomrek cancels Haul: Interrupted by a giant buzzard.",
                                  "Urist cancels Fish: Interrupted by a giant buzzard."]))   # 2 distinct lines so far
        self.assertNotIn("giant buzzard", ov.marked)
        ov.load(fort(42, cancels=["Ingiz cancels Fell: Interrupted by a giant buzzard."]))
        self.assertEqual(ov.marked.get("giant buzzard"), "interrupt")   # MARK_LEARN_INTERRUPTS distinct lines
        self.assertEqual(ov.marked.get("mantis man"), "combat")
        self.assertEqual(ov.marked.get("water buffalo"), "combat")
        self.assertNotIn("platypus", ov.marked)
        self.assertNotIn("puppy", ov.marked)
        self.assertNotIn("stonecrafter", ov.marked)

    def test_the_record_kea_brawl_is_read(self):   # full2 hint hard MY1-1 day 40 (a mason drowned in it)
        ov = harness.Overseer(FakeGame(), days=216)
        found = ov.learn_marks({"dwarves": [MASON, dict(MASON, profession="Carpenter")], "recent_events": [
            "The kea bites the mason in the head, denting the skin and bruising the muscle!",
            "The carpenter scratches the kea in the right lower leg and the severed part sails off in an arc!"]})
        self.assertEqual([f[0] for f in found], ["kea", "kea"])


class Guard(Quiet):
    def look(self, ov, game, day, **kw):
        ov.load(fort(day, **kw))
        ov.count = 0
        game.calls.clear()
        ov.defend()
        ov.wildlife_response()
        ov.mark_guard()
        return [(t, a) for t, a in game.calls if t in ("civilian_alert", "squad_order")]

    def test_a_carnotaurus_near_a_citizen_sounds_the_alert_and_sends_no_soldier(self):
        # f7f4716b OP1-4: the carnotaurus killed a metalcrafter working outside on day 80 (hostile False)
        game = FakeGame([{"id": 5, "race": "CARNOTAURUS", "hostile": False, "x": 160, "y": 45, "z": 169}])
        ov = harness.Overseer(game, days=336)
        calls = self.look(ov, game, 78, squads=[SQUAD_READY])
        self.assertEqual(calls, [("civilian_alert", {"on": True})])   # 10 tiles from the mason, 65 from the wagon
        self.assertIn("carnotaurus", ov.wild_watched())

    def test_a_langur_troop_gets_the_alert_and_a_ready_squad_stationed_on_it(self):
        game = FakeGame([{"id": 31, "race": "GRAY_LANGUR", "hostile": False, "x": 122, "y": 104, "z": 169}])
        ov = harness.Overseer(game, days=216)
        calls = self.look(ov, game, 171, squads=[SQUAD_READY])
        self.assertIn(("civilian_alert", {"on": True}), calls)
        self.assertIn(("squad_order", {"order": "station", "x": 122, "y": 104, "z": 169}), calls)
        self.assertIsNotNone(ov.mark_station)
        # the next day, alert on and the station standing: defend() does not stand the squad down
        calls = self.look(ov, game, 172, alert=True, squads=[dict(SQUAD_READY, orders=[{"order": "station"}])])
        self.assertNotIn(("squad_order", {"order": "stand_down"}), calls)
        self.assertNotIn(("civilian_alert", {"on": False}), calls)   # held while the troop is near
        # the troop gone past MARK_RANGE: the squad stands down
        game.units = [{"id": 31, "race": "GRAY_LANGUR", "hostile": False, "x": 10, "y": 10, "z": 169}]
        calls = self.look(ov, game, 176, alert=True, squads=[dict(SQUAD_READY, orders=[{"order": "station"}])])
        self.assertIn(("squad_order", {"order": "stand_down"}), calls)
        self.assertIsNone(ov.mark_station)

    def test_a_half_armed_squad_is_not_sent(self):
        game = FakeGame([{"id": 31, "race": "GRAY_LANGUR", "hostile": False, "x": 122, "y": 104, "z": 169}])
        ov = harness.Overseer(game, days=216)
        calls = self.look(ov, game, 171, squads=[SQUAD_WEAK])
        self.assertEqual(calls, [("civilian_alert", {"on": True})])

    def test_a_far_or_visiting_animal_sounds_nothing(self):
        game = FakeGame([{"id": 31, "race": "GRAY_LANGUR", "hostile": False, "x": 10, "y": 10, "z": 169},
                         {"id": 32, "race": "GRAY_LANGUR", "hostile": False, "visitor": True, "x": 96, "y": 96,
                          "z": 169}])
        ov = harness.Overseer(game, days=216)
        self.assertEqual(self.look(ov, game, 171), [])

    def test_a_marked_animal_back_near_re_sounds_after_the_rest(self):
        # a small marked animal keeps the evidence rule (CX_REVIEW P1-4)
        game = FakeGame([{"id": 5, "race": "BIRD_KEA", "hostile": False, "x": 100, "y": 100, "z": 169}])
        ov = harness.Overseer(game, days=336)
        self.assertEqual(self.look(ov, game, 78), [("civilian_alert", {"on": True})])
        self.assertEqual(self.look(ov, game, 89, alert=True), [("civilian_alert", {"on": False})])   # 10-day cap
        self.assertEqual(self.look(ov, game, 90), [])                                  # the rest: eat and drink
        # still sitting by the wagon, 50 tiles from the mason, no fight — a resident, no re-sound
        self.assertEqual(self.look(ov, game, 95), [])
        game.units = [{"id": 5, "race": "BIRD_KEA", "hostile": False, "x": 145, "y": 45, "z": 169}]
        self.assertEqual(self.look(ov, game, 96), [("civilian_alert", {"on": True})])  # closing on the mason: again

    def test_a_carnotaurus_by_the_wagon_re_sounds_once_the_rest_is_over(self):
        # cx big-beast hold (owner 2026-11-10): no evidence rule for a large beast — only the cap and the rest
        game = FakeGame([{"id": 5, "race": "CARNOTAURUS", "hostile": False, "x": 100, "y": 100, "z": 169}])
        ov = harness.Overseer(game, days=336)
        self.assertEqual(self.look(ov, game, 78), [("civilian_alert", {"on": True})])
        self.assertEqual(self.look(ov, game, 84, alert=True), [])   # held: no evidence, still near the wagon
        self.assertEqual(self.look(ov, game, 89, alert=True), [("civilian_alert", {"on": False})])   # 10-day cap
        self.assertEqual(self.look(ov, game, 90), [])                                  # the rest: eat and drink
        self.assertEqual(self.look(ov, game, 92), [("civilian_alert", {"on": True})])  # rest over, still near

    def test_danger_signs(self):
        game = FakeGame([{"id": 31, "race": "GRAY_LANGUR", "hostile": False, "x": 122, "y": 104, "z": 169}])
        ov = harness.Overseer(game, days=216)
        signs = ov.danger_signs(fort(171, cancels=["U cancels Eat: Interrupted by a gray langur."]))
        self.assertIn("marked:gray langur", signs)
        self.assertIn("near:gray langur", signs)
        self.assertIn("interrupt:gray langur", signs)
        ov.danger_signs(fort(171))
        self.assertEqual(game.queries, 1)   # the chunk look's query: once a game day
        game.units = []
        self.assertEqual(ov.danger_signs(fort(172)), [])


class ChunkGame:
    def __init__(self, days=216, stop_at=None):
        self.days, self.day = days, 100
        self.actions, self.observed = [], 0
        self.last = {"day": self.day, "tick": self.day * 1200, "days_left": days - self.day}
        self.stop_at = stop_at

    def observe(self):
        self.observed += 1
        self.last = {"day": self.day, "tick": self.day * 1200, "days_left": self.days - self.day, "game_over": False}
        return {**self.last, "observation": {"date": {"abs_tick": self.day * 1200}}}

    def act(self, name, args):
        self.actions.append((name, dict(args)))
        res = {"advanced_days": args["days"], "advanced_ticks": args["days"] * 1200, "stopped": None}
        if self.stop_at is not None and self.day < self.stop_at <= self.day + args["days"]:
            res = {"advanced_days": self.stop_at - self.day, "advanced_ticks": 600,
                   "stopped": {"reason": "citizen_died", "detail": "8 citizens, was 9"}}
        self.day += int(res["advanced_days"])
        self.last = {"day": self.day, "tick": self.day * 1200, "days_left": self.days - self.day}
        return {**self.last, "ok": True, "result": res}


class FakeGuard:
    def __init__(self, seq=()):
        self.risk, self.seq, self.looks = [], list(seq), 0

    def danger_signs(self, resp, query=True):
        self.looks += 1
        return self.seq.pop(0) if self.seq else []

    def water_rising_stop(self):
        pass


def plain_runner(game, guard, wall_s=None):
    r = plain.Plain.__new__(plain.Plain)
    r.game, r.guard, r.stats = game, guard, {}
    r.wall_s, r.t0, r.model_wait, r.day0 = wall_s, time.monotonic(), 0.0, 100
    return r


class Chunked(Quiet):
    def test_a_quiet_advance_runs_whole_in_two_day_pieces(self):
        game, guard = ChunkGame(), FakeGuard()
        resp = plain_runner(game, guard).chunked({"days": 7})
        self.assertEqual([a["days"] for _, a in game.actions], [2, 2, 2, 1])
        self.assertEqual(resp["result"]["advanced_days"], 7)
        self.assertIsNone(resp["result"]["stopped"])
        self.assertEqual(game.observed, 3)

    def test_a_new_sign_stops_it_and_hands_back(self):
        game, guard = ChunkGame(), FakeGuard([[], ["marked:gray langur"]])
        resp = plain_runner(game, guard).chunked({"days": 10})
        self.assertEqual([a["days"] for _, a in game.actions], [2, 2])
        self.assertEqual(resp["result"]["advanced_days"], 4)
        self.assertEqual(resp["result"]["stopped"]["reason"], "danger_sign")

    def test_a_sign_already_on_runs_one_day_pieces_and_does_not_stop_on_itself(self):
        game, guard = ChunkGame(), FakeGuard([["alert"], ["alert"]])
        guard.risk = ["alert"]
        resp = plain_runner(game, guard).chunked({"days": 3})
        self.assertEqual([a["days"] for _, a in game.actions], [1, 1, 1])
        self.assertEqual(resp["result"]["advanced_days"], 3)

    def test_a_tripwire_inside_a_piece_ends_it(self):
        game, guard = ChunkGame(stop_at=103), FakeGuard()
        resp = plain_runner(game, guard).chunked({"days": 7})
        self.assertEqual([a["days"] for _, a in game.actions], [2, 2])
        self.assertEqual(resp["result"]["stopped"]["reason"], "citizen_died")

    def test_a_tight_wall_clock_runs_it_whole(self):
        game, guard = ChunkGame(), FakeGuard()
        r = plain_runner(game, guard, wall_s=1000)
        r.t0 = time.monotonic() - 800   # 800 s for 0 days... measured over 10 days below
        r.day0 = 90
        resp = r.chunked({"days": 7})
        self.assertEqual([a["days"] for _, a in game.actions], [7])
        self.assertEqual(resp["result"]["advanced_days"], 7)

    def test_the_models_stop_on_list_is_dropped(self):
        game = ChunkGame()
        r = plain_runner(game, FakeGuard())
        r.tool_names, r.messages, r.added, r.cancelled = {"advance_days"}, [], {}, []
        r.stats = {"actions": 0, "rejected": 0, "advances": 0, "churn_refused": 0}
        r.memory = SimpleNamespace(record=lambda *a, **k: None)
        r.run_call({"id": "1", "function": {"name": "advance_days", "arguments": json.dumps(
            {"days": 2, "stop_on": ["citizen_died"]})}})
        self.assertEqual(game.actions, [("advance_days", {"days": 2})])


if __name__ == "__main__":
    unittest.main()
