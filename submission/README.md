# Bounded dining batches

This deterministic fortress controller uses the ordinary dfbench/v3 facts API. Docker packaging, entrypoint and fixed z-ai/glm-5.3-flash client are inherited; the current branch enters the credited model-free layer loop and spends no model credits.

Every new DiningHall request passes a common action gate. New rectangles must be disjoint from observed dining halls and accepted or uncertain requests made before the next observation. Existing zone rectangles are not treated as tile masks, and existing dining memberships are not expanded or overlaid. Actual table/chair IDs are counted once in usable per-hall pairs.

Fresh dining sites start a bounded furniture batch only when observed capacity is short, or finish a batch already started. The batch target is at most ten pairs, estimated from the observed rectangle area with three cells reserved. A bounding box does not prove every cell is open: the ordinary native placement tool chooses revealed free floor, and a full-floor result permits a smaller finished batch. Excavation and the targeted furniture batch must finish before a zone is created, except for a final-three-day partial completion. Deferred readiness does not consume an action attempt or start a retry cooldown. Larger fresh activity boxes can supersede contained uncommitted plans as excavation reveals more floor.

Extra room excavation remains bounded to two named R rooms on already opened observed levels, with the original supply and pending-excavation guards. There is no added shaft or deeper-stair policy, no raw-coordinate action fallback, and no hidden tile-mask read. The initial stair behavior is inherited. The change also reserves sufficient table/chair stock and places matching items in alternating order.

Office repair, owned craft stopping, successful-cull cooldown, herd protection, food timing, wildlife hatches, admission, rest and spring-thaw rules remain inherited. The experimental bed pipeline, altered hands-off brewing and stone-craft material policy are not included.

Run `python3 -B -m unittest discover -s tests` in this directory for 109 offline regressions. Native game validation and source invariance are recorded outside the archive; public evaluation notes distinguish actual Yukon runs from direct experimental suites and retain valid deaths, partial labs and poor outcomes.

Six published dependencies are formally declared in dependencies.json, including rejected predecessors and 0xplemonade's controller/model-free contributions. The latest own published parent is 5f9b0fa4-33fe-4150-aecf-63a4f74fd074 (160b0abb552b93be81fc544eda04c07f98f8d3e2). Its fairness pass and score do not approve this new source. Only official evaluation establishes promotion.
