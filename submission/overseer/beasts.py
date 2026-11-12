"""Open play: large wild predators.

The game API lists a unit as hostile when it is an invader, undead, crazed, agitated or a great beast. A wild
animal that hunts is none of those: no threat field names it, no advance stops for it and the inherited alert
never sounds. This version of the game has such animals in ordinary, calm country. This file holds the list this
layer goes by and reads the units query against it; overseer/openplay.py decides what follows.
"""

# Surface animals the game's own creature definitions mark [LARGE_PREDATOR] with an adult BODY_SIZE over a dwarf's
# 60000 and that are not confined to water, by the id the units query gives. (The game's documentation: a large
# predator attacks what is smaller than itself.) Smaller ones are left out: dingos were in sight for weeks on two
# training forts and attacked nobody.
BEASTS = frozenset((
    "CRETACEOUS_CARNOTAURUS", "ALLIGATOR", "CROCODILE_SALTWATER", "BEAR_GRIZZLY", "BEAR_BLACK", "BEAR_POLAR", "TIGER",
    "LION", "JAGUAR", "ANACONDA", "CRETACEOUS_TYRANNOSAURUS", "CRETACEOUS_SPINOSAURUS_MIRABILIS",
    "CRETACEOUS_SPINOSAURUS_AEGYPTIACUS", "CRETACEOUS_UTAHRAPTOR", "CRETACEOUS_DEINONYCHUS",
    "CRETACEOUS_QUETZALCOATLUS", "JURASSIC_TORVOSAURUS", "JURASSIC_ALLOSAURUS", "JURASSIC_AFROVENATOR",
    "JURASSIC_CERATOSAURUS", "JURASSIC_DILOPHOSAURUS", "CENOZOIC_ANDREWSARCHUS", "CENOZOIC_MEGALANIA",
    "CENOZOIC_SMILODON", "CENOZOIC_KELENKEN", "PERMIAN_ANTEOSAURUS", "PERMIAN_DIMETRODON", "OGRE", "YETI",
    "SASQUATCH", "BLIZZARD_MAN", "BEAK_DOG", "NIGHTWING", "GRIMELING"))
# ... of which these keep to the water's edge: they count only when close to the wagon
LURKERS = frozenset(("ALLIGATOR", "CROCODILE_SALTWATER", "ANACONDA", "CRETACEOUS_SPINOSAURUS_MIRABILIS",
                     "CRETACEOUS_SPINOSAURUS_AEGYPTIACUS", "GRIMELING"))
LURK_SCALE = 5          # a lurker counts as this many times farther away than it is: 20 tiles for the others' 100.
                        #   Alligators 25 to 65 tiles from the wagon killed nobody once nobody fished and the first
                        #   felling waited for them; six of them 14 tiles from it killed in every build


# Small wild animals that come in troops or flocks. Not large predators and never listed as hostile, yet in our
# recorded open-play games they made most of the attacks on citizens (rhesus macaques, keas, gray langurs, with
# giant keas and buzzards) and cross 80 tiles in under a day. Named as the game's reports name them; a race id from
# the units query matches a name when it has the same words, ignoring "BIRD" (BIRD_KEA, GIANT_KEA, GRAY_LANGUR,
# BIRD_BUZZARD; MACAQUE_RHESUS and RHESUS_MACAQUE alike). Species seen attacking a citizen in a game's own combat
# reports are added to these for that game (fought()).
TROOP_NAMES = ("rhesus macaque", "kea", "giant kea", "gray langur", "buzzard")
FOUGHT_MAX = 20         # species a game may add to the troops from its combat reports


def words(name):
    """A race id or a creature's name as a set of lower-case words, without BIRD: the key troops are matched by."""
    if not isinstance(name, str):
        return frozenset()
    return frozenset(w for w in name.lower().replace("_", " ").replace("-", " ").split() if w != "bird")


TROOPS = frozenset(words(n) for n in TROOP_NAMES)


def fought(events, citizens, attack):
    """The species (as words()) that attacked a citizen in these report lines. `attack` is the digest's own pattern
    for "The <attacker> <bites|strikes|...> ..." (plain/digest.py ATTACK); `citizens` the lower-case words a citizen
    is named by in a report (professions, first names, "dwarf"). An attacker that is itself a citizen is left out,
    and so is one whose report names no citizen as the one attacked."""
    found = set()
    for e in events if isinstance(events, (list, tuple)) else ():
        m = attack.match(e) if isinstance(e, str) else None
        if not m:
            continue
        who = m.group(1).lower()
        if who in citizens or "dwarf" in who.split() or "(" in who:
            continue
        rest = e[m.end():].lower()
        if any(f"the {w} " in rest or f"the {w}'s" in rest or rest.rstrip("!. ").endswith(f"the {w}")
               for w in citizens):
            key = words(who)
            if key:
                found.add(key)
    return found


def whole(*vs):
    """Whole numbers of a size a map can have (a count or a coordinate; nothing else is believed)."""
    return all(isinstance(v, int) and not isinstance(v, bool) and -10 ** 6 < v < 10 ** 6 for v in vs)


def in_sight(units, total, wagon, troops=TROOPS):
    """(found, sure) from the units query's `others`.

    found: the listed animals among the rows that can be read, each {"race", "x", "y", "z", "dist", "beast": True},
    with "troop": True for a wild animal whose words() are in `troops` (one the fort tamed is left out),
    with dist in the API's own measure (the larger of |dx| and |dy| from the wagon, plus three for every level
    between them), times LURK_SCALE for a lurker. One that cannot be placed (no wagon in the observation, or a
    position that is not three whole numbers) has x, y and z None and dist 0: in sight, somewhere.
    sure: nothing was left out, so what the list does not show is not there. Only when the answer's own count
    says the list is whole (in 4,008 answers of 25 recorded games it always did); False when there is no list,
    no such count, a row that cannot be read, or a listed animal that cannot be placed."""
    if not isinstance(units, list):
        return [], False
    sure = whole(total) and total == len(units)
    wagon = wagon if isinstance(wagon, dict) else {}
    w = (wagon.get("x"), wagon.get("y"), wagon.get("z"))
    found = []
    for u in units:
        race = u.get("race") if isinstance(u, dict) else None
        if not isinstance(race, str):
            sure = False            # it may be one of them
            continue
        troop = race not in BEASTS and words(race) in troops and u.get("tame") is not True
        if not (race in BEASTS or troop) or u.get("hostile") is True or u.get("visitor") is True:
            continue                # a hostile one is in the threats list already
        p = (u.get("x"), u.get("y"), u.get("z"))
        if whole(*p) and whole(*w):
            dist = max(abs(p[0] - w[0]), abs(p[1] - w[1])) + 3 * abs(p[2] - w[2])
            found.append({"race": race, "x": p[0], "y": p[1], "z": p[2], "beast": True,
                          "dist": dist * LURK_SCALE if race in LURKERS else dist, "troop": troop})
        else:
            sure = False
            found.append({"race": race, "x": None, "y": None, "z": None, "beast": True, "dist": 0, "troop": troop})
    return found, sure
