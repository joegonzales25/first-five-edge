# NBA Edge Detector v0 Plan

## Product Scope

NBA is a separate Edge Detector market. It should reuse the shared product shell,
snapshot discipline, lock logic, and performance philosophy from MLB, but the
model assumptions, thresholds, confidence rules, and historical performance must
remain NBA-specific.

Model output is informational only. The agent should not produce staking
guidance, betting recommendations, or cross-sport performance comparisons.

WNBA remains governed by `docs/wnba_edge_detector_v1.md`.

## Initial Market Scope

NBA v0 starts with:

```text
Full Game
First Half placeholder
```

First Quarter can be considered later after Full Game and First Half have
enough tracked history.

Implementation note: v0 launches with full-game side and scoring-environment
signals because the free ESPN scoreboard feed reliably supplies game/final
scores. First Half remains a visible `Model Pending` placeholder until a
reliable halftime-result source is added.

## Output Contract

NBA output should mirror the MLB user-facing contract:

```text
Pick
Confidence
Score
Watch
Lean
No Edge
```

Official picks are locked and graded as the production record. Watches and
leans may be stored and graded as discovery performance, but they must be
reported separately from official pick hit rate.

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

NBA-specific analysis fields can be added to exports once the model contract is
finalized, but they should not replace the shared fields above.

## Model Philosophy

NBA v0 uses a conservative hybrid model:

```text
45% Team Strength / Efficiency
25% Situational Spot
20% Injury / Availability
10% Market Context
```

Market context is optional in v0 and should use free/public data only unless a
paid data source is explicitly approved later.

## Model Pillars

### Team Strength / Efficiency

Baseline team quality should include:

```text
Offensive efficiency
Defensive efficiency
Net rating
Pace
Home/away splits
Recent form
```

This pillar should carry the most weight because it is the most stable starting
point for NBA game-level modeling.

### Situational Spot

Schedule and context should include:

```text
Rest advantage
Back-to-back
Three games in four nights
Travel / road trip context
Home stand context
Potential lookahead or schedule compression
```

Situational logic should adjust the baseline. It should not override team
strength by itself unless later backtesting supports that behavior.

### Injury / Availability

Injury and availability should affect confidence and score:

```text
Confirmed key player out
Questionable key player
Probable key player
Multiple rotation players unavailable
Late-breaking uncertainty
```

NBA v0 may still allow official picks with injury risk, but confidence should
be downgraded when key availability is uncertain.

### Market Context

Market context is optional in v0 and should be lightweight:

```text
Available spread or moneyline
Line movement if available
Implied market expectation
Model-vs-market gap
```

If reliable free market data is unavailable, this pillar should be omitted from
pick gating rather than filled with weak data.

## Pick Rules

Official NBA picks should be very selective:

```text
Require at least two model pillars to agree.
Downgrade confidence for injury uncertainty.
Avoid official picks when the model edge depends on unavailable or stale data.
Use Watch or Lean when only one strong pillar is present.
Use No Edge when direction is weak or conflicting.
```

Initial confidence bands should mirror MLB style:

```text
A+ = strongest agreement and clean availability
A  = strong agreement with manageable uncertainty
B  = clear agreement but lower margin or moderate uncertainty
C  = thin official edge
No Edge = below official threshold
```

Exact score thresholds should not be finalized until a backtest dataset is
selected.

## Watch And Lean Rules

Watches and leans are graded discovery signals:

```text
Watch = model sees something worth monitoring, but it is not close enough to an official pick
Lean = stronger than a Watch; direction is clear, but one official-pick requirement is still missing
```

They should appear in the analysis layer and may be filtered in the UI, but they
must be reported separately from official pick performance.

Discovery performance can be stored and graded once enough rows exist.

## Snapshot And Lock Rules

NBA should follow the MLB snapshot philosophy:

```text
Pregame snapshots can update picks.
Picks freeze once the game is locked/live.
Performance must match locked game-card picks.
Streamlit should read current snapshots, not mutate history during page loads.
The current-slate UI must display `Snapshot as of: M/D/YYYY, H:MM AM/PM ET`
under the filter/result count, sourced from NBA snapshot history rather than
Streamlit page-load time.
```

Because NBA is injury-sensitive, the final useful snapshot may be closer to game
time than MLB. The initial implementation should still use the MLB-style live
lock unless a later workflow adds a dedicated pre-tip lock window.

## Data Source Position

NBA v0 should start with free/public data. Paid APIs may be considered later for:

```text
Injuries
Confirmed lineups
Odds
Line movement
Advanced team efficiency
```

The first implementation should avoid a dependency on paid data.

## Implementation Notes

Expected future files:

```text
nba_agent.py
nba_data.py
nba_model_history.py
snapshot_nba_slate.py
.github/workflows/nba-snapshot.yml
```

Expected future storage:

```text
nba_model_history
```

Shared UI components may be reused, but NBA model logic and performance
tracking should remain isolated from MLB, WNBA, NFL, and future NHL logic.

## Open Questions

Before implementation:

```text
1. Choose the first reliable free NBA data source.
2. Decide whether Full Game and First Half launch together or sequentially.
3. Define initial score thresholds from backtest data.
4. Decide how injury uncertainty is represented in exports.
5. Decide whether free odds data is reliable enough for the 10% market pillar.
```

## Approved Validation Contract

NBA remains `test/planning` until both validation phases pass and the owner
approves promotion. Validation does not change the model baseline, confidence
thresholds, or selection rules.

### Phase A: Historical Holdout

Use at least two completed regular seasons. Run each season independently so
team state does not carry across season boundaries. The latest season is the
default chronological holdout.

Required review:

```text
No missing required rows or duplicate games
At least 50 holdout side signals
At least 50 holdout scoring-environment signals
Side accuracy compared with a home-team baseline on the same signal rows
Scoring accuracy compared with the majority scoring baseline
Confidence ordering reviewed with at least 20 signals in comparable tiers
Margin and total MAE
Home/away, rest, and limited-history splits
```

Historical injury and availability information must be treated as unavailable
unless it is reconstructable as of game time. The base model must be reviewed
separately from any future injury component.

Run:

```powershell
python season_model_validation.py historical --market nba --input <normalized-games.csv> --holdout-season <season>
```

The normalized input requires:

```text
season
game_date
away_team
home_team
away_score
home_score
```

### Phase B: Live Shadow

Start with manual snapshots. After one week of clean manual operation, enable
hourly shadow scheduling. Do not designate the model as a Candidate until it
has at least four complete tracked weeks and 50 locked, graded Official side
decisions.

Run the stored-history audit with:

```powershell
python season_model_validation.py shadow --market nba --market-version 0.1.0-test --model-version 0.1.0-test
```

The audit requires completed Official rows to have scores and grades, completed
rows to be locked, and every locked row to have `locked_at`. Game cards,
history, exports, and performance must still be reconciled manually before
owner approval.

Passing either CLI report does not enable the NBA schedule or authorize a
release. Reports always require owner review.
