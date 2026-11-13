# Successful-cull cooldown on the published controller

This revision uses my published model-free e401f220-2014-40a8-b488-dcb998fae79b controller unchanged except one cooldown condition in overseer/openplay.py. A protected/empty herd check that marks no animal no longer starts a delay before the next emergency. Successful marks still use the same spacing. Animal ranking, pet exclusion, herd protection, early food thresholds, feast timing, dining, office/workshop repair, owned craft stopping, wildlife and thaw policies remain the published controller's.

A public trace logged an empty protected-herd check on day 191 with food=2, followed by food=0 on day 193, but the old timer delayed the next cull until day 197. A scripted replay reproduces the delay in the published source and an immediate eligible mark in this correction. In the focused native comparison, a day-190 empty check was followed by a day-192 food-zero mark, exercising the new rule. Three valid public MY1 outcomes per arm averaged 99.5333 versus 98.2333, with no deaths; different native histories/populations limit causal interpretation.

Five published dependencies are credited in dependencies.json, including my office/workshop/craft predecessors and 0xplemonade's promoted controller and model-free branch/tests. The policy still uses layer_only and makes no model requests; the unused client names the required fixed GLM model. Standard-library Python only. Local games use real DF and the mixed stack; public local scores are not official-comparable.

Known baseline limitation: ordinary dining-zone expansion can leave furniture in overlapping dining memberships, and the public scorer can sum that furniture more than once. This branch does not change zoning or add any new zone policy; the issue is disclosed in its public note rather than claimed as an improvement. Separate fresh-hall/pair-count experiments eliminated overlaps but had capacity and survival losses, and are not included here. The new code targets a real delay before obtaining food, not dining bookkeeping. This source requires its own review and full official evaluation; the predecessor's fairness pass does not approve this change or settle the disclosed limitation.

The source passes 42 tests: the 37 published-controller tests and five new cooldown/protection/refusal regressions. No fresh-hall rewrite, extra mining, dairy, lockdown/rest change, largest-animal policy or proactive herd threshold is included.

Tests: PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s submission/tests.
