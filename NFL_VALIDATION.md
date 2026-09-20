# NFL baseline validation

## First-half Watch experiment

First-half version 0.1.0-watch uses completed regular-season quarter scores from the ESPN scoreboard. Team aliases align with nflverse IDs. Quarter-two scores are accepted only at halftime or later. Missing quarters are not interpreted as zero.

The model fits opponent-adjusted first-half team strengths and a home-field coefficient using ridge regression. It requires eight prior games for each team, uses a 180-day weight half-life and ridge penalty 4, and emits only Watch picks at an absolute predicted margin of at least two points. These are experimental settings, not validated confidence thresholds. Games within six hours of the target kickoff are excluded from training. Neutral sites omit home advantage. No injury, quarterback, pace, or possession features are currently included.

Run `python nfl_first_half.py --season 2025` for a chronological holdout report using 2024/2025 data. Inspect coverage and results before promoting any signals. Live source access was denied in the local development environment; synthetic regression tests do not establish predictive accuracy or live feed availability.

The snapshot workflow loads first-half data once per season per run. Source failure is logged and does not stop the baseline snapshot. Existing first-half predictions survive transient fetch failures. Older already-locked snapshots are never given retrospective first-half picks. Halftime results settle independently, ties push, and settled results survive missing subsequent data. The GUI displays Not Available until sufficient data is recorded.

Keep baseline 1.0.0 decision thresholds unchanged during monitoring.

## Reporting definitions

- Confidence (legacy export column) and Side Confidence both describe the side margin tier.
- Score (legacy export column) remains the combined game edge score.
- Side Score is absolute model margin, measured in points.
- Scoring Score is absolute projected-total deviation from the stored league baseline, measured in points.
- Scoring Confidence is Uncalibrated. Do not assign probability or A/B/C labels without validation.
- Scoring Correct/Missed measures the direction relative to the stored league baseline.
- An active scheduled pick should be Pending, never No Signal.

## Monitoring gate

Review each market separately after at least 50 settled Official signals. This is a review checkpoint, not proof of predictive value. Report counts, pushes, unresolved rows, accuracy uncertainty, coverage, side confidence tiers, and scoring-deviation bands. Keep Official, Lean, Watch, Baseline, and Challenger separate. Preserve pregame features and use chronological holdout validation before changing thresholds. Do not treat two signals on one game as independent observations.

## Odds collection prerequisite

A timestamped sportsbook data source is required before reporting ROI or closing-line value. Capture game ID, bookmaker, source timestamp, capture timestamp, market, selection, line, decimal price, and scheduled kickoff. Keep quotes append-only and distinguish the quote at prediction time from the last eligible quote before actual kickoff. Do not use post-kickoff or retrospectively supplied closing quotes as prediction inputs.

Capture moneyline prices for winner picks; spread and total lines require their associated prices. Grade totals against the recorded sportsbook line separately from scoring-environment results. Leave price, ROI, and CLV unavailable when quotes are absent. Historical scores and league baselines cannot reconstruct these prices.

## Reconciliation

The snapshot writer now refreshes result fields after updating a Pregame prediction. The next NFL snapshot run repairs stale Pending/No Signal states for games in its processing window. Locked predictions remain immutable and are graded using their stored selections. Older games outside the window require an explicit run for their date; do not assume a deployment itself repaired production records.
