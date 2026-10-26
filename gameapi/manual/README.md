# gameapi/manual: the game API's reference manual

`MANUAL.md` is the text `GET /task` serves as `manual` (contract `docs/GAME-API.md` §3). The facts adapter
(`gameapi/server/adapter.py`, `Facts.manual()`) reads it verbatim. It is the frozen MANUAL (`harness2.MANUAL`) minus
its advice, extended to the season-0 surface: all 22 tools (with `add_manager_order`, `slaughter` and every
workshop type), the obs schema 6 fields, the 9 queries, `/events` and the server's rules, checked against the code
in `gameapi/facts/` and `gameapi/server/`.

`MOOD-VISIBILITY.md` covers a separate question: whether the mood item lists in the observation show more than a
vanilla DF player can see. It proposes a change to `gameapi/facts`, which has not been applied.

## The line between facts and advice

Spec §3.2: the API gives facts and the harness interprets. The manual keeps:
- what a tool does, its arguments, checks, effects and result fields;
- what each observation field and query result means, with its units and ids;
- the site kinds;
- the server's rules;
- how DF behaves when a tool asks it for something, including the frozen harness's in-game measurements, which are
  marked as measured.

It drops:
- anything that tells the reader what to do, in which order, or what to aim for;
- judgements of whether a state is good or bad;
- the score's priorities.

Examples of what was dropped or reworded:

| frozen MANUAL | here | why |
|---|---|---|
| "appoint_manager first." | appoint_manager's effect; "with no manager they stay unvalidated" | an order of play is advice; the mechanism is a fact |
| "From 20 citizens the manager validates only from an office of their own …" | kept as a measurement (*measured in game, not a documented DF rule*), next to DF's `manager_required_office` | the facts layer dropped `manager_needs_office` as a measured threshold; the measurement is still a fact once it is labelled |
| "add_order repeat/when keeps an order going (e.g. brew daily while drink is below 50) instead of one-shot amounts" | what `repeat` and `when` do in DF | the example target (50) and "instead of one-shot" are strategy |
| "recent_cancellations … Fix the cause; re-queuing the same order won't help." | "DF's job-cancellation reports, as DF wrote them" | an instruction |
| "stuck_because says why the harness thinks an order isn't progressing" | removed | `stuck_because` is no longer in the observation (interpretation, now the baseline harness's) |
| "stress … 0-1 is stressed" | "0 = most stressed … 6 = content"; `stressed_citizens` counts ≤ 1 "(the definition the trusted recorder uses)" | the threshold is the scorer's definition, so it is given as that, not as a judgement |
| "Digging on its own adds nothing." "Making things counts only through these …" | removed; the manual points to `challenge/SCORING.md` | statements about the score are scoring documentation, and here they read as priorities |
| The SCORE paragraph ("What counts is how the fort is doing, in this order …") | removed (pointer to SCORING.md) | as above |
| "an armed party can kill most of a fortress in a day"; "a squad sent against a stronger party loses its members" | "Civilians without weapons fight unarmed"; squads use only existing equipment | the outcome forecasts are judgements; the mechanics are facts |
| "Locked doors … stop these invaders, and your own dwarves too: lock once everyone is inside." | "A locked door is forbidden: the fortress's own dwarves and animals don't pass it either." | "lock once everyone is inside" is advice |
| "Farming underground: dig_stairs down …, dig_room …, advance until dig_designations_pending is 0, then build_farm" | each tool's effect, and DF's rule that crops grow only on plots of their kind (subterranean or not) | a recipe of moves is a strategy |
| "Nothing happens unless you call advance_days (1-14 days)" | time moves only during advance_days (1-28 days) and when the server runs the fort itself | rewording, and v0's limit |
| "You are the overseer …"; "one tool call per turn"; "Older observations in the conversation are omitted" | removed | the frozen loop's prompt and window, which are harness choices |

Facts the frozen MANUAL didn't have and that are added here: the K-actions rule, hands-off and wall cap, the error
codes, the hidden-information rules, every tool's checks and result fields, the stock-name → DF-condition table of
`add_order` (whose meanings differ from the observation fields of the same names), the tripwire definitions, the
query result shapes, and the `/events` paging limit.

## Effect on the baseline harnesses

The plain baseline (`baseline/plain/prompt.py`, season 0's `submission/`) puts sections 4 (Sites) and 6 (The
observation) of this file in its system prompt, under "GAME API REFERENCE (from the game server …)". So this file
is not neutral for the baseline: editing those sections changes what the baseline's model reads, and that is paid
for at every model call. The organiser's reference harness appends the whole file only with
`DFBENCH_STARTER_API_MANUAL=1`.

The legacy adapter (`--facts legacy`, over harness2) still serves `harness2.MANUAL`, because its tools are the
frozen 20, not the ones described here.

## Changing the manual

Changes that alter the meaning of a tool or field go with the code change. `gameapi/server/tests` checks that
`/task` serves this file unchanged and names every tool and query. The file is in the v3 key's `sem`/`obs` file list
(`adapter.Facts.key_tool_files()`), because the baseline harness puts parts of it in its prompt: editing it changes the key.
