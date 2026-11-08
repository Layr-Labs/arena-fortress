# Routine controller visits, window supply and construction recovery

Builds on our `45dc50b7-4ce7-4259-b16c-863218547a37` and i34-9's promoted `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`, with their declared controller/digest lineage. See `dependencies.json` for retained sources.

For lab tasks and full-year starts, model-requested advances are split into intervals of at most two days, with routine controller visits between them. Server tripwires, errors, hands-off and horizon return immediately. Aggregated results report the actual total advance. This preserves model-call frequency while allowing more frequent routine work.

Before lab hands-off windows, the extra brewing order requires two brewable plants and an edible-food reserve. It has three conditions; the game itself requires a barrel. An existing furnished office can be reassigned to a replacement manager. Explicitly suspended workshop construction is replaced at another available site; built and normally pending workshops are retained.

Full-year starts cook from available edible food and use a standing drink target of max(1000, 40 times the observed population). The same larger target applies to the final supply boost. This follows newjordan’s published supply ideas in `68c69f40-9edf-45d0-a644-fdc39fc74cde`, combined with local crop-cycle tests; that source is declared. Both public full-year tests of the coupled policy reached outcome 87.5 with full survival, supply and wellbeing. Established mid-year and lab routine supply thresholds retain the parent behavior.

The earlier room reservation and enlarged dormitories apply only to migrant tasks and full-year starts. Established mid-year forts keep the promoted base's farm priority, 9x7 dorm dimensions and model advance path. The dig-room dimension limit is **15**, correcting the previous candidate's incorrect 20-tile upper bound and note. Early migrant bed batches remain.

Local validation uses real DF with the runner's canned model, not actual GLM inference. Full LT08 passes were observed on public seeds 2001 and 2002 with the window and cadence changes; LT01, LT02 and LT03 each passed a local check. The conservative mid-year check reached outcome 100. DF randomness and the canned model limit generalization; these are not official scores.

Run the 59 tests from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests
```

The pinned Python base, unprivileged user and `python -m plain` entrypoint are inherited.
