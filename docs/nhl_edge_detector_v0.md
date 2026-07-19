# NHL Edge Detector v0 Plan

## Product Scope

NHL is a separate Edge Detector market. It should reuse the shared product shell,
snapshot discipline, lock logic, and performance philosophy from MLB, but NHL
model assumptions, thresholds, confidence rules, and historical performance must
remain isolated.

Model output is informational only. The agent should not produce staking
guidance, betting recommendations, or cross-sport performance comparisons.

## Initial Market Scope

NHL v0 starts with:

```text
Full Game Moneyline
```

First Period, puck line, totals, and regulation-only markets can be considered
after Full Game has enough tracked history.

## Output Contract

NHL output should mirror the MLB/NBA user-facing contract:

```text
Pick
Confidence
Score
Watch
Lean
No Edge
```

Official picks are locked and graded. Watches and leans are discovery signals
only until validated by tracked history.

Historical rows should preserve a market-specific version of the shared fields:

```text
model_version
slate_date
market
game
pick
confidence
score
signal_type
result
stored_outcome
status
created_at
updated_at
locked_at
snapshot_status
outcome
```

NHL-specific analysis fields can be added to exports once the model contract is
finalized, but they should not replace the shared fields above.

## Grading Contract

The official Full Game Moneyline result should be graded including overtime and
shootout, matching the standard full-game moneyline outcome.

When data is available, regulation result should also be tracked separately for
analysis:

```text
regulation_winner
regulation_margin
went_to_overtime
shootout_result
```

Regulation tracking is analytical only in v0. It should not replace the official
graded outcome unless a separate regulation market is explicitly launched later.

## Model Philosophy

NHL v0 uses a conservative hybrid model:

```text
35% Team Shot / Expected Goal Profile
30% Goalie / Netminder Edge
20% Situational Spot
15% Special Teams / Discipline
```

Market context can be added later if reliable free odds data is available, but
it should not be required for the first core score.

## Model Pillars

### Team Shot / Expected Goal Profile

Baseline team quality should include:

```text
Shot share
Expected goals for
Expected goals against
High-danger chance profile
Recent five-on-five form
Home/away split
```

This pillar should represent process quality rather than only recent win/loss
results.

### Goalie / Netminder Edge

Goalie context should include:

```text
Confirmed starter
Projected starter
Save percentage
Goals saved above expected, when available
Recent workload
Back-to-back goalie usage
Team defensive environment in front of goalie
```

NHL v0 may still allow official picks with unconfirmed goalies, but confidence
should be downgraded when starter information is uncertain.

### Situational Spot

Schedule and context should include:

```text
Rest advantage
Back-to-back
Three games in four nights
Travel / road trip context
Home stand context
Altitude or long-distance travel where relevant
```

Situational logic should adjust the baseline. It should not override team and
goalie strength by itself unless later backtesting supports that behavior.

### Special Teams / Discipline

Special teams and penalty context should include:

```text
Power play rate
Penalty kill rate
Penalty differential
Penalty minutes / discipline profile
Special teams mismatch
```

This pillar can support or weaken a side edge, but it should not dominate the
initial model.

## Pick Rules

Official NHL picks should be very selective:

```text
Require at least two model pillars to agree.
Downgrade confidence for unconfirmed starting goalie information.
Avoid official picks when the model edge depends on unavailable or stale data.
Use Watch or Lean when only one strong pillar is present.
Use No Edge when direction is weak or conflicting.
```

Initial confidence bands should mirror MLB style:

```text
A+ = strongest agreement and confirmed goalie context
A  = strong agreement with manageable uncertainty
B  = clear agreement but lower margin or moderate uncertainty
C  = thin official edge
No Edge = below official threshold
```

Exact score thresholds should not be finalized until a backtest dataset is
selected.

## Watch And Lean Rules

Watches and leans are discovery only:

```text
Watch = strong non-pick signal below official threshold
Lean = weaker directional read below Watch strength
```

Common NHL watch scenarios:

```text
Strong team process edge, but goalie unconfirmed
Goalie edge present, but team process is neutral
Situational edge present, but market direction is weak
Two pillars agree, but margin is below official pick threshold
```

They should appear in the analysis layer and may be filtered in the UI, but they
should not be counted in official performance.

Discovery performance can be tracked separately once enough rows exist.

## Snapshot And Lock Rules

NHL should follow the MLB snapshot philosophy:

```text
Pregame snapshots can update picks.
Picks freeze once the game is locked/live.
Performance must match locked game-card picks.
Streamlit should read current snapshots, not mutate history during page loads.
The current-slate UI must display `Snapshot as of: M/D/YYYY, H:MM AM/PM ET`
under the filter/result count, sourced from NHL snapshot history rather than
Streamlit page-load time.
```

Because NHL is goalie-sensitive, the final useful snapshot may be closer to game
time than MLB. The initial implementation should still use the MLB-style live
lock unless a later workflow adds a dedicated confirmed-goalie or pre-puck-drop
lock window.

## Data Source Position

NHL v0 should start with free/public data. Paid APIs may be considered later for:

```text
Confirmed goalies
Injuries
Odds
Line movement
Expected goals
Advanced goalie metrics
```

The first implementation should avoid a dependency on paid data.

## Implementation Notes

Expected future files:

```text
nhl_agent.py
nhl_model.py
.github/workflows/nhl-snapshot.yml
```

Expected future storage:

```text
nhl_model_history
```

Shared UI components may be reused, but NHL model logic and performance tracking
should remain isolated from MLB, NBA, WNBA, and NFL logic.

## Open Questions

Before implementation:

```text
1. Choose the first reliable free NHL data source.
2. Decide whether regulation result is included in exports from day one.
3. Define initial score thresholds from backtest data.
4. Decide how goalie uncertainty is represented in exports.
5. Decide whether free expected-goals data is reliable enough for v0.
```
