"""h2: a released lockdown orders a workshop on the surface, so that DF rebuilds its path index.

The API's lock_door only sets the hatch's flag. If DF rebuilds its path index while a hatch is locked, shelter and
surface become separate walk groups and the API's unlock leaves them so: citizens below find nothing above. In local
games that state lasted 20 and 52 days, digging and a farm plot below did not end it, and a workshop finished on the
surface did (challenge issue #238). A workshop waits for a dwarf with its labour, so one of each kind is ordered, and
the release is watched until one of them is seen finished."""
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import E1, HATCH, Lockdown, StubGame, hold, locked, threat_resp  # noqa: E402
from overseer.harness import Overseer  # noqa: E402
from overseer.openplay import CUT_DAYS, REINDEX_DAYS, REINDEX_MAX, REINDEX_SHOPS  # noqa: E402

FIRST, SECOND, THIRD = REINDEX_SHOPS
EACH = [(FIRST, "W1"), (SECOND, "W2"), (THIRD, "W3")]       # what a release orders on a fort with free sites
DAYS = 216 if FIRST == "Farmers" else 336        # the task this tree plays: the handed-over fort, or the full year


def sites(n=15):
    return (E1,) + tuple({"id": "W%d" % i, "kind": "W", "w": 3, "h": 3, "x": 80 + 4 * i, "y": 90, "z": 153,
                          "free": True} for i in range(1, n + 1))


def after(day, dist=None, alert=False, up=0, drink=50, shops=(), where=None, **kw):
    """A pass after the release: `up` of the ten citizens above ground, the rest two levels down; `shops` are the
    (id, kind, built) workshops listed beside the fort's own (a fourth entry, "suspended": its construction is)."""
    r = threat_resp(day, dist, alert=alert, sites=sites() if where is None else where, **kw)
    r["days_left"] = DAYS - day
    o = r["observation"]
    o["stocks"]["drink"] = drink
    for i, p in enumerate(o["dwarves"]):
        p.update(x=95, y=96, z=153 if i < up else 151)
    for i, k, b, *held in shops:
        w = {"id": i, "type": k, "built": b, "x": 90, "y": 90, "z": 153}
        if not b:
            w["job_details"] = [{"job": "ConstructBuilding", **({"suspended": True} if held else {})}]
        o["workshops"].append(w)
    return r


class Reconnect(Lockdown, unittest.TestCase):
    def setUp(self):
        self.buf = io.StringIO()
        self.out = redirect_stdout(self.buf)
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def play(self, r, refuse=(), codes=(), **state):
        """As Lockdown.play, on this tree's task, with a game that answers a build_workshop with the new workshop's
        id (501, 502, ...)."""
        g = StubGame(refuse=refuse)
        plain = g.act

        g.codes = list(codes)                # error codes the next build_workshop calls are refused with

        def act(tool, args):
            out = plain(tool, args)
            if tool == "build_workshop" and g.codes:
                return {"ok": False, "error_code": g.codes.pop(0), "error": "scripted"}
            if tool == "build_workshop" and out.get("ok"):
                out["result"] = {"id": 500 + len([1 for t, _ in g.calls if t == "build_workshop"]), "type": args["type"]}
            return out
        g.act = act
        ov = Overseer(g, goal="Run the fortress", days=DAYS)
        ov.set_task({"goal": "Run the fortress for %d days." % DAYS})
        ov.load(r)
        ov.count = 0
        for k, v in state.items():
            setattr(ov, k, v)
        ov.defend()
        return ov, g

    def logged(self, event):
        rows = [json.loads(line[line.find("{"):]) for line in self.buf.getvalue().splitlines() if "{" in line]
        return [r for r in rows if r.get("kind") == "reconnect" and r.get("event") == event]

    def release(self, day=120, refuse=(), codes=(), shops=(), where=None, edit=None, **state):
        """The pass that ends a lockdown: no hostile in sight any more, the hatch still shown locked."""
        r = after(day, alert=True, doors=locked(HATCH["id"]), shops=shops, where=where)
        if edit:
            edit(r["observation"])
        ov, g = self.play(r, refuse=refuse, codes=codes, lock=hold(day - 5), own_locks={HATCH["id"]}, **state)
        self.assertIsNone(ov.lock)
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": HATCH["id"]}])
        return ov, g

    def builds(self, g):
        return [(a["type"], a["site"]) for a in g.tools("build_workshop")]

    # the order
    def test_a_release_orders_one_workshop_of_each_kind(self):
        ov, g = self.release()
        self.assertEqual(self.builds(g), EACH)
        self.assertEqual(len(self.logged("build")), 3)
        self.again(ov, g, after(121, shops=[(501, FIRST, False), (502, SECOND, False), (503, THIRD, False)]))
        self.assertEqual(len(g.tools("build_workshop")), 3)                    # asked once while they wait

    def test_no_workshop_without_a_release(self):
        ov, g = self.play(after(120, up=4))
        for day in (121, 122, 123, 124):
            self.again(ov, g, after(day, up=4))
        self.assertEqual(g.tools("build_workshop"), [])
        self.assertIsNone(ov.freed)

    def test_an_accepted_build_is_booked_like_any_other(self):
        ov, g = self.release()
        for kind, site in EACH:
            self.assertIn((site, kind), ov.full_sites)
            self.assertEqual(ov.built_n.get(kind), 1)
            if isinstance(getattr(ov, "w_used_now", None), set):               # the tree that reserves a site for a pass
                self.assertIn(site, ov.w_used_now)
        self.assertEqual(ov.reindex_n, 3)

    def test_a_refused_site_is_followed_by_the_next(self):
        ov, g = self.release(refuse={("build_workshop", None)})
        self.assertEqual(self.builds(g), EACH)                                 # every one refused, each on its own site
        self.assertEqual(ov.reindex_n, 0)
        g.refuse.clear()
        self.again(ov, g, after(121))
        self.assertEqual(self.builds(g)[3:], [(FIRST, "W4"), (SECOND, "W5"), (THIRD, "W6")])
        self.assertEqual(ov.reindex_n, 3)

    def test_a_refusal_for_material_is_asked_again_on_the_same_site(self):
        ov, g = self.release(codes=["no_material"])
        self.assertEqual(self.builds(g), [(FIRST, "W1")])                      # nothing more on a pass without material
        self.again(ov, g, after(121))
        self.assertEqual(self.builds(g), [(FIRST, "W1")] + EACH)
        self.assertEqual(ov.reindex_n, 3)

    def test_a_site_without_an_id_is_passed_over(self):
        where = (E1, {"kind": "W", "w": 3, "h": 3, "x": 70, "y": 90, "z": 153, "free": True}) + sites()[1:]
        ov, g = self.release(where=where)
        self.assertEqual(self.builds(g), EACH)

    def test_the_last_site_is_left_for_a_butchers_still_to_come(self):
        def no_butchers(o):
            o["workshops"] = [w for w in o["workshops"] if w["type"] != "Butchers"]
        ov, g = self.release(where=sites(1), edit=no_butchers)
        self.assertEqual(g.tools("build_workshop"), [])
        ov, g = self.release(where=sites(3), edit=no_butchers)
        self.assertEqual(self.builds(g), EACH[:2])
        ov, g = self.release(where=sites(1))                                   # the Butchers stands: nothing to keep
        self.assertEqual(self.builds(g), EACH[:1])

    def test_a_kind_without_a_site_is_ordered_when_one_is_free(self):
        ov, g = self.release(where=sites(1))
        self.assertEqual(self.builds(g), EACH[:1])
        self.again(ov, g, after(121, shops=[(501, FIRST, False)], where=(E1,) + sites()[2:5]))
        self.assertEqual(self.builds(g), [(FIRST, "W1"), (SECOND, "W2"), (THIRD, "W3")])

    def test_no_more_material_than_there_is(self):
        def two_logs(o):
            o["stocks"]["logs_usable"] = 2
        ov, g = self.release(edit=two_logs)
        self.assertEqual(self.builds(g), EACH[:2])

    def test_nothing_is_ordered_on_a_list_that_cannot_be_read(self):
        def broken(o):
            o["workshops"] = "ERR: scripted"
        ov, g = self.release(edit=broken)
        self.assertEqual(g.tools("build_workshop"), [])
        self.again(ov, g, after(121, shops=[(77, FIRST, False)]))              # readable again: one already waits
        self.assertEqual(self.builds(g), [(SECOND, "W1"), (THIRD, "W2")])
        self.assertIsNotNone(ov.freed)

    def test_a_kind_still_waiting_is_not_ordered_again(self):
        ov, g = self.release(shops=[(77, FIRST, False)])                       # ordered at an earlier release
        self.assertEqual(self.builds(g), [(SECOND, "W1"), (THIRD, "W2")])
        self.again(ov, g, after(121, up=1, shops=[(77, FIRST, True)]))         # and built now: that joins the sides
        self.assertIsNone(ov.freed)

    def test_a_suspended_copy_does_not_stand_in(self):
        ov, g = self.release(shops=[(77, FIRST, False, "suspended")])          # nobody will finish that one
        self.assertEqual(self.builds(g), EACH)

    def test_a_kind_is_ordered_once_a_release_even_if_it_never_shows(self):
        ov, g = self.release()
        for day in range(121, 127):                                            # accepted, and never on the list
            self.again(ov, g, after(day, up=2))
        self.assertEqual(self.builds(g), EACH)

    def test_no_more_than_the_cap_in_one_game(self):
        ov, g = self.release(reindex_n=REINDEX_MAX - 1)
        self.assertEqual(self.builds(g), EACH[:1])                             # the last one the game may have
        self.assertEqual(ov.reindex_n, REINDEX_MAX)
        self.again(ov, g, after(121, up=3, shops=[(501, FIRST, True)]))
        ov.lock, ov.own_locks = hold(125), {HATCH["id"]}
        self.again(ov, g, after(130, alert=True, doors=locked(HATCH["id"]), shops=[(501, FIRST, True)]))
        self.again(ov, g, after(131, up=3, shops=[(501, FIRST, True)]))
        self.assertEqual(len(g.tools("build_workshop")), 1)

    # the watch
    def test_the_watch_ends_when_a_workshop_is_seen_built(self):
        ov, g = self.release()
        waiting = [(501, FIRST, False), (502, SECOND, False), (503, THIRD, False)]
        self.again(ov, g, after(121, up=3, shops=waiting))
        self.assertIsNotNone(ov.freed)                                         # out, but not joined yet
        self.again(ov, g, after(122, up=3, shops=[(501, FIRST, False), (502, SECOND, True), (503, THIRD, False)]))
        self.assertIsNone(ov.freed)                                            # any one of them built joins the sides
        self.assertEqual(len(self.logged("built")), 1)
        self.assertEqual(len(g.tools("build_workshop")), 3)

    def test_the_forts_own_workshop_of_these_kinds_counts(self):
        ov, g = self.release(shops=[(60, SECOND, False)])                      # one the fort itself had ordered
        self.assertEqual(self.builds(g), [(FIRST, "W1"), (THIRD, "W2")])
        self.again(ov, g, after(121, up=1, shops=[(60, SECOND, True), (501, FIRST, False), (502, THIRD, False)]))
        self.assertIsNone(ov.freed)

    def test_another_kind_finished_does_not_end_the_watch(self):
        ov, g = self.release(shops=[(60, "Kitchen", False)])                   # not a kind seen to join the sides
        self.again(ov, g, after(121, up=1, shops=[(60, "Kitchen", True), (501, FIRST, False)]))
        self.assertIsNotNone(ov.freed)

    def test_a_workshop_first_seen_built_after_the_release_counts(self):
        ov, g = self.release(where=sites(0))                                   # nothing could be ordered here
        self.assertEqual(g.tools("build_workshop"), [])
        self.again(ov, g, after(121, up=1, shops=[(777, FIRST, True)], where=sites(0)))     # placed and built since
        self.assertIsNone(ov.freed)

    def test_a_workshop_finished_during_the_lockdown_does_not_count(self):
        ov, g = self.release(shops=[(77, FIRST, True)])                        # built while the hatch was locked
        self.assertEqual(self.builds(g), EACH)
        self.again(ov, g, after(121, up=2, shops=[(77, FIRST, True), (501, FIRST, False)]))
        self.assertIsNotNone(ov.freed)

    def test_the_watch_ends(self):
        ov, g = self.release()
        for day in range(121, 122 + REINDEX_DAYS + 1):
            self.again(ov, g, after(day, shops=[(501, FIRST, False), (502, SECOND, False), (503, THIRD, False)]))
        self.assertIsNone(ov.freed)

    def test_each_release_orders_what_is_not_waiting(self):
        ov, g = self.release()
        done = [(501, FIRST, True), (502, SECOND, False), (503, THIRD, False)]
        self.again(ov, g, after(121, up=3, shops=done))
        self.assertIsNone(ov.freed)
        ov.lock, ov.own_locks = hold(125), {HATCH["id"]}                       # a second lockdown, released on day 130
        self.again(ov, g, after(130, alert=True, doors=locked(HATCH["id"]), shops=done))
        self.assertEqual(self.builds(g), EACH + [(FIRST, "W4")])               # the two still unbuilt will do for theirs

    # the log of a fort that stays below
    def test_nobody_above_and_no_drink_taken_is_logged_once(self):
        ov, g = self.release()
        for day in range(121, 121 + CUT_DAYS + 3):
            self.again(ov, g, after(day, shops=[(501, FIRST, False)]))
        self.assertEqual(len(self.logged("cut_off")), 1)

    def test_a_fort_that_came_up_is_not_logged_as_cut_off(self):
        ov, g = self.release()
        self.again(ov, g, after(121, up=1, shops=[(501, FIRST, False)]))
        for day in (122, 123):
            self.again(ov, g, after(day, shops=[(501, FIRST, False)]))
        self.assertEqual(self.logged("cut_off"), [])

    def test_a_drink_taken_counts_as_out(self):
        ov, g = self.release()
        for day in (121, 122, 123):                                            # nobody seen above, but drinks went
            self.again(ov, g, after(day, drink=41, shops=[(501, FIRST, False)]))
        self.assertEqual(self.logged("cut_off"), [])

    def test_an_alert_is_not_read_as_cut_off(self):
        ov, g = self.release()
        for day in (121, 122, 123):                                            # an alert (the thaw's) holds everyone below
            ov.load(after(day, alert=True, shops=[(501, FIRST, False)]))
            ov.reconnect(True)
        self.assertEqual(self.logged("cut_off"), [])
        self.assertIsNotNone(ov.freed)

    def test_an_alert_that_cannot_be_read_is_not_read_as_cut_off(self):
        ov, g = self.release()
        for day in (121, 122, 123):                                            # everybody below, the burrows unreadable
            ov.load(after(day, shops=[(501, FIRST, False)]))
            ov.reconnect(None)
        self.assertEqual(self.logged("cut_off"), [])

    def test_what_cannot_be_read_is_not_read_as_cut_off(self):
        ov, g = self.release()
        for day in (121, 122, 123):
            r = after(day, shops=[(501, FIRST, False)])
            r["observation"]["dwarves"] = "ERR: scripted"
            r["observation"]["stocks"] = "ERR: scripted"
            ov.load(r)
            ov.reconnect(False)
        self.assertEqual(self.logged("cut_off"), [])

    def test_a_half_read_list_of_dwarves_is_not_read_as_cut_off(self):
        ov, g = self.release()
        for day in (121, 122, 123):
            r = after(day, shops=[(501, FIRST, False)])
            for p in r["observation"]["dwarves"][1:]:                          # one position known, below; nine not
                del p["z"]
            ov.load(r)
            ov.reconnect(False)
        self.assertEqual(self.logged("cut_off"), [])


if __name__ == "__main__":
    unittest.main()
