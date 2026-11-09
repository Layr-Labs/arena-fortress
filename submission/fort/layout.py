"""Layout rules: stairs, a farm level and a living level, farm plots, furniture, zones and the manager's office.

The fort's levels below the surface:
  farm level   (usually surface-1, soil): one big room of 3x3 farm plots
  living level (usually surface-2): one big room holding the dormitory, dining hall and meeting area together
  overflow     (surface-3 and down): a second living room when the first is full
Sites come from the server (W/F/R/A/S ids); rooms are dug with dig_room on an R site with a larger w,h, and the
level's A site then covers the whole dug area for place_furniture and make_zone.
"""
from .memory import DAY
from .state import ceil_div

FARM_ROOM = (9, 9)
LIVE_ROOM = (11, 9)
BIG_LIVE_ROOM = (15, 11)
STAIR_DEPTH = 4          # levels below the surface the main stair reaches
PAIRS_PER_CYCLE = 8


def farm_target(fort):
    return max(4, min(24, ceil_div(fort.citizens, 2) + 2))


def farm_z(fort):
    if fort.farms:
        zs = [f.get("z") for f in fort.farms if f.get("z") is not None]
        if zs:
            return max(set(zs), key=zs.count)
    return fort.surface_z - 1 if fort.surface_z is not None else None


def live_zs(fort, mem):
    """Living levels, preferred first: where the dormitory is, else the levels below the farm level."""
    zs = []
    if mem.vals.get("live_z") is not None:
        zs.append(mem.vals["live_z"])
    for z in fort.zones_of("Dormitory"):
        if z.get("z") is not None and z["z"] not in zs:
            zs.append(z["z"])
    fz = farm_z(fort)
    if fz is not None:
        for dz in (1, 2, 3):
            if fz - dz not in zs:
                zs.append(fz - dz)
    return zs


def a_site(fort, z):
    a = [s for s in fort.sites_of("A", free_only=False) if s.get("z") == z]
    return max(a, key=lambda s: s.get("open_tiles") or 0) if a else None


def taken(mem):
    return mem.vals.setdefault("room_rs", set())


def r_free(fort, z, soil=None, mem=None):
    out = [s for s in fort.sites_of("R") if s.get("z") == z and not s.get("designated")
           and (mem is None or s["id"] not in taken(mem))]
    if soil is not None:
        out = [s for s in out if bool(s.get("soil")) == soil] or out
    return out


def deepest_level(fort):
    zs = [s.get("z") for s in fort.sites if s.get("kind") in ("A", "R") and s.get("z") is not None]
    return min(zs) if zs else None


def busy(fort):
    if fort.dig_pending:
        return True
    if any(not w.get("built") for w in fort.workshops):
        return True
    return any(not f.get("built") for f in fort.furniture)


def dig_pending_at(fort, z):
    by = fort.o.get("dig_pending_by_z") or {}
    return by.get(str(z), 0) or by.get(z, 0) or 0


# ---------------------------------------------------------------------------------------------------------------
def steps(fort, mem):
    if fort.surface_z is None:
        return []
    now = fort.tick
    out = []
    out += stair_steps(fort, mem, now)
    out += farm_steps(fort, mem, now)
    out += living_steps(fort, mem, now)
    out += office_steps(fort, mem, now)
    return out


def stair_steps(fort, mem, now):
    """A staircase down to surface-STAIR_DEPTH when the levels the plan needs have no R/A sites yet."""
    deep = deepest_level(fort)
    want = fort.surface_z - STAIR_DEPTH + 1      # we need at least down to surface-3
    if deep is not None and deep <= want:
        return []
    if not mem.may("stair", now, every_days=3, max_tries=4):
        return []
    ss = fort.near_wagon(fort.sites_of("S"))
    if not ss:
        return []
    return [("stair", "dig_stairs", {"site": ss[0]["id"], "z_bottom": fort.surface_z - STAIR_DEPTH})]


def farm_steps(fort, mem, now):
    out = []
    target = farm_target(fort)
    have = len(fort.farms)
    if have >= target:
        return out
    fz = farm_z(fort)
    lz = {z.get("z") for z in fort.zones_of("Dormitory")} | {mem.vals.get("live_z")}
    fs = [s for s in fort.sites_of("F") if s.get("z") not in lz]
    fs.sort(key=lambda s: (s.get("z") != fz, s.get("z") or 0))
    for s in fs[:target - have]:
        key = "farm:" + s["id"]
        if mem.may(key, now, every_days=2, max_tries=3):
            out.append((key, "build_farm", {"site": s["id"]}))
    if not fs and dig_pending_at(fort, fz) == 0:
        # no free farm site: dig (another) farm room on the farm level, soil first
        rs = r_free(fort, fz, soil=True, mem=mem)
        n = mem.vals.get("farm_rooms", 0)
        if rs and n < 3 and mem.may("farmroom", now, every_days=4, max_tries=5):
            w, h = FARM_ROOM
            out.append(("farmroom", "dig_room", {"site": rs[0]["id"], "w": w, "h": h}))
            mem.vals["farm_rooms_pending"] = True
    return out


def living_need(fort):
    c = max(1, fort.citizens)
    return (c + 4) + 2 * (c + 2) + 4


def living_steps(fort, mem, now):
    out = []
    zs = live_zs(fort, mem)
    if not zs:
        return out
    # capacity: open tiles on the living levels that already have a dug area
    cap = 0
    level = None
    for z in zs:
        a = a_site(fort, z)
        if a and (a.get("open_tiles") or 0) >= 12:
            cap += a.get("open_tiles") or 0
            if level is None:
                level = z
    need_more = cap < living_need(fort) - placed_on(fort, zs)
    if need_more and not any(dig_pending_at(fort, z) for z in zs):
        for z in zs:
            rs = r_free(fort, z, mem=mem)
            if rs and mem.may(f"liveroom:{z}", now, every_days=4, max_tries=3):
                w, h = BIG_LIVE_ROOM if fort.citizens >= 25 else LIVE_ROOM
                out.append((f"liveroom:{z}", "dig_room", {"site": rs[0]["id"], "w": w, "h": h}))
                break
    if level is None:
        return out
    a = a_site(fort, level)
    sid = a["id"]
    # furniture onto the living level
    if fort.free("bed") > 0 and mem.may("place:bed", now, every_days=1, backoff=False):
        out.append(("place:bed", "place_furniture", {"kind": "bed", "site": sid, "count": min(30, fort.free("bed"))}))
    pairs = min(fort.free("table"), fort.free("chair") - office_chair_reserve(fort), PAIRS_PER_CYCLE,
                ((a.get("open_tiles") or 0) - 6) // 3)
    if dig_pending_at(fort, level):
        pairs = 0          # the room is still being dug: its designated tiles take no furniture yet
    if pairs > 0 and not mem.may("place:pairs", now, every_days=1, backoff=False):
        pairs = 0
    elif pairs > 0:
        mem.record("place:pairs", now, True)
    for i in range(max(0, pairs)):
        out.append((f"place:table:{i}", "place_furniture", {"kind": "table", "site": sid, "count": 1}))
        out.append((f"place:chair:{i}", "place_furniture", {"kind": "chair", "site": sid, "count": 1}))
    # zones over the living level (again whenever furniture sits outside every zone)
    if dig_pending_at(fort, level) == 0:
        area = (a.get("w") or 0) * (a.get("h") or 0)
        for kind, typ in (("dormitory", "Dormitory"), ("dining_hall", "DiningHall"), ("meeting_area", "MeetingHall")):
            have = [z for z in fort.zones_of(typ) if z.get("z") == level]
            biggest = max(((z.get("w") or 0) * (z.get("h") or 0) for z in have), default=0)
            if biggest < area and mem.may(f"zone:{kind}:{level}", now, every_days=2, max_tries=8):
                out.append((f"zone:{kind}:{level}", "make_zone", {"kind": kind, "site": sid}))
    return out


def placed_on(fort, zs):
    return sum(1 for f in fort.furniture if f.get("z") in zs)


def office_chair_reserve(fort):
    return 1 if needs_office(fort) else 0


def needs_office(fort):
    off = fort.office()
    return bool(fort.manager_id()) and not (off and off.get("chair")) and (
        fort.citizens >= 10 or fort.adm.get("manager_required_office"))


def office_steps(fort, mem, now):
    """An office for the manager: a 3x3 room (an R site of its own), a chair, an office zone assigned to him."""
    if not needs_office(fort):
        return []
    out = []
    mgr = fort.manager_id()
    rid = mem.vals.get("office_room")
    room = fort.site(rid) if rid else None
    if room is not None and any("Office" not in str(u) for u in room.get("used_by") or []):
        mem.vals.pop("office_room", None)
        room = None
    if room is None:
        cands = []
        for z in sorted({z for z in [farm_z(fort)] + live_zs(fort, mem) if z is not None}):
            cands += r_free(fort, z, mem=mem)
        if cands and mem.may("office:dig", now, every_days=3, max_tries=4):
            out.append(("office:dig", "dig_room", {"site": cands[0]["id"], "w": 3, "h": 3}))
        return out
    if not room.get("dug"):
        return out
    zone = next((z for z in fort.zones_of("Office") if z.get("x") == room.get("x") and z.get("y") == room.get("y")
                 and z.get("z") == room.get("z")), None)
    chair_in = zone and ((zone.get("furniture") or {}).get("chair") or (zone.get("furniture_planned") or {}).get("chair"))
    if not chair_in and fort.free("chair") > 0 and mem.may("office:chair", now, every_days=2, max_tries=6):
        out.append(("office:chair", "place_furniture", {"kind": "chair", "site": rid, "count": 1}))
    if zone is None:
        if mem.may("office:zone", now, every_days=2, max_tries=6):
            out.append(("office:zone", "make_zone", {"kind": "office", "site": rid}))
    elif zone.get("owner") != mgr and mem.may("office:assign", now, every_days=1, max_tries=8):
        out.append(("office:assign", "assign_zone", {"zone_id": zone["id"], "dwarf_id": mgr}))
    return out


def after(key, tool, args, resp, mem):
    """Bookkeeping once a layout step has run: which R sites became rooms, and which one is the office."""
    if not resp.get("ok") or tool != "dig_room":
        return
    taken(mem).add(args.get("site"))
    if key == "office:dig":
        mem.vals["office_room"] = args.get("site")
    elif key.startswith("liveroom:") and mem.vals.get("live_z") is None:
        mem.vals["live_z"] = int(key.split(":")[1])
    elif key == "farmroom":
        mem.vals["farm_rooms"] = mem.vals.get("farm_rooms", 0) + 1
