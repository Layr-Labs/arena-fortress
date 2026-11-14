"""Open play: large wild predators and fast aggressive troop species.

The game API lists a unit as hostile when it is an invader, undead, crazed, agitated or a great beast. A wild
animal that hunts or raids in fast troops is none of those: no threat field names it, no advance stops for it and
the inherited alert never sounds. This file holds the static predator/troop sets plus reactive species matching for
wild species observed attacking citizens; overseer/openplay.py decides what follows.
"""
import re

# Surface animals the game's own creature definitions mark [LARGE_PREDATOR] with an adult BODY_SIZE over a dwarf's
# 60000 and that are not confined to water, by the id the units query gives.
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
LURK_SCALE = 5

# Fast troop species that raid surface workers without setting `hostile=True` (f4bb39b empirical attack records,
# excluding peaceful scavengers like buzzards so the 60-day lockdown budget is preserved for real attackers).
TROOPS = frozenset((
    frozenset(("rhesus", "macaque")),
    frozenset(("gray", "langur")),
    frozenset(("giant", "kea")),
    frozenset(("mandrill",)),
    frozenset(("baboon",)),
    frozenset(("chimpanzee",)),
))
IGNORE_WORDS = frozenset(("bird", "the", "a", "an", "stray", "wild"))


def race_words(text):
    """Normalized word set for matching creature race IDs (`MACAQUE_RHESUS`) and combat log names (`rhesus macaque`)."""
    if not isinstance(text, str):
        return frozenset()
    parts = [w for w in re.split(r"[^a-z0-9]+", text.lower()) if w and w not in IGNORE_WORDS]
    return frozenset(parts)


def is_troop(race, extra=()):
    words = race_words(race)
    return bool(words) and (words in TROOPS or words in extra)


def whole(*vs):
    """Whole numbers of a size a map can have (a count or a coordinate; nothing else is believed)."""
    return all(isinstance(v, int) and not isinstance(v, bool) and -10 ** 6 < v < 10 ** 6 for v in vs)


def in_sight(units, total, wagon, extra=()):
    """(found, sure) from the units query's `others`."""
    if not isinstance(units, list):
        return [], False
    sure = whole(total) and total == len(units)
    wagon = wagon if isinstance(wagon, dict) else {}
    w = (wagon.get("x"), wagon.get("y"), wagon.get("z"))
    found = []
    for u in units:
        race = u.get("race") if isinstance(u, dict) else None
        if not isinstance(race, str):
            sure = False
            continue
        if u.get("hostile") is True or u.get("visitor") is True or u.get("tame") is True:
            continue
        beast = race in BEASTS
        troop = not beast and is_troop(race, extra)
        if not beast and not troop:
            continue
        p = (u.get("x"), u.get("y"), u.get("z"))
        row = {"race": race, "beast": True}
        if troop:
            row["troop"] = True
        if whole(*p) and whole(*w):
            dist = max(abs(p[0] - w[0]), abs(p[1] - w[1])) + 3 * abs(p[2] - w[2])
            row.update(x=p[0], y=p[1], z=p[2], dist=dist * LURK_SCALE if race in LURKERS else dist)
        else:
            sure = False
            row.update(x=None, y=None, z=None, dist=0)
        found.append(row)
    return found, sure
