"""Open play (MY1, OP1: no hands-off window): when the animals are slaughtered, the labour rule, the hatches on
the surface stairs, the shelter burrow and the wildlife lockdown. A mixin for Overseer (overseer/harness.py), which
calls these from its plan and keeps their state. In its own file so that each file can be read in full.
"""
import json
import time

from dfbench_client import ActionLimit, GameAPIError, GameOver, HandsOff
from overseer.beasts import BEASTS, LURK_SCALE, LURKERS, in_sight, whole

DAY = 1200


def log(kind, **kw):
    print(json.dumps({"t": round(time.time(), 2), "kind": kind, **kw}, default=str), flush=True)


def d(v):
    return v if isinstance(v, dict) else {}


def lst(v):
    return v if isinstance(v, list) else []


# Open play (MY1, OP1: no hands-off window). Measured in game: these forts have next to no stockpile space, and every
# perishable (raw meat, cleaned fish, plants, prepared meals too) rots 16-19 days after it is made. The food count is
# therefore a moving sum of the last two and a half weeks' production, and an animal slaughtered a month before the
# horizon becomes a drop inside the scored final stretch. Live animals are the one food store that can't rot.
FEAST_DAYS = 14         # animals are slaughtered from this many days before the horizon: none of that meat can rot in time
FEAST_BATCH = 3         # animals marked per pass during the feast
FEAST_KEEP = 3          # the largest animals a hunger cull leaves alone, so a feast is left to have
HUNGER = 0.25           # edible food per citizen (at least 3) below which one small animal is slaughtered: a week or
                        #   two of eating. A higher trigger empties the herd long before the feast on a food-poor fort
HUNGER_FINAL = 2.0      # ... (at least 8) from FINAL_STRETCH days out, where a day at zero costs coverage: an
                        #   earlier cull's meat rots all at once, and a game went from 14 food to none in three days
FINAL_STRETCH = 30      # the scored 28 days plus the time a cull takes to become food
HUNGER_GAP = 8          # days between hunger culls
HUNGER_GAP_FINAL = 5    # ... from FINAL_STRETCH days out
COOK_RAW = 6            # meat, fish, cheese and eggs in stock (food that is neither a plant nor a meal) from which the
                        #   feast cooks: with less, a cook would only take the plants the still needs
DRINK_SAFE = 28         # drink per citizen at which brewing stops for the feast, so the plants harvested in those
                        #   days stay in the food count. A year's drinking is about 20; with no brewing at all over the
                        #   final stretch, 28 still projects past a year at a fifth more than that rate
DRINK_REOPEN = 22       # ... and below which brewing is allowed again

# Open play: dangerous wildlife. Measured on a training embark: three undead harpies were visible two to eight days
# before they struck, every dwarf stood at the wagon on the surface, and the inherited alert never sounded because
# they were not invaders. Four and five citizens died in the two games played there with no defence. Sounding the
# alert without sealing the stairs was worse (fourteen and nine dead in two of three games: the harpies follow the
# dwarves down). With a hatch over the stair, locked while the alert holds, nobody died in three games. So a
# wildlife lockdown starts only when every surface stair this layer knows of has a built hatch, it locks those
# hatches and nothing else, and it ends at once if that seal is lost or a hostile is inside the shelter. The
# inherited shelter burrow is made before the dormitory is dug and covered one tile; it is grown as the fort is dug.
WILD_NEAR = 100         # tiles from the wagon at which any visible hostile starts a lockdown
WILD_CLEAR = 130        # ... and the lockdown holds while one is this close
WILD_DAYS = 20          # the longest a lockdown is held: the harpies stayed within 35 tiles for up to 20 days.
                        #   Workshops, drink and the wagon are above ground, so a lockdown stops production and
                        #   nobody below can drink or eat
WILD_REST = 1           # days above ground for food and drink after a lockdown that ran its full length. In game
                        #   most of a fort that had been shut for three weeks drank and ate within a day of being
                        #   let out, the harpies were back at the wagon within hours, and two dwarves died on the
                        #   third and fourth day above ground: one day, then the fort may be shut again
ADMIT_FAR = 60          # a locked hatch is opened for citizens shut out above it only while every hostile and large
                        #   predator in sight is farther than this from it (the API's measure, a lurker counted as in
                        #   overseer/beasts.py). Nothing in the game opens a locked hatch for a dwarf who was asleep
                        #   on the surface when it was locked, or for a migrant who arrives during a lockdown: in 15
                        #   of 33 recorded lockdowns citizens waited beside the hatch for up to three weeks, and a
                        #   carnotaurus that had kept 40 to 100 tiles off for two weeks killed one of them there
ADMIT_DAYS = 2          # the longest one opening lasts
THAW_BEFORE = 1         # days before a spring from which the civilians are kept in the shelter, ...
THAW_AFTER = 3          # ... to this many days into it. Ice thaws at the start of spring, and a dwarf on it drowns: on
                        #   the fort with frozen water in reach (1016-p) the thaw came between spring days 1 and 2 in
                        #   all eight full-year games, and in one a woodcrafter idle in the frozen river bed drowned
THAW_FROM_DAY = 30      # not in a game's first month (an embark has no shelter yet, and its first days matter most)
YEAR = 336 * DAY        # ticks in a year; a year starts with spring (the API: abs_tick = year * YEAR + tick of the year)
ADMIT_MAX = 3           # openings a lockdown may make
STAIR_CAP = 8           # the API lists at most this many surface stairs: at the cap the list may be incomplete
SHUT_TRIES = 2          # passes a hatch may stay open after it was due to be locked before the lockdown is given up
BLIND_TRIES = 3         # passes in a row without a readable observation, before any has shown every stair hatch
                        #   locked, after which the lockdown is given up: the alert is not held over an open stair
RELEASE_ROUNDS = 3      # tries at each call when the harness lets go of a lockdown on its way out
BURROW_SIDE = 40        # create_burrow refuses a box wider or taller than this, so a dug level that large is
                        #   left out of the shelter: each call for one was refused, every six days, to the end
FOREVER = 10 ** 9       # a failure limit for actions that must be retried for as long as they are needed
BEAST_BUDGET = 60       # days a game may spend shut for large wild predators alone (overseer/beasts.py), counted
                        #   from the first sight of one in a lockdown to the opening of the fort. A visit of the
                        #   one seen in game lasted 7 to 23 days, about once a game-year; a handed-over fort shut
                        #   for 92 of 102 days in a test kept its stocks, its mood and every dwarf
BEAST_DRINK = 2         # drink per citizen below which the fort is not shut, or kept shut, for such an animal alone:
                        #   it needs its Still
BEAST_FOOD = 1          # ... and food per citizen
BEAST_FAILS = 2         # looks that may fail in a row before the layer stops looking for a reason to shut the fort:
                        #   an unanswered query is retried by the client for minutes of the game's wall time
HOLD_FAILS = 4          # ... and before it stops looking during a lockdown, which then runs to its limit
BUTCHER_LEAD = 3        # with nobody hunting: days before the feast at which the Butchers is built
CALM_TRIES = 5          # refusals of the labour plugin after which the inherited workshop rules return
# Open play: the first felling. Measured in 51 recorded full-year games: the tree-felling plugin fells about 250
# trees in the first week, 50 to 119 tiles from the wagon (146 of 152 sightings of a felling dwarf were over 30
# tiles out), and every later bed or barrel means fetching one of those logs. On the training embarks that start
# with alligators at the river (two of eight), the alligators were in sight for the first two to five weeks and
# never after. They are not listed as hostile, and in short test games they killed or mauled dwarves in that time.
PREDATORS = BEASTS | {"COUGAR", "WOLF"}
                        # the large predators of overseer/beasts.py and two smaller ones, by the id the units
                        #   query gives. Alligators and a carnotaurus were seen to attack in test games; the
                        #   others are listed on what the game's creature definitions say of them
FELL_WAIT_DAYS = 35     # the longest the first felling waits for them to leave
FELL_WAIT_DRINK = 4     # drink per citizen below which it waits no longer: no logs means no barrels and no Still
FELL_WAIT_FOOD = 2      # ... and food per citizen
FELL_BLIND = 2          # unanswered looks in a row after which it waits no longer
ANIMAL_RANK = {"WATER_BUFFALO": 100, "YAK": 70, "COW": 60, "HORSE": 50, "CAMEL_1_HUMP": 50, "CAMEL_2_HUMP": 50,
               "MULE": 40, "DONKEY": 30, "REINDEER": 20, "LLAMA": 18, "PIG": 10, "ALPACA": 7, "SHEEP": 5, "GOAT": 5,
               "DOG": 3, "BIRD_TURKEY": 1.5, "BIRD_GOOSE": 1.3, "BIRD_PEAFOWL_BLUE": 1.2, "BIRD_CHICKEN": 0.7,
               "BIRD_DUCK": 0.6, "BIRD_GUINEAFOWL": 0.6, "RABBIT": 0.5, "CAVY": 0.2}
                        # relative adult size (unlisted: 1, a cat). Measured yields are flatter than size: a dog or a
                        #   cow gives 20-40 food, a turkey 10, a cat 7, a rabbit or cavy next to nothing


class OpenPlayRules:
    # ---- when the animals are slaughtered
    def provision(self):
        """The supply sub-score reads the food count's trend over the final stretch (the last quarter of the run, at
        most 28 days): flat or rising is full credit, falling is credited only as far as the stock would last. Food
        rots in about 17 days here, so meat from a month before the horizon is a fall inside that stretch. The
        animals are therefore kept for the last FEAST_DAYS days, when nothing slaughtered can rot before the horizon,
        and slaughtered then, a few per pass, with cooking alongside (it turns tallow into counted meals). Before
        that, one small animal goes only when the fort is nearly out of food."""
        food = self.st.get("food_edible") or 0
        if self.days_left <= FEAST_DAYS:
            self.feast()
        elif self.days_left <= FINAL_STRETCH:
            if food < max(8, HUNGER_FINAL * self.cit):
                self.cull("hunger", 1, smallest=True, retry=HUNGER_GAP_FINAL)
        elif food < max(3, HUNGER * self.cit):
            self.cull("hunger", 1, smallest=True, retry=HUNGER_GAP)

    def feast(self):
        self.cull("feast", FEAST_BATCH, smallest=False, retry=1)
        st = self.st
        raw = (st.get("food_edible") or 0) - (st.get("prepared_meals") or 0) - (st.get("plants_total") or 0)
        if raw >= COOK_RAW and not any(x.get("recipe") == "cook_meal" and not x.get("repeat")
                                       and (x.get("left") or 0) > 0 for x in self.orders):
            self.act("o_cook_feast", "add_order", {"recipe": "cook_meal", "amount": int(min(6, max(2, raw // 10)))},
                     retry=1, limit=99)
        drink = st.get("drink") or 0
        if drink >= DRINK_SAFE * self.cit:
            self.brew_stopped = True
        elif self.brew_stopped and drink < DRINK_REOPEN * self.cit:
            self.brew_stopped = False        # the regular supply step adds its brew order again
        if self.brew_stopped:                # every pass: a refused or cut-short cancellation is tried again
            for oid in sorted(self.brew_own):
                self.act("brew_stop_%s" % oid, "cancel_order", {"order_id": oid}, retry=1, limit=4)

    def cull(self, key, n, smallest, retry):
        """Mark up to n of the fortress's unowned tame animals for slaughter. The feast takes the largest first. A
        hunger cull takes the smallest animal that is still a meal and leaves the FEAST_KEEP largest alone unless
        the food is gone and nothing else is left. Returns how many were marked."""
        if self.now - self.culled.get(key, -10 ** 9) < retry * DAY:
            return 0
        if "Butchers" not in self.shops() and ("Butchers" not in self.listed() or not self.core_missing()):
            self.build("Butchers")
        try:
            q = self.game.query("units", kind="animals")
        except GameAPIError as e:     # a failed read costs this pass, not the rest of the plan
            log("cull_query_error", error=str(e)[:160])
            return 0
        herd = [d(a) for a in lst(d(d(q).get("result")).get("units") or d(d(q).get("result")).get("animals"))]
        herd = [a for a in herd if a.get("tame") and a.get("pet_owner_id") in (None, -1)
                and not a.get("marked_for_slaughter") and a.get("id") is not None]
        size = lambda a: ANIMAL_RANK.get(str(a.get("race")), 1) * (1 if a.get("adult", True) else 0.3)   # noqa: E731
        herd.sort(key=lambda a: (-size(a), str(a.get("id"))))          # largest first
        pick = herd
        if smallest:
            spare = herd[FEAST_KEEP:]
            if not spare and (self.st.get("food_edible") or 0) <= 0:
                spare = herd
            elif not spare and self.final_floor(len(herd)):
                # Adapted from 0xplemonade 8c28e5dc / 3047877 final_floor():
                # take one smallest reserve animal before zero, keep one for the feast.
                spare, n = sorted(herd, key=lambda a: (size(a) < 1, size(a), str(a.get("id"))))[:1], 1
            pick = sorted(spare, key=lambda a: (size(a) < 1, size(a), str(a.get("id"))))
        marked = 0
        for a in pick:                # an animal the API refuses does not block the next one
            if marked >= n:
                break
            r = self.act("cull_%s" % a["id"], "slaughter", {"unit_id": a["id"]}, retry=1, limit=2)
            marked += bool(r and r.get("ok"))
        # A protected or empty herd is not a meal: do not delay a later emergency
        # merely because an earlier check had no eligible animal to mark.
        if marked:
            self.culled[key] = self.now
        log("cull", key=key, day=self.day, days_left=self.days_left, herd=len(herd), marked=marked,
            food=self.st.get("food_edible"), drink=self.st.get("drink"), cit=self.cit)
        return marked

    def final_floor(self, herd_n):
        """Peer 8c28e5dc's final food floor, isolated from grazer, feast and batch changes."""
        return (self.open_play() and FEAST_DAYS < self.days_left <= FINAL_STRETCH and herd_n > 1
                and (self.st.get("food_edible") or 0) <= max(3, (self.cit or 0) // 5))

    # ---- the first trees wait for the predators to leave
    def felling_waits(self):
        """Open play, while the tree-felling plugin is still off: True while a large predator is in sight.

        Enabling the plugin sends two or three dwarves across the whole map for a week, and it cannot be turned
        off again. So before it is enabled this looks at the creatures in sight (the units query; they are never
        in the threats list) and waits while one of PREDATORS is there. It stops waiting for good when none is in
        sight, after FELL_WAIT_DAYS, when drink or food runs short (nothing can be built without logs), or when
        the look itself fails twice in a row. The idea of holding the first felling for visible alligators is
        mpjunior92's (submission a01ba5c4); the bounds and the species list here are this layer's."""
        if self.fell is False:
            return False
        if self.fell is None:
            self.fell = {"since": self.now, "blind": 0}
        st, why = self.st, None
        if self.now - self.fell["since"] >= FELL_WAIT_DAYS * DAY:
            why = "days"
        elif (st.get("drink") or 0) < FELL_WAIT_DRINK * self.cit or (st.get("food_edible") or 0) < FELL_WAIT_FOOD * self.cit:
            why = "supplies"
        else:
            try:
                q = self.game.query("units", kind="others", limit=300)
                units = d(d(q).get("result")).get("units")
            except (GameOver, HandsOff):
                raise
            except Exception as e:      # whatever goes wrong with the look, the rest of the pass must still run
                units = None
                log("felling_look_error", error=repr(e)[:160])
            if not isinstance(units, list):
                self.fell["blind"] += 1
                if self.fell["blind"] < FELL_BLIND:
                    return True
                why = "blind"
            else:
                self.fell["blind"] = 0
                seen = sorted({str(d(u).get("race")) for u in units if not d(u).get("visitor")} & PREDATORS)
                if seen:
                    if self.fell.get("told") != seen:
                        log("felling_waits", day=self.day, seen=seen)
                        self.fell["told"] = seen
                    return True
                why = "clear"
        log("felling_starts", day=self.day, why=why, waited=round((self.now - self.fell["since"]) / DAY, 1))
        self.fell = False
        return False

    # ---- nobody fishes
    def no_fishing(self, plugins):
        """Open play: nobody fishes, and nobody hunts until the feast needs a Butchers.

        Measured on the training forts: every embark has one Fisherdwarf, the only dwarf with the fishing labour,
        who fishes 70 to 100 tiles from the wagon. River predators killed that dwarf in recorded games (a sea
        lamprey made the fisher dodge into the water and drown; alligators come ashore). No tool sets a labour, but
        autolabor, one of the plugins the public enable_automation tool offers, gives the fishing labour to nobody
        while the fort has no Fishery, and the hunting labour to nobody while it has no Butchers (its
        documentation; checked in game: the fishing labour went from one dwarf to none the day after it was
        enabled, and the dwarf took farm and hauling jobs at the wagon). So on a fort that starts with neither
        workshop this layer enables autolabor, builds no Fishery and builds the Butchers only just before the
        feast. A fort that already has one of them is left as it was."""
        ws = self.o.get("workshops")
        if self.calm is None and isinstance(ws, list):
            self.calm = not ({"Fishery", "Butchers"} & {d(w).get("type") for w in ws})
            log("calm", on=self.calm)
        if self.calm and plugins.get("autolabor") != "on":
            # daily until the game accepts it; after that only a slow reminder, in case the state is misreported
            r = self.act("plug_autolabor", "enable_automation", {"name": "autolabor"},
                         retry=10 if self.calm_ok else 1, limit=FOREVER)
            if r is not None and r.get("ok"):
                self.calm_ok = True
            elif r is not None:
                self.calm_fail += 1
                if self.calm_fail >= CALM_TRIES and not self.calm_ok:   # it will not turn on: the fisher fishes,
                    self.calm = False                                    # so the catch needs its Fishery again
                    log("calm", on=False, why="autolabor did not turn on")

    # ---- open play: dangerous wildlife
    def surface_hatches(self):
        """(sealed, hatches): the built hatch over each surface stair this layer has ever seen listed. Sealed only
        when every one of them has its own built hatch on the same tile, the site and door lists are present and
        the stair list is under the API's cap (at the cap it may be incomplete)."""
        doors = self.o.get("doors")
        if not isinstance(self.map.get("sites"), list) or not isinstance(doors, dict) \
                or not isinstance(doors.get("list"), list):
            return False, []
        listed = self.kind("E")
        for s in listed:
            if s.get("id") is not None and None not in (s.get("x"), s.get("y"), s.get("z")):
                self.stairs[s["id"]] = (s["x"], s["y"], s["z"])
        entries = [d(x) for x in lst(doors.get("list"))]
        found = []
        for pos in self.stairs.values():
            h = next((x for x in entries if x.get("kind") == "hatch" and x.get("built") and x.get("id") is not None
                      and (x.get("x"), x.get("y"), x.get("z")) == pos), None)
            if h is None:
                return False, []
            found.append(h)
        return bool(found) and len(listed) < STAIR_CAP, found

    def place_hatches(self):
        """A hatch cover over each stair that opens on the surface. Unlocked it changes nothing."""
        doors = d(self.o.get("doors"))
        taken = {(d(x).get("x"), d(x).get("y"), d(x).get("z")) for x in lst(doors.get("list"))
                 if d(x).get("kind") == "hatch"}
        stairs = self.kind("E")
        gaps = [s for s in stairs if (s.get("x"), s.get("y"), s.get("z")) not in taken]
        if not gaps:
            return
        free = doors.get("hatch_cover_items_free") or 0
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        # a fort ends with two surface stairs (the first and the one this layer digs for the dormitory), and in
        # game a cover took six days from order to stock: the second one's is ordered with the first
        want = max(len(gaps), 2 - (len(stairs) - len(gaps)))
        if free < want and "Carpenters" in have and self.logs() >= 3 and not self.pending("make_hatch_cover"):
            self.act("o_hatch", "add_order", {"recipe": "make_hatch_cover", "amount": min(3, want - free)},
                     retry=4, limit=4)
        for s in gaps[:free]:
            self.act("hatch_%s" % s["id"], "build_door", {"kind": "hatch", "site": s["id"]}, retry=3, limit=3)

    def grow_shelter(self, bur):
        """The shelter burrow follows the dig: each dug level is added again once it has grown, so a lockdown
        sends civilians somewhere they fit. (create_burrow adds a site's box to the same burrow.)"""
        if not any(d(b).get("civ_alert_burrow") for b in lst(bur.get("list"))):
            return
        for a in self.kind("A"):
            tiles = a.get("open_tiles") or 0
            side = max([v for v in (a.get("w"), a.get("h")) if isinstance(v, int)] or [0])
            if tiles >= 6 and tiles >= self.sheltered.get(a["id"], 0) + 10 and side <= BURROW_SIDE:
                r = self.act("shelter_%s" % a["id"], "create_burrow", {"site": a["id"]}, retry=6, limit=FOREVER)
                if r and r.get("ok"):
                    self.sheltered[a["id"]] = tiles

    def look_for_beasts(self, holding=False):
        """(found, sure): the large wild predators in sight and whether the list can be relied on for what it does
        not show (overseer/beasts.py). One query a pass, only while the fort could be shut or is. Whatever goes
        wrong with the call or its answer is a failed look: nothing found, nothing sure. After BEAST_FAILS failed
        looks in a row the layer stops looking for a reason to shut the fort; during a lockdown it goes on for
        HOLD_FAILS, since an animal seen inside the shelter must end it."""
        if self.beast_fail >= (HOLD_FAILS if holding else BEAST_FAILS):
            return [], False
        try:
            q = d(d(self.game.query("units", kind="others", limit=300)).get("result"))
            if not isinstance(q.get("units"), list):
                raise ValueError("no unit list in the answer")
            found, sure = in_sight(q.get("units"), q.get("total"), self.map.get("wagon"))
            told = sorted({b["race"] for b in found})
            if told != self.beast_told:
                log("beasts", day=self.day, seen=told, nearest=min((b["dist"] for b in found), default=None))
                self.beast_told = told
        except (GameOver, HandsOff):
            raise
        except Exception as e:      # the rest of the pass must still run: the lockdown's own checks above all
            self.beast_fail += 1
            log("beast_look_error", error=repr(e)[:160], failed=self.beast_fail)
            return [], False
        self.beast_fail = 0
        return found, sure

    def beast_short(self):
        """Is the fort too short of drink or food to be shut for an animal? True when either is known to be; None
        when neither is and one of them cannot be read."""
        short = unread = False
        for v, need in ((self.st.get("drink"), BEAST_DRINK), (self.st.get("food_edible"), BEAST_FOOD)):
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v:
                short = short or v < need * self.cit
            else:
                unread = True
        return True if short else None if unread else False

    def beast_limit(self, lock):
        """Why a lockdown that only such animals keep shut must end now: the game's days for them are spent, or
        the fort needs its Still and its kitchen more. None while it may go on."""
        if self.beast_spent + self.now - lock["beast"] >= BEAST_BUDGET * DAY:
            return "budget"
        return "supplies" if self.beast_short() else None

    def beast_may_shut(self, beasts):
        """May the fort be shut for these animals alone? Not for one that cannot be placed (it may be inside), not
        beyond the game's budget of such days, and not when drink or food is short or cannot be read."""
        if any(b["x"] is None for b in beasts) or self.beast_spent >= BEAST_BUDGET * DAY:
            return False
        return self.beast_short() is False

    def wildlife(self, alert, open_play=True):
        """One pass of the wildlife lockdown. Returns the civilian alert as this pass leaves it.

        A lockdown is this layer's own state, in two phases. HOLD: the alert is on and each surface stair's hatch is
        locked by its own id. RELEASE: the decision to end is made and is carried out until the game confirms it,
        the alert first and then the hatches; nothing new starts meanwhile. A missing or failed part of the
        observation is never read as "the danger is gone": while one is missing a hold only runs its clock, and it
        is given up if no observation has yet shown the stair shut.

        A large wild predator in sight (overseer/beasts.py; the API calls it no threat) counts as a hostile here,
        at its distance from the wagon, and is looked for with the units query while the fort could be shut or is.
        For such animals alone the fort is shut, and kept shut, only while drink and food allow and within
        BEAST_BUDGET days a game; a lockdown that has had one in sight is not ended as "gone" on a look that
        failed or was incomplete.

        It starts when a visible hostile that is not an invader is within WILD_NEAR of the wagon, every hostile is
        listed and none is inside the shelter, the fort can be sealed, the shelter has room and the fort is owed no
        time above ground. It ends when none is within WILD_CLEAR; after WILD_DAYS (a day above ground follows);
        when invaders arrive (their inherited rule takes the alert, for no longer than WILD_DAYS from the start);
        and, for the rest of the game, when a hostile is inside the shelter, the seal is lost, or a hatch will not
        lock. With more hostiles in sight than the API lists, a standing lockdown is held to its limit: the ones
        that are not listed can be shown neither gone nor inside."""
        th, bur, doors = self.o.get("threats"), self.o.get("burrows"), self.o.get("doors")
        alert_known = isinstance(bur, dict) and isinstance(bur.get("civilian_alert"), bool)
        seen = th.get("visible_hostiles") if isinstance(th, dict) else None
        dist = th.get("nearest_hostile_dist_to_wagon") if isinstance(th, dict) else None
        dist = dist if isinstance(dist, (int, float)) and not isinstance(dist, bool) else None
        counted = isinstance(seen, int) and not isinstance(seen, bool)
        known = (isinstance(th, dict) and isinstance(doors, dict) and alert_known and counted
                 and isinstance(th.get("hostiles"), list) and isinstance(bur.get("list"), list)
                 and isinstance(doors.get("list"), list) and isinstance(self.map.get("sites"), list)
                 and (not seen or dist is not None))      # hostiles in sight and no distance: not readable
        th, bur = d(th), d(bur)
        seen = seen if counted else 0
        hostiles = [d(h) for h in lst(th.get("hostiles"))]
        listed = len(hostiles) >= seen       # the API lists twenty at most
        sealed, hatches = self.surface_hatches()
        listing = d(self.o.get("doors")).get("list")
        if self.lock is not None and isinstance(listing, list):
            shown = {d(x).get("id"): d(x).get("locked") for x in listing}
            for i in d(self.lock.get("admit")).get("opened", ()):
                if shown.get(i) is True:     # opened for citizens, shown locked again: this layer unlocks it at the end,
                    self.own_locks.add(i)    #   and a close still owed for it is done (read from the door list itself:
                    self.lock.setdefault("pending", set()).discard(i)   # a stair without its hatch hides nothing)
        # Large wild predators are in no threat field: they are looked for here and counted with the hostiles.
        # The look is its own evidence. What it finds counts; a look that fails or is incomplete finds less and
        # proves no absence, and it never makes the doors, the alert or the threats above any less readable.
        holding = self.lock is not None and self.lock["phase"] == "hold"
        api_seen, api_dist = seen, dist      # the API's hostiles alone
        beasts, sure = [], True
        if holding or (open_play and sealed and not self.wild_off):
            beasts, sure = self.look_for_beasts(holding)
            try:      # for the model loop's digest only, in tiles from the wagon: it must never stop this pass
                rows = [((b["dist"] // LURK_SCALE if b["race"] in LURKERS else b["dist"]) if b["x"] is not None
                         else None, b["race"]) for b in beasts]
                self.beast_view = {"day": self.day, "sure": sure,
                                   "seen": sorted(rows, key=lambda t: (t[0] is None, t[0] or 0, str(t[1])))}
            except Exception as e:
                self.beast_view = None
                log("beast_view_error", error=repr(e)[:160])
        self.beast_seen = any(b["dist"] <= WILD_CLEAR for b in beasts)
        if beasts:
            if holding and self.lock.get("beast") is None:
                self.lock["beast"] = self.now    # the days from here count against the game's budget
            seen += len(beasts)
            hostiles += beasts               # each with its place, for the test of the shelter below
            near = min(b["dist"] for b in beasts)
            dist = near if dist is None else min(dist, near)
        had_beast = holding and self.lock.get("beast") is not None
        beast_gone = sure or not had_beast   # "none in sight" can be believed
        invaders = any(h.get("invader") for h in hostiles) or any(d(v).get("invader")
                                                                  for v in d(th.get("by_race")).values())
        # shut for animals alone: the threats can be read, every hostile of the API's is listed, and none of them
        # would keep this lockdown standing. (The doors need not be readable for that.)
        animals_only = (had_beast and counted and isinstance(th.get("hostiles"), list) and listed and not invaders
                        and (not api_seen or (api_dist is not None and api_dist > WILD_CLEAR)))
        shelter = next((d(b) for b in lst(bur.get("list")) if d(b).get("civ_alert_burrow")), None)
        box = d((shelter or {}).get("bbox"))
        inside = [h for h in hostiles if h.get("in_shelter") or (
            box and None not in (h.get("x"), h.get("y"), h.get("z"))
            and (box.get("x1") or 0) <= h["x"] <= (box.get("x2") or -1)
            and (box.get("y1") or 0) <= h["y"] <= (box.get("y2") or -1)
            and (box.get("z1") or 0) <= h["z"] <= (box.get("z2") or -1))]
        if self.alert_pending and alert_known and not alert:
            self.alert_pending = False       # the unanswered alert is seen off
        threats_read = (isinstance(self.o.get("threats"), dict) and isinstance(th.get("hostiles"), list)
                        and isinstance(self.o.get("burrows"), dict) and isinstance(bur.get("list"), list))
        stairs_read = (isinstance(self.map.get("sites"), list) and isinstance(doors, dict)
                       and isinstance(doors.get("list"), list))
        if self.lock is not None and ((threats_read and inside) or (stairs_read and not sealed)):
            self.wild_off = True             # the scheme failed once, whatever else ends this lockdown

        if self.lock is None:
            if self.own_locks:           # a hatch still shut from an earlier lockdown: that comes first
                self.unlock_own(known)
                return alert
            if (not open_play or not known or self.wild_off or (alert and not self.thaw_alert) or invaders or not seen
                    or dist > WILD_NEAR or not listed or inside or not sealed or not shelter
                    or (shelter.get("tiles") or 0) < max(20, 2 * self.cit) or self.now < self.rest_until):
                return alert
            if (not api_seen or api_dist is None or api_dist > WILD_NEAR) and not self.beast_may_shut(beasts):
                return alert             # no hostile of the API's would start it, and the animals may not
            self.alert_pending = True    # before the call: if the answer is lost the alert is still to be cleared
            r = self.act("lockdown_on", "civilian_alert", {"on": True}, retry=0, limit=FOREVER)
            self.alert_pending = False   # answered: a lockdown below owns it, or it was refused
            if not (r and r.get("ok")):
                return alert
            self.lock = {"since": self.now, "phase": "hold", "why": None, "alert_off": False, "rest": False,
                         "due": None, "tries": 0, "fresh": True, "blind": 0, "shut": False,
                         "beast": self.now if beasts else None}
            log("lockdown", event="on", day=self.day, dist=dist, hostiles=seen, cit=self.cit, beast=bool(beasts))
            alert = True

        lock = self.lock
        if lock["phase"] == "hold":
            age = self.now - lock["since"]
            fresh, lock["fresh"] = lock.get("fresh"), False
            if known:
                lock["blind"] = 0
                lock["hatch_ids"] = [h["id"] for h in hatches]
                lock["shut"] = bool(hatches) and all(h.get("locked") is True for h in hatches)
                left = lock.get("open") or ()    # opened on the last pass for citizens outside: not a failed lock
                if lock["due"] is not None and lock["due"] < self.now and any(
                        h.get("locked") is False and h["id"] not in left for h in hatches):
                    lock["tries"] += 1           # due on an earlier pass and still open
            else:
                lock["blind"] += 1
            why = None
            if age >= WILD_DAYS * DAY:
                why = "cap"
            elif known:
                if invaders:
                    why = "invaders"
                elif inside:
                    why = "inside"
                elif not sealed:
                    why = "seal"
                elif not alert and not fresh:
                    why = "alert_off"
                elif listed and beast_gone and (not seen or dist > WILD_CLEAR):
                    why = "gone"
                elif animals_only and self.beast_limit(lock):
                    why = self.beast_limit(lock)
                elif lock["tries"] >= SHUT_TRIES:
                    why = "cannot_close"
            elif not lock["shut"] and lock["blind"] >= BLIND_TRIES:
                why = "cannot_close"             # alert on, nothing readable, the stair never seen shut
            elif animals_only:
                why = self.beast_limit(lock)     # these two limits need the threats and the stocks, not the doors
            if why is None:
                indoors = (shelter or {}).get("citizens_inside") or 0
                if known and (lock["due"] is not None or indoors >= self.cit - 1 or age >= DAY):
                    if lock["due"] is None:
                        lock["due"] = self.now
                    keep = self.admit(lock, hatches, hostiles, api_seen, api_dist, listed, sure)
                    for h in hatches:            # each stair's own hatch, by id: no other door is touched
                        if h["id"] not in keep and h.get("locked") is not True:
                            mine = h["id"] in self.own_locks
                            self.own_locks.add(h["id"])      # before the call: a lost answer must still be undone
                            r = self.act("lock_%s" % h["id"], "lock_door", {"locked": True, "door_id": h["id"]},
                                         retry=0, limit=FOREVER)
                            if r is not None and not r.get("ok") and not mine:
                                self.own_locks.discard(h["id"])      # refused outright: it is not locked
                elif lock.get("open"):
                    self.admit_close(lock)       # nothing can be read: what was opened for citizens is shut again
                return True
            reclose = set(lock.get("open") or ()) | set(lock.get("pending") or ()) if why == "invaders" else set()
            lock.update(phase="release", why=why, rest=(why in ("cap", "invaders", "budget", "supplies")),
                        alert_off=(why in ("invaders", "alert_off")), outside=[], open=set(), reclose=reclose)
            if why in ("inside", "seal", "cannot_close"):
                self.wild_off = True
            if why == "invaders":            # the inherited invader rule owns the alert from here, on its own clock
                self.alert_since = lock["since"]
            log("lockdown", event="release", why=why, day=self.day, days=round(age / DAY, 1))

        # release: the alert first, then the hatches, until both are confirmed
        if lock["why"] == "invaders":
            if self.now - lock["since"] >= WILD_DAYS * DAY:
                # the invader alert has outlasted what a lockdown may: this layer takes it back and opens the fort
                lock.update(why="cap", alert_off=False, rest=True)
                log("lockdown", event="release", why="cap", day=self.day, after="invaders")
            elif not alert_known or alert:
                self.reclose(lock)
                return alert             # the invader alert is on: the stair stays shut until it is seen off
        if lock["why"] != "invaders" and lock["alert_off"] and alert_known and alert:
            lock["alert_off"] = False    # it is on again: an earlier "off" is not taken on trust
        if not lock["alert_off"]:
            r = self.act("lockdown_off", "civilian_alert", {"on": False}, retry=0, limit=FOREVER)
            if not (r and r.get("ok")):
                return True              # still confined: the hatches stay shut, the next pass tries again
            lock["alert_off"] = True
            alert = False
        self.unlock_own(known)
        if not self.own_locks:
            if lock["rest"]:
                self.rest_until = self.now + WILD_REST * DAY
            if lock.get("beast") is not None:
                self.beast_spent += self.now - lock["beast"]     # from the first sight of one to the opening
            self.lock = None
            log("lockdown", event="off", day=self.day)
        return alert

    def thaw_window(self, lead=0):
        """True from THAW_BEFORE (plus `lead`) days before a spring to THAW_AFTER days into it, from the game's day
        THAW_FROM_DAY on."""
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (self.now, self.day)) \
                or self.day < THAW_FROM_DAY:
            return False
        t = self.now % YEAR
        return t >= YEAR - (THAW_BEFORE + lead) * DAY or t < THAW_AFTER * DAY

    def thaw(self, alert, bur):
        """Open play: keep the civilians in the shelter while the ice thaws. In thaw_window(), with no lockdown
        standing and no invader alert, this layer sounds the civilian alert (no hatch is locked) and owns it; an
        alert nobody else owns is taken over. When the window ends it clears its alert, retrying until the game
        accepts. A lockdown that starts meanwhile owns the alert from then on, and the day above ground owed after a
        full lockdown comes first. Returns the alert as it leaves it."""
        if self.lock is None and self.alert_since is not None and bur.get("civilian_alert") is False:
            self.alert_since = None      # shown off with no lockdown: the invader rule holds no alert (a clear whose
                                         #   answer was lost leaves its clock set)
        if self.lock is not None or self.alert_since is not None or (self.now < self.rest_until and not self.thaw_alert):
            self.thaw_alert = False      # a lockdown or the inherited invader rule has the alert, or the fort is owed
            return alert                 #   its day above ground after a full lockdown
        if self.thaw_window():
            if alert:
                self.thaw_alert = True
            elif isinstance(bur.get("civilian_alert"), bool) and any(d(b).get("civ_alert_burrow")
                                                                     for b in lst(bur.get("list"))):
                mine, self.thaw_alert = self.thaw_alert, True    # before the call: a lost answer must still be cleared
                r = self.act("thaw_on", "civilian_alert", {"on": True}, retry=0, limit=FOREVER)
                if r is not None and r.get("ok"):
                    alert = True
                    log("thaw", event="on", day=self.day)
                elif r is not None:
                    self.thaw_alert = mine                       # refused outright: it is not on
            return alert
        if self.thaw_alert:
            r = self.act("thaw_off", "civilian_alert", {"on": False}, retry=0, limit=FOREVER)
            if r is not None and r.get("ok"):
                self.thaw_alert, alert = False, False
                log("thaw", event="off", day=self.day)
        return alert

    def admit(self, lock, hatches, hostiles, api_seen, api_dist, listed, sure):
        """The ids of the hatches left open on this pass for citizens shut out above them (an empty set: none).

        Called while a lockdown's hatches are due to be locked. A citizen is outside when it stands on the hatches'
        level or above. The hatch nearest each one is left open, or opened again, while the danger can be placed and
        is far: every hostile and large predator in sight has a position and is more than ADMIT_FAR from that hatch,
        no hostile the API lists is within WILD_CLEAR of the wagon (this is for wild animals; the harpies' rule is
        unchanged), every hostile is listed and the look for animals was complete. One opening lasts until the
        citizens are below, the danger comes nearer or ADMIT_DAYS have passed; a lockdown makes ADMIT_MAX of them
        at most. The alert stays on throughout, so the civilians below stay below."""
        a = lock.setdefault("admit", {"n": 0, "since": None, "opened": set()})
        levels = [h["z"] for h in hatches if whole(h.get("z"))]
        out = [p for p in self.people if levels and whole(p.get("x"), p.get("y"), p.get("z")) and p["z"] >= min(levels)]
        lock["outside"] = [(p.get("id"), p.get("profession")) for p in out]
        doors = []
        far = not api_seen or (api_dist is not None and api_dist > WILD_CLEAR)
        if out and far and listed and sure and all(whole(x.get("x"), x.get("y"), x.get("z")) for x in hostiles):
            clear = [h for h in hatches if whole(h.get("x"), h.get("y"), h.get("z"))
                     and all(self.reach(x, h) > ADMIT_FAR for x in hostiles)]
            for p in out:
                if clear:
                    best = min(clear, key=lambda h: (self.span(p, h), h["id"]))["id"]
                    if best not in doors:
                        doors.append(best)
        running = a["since"] is not None
        if doors and running and self.now - a["since"] >= ADMIT_DAYS * DAY:
            doors = []                   # this opening has had its time
        if doors and not running:
            if a["n"] >= ADMIT_MAX:
                doors = []
            else:
                a["n"] += 1
                a["since"] = self.now
                log("lockdown", event="admit", day=self.day, n=a["n"], doors=doors, outside=lock["outside"])
        if running and not doors:
            a["since"] = None
            log("lockdown", event="admit_end", day=self.day, outside=lock["outside"])
        for i in doors:
            a["opened"].add(i)
            if next(h for h in hatches if h["id"] == i).get("locked") is not False:
                r = self.act("admit_%s" % i, "lock_door", {"locked": False, "door_id": i}, retry=0, limit=FOREVER)
                if r is not None and r.get("ok"):
                    self.own_locks.discard(i)
        lock["open"] = set(doors)
        return lock["open"]

    def reclose(self, lock):
        """While invaders hold the alert after a lockdown, lock again, by id, what an opening for citizens left open
        or a close still owed: the invader rule keeps the stair shut. An id is kept until the door list shows it
        locked."""
        listing = d(self.o.get("doors")).get("list")
        shown = {d(x).get("id"): d(x).get("locked") for x in listing} if isinstance(listing, list) else {}
        for i in sorted(lock.get("reclose") or ()):
            if shown.get(i) is True:
                lock["reclose"].discard(i)
                continue
            mine = i in self.own_locks
            self.own_locks.add(i)                # before the call: a lost answer must still be undone
            r = self.act("lock_%s" % i, "lock_door", {"locked": True, "door_id": i}, retry=0, limit=FOREVER)
            if r is not None and not r.get("ok") and not mine:
                self.own_locks.discard(i)

    def admit_close(self, lock):
        """Lock again, by id, the hatches an opening left open: used when the observation can't be read. Each stays
        owed (lock["pending"]) until the door list shows it locked: a refused or lost close is not forgotten."""
        for i in sorted(lock.get("open") or ()):
            lock.setdefault("pending", set()).add(i)
            mine = i in self.own_locks
            self.own_locks.add(i)                # before the call: a lost answer must still be undone
            r = self.act("lock_%s" % i, "lock_door", {"locked": True, "door_id": i}, retry=0, limit=FOREVER)
            if r is not None and not r.get("ok") and not mine:
                self.own_locks.discard(i)
        if lock.get("admit"):
            lock["admit"]["since"] = None
        lock["open"] = set()
        log("lockdown", event="admit_end", day=self.day, why="blind")

    @staticmethod
    def span(a, b):
        """The API's distance between two placed things: the larger of |dx| and |dy|, plus three a level."""
        return max(abs(a["x"] - b["x"]), abs(a["y"] - b["y"])) + 3 * abs(a["z"] - b["z"])

    def reach(self, x, h):
        """How far a hostile or large predator counts as being from hatch h (a lurker at LURK_SCALE times)."""
        s = self.span(x, h)
        return s * LURK_SCALE if x.get("beast") and x.get("race") in LURKERS else s

    def status(self):
        """What the model loop's digest says of these rules: the large predators the last look found, the standing
        lockdown and who is shut out of it, and whether the first felling waits. Facts only; nothing is decided
        here."""
        lock, view = self.lock, None
        if lock is not None:
            a = lock.get("admit") or {}
            view = {"since_day": (self.day or 0) - (self.now - lock["since"]) // DAY, "phase": lock["phase"],
                    "gathering": lock["phase"] == "hold" and lock.get("due") is None,
                    "hatches": sorted(set(lock.get("hatch_ids") or ()) | set(self.own_locks)),
                    "opening": sorted(lock.get("open") or ()), "openings_left": ADMIT_MAX - (a.get("n") or 0),
                    "far": ADMIT_FAR, "lurk": LURK_SCALE}
        fell = self.fell if isinstance(self.fell, dict) else None
        return {"beasts": self.beast_view, "lockdown": view, "thaw": bool(self.thaw_alert),
                "fell_wait": list(fell.get("told") or ()) if fell is not None else None}

    def unlock_own(self, known=False):
        """Open every hatch this layer sent a lock for, by id. An id is dropped only when the unlock is answered ok
        or a complete door list shows it gone or says it is not locked: a missing list or field proves nothing."""
        doors = {d(x).get("id"): d(x) for x in lst(d(self.o.get("doors")).get("list"))} if known else None
        for i in sorted(self.own_locks):
            if doors is not None and (i not in doors or doors[i].get("locked") is False):
                self.own_locks.discard(i)
                continue
            r = self.act("unlock_%s" % i, "lock_door", {"locked": False, "door_id": i}, retry=0, limit=FOREVER)
            if r and r.get("ok"):
                self.own_locks.discard(i)

    def release(self):
        """On the way out: the server plays on unmanaged after an exit, and nothing in the game ends a lockdown.
        The alert is cleared and each owned hatch unlocked, every call on its own, and a call that is refused or
        fails is tried again, RELEASE_ROUNDS times in all. When the day's actions are spent, a day is advanced to
        get new ones. What is still not confirmed after that stays as it is."""
        clear = self.lock is not None or self.alert_pending or self.thaw_alert
        for n in range(RELEASE_ROUNDS):
            if not clear and not self.own_locks:
                break
            spent = False
            calls = ([("civilian_alert", {"on": False}, None)] if clear else []) + \
                [("lock_door", {"locked": False, "door_id": i}, i) for i in sorted(self.own_locks)]
            for tool, args, door in calls:
                try:
                    ok = bool(d(self.game.act(tool, args)).get("ok"))
                except (GameOver, HandsOff) as e:
                    log("release_error", tool=tool, error=repr(e)[:120])
                    return                   # the game is over or out of reach: nothing more can be done
                except ActionLimit as e:
                    ok, spent = False, True
                    log("release_error", tool=tool, error=repr(e)[:120])
                except Exception as e:
                    ok = False
                    log("release_error", tool=tool, error=repr(e)[:120])
                if ok and door is None:
                    clear, self.alert_pending, self.thaw_alert = False, False, False
                elif ok:
                    self.own_locks.discard(door)
            if spent and (clear or self.own_locks) and n + 1 < RELEASE_ROUNDS:
                try:
                    self.game.act("advance_days", {"days": 1})
                except Exception as e:
                    log("release_error", tool="advance_days", error=repr(e)[:120])
                    return
        if not clear and not self.own_locks:
            self.lock = None

    def owns_lock(self, args):
        """A model lock_door call that would undo a standing lockdown: one of this layer's hatches by id, the hatch
        on any surface stair this layer knows, or every door at once."""
        if self.lock is None and not self.own_locks:
            return False
        i = args.get("door_id") if isinstance(args, dict) else None
        if i is None or i in self.own_locks:
            return True
        spots = set(self.stairs.values())
        return any(d(x).get("id") == i and d(x).get("kind") == "hatch"
                   and (d(x).get("x"), d(x).get("y"), d(x).get("z")) in spots
                   for x in lst(d(self.o.get("doors")).get("list")))

    def seals_stair(self, args):
        """A model lock_door call on an open task that would shut a way to the surface: every door at once, a door
        on a surface stair this layer knows, any door or hatch on the surface level or above it (the stair list
        covers 30 tiles around the wagon and eight stairs, the door list covers the map), or a door that cannot
        be placed (the door list is unreadable or does not have it, or the surface level was never reported).
        This layer puts a hatch on every surface stair and shuts it itself, with the alert on and the civilians
        below. Shut at any other time it cuts the dwarves off from the food and drink on the surface, and nothing
        here would open it again: in one game the model locked all three stair hatches with one call. A lab
        task never records a stair, so there the doors stay the model's."""
        if not (self.open_task() or self.stairs) or not isinstance(args, dict) or args.get("locked") is False:
            return False
        i = args.get("door_id")
        doors = d(self.o.get("doors")).get("list")
        if i is None or not isinstance(doors, list):
            return True
        spots = set(self.stairs.values())
        for x in doors:
            if d(x).get("id") == i and not isinstance(i, bool):
                z = d(x).get("z")
                if (d(x).get("x"), d(x).get("y"), z) in spots:
                    return True
                return self.surface_seen is None or not isinstance(z, int) or z >= self.surface_seen
        return True
