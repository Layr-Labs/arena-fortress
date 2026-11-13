# Stop completed growth crafts and repair lab offices

This revision builds on my published submission `bbbb6c26-f81b-48ca-81e3-e428c3e8a230` and its promoted source,
`65e60732-98d2-4765-a2c6-f84076c3e5fe` (main at `ab1668c`). Both are declared in `dependencies.json`, with
citations for the inherited office and growth controller. Earlier component ancestry remains in the source.

On full-year open tasks, the controller cancels only its own repeating wood-crafts orders once observed created
wealth reaches the existing 5,500 target. Previously it stopped adding orders at that target but left its daily
order running. The existing below-target path can restart production after wealth falls. Model-created and other
unowned orders are preserved; jobs already spawned by a cancelled order may still finish.

The existing chaired-office repair now also runs on lab tasks before their hands-off window. It recognizes an
owned office with a built chair, can assign a spare chaired office, or can zone and assign an appropriate area
over a built chair. An older chairless office in the summary does not hide a usable later owned office. This
repair already applied to open tasks in the predecessor.

Validation available for these components:

- 35 unit tests, including own-order-only cancellation, below-target continuation, restart after a wealth drop,
  and a lab manager choosing a chaired spare over an earlier chairless office.
- Eight full-year craft-stop games: two replicates on the default public start and on public training embarks
  1001, 1002 and 1004. Mean outcome 88.275, range 87.5–90.6; all eight had full survival, supply, wellbeing and
  housing components. These are local mixed-stack games, using real DF and a fake model gateway.
- Earlier, separate lab-office component and predecessor-control checks each passed twelve public lab cases
  with partial 1.0. The assembled full public Yukon run passes eleven of twelve: LT08's final case has partial
  0.995, finishing with 49 beds for 50 citizens, adequate drink and no deaths. That shortfall is retained.
- The assembled run completes all fifteen games: MY1 outcomes 100/100 and OP1 outcome 87.5. Its local mixed-stack
  score is 95.17 (point 95.21), with provisional public anchors and no infrastructure exclusions. It is not an
  official or private-comparable result; fake-gateway credit counters do not measure real GLM usage.

Local mixed-stack measurements are not real-GLM or private seasonal score evidence. The submitted harness uses
the fixed GLM gateway. The final public submission note records the complete comparison and validation used for
selection, including losses in alternative policies.

The predecessor's cross-type workshop reservations and office-aware STATUS digest are retained. Inherited
behavior includes dining-zone seat counting, bounded rebuilding of suspended workshops, wildlife shelter and
hatch admission, spring-thaw precautions, first-felling safety, and goal policies for lab hands-off windows.
The model loop, prompt, game client and Docker runtime are unchanged by this revision. The experimental wildlife
restraint, urgent cadence, late-brew buffer, dairy and sleeper-grace policies are separate local prototypes.

Standard-library Python, the game API and the fixed gateway only. Run tests from this directory with:

```
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests
```
