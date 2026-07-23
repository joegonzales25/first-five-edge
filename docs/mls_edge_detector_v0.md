# MLS Edge Detector v0 Plan

## Product Scope

MLS is a separate Edge Detector market. It should reuse the shared product
shell, snapshot discipline, lock logic, and performance philosophy from MLB,
WNBA, NBA, NHL, and College Basketball, but all model assumptions, thresholds,
confidence rules, and historical performance must remain MLS-specific.

Model output is informational only. The agent should not produce staking
guidance, betting recommendations, or cross-sport performance comparisons.

MLS should not share generic soccer history tables in v0. It needs its own
market version, model version, scheduled/manual snapshot path, and performance
reporting. A future soccer framework can generalize MLS patterns after the
first market proves stable.

## Initial Market Scope

MLS v0 should start with:

```text
Full Match Result
Double Chance
Goals Environment
Both Teams To Score
First Half placeholder
```

Initial official markets:

```text
Full Match Result: Home / Away / Draw / Pass
Double Chance: Home or Draw / Away or Draw / Home or Away / Pass
Goals Environment: High / Low / Neutral
Both Teams To Score: discovery-only Yes / No / Pass
```

First Half should be visible as `Model Pending` only in v0 unless a reliable
halftime score source is selected for both current slate settlement and
historical backtesting.

## Output Contract

MLS output should mirror the shared user-facing contract:

```text
Pick
Confidence
Score
Watch
Lean
No Edge / Pass
```

Official picks are locked and graded as the production record. Watches and
leans are graded discovery signals, but they must be reported separately from
official pick hit rate.

Historical rows should preserve a market-specific version of the shared fields:

```text
model_version
market_version
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

MLS-specific analysis fields can be added to exports once the model contract is
finalized, but they should not replace the shared fields above.

## Model Philosophy

MLS v0 should use a conservative soccer model:

```text
35% Team Strength / Form
25% Attack / Defense Goal Profile
20% Home / Travel / Schedule Context
10% Draw Risk
10% Lineup / Availability Risk
```

Market context is optional in v0 and should use free/public data only unless a
paid data source is explicitly approved later.

Because soccer has lower scoring, higher draw frequency, and meaningful lineup
uncertainty, MLS thresholds should be selective. No Edge / Pass should be common.

## Model Pillars

### Team Strength / Form

Baseline team quality should include:

```text
Points per match
Goal difference
Recent form
Home / away split
Opponent strength when available
Conference context
```

Raw table position should not be used alone. MLS parity, travel, and home-field
effects make home/away and recent form especially important.

### Attack / Defense Goal Profile

Scoring context should include:

```text
Goals for
Goals against
Recent scoring trend
Clean sheets
Failed-to-score rate
Both-teams-to-score frequency
Over / under frequency
```

If expected-goals data is available from a reliable source, it should improve
this pillar. If not, v0 should begin with score-derived team profiles and treat
confidence more conservatively.

### Home / Travel / Schedule Context

MLS situational context should include:

```text
Home-field advantage
Long-distance travel
Short rest
Midweek match
Road-trip sequence
Cup / continental competition congestion
Altitude where relevant
```

Away official picks should require stronger evidence than home-side or double
chance signals.

### Draw Risk

Draw risk should be explicit:

```text
Similar team strength
Low scoring projection
Defensive profiles
Recent draw tendency
Away team content with point
```

Draw risk should downgrade full-match side confidence. It can support a draw
pick or push the model toward double chance instead of full-match result.

### Lineup / Availability Risk

Availability context should include:

```text
International duty
Injuries
Suspensions
Rotation risk
Key attacker / goalkeeper / center back missing
```

MLS v0 may allow official picks with incomplete lineup data, but confidence
should be downgraded when the model direction depends on uncertain personnel.

## Pick Rules

Official MLS picks should be very selective:

```text
Require at least two model pillars to agree.
Require draw risk to be evaluated for every full-match result pick.
Downgrade away-side confidence unless the edge is strong.
Downgrade confidence for lineup or international-absence uncertainty.
Avoid official picks when data quality is stale or incomplete.
Use Double Chance when side direction is clear but draw risk is material.
Use Watch or Lean when only one strong pillar is present.
Use No Edge / Pass when direction is weak or conflicting.
```

Initial confidence bands should mirror the shared style:

```text
A+ = strongest agreement, clean data, low draw/lineup risk
A  = strong agreement with manageable uncertainty
B  = clear agreement but moderate draw, away, or lineup risk
C  = thin official edge
No Edge / Pass = below official threshold
```

Exact score thresholds should not be finalized until a data source and backtest
dataset are selected.

## Watch And Lean Rules

Watches and leans are graded discovery signals:

```text
Watch = model sees something worth monitoring, but it is not close enough to an official pick
Lean = stronger than a Watch; direction is clear, but one official-pick requirement is still missing
```

Common MLS watch scenarios:

```text
Strong home profile, but draw risk is elevated
Clear goals environment, but recent form is volatile
Away side looks better, but travel/rest risk is material
BTTS profile is clear, but one attack is lineup-sensitive
Two pillars agree, but edge is below official threshold
```

They should appear in the analysis layer and may be filtered in the UI, but they
must be reported separately from official pick performance.

## Snapshot And Lock Rules

MLS should follow the shared snapshot philosophy:

```text
Pregame snapshots can update picks.
Picks freeze once the match is locked/live.
Performance must match locked game-card picks.
Streamlit should read current snapshots, not mutate history during page loads.
The current-slate UI must display `Snapshot as of: M/D/YYYY, H:MM AM/PM ET`
under the filter/result count, sourced from MLS snapshot history rather than
Streamlit page-load time.
```

If no pregame snapshot exists before kickoff, the match should be marked
`Not Tracked` rather than graded from stale or post-kickoff data.

## Data Source Position

MLS v0 should start with ESPN as the free/public data source. ESPN is approved
for v0 because it should support the first implementation without adding a paid
dependency. If ESPN coverage, competition filtering, kickoff timestamps,
scores, or recent-history depth are insufficient, the data-source decision
should be revisited before expanding model scope.

The ESPN path must reliably provide:

```text
Fixtures
Kickoff time
Home / away teams
Status
Final score
Recent match history
Standings or enough history to derive form
```

Stronger model quality may require paid or richer data for:

```text
Expected goals
Injuries
Suspensions
Confirmed lineups
Odds / market context
Competition congestion
```

If reliable free lineup and xG data are unavailable, MLS v0 should launch with
conservative confidence and clear data-quality notes.

Approved v0 source:

```text
Primary source: ESPN soccer / MLS scoreboard and history endpoints
Fallback source: TBD only if ESPN proves insufficient
```

ESPN soccer can expose MLS regular-season rows with soccer-specific season type
values. The v0 loader trusts ESPN's `regular-season` slug first, and keeps
known numeric regular-season types as a fallback. As of the July 22, 2026 slate,
ESPN exposes MLS regular-season events with season type `13846`.

## Approved V0 Decisions

The following decisions are approved for v0:

```text
1. MLS v0 includes regular-season MLS matches only.
2. Exclude Leagues Cup, U.S. Open Cup, CONCACAF Champions Cup, friendlies, playoffs, and other non-regular-season competitions from v0.
3. Full Match Result may allow official Draw picks in v0, but only with strict draw-risk agreement such as low scoring environment, balanced team strength, and no clear side edge.
4. Double Chance is the primary official MLS v0 market. Full Match Result remains official-eligible, but should be more selective because it must clear Home / Away / Draw uncertainty.
5. Goals Environment uses non-line-specific High / Low / Neutral labels in v0. It should not imply an Over/Under line unless actual market totals are added later.
6. Both Teams To Score is discovery-only in v0. BTTS Yes / No signals may appear as Watch or Lean and should be graded separately before any promotion to official picks.
7. First Half is visible as `Model Pending` only in v0. It should not be graded until reliable halftime settlement data is selected.
8. MLS v0 uses free/public data only, even if that limits lineup, injury, expected-goals, and odds quality at launch.
```

## V0 Implementation

MLS v0 uses:

```text
Source: ESPN MLS scoreboard
Storage: Turso-backed mls_model_history, separate from every other market
Snapshot command: snapshot_mls_slate.py
UI: MLS sport pill with current slate, snapshot freshness, game cards, and performance summary
Schedule: hourly GitHub Actions cron, with manual dispatch still available
```

When the scheduled MLS snapshot runs without an explicit date, it records the
current ET slate and revisits the previous ET slate to settle late finals. A
manual `slate_date` dispatch records only that requested slate date.
