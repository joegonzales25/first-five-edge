# Legacy UI / Data Field Audit

Current product outputs should stay centered on:

1. 1st Inning: YRFI / NRFI / No Edge
2. First 5: away team / home team / No Edge
3. Full Game: away team / home team / No Edge
4. Market Watch: Over Watch / Under Watch / Live Watch / Bullpen Watch / No Edge

## Quarantined Internal Fields

These fields may remain in the dataframe for compatibility, debugging, exports, or baseline comparisons, but should not drive product UI copy.

| Field | Current Role | Product Direction |
|---|---|---|
| Recommendation | Legacy combined recommendation summary | Internal only |
| Confidence | Legacy first-inning confidence | Internal only; use market-specific confidence columns |
| Edge Score | Legacy composite score | Internal only; do not use for top looks |
| NRFI Score | Legacy first-inning score | Internal only; use First Inning Score |
| Lean | Legacy NRFI/YRFI lean text | Internal only; use First Inning Pick |
| F5 Edge | Legacy First 5 lean text | Internal only; use F5 Pick |
| Agent Notes | Legacy model explanation | Internal only; use current key factors and analysis tables |

## Visible UI Rules

| Area | Rule |
|---|---|
| Game cards | Use only current model outputs and compact key factors |
| Top Looks | Use current model picks, current confidence columns, and current scores |
| Market Watch | Avoid betting language; use watch language only |
| Analysis expander | Keep trust-but-verify tables; keep experimental details hidden until promoted |
| Performance | Track model outputs by version; do not grade legacy recommendation fields |

## Legacy Terms To Keep Out Of Product UI

- Pass
- YRFI Yes
- NRFI Yes
- Away F5
- Home F5
- Away Full Game
- Home Full Game
- Ride
- Fade
- Betting
- Lock
- Best bet
