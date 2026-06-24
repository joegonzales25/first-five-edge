# Basketball Edge Detector v0 Plan

## Product Scope

NBA and WNBA models should follow the NFL module shape: matchup intelligence only, no odds, staking guidance, market-value language, or betting recommendations.

The initial implementation is model-first. UI enablement should wait until a backtest data source is selected and the thresholds are validated.

## Shared Row Contract

Basketball model output should preserve the shared multi-sport fields:

```text
Sport
Game Time
Game
Model Signal
Edge Score
Confidence
Side Edge
Scoring Edge
Early Edge
Agent Notes
Status
```

Historical rows also include:

```text
Away Score
Home Score
Actual Winner
Predicted Winner
Winner Correct
Model Margin
Actual Margin
Margin Error
Projected Total
Actual Total
Total Error
Scoring Correct
League Total Baseline
```

## Initial Model

The first NBA/WNBA model uses rolling pregame team state:

```text
Team strength = offense vs league baseline + defense vs league baseline + season margin + recent form
Side edge = projected home margin including home-court and rest context
Scoring environment = projected total vs rolling league total baseline
```

Default thresholds are intentionally conservative placeholders until backtests are run.

NBA defaults:

```text
A side edge: model margin >= 9.0
B side edge: model margin >= 6.5
C side edge: model margin >= 4.0
Scoring environment threshold: +/- 5.0 points vs rolling league baseline
Default total baseline: 226.0
```

WNBA defaults:

```text
A side edge: model margin >= 7.0
B side edge: model margin >= 5.0
C side edge: model margin >= 3.0
Scoring environment threshold: +/- 4.0 points vs rolling league baseline
Default total baseline: 164.0
```

## Input Data Contract

The CSV backtest path expects one row per completed game with:

```text
season
game_date
away_team
home_team
away_score
home_score
```

Optional columns:

```text
game_id
away_rest
home_rest
```

## Implementation Notes

Files:

```text
basketball_model.py
nba_agent.py
wnba_agent.py
```

Run a local CSV backtest with:

```powershell
python basketball_model.py --league NBA --games-csv path\to\nba_games.csv --season 2025
python basketball_model.py --league WNBA --games-csv path\to\wnba_games.csv --season 2025
```

Next steps:

```text
1. Choose canonical WNBA historical game data source.
2. Generate WNBA historical backtests.
3. Tune WNBA side and scoring thresholds.
4. Decide which WNBA features survive v1.0 validation.
5. Revisit NBA only after the WNBA model has been kicked.
```

See `docs/wnba_edge_detector_v1.md` for the WNBA v1.0 agent interview.
