# No model: dry rooms, grazers culled first, an earlier feast, food through the final stretch and the thaw near the wagon

This is the promoted PR #124 harness (submission `65e60732`) with the model switched off as in PR #142
(`NO_MODEL = True` in `plain/harness.py`: the deterministic layer plays the whole game, no model call is made), and
these changes on the long open tasks (MY1, OP1) only:

- beds and dining seats that outgrow their rooms: beds go to the next site the game takes them on when the
  dormitory level is too wide for furniture or full, and when no site can take more beds or dining seats one
  more 3x3 room is dug for them (one at a time, at most four a game);
- the manager's office is set up from the start, on a dug room (a level from day 10), never on a farm level, a site
  the game refuses its chair on is retired, any office the manager owns counts, and its chair comes first: from
  about 20 citizens DF validates no manager order without one;
- one meeting area below ground on the dining or dormitory level, so idle dwarves wait there and not at the wagon;
- the standing brew order runs from one brewable plant; the first staircase avoids nearby water; two animals per
  hunger cull in the final stretch for a fort of 15 or more; drink and barrels for the last winter from about 150
  days before the end of a full-year game;
- the civilian alert also holds around the thaw of the water near the wagon: deep water seen in autumn and gone
  from the observation (ice is not water) records a freeze, the thaw is expected at the freeze's mirror image
  about day 293 of the year (both mirror each other on every fort where we saw the water freeze), and the alert
  runs from a day before it to two days after the water is seen again, besides the window at the start of spring;
- placed furniture that was unbuilt when DF reported a suspended construction, and is still unbuilt ten days
  later, is not counted as coming, so free items are placed in its stead (no tool resumes a suspended job); the
  last bed order of the game counts such beds as missing;
- rooms are dug only where the map shows no water, ice or magma in the box or beside it on its level: `dig_room`
  measures the box from the site's corner, and a 9x7 dormitory reached a river one level down and drowned a dwarf.
  A wet box shrinks from the same corner (7x5, 5x5, 5x3, 3x3); a room with no dry box is left undug and the next
  room takes its role; a failed map query digs as before;
- a hunger cull takes grazers first, the oldest first: no tool makes a pasture, so they starve (every local
  full-year game lost three to nine, all grazers), and the animals kept for the feast are the largest others;
- the feast starts 15 days before the end (was 14), the day before the spring alert would keep the butcher in
  the shelter;
- from 30 days before the end until the feast, when nothing but the animals kept for the feast is left and the
  food is at most 3 (or a fifth of the citizens), the smallest of them goes, one a pass, never the last: a cull
  waited for 0 food, the pass sees the food every two days, and food stood at 0 for up to seven scored days;
- a W site a workshop was placed on is not offered to another workshop type in the same pass (yukonautominer's
  `bbbb6c26`): the observation is a pass old, and the Still and Kitchen were refused on the Carpenters' site and
  came on day 4 to 8.

The lab tasks run exactly as PR #124 (its office step verbatim, the two-plant brew order, the usual staircase site,
no map query before digging, the old workshop-site and bed counts; the slaughter schedule is open play only).
The model loop, prompt and digest are still in the package, unused while `NO_MODEL` is on. The rest of this file
describes the PR #124 build.

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
