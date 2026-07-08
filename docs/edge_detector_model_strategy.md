# Edge Detector Model Strategy

Edge Detector is a market intelligence shell for repeatable model development, signal tracking, and performance review. Model outputs are informational only. They are not betting advice, staking guidance, bankroll guidance, or instructions to wager.

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
Needs its own tracking contract before persistent performance tracking is enabled.
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
Bump when model inputs, weights, signal rules, or grading assumptions change.
```

Pure copy or visual cleanup does not require a market/model version bump unless it changes how users evaluate that market.

## Database Strategy

Use one Turso database with separate market tables while markets are still maturing.

Initial structure:

```text
model_history          # MLB
wnba_model_history     # WNBA
nfl_model_history      # NFL future
```

This gives one operational backend while keeping market performance separate.

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
Require a tracking contract before persistent tracking.
Allow shared UI helpers by default.
Keep shared UI shell patterns visually consistent across markets.
Require confirmation for shared model/performance logic.
Use Validated instead of Production.
Keep product, market, and model versions separate.
Do not create Top picks until tracked performance supports them.
Use this strategy before starting NBA, NHL, or any future market.
```
