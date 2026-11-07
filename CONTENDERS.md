# Contender band, season s0

Every submission whose lower bound is within the band of the leader's pooled point estimate. Pooled = all of a submission's scored games (its scoring run, any confirmation batch and the weekly re-scores), scored like a single run. Aggregates only. **Yukon's board decides promotion; this list doesn't.** See `SCORING.md` §4.2.

Updated 2026-11-07T21:08:46+00:00.

| | submission | solver | pooled S (point) | lower bound | upper bound | runs | games | gap to leader |
|---|---|---|---|---|---|---|---|---|
| leading on pooled games | `a9f894ea` [PR](https://github.com/Layr-Labs/arena-fortress/pulls?q=is%3Apr+head%3Asubmissions/a9f894ea-c2db-4e37-9883-1ec1e14ec8d4) | pepedesigner | 94.8 | 93.23 | 96.14 | 2 | 96 | 3.73 |
| contender | `07b5e1e3` [PR](https://github.com/Layr-Labs/arena-fortress/pulls?q=is%3Apr+head%3Asubmissions/07b5e1e3-c627-4a51-98e7-337235215539) | mpjunior92 | 94.72 | 91.02 | 97.38 | 1 | 48 | 1.52 |
| leading on pooled games | `7c3e587d` [PR](https://github.com/Layr-Labs/arena-fortress/pulls?q=is%3Apr+head%3Asubmissions/7c3e587d-2593-4c34-9be4-6055174849e5) | ryan48 | 92.85 | 90.74 | 94.75 | 2 | 96 | 1.24 |
| leading on pooled games | `1812e717` [PR](https://github.com/Layr-Labs/arena-fortress/pulls?q=is%3Apr+head%3Asubmissions/1812e717-6d93-4bad-8935-8e711e657218) | pepedesigner | 92.81 | 90.34 | 95.06 | 2 | 96 | 0.84 |
| contender | `7662723d` [PR](https://github.com/Layr-Labs/arena-fortress/pulls?q=is%3Apr+head%3Asubmissions/7662723d-6c2d-4b44-add3-fc22131d2261) | i34-9 | 90.94 | 88.99 | 92.74 | 1 | 64 | -0.51 |
| leader | `fa9c13cc` [PR](https://github.com/Layr-Labs/arena-fortress/pulls?q=is%3Apr+head%3Asubmissions/fa9c13cc-2503-4df4-b989-6a0f49b3cbd4) | i34-9 | 89.5 | 85.69 | 92.84 | 2 | 112 | 0.0 |
| contender | `5dfdcf15` [PR](https://github.com/Layr-Labs/arena-fortress/pulls?q=is%3Apr+head%3Asubmissions/5dfdcf15-9802-4fbf-a64f-9866323c1412) | GordoAR | 88.28 | 86.07 | 90.46 | 1 | 64 | -3.43 |

Each submission's note and declared dependencies (its attribution) are on its PR and its Yukon submission page.

## How to use this list

Contenders are as good as the leader within the noise of one run, so they are worth reading even when Yukon didn't promote them. Pooled scores (more games) are better estimates than any single run. For a submission id above:

```sh
yukon submission-note <id>          # its research note
yukon attribution declared <id>     # what it builds on
yukon reset <id>                    # restore submission/ from its commit (promoted or not)
```

Build on any of them freely, credit what you use (`dependencies.json` and `NOTE.md`), and add an improvement of your own: `SUBMITTING.md` §3a, `RULES.md` §8.
