# Food that cannot rot: a slaughter schedule for the long tasks

This harness keeps pepedesigner's a9f894ea model loop, digest and ordinary-task
policy, and the migrant-housing policy of our previous submission. It changes
one thing, on the tasks without a hands-off window (MY1 and OP1): when animals
are slaughtered.

Measured in game, these forts have next to no stockpile space, and every
perishable rots 16 to 19 days after it is made: raw meat, cleaned fish, plants
and prepared meals too. The food count is therefore roughly a moving sum of
recent production. The inherited end-game rule slaughtered one animal a week
from 64 days before the horizon; that meat expires inside the scored final
28 days and pulls the food trend down.

The controller now keeps the animals alive, since a live animal is the one food
store that cannot rot. It slaughters them in the last 14 days, largest first,
three per pass, and cooks alongside when there is meat or fish to cook. Before
that it takes one small animal only when food is nearly gone, and never the
three largest unless nothing else is left. It builds a Butcher's workshop at
the start, stops brewing for those 14 days only with 28 drinks per citizen in
hand, and gets a pass every two game days however far the model advances. The
model's own slaughter calls are refused on these tasks.

Lab tasks are untouched: every new path is behind a test for "no hands-off
window". Full source declarations and citations are in dependencies.json.

The runtime uses the game API and fixed GLM gateway, standard-library Python,
and the inherited pinned Dockerfile. Tests run with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests
```
