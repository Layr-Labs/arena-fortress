"""A read-only view of one observation: the numbers and lookups the playbook and the advisor need.

Everything here is derived from GET /observe (facts only). The interpretation (what counts as a problem, what the
fort needs next) is this harness's own.
"""
import math

from .memory import DAY

CORE_WORKSHOPS = ("Carpenters", "Still", "Kitchen")


class Fort:
    def __init__(self, resp, game, info, mem):
        self.resp = resp
        self.game = game
        self.info = info
        self.mem = mem
        o = resp.get("observation") if isinstance(resp.get("observation"), dict) else {}
        self.o = o
        self.day = resp.get("day") or 0
        self.tick = resp.get("tick") or (o.get("date") or {}).get("abs_tick") or 0
        self.days_left = resp.get("days_left") if resp.get("days_left") is not None else 336
        self.days_total = self.day + self.days_left
        self.hands_off_in = resp.get("hands_off_in_days")
        self.st = o.get("stocks") if isinstance(o.get("stocks"), dict) else {}
        self.adm = o.get("administrators") if isinstance(o.get("administrators"), dict) else {}
        self.dwarves = [d for d in o.get("dwarves") or [] if isinstance(d, dict)]
        self.citizens = self.adm.get("citizens") or len(self.dwarves)
        m = o.get("map") if isinstance(o.get("map"), dict) else {}
        self.map = m
        self.surface_z = m.get("surface_z")
        self.sites = [s for s in m.get("sites") or [] if isinstance(s, dict)]
        self.workshops = [w for w in o.get("workshops") or [] if isinstance(w, dict)]
        self.orders = [x for x in o.get("orders") or [] if isinstance(x, dict)]
        self.farms = [f for f in o.get("farm_plots") or [] if isinstance(f, dict)]
        self.zones = [z for z in o.get("zones") or [] if isinstance(z, dict)]
        self.furniture = [f for f in o.get("furniture") or [] if isinstance(f, dict)]
        self.plugins = o.get("plugins") if isinstance(o.get("plugins"), dict) else {}
        self.threats = o.get("threats") if isinstance(o.get("threats"), dict) else {}
        self.moods = [x for x in o.get("moods") or [] if isinstance(x, dict)]
        self.military = o.get("military") if isinstance(o.get("military"), dict) else {}
        self.burrows = o.get("burrows") if isinstance(o.get("burrows"), dict) else {}
        self.doors = o.get("doors") if isinstance(o.get("doors"), dict) else {}
        self.cancellations = [str(x) for x in o.get("recent_cancellations") or []]
        self.events = [str(x) for x in o.get("recent_events") or []]
        self.dig_pending = o.get("dig_designations_pending") or 0

    # --- stocks ---------------------------------------------------------------------------------------------------
    def s(self, key, default=0):
        v = self.st.get(key, default)
        return v if isinstance(v, (int, float)) else default

    def free(self, kind):
        return (self.st.get("furniture_free") or {}).get(kind, 0) or 0

    @property
    def drink(self):
        return self.s("drink")

    @property
    def food(self):
        return self.s("food_edible")

    def seeds_kinds(self):
        return self.st.get("seeds_by_kind") or {}

    def raw_fish(self):
        """Raw fish in stock (free query, cached per view): they are food only once a Fishery cleans them."""
        if not hasattr(self, "_raw_fish"):
            try:
                r = self.game.query("stocks", item_type="FISH_RAW", limit=50).get("result") or {}
                self._raw_fish = sum((g.get("count") or 0) - (g.get("rotten") or 0) for g in r.get("groups") or [])
            except Exception:  # noqa: BLE001
                self._raw_fish = 0
        return self._raw_fish

    # --- workshops, orders ------------------------------------------------------------------------------------------
    def ws(self, typ, built=None):
        return [w for w in self.workshops if w.get("type") == typ and (built is None or bool(w.get("built")) == built)]

    def has_ws(self, typ):
        return bool(self.ws(typ))

    def orders_for(self, recipe=None, job=None, repeat=None):
        out = []
        for x in self.orders:
            if recipe and x.get("recipe") != recipe:
                continue
            if job and x.get("job") != job:
                continue
            if repeat is not None and bool(x.get("repeat")) != repeat:
                continue
            out.append(x)
        return out

    def pending(self, recipe):
        """Units still to make from one-time orders of this recipe."""
        return sum(x.get("left") or 0 for x in self.orders_for(recipe, repeat=False))

    # --- sites ------------------------------------------------------------------------------------------------------
    def sites_of(self, kind, free_only=True):
        return [s for s in self.sites if s.get("kind") == kind and (not free_only or s.get("free"))]

    def site(self, sid):
        return next((s for s in self.sites if s.get("id") == sid), None)

    def wagon(self):
        w = self.map.get("wagon") or {}
        return w.get("x"), w.get("y"), w.get("z")

    def near_wagon(self, sites):
        wx, wy, _ = self.wagon()
        if wx is None:
            return list(sites)
        return sorted(sites, key=lambda s: max(abs(s["x"] - wx), abs(s["y"] - wy)))

    # --- living space -----------------------------------------------------------------------------------------------
    def zones_of(self, typ):
        t = typ.lower().replace("_", "")
        return [z for z in self.zones if str(z.get("type", "")).lower().replace("_", "") == t]

    def placed(self, kind):
        return sum(1 for f in self.furniture if f.get("kind") == kind)

    def beds_placed(self):
        return self.placed("bed")

    def seats(self):
        """Dining seats: placed chairs in a dining-hall zone with a table in the same zone (approximation)."""
        n = 0
        for z in self.zones_of("DiningHall"):
            f = z.get("furniture") or {}
            n += min(f.get("chair", 0) or 0, f.get("table", 0) or 0)
        return n

    def office(self):
        off = self.adm.get("manager_office")
        return off if isinstance(off, dict) else None

    def manager_id(self):
        return self.adm.get("MANAGER_id")

    # --- threats ----------------------------------------------------------------------------------------------------
    def hostiles(self):
        return self.threats.get("visible_hostiles") or 0

    # --- for the advisor ----------------------------------------------------------------------------------------------
    def problems(self):
        p = []
        c = max(1, self.citizens)
        if self.drink < c:
            p.append(f"drink low: {self.drink} for {c} citizens (brewable plants {self.s('plants_brewable')}, "
                     f"empty barrels {self.s('barrels_empty')})")
        if self.food < 2 * c:
            p.append(f"edible food low: {self.food} for {c} citizens")
        if self.hostiles():
            p.append(f"{self.hostiles()} hostiles visible: {self.threats.get('by_race')}")
        for m in self.moods:
            p.append(f"mood: unit {m.get('unit_id')} {m.get('mood')} skill {m.get('skill')} job {m.get('job')} "
                     f"workshop {m.get('claimed_workshop')} needs {m.get('items_needed')}")
        st = self.o.get("stressed_citizens") or 0
        if st:
            p.append(f"{st} citizens stressed")
        if not self.adm.get("manager_active_for_orders"):
            p.append("no active manager: orders are not validated")
        stuck = [x for x in self.orders if not x.get("validated") and self.tick - (x.get("created_tick") or self.tick) > 5 * DAY]
        if stuck:
            p.append(f"{len(stuck)} orders unvalidated for 3+ days (manager office? {self.adm.get('manager_office')})")
        return p

    def summary(self):
        c = self.citizens
        lines = [
            f"citizens {c}, stressed {self.o.get('stressed_citizens')}, dead so far {self.threats.get('dead_citizens_total', 0)}",
            f"drink {self.drink}, edible food {self.food}, meals {self.s('prepared_meals')}, brewable plants "
            f"{self.s('plants_brewable')}, seeds {self.s('seeds')}, logs {self.s('logs_usable')}, "
            f"boulders {self.s('boulders_usable')}, empty barrels {self.s('barrels_empty')}",
            f"beds placed {self.beds_placed()} (free items {self.free('bed')}), dining seats ~{self.seats()} "
            f"(free tables {self.free('table')}, chairs {self.free('chair')})",
            "workshops: " + ", ".join(f"{w.get('type')}#{w.get('id')}{'' if w.get('built') else '(unbuilt)'}"
                                      f"[{len(w.get('jobs') or [])} jobs]" for w in self.workshops),
            "orders: " + ", ".join(f"#{x.get('id')} {x.get('recipe') or x.get('job')} {x.get('left')}/{x.get('total')}"
                                   f"{' ' + x['repeat'] if x.get('repeat') else ''}{'' if x.get('validated') else ' unvalidated'}"
                                   for x in self.orders),
            f"farm plots {len(self.farms)}: " + ", ".join(sorted({str(f.get('crop_this_season')) for f in self.farms})),
            "zones: " + ", ".join(f"{z.get('type')}#{z.get('id')}@z{z.get('z')}" for z in self.zones),
            f"manager active {self.adm.get('manager_active_for_orders')}, office {self.adm.get('manager_office')}",
            f"dig pending {self.dig_pending}; plugins {self.plugins}",
            "free sites: " + " ".join(f"{s['id']}@z{s.get('z')}" for s in self.sites if s.get("free"))[:600],
        ]
        if self.cancellations:
            lines.append("recent cancellations: " + " | ".join(self.cancellations[:5])[:600])
        if self.events:
            lines.append("recent events: " + " | ".join(self.events[:4])[:400])
        return "\n".join(lines)

    def autopilot_plan(self):
        return ["manager, office, automation plugins (autochop, seedwatch, autofarm)",
                "workshops Carpenters/Still/Kitchen and standing orders for barrels, drink, meals, beds, tables, chairs",
                "stairs, a farm level and a living level; farm plots, beds, dining tables and chairs, zones",
                "time: the harness advances days itself"]


def ceil_div(a, b):
    return int(math.ceil(a / float(b)))
