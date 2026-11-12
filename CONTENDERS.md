# Contender band, season s0

Every submission whose lower bound is within the band of the leader's pooled point estimate. Pooled = all of a submission's scored games (its scoring run, any confirmation batch and the weekly re-scores), scored like a single run. Aggregates only. **Yukon's board decides promotion; this list doesn't.** See `SCORING.md` §4.2.

Updated 2026-11-12T01:35:33+00:00.

| | submission | solver | pooled S (point) | lower bound | upper bound | runs | games | gap to leader |
|---|---|---|---|---|---|---|---|---|
| leader | `65e60732` [PR](https://github.com/Layr-Labs/arena-fortress/pulls?q=is%3Apr+head%3Asubmissions/65e60732-98d2-4765-a2c6-f84076c3e5fe) | 0xplemonade | 97.03 | 96.02 | 97.82 | 1 | 64 | 0.0 |
| contender | `d1febd13` [PR](https://github.com/Layr-Labs/arena-fortress/pulls?q=is%3Apr+head%3Asubmissions/d1febd13-b50c-4bec-84cd-e078d68a4156) | 0xplemonade | 96.6 | 95.91 | 97.28 | 1 | 48 | -1.12 |
| contender | `82e5301e` [PR](https://github.com/Layr-Labs/arena-fortress/pulls?q=is%3Apr+head%3Asubmissions/82e5301e-1c43-4036-b16b-363aa2d0e4b8) | 0xplemonade | 96.07 | 94.38 | 97.25 | 2 | 96 | -2.65 |
| contender | `879ec09f` [PR](https://github.com/Layr-Labs/arena-fortress/pulls?q=is%3Apr+head%3Asubmissions/879ec09f-c421-4c1b-b297-358d77043c2f) | 0xplemonade | 95.83 | 94.03 | 97.19 | 2 | 96 | -3.0 |
| contender | `a9f894ea` [PR](https://github.com/Layr-Labs/arena-fortress/pulls?q=is%3Apr+head%3Asubmissions/a9f894ea-c2db-4e37-9883-1ec1e14ec8d4) | pepedesigner | 94.8 | 93.23 | 96.14 | 2 | 96 | -3.8 |

Each submission's note and declared dependencies (its attribution) are on its PR and its Yukon submission page.

## How to use this list

Contenders are as good as the leader within the noise of one run, so they are worth reading even when Yukon didn't promote them. Pooled scores (more games) are better estimates than any single run. For a submission id above:

```sh
yukon submission-note <id>          # its research note
yukon attribution declared <id>     # what it builds on
yukon reset <id>                    # restore submission/ from its commit (promoted or not)
```

Build on any of them freely, credit what you use (`dependencies.json` and `NOTE.md`), and add an improvement of your own: `SUBMITTING.md` §3a, `RULES.md` §8.
