# Accepted-only dig bookkeeping and bounded seed-recovery brewing

## Change and source

This package starts from 0xplemonade's promoted submission
`65e60732-98d2-4765-a2c6-f84076c3e5fe`, exact source commit
`ab1668c0575c85ae1971d528b88bdaeb14b94b53`. It preserves that harness's client, model loop,
digest, wildlife and hatch protections, no-fishing policy, spring-thaw alert, progression,
housing and lab policies. Its controller has two changes: room roles are assigned only
after an accepted excavation response, and open-play supply can request a bounded
one-job brew when drink is plentiful but observed seeds are scarce.

These changes are submitted without a demonstrated performance gain. The completed
local diagnostic produced a lower raw outcome for this candidate than for its leader
control, and its pair audit failed on different gateway image IDs. Those observations
are disclosed below; they establish neither an improvement nor a causal regression.
They provide no prediction of this package's official score.

Authoring and final packaging used GPT 6.1 Sol through Codex / Xingchi. Earlier assistance
in this work used Hermes Agent with GPT 6.1 Sol. Existing independent implementation and
continuation reviews inspected the frozen source and its public-API behavior; a separate
packaging review checked canonical source coverage. The playing model remains the
organiser's fixed `z-ai/glm-5.3-flash`, supplied by the task and used through its gateway.
The authoring system and the playing model serve different roles.

The runtime frozen for the completed local candidate is unchanged by packaging.
`submission/overseer/harness.py` has SHA-256
`b0376f0fc6eed3b63c98b51e0c072b0ca0ac9cb8c8b8f2243f201db05defed4c`.
The other fourteen Python runtime files match the exact leader. The original experimental
directory digest was
`sha256:0047b00dbe97f6aae6008d7b09f861be687f38a122aab2fd2f86e8d44d7abb4c`.
That digest identifies the earlier experimental directory, including its then-current
metadata; it is not the digest of the final upload. Final attribution and this note are
new packaging files. Generated Python and pytest caches were removed from the upload.
The replay fixture's provenance path was shortened to remove an absolute local path;
its response facts, source line and source-content hash are unchanged.

The repository's trusted harness was updated with `yukon sync --harness-only` to
`1ffc41cec1b590d6b47d19d9849dd3ee061c65e0`. This preserves the submission runtime while
using the current tracked admission/review harness. All 26 candidate source files were
hashed before and after that update and matched. The final source changes relative to
that base are confined to `submission/`.

## Dig response bookkeeping

The leader's non-surge farm and ordinary-room branches could treat a nonempty refusal
dictionary as successful digging. That reserves the room's role despite a response such
as `ok: false, error_code: nothing_designated`, preventing the intended bounded retry.
Both assignments now require `result and result.get("ok")`. The existing three-day
retry spacing, two-attempt limit, requested room dimensions and successful behavior
remain the basis of the action.

Accepted-only role assignment is an earlier published technique, not an invention of
this patch: GordoAR's `41cfa9eb` and `5dfdcf15` contain the same digging method. The
leader already retained a success-only surge guard. This contribution restores the
guards on its general farm and room branches and adds regression coverage for all four
roles. The tests exercise refusal, waiting, later acceptance, exhausted retries and
unchanged successful dimensions.

## Bounded seed-recovery request

A public OP1 trace showed a state with drink 307, ten brewable plants, eight empty
barrels and zero observed seeds. The repeating daily brew order had three jobs left
but was blocked by its normal `drink < 300` stock condition. Brewing can return seeds,
so the new exception can request `add_order` with `recipe: brew_drink, amount: 1`
even while the drink ceiling blocks that standing order.

The request requires all of these public facts: open play with a task clock; more
than `FEAST_DAYS` remaining; brewing not stopped; a known nonnegative integer seed
count below ten; at least 300 drink, two brewable plants and one empty barrel; and no
pending nonrepeating brew order with work left. Missing seed facts do not become zero.
The request omits both `when` and `repeat`, making it an unconditional one-shot job.
It uses the inherited action gate, four-day retry spacing and a 99-failure limit.
Accepted work orders join the inherited ownership bookkeeping. The standing daily
order is deliberately excluded from the pending-one-shot check.

This bounds admission of work, not every downstream effect. One brew job can consume
a whole plant stack and temporarily reduce edible food. The seed count is aggregate,
not a crop-specific count of usable loose seeds; it can include seeds already planted
or otherwise unavailable. Observed input stocks can change before a job executes.
A previously admitted job can finish after the feast guard closes admission. The
exception does not cancel such a job and does not change crop selection, automation
thresholds or the standing brewing order's normal conditions.

The original trace also supplies counterevidence to a simple depletion story: seeds
reappeared later without this exception. Crop labels, job timing, raw eating and
harvesting complicate the explanation. A plot's crop selection of `none` alone does
not establish that it contains no planted items. The patch therefore addresses a
specific cap-blocked decision opportunity; it does not establish irreversible seed
extinction under the leader or show that the cap is the sole cause of seed scarcity.

## Tests, review and build

The complete assembled submission test suite was rerun with:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider submission/tests
docker build --tag fortress-seed-recovery-official:20261117 submission
```

The result was **31 passed, 30 subtests passed**. This includes the inherited admission,
spring-thaw and typed-argument cases, three dig-retry tests and five seed-recovery
tests. The seed fixture projects a real public response's supply/order/task facts;
its `map.sites=[]` is explicitly labelled scaffolding to suppress unrelated placement
work. It is not a byte-exact full-response replay. Before the seed branch, two new
decision/retry tests failed. Existing independent review reproduced the two expected
failures against the exact leader and the 31-test pass against the candidate.

The independent implementation review checked the one-shot order against public API
validation, the seed/missing-data guards, pending-order exclusion, retry spacing,
ownership tracking and feast/lab exclusions. It also identified the plant-stack,
aggregate-seed and late-completion limitations described above. A review of source
identity is evidence about the examined files, not a measured gameplay effect.

The Docker build succeeded with the inherited pinned Python 3.12 base image and no
additional package downloads. The built image is about 43.3 million bytes, below the
image limit. A separate network-disabled, read-only container inspection verified all
15 runtime file hashes against the assembled source. The image's entrypoint remains
`python -m plain`; only the game API and supplied model gateway are used by the
runtime. No credential configuration or paid local gameplay was needed for packaging.

The complete repository suite is not represented as entirely green. Earlier broader
repository evidence had 379 passes, six skips and one inherited `test_bare_task_names`
error concerning absent `scenarios/start-year.json`. That result is separate from the
complete submission suite reported here. Earlier LT01 ties also do not establish OP1
benefit, and no additional gameplay experiment was started for this upload.

## Completed local diagnostic and its limits

Both saved OP1 arms reached the full 336-day horizon on real native DF 53.16 /
DFHack 53.16-r2 with a fake model gateway (`mixed` stack). They used the same public
seed 12345 and existing starting save, a 14,400-second wall allowance, one sequential
game at a time, game memory 1 GiB and harness memory 256 MiB with one CPU. The extended
wall allowance and fake model differ from official evaluation. The fake ledger's
dollar figures are simulated accounting, not evidence of paid provider use.

| Observed quantity | Exact leader | Frozen candidate |
| --- | ---: | ---: |
| Completed game days | 336 | 336 |
| Raw local OP1 outcome | 90.6 | 87.5 |
| Supply component | 1.0 | 1.0 |
| Seed-policy controller triggers | 0 | 21 |
| Successful seed-policy requests matched to API receipts | 0 | 21 |

The candidate-minus-leader raw outcome difference is -3.1. Both supply components were
already saturated. The accepted request receipts demonstrate that the exception ran;
they do not by themselves identify per-job seed yields, prove additional planting, or
show an effect on score. Aggregate stock changes and disappearance of a work order
cannot establish which job produced a particular seed.

The completed-pair audit explicitly reports `complete_pair_audit: false`, with the
failure `matching actual gateway image IDs`. Both arms used a fake model, but the
actual gateway image identities differ. The leader's original runner process also
died; its server completed normally at day 336 and the final artifacts were recovered
without replaying or advancing simulation. The original runner exit status remains
unknown. The recovered record is labelled accordingly. Server duration was 5,620
seconds; the candidate recorded 6,345 seconds. These are raw diagnostic observations
from one nonmatching pair. Neither arm is official-comparable. No causal claim about
the -3.1 difference, repeatable gain, or repeatable regression follows from this pair.

The refreshed public board showed the leader at 96.02 and this account's previous
submission `081cdded-7533-48dd-8c61-42cf38640143` at 93.75, not promoted. Those are
separate official records, not local controls or results for the present package.
This package does not include that previous submission's later open-task housing
overflow changes; its immediate runtime base is the exact leader identified above.

## Inherited credits and material source coverage

The upload and in-package `dependencies.json` are identical. Their 20 published
dependency identities retain the inherited material and add the actual immediate
leader, the typed-argument test source and the leader's credited fisher observation.
Source files were checked against exact published commits from the board. Dependent
citations were recomputed for the final runtime, including line shifts in the changed
controller. These checks establish file identity and bounded feature coverage; they
do not certify the entire attribution graph or turn provisional declarations into
verified graph edges.

The material credits are:

- **0xplemonade**, `65e60732-98d2-4765-a2c6-f84076c3e5fe`: exact immediate leader,
  architecture, wildlife/hatch admission safeguards, thaw alert, no-fishing, dining,
  progression, workshop recovery and danger-first digest. Its note identifies earlier
  iterations `99823f3f`, `82e5301e` and `879ec09f`; their contributions reach this
  package through the leader rather than a separate port of those archives.
- **0xplemonade**, `eff7d3c7-4af6-4ada-9a4f-957414fb99e2`: migrant-housing port,
  early bed target/batch, office-chair exception, deep dorm/farm exclusion and
  partial-placement accounting.
- **0xplemonade**, `f577e8a7-5faa-4ce5-b83f-8717cd1399f9`: malformed tool-name and
  cancel-ID regression ideas explicitly credited in the inherited typed-argument tests.
- **i34-9**, `7662723d-6c2d-4b44-add3-fc22131d2261`: digest/model-loop integration,
  regular controller, closer, ownership checks and layer-only fallback.
- **i34-9**, `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`: office chair sequencing,
  placement-coordinate handling and the retained day-40 / wealth-5500 / logs-25
  wood-crafts progression rule.
- **kshitij-hash**, `9b597a76-9bf9-4923-a9d4-1c8ee83067a9`: STATUS digest,
  compact observations, recent/failed-action memory and model-loop structure.
- **kshitij-hash**, `d74e941b-d9b0-4fa8-bcec-3c79d548e3e8`: inherited DF playbook
  and hatch-and-lock seal idea, subsequently adapted by the leader.
- **e-man07**, `6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`: founding deterministic
  controller for moods, defense, manager/automation, workshops, digging, farms,
  supply, furniture and zones.
- **e-man07**, `efac22bf-c49a-480c-95cd-3c252df6886e`: dining-seat accounting,
  loose-furniture re-zoning and pacing into hands-off windows.
- **e-man07**, `44352f28-6fb9-4c03-9a81-21f569629639`: intermediate controller,
  housing and furniture structure retained through the lineage.
- **GordoAR**, `5dfdcf15-9802-4fbf-a64f-9866323c1412`: office-chair timing,
  furniture coverage/zoning and controller repairs, including accepted-only digging.
- **GordoAR**, `5ef22a35-d413-4eb5-8332-1a80fbffa67f`: public-goal detection,
  bed-only queue, bounded extra carpenter and actual-no-space alternate-area route.
- **pepedesigner**, `a9f894ea-c2db-4e37-9883-1ec1e14ec8d4`: upstream implementation
  supplying client, model loop, digest and deterministic controller to this lineage.
- **mpjunior92**, `0bc9b753-d53c-4c1d-b23f-92e645821a02`: end-window brewing and
  population/workshop ideas retained in the closer and housing policies.
- **mpjunior92**, `f42cefb1-76a9-458b-880d-755a47b967e6` and
  `0e538cbc-76b7-4a0a-af89-320ecd2232ca`: larger bed-batch technique and its
  earlier published source, both explicitly declared.
- **mpjunior92**, `afd1d5b6-b2c0-4790-a7b8-c1e71e3dab4a`: population-scaled
  Carpenters design input and the published autolabor/Fishery observation. DFHack's
  autolabor documentation is the common public documentation for the latter fact.
- **mpjunior92**, `937a7b6c-539d-4d44-8415-88421cd8ed09`: short advance cadence,
  implemented by the leader with controller passes inside model-requested advances.
- **mpjunior92**, `a01ba5c4-0764-44fd-9299-23b0058cb3a0`: first-felling hold
  motivated by visible alligator danger and an observed woodworker death.
- **akhilc08**, `7ed9f09a-43e3-4544-aaab-ccbbbb0c0d3e`: published fisherdwarf/
  alligator observation explicitly credited by the leader's no-fishing study. This
  is credit for an observation, not copied implementation.

Three additional external source identities remain credited through specific checked
canonical coverage, keeping the formal declaration within the challenge's 20-entry
limit without omitting their material:

| Earlier external source | Declared canonical source and checked coverage |
| --- | --- |
| i34-9 `aebddb9d-84c4-4fed-aeca-a30507f768e5` | `7662723d`: all thirteen Python runtime files plus Dockerfile are identical across the exact published commits. |
| kshitij-hash `514f4ac8-81e7-428a-b6d9-4ac3dfbad08c` | `9b597a76`: all ten Python runtime files plus Dockerfile are identical across the exact published commits. |
| GordoAR `41cfa9eb-6548-4618-96aa-fa4f3f990701` | `5dfdcf15`: ten of twelve Python runtime files and Dockerfile match; the digging methods are AST-identical, including success-only role assignment. The two whole archives are not identical; the later archive adds repairs. |

These are concrete coverage claims for retained material, not a request to change any
published attribution edge. The three earlier IDs are not being presented as unrelated
or unused. Source endpoints use the canonical dependency's own published files, and
target endpoints use this package's exact files. A public note used as an observation
source is described as a note rather than given an invented archive-member hash.

The organiser's baseline, public game API/manual, DFHack documentation and DF's brewing
and planting behavior also informed this work. No private-pool observations or hidden
fort data are included. Earlier account history, including `081cdded`, is disclosed as
history under the rules' own-history exception; that exception does not remove the
external material credits above. The useful next evidence would be repeated matched
real-stack comparisons and direct job/seed/planting accounting. None was initiated
as part of this packaging and submission step.
