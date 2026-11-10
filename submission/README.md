# Preserve housing floors when the model requests farms

The harness runs python -m plain: the fixed z-ai/glm-5.3-flash model through the supplied metered gateway, with the inherited deterministic Overseer between model consultations. It uses the facts-only GameClient interface. This revision extends the existing ownership guards to ordinary long-game farm placement.

The complete published parent is 7dec8dfb-770a-46ab-a933-20456e6cf351 at commit4cde6a06c379db10d2c297fe306d19acffa109a8. All47parent files were verified against that public commit. That submission published its source but failed Weekly cap(cost control) before official games; its local mixed96.79 is not an official score or promotion. The parent contains the PLANT_GROWTH fruit fallback repair, cooking-only seedwatch guidance, fish-cooking/housing/food/recovery policies and191checks.

## Change

On ordinary horizons of at least216days, without a hands-off window or migrant goal, Plain refuses a model build_farm request on an observed floor containing an R room successfully reserved by the controller for dormitory, dining or office use. This mirrors the controller's existing farm-floor isolation. It retains the latest model-visible site catalog before digest queries, so an F-site alias exposed by excavation is checked by its observed floor rather than merely by its identifier. Unknown or malformed sites are left to native argument validation.

The model receives a local layer_owned refusal explaining that it should choose a crop site on another floor. Existing plots and the controller's own farm construction are not removed or changed. Other model tools, other floors, the four short lab tasks and migrant goals retain their existing authority. The policy reserves the floor, not just the nominal3x3 room rectangle; that conservative choice matches the inherited broad-area furniture and zone policy. It may constrain otherwise usable crop space and does not promise to solve every housing or farming problem.

All deterministic controller code is byte-identical to the published parent, including craft start40/log reserve25/wealth target5500, migrant beds, military/logging behavior, ordinary and window supply orders, and the native-container-compatible fruit fallback. No rejected14-day livestock timing, extra-room excavation, meal-subtype experiment, fishing restriction, hatch strategy or budget-cadence patch is included. The fixed model, client, parser, pricing/budget handling, tool schemas and action limits are unchanged.

## Evidence

The parent public MY2021 control ended96.2 with20citizens,22built beds,7dining seats,6free tables and6free chairs. The controller dug R2 as7x5dining on3; the model subsequently farmed it via F2 on14. Both F2 and R2 were visible on the same observed floor. Later tables and chairs filled an office whose conversion to DiningHall was refused site_used. An offline decision replay of that exact recorded request against the real preceding observation confirms that this guard would refuse it. The replay made no game or model calls and is not a causal score measurement.

All201checks passed:191inherited plus10own ownership/transport/fresh-site/scope cases. They cover the recorded F2 alias, the room itself, dorm/office reservations, an alias absent from the older controller catalog, ordinary crop floors, crop roles, labs, migrant goals, malformed sites and unrelated model tools.

Three selected native public216-day prototype games completed normally with exit0/no OOM:
- MY2021: parent96.2, candidate100;18citizens/22beds/10seats/no death;0local guard refusals.
- MY2020: parent100, candidate97.4;19citizens/22beds/12seats/no death; wellbeing.947;0local guard refusals.
- MY2019: parent100, candidate100;20citizens/22beds/12seats/no death;1local farm-floor guard refusal.

All three had full food/drink supply credit. The adverse wellbeing comparison is retained. Population, layout and jobs vary between native runs, and two cases did not execute the new refusal, so these outcomes do not establish a causal score gain. The active refusal in MY2019 and offline recorded-request replay are separate behavioral evidence.

The tested prototype has source103cadb4687eb09fb55a6c63ee684e2a4b68a3c7aae88b7584aefafd965b4a94,201checks/48files. Only README.md and dependencies.json change for final packaging; executable code and tests remain byte-identical. The accompanying public submission note records the exact final full standard run and additional comparisons. Local mixed runs use real DF53.16/DFHack53.16-r2 with canned replies, not hosted GLM or real pricing.

## Validation and attribution

Run from submission: PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests. The repository's normal yukon setup/run track harness-glm-5-3-flash commands provide the native full-suite check. Docker uses the inherited pinned Python image and entrypoint; no game binary, private save reader, stock injector, extra provider credential or alternative model is included.

One dependency names the complete published7dec source, retaining its material upstream lineage. The accompanying note carries the historical author/feature credits. The own new contribution is the bridge between controller housing reservations and model farm actions plus its10decision checks. A separate own195-check late-livestock experiment was rejected after OP2021 fell73.4versus87.5 with food supply.737; its peer879ec09f timing idea is not imported here. Three unscored meal-subtype probes produced only biscuits despite accepted stew/roast subtypes and are also absent.

Fishing/drowning and other inherited game risks remain unresolved. No-death repeats, adequate furniture, accepted orders or normal exits alone do not establish safety, full supply, an official score or promotion.
