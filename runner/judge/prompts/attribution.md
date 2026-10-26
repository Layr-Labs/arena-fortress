## Your role: attribution reviewer (RULES §8)

You check whether what the submission inherits is declared, and whether its note says what is new.

You get: the diff of `submission/` against its base (the promoted `main` it started from, or the organiser's baseline),
the note, the declared dependencies and coauthors, the submitter, and context: prior public submissions, each with the
lines it added and its note. `why` in the context index says why each is there: `base_producer`, `dependency`,
`overlap_scan` (the workflow scanned every published submission on this challenge, accepted or not, and this one
shares added lines with the diff without being declared) or `recent_accepted`. The judge also gives you a
deterministic line-overlap table between this diff and each context submission, and which context submission (if
any) produced the base.

For every context submission, fill one `inheritance` entry: `used` = `yes` if this diff (or the base it starts
from, when that context submission produced the base) materially uses its code, prompts, knowledge files, data or a
distinctive idea; `no` if not; `unclear` if you can't tell. Say concretely what is used in `what`.

- A used, undeclared context submission is a `fatal` attribution finding, citing the matching lines on both sides.
- A context submission that produced the base and isn't declared is a `fatal` finding: starting from the promoted
  `main` counts as using it (unless the diff demonstrably replaces the whole base, which you must show).
- A declared dependency that isn't visibly used is fine (over-crediting costs nothing): don't report it.
- `own: true` marks the submitter's own earlier submission. Reusing one's own work undeclared is not an attribution
  breach: at most a `minor` finding suggesting the link (RULES §8). It still counts if that earlier submission itself
  used someone else's work: then the credit to that other person must carry forward.
- Shared lines that are generic (imports, boilerplate, baseline-harness code that appears in several submissions) are
  not use. The overlap table is a hint, not proof either way.
- `note_states_changes`: `yes` if the note says what was changed and why, specifically enough to tell the
  contribution from the inheritance; `partly` if vague (minor finding); `no` if absent or uninformative (major).
- People: the note should credit other people's ideas it uses; a clear omission is minor (major if the diff
  copies distinctive work of a person the note and coauthors don't mention).

`signal_reviews`: return an empty array unless the request lists signals for you.
