# NFL Edge Detector v1.0 Plan

## Product Scope

NFL Edge Detector v1.0 expands the existing First Five Edge app into the broader Edge Detector product shell.

The NFL module should provide matchup intelligence only. It should not provide betting recommendations, staking guidance, odds comparisons, market-value language, or bankroll language.

## Brand And Navigation

Parent brand:

```text
Edge Detector
```

Sport page title:

```text
NFL Edge Detector
```

Initial sport selector:

```text
All | NFL | NBA | NHL | MLB | CBB
```

Initial behavior:

```text
All = home dashboard placeholder
NFL = real v1.0 page
MLB = current working MLB page
NBA/NHL/CBB = coming soon placeholders
```

## NFL Page Modes

The NFL page should have two visible modes:

```text
Current Slate
Historical Lab
```

Current Slate is the default page.

Historical Lab is visible in v1.0 for validation, but may be removed or disabled later.

## Current Slate

Purpose:

```text
Show upcoming/current regular-season NFL games as matchup cards.
```

Default slate behavior:

```text
Default to the nearest upcoming NFL regular-season week with scheduled games.
If there are no upcoming NFL games, show an empty state.
```

Empty state:

```text
No upcoming NFL games found.
Use Historical Lab to review the 2025 model test.
```

Current Slate should not include preseason games in v1.0.

## Historical Lab

Purpose:

```text
Show 2025 historical model output with final results and performance metrics.
```

Historical Lab is fixed to the 2025 regular season in v1.0.

Optional filter:

```text
All Weeks | Week 1 | Week 2 | ... | Week 18
```

Historical cards should show moderate result detail on the collapsed card:

```text
Final Score
Winner: Correct / Missed
Scoring: Correct / Missed
Margin Error
Total Error
```

The Historical Lab summary should include:

```text
Core metrics
Confidence-tier breakdown
High/Low scoring-environment split
```

## Card Design

Use the current dark MLB card style for v1.0 to reduce implementation risk and keep visual continuity.

Use compact NFL team abbreviations:

```text
DAL @ PHI
```

Use top filter pills only. Do not use sidebar filters for NFL v1.0.

NFL card tiles:

```text
Side Edge
Scoring Environment
Early Edge
```

Early Edge is included for layout parity with MLB but should be marked as:

```text
Model Pending
```

until first-half or early-game logic is implemented.

Display team-specific side labels in the UI:

```text
PHI Edge
DAL Edge
```

Do not put confidence grades inside the main signal text. Show confidence separately:

```text
Side Edge: PHI Edge
Confidence: A
```

Collapsed cards should show a short Key Factors summary. Expanded analysis should show the full Key Factors list.

## Shared Row Contract

NFL rows should use the same top-level fields needed for the future multi-sport dashboard:

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

The UI should also derive:

```text
Key Factors Summary
Key Factors List
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

## Model Language

Allowed terms:

```text
Edge
Model Signal
Side Edge
Scoring Environment
Early Edge
Confidence
Agent Notes
Watch
Pass
```

Avoid terms:

```text
Bet
Pick
Play
Lock
Unit
Stake
Wager
Bankroll
ROI
Expected value
+EV
Best bet
Market edge
Value
```

## Current Test Model

The current NFL test model is in:

```text
nfl_backtest.py
```

It uses nflverse game data and rolling pregame team state.

Current tuned defaults:

```text
A side edge: model margin >= 11
B side edge: model margin >= 8
C side edge: model margin >= 5
Scoring environment threshold: +/- 2.5 points vs rolling league baseline
```

2025 tuned backtest:

```text
games: 272
winner accuracy: 64.3%
side signal games: 164
side signal accuracy: 69.5%
margin MAE: 11.21
total MAE: 10.71
scoring signal games: 41
scoring signal accuracy: 70.7%
```

Confidence tiers:

```text
A: 82 games, 72.0% winner accuracy
B: 41 games, 73.2% winner accuracy
C: 41 games, 61.0% winner accuracy
Pass: 108 games, 56.5% winner accuracy
```

Scoring signal split:

```text
High Scoring Environment: 21 games, 66.7%
Low Scoring Environment: 20 games, 75.0%
```

## Implementation Notes

Suggested v1.0 implementation order:

```text
1. Add shared Edge Detector sport selector to app.py.
2. Wrap existing MLB page in an MLB render function without changing MLB model logic.
3. Add NFL page with Current Slate and Historical Lab tabs.
4. Build nfl_agent.py from the tested nfl_backtest.py model functions.
5. Render Historical Lab from nfl_backtest_2025.csv or generated model output.
6. Render Current Slate from nflverse schedule data using the same model engine.
7. Add coming-soon placeholders for NBA, NHL, and CBB.
```
