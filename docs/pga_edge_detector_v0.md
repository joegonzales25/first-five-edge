# PGA Edge Detector v0 Plan

## Product Scope

PGA is a separate Edge Detector market. It should reuse the shared product
shell, snapshot discipline, lock logic, and performance reporting philosophy
from the existing agents, but all model assumptions, thresholds, confidence
rules, and historical performance must remain PGA-specific.

Model output is informational only. The agent should not produce staking
guidance, bankroll guidance, or instructions to wager.

PGA should not share MLB, NFL, NBA, WNBA, NHL, or CBB history tables. It needs
its own market version, model version, snapshot path, performance table, and
market-specific grading rules.

## Initial Market Scope

PGA v0 should start narrow and selective:

```text
Top 20 finish
Make/Miss Cut
Head-to-head matchup
Outright winner watch only
Top 5 / Top 10 discovery
First Round Leader / round matchup future research
```

Initial official markets:

```text
Top 20 finish
Make Cut
Head-to-head matchup, if matchup data is available
Outright winner, only if confidence is high enough
```

Outright winner should not be a primary volume market in v0. The payout is
large, but the variance is also large. Outright winner can become an official
pick only when the model clears the highest confidence gate. Otherwise, it
should remain a watch or lean.

Top 5 and Top 10 can be included as discovery markets once finish-position data
and pricing are available. They should not become official until Top 20 and
Make Cut performance are stable.

First Round Leader and round matchups should stay in future research. They need
round-level form, tee-time wave, weather, wind, course setup, and live/round
settlement support before they are reliable enough for official tracking.

## Output Contract

PGA output should mirror the shared Edge Detector contract:

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

PGA historical rows should preserve a market-specific version of the shared
fields:

```text
model_version
slate_date
market
event
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

PGA-specific fields can be added without replacing the shared fields:

```text
tournament
course
player
opponent
tee_time
wave
starting_odds
closing_odds
course_fit_score
recent_form_score
field_strength_score
cut_reliability_score
weather_risk
```

## Model Philosophy

PGA v0 should be a ranking and fit model first. It should identify players who
fit the course, field, and market better than their apparent public price. It
should not be treated like a simple win/loss team model.

Suggested initial weights:

```text
30% Recent Form
25% Course Fit
20% Baseline Player Strength
10% Field Strength
10% Cut Reliability / Volatility
```

Market price/value should be added as soon as a reliable odds source is
available. Until then, official picks should be more conservative, and watches
should carry most of the discovery load.

## Model Pillars

### Recent Form

Recent form should look at the player's most recent events, not just season-long
rank.

Useful signals:

```text
Last 4-8 starts
Recent finish trend
Recent strokes gained trend
Recent approach trend
Recent putting trend
Recent missed cuts
Withdrawals or injury flags
```

Recent form should be capped. One hot tournament should not override a weak
longer-term profile.

### Course Fit

Course fit should compare player skill profile to the demands of the course.

Useful signals:

```text
Driving distance
Driving accuracy
Strokes gained approach
Greens in regulation
Around-the-green skill
Putting surface history
Par 5 scoring
Long iron proximity
Short wedge proximity
Scrambling
Bogey avoidance
Birdie or better rate
```

Course fit should be especially important for Top 20 and Make Cut markets.

### Baseline Player Strength

Baseline strength should represent the player's general ability before recent
form and course fit are applied.

Useful signals:

```text
Season strokes gained total
Season strokes gained tee-to-green
Official world golf ranking, if available
Data Golf ranking, if available and approved
Field-adjusted scoring average
Longer-term finish distribution
```

### Field Strength

PGA results are not equal across fields. A Top 10 in a weak alternate event
should not be treated the same as a Top 10 in a major or signature event.

Useful signals:

```text
Field rank percentile
Strength of recent event fields
Major / signature / standard / alternate event type
Number of elite players in field
Depth of field
```

Field strength should be required for official picks.

### Cut Reliability

Make Cut and Top 20 need a volatility profile.

Useful signals:

```text
Season cut rate
Recent cut rate
High-variance player flag
Opening-round scoring consistency
Blow-up round frequency
Course-specific cut history
```

### Weather and Draw

Weather and tee-time draw should be ignored in PGA v0. They can be revisited
after the core model has stable schedule, field, finish, cut, course, and
pricing data.

## Confidence Rules

PGA confidence should be conservative.

Suggested official-pick confidence gates:

```text
A: Strong model edge, strong course fit, strong recent form, low volatility, price/value confirmed
B: Strong model edge with one moderate risk flag
C: Small edge or incomplete pricing support
No Edge: Weak edge, poor data quality, or conflicting profile
```

Confidence caps:

```text
No price/value check: cap at B
No course-fit data: cap at C
No field-strength context: cap at C
Injury/withdrawal concern: cap at C or No Edge
First-time course with thin profile: cap at C
Outright winner in v0: official only at highest confidence, otherwise Watch/Lean
```

## Watch and Lean Rules

PGA should use watches and leans heavily.

Watch:

```text
Player fits the course
Player has improving recent form
Player may become interesting if price improves
Market is not ready for official grading
```

Lean:

```text
Model shows an edge, but confidence is below official gate
One important input is missing
The signal is market-specific but not yet validated
The player has enough upside but too much volatility
```

Official pick:

```text
All required data is available
The market is supported by settlement data
The model edge clears the confidence gate
The pick can be locked before event start
```

## Snapshot and Lock Rules

PGA snapshots should follow the shared Edge Detector discipline.

Pregame snapshots can update until market lock. Once the tournament or round
starts, official picks must be frozen.

Recommended v0 lock points:

```text
Tournament markets: lock at first scheduled tee time for Round 1
Make Cut: lock at first scheduled tee time for Round 1
Top 20: lock at first scheduled tee time for Round 1
Head-to-head tournament matchup: lock at first scheduled tee time for Round 1
Round-specific markets: lock at first scheduled tee time for that round
```

If a player withdraws before lock, the row should be updated or removed based
on market rules. If a player withdraws after lock, the row should retain the
locked pick and settle according to the market's official rules.

## Performance Reporting

PGA performance should be segmented by market.

Initial performance cards:

```text
Top 20
Make Cut
Head-to-Head
Discovery
```

Performance splits:

```text
Confidence
Market
Event type
Course type
Field strength
Course fit tier
Recent form tier
Weather/draw risk
Price/value available vs unavailable
```

Outright winner should be counted in official hit rate only when the row is
published as an official pick. Outright watches and leans remain discovery.

## Data Source Requirements

PGA v0 needs four core data groups:

```text
Tournament schedule and field
Player historical results
Course profile
Settlement results by market
```

Useful optional data:

```text
Strokes gained
Odds / market prices
Tee times
Weather
Withdrawals
World ranking / field strength
```

Free/public data should be used first. Paid data should be considered only if
it materially improves reliability for official markets.

## V0 Build Recommendation

Build order:

```text
1. PGA documentation and business rules
2. Data-source spike for schedule, field, results, and cut data
3. Separate PGA history table and manual snapshot path
4. Current tournament display with watches and leans
5. Official Top 20 and Make Cut tracking
6. Head-to-head matchup support if data source allows it
7. Pricing/value layer
8. Round-specific markets later
```

The first production-like PGA release should not launch with every available
market. It should launch with a small number of explainable, trackable markets
and expand only after performance history supports the expansion.
