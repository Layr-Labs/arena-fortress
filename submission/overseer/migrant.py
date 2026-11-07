"""Public-goal migrant policy on i34-9's fa9c13cc controller.

Goal-based brewing, bed priority, overflow and pacing build on GordoAR 5ef22a35
and pepedesigner a9f894ea / 1812e717. The capacity accounting, partial-placement
continuation, space retry cache and office-chair exception are this revision.
Only the public task, observations and normal action responses are used.
"""
from .harness import Overseer, covers, d, lst


def applies(info):
    return bool(d(info).get("hands_off")) and (
        "every dwarf must have a placed bed" in str(d(info).get("goal") or "").casefold())


def bed_facts(resp):
    obs = d(resp.get("observation"))
    beds = [f for f in lst(obs.get("furniture")) if d(f).get("kind") == "bed"]
    citizens = d(obs.get("administrators")).get("citizens") or len(lst(obs.get("dwarves")))
    built = sum(bool(f.get("built")) for f in beds)
    free = d(d(obs.get("stocks")).get("furniture_free")).get("bed") or 0
    queued = sum(max(0, x.get("left") or 0) for x in lst(obs.get("orders"))
                 if d(x).get("recipe") == "make_bed")
    return {"citizens": citizens, "target": citizens + 12, "built": built,
            "planned": len(beds) - built, "free": free, "queued": queued}


class MigrantOverseer(Overseer):
    def __init__(self, game, goal="", days=0):
        super().__init__(game, goal=goal, days=days)
        self.full_areas = {}

    def workshops(self):
        super().workshops()
        carpenters = sum(d(w).get("type") == "Carpenters" for w in lst(self.o.get("workshops")))
        # Both built and planned workshops count. A successful build in super()
        # shares this rate-limit key, so stale facts cannot add a second today.
        if carpenters == 1 and self.logs() >= 5:
            self.build("Carpenters", retry=3)

    def supply(self):
        # A capped inherited order is not evidence of the required uncapped one.
        uncapped = any(x.get("recipe") == "brew_drink" and x.get("repeat")
                       and not any(d(c).get("stock") == "drink" for c in lst(x.get("when")))
                       for x in self.orders)
        if not uncapped:
            self.act("o_brew_growth", "add_order", {
                "recipe": "brew_drink", "amount": 3, "repeat": "daily",
                "when": [{"stock": "plants_brewable", "at_least": 2},
                         {"stock": "barrels_empty", "at_least": 1}]}, retry=3)
        if not self.standing("make_barrel"):
            self.act("o_barrel", "add_order", {
                "recipe": "make_barrel", "amount": 2, "repeat": "daily",
                "when": [{"stock": "barrels_empty", "below": 4},
                         {"stock": "logs", "at_least": 2}]}, retry=3)

        # Bed priority must not starve the manager's prerequisite. Existing
        # planned/installed office chairs count; dining chairs do not.
        office_ready = bool(d(self.adm.get("manager_office")).get("chair"))
        office_chair = any(d(z.get("furniture")).get("chair")
                           or d(z.get("furniture_planned")).get("chair") for z in self.zone("office"))
        if self.cit >= 14 and not office_ready and not office_chair and not self.free.get("chair") \
                and not self.pending("make_chair") and self.logs():
            self.act("o_manager_chair", "add_order", {"recipe": "make_chair", "amount": 1}, retry=2)

        # Free items plus all placement jobs are usable commitments; the total
        # stock count also includes unavailable/forbidden items. Never order the
        # same remaining need again while an earlier bed order is pending.
        committed = (self.placed.get("bed") or 0) + (self.free.get("bed") or 0)
        short = self.bed_target() - committed
        if short > 0 and not self.pending("make_bed") and self.logs():
            self.act("o_make_bed", "add_order", {"recipe": "make_bed", "amount": min(16, short)},
                     retry=1, limit=99)

    def housing_check(self):
        # supply() sizes production and furnish() installs the reserve every
        # pass; the inherited late bed/seat orders would duplicate that work.
        pass

    def area_state(self, area):
        geometry = tuple(area.get(k) for k in ("x", "y", "z", "w", "h", "open_tiles"))
        occupied = sum(covers(area, f) for f in lst(self.o.get("furniture")) if isinstance(f, dict))
        return geometry, occupied

    def furnish(self):
        remaining = min(self.free.get("bed") or 0,
                        max(0, self.bed_target() - (self.placed.get("bed") or 0)), 30)
        primary = self.room_for("dorm")
        # Use only public A sites and already-dug R rooms. An area's open_tiles
        # includes stairs and occupied floor: only an API placement proves space.
        areas = self.kind("A") + self.dug_rooms()
        if primary:
            areas = [primary] + areas
        seen, candidates = set(), []
        for area in areas:
            if area["id"] in seen or (area.get("open_tiles", 6) or 0) < 1:
                continue
            seen.add(area["id"])
            # Default site rectangles have a public 20x20 action limit.
            if any((area.get(k) or 0) > 20 for k in ("w", "h")):
                continue
            candidates.append(area)
        candidates.sort(key=lambda a: (a != primary, -(a.get("open_tiles") or 0), a["id"]))
        attempted = 0
        for area in candidates:
            state = self.area_state(area)
            old = self.full_areas.get(area["id"])
            # New dug floor or removed furniture can reopen a full area. A mere
            # day change, or even more furniture, cannot.
            blocked = old is not None and state[0] == old[0] and state[1] >= old[1]
            points = []
            if remaining and not blocked and attempted < 3:
                key = "surge_beds_" + area["id"]
                if self.may(key, retry=1, limit=99):
                    result = d(self.act(key, "place_furniture",
                                       {"kind": "bed", "site": area["id"], "count": remaining},
                                       retry=1, limit=99))
                    attempted += 1
                    if result.get("ok"):
                        at = d(result.get("result")).get("at") or []
                        if at and not isinstance(at[0], (list, tuple)):
                            at = [at]
                        points = [{"kind": "bed", "x": x, "y": y, "z": z} for x, y, z in at]
                        # Partial success consumes only returned placements.
                        # Continue into another area with the actual remainder.
                        remaining = max(0, remaining - len(points))
                    elif result.get("error_code") == "no_space":
                        self.full_areas[area["id"]] = state
                    elif result.get("error_code") == "no_material":
                        remaining = 0
            if self.needs_zone(area, self.zone("dorm") + self.zone("bedroom"), ("bed",), points):
                self.act("surge_dorm_" + area["id"], "make_zone",
                         {"kind": "dormitory", "site": area["id"]}, retry=3)

    def advance_cap(self, resp):
        facts = bed_facts(resp)
        left = resp.get("hands_off_in_days")
        if facts["built"] < facts["target"]:
            if facts["free"] or facts["planned"] or (isinstance(left, int) and left <= 7):
                return 1
            return 2
        return 3

    def status(self, resp):
        f = bed_facts(resp)
        return ("MIGRANT CAPACITY: citizens={citizens}; reserve target={target}; "
                "built beds={built}; placement jobs={planned}; free bed items={free}; "
                "manufacturing jobs left={queued}. Only built beds meet the final goal. "
                "The layer handles bed production/placement, two carpenters, the manager chair, "
                "and uncapped brewing. Repair a reported blocker; do not duplicate these orders.").format(**f)
