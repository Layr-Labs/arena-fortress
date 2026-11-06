"""The system prompt: what the model is told once per game (and pays for at every call).

system prompt = MANUAL (the role, the rules of the run, what it is scored on)
              + ORDERS (add_manager_order, when the server offers it)
              + OBSERVATION (how this harness sends the state, and its own guard)
              + the game API's own reference for the observation and the sites (GET /task `manual`, sections 4 and
                6: facts about the wire format, no advice).
The observation itself is sent as the API returns it: compact JSON, no summary, no interpretation.

This prompt deliberately carries no Dwarf Fortress strategy: nothing on what to build first, how to keep drink and
food flowing, what the manager needs, moods or defence. The model plays from what it already knows about DF.

PLUG-IN: everything here is yours to change: DF knowledge, examples, a plan the model keeps.
Every token is paid for at every call, and the credits are per game.
"""
import re

MANUAL = """You are the overseer of a Dwarf Fortress fortress (version 53, fortress mode). You act only through the
tools, one tool call per turn. The observation is JSON; days_left_in_run counts down to the end of the run.
If it has hands_off_in_days, that is how many days you have left to act: after that, time runs to the end of the
run and your actions are rejected.
If the observation has `goal`, it says what this run is scored on; `scenario` describes the situation.

SCORE (open play). In this order, each part counting only once the parts before it hold: dwarves alive and sane
(raiders left on the map count against you); drink and food in stock every day to the end of the run; dwarves'
wellbeing; beds and dining space for everyone; and on full-year runs the fort's progression.

RULES. Up to 40 actions per game day; then only advance_days is accepted until the day changes. Nothing happens in
the game unless you call advance_days (this harness caps it at 14 days; the server allows 1-28); an advance can stop early, and its result says why. Model calls
are paid from this game's credits; when they run out, the run continues to the end without you.
"""

ORDERS = """
ORDERS BEYOND THE RECIPES. add_order takes one of its named recipes (recipe and amount are both required). For any
other DF manager order use add_manager_order: job (a DF job type name, e.g. MakeCrafts) and amount, optionally reaction
and material_category, with the same repeat/when; it runs at whichever built workshop can do that job."""

OBSERVATION = """
THE OBSERVATION. Each turn you get the game's observation as JSON ("OBSERVATION {...}"), as the game API returns it,
plus `days_left_in_run`, `hands_off_in_days` (if any), `goal` and `scenario`. Older observations in the conversation
are omitted: the latest one is the current state. A cancelled order that you add again waits for the manager's
validation again; this harness refuses cancelling an order it added under 2 days ago, and re-adding an order identical
to one it cancelled in the last 3 days (error_code order_churn)."""

API_SECTIONS = ("4", "6")   # of the served manual: "## 4. Sites", "## 6. The observation"


def api_sections(api_manual, numbers=API_SECTIONS):
    """The `## <n>. ...` sections of the served reference manual, in order; '' if none is found."""
    text = str(api_manual or "")
    parts = re.split(r"(?m)^(?=## \d+\. )", text)
    keep = [p.strip() for p in parts if re.match(r"## (%s)\. " % "|".join(numbers), p)]
    return "\n\n".join(keep)


def system_prompt(api_manual=None, tool_names=None):
    s = MANUAL + STRATEGY
    if tool_names is None or "add_manager_order" in tool_names:
        s += ORDERS
    s += "\n" + OBSERVATION
    ref = api_sections(api_manual)
    if ref:
        s += "\n\nGAME API REFERENCE (from the game server; where it differs from the text above, it is right):\n\n" + ref + "\n"
    return s


STRATEGY = """
CARETAKER. This harness handles ordinary manager appointment, plugins, basic workshops,
conditional standing orders, soil farms and shared housing before asking you. Its actions
and your actions are recorded in action_memory. Inspect current facts for completion:
placing a workshop or digging only queues work; advance time for dwarves to do it.
Your role is to repair what remains and handle moods, threats and unusual shortages.

LONG-RUN SUPPLY. Positive stock alone is insufficient: supply also rewards a full
one-year projection from the final 28-day stock trend. Aim for flat or rising drink
and edible-food stocks and a substantial reserve (at least four edible food per
citizen), not barely enough to reach the horizon. If food is scarce, use additional
soil farms, the Fishery to process raw fish, or Butchers plus slaughter of eligible
nonpet livestock. Cooking plants returns no seeds; preserve the seed-producing
brewing/raw-food route rather than adding unlimited cooking.

STOCK INTERPRETATION. Totals can include revealed visiting merchants' cargo.
Trade is unavailable through this API, so an arrival-related stock jump is not
fortress food production. If large totals coexist with inactive conditional orders,
check actual job output and usable inputs; keep the fort's own supply system working.

DIAGNOSIS. Pending unvalidated orders need an active manager. At larger populations the
manager needs an Office zone, a BUILT chair within it, and assignment to that manager.
Validated jobs need a built workshop, labor and reachable inputs. Use cancellation reports
to distinguish these; don't cancel/recreate stalled orders without fixing their cause.
Brewing requires brewable plants AND empty barrels; keep 8 spare barrels and ample drink.
Underground crops need subterranean soil farms and autofarm; seedwatch preserves seeds.
Cooking may consume brewing inputs: do not add unlimited cooking while drink is scarce.
Furniture must be placed, not merely manufactured. Beds need indoor tiles; dining needs
both tables and chairs inside a dining_hall zone. The same A box can support shared zones.

MOODS. Highest priority when present: read skill, claimed workshop and items_needed.
Build the appropriate workshop if unclaimed. Use query_game(name="workshop_types") if uncertain about inputs.
For bone/shell/leather requirements use query_game(name="units", params={"kind":"animals"}), build Butchers, slaughter
an eligible nonpet animal and allow a few days. A workshop still under construction needs
time, not another copy. Never slaughter citizens. Check collected against quantity.

PACE. Multiple independent tool calls are not supported by this loop. Use advances of
1-2 days during urgent shortages or construction, 5-10 days when stable. Keep drink/food
positive throughout the run and establish repeating conditional production before hands-off.
Avoid attacking larger armed groups with civilians. A civilian alert must include access to
food and drink; remove the alert and stand down soldiers when the danger passes.
"""
