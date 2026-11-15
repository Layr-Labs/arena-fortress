# Queue an uncovered migrant bed shortfall before the current order finishes

This candidate starts from our unpublished, committed172 model-input schema-fix bank on promoted65e. That bank is negative and unselected: its one standard15 run had11/12 full lab passes, no deaths, and LT08-2 partial0.9811 with49placed beds for53citizens. It is not treated as successful validation or declared under a fabricated submission ID. The direct published65e parent and18material ancestors remain declared. Our own units-list labor parser repair stays unchanged in both new comparison arms.

The new world-policy change is one early finite bed pipeline top-up, called after the existing supply planner. It applies only when all three existing explicit goal flags hold (migrant surge, placed-beds-first, hands-off lab), the actual integer hands-off clock is above the existing14-day preparation interval, and known integer bed stock plus all known finite pending bed-order quantities cannot cover the citizens already present. It uses the original target max(citizens+12,50), subtracts current stock and pending quantities, and requests at most30beds. It never raises SURGE_BEDS or changes the normal planner. Unknown/malformed stock/order/clock values and any repeating bed order suppress the helper. A regular bed order or closing order already queued in the same pass suppresses it too. At most one additional order is accepted per task; ordinary refusal retries remain bounded.

Motivation is actual normal API timing, not an assumed production formula. All three172LT08 ledgers were screened: early projected49beds cannot cover50citizens on public2002 or53on2005, while2001 has no such context. In the failed2005game, the initial30-bed order is still pending after migration. The default planner waits until it completes on day32 before queuing16more. The manager office already has a chair, but that new order remains unvalidated through day37, validates at38, and production completes after the hands-off boundary39. AtH there are65beditems but only49placed. This does not prove an earlier order will be validated or completed in time, that labor/wood is available, or that other supply clauses will be unharmed. A higher stock target alone would leave the existing pending-order block, so it is not changed here.

The entire Plain harness/run/user-message, model client/options, prompt, digest, all open-play rules and beast module are byte-identical to172. No extra query, model bypass, model substitution, new site class, private-pool access, runner/scorer/snapshot mutation, or tuning to new world seeds is introduced. The local canned gateway is not real GLM quality or spend. The42unit tests include31inherited schema/base tests plus11focused top-up tests. A new prospective fixed native comparison is still required; no173game has run and no173source is installed, selected or submitted. Earlier negative172/170 studies remain separate and cannot be reclassified or pooled into utility.

---

Historical172 preparation README below is retained for provenance. Its pre-native172 statements describe that earlier preparation and are superseded by the completed negative172 validation described above.

# Preserve the existing labor digest for the native citizen-query schema

Fresh promoted65e60732 starting source. Plain.user_message already queries citizen units and passes q.get("result", q) into the STATUS digest. The native result is {"kind":"citizens", "total":..., "units":[...]}. The original _labors reads citizens/result-list/direct-list instead, returns None, and discards the actual labor data. The only runtime edit adds the native units-list shape before the existing legacy forms. All existing labor interpretation, memory, NEXT wording and per-section exception handling remain.

The full Plain harness/run/user_message, fixed model and model client/options, prompt, game API requests, action rules, pacing, seasonal windows and supply policies are unchanged. The model now receives the previously intended labor line and, when warranted, its existing missing-labor guidance. No new query or diagnostic is added to play. No wealth/progression row, wall guard, food floor, office helper, kea, finite brewing, seasonal extension or other peer policy is included.

Offline evidence: EVERY normal citizen query from ALL54 completed actual promoted65e controls in studies162 through168 was checked. All1200 native results previously produce no labor line; repaired parsing exactly equals original labor/NEXT/memory semantics on the identical people placed under its expected legacy key. Four samples in four games report missing core labors. These adaptive public historical contexts are correctness evidence, not new native trials, model actions or score gains. Eight focused regression tests cover native/legacy/malformed shapes, missing labors, memory, nonmutation and integration, alongside23 original tests.

The canned local gateway ignores the content of this added line, so local games cannot establish real GLM decision improvement. Validation must explicitly distinguish own-source full ordered API plus exact model-request SHA replay from a baseline ordered-API/canned-response equivalence check that deliberately allows changed model-request SHA. Positive local score gain is not a sensible gate for a model-input schema repair under a content-insensitive fake gateway. No negative policy study is rescued or pooled, and no private score, fairness approval or real-model benefit is promised. Any native experiment and admission decision need their own prospective protocol and retained outcomes before selection.

Direct material parent65e plus18retained material ancestors with actual published source/range hashes; the new parsing line and regression tests are our own work. No prototype has been uploaded and no native172 game has run.

---

# Dining seats, Hamlet wealth, stuck workshops, a lockdown's shut-out citizens and the spring thaw

The model loop, digest and controller are our PR #115 build (pepedesigner's a9f894ea line, with its
wildlife lockdown, no fishing and first-felling wait). This build changes six things. All but the third and
fifth apply to the long open tasks only (MY1, OP1; lab tasks keep the earlier dining and wealth steps and
have no lockdown):

- Dining seats are counted the way DF lists them (a table or chair inside a dining zone, each once),
  dining furniture goes only where a dining zone covers it or can be made, and tables and chairs are
  ordered against that count. GordoAR's coverage check (5dfdcf15) zones a site after placement.
- Full-year games make wood crafts from day 40 while 25 logs are in stock, until created wealth is
  5,500: i34-9's rule (fa9c13cc) for the Hamlet rank.
- A workshop whose construction DF suspended for three days is built again on another site, at most
  twice per type (a core workshop that is missing altogether takes a free site first): no tool resumes a
  suspended job.
- A citizen on the surface when a wildlife lockdown's hatch is due to lock (asleep, or a migrant who
  arrives later) is let in: the nearest hatch that every hostile and large predator in sight is more than
  60 tiles from stays open, or is opened again; it locks when they are below, when the danger comes nearer,
  or after two days, at most three times a lockdown, and at once if invaders take the alert over. The
  alert stays on throughout.
- The civilian alert holds from the last day of winter to the third day of spring (no hatch is locked):
  ice thaws then, and a woodcrafter idle in a frozen river bed drowned at the thaw in a local full-year
  game. A lockdown can still start meanwhile and takes the alert over; the day above ground owed after a
  full lockdown comes first.
- The STATUS digest starts with ALERT lines for dangers to life (a citizen's death or fight with a large
  predator in the latest reports, a large predator in reach of the wagon, citizens shut out), stating the
  lockdown as the observation shows it. Its threats line says that ordinary wild animals are not listed as
  hostiles, and it no longer suggests steps the harness refuses (autochop while the first felling waits,
  the civilian alert, a Fishery or Butchers on a calm fort).

Declarations and citations are in dependencies.json. Standard-library Python, the game API and the fixed
GLM gateway only. Tests: `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests`.
