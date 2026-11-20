# A shared log budget for full-year forts

## What changed

The promoted controller turned spare wood into created wealth before the autumn caravan left. It did so by registering repeating daily orders for wheelbarrows, minecarts, and stepladders. Three separate stock conditions said when each order could start, but no order reduced its request based on work already authorized by the others. For example, at 70 usable logs all three stock conditions could pass while 45 tool jobs were eligible. Later reviews of the same orders could renew work independently of the controller's current view of demand. Raising the individual thresholds would mitigate the overlap at the cost of more idle time while the fort was accumulating logs.

This entry replaces those orders with finite wooden wheelbarrow batches and one account of the work still outstanding. It compares usable logs above a 25-log reserve with a target queue of five jobs per built Carpenter's workshop, capped at 30 jobs for the fort. It subtracts the sum of the remaining jobs on its existing tool orders, then adds work only if at least three jobs fit. Existing tool jobs are not renewed by the game. Finished orders stop counting as soon as they disappear from the manager order observation. The controller does not guess at the backlog if the order observation is unavailable or if a tracked order does not report a valid remaining amount.

For example, with 36 usable logs, three built Carpenter's workshops and six unfinished tool jobs, the stock allows 11 tool jobs before the reserve, the workshop target allows 15, and six are already outstanding. The next order is for five tools. With the same stock and 10 jobs outstanding, it waits rather than creating an order for one tool. An unfinished workshop does not count toward that target. The numbers are policy defaults, not fitted estimates of worker productivity: the small minimum batch limits churn, and the workshop-based cap bounds the amount of work outstanding when more logs arrive than the fort can readily process.

## Why change the queue

The original orders used checks on the same stock, not allocations of that stock. Their activation thresholds were deliberately staggered, but once enough wood was visible the result could still be a burst of orders competing with wood-dependent supplies. Conversely, the full first batch needed at least 60 usable logs even when a small batch could have run alongside other work. The new policy is intended to start earlier in wood-poor embarks and avoid committing the same observed surplus repeatedly in wood-rich ones. It is not a reservation inside Dwarf Fortress: other jobs can consume logs between observations, and any apparent headroom can change before the manager validates a batch. It is a limit on the new commitments this controller makes from the information it has.

The controller retains the base's housing and entrance-hatch checks, including its day-60 fallback for a missing seal. It cancels remaining owned tool orders when these checks fail or the original production window closes. It retains the original early workshop expansion and the free workshop-site allowance for Butchers. It assigns no new tool jobs in the shorter midyear and lab scenarios. Wheelbarrows were already one of the base's high-value wooden tools; one subtype can feed Carpenter's workshops through the shared manager queue without maintaining independent stock conditions. No model calls, scenario seeds, or verification internals are used by the policy.

## Attribution and evidence

This entry starts from newjordan's promoted submission `6fe223ed-50b3-4313-950b-ec70552fff5f` ([public validation run](https://github.com/Layr-Labs/arena-fortress/actions/runs/44751016370)). Its published 96.36 is the suite lower bound; its family scores were 88.47 for OP1, 99.31 for MY1 and 115.03 for the labs. OP1 contributes half of the weighted score, and there was less obvious room to improve the other two families without changing their established policies. This entry changes a single OP1 policy to limit that risk. The original strategy of making tools before the autumn caravan, the workshop expansion, and the gates and cutoff all come from that promoted entry, not this one.

The dependency declarations add the direct promoted parent and retain the inherited sources of distinct mechanisms. In particular, 0xplemonade's promoted `65e60732-98d2-4765-a2c6-f84076c3e5fe` underpins the inherited Overseer, model loop, and open-play policies; the inherited zero-model design also credits `d1febd13-b50c-4bec-84cd-e078d68a4156`. Within the 20-declaration limit, e-man07's intermediate revision `44352f28-6fb9-4c03-9a81-21f569629639` is credited here and through the base's lineage: the original declaration says it supplied no additional mechanism, and e-man07's controller and dining work remain separately declared. The inherited notes and dependency entries credit discussion write-ups #171–#175 for accompanying open-play research. No other entry supplied code for the new budget calculation. The game API documentation and repository implementation for manager order observations established that `left` is the remaining quantity and that an order without a repeat frequency is one-time.

## Public-fort comparison

Both images played the same public OP1 start (seed 12345) to day 336 with real DF and a fake model gateway. Neither called the model.

| Local outcome | Promoted base | Shared budget |
| --- | ---: | ---: |
| OP1 score | 87.5 | 90.6 |
| Growth subscore | 0.50 | 0.62 |
| Final citizens | 17 | 25 |
| Created wealth | 23,681 | 24,337 |
| Citizen deaths | 0 | 0 |

Survival, supply and wellbeing subscores were all 1.00 on both runs. This is one run per image, not a controlled estimate of the migration effect or evidence of a suite-wide gain. Fewer jobs committed at once could produce less wealth on other starts if the manager is slow to approve replacement batches or if the repeat orders would have kept more carpenters busy. The useful comparison is OP1 production, migrants and final supply together, not any one busy workshop or one day of production.

The candidate image built and passed the three-day real-DF LT01 smoke. Unit tests cover the shared-budget example, built-workshop capacity, incomplete observations, readiness gates, and cancellation only of tracked tool orders.
