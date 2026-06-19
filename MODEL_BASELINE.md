# EdgeFinder MLB v2.2.7 Baseline

This baseline is bookmarked by git tag `v2.2.7-baseline`.

As of `v2.3.1`, Model 2.3 is the active product model. This v2.2.7 baseline is retained only as rollback/reference context and should not be exposed as a user-facing model selector.

## Primary Outputs

1. 1st Inning: `YRFI`, `NRFI`, or `No Edge`
2. First 5: away team, home team, or `No Edge`
3. Full Game: away team, home team, or `No Edge`
4. Market Watch: informational watch output

## Guardrails

- The model avoids forced picks.
- `No Edge` is a valid and expected output.
- Model outputs are informational only.
- The UI should avoid the word "betting" unless explicitly requested.
- Trust-but-verify analysis tables should be preserved.

## 1st Inning Model

| Factor | Weight |
|---|---:|
| Pitcher YRFI % | 40% |
| Offense YRFI % | 35% |
| 1st Inning ERA | 10% |
| 1st Inning WHIP | 10% |
| 1st Run Avg | 5% |

Thresholds:

- `score >= 58`: YRFI
- `score <= 42`: NRFI
- Otherwise: No Edge

Confidence is based on distance from 50 using the shared confidence table.

## First 5 Model

| Factor | Weight |
|---|---:|
| Starter Edge | 60% |
| Offensive Edge | 40% |

Bullpen data is not used in First 5 decisions.

## Full Game Model

| Factor | Weight |
|---|---:|
| Starter Edge | 35% |
| Offensive Edge | 30% |
| Bullpen Edge | 30% |
| Context | 5% placeholder |

## Data Upgrade Path

After the v2.2.7 baseline, MLB first-inning split data and recent pitcher form can be added as analysis/supporting data before changing scoring weights.
