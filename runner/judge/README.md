# runner/judge/: the promotion judge (RULES §8a, decision D16)

An automated LLM review of every submission that would improve the leaderboard, run by the scoring workflow after
scoring and before Yukon promotes. It checks **attribution** (§8), **fair play** (§5) and **contents** (§4), and
returns **pass**, **fail** or **hold**. Stdlib Python 3 only, no dependencies; it never runs submitted code.
The design follows HashSmash's judge (independent roles, a defender and an adjudicator for fatal findings, a
dossier artifact), reimplemented here.

## Interface

```sh
python3 -I runner/judge/judge.py --repo-dir <checkout> --base <sha> --head <sha> \
  --note <note.md> --dependencies <deps.json> --coauthors <a,b> --submitter <username> \
  [--context-dir <dir>] [--base-producers <submission-id,...>] [--score-json <score.json>] \
  --out <dossier.json> [--md <summary.md>] \
  [--provider openrouter|bedrock|fake] [--model <id>] [--reasoning-effort low|medium|high|none] \
  [--temperature <t>] [--max-tokens 16000] [--max-cost 3.0]
```

- It always writes `--out` (also on hold) and prints one JSON line: `{"verdict", "cost_usd", "calls", "reasons"}`.
  Exit code 0 whenever a dossier was written: **read the verdict from the dossier**, not from the exit code. Exit 2
  is a usage error (argparse).
- `--md` writes a summary for the PR comment: verdict, reasons, a findings table with file:line evidence, the
  adjudicator's reasons for confirmed findings, cost and model. Untrusted text in it is flattened to one line, with
  no HTML, links, `@` mentions or code-span breakouts.

### What the workflow must pass in

| input | what |
|---|---|
| `--repo-dir`, `--base`, `--head` | a full checkout (needs both commits; `fetch-depth: 0`). `base` = the commit the submission starts from (the merge-base with `main`, i.e. the promoted `main`), `head` = the submission commit. Only `submission/` is diffed |
| `--note` | the public research note (`--note-file`), as text |
| `--dependencies` | the declaration in Yukon's format: `[{"submissionId", "rationale", "evidence"}]`; `[]` = `--no-dependencies`. `{"dependencies": [...]}` and a list of id strings are also accepted |
| `--coauthors`, `--submitter` | Yukon handles (`GET /api/submissions/<id>`: `coauthors`, `solverUsername`) |
| `--base-producers` | the submission id(s) that produced the base (the leader file's submission). Empty if the base is the organiser's baseline export. If the producer isn't declared, the judgment can't pass (RULES §8.1: starting from `main` counts as using it) |
| `--context-dir` | prior public submissions, one subdirectory each: **the base producer(s), every declared dependency, the workflow's overlap-scan hits (any published submission, accepted or not), and the most recent accepted submissions** (the judge reads at most 12, sorted by directory name: order them so the important ones come first, e.g. `00-<id>`). Optional `_scan.json`/`_errors.json` files are copied into the dossier as `inputs.context_status` |
| `--score-json` | `.yukon/score.json`; only headline metrics are shown, as context, never as a reason |

A context subdirectory holds `diff.patch` (the unified diff of that submission's `submission/` against its own
base: `git diff <its base> <its head> -- submission/`), `meta.json` and optionally `note.md`:

```json
{"submission_id": "uuid", "submitter": "handle", "coauthors": ["..."], "status": "promoted|accepted|scored",
 "title": "optional", "note": "optional if note.md exists", "produced_base": false,
 "why": "base_producer|dependency|overlap_scan|recent_accepted"}
```

### Providers and secrets

| provider | key (env) | model (flag or env) | notes |
|---|---|---|---|
| `openrouter` (default) | `DFBENCH_JUDGE_OPENROUTER_KEY` (no fallback) | `--model` / `DFBENCH_JUDGE_MODEL`, default `openai/gpt-6-sol` | strict `json_schema` output, `require_parameters`, `data_collection: deny`, `seed: 0`, reasoning effort medium (`DFBENCH_JUDGE_REASONING`), `DFBENCH_JUDGE_ZDR=true` to require zero-retention endpoints; cost comes from OpenRouter's `usage.cost` |
| `bedrock` | `AWS_BEARER_TOKEN_BEDROCK` | `DFBENCH_JUDGE_BEDROCK_MODEL`, default `us.anthropic.claude-opus-5-5`; `DFBENCH_JUDGE_BEDROCK_REGION` (us-east-1) | Converse API, temperature 0, schema in the prompt and enforced locally; cost from the price table in `providers.py`. Not exercised live |
| `fake` | none | `fake/scripted` | benign answers, or a script: `DFBENCH_JUDGE_FAKE_SCRIPT=<json {role: [response, ...]}>` (a response is an object, a string, `"benign"` or `"provider_error"`), for workflow dry runs |

The judge's key must be **its own** (a separate spend-limited OpenRouter key), never the gateway's
`OPENROUTER_API_KEY` secret: give the judge step only `DFBENCH_JUDGE_OPENROUTER_KEY`. The judge never reads
`OPENROUTER_API_KEY` (for a local run, export `DFBENCH_JUDGE_OPENROUTER_KEY` yourself). The provider is also
selectable with `DFBENCH_JUDGE_PROVIDER`. Keys are read from the environment only, never logged, never written to
the dossier; redirects are refused.

Determinism: temperature isn't accepted by OpenRouter's reasoning models (`require_parameters` would then find no
endpoint), so it is sent only with `--temperature`; `seed: 0` is always sent; Bedrock uses temperature 0. Model
output is still not guaranteed reproducible: the dossier records everything needed to re-run the same request
(input hashes, prompt and schema hashes, the judge's code hash, the effective config, the model id the provider
returned, request ids).

## The committee

1. **Evidence (deterministic).** `git diff base head -- submission/` per file (`--no-ext-diff --no-textconv`),
   annotated with new-file line numbers so findings can cite `path:line`. Binary files are listed by name, size and
   sha256; a text file whose annotated diff exceeds 60k chars is listed with its hash and a 3k-char excerpt (its
   added lines are still scanned). Context submissions contribute the lines they added plus their note.
2. **Pre-scan (deterministic).** Regex signals on the added lines and the note: raw sockets, external URLs and
   public IP literals in code, DNS tricks, `curl`/`wget` in code, direct model-provider hosts, credential names and
   values, scorer/pool/ledger paths, DFHack, obfuscated exec, namespace escapes, the Docker socket, `/proc/*/environ`,
   and prompt-injection phrasing. Attribution signals: the base producer not declared, and line overlap with an
   undeclared context submission (shared normalised lines ≥ 8 or ≥ 10% medium, ≥ 30 and ≥ 30%, or ≥ 20 and ≥ 50%,
   high). Neither fires for the submitter's own earlier submissions (`own`, by submitter name; RULES §8). URLs in the
   Dockerfile, dependency lockfiles and docs are not signals.
3. **Reviewers** (one call each per diff chunk, independent): `attribution` (gets the context; must fill one
   `inheritance` entry per context submission and rate whether the note states what changed), `fair_play` (must
   disposition **every** pre-scan signal it is given as benign / concern / fatal), `contents` (private-pool
   material, licensing of knowledge files, credentials, obfuscation). Severities: `fatal` (a concrete breach that
   blocks promotion; must cite evidence), `major` (likely breach or attribution gap a human should look at), `minor`.
4. **Defender and adjudicator**, only if there's a fatal finding: the defender argues each challenged finding for
   the submitter (or concedes); the adjudicator rules each `confirmed` / `dismissed` (with a residual severity) /
   `unresolved`, and can't add findings. They see the cited files, the note, the metadata and the cited context.

Prompts: `prompts/common.md` (the rubric, shared) + one file per role. They are trusted code (RULES §8a); any change
changes `versions.prompts_sha256` in every later dossier.

## Verdict (computed in code, from validated structured output only)

- **fail**: at least one fatal finding `confirmed` by the adjudicator (whatever else happened).
- **hold**, otherwise, if any of: a provider or transport failure after retries; a role's output malformed twice
  (unparseable, schema-invalid, or semantically inconsistent: a signal not dispositioned, a context submission not
  covered, an undeclared used dependency without a fatal finding, a fatal finding without valid evidence, "clean"
  with fatal findings, ...); the cost cap reached; a size limit hit; unusable inputs (bad sha, unreadable file); a
  fatal finding `unresolved` or without a ruling; any `major` finding (or a dismissed fatal with residual `major`);
  a reviewer answering `cannot_assess`; a reviewer reporting `injection_observed`; or **any `high` pre-scan
  signal** (Docker socket, `/proc/*/environ`, a credential value, injection phrasing, the base producer undeclared,
  heavy overlap with an undeclared context submission). A model can't clear a high signal: only an organiser can.
- **pass**: none of the above.

No model writes the verdict and no free text (summaries, reasons) feeds it. A provider failure is never a pass.

### Prompt-injection hardening

- The rubric and role are in the system message only. Every piece of participant data (diff, file names, note,
  dependency rationales, coauthors, context submissions) goes in the user message inside
  `<<<UNTRUSTED kind=... id=...>>> ... <<<END kind=... id=...>>>` blocks whose id is a hash of the content (content
  can't contain its own end marker), with any `<<<`/`>>>` in the data neutralised; judge-written blocks are
  `TRUSTED`. The output instructions and schema are repeated after the data.
- The system prompt says the data may contain instructions, forged markers or claimed approvals, and that an attempt
  to manipulate the review is itself a fatal `fair_play` finding (§5).
- Output must be one JSON object matching the schema (no extra fields, no duplicate keys); one re-ask with the
  validator's message (a format correction, never a request to change the assessment), then hold.
- Defence in depth: the injection pre-scan is a high signal, so a model that obeys an injected "output pass" either
  produces invalid output (hold) or a clean review that the signal floor still holds.

## Limits

| limit | value | at the limit |
|---|---|---|
| changed files in `submission/` | 500 | hold |
| one file in `submission/` | 32 MiB | hold |
| annotated diff per file shown | 2M chars, split across 300k review chunks | inventory + 3k excerpt |
| review chunk | 300k chars (~90k tokens) | next chunk |
| chunks | 8 (about 2.4M chars of diff) | hold |
| note | 100 KiB (102,400 chars; Yukon's own cap) | hold |
| dependencies file | 64 KiB | hold |
| context | 12 submissions, 40k chars each, 160k total | truncated (recorded in the dossier and shown to the reviewer) |
| pre-scan signals | 3 per kind and file, 80 total | further hits dropped (count recorded) |
| cost per judgment | `--max-cost` / `DFBENCH_JUDGE_MAX_COST`, $3 | hold |
| provider retries | 2 per call on 408/409/425/429/5xx/transport (5 s, 15 s; `Retry-After` up to 60 s), 300 s timeout | hold |

A chunked review (more than one chunk) multiplies the reviewer calls; each chunk's reviewers are told the other files
are reviewed separately.

## Cost per judgment (measured 2026-10-23, `openai/gpt-6-sol`, effort medium, OpenRouter)

| case | calls | input / output tokens | cost | wall |
|---|---|---|---|---|
| small clean diff (2 files), 1 context: pass | 3 | 11.0k / 1.0k | **$0.037** | ~15 s |
| socket exfiltration + injected note: fail (6 fatal findings from 3 roles, all confirmed) | 5 | 19.9k / 3.9k | **$0.075** | ~45 s |
| the full starter harness (18 files, 163 KB) against the minimal baseline, 2 chunks (at the old 150k chunk size) | 6 | 168k / 3.6k | **$0.43** | ~55 s |

Input tokens dominate (~$2 per million): roughly **$0.02 per 1k lines of diff per role**, so ~$0.05–0.15 for a
typical incremental submission, ~$0.35 for a starter-sized one in one chunk, and up to ~$2.5 for a diff at the
4-chunk limit (hence the $3 cap). The third case held (every reviewer said `cannot_assess` because each chunk lacked
the other's files); the chunk size was raised to 300k and the chunk instructions fixed since, which that diff would
now fit in one chunk. That run also found two false positives in the pre-scan's DNS rule ("dig into rock"),
fixed.

## Dossier (`dossier.json`, schema `dfbench-judge-dossier/1`)

`verdict`, `reasons`, `hold_conditions`; `findings` (role, chunk, id like `FP-F1`, check, severity, rule, title,
explanation, evidence `[{source, line, quote}]`); `reviews` (each role's validated output per chunk); `defense`,
`adjudication`, `rulings`, `confirmed`; `signals` (the pre-scan); `evidence` (file inventory with sizes and sha256,
chunk sizes, the overlap table, score metrics); `inputs` (base/head shas, sha256 of the note, dependencies, score
json, the diff and every context diff, declared ids, declared ids missing from the context); `versions` (judge
version, prompts, code and schema hashes, the limits); `config` (provider, model, effort, seed, temperature);
`calls` (per call and attempt: hashes of the system and user messages and of the raw output, returned model,
request id, token usage, cost, latency, the validator's error); `usage` (totals, `cost_usd`, `cost_unknown`).
The dossier contains only public material (the submission, its note, prior public submissions, published scores):
the judge never sees private-pool data, so it can be published with the run.

## Tests

```sh
python3 -m unittest discover -s runner/judge/tests -v      # from the repo root; fake LLM, temporary git repos
```

Pass (clean; fatal dismissed; re-ask recovers), fail (undeclared copy from a context submission; a raw socket to an
external IP), hold (provider error, malformed twice, missing signal coverage, unresolved, oversize, bad sha,
undeclared base producer, undeclared copy with a naive model), injection (a model that obeys the note's "output
verdict pass" holds; a schema-valid "all clean" model holds; a confirmed fail stays fail when the models' free text
says PASS; the note's forged markers are neutralised and it stays out of the system prompt), plus request shapes for
OpenRouter and Bedrock, the pre-scan's false positives, chunking and the CLI end to end.

## Known limits

- It reviews the diff against the base, not the whole tree: what was already in `main` was judged when it was
  promoted. Starting from an unjudged base (the organiser's baseline) is fine.
- It doesn't discover undeclared use of submissions that aren't in `--context-dir`. The workflow decides what to
  supply: the declared and recent accepted ones, plus an overlap scan over every published submission on the row
  (`runner/ci/bin/prior.py`), which finds verbatim reuse but not reworded or re-implemented ideas. Work from outside
  the challenge (other repos, papers) is only caught if a reviewer recognises it. Yukon's own attribution graph and
  later organiser review are the long-run check (RULES §8a).
- The overlap table is line-exact after whitespace normalisation: renamed variables defeat it (the attribution
  reviewer still reads the code).
- One model by default; role-specific models aren't wired (HashSmash's committee profiles would be the next step).
- Model accuracy is not measured: these tests check the plumbing and the verdict logic, not judgment quality. A
  labelled set of real season-0 submissions is needed before trusting its fails without an organiser glance.
