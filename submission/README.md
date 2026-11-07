# Managed-window housing and isolated full-year supply


The program starts from i34-9's promoted fa9c13cc controller (commit 2f3abb30, reported LB 91.32). The creator of this successor is mpjunior92 using GPT 6.1 Sol in Codex. The game model remains the task-provided z-ai/glm-5.3-flash through the organiser gateway.

The entrypoint python -m plain runs one model loop with three controller choices:

- An explicit, valid public task.hands_off window selects the managed controller. It retains the bounded office/housing/brewing work from published f42cefb1 and adds uncovered one-shot bed commitments while an older batch remains pending.
- Other runs shorter than a full 336-day year select the exact promoted controller.
- Other runs of at least 336 days select a subclass of that same controller with a higher normal-brew cap only.

Routing reads the public window and horizon, with no fort/seed/name selector. The original controller is copied byte-for-byte into overseer/frontier.py; overseer/year.py contains only the full-year normal-brewing override. Its endgame_supply and food/slaughter methods are inherited unchanged. plain/harness.py retains the promoted prompt, digest, model loop and ownership guards, plus the controller selector and managed advance cap.

For managed populations of at least 25 citizens, the bed queue subtracts current bed items and all remaining one-shot bed jobs from the inherited target. It adds only the positive uncovered quantity, at most 30. Remaining jobs already include in-progress jobs. Repeating or malformed quantities keep conservative behavior. Targets, cancellation policy and global labor assignment are unchanged.

The full-year normal brew cap, evaluated at standing-order creation, is max(600, 30*citizens), with the inherited amount 3, daily repetition, two-plant floor and empty-barrel condition. The original promoted food and slaughter policy is retained. Shared action keys prevent duplicate daily brew creation while an observation is stale.

The split-policy design is credited to e-man07's 1e6cbe5e public note/source. His later ae0c2b7b negative-evidence analysis informed exclusion of optional late slaughter; its causal uncertainty is retained. No peer source code was copied. NOTE.md explains the exact scope, previous official rejection, public measurements, negative experiments, inherited authors and the deferred unpublished canceled source. dependencies.json is the 20-target declaration, with exact code citations and prose evidence for the peer analysis.

The Dockerfile pins Python3.12-slim to the inherited registry digest and copies the unchanged standard-library client plus the plain/controller packages. No model, API credential or game install is embedded in the submission. Runtime URLs, model name, limits and credentials come from the organiser's task contract.

Local verification uses the normal runner described in runner/README.md. Real DF with --stack mixed exercises a canned fake gateway and is not a GLM performance measurement or ranked result. The selected program passed 94 software checks and the ordinary full-year Yukon OP1 run at O87.5, with full survival, supply and wellbeing. See NOTE.md for exact source digests, complete public results, negative experiments and limitations.

All program changes are under submission/. Scratch prototypes and public-fort recordings are kept outside the submitted directory.
