"""DFHack commands for the `automation` reference arm (policies.Automation).

The arm plays the way a human with stock DFHack 53.16-r2 can: it turns on the bundled automation through
`control-panel`, imports standing work orders with `orders import`, and lays out the fort with `quickfort`
blueprints (DFHack's library plus automation/yukon-automation.csv). Everything goes through `dfhack-run` with an
allowlist checked here, and setup refuses to run if DFHack tags any tool it uses as `armok` (DFHack's own label
for "god-like powers"). This module is not part of the LLM tool API: the model arms never see it.
See research/automation-arm.md for the feature inventory and the fairness audit.
"""
import json, os, re, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness as H

DIR = os.path.dirname(os.path.abspath(__file__))
BLUEPRINT = "yukon-automation.csv"            # installed into dfhack-config/blueprints/ (the player blueprint dir)
STANDING = "yukon-standing"                  # automation/standing-orders.json, installed into dfhack-config/orders/

# gui/control-panel "automation" entries the arm enables: Dreamfort's /setup_help list, minus the four
# EXCLUDED below. `control-panel enable X` is what ticking X on the control panel's Enabled tab does.
CONTROL_PANEL = [
    "autobutcher", "autochop", "autoclothing", "autofarm", "autofish", "automilk", "autonestbox", "autoshear",
    "autoslab", "ban-cooking all", "cleanowned", "logistics enable autoretrain", "nestboxes", "orders-sort",
    "prioritize", "seedwatch", "suspendmanager", "tailor",
]
# Recommended by Dreamfort's /setup_help (or present in the control panel) but not used, and why.
EXCLUDED = {
    "buildingplan set boulders false": "no stone is reachable without digging through the aquifer, so planned "
                                       "buildings would never get materials",
    "buildingplan set logs false": "logs are the only building material on this site",
    "autocheese": "not in 53.16-r2's control panel",
    "autolabor": "docs say its algorithms are not updated for v50; enabling it replaces the default work details",
    "combine": "merges item stacks by editing items directly instead of through hauling jobs",
    "work-now": "changes job-search timing, a game-mechanics change no player setting gives",
    "timestream": "changes how fast the simulation runs relative to the calendar",
    "immortal-cravings": "gameplay change; no immortals here anyway",
    "dwarfvet": "gameplay change (adds animal hospitals)",
}
# The first word of every command this module may send. Each is a player-facing DFHack tool; setup checks
# their DFHack tags at run start (fairness_check). `lua` is only ever `lua -f automation/automation.lua`, a
# read-only map query (site finding and dig progress), like the harness's own observe scripts.
TOOLS = ["control-panel", "orders", "quickfort", "help", "lua"] + sorted({c.split()[0] for c in CONTROL_PANEL})
CHECKED_TOOLS = sorted(set(TOOLS) - {"help", "lua", "orders-sort"} | {"buildingplan", "workorder"})   # orders-sort = `orders sort`


class Refused(RuntimeError):
    pass


def run(*args):
    """dfhack-run with the allowlist enforced. Returns stdout+stderr with ANSI codes stripped."""
    if not args or args[0] not in TOOLS:
        raise Refused(f"automation arm may not run {args[:1]}")
    if args[0] == "lua" and list(args[1:3]) != ["-f", os.path.join(DIR, "automation.lua")]:
        raise Refused("lua is only allowed for automation/automation.lua")
    return H.dfhack(*args, with_stderr=True)


def query(*args):
    raw = run("lua", "-f", os.path.join(DIR, "automation.lua"), *map(str, args))
    try:
        return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except ValueError:
        return {"ok": False, "error": raw[-300:]}


def fairness_check():
    """DFHack tags every tool; `armok` marks god-mode tools (instant builds, reveal, item creation, ...).
    Refuse to play if any tool this arm uses carries it."""
    tags = {}
    for t in CHECKED_TOOLS:
        m = re.search(r"Tags:\s*(.*)", run("help", t))
        tags[t] = [x.strip() for x in m.group(1).split("|")] if m else []
    bad = [t for t, tg in tags.items() if "armok" in tg]
    if bad:
        raise Refused(f"armok-tagged tools in the automation arm: {bad}")
    return tags


def install():
    """Copy the arm's blueprint and standing orders into the player's DFHack config dirs (what saving a
    blueprint or an orders file from the game does)."""
    cfg = os.path.join(H.DF, "dfhack-config")
    for sub, src, dst in (("blueprints", BLUEPRINT, BLUEPRINT), ("orders", "standing-orders.json", STANDING + ".json")):
        os.makedirs(os.path.join(cfg, sub), exist_ok=True)
        shutil.copy(os.path.join(DIR, src), os.path.join(cfg, sub, dst))


def quickfort(name, x, y, z, *extra, blueprint=BLUEPRINT, command="run"):
    """Apply one blueprint section with its start cursor at x,y,z. Returns (ok, short result)."""
    out = run("quickfort", command, blueprint, "-n", name, "--cursor", f"{x},{y},{z}", *extra)
    # quickfort reports success even when every tile was unsuitable: require something to have been designated
    ok = ("successfully completed" in out and "rror" not in out
          and (command == "orders" or re.search(r"designated[^:\n]*:\s*[1-9]", out) is not None))
    stats = "; ".join(l.strip() for l in out.splitlines()[1:] if ":" in l and "statistics" not in l)
    return ok, (stats or out[-200:])


def setup():
    """One-time setup at run start. Returns a list of log lines."""
    log = []
    install()
    tags = fairness_check()
    log.append("fairness: no armok tag on " + ",".join(sorted(tags)))
    for c in CONTROL_PANEL:
        out = run("control-panel", "enable", c)
        log.append(f"control-panel enable {c}: {out.splitlines()[-1][:80] if out else ''}")
    log.append(import_orders(STANDING))
    return log


def import_orders(name):
    """`orders import`: yukon-standing at setup; library/basic once the fort has more hands (Dreamfort's checklist
    imports it after the first migrant wave; imported at embark, its ~45 orders keep the lone carpenter busy
    with bins, cages, buckets and splints instead of barrels)."""
    before = run("lua", "-f", os.path.join(DIR, "automation.lua"), "orders")
    out = run("orders", "import", name)
    after = run("lua", "-f", os.path.join(DIR, "automation.lua"), "orders")
    return f"orders import {name}: manager orders {_num(before)} -> {_num(after)} {out[-80:]}"


def _num(raw):
    m = re.search(r'"n":\s*(\d+)', raw)
    return int(m.group(1)) if m else None
