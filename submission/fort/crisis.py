"""Crisis rules: strange moods, hostiles, food emergencies. These run before the economy in each plan.

Mood workshops follow DF's own claim rules (DF wiki "Strange mood": the workshop a mood claims depends on the moody
dwarf's highest moodable skill).
"""
from .memory import DAY

MOOD_WORKSHOP = {
    "WOODCRAFT": "Craftsdwarfs", "STONECRAFT": "Craftsdwarfs", "BONECARVE": "Craftsdwarfs",
    "CARPENTRY": "Carpenters", "MASONRY": "Masons", "BOWYER": "Bowyers", "GLASSMAKER": "GlassFurnace",
    "CUTGEM": "Jewelers", "ENCRUSTGEM": "Jewelers", "GEM_CUTTING": "Jewelers", "GEM_SETTING": "Jewelers",
    "FORGE_WEAPON": "MetalsmithsForge", "FORGE_ARMOR": "MetalsmithsForge", "FORGE_FURNITURE": "MetalsmithsForge",
    "METALCRAFT": "MetalsmithsForge", "LEATHERWORK": "Leatherworks", "WEAVING": "Loom", "CLOTHESMAKING": "Clothiers",
    "MECHANICS": "Mechanics", "TANNER": "Tanners",
}
INSANE = ("Melancholy", "Raving", "Berserk", "Traumatized")


def urgent(fort):
    return bool(fort.hostiles() or fort.moods or fort.drink == 0)


def steps(fort, mem):
    now = fort.tick
    out = []
    out += mood_steps(fort, mem, now)
    out += defence_steps(fort, mem, now)
    out += food_steps(fort, mem, now)
    return out


# --- moods -------------------------------------------------------------------------------------------------------
def mood_steps(fort, mem, now):
    out = []
    for m in fort.moods:
        if m.get("mood") in INSANE:
            continue
        typ = MOOD_WORKSHOP.get(str(m.get("skill") or "").upper())
        if not typ:
            continue
        if m.get("claimed_building_id") is not None:
            continue
        # a free workshop of the type (no jobs) lets the dwarf claim it; else build one
        idle = [w for w in fort.ws(typ) if not w.get("jobs")]   # built or still being built
        if idle or len(fort.ws(typ)) >= 2:
            continue
        sites = fort.near_wagon(fort.sites_of("W"))
        key = f"mood:ws:{typ}:{len(fort.ws(typ))}"
        if sites and mem.may(key, now, every_days=1, max_tries=6):
            out.append((key, "build_workshop", {"type": typ, "site": sites[0]["id"]}))
    return out


# --- defence -----------------------------------------------------------------------------------------------------
def invaders(fort):
    return [h for h in fort.threats.get("hostiles") or [] if isinstance(h, dict)]


def defence_steps(fort, mem, now):
    out = []
    hs = invaders(fort)
    alert = fort.burrows.get("civilian_alert")
    burrow = next((b for b in fort.burrows.get("list") or [] if b.get("civ_alert_burrow")), None)
    squads = fort.military.get("squads") or []
    squad = squads[0] if squads else None
    if not hs:
        if alert and mem.may("alert:off", now, every_days=0.5):
            out.append(("alert:off", "civilian_alert", {"on": False}))
        if squad and squad.get("orders") and mem.may("squad:standdown", now, every_days=1):
            out.append(("squad:standdown", "squad_order", {"order": "stand_down"}))
        return out
    mem.vals["last_hostile_tick"] = now
    near = fort.threats.get("nearest_hostile_dist_to_wagon")
    near = 10 ** 6 if near is None else near
    # shelter: a burrow over the living level, then the civilian alert while the hostiles are close
    if burrow is None:
        live = [s for s in fort.sites_of("A", free_only=False) if s.get("z") is not None
                and fort.surface_z is not None and s["z"] < fort.surface_z]
        live.sort(key=lambda s: -(s.get("open_tiles") or 0))
        if live and mem.may("burrow", now, every_days=1, max_tries=3):
            out.append(("burrow", "create_burrow", {"site": live[0]["id"], "levels": 3}))
    elif not alert and near <= 60 and mem.may("alert:on", now, every_days=0.5):
        out.append(("alert:on", "civilian_alert", {"on": True}))
    # a squad, armed with what exists, attacking parties it can match
    if squad is None and fort.citizens >= 8 and mem.may("squad", now, every_days=2, max_tries=3):
        out.append(("squad", "create_squad", {"size": max(2, min(8, fort.citizens // 3))}))
    elif squad:
        if squad.get("uniform") in (None, "none") and mem.may("equip", now, every_days=2, max_tries=3):
            out.append(("equip", "equip_squad", {"uniform": "weapon_only"}))
        armed = squad.get("armed") or 0
        attacking = any(o.get("order") == "attack" and o.get("targets_alive") for o in squad.get("orders") or [])
        if not attacking and armed >= max(1, len(hs)) and mem.may("attack", now, every_days=0.5):
            out.append(("attack", "squad_order", {"order": "attack"}))
    return out


# --- food --------------------------------------------------------------------------------------------------------
def food_steps(fort, mem, now):
    out = []
    c = max(1, fort.citizens)
    if fort.food >= 2 * c:
        return out
    if not fort.has_ws("Butchers"):
        sites = fort.near_wagon(fort.sites_of("W"))
        if sites and mem.may("ws:Butchers", now, every_days=3, max_tries=4):
            out.append(("ws:Butchers", "build_workshop", {"type": "Butchers", "site": sites[0]["id"]}))
        return out
    if not mem.may("slaughter", now, every_days=2):
        return out
    try:
        r = fort.game.query("units", kind="animals", limit=300).get("result") or {}
    except Exception:  # noqa: BLE001 - a failed query just skips the step
        return out
    animals = [a for a in r.get("units") or [] if a.get("tame") and a.get("adult") and a.get("pet_owner_id") in (None, -1)
               and not a.get("marked_for_slaughter")]
    # keep one female of each race for breeding where possible
    keep, pick = set(), None
    for a in animals:
        if a.get("female") and a.get("race") not in keep:
            keep.add(a.get("race"))
            continue
        pick = a
        break
    if pick is not None:
        out.append(("slaughter", "slaughter", {"unit_id": pick["id"]}))
    return out
