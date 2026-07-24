# College Football Edge Detector v0 Plan

## Status

```text
Experimental v0 implemented; shadow validation pending
Market release: 0.1.0-test
Model baseline: 0.1.0-test
Scheduled snapshots: disabled
```

The policy interview and experimental v0 build are complete. No CFB model
outputs are production decisions until the data-source review, backtest,
shadow validation, grading audit, and release approval are complete.

## Product Scope

College Football is a separate Edge Detector market. It should reuse the shared
product shell, snapshot discipline, lock rules, performance-report shape, and
Official / Lean / Watch vocabulary while keeping all model logic, thresholds,
history, and performance isolated from NFL and other sports.

Model output is informational only. The agent should not provide staking
guidance, bankroll language, or implied guarantees.

## V0 Shape

The following approved shape is implemented for experimental testing:

```text
Competition pool: FBS-focused
Primary market: Full Game side / moneyline-style team edge
Secondary market: Scoring environment
Planned market: First Half side
Discovery tiers: Lean and Watch
Selection posture: Very selective
Data cost: Free/public sources first
Storage: Separate CFB Turso history
Snapshots: Separate CFB workflow, disabled until season readiness
Performance: Official, Lean, and Watch reported separately
```

Spread and total recommendations should not be presented unless reliable
market lines and line timestamps are explicitly added to the data contract.
Without those fields, v0 should describe team-side and scoring-environment
edges rather than claiming against-the-spread or over/under value.

## Shared Output Contract

Each tracked CFB decision should preserve:

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
tracking_segment
result
stored_outcome
status
created_at
updated_at
locked_at
snapshot_status
outcome
```

Official Picks, Leans, and Watches must be frozen from stored pregame snapshots
and graded separately. Page loads must never create or rewrite prediction
history.

## Provisional Model Pillars

Candidate factors for later approval:

```text
Team strength and opponent adjustment
Offensive and defensive efficiency
Explosiveness and finishing drives
Success rate and early-down efficiency
Havoc, turnovers, and sack pressure
Special teams
Quarterback and roster availability
Home field, neutral site, travel, rest, and altitude
Recent form with season-long priors
Conference and schedule strength
Weather
Market context, only if reliable timestamped lines are approved
```

Small samples, roster turnover, coaching changes, uneven schedules, FBS/FCS
matchups, and bowl opt-outs require explicit uncertainty downgrades.

## Snapshot And Performance Contract

CFB should follow the shared release-lockdown rules:

```text
Pregame decisions may update until kickoff.
The latest stored pregame snapshot locks at kickoff.
Locked picks and segments cannot change.
Post-kickoff runs may update status and results only.
Missing pregame snapshots are Not Tracked.
Performance cards, detail rows, and exports must reconcile.
Current-slate freshness comes from stored CFB snapshot history.
Performance pages default to the latest tracked slate and use report filters.
```

## Interview Decision Log

### 1. Competition Pool

Status: Approved for v0; scope adjustment deferred

Approved starting rule:

```text
Model FBS teams.
Include regular-season FBS-vs-FBS games.
Allow FBS-vs-FCS games on the slate, but cap them at Watch unless a later
backtest supports stronger treatment.
Exclude FCS-vs-FCS games from v0.
```

Rationale: FBS provides broader public data coverage and more comparable team
quality. FCS depth, roster, injury, and efficiency data are less consistent.

Revisit after data-source validation and backtesting. That review may support
expansion beyond this pool or a narrower scope such as ranked teams, selected
conferences, or games that meet minimum data-completeness requirements.

### 2. Official Market Scope

Status: Approved for v0

```text
Full Game side / team edge: Official-eligible
Scoring environment: Lean or Watch only
First Half side: Lean or Watch until halftime data is validated
Spread and totals: Excluded until reliable timestamped market lines are added
```

Full Game side is the only initial Official-eligible market. Scoring and First
Half outputs must remain separate discovery decisions and must not affect the
official Full Game performance record.

The approved scope does not imply against-the-spread or over/under value.
Those markets require stored market lines and line timestamps before they can
be modeled, locked, or graded.

### 3. Schedule Scope

Status: Approved for v0

```text
Regular season: Included
Conference championships: Included
College Football Playoff: Included
Non-playoff bowls: Excluded initially
Preseason and spring games: Excluded
```

CFP decisions must be downgraded when quarterback, roster, coaching, or other
material availability information is incomplete. Non-playoff bowls remain
excluded because opt-outs, transfers, coaching changes, and motivation create
a materially different prediction environment. Bowl expansion can be reviewed
later as a separate release decision.

### 4. First Half Activation Gate

Status: Approved for v0

First Half remains graded Lean/Watch discovery until all requirements are met:

```text
Reliable current and historical halftime scores
At least two complete backtest seasons
Separate First Half thresholds and confidence calibration
Stored pregame First Half snapshots
Independent First Half grading and performance cards
Promotion supported by First Half results, not Full Game performance
```

Moving First Half to Official eligibility requires a reviewed market-release
change. It must not be promoted automatically when the data source begins
returning halftime scores.

### 5. Scoring Environment Grading

Status: Approved for v0

```text
Outputs: High, Low, or Neutral Scoring Environment
High/Low segment: Lean or Watch discovery
Neutral segment: No Edge and not graded
Grading reference: Stored pregame model scoring baseline
Sportsbook total: Not used in v0
```

High and Low describe model-relative scoring environments. They must not use
Over/Under terminology or imply value against a market total. Promotion to
Official eligibility requires separate scoring-model validation, calibration,
and an approved market-release change.

### 6. Neutral Sites And Rivalries

Status: Approved for v0

```text
Neutral site: Remove standard home-field advantage
Venue: Verify the actual venue instead of trusting listed home designation
Rivalry: Never creates an edge by itself
Rivalry uncertainty: May downgrade confidence one tier
Conference championship / CFP: Apply neutral-site handling when applicable
```

A rivalry downgrade is not mandatory when backtesting supports stable matchup
behavior and current inputs are complete. The reason for applying or waiving a
downgrade should be preserved in the card analysis and snapshot details.

### 7. Availability Downgrades

Status: Approved for v0

```text
Starting quarterback confirmed out: Recalculate and cap at Lean
Starting quarterback uncertain: Cap at Watch
Multiple material unit absences: Downgrade one tier
Midseason head-coach or coordinator change: Cap at Lean
Incomplete availability data: Cap at Watch
Confirmed normal availability: No downgrade
```

Pregame snapshots may update the pick, segment, and confidence when material
availability changes. Once kickoff locks the snapshot, later runs may update
results only. An earlier Official pick must not be preserved before kickoff
after a material availability change invalidates its eligibility.

### 8. Weather Policy

Status: Approved for v0

```text
Primary weather input: Sustained wind and gusts
Rain or snow alone: Does not create an edge
Precipitation: Use with wind, temperature, field, and team-style context
Extreme temperature or altitude: Situational adjustment
Severe weather / relocation / uncertain kickoff: Cap at Watch
Weather provenance: Store forecast or observation timestamp
```

Weather may adjust a side decision and the discovery scoring environment, but
it must not independently create an Official side pick. Weather inputs should
be refreshed before kickoff and frozen with the locked snapshot.

### 9. Data Source

Status: Approved for v0

```text
Primary source: CollegeFootballData REST API v2
Initial access: Free API key / free tier
Persistent storage: Separate CFB tables in Turso
Status fallback: ESPN scoreboard verification when needed
Secrets: GitHub Actions and Streamlit secrets
Paid upgrade: Only when measured call volume or required endpoints justify it
```

CFBD should provide the primary schedule, score, team-statistics, historical,
ratings, rankings, roster, venue, and available weather inputs. The loader
should batch requests, cache stable reference data, and record source
timestamps so the free allowance is not consumed by unnecessary page loads.

Current references:

- [CFBD API tiers](https://collegefootballdata.com/api-tiers)
- [CFBD REST API schema](https://api.collegefootballdata.com/)

The Streamlit page must read stored CFB snapshots from Turso. It must not call
CFBD to create or mutate prediction history during page loads.

### 10. Historical Backtest Window

Status: Approved for v0

```text
Core seasons: 2018-2025
Included games: FBS regular season, conference championships, and CFP
2020 season: Diagnostic-only; exclude from primary calibration
Recent comparison: Report a rolling three- and four-season view
Non-playoff bowls: Excluded from initial calibration
FBS-vs-FCS: Separate Watch-only diagnostic population
Data timing: Use only information available before kickoff
```

Backtest reporting must show both the full approved period and recent-period
results. The recent view should carry more weight when evaluating production
readiness because transfer activity, roster turnover, and the current college
football structure can make older seasons less representative.

Every historical feature must be reconstructable as of the applicable pregame
snapshot. Final scores, later rankings, later injury information, and any other
post-kickoff data must not enter prediction generation or confidence
calibration.

### 11. Confidence Gates

Status: Approved for v0

```text
Official: FBS-vs-FBS side clears every validated model and data-quality gate
Lean: Directional advantage misses one Official gate or has a moderate downgrade
Watch: Preliminary or fragile signal, incomplete inputs, or a hard market cap
Pass: No actionable directional advantage
FBS-vs-FCS: Hard cap at Watch
Multiple downgrades: Apply the most restrictive cap
Grading: Report Official, Lean, and Watch separately
Numeric bands: Provisional until established by the approved backtest
```

An Official decision requires complete required inputs and no active downgrade
that caps the signal below Official. A signal must not be promoted merely to
fill a slate or satisfy a target pick count.

Lean and Watch decisions are model decisions and must be frozen, graded, and
included in performance reporting. Their records must remain separate from the
Official record so discovery performance cannot inflate the published Official
results.

Initial score bands may be used during development, but they must be labeled
provisional. Production thresholds require backtest support, documented
sample sizes, and approval through the release process.

### 12. Snapshot Cadence

Status: Approved for v0

```text
Scheduler: GitHub Actions
In-season cadence: Hourly
Idle behavior: Exit early when no relevant games require an update
Application behavior: Streamlit reads Turso and never creates snapshots
Pregame behavior: Decisions may change before scheduled kickoff
Lock point: Freeze the latest valid pregame snapshot at kickoff
Delayed game: Remains locked after its original scheduled kickoff
Postponed/rescheduled game: Unlock only after a confirmed new date and time
Results: Continue hourly updates until final
UI freshness: Display the latest stored snapshot time under the result count
```

Every supported market for a game must lock from the same final pregame
snapshot. The loader must not recompute a decision using live-game information.
Once locked, only status, result, grading, and other non-prediction fields may
change.

The current-slate UI must display snapshot freshness in the standard format:
`Snapshot as of: M/D/YYYY, H:MM AM/PM ET`. The timestamp must come from CFB
snapshot history in Turso, not from page-load time.

### 13. Performance and Export Rules

Status: Approved for v0

```text
Default reporting date: Today
Filters: Market, reporting window, model version, decision tier, confidence, outcome
Decision tiers: Report Official, Lean, and Watch separately
Win percentage: Hits / (Hits + Misses); exclude pushes
Pending and pushes: Display separately
Pass / No Edge: Exclude from graded records
Performance eligibility: Locked decisions only
Postponed / canceled / abandoned: Ungraded
Data authority: Turso
Export population: Must match the active report filters
```

Performance cards must show record, completed count, pending count, pushes, and
win percentage where a completed decision exists. A combined view may be
offered only if it is clearly labeled and does not replace the separate
Official, Lean, and Watch records.

The export must include the fields required to reconstruct and audit each
decision, including:

```text
model_version
slate_date
game_id
market
game
pick
decision_tier
confidence
score
result
stored_outcome
status
scheduled_kickoff
created_at
updated_at
locked_at
snapshot_status
source timestamps
data-quality flags
downgrade reasons
final score
```

The UI report and export must use the same Turso query population and filter
logic so their records and totals reconcile.

### 14. Production Release Gate

Status: Provisionally approved for v0; revisit before production

```text
Historical validation: Complete the approved backtest with leakage checks
Benchmarks: Define success criteria before reviewing final results
Baseline: Compare out-of-sample results with a documented baseline model
Live validation: At least four complete shadow weeks
Official sample: At least 25 locked and graded Official decisions
Lock integrity: Verify decisions cannot change after kickoff
Data audit: Verify schedules, final scores, grades, and snapshot timestamps
Reconciliation: UI totals must match equivalent filtered exports
Defects: No unresolved critical data or grading defects
Release controls: Document version, data contract, rollback, and limitations
Approval: Explicit owner approval before production scheduling or designation
```

The four-week shadow period and 25-decision Official minimum are provisional
starting points. They must be reviewed after the historical backtest and again
before production approval. Neither threshold authorizes release by itself.

Success benchmarks must be fixed before final backtest evaluation to prevent
retrospective threshold selection. Production approval should consider
performance, calibration, sample size, data reliability, and operational
integrity together.

### Interview Status

The v0 policy interview is complete. The production release gate remains an
explicit revisit item before the CFB scheduler is enabled for production.

## Experimental V0 Implementation

Implemented components:

```text
Primary source: CollegeFootballData.com API
Status and score overlay: ESPN scoreboard
Markets: Full Game, Scoring Environment, First Half
Decision tiers: Official, Lean, Watch, Pass
History authority: cfb_model_history in the configured Turso database
Page behavior: Read-only from stored CFB history
Snapshot command: snapshot_cfb_slate.py
Workflow: .github/workflows/cfb-snapshot.yml
Workflow trigger: Manual only
```

The workflow requires the existing `TURSO_DATABASE_URL` and
`TURSO_AUTH_TOKEN` secrets plus a CFB-specific `CFBD_API_KEY` secret. The
Streamlit page does not require the CFBD key because it does not contact CFBD
or create snapshots.

The initial rating and scoring thresholds are provisional development bands,
not production-calibrated thresholds. The source does not yet include the
approved material-availability feed, so every non-Pass decision is currently
capped at Watch. This prevents the experimental implementation from producing
an Official decision before that hard gate is satisfied.

The manual workflow should be used to verify schedule normalization, Turso
writes, kickoff locking, grading, current-slate cards, freshness timestamps,
performance filters, and export reconciliation. Hourly scheduling remains
disabled until the production gate is approved. Before enabling it, confirm
the CFBD monthly request budget for the final loader cadence and reference-data
refresh strategy.
