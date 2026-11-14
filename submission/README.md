# The manager's office gets its chair on every task

This build is 0xplemonade's leader (65e60732) with one change, to the manager's office in overseer/harness.py.
From about 20 citizens DF validates no work order until the manager has an office with a built chair, and that
includes the order for the chair itself. In a local full-year game the office was made over a 7x3 level with no
open floor; its chair was refused six times for want of floor, the free chairs then went to the dining hall, and
from day 210 (21 citizens) no bed, chair, brew or meal order was validated for the rest of the year.
0xplemonade found the same deadlock first (discussions #173 items 20 and 26, #174, #175) and set the office up chair
first in PR 145 (bbd7752f); this is an independent implementation of that idea on the leader's code (no code taken),
plus a step that gives up and moves an office whose site refuses its chair.

- A new office goes on a dug office or dining room, else on an A site with open floor: one that no dining hall or
  dormitory covers first, then the most open tiles. A site an office was given up on is not used again.
- The office's chair is placed as soon as the zone is made on every task (before, only the migrant task did this).
- An office whose site refuses its chair twice for want of floor (`no_space`) is handed to another citizen with no
  position, and a new office is made elsewhere and given its chair.
- When the manager's office has no chair and none is free, one chair is ordered on every task (before, only the
  migrant task's bed-only queue did this).

Tests: `tests/test_office.py` replays the recorded failure on a stub game.

---

# Dining seats, Hamlet wealth, stuck workshops, a lockdown's shut-out citizens and the spring thaw

The model loop, digest and controller are our PR #115 build (pepedesigner's a9f894ea line, with its
wildlife lockdown, no fishing and first-felling wait). This build changes six things. All but the third and
fifth apply to the long open tasks only (MY1, OP1; lab tasks keep the earlier dining and wealth steps and
have no lockdown):

- Dining seats are counted the way DF lists them (a table or chair inside a dining zone, each once),
  dining furniture goes only where a dining zone covers it or can be made, and tables and chairs are
  ordered against that count. GordoAR's coverage check (5dfdcf15) zones a site after placement.
- Full-year games make wood crafts from day 40 while 25 logs are in stock, until created wealth is
  5,500: i34-9's rule (fa9c13cc) for the Hamlet rank.
- A workshop whose construction DF suspended for three days is built again on another site, at most
  twice per type (a core workshop that is missing altogether takes a free site first): no tool resumes a
  suspended job.
- A citizen on the surface when a wildlife lockdown's hatch is due to lock (asleep, or a migrant who
  arrives later) is let in: the nearest hatch that every hostile and large predator in sight is more than
  60 tiles from stays open, or is opened again; it locks when they are below, when the danger comes nearer,
  or after two days, at most three times a lockdown, and at once if invaders take the alert over. The
  alert stays on throughout.
- The civilian alert holds from the last day of winter to the third day of spring (no hatch is locked):
  ice thaws then, and a woodcrafter idle in a frozen river bed drowned at the thaw in a local full-year
  game. A lockdown can still start meanwhile and takes the alert over; the day above ground owed after a
  full lockdown comes first.
- The STATUS digest starts with ALERT lines for dangers to life (a citizen's death or fight with a large
  predator in the latest reports, a large predator in reach of the wagon, citizens shut out), stating the
  lockdown as the observation shows it. Its threats line says that ordinary wild animals are not listed as
  hostiles, and it no longer suggests steps the harness refuses (autochop while the first felling waits,
  the civilian alert, a Fishery or Butchers on a calm fort).

Declarations and citations are in dependencies.json. Standard-library Python, the game API and the fixed
GLM gateway only. Tests: `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests`.
