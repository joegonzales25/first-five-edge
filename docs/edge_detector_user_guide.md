# Edge Detector User Guide

Edge Detector is a market intelligence and performance tracking app. Model
outputs are informational only. They are not betting advice, staking guidance,
bankroll guidance, or instructions to wager.

## Core Terms

### Official Pick

An Official Pick is a production signal that clears the market's approved pick
gate.

Official Picks are:

```text
stored in a snapshot
locked when the market starts
graded after the result is known
included in official performance
reported separately from Watches and Leans
```

### Lean

A Lean is stronger than a Watch. It means the model direction is clear, but one
requirement still blocks an Official Pick.

Typical reasons:

```text
close to the confidence gate but just short
good edge score but confidence is capped
conflicting model factor prevents an official pick
data quality or timing issue prevents locking it as official
enough upside to track, but too much uncertainty for official performance
```

Leans can be stored and graded as discovery performance, but they are not
Official Picks.

### Watch

A Watch means the model sees something worth monitoring, but it is not close
enough to an Official Pick.

Typical reasons:

```text
good matchup profile but score is below the pick gate
one side of the model is favorable but confirmation is missing
market context is interesting but incomplete
lineup, injury, weather, odds, or late movement confirmation is needed
pattern is useful for discovery tracking
```

Watches can be stored and graded as discovery performance, but they are not
Official Picks.

### No Edge

No Edge means the model does not have enough signal for an Official Pick, Lean,
or Watch.

No Edge rows are not graded as wins or losses.

### Pending

Pending means a stored Official Pick, Lean, or Watch has not settled yet.

Pending should not be used for completed events that were never stored before
lock. Those rows should become Not Tracked.

### Locked

Locked means the stored pick record is frozen because the market has started.

After lock:

```text
pick does not change
confidence does not change
score does not change
signal type does not change
result/status may update
performance may update when final
```

### Not Tracked

Not Tracked means the event started or completed before a valid pre-lock
snapshot existed.

Not Tracked rows are excluded from:

```text
Official Pick performance
Lean performance
Watch performance
promotion analysis
```

### Snapshot As Of

Snapshot as of shows the freshness of the stored market snapshot.

Required display:

```text
Snapshot as of: M/D/YYYY, H:MM AM/PM ET
```

The timestamp must come from stored snapshot history, not Streamlit page-load
time.

If no stored snapshot exists, use:

```text
Snapshot as of: Not available
```

## Performance Segments

Edge Detector separates performance into distinct segments:

```text
Official Picks = production record
Leans = discovery record
Watches = discovery record
```

These segments must not be blended into one hit rate.

## Snapshot Rules

Global rules:

```text
1. Official Picks, Leans, and Watches must come from stored snapshots to be graded.
2. Pregame snapshots may update until the market starts.
3. Once the market starts, the latest stored snapshot locks.
4. After lock, later page loads or data refreshes can update result fields only.
5. Missing stored snapshots become Not Tracked, not stale Pending rows.
```

## Release Rules

Global rules:

```text
model logic change = model version increment
grading/release-contract change = market release increment
experimental markets = labeled test/planning/paused or hidden
production readiness = cards, history, exports, and performance reconcile
```

## Market Status

Current lockdown status:

```text
MLB: production candidate, pending final reconciliation audit
WNBA: active monitored test market
NBA: test/planning; scheduled snapshots disabled until season
NHL: test/planning; scheduled snapshots disabled until season
CBB: v0 framework; manual snapshots only until data/source validation
PGA: documented and paused
NFL: needs classification before production lockdown
```

