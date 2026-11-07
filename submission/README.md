# Hybrid fortress controller

This package keeps the 106-test public-goal source and adds six tests for a larger first dormitory dig. It uses a deterministic controller before the plain model loop. The controller makes no model calls. See [NOTE.md](NOTE.md) for source credit, precise conditions, tests, and trial limits.

## Goal policies

- With a hands-off window and a goal that says “drink must not end lower,” the controller makes a daily brew order without the drink ceiling. It keeps the plant and barrel conditions. Other tasks keep the ceiling.
- With a hands-off window and a goal that says “every dwarf must have a placed bed,” the controller skips dining table and chair orders and placement. It uses one-turn pacing, requests a second Carpenter when fewer than two are planned or built, and may try one other observed area after actual `no_space` on primary bed placement. Other tasks keep four-turn pacing and the existing one-Carpenter target.
- For the bed goal, the first dormitory dig is 11 by 9 instead of 9 by 7. The 36 extra candidate tiles are not proof of dry or free capacity. Other tasks keep the earlier size.
- While that bed goal is unmet, model-requested advances are capped at two days so the controller can check progress. Other tasks and a satisfied bed goal retain the 14-day cap.

The recorded test case used A7 at `(93, 91, 75)` and A2 at `(90, 86, 77)`. The runtime uses observed areas and has no fixed coordinates. A parent trial accepted one alternate bed placement; this does not prove total capacity. Open tiles do not prove placement capacity.

## Checks and result status

All 112 software tests pass. The fake LT08 container check built and exited cleanly at day 39; its server reached day 60. The fake lab predicate did not pass. One full native local LT08 game passed all four clauses: 54 built beds for 48 citizens, no deaths, positive supply, and drink 548 to 560. It used unpriced Qwen on a public seed. This version has no official GLM result. Its 106-test parent scored 79.8 and was not promoted; the accepted 54-test source remains at 86.07.
