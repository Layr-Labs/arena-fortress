"""A dependency-based overseer with one task card and a compact API reference.

The action loop and its guards are inherited from the organizer's plain baseline.
Strategy text lives in prompts/ so it can be reviewed separately from execution.
Only public task metadata selects a card; observed state still determines actions.
"""
import re
from pathlib import Path

PROMPTS = Path(__file__).with_name("prompts")
MANUAL = (PROMPTS / "overseer.txt").read_text(encoding="utf-8")

ORDERS = """
ORDERS BEYOND THE RECIPES. add_order takes recipe and amount. For other DF manager orders,
add_manager_order takes job and amount, optionally reaction, material_category, material,
item_subtype and repeat/when. Use an offered job and its correct workshop. Do not invent
query tools: this harness supplies native game actions only."""

OBSERVATION = """
OBSERVATION FORMAT. The user message OBSERVATION {...} contains current game facts,
days_left_in_run, hands_off_in_days if relevant, goal and scenario. Older observations
are omitted; no stock history or persistent plan is supplied. Use only visible facts.
stocks.food_edible is edible food; furniture_free is available unplaced furniture.
Furniture entries have built and zone_ids; zones have furniture and furniture_planned.
Orders have validated, active, left, jobs_in_progress and when. A false built flag is
pending construction, not a functioning workshop. R sites distinguish designated and dug.
Stress categories run from 0 (most stressed) to 6 (content).

MOODS. Current mood facts include skill, job, claimed_workshop, waiting and collected_items.
items_needed appears while waiting and contains visible demand clues. Primary quantity
can be null; Fey moods may reveal material/cloth details. No hidden availability counts
or raw flags are available. Verify completion from observable progress and events.

GUARDS. This harness refuses cancelling an order it added under 2 days ago and re-adding
an identical order within 3 days of cancelling it. These are order_churn refusals.
It advances one day after 10 consecutive actions without an advance, enforces the
daily action allowance and caps advance_days at 14 days. Its credit reserve ends model
calls before the gateway limit. Plan the unattended period before the reserve is reached.
"""

API_SECTIONS = ("4", "6")
CARDS = frozenset(("OP1", "MY1", "LT01", "LT02", "LT03", "LT08"))


def api_sections(api_manual, numbers=API_SECTIONS):
    """Extract numbered sections of the server reference without changing its text."""
    text = str(api_manual or "")
    parts = re.split(r"(?m)^(?=## \d+\. )", text)
    keep = [p.strip() for p in parts if re.match(
        r"## (%s)\. " % "|".join(re.escape(n) for n in numbers), p)]
    return "\n\n".join(keep)


def task_card(task):
    """Select only from explicit public task names/ids; unknown tasks use the core."""
    if not isinstance(task, dict):
        return ""
    for key in ("name", "id"):
        name = task.get(key)
        if not isinstance(name, str):
            continue
        prefix = re.split(r"[-_\s]", name.upper(), maxsplit=1)[0]
        if prefix in CARDS:
            return (PROMPTS / f"{prefix}.txt").read_text(encoding="utf-8")
    return ""


def system_prompt(api_manual=None, tool_names=None, task=None):
    s = MANUAL
    if tool_names is None or "add_manager_order" in tool_names:
        s += "\n" + ORDERS
    s += "\n" + OBSERVATION
    card = task_card(task)
    if card:
        s += "\n\n" + card
    # Site geometry is essential and relatively stable. The served observation
    # section contains obsolete mood fields; use the corrected compact guide above.
    ref = api_sections(api_manual, ("4",))
    if ref:
        s += "\n\nGAME API SITE REFERENCE (current tool schemas govern accepted arguments):\n\n" + ref + "\n"
    return s
