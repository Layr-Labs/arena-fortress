# The promoted PR #124 harness with the model on, plus the #145/#154 layer: beds and dining seats that outgrow their rooms, the manager's office from the start, an underground meeting area and the supply fixes

This build is the promoted PR #124 harness (submission `65e60732`, published 96.02) playing with the model on —
its model loop, digest, prompt and `plain/harness.py` are kept verbatim — with the deterministic-layer
improvements of the PR #145/#154 line (submission `307ced15`) merged onto the same base. From that line this
build takes, on the long open tasks (MY1, OP1) only:

- beds and dining seats that outgrow their rooms: beds go to the next site the game takes them on when the
  dormitory level is too wide for furniture or full, and when no site can take more beds or dining seats one
  more 3x3 room is dug for them (one at a time, at most four a game);
- the manager's office is set up from the start, on a dug room (a level from day 10), never on a farm level, a site
  the game refuses its chair on is retired, any office the manager owns counts, and its chair comes first: from
  about 20 citizens DF validates no manager order without one;
- one meeting area below ground on the dining or dormitory level, so idle dwarves wait there and not at the wagon;
- the standing brew order runs from one brewable plant; the first staircase avoids nearby water; two animals per
  hunger cull in the final stretch for a fort of 15 or more; drink and barrels for the last winter from about 150
  days before the end of a full-year game.

The lab tasks run exactly as PR #124 (its office step verbatim, the two-plant brew order, the usual staircase
site): the merged layer gates every new step behind the open-task check, and the office step keeps PR #124's
`office_lab` path for lab tasks.

The one edit of ours outside the merge is `plain/harness.py`: PR #154's measurement flag `NO_MODEL = True` and its
early `layer_only` return are removed, so the build plays with the model the way PR #124 does. The reasoning is in
our note: on the private MY1 forts the model was patching a housing gap the layer alone left open (PR #142's four
short-of-housing MY1 games against PR #124's one tier-1 game), and the leader's published 96.02 was reached with
the model on. The rest of this file describes the PR #124 build.

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
