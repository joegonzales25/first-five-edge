# Edge Detector Model Strategy

Edge Detector is a market intelligence shell for repeatable model development, signal tracking, and performance review. Model outputs are informational only. They are not betting advice, staking guidance, bankroll guidance, or instructions to wager.

Shared user-facing terminology is maintained in
`docs/edge_detector_user_guide.md`. Market-specific docs may add details, but
they should not redefine Official Pick, Lean, Watch, No Edge, Pending, Locked,
Not Tracked, or Snapshot as of.

## Product Hierarchy

```text
Edge Detector
|-- Market
|-- Model
|-- Signal
|-- Tracking contract
|-- Performance review
`-- Release/version record
```

A market is any bounded prediction domain where Edge Detector can define:

```text
input data contract
repeatable model process
signal definitions
output contract
performance tracking contract
promotion criteria
market intake scorecard
```

Markets can be sports, leagues, bet types, player props, team totals, futures, or any other domain where a repeatable edge-detection process can be tested.

## Market Shell

Every new market starts from the same shell:

```text
Market Identity
Market Thesis
Market Intake Scorecard
Data Contract
Model Inputs
Context Factors
Signal Definitions
Output Contract
Tracking Contract
Performance Dashboard
Maturity Stage
Promotion Criteria
Release/Version Rules
Cross-Market Boundary Rules
```

The shell is the launch checklist. A market should not move into tracked testing until the required sections are defined.

## Isolation Rules

New markets begin isolated by default.

Allowed shared areas:

```text
app shell
sport/market picker
query-param helpers
visual styling
market navigation/filter-card format
sidebar data-source/model-info placement
Turso connection pattern
release registry, when added
```

Protected market-specific areas:

```text
model logic
signal definitions
grading rules
performance tables
promotion criteria
market release assumptions
```

Shared UI helpers may be reused by default. Shared model logic, performance logic, grading logic, or storage tables require explicit confirmation before implementation.

## Current Market Boundaries

MLB:

```text
More mature market.
Tracks multiple signal families, including first inning, first five, and full game.
Uses model_history for MLB performance tracking.
Should not absorb WNBA or NFL rows.
```

NFL:

```text
Separate market module.
Uses NFL-specific model logic and historical lab assumptions.
Uses nfl_model_history for isolated NFL performance tracking.
Uses the shared Turso connection pattern with the NFL-only table.
Runs an hourly scheduled snapshot, updates pregame decisions, and locks at kickoff.
Grades Official, Lean, and Watch segments separately.
Keeps the 1.0.0 model calculations and official thresholds unchanged.
```

WNBA:

```text
Early maturity market.
Tracks WNBA full-game side and scoring-environment signals.
Uses wnba_model_history for WNBA performance tracking.
Uses the shared Turso connection pattern with the WNBA-only table.
Uses the shared app-shell navigation rhythm and sidebar model-info placement.
Should not write to MLB model_history.
No Top signal cut until tracked WNBA performance supports it.
```

Future markets:

```text
Start isolated.
Use the market shell.
Reuse shared infrastructure only where boundaries are clear.
Do not inherit another market's signal or grading assumptions without validation.
Popularity or liquidity is a demand signal, not approval to build.
```

## Market Intake Scorecard

Before adding a new market, score the market against repeatability,
modelability, and operational usefulness.

Required intake checks:

```text
demand/liquidity signal
repeatable event structure
objective settlement rule
available pre-event data
historical data depth
snapshot timing feasibility
fair grading window
data-quality risk
integrity/insider-info risk
fit with Edge Detector shell
```

Default decision rule:

```text
Popular markets can enter Design.
Only markets with clear data, settlement, and tracking paths can enter Lab.
Only markets with a written tracking contract can enter Tracked Test.
```

This keeps Edge Detector open to markets everywhere without turning the
product into unrelated one-off predictions.

## Context Factor Layer

Context factors are cross-market concepts that may influence a model, but
their interpretation must remain market-specific.

Shared context-factor concepts:

```text
availability
injuries
starting lineups
late scratches
rest and schedule position
weather
venue/environment
depth chart or role replacement
usage/minutes/workload risk
```

Market-specific interpretation examples:

```text
MLB: starting pitcher, confirmed lineup, key hitter absence, bullpen availability
WNBA/NBA: injury status, starters, minutes restriction, usage concentration
NFL: QB status, practice participation, inactives, offensive line and secondary injuries
NHL future: goalie confirmation, scratches, back-to-back goalie rotation
Soccer future: starting XI, rotation, suspensions, red-card availability
```

Availability context should measure role impact, not just whether a player is
out. A late scratch, replacement quality, position scarcity, usage share, and
matchup interaction can matter more than a generic injury label.

Tracking rule:

```text
Snapshot what was known before the event starts.
Store or note lineup/injury source timing when availability affects a signal.
Do not let post-event lineup knowledge change pre-event context grades.
```

Shared context concepts are allowed by default. Shared availability weights,
thresholds, injury grading, or lineup-adjustment logic require confirmation
before implementation.

## Versioning

Edge Detector uses layered versioning:

```text
Product Release: Edge Detector v2.3.27
Market Release: WNBA v1.0.2-test
Model Baseline: WNBA Model v1.0.0-test
```

Product release:

```text
App-wide release identifier.
Used for git commits, tags, and release notes.
```

Market release:

```text
Market-specific UI, data, tracking, or workflow version.
Bump when a user-facing market workflow changes.
```

Model baseline:

```text
Prediction-logic version.
Bump when model inputs, weights, thresholds, confidence gates, or signal rules change.
```

Pure copy or visual cleanup does not require a market/model version bump unless it changes how users evaluate that market.

Market-release changes include grading rules, snapshot rules, exported fields,
UI contract changes, performance definitions, and Watch/Lean tracking behavior.

Watch/Lean display layers do not require a model baseline bump when they are
derived from existing model outputs. They do require a market release note when
they become stored, graded, filtered, exported, or otherwise change the
user-facing performance contract.

## Database Strategy

Use one Turso database with separate market tables while markets are still maturing.

Initial structure:

```text
model_history          # MLB
wnba_model_history     # WNBA
nba_model_history      # NBA future
nhl_model_history      # NHL future
nfl_model_history      # NFL monitored test
```

This gives one operational backend while keeping market performance separate.

Production deployments must use Turso for history storage. SQLite is allowed
only for intentional local/dev runs. Set `APP_ENV=production`,
`HISTORY_BACKEND=turso`, `TURSO_DATABASE_URL`, and `TURSO_AUTH_TOKEN` in
deployed app secrets and scheduled workflows. If production is configured
without Turso credentials, the app or snapshot job should fail clearly instead
of silently writing to local SQLite. Use `ALLOW_SQLITE_HISTORY_FALLBACK=true`
only for an explicit local/dev exception.

A unified table such as `market_model_history` can be considered later, only after multiple markets have stable and comparable tracking contracts.

## Future Market Candidates

Future-market interest should be tracked without committing to implementation.

Nearer sports candidates:

```text
NBA
NHL
soccer / World Cup
tennis
UFC / boxing, if data quality supports it
```

Non-sports candidates:

```text
weather events
macro releases such as CPI, unemployment, and Fed decisions
equities earnings events
```

Equities earnings should be treated as an event market, not generic stock
prediction.

Possible Equities Earnings first shell:

```text
Market: Equities Earnings
Initial angle: implied move vs realized move
Other signal families: surprise risk, guidance revision risk, analyst estimate dispersion, sentiment/fundamental mismatch, post-earnings drift
Tracking: snapshot before earnings release
Potential grading windows: same day, next trading day, five trading days
```

Politics, personal outcomes, vague news markets, entertainment props with
insider-leak risk, and subjective-resolution markets should be avoided or
deferred unless a strong tracking contract and integrity review exist.

## Tracking Contracts

Every market needs a written tracking contract before persistent tracking is enabled.

Each tracking contract must define:

```text
table name
snapshot eligibility
result grading timing
valid signal types
excluded rows
version fields
summary metrics
export fields
data-quality notes
```

Default rule:

```text
Create prediction snapshots before the event starts.
Grade only existing snapshots when results become final.
Do not backfill final-only rows as if they were pre-event predictions.
```

This protects the review process from hindsight bias.

### Performance Report Standard

Every market should use the same report shape while keeping calculations,
thresholds, grading rules, and promotion criteria market-specific.

Required report sections:

```text
Official Performance
Discovery Performance
Diagnostics / Splits
Export
```

Performance reports are history views, not current-slate card views. They
should not display a `Slate Date` input. Default the reporting anchor to the
latest tracked slate date when stored history exists; otherwise default to
today. Users should narrow reports with the performance controls such as
Day(s), market/signal, confidence, model version, and official/discovery
segment filters.

The `Current model` report option must include that model baseline's stored
history across market releases. A newly incremented market release with no
snapshots must not hide report filters or make existing current-model history
appear empty. Show the release-specific zero-snapshot state as a diagnostic,
and use the full-history empty state only when the market has no stored
performance history.

When a market tracks Watches or Leans, show them as release-tier model
decisions on the same performance surface as Official Picks. Use the same card
shape and filters for `Official Picks`, `Leans`, and `Watches`, but keep each
segment's record and hit rate separate. Do not blend discovery-tier records
into official performance.

Current slate and game-card pages should continue to display `Slate Date`.
Snapshot freshness should remain visible under the filter/result count in both
current and performance views.

Official Performance includes locked official picks only:

```text
hits
misses
pushes
pending
completed
win rate
market split
confidence split
score band split
signal type split, when applicable
date range
```

Discovery Performance includes watches and leans only:

```text
watch outcomes
lean outcomes
hit/miss by discovery label
volume by discovery label
promotion candidates
```

Discovery results are calibration signals. They do not affect official model
record until a market-specific rule promotes a discovery bucket into an
official pick rule.

Diagnostics / Splits are used for model tuning:

```text
score bands
confidence bands
signal types
snapshot timing
locked vs stale rows
data uncertainty flags, such as injuries or goalie status
push / no-action handling
market-specific context fields
```

Exports must include enough fields to reproduce the report:

```text
model_version
market_version
slate_date
sport
market
game
pick
confidence
score
signal_type
discovery_label
discovery_type
discovery_side
result
outcome
status
created_at
updated_at
locked_at
snapshot_status
```

Market-specific fields may be added. They should not replace the shared
reporting fields unless a market-specific tracking contract explicitly says so.

### Snapshot and Lock Contract

Snapshot and lock rules are product-level Edge Detector rules. They apply to
MLB, WNBA, NFL, and future markets unless a market-specific tracking contract
explicitly overrides them.

Definitions:

```text
Current Read: latest model output before event lock; can change.
Official Pick: production signal that clears the market's pick gate.
Tracked Discovery Signal: stored Watch or Lean used for discovery performance.
Locked Pick: stored official pick after the event has reached lock.
Not Tracked: event started or resolved before a valid pre-lock snapshot existed.
Result: resolved event outcome.
```

Universal rules:

```text
1. Current reads may update until event lock.
2. At lock, pick, confidence, score, and signal metadata freeze.
3. After lock, only result, status, outcome, and updated timestamp may change.
4. Performance cards grade stored official picks, stored Watches, and stored Leans only.
5. Official Pick, Lean, and Watch performance must be reported separately.
6. Event/game cards must show the same locked official pick that official performance grades.
7. If no pre-lock snapshot exists, mark the row Not Tracked and exclude it from all performance segments.
8. Current/live recalculated reads may be shown after lock only if clearly labeled Current Read.
9. The UI must show global snapshot freshness and per-event lock state for every current-slate market.
10. Missing snapshots must not remain Pending after the event is complete.
```

Default lock timing:

```text
Sports markets: scheduled event start / game start.
MLB: game start for v1 lock implementation; future target is T-minus 30 minutes.
WNBA: game start for v1 lock implementation; future target is T-minus 30 minutes.
NFL: game start for v1 lock implementation; future target is T-minus 60 to 90 minutes.
Earnings: earnings release or market/session cutoff defined by contract.
Other event markets: market close or event timestamp defined by contract.
```

Display rules:

```text
Under every current-slate filter/result count:
Snapshot as of: M/D/YYYY, H:MM AM/PM ET

Timestamp source:
Use the market's stored snapshot history updated_at/created_at values.
Do not use Streamlit page-load time as the snapshot timestamp.

Event card status:
Scheduled / unlocked: 3:45 PM PDT - Scheduled
Locked: 🔒 3:45 PM PDT - In Progress
Not tracked: ⚠ Not Tracked - 3:45 PM PDT - In Progress
```

Scheduling rule:

```text
Streamlit page loads are not scheduled snapshots.
Use an external scheduler, initially GitHub Actions, to refresh pregame snapshots.
Only active in-season or actively monitored markets should have scheduled
snapshot workflows enabled. Off-season and planning markets may keep manual
snapshot workflows for testing.
Scheduled active-market snapshot jobs should process the current ET slate and
at least the previous ET slate by default, so late finals can settle after
midnight without leaving stored signals Pending.
Manual workflow dispatch with an explicit slate date should process only that
requested slate date unless a backfill operation is explicitly approved.
```

### Watch and Lean Discovery Layer

Watch and Lean labels are product discovery signals. They help users review
near-threshold model reads without blending those reads into official pick
performance.

Definitions:

```text
Pick: official tracked model signal; locked and graded.
Watch: model sees something worth monitoring, but it is not close enough to an official pick.
Lean: stronger than a Watch; model direction is clear, but one requirement still blocks an official pick.
No Edge: no official pick, watch, or lean.
```

Universal rules:

```text
1. Watch and Lean labels must be derived from existing model output fields unless a model change is explicitly approved.
2. Stored Watch and Lean rows may be graded for discovery performance.
3. Watch and Lean performance must never be blended into official pick hit rate.
4. Watch and Lean labels must not be stored as official picks in market performance tables.
5. Event/game cards may display Watch and Lean labels only if clearly separated from Picks.
6. Filters may expose Watch and Lean views for review, but those views are discovery views.
7. Promotion from Watch/Lean to Pick requires tracked discovery history and a confirmed model or market release change.
8. Old Watch/Lean history remains discovery history unless an explicit migration is approved.
```

Initial MLB discovery thresholds:

```text
1st Inning NRFI Lean: No Edge pick, NRFI-leaning signal, score 58-64.
1st Inning NRFI Watch: No Edge pick, NRFI-leaning signal, score 55-57.
1st Inning YRFI Lean: No Edge pick, YRFI-leaning signal, score 25-34.
1st Inning YRFI Watch: No Edge pick, YRFI-leaning signal, score 35-39.

F5 Lean: No official F5 pick, directional team read, score 7.0-11.9.
F5 Watch: No official F5 pick, directional team read, score 4.0-6.9.

Full Game Lean: No official Full Game pick, directional team read, score 6.5-8.9.
Full Game Watch: No official Full Game pick, directional team read, score 4.0-6.4.
```

Market-specific notes:

```text
MLB: Official, Lean, Watch, and No Edge use the corrected strength order above.
WNBA: Side and Scoring decisions use WNBA-specific near-threshold bands and
      store one segment per decision.
MLS: Double Chance, Full Match, Goals, and BTTS use MLS-specific bands and
     store one segment per decision.
NFL: Side and Scoring decisions use NFL-specific near-threshold bands and
     store one segment per decision.
NBA, NHL, CBB, and PGA: Keep current behavior until their market-specific
                       discovery thresholds and active schedules are approved.
Future markets: Do not inherit MLB, WNBA, or MLS thresholds.
```

## Maturity Stages

Markets move through explicit maturity stages:

```text
Design
Lab
Current Slate Test
Tracked Test
Candidate
Validated
Retired
```

Design:

```text
Market thesis and model assumptions are being discussed.
```

Lab:

```text
Historical or offline testing is available.
```

Current Slate Test:

```text
Live/current slate outputs are visible, but persistent performance may not be active.
```

Tracked Test:

```text
Pregame snapshots and final results are stored under a written tracking contract.
```

Candidate:

```text
Tracked performance is strong enough for regular review and cautious iteration.
```

Validated:

```text
Signal definitions are stable across meaningful sample sizes and review windows.
```

Retired:

```text
Market or model version is no longer active.
```

Use `Validated`, not `Production`, to avoid overstating certainty.

## Promotion Criteria

Each market needs market-specific criteria, plus universal minimums.

Universal minimums:

```text
written tracking contract
clear signal definitions
stable data source
availability/context-factor policy, when relevant
completed snapshot sample
performance dashboard
performance diagnostics/export
miss-review workflow
no major data-quality failures
```

## Product Shell UI Standards

Markets should share a recognizable Edge Detector shell where that does not
blur market assumptions.

Shared UI standards:

```text
sport/market picker at the top of the app
large filter-card navigation for primary current-slate views
filter cadence of controls, count caption, divider, then content
sidebar data-source and model-info placement
performance review layout with filters, cards, diagnostics, export, detail rows, and split tables
```

Market-specific UI content remains isolated:

```text
filter labels and counts
signal names
confidence tiers
performance metrics
split-table definitions
placeholder states such as Top or Early
```

The shared shell may make MLB, WNBA, NFL, and future markets feel like one
product, but it must not imply that model logic, grading rules, performance
tables, or promotion criteria are shared.

Example WNBA Tracked Test to Candidate gate:

```text
75+ completed snapshots
side signal accuracy above baseline
scoring signals show useful directional accuracy
confidence tiers separate cleanly
rest/schedule feature reviewed for value
no major data-quality failures
```

No market should add a `Top` signal cut until tracked performance proves which signal bands deserve that label.

## Data and Release Lockdown Status

The approved lockdown strategy is market-specific.

MLB:

```text
Status: production candidate.
Data source of truth: stored snapshot history.
Lock rule: 1st Inning, First 5, and Full Game lock at market/game start.
Performance: official picks, leans, and watches report separately.
Next gate: final reconciliation audit across cards, history, exports, and performance cards.
```

WNBA:

```text
Status: active monitored test market.
Schedule: hourly during active monitoring; scheduled runs process current ET slate plus previous ET slate for settlement.
Data source of truth: stored WNBA snapshot history.
Performance: official side/scoring signals report separately from stored leans/watches when implemented.
Next gate: completed-slate audit to confirm cards, exports, and performance reconcile.
```

MLS:

```text
Status: active monitored test market.
Schedule: hourly during active monitoring; scheduled runs process current ET slate plus previous ET slate for settlement.
Data source of truth: stored MLS snapshot history.
Performance: Double Chance, Full Match, Goals, and BTTS report separately.
Next gate: completed-slate audit to confirm cards, exports, and performance reconcile.
```

NBA:

```text
Status: test/planning.
Schedule: disabled until closer to season.
Data source of truth: separate NBA history table once active.
Next gate: manual snapshot and completed-game grading validation before scheduled tracking.
```

NHL:

```text
Status: test/planning.
Schedule: disabled until closer to season.
Data source of truth: separate NHL history table once active.
Next gate: confirm launch markets and validate live-season data before scheduled tracking.
```

CBB:

```text
Status: v0 framework.
Schedule: manual only until data/source validation.
Data source of truth: separate CBB history table once active.
Next gate: validate season data, full-game settlement, and first-half data quality before official grading.
```

PGA:

```text
Status: documented and paused.
Schedule: none.
Data source of truth: not selected.
Next gate: data-source verification for field list, finish position, cut result, and market settlement.
```

NFL:

```text
Status: active monitored test.
Schedule: hourly at minute 15 during the regular season.
Data source of truth: separate nfl_model_history table in Turso.
Lock: scheduled kickoff.
Performance: stored Official, Lean, and Watch decisions are graded separately;
Not Tracked rows are excluded.
Model baseline: 1.0.0 remains unchanged by the monitored-test lifecycle release.
Next gate: reconcile a representative in-season sample before production review.
```

## Release Checklist

Before a push/tag:

```text
confirm affected market(s)
confirm product release version
confirm market release version
confirm model baseline version, if model logic changed
confirm database/table changes
confirm no unintended cross-market changes
run validation commands
confirm release label
push commit and tag
```

Recommended release label format:

```text
vX.Y.Z - concise product release summary
```

Recommended market note format:

```text
WNBA v1.0.2-test - Performance view filters
```

## New Market Launch Workflow

When a user says a market name, use the strategy shell:

```text
1. Create market identity.
2. Interview model assumptions.
3. Define data source and data contract.
4. Define signal families.
5. Define output contract.
6. Define tracking contract.
7. Define UI views.
8. Assign maturity stage.
9. Build isolated market module.
10. Track performance.
11. Promote only when evidence supports it.
```

The first implementation should be narrow. Add shared abstractions only after repeated market implementations prove the shape is stable.

## Standing Decision Rules

```text
Use "Market" as the primary domain term.
Use one Turso database with separate tables.
Do not create a unified performance table yet.
Use the same performance report shape with separate market calculations.
Require a tracking contract before persistent tracking.
Allow shared UI helpers by default.
Keep shared UI shell patterns visually consistent across markets.
Require confirmation for shared model/performance logic.
Use Validated instead of Production.
Keep product, market, and model versions separate.
Do not create Top picks until tracked performance supports them.
Use this strategy before starting NBA, NHL, or any future market.
```
