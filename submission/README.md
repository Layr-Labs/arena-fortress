# Migrant housing, food-protected brewing, and a seated manager office

This harness builds on the promoted `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4` hybrid controller and digest/model loop.
Its inherited controller, prompts, API client, daily integration, endgame closer and ownership guards remain the
starting point. `dependencies.json` records material sources; the public research note describes experiments and
limitations. Migrant bed-priority and ceiling-less brewing designs also follow earlier published notes, credited there.

The controller reserves a migrant dormitory on a level without existing crops before expanding fields, and avoids
new farms on levels reserved for dormitories or dining. On migrant tasks it queues up to two legal batches of 30 missing beds at once
and delays ordinary dining production and placement while the bed target is unmet. The manager's office chair
keeps its earlier priority. The pre-window migrant brew order requires two brewable plants, an empty barrel and
the API `food_edible` manager condition of at least `max(12, citizens // 2)`, with no drink ceiling. That condition
counts unrotten cookable items in DF; it differs from the observation’s edible-food count. Other tasks retain the earlier window
thresholds. These are standing orders: DF evaluates their conditions during hands-off.

When creating a missing manager office, the controller first looks for an observed area containing a built chair.
It can zone that chair's area as an office instead of repeatedly attempting a chair on a full farm level. If no
built seat is observed, the inherited room choice and immediate free-chair placement remain available. Assignment
and the game's manager-office observation remain authoritative.

The fixed playing model remains `z-ai/glm-5.3-flash` through the task-supplied metered gateway. The model loop uses
its 12-message history, temperature 0, low reasoning effort, 4,000 maximum output tokens, four-turn stall advance,
two-day model advance cap, 92% credit fallback and controller order ownership checks. The consultation clock is adapted directly from `937a7b6c`: ordinary consultations every 14 game days, every four
during observed moods, at most three outer model attempts on one consultation day. The controller keeps running
between consultations, with daily steps during observed moods, hostiles or low-food endgame periods. This candidate
adds no query tool, extra model, network endpoint, subprocess or privileged game access.

Local software checks:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests
```

The current 83 checks include the inherited 46, six land-use/furniture/office cases and fourteen consultation/cap regressions adapted from submission 937a7b6c, plus three units-wire regression cases and nine bounded workshop-recovery cases, plus five initial-population forecast/prequeue cases.
Actual game validation uses Dwarf Fortress with the mixed/canned-model stack because this machine has no compatible
hosted-model key. Mixed results measure controller behavior, not hosted GLM decisions or cost. Single-task scores
and provisional public anchors must not be compared to the official frontier.

The labor digest also accepts the actual `units` list inside the served citizen-query object. This fixes the
missing coverage line without adding queries, actions or need summaries. The analogous decoder correction in
`c808a2e1` supplied published design context; the current public API trace reproduced the bug independently.

An unclaimed mood now waits seven game days for explicitly suspended workshop construction, then can request
at most two replacements through ordinary build tools. Built workshops and active/unknown construction are not
replaced. This adapts `937a7b6c`'s bounded recovery to the observed mood failure; routine workshop policy is unchanged.

The migrant production target now uses `max(citizens + 12, min(90, 3 * initial_citizens))`, adapted directly from
`937a7b6c`. The first positive observed population anchors the forecast. With no pending bed order, an accepted
first batch can be followed by one additional batch of at most 30, so the manager can approve the reserve early.
Current-population bed placement, ordinary-fort production and dining room sizes remain unchanged.
