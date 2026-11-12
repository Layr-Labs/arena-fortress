"""The system prompt: what the model is told once per game (and pays for at every call).

system prompt = MANUAL (the role, the rules of the run, what it is scored on)
              + ORDERS (add_manager_order, when the server offers it)
              + OBSERVATION (how this harness sends the state, and its own guard)
              + the game API's own reference for the observation, the sites and the known limits of v0 (GET /task
                `manual`, sections 4, 6 and 10: facts about the wire format, no advice).
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

AUTOMATIC = """
ALREADY HANDLED FOR YOU. A deterministic layer runs once per game day, before you: the manager and their office,
autochop/seedwatch/autofarm, the Carpenters/Still/Kitchen workshops, standing brew/barrel/cook orders, digging rooms,
farm plots, ordering and placing beds, tables and chairs, the dormitory and dining zones, the shelter burrow, and the
workshop a strange mood asks for. Don't repeat that work. Use your turns for what it can't see: why something is
stuck, shortages, threats, and advancing time."""

OBSERVATION = """
THE OBSERVATION. Each turn you get the game's observation as JSON ("OBSERVATION {...}"), as the game API returns it,
plus `days_left_in_run`, `hands_off_in_days` (if any), `goal` and `scenario`. Older observations in the conversation
are omitted: the latest one is the current state. A cancelled order that you add again waits for the manager's
validation again; this harness refuses cancelling an order it added under 2 days ago, and re-adding an order identical
to one it cancelled in the last 3 days (error_code order_churn)."""

API_SECTIONS = ("4", "6", "10")   # of the served manual: "## 4. Sites", "## 6. The observation",
                                  # "## 10. Known limits of v0"


def api_sections(api_manual, numbers=API_SECTIONS):
    """The `## <n>. ...` sections of the served reference manual, in order; '' if none is found."""
    text = str(api_manual or "")
    parts = re.split(r"(?m)^(?=## \d+\. )", text)
    keep = [p.strip() for p in parts if re.match(r"## (%s)\. " % "|".join(numbers), p)]
    return "\n\n".join(keep)


def system_prompt(api_manual=None, tool_names=None):
    s = MANUAL
    if tool_names is None or "add_manager_order" in tool_names:
        s += ORDERS
    s += "\n" + AUTOMATIC + "\n" + OBSERVATION
    ref = api_sections(api_manual)
    if ref:
        s += "\n\nGAME API REFERENCE (from the game server; where it differs from the text above, it is right):\n\n" + ref + "\n"
    return s
