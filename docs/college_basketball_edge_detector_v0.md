# College Basketball Edge Detector v0 Plan

## Product Scope

College Basketball is a separate Edge Detector market. It should reuse the
shared product shell, snapshot discipline, lock logic, and performance
philosophy from MLB/NBA/WNBA, but all model assumptions, thresholds,
confidence rules, and historical performance must remain college-basketball
specific.

Model output is informational only. The agent should not produce staking
guidance, betting recommendations, or cross-sport performance comparisons.

College basketball should not share NBA or WNBA history tables. It needs its own
market version, model version, scheduled/manual snapshot path, and performance
reporting.

## Initial Market Scope

College Basketball v0 should start narrow:

```text
Full Game
First Half, official only if reliable first-half scores are available
Scoring environment discovery
First to 10 / Race to 10 future research
```

Initial official market:

```text
Full Game side / moneyline-style team edge
```

First Half side should be included in the v0 model plan. It can become an
official graded market once the selected data source provides consistent
halftime scores for historical backtesting, current slate display, and live
settlement. If halftime data is incomplete or unreliable, First Half should
remain visible as a planned market but should not be counted in official
performance.

Scoring environment may be shown as discovery context if totals data is
available and reliable, but it should not be counted in official performance
until separately validated.

First to 10 / Race to 10 should stay in future research. It exists as a
sportsbook prop, but it requires fast play-by-play data and precise live
settlement. It should not be launched until a reliable source and backtest path
are identified.

## Output Contract

College Basketball output should mirror the shared user-facing contract:

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

College-basketball-specific analysis fields can be added to exports once the
model contract is finalized, but they should not replace the shared fields
above.

## Model Philosophy

College Basketball v0 should use a conservative hybrid model:

```text
40% Team Strength / Efficiency
20% Tempo / Scoring Environment
20% Situational Spot
10% Roster / Availability
10% Market Context, optional
```

Market context is optional in v0 and should use free/public data only unless a
paid data source is explicitly approved later.

Because college basketball has a large team pool, uneven schedules, conference
strength gaps, neutral-site games, and higher matchup variance, thresholds
should be more conservative than NBA until backtesting proves otherwise.

## Model Pillars

### Team Strength / Efficiency

Baseline team quality should include:

```text
Adjusted offensive efficiency
Adjusted defensive efficiency
Net rating
Strength of schedule
Conference quality
Home/away/neutral split
Recent form
Quality of wins/losses
```

This pillar should carry the most weight. Raw win/loss record should not be
trusted without schedule strength context.

### Tempo / Scoring Environment

Scoring context should include:

```text
Possessions / pace
Offensive tempo
Defensive tempo allowed
Three-point attempt rate
Free-throw rate
Turnover rate
Offensive rebounding rate
Recent game-total trend
```

Tempo should inform scoring-environment discovery and can support side
confidence, but it should not create an official side pick by itself.

### Situational Spot

Schedule and context should include:

```text
Rest advantage
Travel distance
Back-to-back tournament games
Neutral-site game
Conference tournament context
Non-conference travel
Lookahead / sandwich spots
Altitude where relevant
```

Situational logic should adjust the baseline. It should not override team
strength by itself unless later backtesting supports that behavior.

### Roster / Availability

Roster and availability should affect confidence and score:

```text
Confirmed key player out
Questionable key player
Multiple rotation players unavailable
Suspensions
Transfer eligibility changes
Late-season roster role changes
```

College Basketball v0 may still allow official picks with roster uncertainty,
but confidence should be downgraded when key availability is uncertain or stale.

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

Official College Basketball picks should be very selective:

```text
Require at least two model pillars to agree.
Require schedule-strength context for every official pick.
Require a data-quality gate before any official pick.
Allow First Half official picks only when halftime scoring data is reliable.
Downgrade confidence for roster or availability uncertainty.
Downgrade confidence for neutral-site or tournament games until tested.
Avoid official picks when edge depends on unavailable or stale data.
Use Watch or Lean when only one strong pillar is present.
Use No Edge when direction is weak or conflicting.
```

Coverage tiers:

```text
Official Pick Eligible = Top 25 teams, major-conference games, tournament games
with reliable data, or any matchup where both teams have enough
schedule-strength and efficiency history.

Watch/Lean Only = mid-major games with usable but weaker data, early-season
games before enough signal exists, or games with meaningful roster/news
uncertainty.

No Edge / Suppressed = small-conference games with thin data, teams with limited
reliable history, missing schedule-strength context, or missing First Half data
for First Half markets.
```

College Basketball v0 may display all available games, but official picks should
only be allowed after the data-quality gate passes. Top 25 and high-major games
are more likely to pass that gate. Smaller-school games can still surface as
Watch/Lean when the signal is interesting, but they should be harder to promote
to official picks.

Uncertainty cap:

```text
Neutral-site uncertainty or key roster uncertainty caps confidence at B.
If uncertainty is material and unresolved, use Watch/Lean instead of an
official pick.
```

Initial confidence bands should mirror the shared style:

```text
A+ = strongest agreement, clean roster context, and strong schedule-adjusted edge
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
Display in analysis/filtering only
Report separately from official pick performance
```

Common College Basketball watch scenarios:

```text
Strong efficiency edge, but opponent schedule strength is uncertain
Strong home/road profile edge, but roster news is incomplete
Tempo/scoring setup is clear, but official scoring market is not launched
First Half direction is present, but halftime data is not yet trusted
Fast-start / Race to 10 setup is interesting, but play-by-play support is missing
Two pillars agree, but neutral-site context caps confidence
Small-conference data is thin or opponent quality is uneven
```

They should appear in the analysis layer and may be filtered in the UI, but they
must be reported separately from official pick performance.

Discovery performance can be stored and graded once enough rows exist.

## Snapshot And Lock Rules

College Basketball should follow the cross-agent snapshot philosophy:

```text
Pregame snapshots can update picks.
Picks freeze once the game is locked/live.
Performance must match locked game-card picks.
Streamlit should read current snapshots, not mutate history during page loads.
The current-slate UI must display `Snapshot as of: M/D/YYYY, H:MM AM/PM ET`
under the filter/result count, sourced from College Basketball snapshot history
rather than Streamlit page-load time.
```

Because roster and injury information is often less structured in college
basketball, the final useful snapshot may be closer to tip-off than NBA. The
initial implementation should still use the shared live-lock rule unless a
later workflow adds a dedicated pre-tip lock window.

## Data Source Position

College Basketball v0 should start with free/public data where possible. Paid
APIs may be considered later for:

```text
Injuries / availability
Odds
Line movement
Adjusted efficiency
Advanced tempo and possession stats
Neutral-site metadata
Conference tournament metadata
```

The first implementation should avoid a dependency on paid data unless we
explicitly decide that free data is too incomplete for a useful v0.

Initial data-source spike:

```text
Primary candidate = CollegeBasketballData.com
Fallback/current-slate candidate = SportsDataverse / ESPN wrappers
Optional odds candidate = The Odds API
```

CollegeBasketballData.com is the preferred first spike because it exposes games,
scoreboard, play-by-play, team stats, rankings, ratings, and lines behind a
college-basketball-specific API. The first spike should verify:

```text
Current slate by date
Final scores
Halftime scores or play-by-play enough to derive halftime
Team ratings, efficiency, or enough team stats to build v0 scoring
```

SportsDataverse / ESPN wrappers should be kept as a fallback for schedule,
scoreboard, play-by-play, box score, team, and standings coverage.

The Odds API can be considered later for optional market context such as
moneyline, spread, and total, but odds should not be required for the first CBB
v0 implementation.

Women's college basketball should be treated as a separate future market with
separate history and performance reporting, not mixed into men's college
basketball results.

## Historical Data Contract

The first backtest path should expect one row per completed game:

```text
season
game_date
away_team
home_team
away_score
home_score
neutral_site
```

Optional:

```text
game_id
away_halftime_score
home_halftime_score
away_rest
home_rest
conference_game
away_conference
home_conference
away_seed
home_seed
spread
total
```

Neutral-site handling is important and should not be inferred from missing home
court data unless the data source supports that assumption.

## Implementation Notes

Expected future files:

```text
cbb_data.py
cbb_agent.py
cbb_model_history.py
snapshot_cbb_slate.py
.github/workflows/cbb-snapshot.yml
```

v0 implementation status:

```text
cbb_data.py = ESPN men's college basketball scoreboard loader
cbb_agent.py = conservative full-game side model with scoring-environment context
cbb_model_history.py = separate CBB snapshot/history table
snapshot_cbb_slate.py = manual snapshot entrypoint
.github/workflows/cbb-snapshot.yml = manual-only workflow until season tracking is ready
```

ESPN CBB scoreboard requests must use either one `YYYYMMDD` value for a
single-date slate or one `YYYY` value for calendar-year history. The endpoint
returns `404` for hyphenated date ranges. Current-slate loads should check the
selected date first and only load calendar-year history when games exist,
filtering those events to the active season before calculating ratings or rest.

Expected future storage:

```text
cbb_model_history
```

Shared UI components may be reused, but College Basketball model logic and
performance tracking should remain isolated from MLB, NFL, WNBA, NBA, and NHL
logic.

The College Basketball UI should follow the cross-agent snapshot display
standard:

```text
Snapshot as of: M/D/YYYY, H:MM AM/PM ET
```

## Open Questions

Before implementation:

```text
1. Choose the first reliable free College Basketball data source.
2. Confirm whether the data source supports reliable halftime scores for First Half grading.
3. Decide how neutral-site games are represented and weighted.
4. Define initial score thresholds from a historical backtest dataset.
5. Decide how roster/availability uncertainty is represented in exports.
6. Decide whether free odds data is reliable enough for the optional market pillar.
7. Women's college basketball is a separate future market.
8. Decide whether Race to 10 has enough data support to move out of future research.
```
