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
    "SASQUATCH", "BLIZZARD_MAN", "BEAK_DOG", "NIGHTWING", "GRIMELING",
    # ... and the two this list's own notes named as missing: [LARGE_PREDATOR] at 60000 and 40000, temperate
    # forest and shrubland, the wolf in packs of three to seven
    "COUGAR", "WOLF",
    # ... and a temperate river animal with no [LARGE_PREDATOR] tag that is bigger than a dwarf (adult 80000): in a
    # local full-year game (leader's harness, 2026-11-15) one tore a woodworker's upper spine on day 8 of the first
    # felling and he bled to death. Its id has spaces in it, as the units query gives it
    "ALLIGATOR SNAPPING TURTLE",
    # ... and the troop thieves (THIEVES below)
    "GRAY_LANGUR", "MACAQUE_RHESUS", "MANDRILL", "CAPUCHIN"))
# ... of which these keep to the water's edge: they count only when close to the wagon
LURKERS = frozenset(("ALLIGATOR", "CROCODILE_SALTWATER", "ANACONDA", "CRETACEOUS_SPINOSAURUS_MIRABILIS",
                     "CRETACEOUS_SPINOSAURUS_AEGYPTIACUS", "GRIMELING", "ALLIGATOR SNAPPING TURTLE"))
LURK_SCALE = 5          # a lurker counts as this many times farther away than it is: 20 tiles for the others' 100.
                        #   Alligators 25 to 65 tiles from the wagon killed nobody once nobody fished and the first
                        #   felling waited for them; six of them 14 tiles from it killed in every build
# Troop thieves: primates the creature definitions mark [CURIOUSBEAST_EATER][CURIOUSBEAST_ITEM] that roam in
# clusters of five to ten. They come into the fort for food and items and are not hostile to the API. In a local MY1
# game (leader's harness, 2026-11-15) five gray langurs came to 29 tiles of the wagon, one tore a leatherworker's
# upper spine the next day and he died; in another, four came to 13 tiles and mauled a miner. A single one that
# stayed 15 to 49 tiles out for twenty days attacked nobody. So they count only as a troop, and only when close.
THIEVES = frozenset(("GRAY_LANGUR", "MACAQUE_RHESUS", "MANDRILL", "CAPUCHIN"))
THIEF_SCALE = 2         # a thief counts as this many times farther away than it is: 50 tiles for the others' 100
TROOP_MIN = 2           # thieves of one species in sight below this many count for nothing


def scale(race):
    """How many times farther away than it is an animal of this race counts."""
    return LURK_SCALE if race in LURKERS else THIEF_SCALE if race in THIEVES else 1


def whole(*vs):
    """Whole numbers of a size a map can have (a count or a coordinate; nothing else is believed)."""
    return all(isinstance(v, int) and not isinstance(v, bool) and -10 ** 6 < v < 10 ** 6 for v in vs)


def in_sight(units, total, wagon):
    """(found, sure) from the units query's `others`.

    found: the listed animals among the rows that can be read, each {"race", "x", "y", "z", "dist", "beast": True},
    with dist in the API's own measure (the larger of |dx| and |dy| from the wagon, plus three for every level
    between them), times LURK_SCALE for a lurker and THIEF_SCALE for a thief (only a troop of TROOP_MIN or more of
    its species is listed). One that cannot be placed (no wagon in the observation, or a
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
    troops = {}
    for u in units:
        race = u.get("race") if isinstance(u, dict) else None
        if race in THIEVES and u.get("hostile") is not True and u.get("visitor") is not True:
            troops[race] = troops.get(race, 0) + 1
    for u in units:
        race = u.get("race") if isinstance(u, dict) else None
        if not isinstance(race, str):
            sure = False            # it may be one of them
            continue
        if race not in BEASTS or u.get("hostile") is True or u.get("visitor") is True:
            continue                # a hostile one is in the threats list already
        if race in THIEVES and troops.get(race, 0) < TROOP_MIN:
            continue                # a lone thief: no troop
        p = (u.get("x"), u.get("y"), u.get("z"))
        if whole(*p) and whole(*w):
            dist = max(abs(p[0] - w[0]), abs(p[1] - w[1])) + 3 * abs(p[2] - w[2])
            found.append({"race": race, "x": p[0], "y": p[1], "z": p[2], "beast": True,
                          "dist": dist * scale(race)})
        else:
            sure = False
            found.append({"race": race, "x": None, "y": None, "z": None, "beast": True, "dist": 0})
    return found, sure
