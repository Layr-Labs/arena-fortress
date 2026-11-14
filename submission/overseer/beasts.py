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
# Narrow short-game adaptation of published e6635fdb troop handling.
# Exact observed BIRD_KEA only; no fuzzy species matching or learned attacks.
TROOP_NAMES = frozenset(("BIRD_KEA",))

# ... of which these keep to the water's edge: they count only when close to the wagon
LURKERS = frozenset(("ALLIGATOR", "CROCODILE_SALTWATER", "ANACONDA", "CRETACEOUS_SPINOSAURUS_MIRABILIS",
                     "CRETACEOUS_SPINOSAURUS_AEGYPTIACUS", "GRIMELING"))
LURK_SCALE = 5          # a lurker counts as this many times farther away than it is: 20 tiles for the others' 100.
                        #   Alligators 25 to 65 tiles from the wagon killed nobody once nobody fished and the first
                        #   felling waited for them; six of them 14 tiles from it killed in every build


def whole(*vs):
    """Whole numbers of a size a map can have (a count or a coordinate; nothing else is believed)."""
    return all(isinstance(v, int) and not isinstance(v, bool) and -10 ** 6 < v < 10 ** 6 for v in vs)


def in_sight(units, total, wagon, troops=frozenset()):
    """(found, sure) from the units query's `others`.

    found: the listed animals among the rows that can be read, each {"race", "x", "y", "z", "dist", "beast": True},
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
        troop = race in troops and u.get("tame") is not True
        if not (race in BEASTS or troop) or u.get("hostile") is True or u.get("visitor") is True:
            continue                # a hostile one is in the threats list already
        p = (u.get("x"), u.get("y"), u.get("z"))
        if whole(*p) and whole(*w):
            dist = max(abs(p[0] - w[0]), abs(p[1] - w[1])) + 3 * abs(p[2] - w[2])
            found.append({"race": race, "x": p[0], "y": p[1], "z": p[2], "beast": True,
                          "dist": dist * LURK_SCALE if race in LURKERS else dist})
        else:
            sure = False
            found.append({"race": race, "x": None, "y": None, "z": None, "beast": True, "dist": 0})
    return found, sure
