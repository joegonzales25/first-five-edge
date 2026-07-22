import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from html import escape
from io import StringIO
import csv
import re
import sqlite3
from zoneinfo import ZoneInfo
from mlb_agent import get_today_games, team_abbreviation
from nfl_agent import (
    build_current_slate,
    build_historical_lab,
    historical_summary_tables,
)
from wnba_agent import (
    backtest_no_rest_schedule,
    build_current_season_lab as build_wnba_current_season_lab,
    build_current_slate as build_wnba_current_slate,
    backtest_schedule as build_wnba_historical_lab,
    historical_summary_tables as wnba_historical_summary_tables,
)
from nba_agent import (
    build_current_season_lab as build_nba_current_season_lab,
    build_current_slate as build_nba_current_slate,
    backtest_schedule as build_nba_historical_lab,
    historical_summary_tables as nba_historical_summary_tables,
)
from nhl_agent import (
    build_current_season_lab as build_nhl_current_season_lab,
    build_current_slate as build_nhl_current_slate,
    backtest_schedule as build_nhl_historical_lab,
    historical_summary_tables as nhl_historical_summary_tables,
)
from cbb_agent import (
    build_current_season_lab as build_cbb_current_season_lab,
    build_current_slate as build_cbb_current_slate,
    backtest_schedule as build_cbb_historical_lab,
    historical_summary_tables as cbb_historical_summary_tables,
)
from mls_agent import (
    build_current_slate as build_mls_current_slate,
)
from wnba_model_history import (
    load_wnba_history,
    load_wnba_performance_tables,
    load_wnba_performance_summary,
)
from nba_model_history import (
    load_nba_history,
    load_nba_performance_tables,
    load_nba_performance_summary,
)
from nhl_model_history import (
    load_nhl_history,
    load_nhl_performance_tables,
    load_nhl_performance_summary,
)
from cbb_model_history import (
    load_cbb_history,
    load_cbb_performance_tables,
    load_cbb_performance_summary,
)
from mls_model_history import (
    load_mls_history,
    load_mls_performance_summary,
)
from model_history import (
    load_slate_history_rows,
)

APP_VERSION = "2.3.29"
MODEL_CACHE_VERSION = "edge-v2329-first-inning-sample-cap-refine"
# Keep performance history stable across UI/cache releases. Change this only
# when the model baseline, grading definition, or history schema intentionally changes.
PERFORMANCE_TRACKING_VERSION = "2.3.29"
FALLBACK_TIMEZONE = "America/New_York"
MARKET_RELEASES = {
    "MLB": "2.3.30",
    "NFL": "1.0.0",
    "WNBA": "1.0.1-test",
    "NBA": "0.1.0-test",
    "NHL": "0.1.0-test",
    "CBB": "0.1.0-test",
    "MLS": "0.1.0-test",
}
MODEL_BASELINES = {
    "MLB": "2.3.29",
    "NFL": "1.0.0",
    "WNBA": "1.0.0-test",
    "NBA": "0.1.0-test",
    "NHL": "0.1.0-test",
    "CBB": "0.1.0-test",
    "MLS": "0.1.0-test",
}
SPORT_CONFIG = {
    "MLB": {"enabled": True},
    "NFL": {"enabled": True},
    "WNBA": {"enabled": True},
    "NBA": {"enabled": True},
    "NHL": {"enabled": True},
    "CBB": {"enabled": True},
    "MLS": {"enabled": True},
}

team_logo_map = {
    "Arizona Diamondbacks": "https://www.mlbstatic.com/team-logos/109.svg",
    "Athletics": "https://www.mlbstatic.com/team-logos/133.svg",
    "Atlanta Braves": "https://www.mlbstatic.com/team-logos/144.svg",
    "Baltimore Orioles": "https://www.mlbstatic.com/team-logos/110.svg",
    "Boston Red Sox": "https://www.mlbstatic.com/team-logos/111.svg",
    "Chicago Cubs": "https://www.mlbstatic.com/team-logos/112.svg",
    "Chicago White Sox": "https://www.mlbstatic.com/team-logos/145.svg",
    "Cincinnati Reds": "https://www.mlbstatic.com/team-logos/113.svg",
    "Cleveland Guardians": "https://www.mlbstatic.com/team-logos/114.svg",
    "Colorado Rockies": "https://www.mlbstatic.com/team-logos/115.svg",
    "Detroit Tigers": "https://www.mlbstatic.com/team-logos/116.svg",
    "Houston Astros": "https://www.mlbstatic.com/team-logos/117.svg",
    "Kansas City Royals": "https://www.mlbstatic.com/team-logos/118.svg",
    "Los Angeles Angels": "https://www.mlbstatic.com/team-logos/108.svg",
    "Los Angeles Dodgers": "https://www.mlbstatic.com/team-logos/119.svg",
    "Miami Marlins": "https://www.mlbstatic.com/team-logos/146.svg",
    "Milwaukee Brewers": "https://www.mlbstatic.com/team-logos/158.svg",
    "Minnesota Twins": "https://www.mlbstatic.com/team-logos/142.svg",
    "New York Mets": "https://www.mlbstatic.com/team-logos/121.svg",
    "New York Yankees": "https://www.mlbstatic.com/team-logos/147.svg",
    "Oakland Athletics": "https://www.mlbstatic.com/team-logos/133.svg",
    "Philadelphia Phillies": "https://www.mlbstatic.com/team-logos/143.svg",
    "Pittsburgh Pirates": "https://www.mlbstatic.com/team-logos/134.svg",
    "San Diego Padres": "https://www.mlbstatic.com/team-logos/135.svg",
    "San Francisco Giants": "https://www.mlbstatic.com/team-logos/137.svg",
    "Seattle Mariners": "https://www.mlbstatic.com/team-logos/136.svg",
    "St. Louis Cardinals": "https://www.mlbstatic.com/team-logos/138.svg",
    "Tampa Bay Rays": "https://www.mlbstatic.com/team-logos/139.svg",
    "Texas Rangers": "https://www.mlbstatic.com/team-logos/140.svg",
    "Toronto Blue Jays": "https://www.mlbstatic.com/team-logos/141.svg",
    "Washington Nationals": "https://www.mlbstatic.com/team-logos/120.svg",
}


def get_query_param(name):
    value = st.query_params.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def is_valid_timezone(timezone_name):
    if not timezone_name:
        return False

    try:
        ZoneInfo(str(timezone_name))
        return True
    except Exception:
        return False


def detect_browser_timezone():
    context_timezone = getattr(st.context, "timezone", None)
    if is_valid_timezone(context_timezone):
        return str(context_timezone), True

    detected_timezone = get_query_param("client_tz")
    if is_valid_timezone(detected_timezone):
        return str(detected_timezone), True

    return FALLBACK_TIMEZONE, False


def current_date_for_timezone(timezone_name):
    try:
        timezone = ZoneInfo(timezone_name)
    except Exception:
        timezone = ZoneInfo(FALLBACK_TIMEZONE)

    return datetime.now(timezone).date()

st.set_page_config(
    page_title="First Five Edge",
    page_icon="⚾",
    layout="wide"
)

st.markdown("""
<style>
.game-card {
    border-radius: 18px 18px 0 0;
    border: 1px solid #243244;
    border-left: 8px solid #0ea5e9;
    padding: 22px;
    margin-bottom: 0;
    background:
        linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(17, 24, 39, 0.98)),
        #0f172a;
    color: #f8fafc;
    box-shadow: 0 18px 34px rgba(15, 23, 42, 0.22);
    position: relative;
}

.game-card::after {
    content: "";
    position: absolute;
    left: -8px;
    right: 0;
    bottom: -22px;
    height: 22px;
    background: #0f172a;
    border-left: 8px solid #0ea5e9;
}

.badge {
    display: inline-block;
    padding: 6px 12px;
    border-radius: 999px;
    color: white;
    font-weight: 700;
    font-size: 14px;
    margin-right: 8px;
    margin-bottom: 8px;
}
.badge-nrfi { background: #16a34a; }
.badge-yrfi { background: #dc2626; }
.badge-f5 { background: #2563eb; }
.badge-pass { background: #6b7280; }
.badge-edge { background: #111827; }

.logo-row {
    display: flex;
    align-items: center;
    gap: 14px;
    margin: -6px -6px 18px -6px;
    padding: 14px 16px;
    flex-wrap: wrap;
    border-radius: 14px;
    background: linear-gradient(90deg, #1e3a8a, #0f766e);
    border: 1px solid rgba(255, 255, 255, 0.1);
}
.logo-team {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-height: 42px;
}
.team-logo {
    width: 44px;
    height: 44px;
    object-fit: contain;
    background: rgba(255, 255, 255, 0.9);
    border-radius: 999px;
    padding: 4px;
}
.team-logo-name {
    font-size: 15px;
    font-weight: 700;
    color: #f8fafc;
}
.logo-at {
    color: #bfdbfe;
    font-weight: 800;
}

.game-title {
    font-size: 28px;
    font-weight: 800;
    margin-top: 8px;
    margin-bottom: 4px;
    color: #ffffff;
}
.muted {
    color: #cbd5e1;
    font-size: 15px;
    margin-bottom: 14px;
}
.data-quality-notice {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border-radius: 999px;
    padding: 8px 12px;
    margin: 0 0 12px 0;
    font-size: 13px;
    font-weight: 800;
    color: #fde68a;
    background: rgba(120, 53, 15, 0.42);
    border: 1px solid rgba(251, 191, 36, 0.42);
}
.data-quality-poor {
    color: #fecaca;
    background: rgba(127, 29, 29, 0.45);
    border-color: rgba(248, 113, 113, 0.45);
}
.recommendation {
    font-size: 18px;
    margin-top: 10px;
    margin-bottom: 10px;
}
.market-watch {
    margin: 12px 0 14px 0;
    padding: 16px 18px;
    border-left: 0;
    border-radius: 14px;
    background: linear-gradient(90deg, #065f46, #047857);
    color: #dcfce7;
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}
.market-heading {
    font-size: 14px;
    font-weight: 800;
    color: #a7f3d0;
    margin-bottom: 4px;
}
.market-pick {
    font-size: 18px;
    font-weight: 900;
    color: #ffffff;
    margin-bottom: 6px;
}
.market-why {
    font-size: 13px;
    font-weight: 800;
    color: #bbf7d0;
    margin-bottom: 4px;
}
.key-factors {
    margin: 0 0 12px 0;
}
.decision-stack {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin: 14px 0 16px 0;
    color: #f8fafc;
    font-size: 16px;
}
.decision-line {
    display: block;
    min-height: 88px;
    border-radius: 14px;
    padding: 14px 16px;
    background: #1e293b;
    border: 1px solid #334155;
    font-weight: 700;
    line-height: 1.3;
    box-shadow: inset 0 0 24px rgba(14, 165, 233, 0.12);
    color: #f8fafc !important;
    text-decoration: none !important;
    cursor: pointer;
    transition: transform 0.12s ease, background 0.12s ease, box-shadow 0.12s ease;
}
.decision-result {
    display: block;
    margin-top: 8px;
    color: #cbd5e1;
    font-size: 13px;
    font-weight: 800;
    line-height: 1.25;
}
.result-outcome {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    margin-left: 6px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 900;
    line-height: 1;
    vertical-align: middle;
}
.result-hit {
    color: #052e16;
    background: #22c55e;
}
.result-miss {
    color: #450a0a;
    background: #ef4444;
}
.result-push {
    width: auto;
    padding: 0 7px;
    color: #0f172a;
    background: #cbd5e1;
    font-size: 11px;
}
.decision-result-mobile {
    display: none;
}
.decision-line:hover {
    transform: translateY(-1px);
    background: #24324a;
}
.decision-line.is-selected {
    background: #26364f;
    box-shadow: 0 0 0 3px rgba(248, 250, 252, 0.18), inset 0 0 28px rgba(248, 250, 252, 0.08);
}
.decision-line:nth-child(1) {
    border-color: #22c55e;
    box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.22), inset 0 0 24px rgba(34, 197, 94, 0.16);
}
.decision-line:nth-child(2) {
    border-color: #38bdf8;
    box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2), inset 0 0 24px rgba(56, 189, 248, 0.15);
}
.decision-line:nth-child(3) {
    border-color: #f97316;
    box-shadow: 0 0 0 2px rgba(249, 115, 22, 0.2), inset 0 0 24px rgba(249, 115, 22, 0.15);
}
.decision-line.is-selected:nth-child(1) {
    box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.42), inset 0 0 28px rgba(34, 197, 94, 0.22);
}
.decision-line.is-selected:nth-child(2) {
    box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.4), inset 0 0 28px rgba(56, 189, 248, 0.22);
}
.decision-line.is-selected:nth-child(3) {
    box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.4), inset 0 0 28px rgba(249, 115, 22, 0.22);
}
@media (max-width: 640px) {
    .decision-stack {
        grid-template-columns: 1fr;
        gap: 10px;
    }

    .decision-line {
        min-height: 70px;
        padding: 12px 14px;
    }

    .decision-result-full {
        display: none;
    }

    .decision-result-mobile {
        display: block;
        font-size: 12px;
    }
}
.edge-view-control {
    position: absolute;
    opacity: 0;
    pointer-events: none;
}
.edge-factor-panel {
    display: none;
}
.edge-view-first:checked ~ .decision-stack .decision-first,
.edge-view-f5:checked ~ .decision-stack .decision-f5,
.edge-view-full:checked ~ .decision-stack .decision-full {
    background: #26364f;
}
.edge-view-first:checked ~ .decision-stack .decision-first {
    box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.42), inset 0 0 28px rgba(34, 197, 94, 0.22);
}
.edge-view-f5:checked ~ .decision-stack .decision-f5 {
    box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.4), inset 0 0 28px rgba(56, 189, 248, 0.22);
}
.edge-view-full:checked ~ .decision-stack .decision-full {
    box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.4), inset 0 0 28px rgba(249, 115, 22, 0.22);
}
.edge-view-first:checked ~ .edge-factor-panels .edge-factor-first,
.edge-view-f5:checked ~ .edge-factor-panels .edge-factor-f5,
.edge-view-full:checked ~ .edge-factor-panels .edge-factor-full {
    display: block;
}
.reason-stack {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 6px 14px;
    margin: 0 0 14px 0;
    color: #e2e8f0;
    font-size: 14px;
}
.reason-item {
    display: flex;
    align-items: flex-start;
    gap: 7px;
    line-height: 1.3;
}
.reason-check {
    color: #22c55e;
    font-weight: 900;
    line-height: 1.2;
}
.key-factors {
    border-radius: 14px;
    padding: 14px 16px 2px;
    background: rgba(30, 41, 59, 0.72);
    border: 1px solid #334155;
}
.key-factors .market-heading {
    color: #bfdbfe;
}
.model-favorite {
    background: linear-gradient(90deg, #064e3b, #047857);
    border-radius: 18px;
    padding: 22px;
    margin-bottom: 22px;
    color: white;
}
.model-label {
    font-size: 13px;
    letter-spacing: 1.5px;
    font-weight: 800;
    color: #bbf7d0;
}
.model-pick {
    font-size: 28px;
    font-weight: 900;
    margin-top: 6px;
}
.top-looks {
    background: linear-gradient(135deg, #064e3b, #0f766e);
}
.top-look-list {
    display: grid;
    gap: 14px;
    margin-top: 14px;
}
.top-look-item {
    display: grid;
    grid-template-columns: 42px 1fr;
    gap: 12px;
    align-items: start;
    padding: 14px 16px;
    border-radius: 14px;
    background: rgba(15, 23, 42, 0.38);
    border: 1px solid rgba(255, 255, 255, 0.12);
}
.top-look-rank {
    width: 34px;
    height: 34px;
    border-radius: 999px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #0f172a;
    color: #a7f3d0;
    font-weight: 900;
}
.top-look-title {
    font-size: 18px;
    font-weight: 900;
    color: #ffffff;
}
.top-look-meta,
.top-look-why {
    margin-top: 4px;
    color: #d1fae5;
    font-size: 14px;
}
.top-look-link {
    display: inline-block;
    margin-top: 8px;
    color: #bfdbfe;
    font-weight: 900;
    text-decoration: none;
}
.top-look-link:hover {
    text-decoration: underline;
}

.performance-results {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
    margin-top: 14px;
}
.performance-card {
    border-radius: 16px;
    padding: 18px;
    background: rgba(15, 23, 42, 0.46);
    border: 1px solid rgba(255, 255, 255, 0.14);
}
.performance-market {
    color: #bfdbfe;
    font-weight: 900;
    font-size: 16px;
}
.performance-hit-rate {
    margin-top: 8px;
    color: #ffffff;
    font-size: 36px;
    font-weight: 950;
    line-height: 1;
}
.performance-record {
    margin-top: 8px;
    color: #d1fae5;
    font-weight: 800;
}
.performance-meta {
    margin-top: 4px;
    color: #cbd5e1;
    font-size: 13px;
}

.last-five-team {
    margin: 10px 0 18px;
}
.last-five-team-label {
    margin: 0 0 6px;
    color: #f8fafc;
    font-size: 16px;
    font-weight: 900;
}
.last-five-table {
    width: 100%;
    border-collapse: collapse;
    margin: 0;
    font-size: 13px;
}
.last-five-table th,
.last-five-table td {
    border-bottom: 1px solid rgba(148, 163, 184, 0.28);
    padding: 7px 8px;
    text-align: left;
    vertical-align: middle;
}
.last-five-table th {
    color: #cbd5e1;
    font-weight: 900;
}
.last-five-table td {
    color: #e2e8f0;
}
.result-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 24px;
    border-radius: 999px;
    padding: 2px 8px;
    color: white;
    font-weight: 900;
}
.result-win {
    background: #16a34a;
}
.result-loss {
    background: #dc2626;
}

.sport-picker {
    display: flex;
    gap: 8px;
    margin: 8px 0 18px;
    overflow-x: auto;
    scrollbar-width: none;
}
.sport-picker::-webkit-scrollbar {
    display: none;
}
.sport-pill {
    display: inline-block;
    min-width: 58px;
    padding: 9px 14px;
    border-radius: 999px;
    text-align: center;
    font-size: 13px;
    font-weight: 900;
    letter-spacing: 0;
    border: 1px solid #334155;
    background: #1e293b;
    color: #cbd5e1;
    text-decoration: none;
}
.sport-pill.active {
    border-color: #22c55e;
    background: linear-gradient(135deg, #1d4ed8, #0f766e);
    color: #ffffff;
    box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.18);
}
.sport-pill.disabled {
    opacity: 0.48;
}

.nfl-control-row {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin: 12px 0 18px;
}
.nfl-control-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 42px;
    padding: 10px 14px;
    border-radius: 14px;
    background: #1e293b;
    border: 1px solid #334155;
    color: #f8fafc;
    font-size: 13px;
    font-weight: 900;
    text-decoration: none;
    white-space: nowrap;
}
.nfl-control-pill.active {
    border-color: #22c55e;
    background: linear-gradient(135deg, #1d4ed8, #0f766e);
    box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.18);
}
.nfl-control-label {
    margin: 12px 0 6px;
    color: #64748b;
    font-size: 13px;
    font-weight: 900;
    text-transform: uppercase;
}
.nfl-slate-label {
    margin: 18px 0 8px;
    color: #64748b;
    font-size: 18px;
    font-weight: 500;
}
.nfl-slate-box {
    width: 100%;
    border-radius: 14px;
    padding: 18px 22px;
    margin: 0 0 26px;
    background: #f1f5f9;
    color: #94a3b8;
    font-size: 22px;
    line-height: 1;
}
.nfl-filter-strip {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
    margin: 0 0 22px;
}
.nfl-filter-strip .nfl-control-pill {
    min-height: 50px;
    min-width: 0;
    padding: 10px 12px;
    border-radius: 12px;
    font-size: 14px;
}
.nfl-filter-strip .nfl-control-pill:first-child {
    grid-column: 1 / -1;
    min-height: 56px;
    font-size: 15px;
}
.nfl-count-caption {
    margin: 0 0 24px;
    color: #64748b;
    font-size: 20px;
    font-weight: 500;
}

.wnba-filter-grid {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 12px;
    margin: 12px 0 24px;
}
.wnba-filter-card {
    display: flex;
    align-items: center;
    min-height: 78px;
    padding: 14px 16px;
    border-radius: 14px;
    background: #1e293b;
    border: 1px solid #334155;
    color: #f8fafc;
    box-shadow: inset 0 0 24px rgba(14, 165, 233, 0.12);
    font-weight: 900;
    line-height: 1.25;
    white-space: pre-line;
    text-decoration: none;
}
.mlb-filter-grid {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 12px;
    margin: 12px 0 8px 0;
}
.mlb-filter-card {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 78px;
    padding: 14px 16px;
    border-radius: 14px;
    background: #1e293b;
    border: 1px solid #334155;
    color: #f8fafc !important;
    box-shadow: inset 0 0 24px rgba(14, 165, 233, 0.12);
    font-size: 15px;
    font-weight: 900;
    line-height: 1;
    text-decoration: none !important;
    white-space: nowrap;
}
.mlb-filter-card:nth-child(1) {
    grid-column: 1 / -1;
    border-color: #22c55e;
}
.mlb-filter-card:nth-child(2) {
    border-color: #38bdf8;
}
.mlb-filter-card:nth-child(3) {
    border-color: #f97316;
}
.mlb-filter-card:nth-child(4) {
    border-color: #a855f7;
}
.mlb-filter-card:nth-child(5) {
    border-color: #ef4444;
}
.mlb-filter-card:nth-child(6) {
    border-color: #f59e0b;
}
.mlb-filter-card:nth-child(7) {
    border-color: #14b8a6;
}
.mlb-filter-card.active {
    background: linear-gradient(135deg, #1d4ed8, #0f766e);
    box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.28), inset 0 0 26px rgba(255, 255, 255, 0.08);
}
.discovery-strip {
    margin: 12px 0 10px 0;
    padding: 10px 12px;
    border-radius: 12px;
    background: rgba(15, 23, 42, 0.72);
    border: 1px solid rgba(56, 189, 248, 0.32);
    color: #e0f2fe;
    font-size: 13px;
    font-weight: 800;
    line-height: 1.3;
}
.discovery-label {
    display: inline-flex;
    align-items: center;
    margin: 3px 6px 3px 0;
    padding: 4px 8px;
    border-radius: 999px;
    background: rgba(14, 165, 233, 0.18);
    color: #f8fafc;
    white-space: nowrap;
}
.discovery-label.lean {
    background: rgba(245, 158, 11, 0.18);
}
.wnba-filter-card:nth-child(1) {
    grid-column: 1 / -1;
    border-color: #22c55e;
}
.wnba-filter-card:nth-child(2) {
    border-color: #38bdf8;
}
.wnba-filter-card:nth-child(3) {
    border-color: #f97316;
}
.wnba-filter-card:nth-child(4) {
    border-color: #a855f7;
}
.wnba-filter-card:nth-child(5) {
    border-color: #ef4444;
}
.wnba-filter-card:nth-child(6) {
    border-color: #14b8a6;
}
.wnba-filter-card.active {
    background: linear-gradient(135deg, #1d4ed8, #0f766e);
    box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.28), inset 0 0 26px rgba(255, 255, 255, 0.08);
}

@media (max-width: 640px) {
    .mlb-filter-grid,
    .wnba-filter-grid {
        grid-template-columns: repeat(6, minmax(44px, 1fr));
        gap: 6px;
    }

    .mlb-filter-card,
    .wnba-filter-card {
        min-height: 44px;
        padding: 8px 4px;
        border-radius: 12px;
        justify-content: center;
        text-align: center;
        font-size: 12px;
        white-space: pre-line;
    }

    .performance-results {
        grid-template-columns: 1fr;
    }
}

div[data-testid="stCaptionContainer"]:has(+ div[data-testid="stVerticalBlock"]) {
    display: none;
}

div[data-testid="stExpander"] {
    margin-top: -22px;
    margin-bottom: 22px;
    position: relative;
    z-index: 2;
}

div[data-testid="stHtml"]:has(.game-card) {
    margin-bottom: -22px;
}

div[data-testid="stExpander"] details {
    border: 1px solid #243244;
    border-top: 0;
    border-left: 8px solid #0ea5e9;
    border-radius: 0 0 18px 18px;
    overflow: hidden;
    background: #0f172a;
    box-shadow: 0 18px 34px rgba(15, 23, 42, 0.22);
}

div[data-testid="stExpander"] details > summary {
    min-height: 48px;
}

div[data-testid="stExpander"] summary {
    background: linear-gradient(90deg, #1e3a8a, #0f766e);
    color: #f8fafc;
    font-weight: 800;
    border-top: 1px solid #334155;
}

div[data-testid="stExpander"] div[data-testid="stExpanderDetails"] {
    background:
        linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(17, 24, 39, 0.98)),
        #0f172a;
    color: #e2e8f0;
    padding: 20px 24px 24px;
}

div[data-testid="stExpander"] div[data-testid="stMarkdownContainer"] h3 {
    color: #ffffff;
    border-left: 5px solid #0ea5e9;
    padding-left: 12px;
    margin-top: 20px;
}

div[data-testid="stExpander"] div[data-testid="stMarkdownContainer"] h4 {
    color: #bfdbfe;
    margin-top: 16px;
}

div[data-testid="stExpander"] hr {
    border-color: #334155;
}

div[data-testid="stExpander"] table {
    border-collapse: separate;
    border-spacing: 0;
    overflow: hidden;
    border-radius: 12px;
    border: 1px solid #334155;
    background: #111827;
}

div[data-testid="stExpander"] thead tr {
    background: linear-gradient(90deg, #1d4ed8, #0f766e);
}

div[data-testid="stExpander"] th {
    color: #f8fafc !important;
    font-weight: 900 !important;
    border-color: #334155 !important;
}

div[data-testid="stExpander"] td {
    color: #e2e8f0 !important;
    border-color: #334155 !important;
    background: #111827;
}

div[data-testid="stExpander"] tbody tr:nth-child(even) td {
    background: #162033;
}
</style>
""", unsafe_allow_html=True)


def split_game_name(game_name):
    if " @ " in game_name:
        away, home = game_name.split(" @ ", 1)
        return away, home
    return "Away", "Home"


def render_team_logo(team_name):
    logo_url = team_logo_map.get(team_name)
    if not logo_url:
        return ""

    return (
        f'<img class="team-logo" src="{escape(logo_url)}" '
        f'alt="{escape(team_name)} logo" loading="lazy">'
    )


def render_logo_matchup(away_team, home_team):
    away_logo = render_team_logo(away_team)
    home_logo = render_team_logo(home_team)

    return (
        '<div class="logo-row">'
        f'<div class="logo-team">{away_logo}<span class="team-logo-name">{escape(away_team)}</span></div>'
        '<span class="logo-at">@</span>'
        f'<div class="logo-team">{home_logo}<span class="team-logo-name">{escape(home_team)}</span></div>'
        '</div>'
    )


def get_row_value(row, column_name, default="Pass"):
    value = row.get(column_name, default)
    if value is None or value == "":
        return default
    return value


def is_no_edge_pick(pick):
    return str(pick).strip() in [
        "",
        "Pass",
        "No Edge",
        "F5 Pass",
        "No Edge (Pass)",
        "Not Tracked",
    ]


def replace_home_away(value, away_team, home_team):
    text = str(value)
    if not away_team or not home_team:
        return text

    replacements = {
        "Away": away_team,
        "Home": home_team,
    }

    for side, team_name in replacements.items():
        text = re.sub(rf"\b{side}\b", team_name, text)

    return text


def format_decision_pick(pick, confidence, away_team=None, home_team=None, market=None):
    if str(pick).strip() == "Not Tracked":
        return "Not Tracked"
    if is_no_edge_pick(pick):
        return "No Edge"

    display_pick = str(pick)
    if away_team and home_team:
        display_pick = replace_home_away(display_pick, away_team, home_team)

    if market == "first":
        display_pick = re.sub(r"\s+Yes$", "", display_pick)
    elif market == "f5":
        display_pick = re.sub(r"\s+F5$", "", display_pick)
    elif market == "full_game":
        display_pick = re.sub(r"\s+Full Game$", "", display_pick)

    if is_no_edge_pick(confidence) or confidence in [None, ""]:
        return display_pick

    return f"{display_pick} ({confidence})"


def render_result_outcome(outcome):
    if outcome == "Hit":
        return '<span class="result-outcome result-hit" aria-label="Hit">&#10003;</span>'
    if outcome == "Miss":
        return '<span class="result-outcome result-miss" aria-label="Miss">&times;</span>'
    if outcome == "Push":
        return '<span class="result-outcome result-push" aria-label="Push">Push</span>'

    return ""


def render_decision_result(result, compact_result=None, outcome=None):
    if result in [None, "", "N/A", "Pending"]:
        return ""

    compact_result = compact_result or result
    outcome_badge = render_result_outcome(outcome)
    return (
        f'<span class="decision-result decision-result-full">Result: {escape(str(result))}{outcome_badge}</span>'
        f'<span class="decision-result decision-result-mobile">{escape(str(compact_result))}{outcome_badge}</span>'
    )


def should_show_game_result(status):
    status = str(status or "").strip().lower()

    if status in ["", "scheduled", "pre-game", "preview", "postponed"]:
        return False

    return True


def get_first_existing_value(row, column_names):
    for column_name in column_names:
        value = row.get(column_name)
        if value not in [None, "", "N/A"]:
            return value
    return None


def format_rank_metric(row, value_column, rank_columns, rank_scope):
    value = get_row_value(row, value_column, "N/A")
    rank = get_first_existing_value(row, rank_columns)

    if rank is None:
        return value

    return f"{value} (#{rank} {rank_scope})"


def format_yrfi_vs_league(row, value_column):
    value = get_numeric_value(row, value_column)
    league_avg = get_numeric_value(row, "League YRFI %")

    if value is None:
        return get_row_value(row, value_column, "N/A")

    if league_avg is None:
        return f"{value:.1f}%"

    difference = value - league_avg
    return f"{value:.1f}% ({difference:+.1f}%)"


def render_last_five_results(row):
    sections = []

    for column_name in ["Away Last 5 Results", "Home Last 5 Results"]:
        results = get_row_value(row, column_name, [])
        if not isinstance(results, list) or not results:
            continue

        results = sorted(
            results,
            key=lambda result: result.get("Sort Date", ""),
            reverse=True,
        )
        team_name = results[0].get("Team", "Team")
        rows = []

        for result in results:
            outcome = str(result.get("Result", "")).upper()
            badge_class = "result-win" if outcome == "W" else "result-loss"
            rows.append(
                "<tr>"
                f"<td>{escape(str(result.get('Date', '')))}</td>"
                f"<td>{escape(str(result.get('Opponent', '')))}</td>"
                f'<td><span class="result-badge {badge_class}">{escape(outcome)}</span></td>'
                f"<td>{escape(str(result.get('Score', '')))}</td>"
                "</tr>"
            )

        sections.append(
            '<div class="last-five-team">'
            f'<div class="last-five-team-label">{escape(str(team_name))}</div>'
            '<table class="last-five-table">'
            "<thead><tr><th>Date</th><th>Opponent</th><th>Result</th><th>Score</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
            "</div>"
        )

    return "".join(sections) if sections else "<p>No recent completed games found.</p>"


def get_numeric_value(row, column_name):
    value = get_row_value(row, column_name, "")
    try:
        return float(str(value).replace("%", "").strip())
    except ValueError:
        return None


def average_available_values(values):
    numbers = [
        value
        for value in values
        if value is not None and not pd.isna(value)
    ]
    if not numbers:
        return None

    return sum(numbers) / len(numbers)


def format_pressure_value(value, suffix="", decimals=1):
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.{decimals}f}{suffix}"


def first_inning_pressure_rows(row):
    signals = [
        {
            "name": "Pitcher YRFI",
            "value": average_available_values([
                get_numeric_value(row, "Away Pitcher YRFI %"),
                get_numeric_value(row, "Home Pitcher YRFI %"),
            ]),
            "suffix": "%",
            "decimals": 1,
            "nrfi_threshold": 18,
            "yrfi_threshold": 38,
            "nrfi_read": "NRFI <= 18.0%",
            "yrfi_read": "YRFI >= 38.0%",
        },
        {
            "name": "Offense YRFI",
            "value": average_available_values([
                get_numeric_value(row, "Away Offense YRFI %"),
                get_numeric_value(row, "Home Offense YRFI %"),
            ]),
            "suffix": "%",
            "decimals": 1,
            "nrfi_threshold": 20,
            "yrfi_threshold": 35,
            "nrfi_read": "NRFI <= 20.0%",
            "yrfi_read": "YRFI >= 35.0%",
        },
        {
            "name": "1st ERA",
            "value": average_available_values([
                get_numeric_value(row, "Away 1st ERA"),
                get_numeric_value(row, "Home 1st ERA"),
            ]),
            "suffix": "",
            "decimals": 2,
            "nrfi_threshold": 3.00,
            "yrfi_threshold": 6.00,
            "nrfi_read": "NRFI <= 3.00",
            "yrfi_read": "YRFI >= 6.00",
        },
        {
            "name": "1st WHIP",
            "value": average_available_values([
                get_numeric_value(row, "Away 1st WHIP"),
                get_numeric_value(row, "Home 1st WHIP"),
            ]),
            "suffix": "",
            "decimals": 2,
            "nrfi_threshold": 1.00,
            "yrfi_threshold": 1.60,
            "nrfi_read": "NRFI <= 1.00",
            "yrfi_read": "YRFI >= 1.60",
        },
        {
            "name": "Off 1st Run Avg",
            "value": average_available_values([
                get_numeric_value(row, "Away 1st Run Avg"),
                get_numeric_value(row, "Home 1st Run Avg"),
            ]),
            "suffix": "",
            "decimals": 2,
            "nrfi_threshold": 0.30,
            "yrfi_threshold": 0.60,
            "nrfi_read": "NRFI <= 0.30",
            "yrfi_read": "YRFI >= 0.60",
        },
    ]

    rows = []
    counts = {"YRFI": 0, "NRFI": 0, "Neutral": 0}

    for signal in signals:
        value = signal["value"]
        if value is None or pd.isna(value):
            direction = "Neutral"
            read = "Data unavailable"
        elif value <= signal["nrfi_threshold"]:
            direction = "NRFI"
            read = signal["nrfi_read"]
        elif value >= signal["yrfi_threshold"]:
            direction = "YRFI"
            read = signal["yrfi_read"]
        else:
            direction = "Neutral"
            read = "Between thresholds"

        counts[direction] += 1
        rows.append({
            "Signal": signal["name"],
            "Value": format_pressure_value(value, signal["suffix"], signal["decimals"]),
            "Direction": direction,
            "Model Read": read,
        })

    return rows, counts


def first_inning_watch_label(row):
    pick = get_row_value(row, "First Inning Pick", "No Edge")
    confidence = get_row_value(row, "First Inning Confidence", "No Edge")
    signal_type = str(get_row_value(row, "First Inning Signal Type", "")).lower()
    score = get_numeric_value(row, "First Inning Score")

    if not is_no_edge_pick(pick) or confidence != "No Edge":
        return None

    if score is None:
        return None

    nrfi_signals = ["one_sided_nrfi", "two_sided_nrfi", "mixed_yrfi_nrfi", "neutral"]
    yrfi_signals = ["one_sided_yrfi", "two_sided_yrfi", "mixed_yrfi_nrfi", "neutral"]

    if signal_type in nrfi_signals:
        if 58 <= score <= 64:
            return "NRFI Watch"
        if 55 <= score <= 57:
            return "NRFI Lean"
    if signal_type in yrfi_signals:
        if 25 <= score <= 34:
            return "YRFI Watch"
        if 35 <= score <= 39:
            return "YRFI Lean"

    return None


def directional_team_label(row, winner_column, away_team=None, home_team=None):
    winner = get_row_value(row, winner_column, "")
    if is_no_edge_pick(winner):
        return None
    return replace_home_away(winner, away_team, home_team)


def range_label(score, watch_min, watch_max, lean_min, lean_max, watch_label, lean_label):
    if score is None:
        return None
    if watch_min <= score <= watch_max:
        return watch_label
    if lean_min <= score <= lean_max:
        return lean_label
    return None


def f5_watch_label(row, away_team=None, home_team=None):
    pick = get_row_value(row, "F5 Pick", "No Edge")
    if not is_no_edge_pick(pick):
        return None

    score = get_numeric_value(row, "F5 Score")
    label = range_label(score, 7.0, 11.9, 4.0, 6.9, "F5 Watch", "F5 Lean")
    if label is None:
        return None

    team = directional_team_label(row, "Starter Edge Winner", away_team, home_team)
    if team is None:
        team = directional_team_label(row, "Offensive Edge Winner", away_team, home_team)
    if team is None:
        return None

    return f"{team} {label}"


def full_game_watch_label(row, away_team=None, home_team=None):
    pick = get_row_value(row, "Full Game Pick", "No Edge")
    if not is_no_edge_pick(pick):
        return None

    score = get_numeric_value(row, "Full Game Score")
    label = range_label(score, 6.5, 8.9, 4.0, 6.4, "Game Watch", "Game Lean")
    if label is None:
        return None

    for winner_column in ["Starter Edge Winner", "Offensive Edge Winner", "Bullpen Edge Winner"]:
        team = directional_team_label(row, winner_column, away_team, home_team)
        if team is not None:
            return f"{team} {label}"

    return None


def discovery_labels(row):
    tracked_labels = get_row_value(row, "Tracked Discovery Labels", "")
    if tracked_labels:
        return [
            label.strip()
            for label in str(tracked_labels).split("|")
            if label.strip()
        ]

    snapshot_status = str(get_row_value(row, "Snapshot Status", "")).strip()
    game_status = str(get_row_value(row, "Status", "")).strip().lower()
    if snapshot_status == "Not Tracked":
        return []
    if snapshot_status == "Locked" and game_status not in ["", "scheduled", "pre-game", "preview", "postponed"]:
        return []

    away_team, home_team = split_game_name(get_row_value(row, "Game", ""))
    labels = [
        first_inning_watch_label(row),
        f5_watch_label(row, away_team, home_team),
        full_game_watch_label(row, away_team, home_team),
    ]
    return [label for label in labels if label]


def has_watch_label(row):
    return any("Watch" in label for label in discovery_labels(row))


def has_lean_label(row):
    return any("Lean" in label for label in discovery_labels(row))


def discovery_label_matches_filter(label, selected_filter):
    if selected_filter in ["All Games", "Top Looks"]:
        return True
    if selected_filter == "NRFI":
        return str(label).startswith("NRFI")
    if selected_filter == "YRFI":
        return str(label).startswith("YRFI")
    if selected_filter == "F5":
        return "F5" in str(label)
    if selected_filter == "Game":
        return "Game" in str(label)
    return False


def has_discovery_label(row, selected_filter, label_type):
    return any(
        label_type in label and discovery_label_matches_filter(label, selected_filter)
        for label in discovery_labels(row)
    )


def first_inning_pressure_summary(row):
    rows, counts = first_inning_pressure_rows(row)
    pick = get_row_value(row, "First Inning Pick", "No Edge")
    confidence = get_row_value(row, "First Inning Confidence", "No Edge")
    score = get_row_value(row, "First Inning Score", "N/A")
    watch_label = first_inning_watch_label(row)

    if watch_label is not None:
        model_read = (
            f"{watch_label}: directional pressure is present, "
            "but confirmation remains below pick threshold."
        )
    elif is_no_edge_pick(pick) or confidence == "No Edge":
        model_read = "No Edge: not enough confirmed pressure signals."
    else:
        model_read = f"{pick} ({confidence}): confirmed pressure signals support the edge."

    summary = (
        f"YRFI signals: {counts['YRFI']} | "
        f"NRFI signals: {counts['NRFI']} | "
        f"Neutral: {counts['Neutral']} | "
        f"Score: {score}"
    )
    return rows, summary, model_read


def direction_alignment(pick_direction, signal_direction):
    if pick_direction is None or signal_direction is None:
        return "Neutral"

    return "Confirms" if pick_direction == signal_direction else "Warning"


def team_alignment(pick, signal_team):
    if is_no_edge_pick(pick) or signal_team in [None, "", "No Edge", "Pass", "Away", "Home"]:
        return "Neutral"

    return "Confirms" if str(pick) == str(signal_team) else "Warning"


def signal_review_row(market, signal, data_read, alignment):
    return {
        "Market": market,
        "Signal": signal,
        "Read": data_read,
        "Alignment": alignment,
    }


def first_inning_signal_review(row):
    pick_direction = first_inning_signal_direction(row)
    league = get_numeric_value(row, "League YRFI %")
    rows = []

    pitcher_yrfi = average_available_values([
        get_numeric_value(row, "Away Pitcher YRFI %"),
        get_numeric_value(row, "Home Pitcher YRFI %"),
    ])
    if pitcher_yrfi is not None and league is not None:
        diff = pitcher_yrfi - league
        signal_direction = "high" if diff >= 3 else "low" if diff <= -3 else None
        rows.append(signal_review_row(
            "1st Inning",
            "Pitcher YRFI vs Lg Avg",
            f"{pitcher_yrfi:.1f}% ({diff:+.1f}%)",
            direction_alignment(pick_direction, signal_direction),
        ))

    offense_yrfi = average_available_values([
        get_numeric_value(row, "Away Offense YRFI %"),
        get_numeric_value(row, "Home Offense YRFI %"),
    ])
    if offense_yrfi is not None and league is not None:
        diff = offense_yrfi - league
        signal_direction = "high" if diff >= 3 else "low" if diff <= -3 else None
        rows.append(signal_review_row(
            "1st Inning",
            "Offense YRFI vs Lg Avg",
            f"{offense_yrfi:.1f}% ({diff:+.1f}%)",
            direction_alignment(pick_direction, signal_direction),
        ))

    first_era = average_available_values([
        get_numeric_value(row, "Away 1st ERA"),
        get_numeric_value(row, "Home 1st ERA"),
    ])
    if first_era is not None:
        signal_direction = "high" if first_era >= 5 else "low" if first_era <= 3.25 else None
        rows.append(signal_review_row(
            "1st Inning",
            "1st Inning ERA",
            f"{first_era:.2f}",
            direction_alignment(pick_direction, signal_direction),
        ))

    first_whip = average_available_values([
        get_numeric_value(row, "Away 1st WHIP"),
        get_numeric_value(row, "Home 1st WHIP"),
    ])
    if first_whip is not None:
        signal_direction = "high" if first_whip >= 1.45 else "low" if first_whip <= 1.10 else None
        rows.append(signal_review_row(
            "1st Inning",
            "1st Inning WHIP",
            f"{first_whip:.2f}",
            direction_alignment(pick_direction, signal_direction),
        ))

    first_run_avg = average_available_values([
        get_numeric_value(row, "Away 1st Run Avg"),
        get_numeric_value(row, "Home 1st Run Avg"),
    ])
    if first_run_avg is not None:
        signal_direction = "high" if first_run_avg >= 0.55 else "low" if first_run_avg <= 0.30 else None
        rows.append(signal_review_row(
            "1st Inning",
            "Offense 1st Run Avg",
            f"{first_run_avg:.2f}",
            direction_alignment(pick_direction, signal_direction),
        ))

    return rows


def edge_winner_team(row, winner_column, away_team, home_team):
    winner = get_row_value(row, winner_column, "No Edge")
    if winner == "Away":
        return away_team
    if winner == "Home":
        return home_team
    if winner in [away_team, home_team]:
        return winner
    return None


def lower_metric_team(row, away_column, home_column, away_team, home_team, min_gap):
    away_value = get_numeric_value(row, away_column)
    home_value = get_numeric_value(row, home_column)
    if away_value is None or home_value is None:
        return None, "N/A"

    gap = abs(away_value - home_value)
    read = f"{away_value:g} / {home_value:g}"
    if gap < min_gap:
        return None, read

    return (away_team if away_value < home_value else home_team), read


def build_signal_review(row, away_team, home_team):
    rows = first_inning_signal_review(row)

    f5_pick = get_row_value(row, "F5 Pick", "No Edge")
    starter_team = edge_winner_team(row, "Starter Edge Winner", away_team, home_team)
    rows.append(signal_review_row(
        "First 5",
        "Starter Edge",
        format_edge_factor(row, "Starter Edge Winner", "Starter Edge Margin", "Starter edge", away_team, home_team),
        team_alignment(f5_pick, starter_team),
    ))

    offense_team = edge_winner_team(row, "Offensive Edge Winner", away_team, home_team)
    rows.append(signal_review_row(
        "First 5",
        "Offensive Edge",
        format_edge_factor(row, "Offensive Edge Winner", "Offensive Edge Margin", "Offensive edge", away_team, home_team),
        team_alignment(f5_pick, offense_team),
    ))

    recent_team, recent_read = lower_metric_team(
        row,
        "Away Last 7 ERA",
        "Home Last 7 ERA",
        away_team,
        home_team,
        1.0,
    )
    rows.append(signal_review_row(
        "First 5",
        "Last 7 Starter ERA",
        recent_read,
        team_alignment(f5_pick, recent_team),
    ))

    full_pick = get_row_value(row, "Full Game Pick", "No Edge")
    rows.append(signal_review_row(
        "Full Game",
        "Starter Edge",
        format_edge_factor(row, "Starter Edge Winner", "Starter Edge Margin", "Starter edge", away_team, home_team),
        team_alignment(full_pick, starter_team),
    ))
    rows.append(signal_review_row(
        "Full Game",
        "Offensive Edge",
        format_edge_factor(row, "Offensive Edge Winner", "Offensive Edge Margin", "Offensive edge", away_team, home_team),
        team_alignment(full_pick, offense_team),
    ))

    bullpen_team = edge_winner_team(row, "Bullpen Edge Winner", away_team, home_team)
    rows.append(signal_review_row(
        "Full Game",
        "Bullpen Edge",
        format_edge_factor(row, "Bullpen Edge Winner", "Bullpen Edge Margin", "Bullpen edge", away_team, home_team),
        team_alignment(full_pick, bullpen_team),
    ))

    return rows


def render_signal_review(row, away_team, home_team):
    rows = build_signal_review(row, away_team, home_team)
    if not rows:
        return

    counts = {
        "Confirms": 0,
        "Warning": 0,
        "Neutral": 0,
    }
    for review_row in rows:
        counts[review_row["Alignment"]] = counts.get(review_row["Alignment"], 0) + 1

    st.markdown("### Signal Review")
    st.caption(
        f'{counts["Confirms"]} confirm - {counts["Warning"]} warning - '
        f'{counts["Neutral"]} neutral'
    )
    st.markdown(
        "| Market | Signal | Read | Alignment |\n"
        "|---|---|---|---|\n"
        + "\n".join(
            f"| {review_row['Market']} | {review_row['Signal']} | "
            f"{review_row['Read']} | {review_row['Alignment']} |"
            for review_row in rows
        )
    )


def signal_label(label, is_signal):
    text = str(label).replace("|", "\\|")
    if not is_signal:
        return text

    return f"**{text}**\\*"


def signal_value(value, is_signal):
    text = str(value).replace("|", "\\|")
    if not is_signal:
        return text

    return f"**{text}**"


def first_inning_signal_direction(row):
    pick = str(get_row_value(row, "First Inning Pick", "")).upper()
    if "YRFI" in pick:
        return "high"
    if "NRFI" in pick:
        return "low"

    return None


def values_in_signal_direction(away_value, home_value, direction, neutral=None):
    away_numeric = safe_compare_float(away_value)
    home_numeric = safe_compare_float(home_value)

    if direction is None or away_numeric is None or home_numeric is None:
        return False, False

    if neutral is not None:
        if direction == "high":
            return away_numeric > neutral, home_numeric > neutral
        return away_numeric < neutral, home_numeric < neutral

    if away_numeric == home_numeric:
        return False, False

    if direction == "high":
        return away_numeric > home_numeric, home_numeric > away_numeric

    return away_numeric < home_numeric, home_numeric < away_numeric


def safe_compare_float(value):
    if value in [None, "", "N/A", "TBD", "Unavailable"]:
        return None

    try:
        return float(str(value).replace("%", "").strip())
    except ValueError:
        return None


def signal_cells_by_direction(
    row,
    away_column,
    home_column,
    direction,
    away_display=None,
    home_display=None,
    neutral=None,
):
    away_value = get_row_value(row, away_column, "N/A")
    home_value = get_row_value(row, home_column, "N/A")
    away_signal, home_signal = values_in_signal_direction(
        away_value,
        home_value,
        direction,
        neutral,
    )

    return (
        signal_value(away_display if away_display is not None else away_value, away_signal),
        signal_value(home_display if home_display is not None else home_value, home_signal),
    )


def signal_cells_by_winner(row, away_column, home_column, winner_column, active=True):
    winner = get_row_value(row, winner_column, "No Edge")
    away_value = get_row_value(row, away_column, "N/A")
    home_value = get_row_value(row, home_column, "N/A")

    if not active:
        return signal_value(away_value, False), signal_value(home_value, False)

    return (
        signal_value(away_value, winner == "Away"),
        signal_value(home_value, winner == "Home"),
    )


def build_market_watch(row):
    away_fatigue = get_numeric_value(row, "Away Bullpen Fatigue")
    home_fatigue = get_numeric_value(row, "Home Bullpen Fatigue")
    starter_margin = get_numeric_value(row, "Starter Edge Margin") or 0
    bullpen_margin = get_numeric_value(row, "Bullpen Edge Margin") or 0
    away_era = get_numeric_value(row, "Away ERA")
    home_era = get_numeric_value(row, "Home ERA")
    away_whip = get_numeric_value(row, "Away WHIP")
    home_whip = get_numeric_value(row, "Home WHIP")

    both_bullpens_tired = (
        away_fatigue is not None and home_fatigue is not None
        and away_fatigue >= 8 and home_fatigue >= 8
    )
    both_bullpens_fresh = (
        away_fatigue is not None and home_fatigue is not None
        and away_fatigue <= 3 and home_fatigue <= 3
    )
    strong_starting_pitching = (
        away_era is not None and home_era is not None
        and away_whip is not None and home_whip is not None
        and ((away_era + home_era) / 2) <= 3.75
        and ((away_whip + home_whip) / 2) <= 1.22
    )

    if both_bullpens_tired:
        return "Scoring May Be Elevated", [
            "Both bullpens fatigued",
            "Elevated late-game scoring risk",
        ]

    if both_bullpens_fresh and strong_starting_pitching:
        return "Scoring May Be Limited", [
            "Fresh bullpens",
            "Strong starting pitching",
        ]

    if starter_margin >= 8 and bullpen_margin < 6:
        return "Live Monitor", [
            "Early starter edge detected",
            "Bullpen edge remains uncertain",
            "Recheck as pitch counts rise",
        ]

    return "No Clear Signal", [
        "No meaningful edge signal detected",
    ]


def render_market_watch(row):
    market_pick, reasons = build_market_watch(row)
    reason_items = "".join(
        f"""
        <div class="reason-item">
            <span class="reason-check">&#10003;</span>
            <span>{escape(reason)}</span>
        </div>
        """
        for reason in reasons[:4]
    )

    return f"""
    <div class="market-watch">
        <div class="market-heading">📈 Market Watch</div>
        <div class="market-pick">{escape(market_pick)}</div>
        <div class="market-why">Why?</div>
        <div class="reason-stack">{reason_items}</div>
    </div>
    """


def render_data_quality_notice(row):
    quality = get_row_value(row, "Model Data Quality", "Good")
    notes = get_row_value(row, "Model Data Quality Notes", "")

    if "Model Data Quality" not in row.index:
        quality_notes = []
        away_pitcher = get_row_value(row, "Away Pitcher", "N/A")
        home_pitcher = get_row_value(row, "Home Pitcher", "N/A")
        missing_pitchers = sum(
            pitcher in [None, "", "N/A", "Unavailable", "TBD"]
            for pitcher in [away_pitcher, home_pitcher]
        )

        away_source = get_row_value(row, "Away 1st Split Source", "Unavailable")
        home_source = get_row_value(row, "Home 1st Split Source", "Unavailable")
        first_sources = [away_source, home_source]

        core_bullpen_fields = [
            "Away 3 Day Bullpen Pitches",
            "Home 3 Day Bullpen Pitches",
            "Away 3 Day Relievers",
            "Home 3 Day Relievers",
            "Away Back-to-Back Arms",
            "Home Back-to-Back Arms",
        ]
        missing_bullpen_fields = [
            field for field in core_bullpen_fields
            if get_row_value(row, field, "N/A") in [None, "", "N/A", "Unavailable", "TBD"]
        ]

        if missing_pitchers == 2:
            quality_notes.append("Probable pitchers missing")
        elif missing_pitchers == 1:
            quality_notes.append("One probable pitcher missing")

        if all(source == "Unavailable" for source in first_sources):
            quality_notes.append("Pitcher first-inning data missing")
        elif any(source in ["Unavailable", "Estimated"] for source in first_sources):
            quality_notes.append("Pitcher first-inning data limited")

        if len(missing_bullpen_fields) == len(core_bullpen_fields):
            quality_notes.append("Bullpen workload data missing")

        if missing_pitchers == 2 or all(source == "Unavailable" for source in first_sources):
            quality = "Poor"
        elif quality_notes:
            quality = "Limited"
        else:
            quality = "Good"

        notes = "; ".join(quality_notes)

    if quality == "Good":
        return ""

    css_class = "data-quality-poor" if quality == "Poor" else "data-quality-limited"
    label = "Limited data" if quality == "Limited" else "Poor data"

    detail = f": {notes}" if notes else ""
    return f"""
    <div class="data-quality-notice {css_class}">
        <span>Data Quality: {escape(label)}{escape(detail)}</span>
    </div>
    """


def format_edge_factor(row, winner_column, margin_column, label, away_team=None, home_team=None):
    winner = get_row_value(row, winner_column, "Pass")
    margin = get_numeric_value(row, margin_column)

    if is_no_edge_pick(winner) or margin is None:
        return f"{label}: no clear edge"

    winner = replace_home_away(winner, away_team, home_team)
    return f"{label}: {winner} +{margin:g}"


def edge_signal_text(row, winner_column, margin_column, label, away_team=None, home_team=None):
    signal = format_edge_factor(row, winner_column, margin_column, label, away_team, home_team)
    if signal.endswith("no clear edge"):
        return f"{label}: no clear confirmation"

    return signal


def build_key_factors(row, view="first", away_team=None, home_team=None):
    factors = []

    if view == "first":
        pick = str(get_row_value(row, "First Inning Pick", "No Edge"))
        score = get_numeric_value(row, "First Inning Score")
        league_yrfi = get_numeric_value(row, "League YRFI %")
        pitcher_yrfi = average_available_values([
            get_numeric_value(row, "Away Pitcher YRFI %"),
            get_numeric_value(row, "Home Pitcher YRFI %"),
        ])
        offense_yrfi = average_available_values([
            get_numeric_value(row, "Away Offense YRFI %"),
            get_numeric_value(row, "Home Offense YRFI %"),
        ])
        matchup_summary = get_row_value(
            row,
            "1st Inning Matchup Summary",
            "No clear matchup pressure",
        )
        watch_label = first_inning_watch_label(row)

        if score is not None:
            if "YRFI" in pick.upper():
                factors.append(f"Score {score:g}: YRFI pressure above neutral")
            elif "NRFI" in pick.upper():
                factors.append(f"Score {score:g}: NRFI pressure below neutral")
            else:
                factors.append(f"Score {score:g}: no clear first-inning edge")

        if watch_label is not None:
            watch_direction = watch_label.replace(" Watch", "")
            watch_direction = watch_direction.replace(" Lean", "")
            factors.append(
                f"{watch_label}: {watch_direction} pressure below pick threshold"
            )

        if pitcher_yrfi is not None and league_yrfi is not None:
            direction = "above" if pitcher_yrfi >= league_yrfi else "below"
            factors.append(
                f"Pitcher YRFI avg {pitcher_yrfi:.1f}% is {direction} league {league_yrfi:.1f}%"
            )

        if matchup_summary not in [None, "", "N/A"]:
            factors.append(f"Matchup: {matchup_summary}")

        if len(factors) < 3 and offense_yrfi is not None and league_yrfi is not None:
            direction = "above" if offense_yrfi >= league_yrfi else "below"
            factors.append(
                f"Offense YRFI avg {offense_yrfi:.1f}% is {direction} league {league_yrfi:.1f}%"
            )

    elif view == "f5":
        factors.append(edge_signal_text(
            row,
            "Starter Edge Winner",
            "Starter Edge Margin",
            "Starter edge",
            away_team,
            home_team,
        ))
        factors.append(edge_signal_text(
            row,
            "Offensive Edge Winner",
            "Offensive Edge Margin",
            "Offensive edge",
            away_team,
            home_team,
        ))

    elif view == "full":
        factors.append(edge_signal_text(
            row,
            "Starter Edge Winner",
            "Starter Edge Margin",
            "Starter edge",
            away_team,
            home_team,
        ))
        factors.append(edge_signal_text(
            row,
            "Offensive Edge Winner",
            "Offensive Edge Margin",
            "Offensive edge",
            away_team,
            home_team,
        ))

        bullpen_winner = get_row_value(row, "Bullpen Edge Winner", "No Edge")
        bullpen_margin = get_numeric_value(row, "Bullpen Edge Margin") or 0
        if is_no_edge_pick(bullpen_winner) or bullpen_margin < 6:
            factors.append("Bullpen workload: no clear edge")
        else:
            bullpen_winner = replace_home_away(bullpen_winner, away_team, home_team)
            factors.append(f"Bullpen workload favors {bullpen_winner}")

    if not factors:
        factors.append("No major model imbalance detected")

    return factors[:4]


def render_key_factors(row, view="first", away_team=None, home_team=None):
    headings = {
        "first": "Key Factors: 1st Inning Edge",
        "f5": "Key Factors: First 5 Edge",
        "full": "Key Factors: Full Game Edge",
    }
    factor_items = "".join(
        f"""
        <div class="reason-item">
            <span class="reason-check">&#10003;</span>
            <span>{escape(factor)}</span>
        </div>
        """
        for factor in build_key_factors(row, view, away_team, home_team)
    )

    return f"""
    <div class="key-factors edge-factor-panel edge-factor-{escape(view)}">
        <div class="market-heading">{escape(headings.get(view, "Key Factors"))}</div>
        <div class="reason-stack">{factor_items}</div>
    </div>
    """


def render_key_factor_panels(row, away_team=None, home_team=None):
    panels = "".join(
        render_key_factors(row, view, away_team, home_team)
        for view in ["first", "f5", "full"]
    )

    return f'<div class="edge-factor-panels">{panels}</div>'


def game_anchor(game_name):
    slug = re.sub(r"[^a-z0-9]+", "-", str(game_name).lower()).strip("-")
    return f"game-{slug}"


def confidence_sort_value(confidence):
    return {
        "A+": 5,
        "A": 4,
        "B": 3,
        "C": 2,
        "D": 1,
    }.get(str(confidence), 0)


def game_matchup_label(game_name):
    away_team, home_team = split_game_name(game_name)
    return f"{away_team} at {home_team}"


def top_look_link(row):
    return f'<a class="top-look-link" href="#{game_anchor(row["Game"])}">Review game card</a>'


def best_row(rows, confidence_column, score_column=None, require_score=False):
    if rows.empty:
        return None

    ranked = rows.copy()
    ranked["_confidence_rank"] = ranked[confidence_column].map(confidence_sort_value)
    ranked["_score_rank"] = 0
    if score_column and score_column in ranked.columns:
        ranked["_score_rank"] = ranked[score_column].apply(
            lambda value: get_numeric_value({"value": value}, "value") or 0
        )
        if require_score:
            ranked = ranked[ranked["_score_rank"] > 0]
            if ranked.empty:
                return None
    elif require_score:
        return None

    ranked = ranked.sort_values(
        ["_confidence_rank", "_score_rank"],
        ascending=False,
        na_position="last",
    )
    return ranked.iloc[0]


def format_score_meta(label, row, score_column, confidence_column):
    score = get_numeric_value(row, score_column)
    confidence = get_row_value(row, confidence_column, "No Edge")
    if score is None:
        return f"{label} unavailable"

    return f"{label} {score:.1f} - Confidence {confidence}"


def build_top_looks(games):
    looks = []

    first_rows = games[
        ~games["First Inning Pick"].apply(is_no_edge_pick)
    ].copy()
    first_row = best_row(
        first_rows,
        "First Inning Confidence",
        "First Inning Score",
        require_score=True,
    )
    if first_row is None:
        looks.append({
            "title": "1st Inning: No edge found",
            "meta": "No qualified YRFI or NRFI look on this slate.",
            "why": "",
            "link": "",
            "game": "",
        })
    else:
        away_team, home_team = split_game_name(first_row["Game"])
        first_pick = format_decision_pick(
            first_row["First Inning Pick"],
            first_row["First Inning Confidence"],
            away_team,
            home_team,
            market="first",
        )
        looks.append({
            "title": f'1st Inning {first_pick}: {game_matchup_label(first_row["Game"])}',
            "meta": format_score_meta(
                "Model score",
                first_row,
                "First Inning Score",
                "First Inning Confidence",
            ),
            "why": "First-inning model threshold cleared",
            "link": top_look_link(first_row),
            "game": first_row["Game"],
        })

    f5_rows = games[
        ~games["F5 Pick"].apply(is_no_edge_pick)
    ].copy()
    f5_row = best_row(
        f5_rows,
        "F5 Confidence",
        "F5 Score",
        require_score=True,
    )
    if f5_row is None:
        looks.append({
            "title": "First 5: No edge found",
            "meta": "No qualified First 5 look on this slate.",
            "why": "",
            "link": "",
            "game": "",
        })
    else:
        away_team, home_team = split_game_name(f5_row["Game"])
        f5_pick = format_decision_pick(
            f5_row["F5 Pick"],
            f5_row["F5 Confidence"],
            away_team,
            home_team,
            market="f5",
        )
        looks.append({
            "title": f'First 5 {f5_pick}: {game_matchup_label(f5_row["Game"])}',
            "meta": format_score_meta(
                "F5 edge",
                f5_row,
                "F5 Score",
                "F5 Confidence",
            ),
            "why": "Starter/offense model supports First 5 look",
            "link": top_look_link(f5_row),
            "game": f5_row["Game"],
        })

    bullpen_rows = games[
        (games["Away Bullpen Fatigue"] >= 8)
        | (games["Home Bullpen Fatigue"] >= 8)
        | (~games["Bullpen Edge Winner"].apply(is_no_edge_pick))
    ].copy()
    if bullpen_rows.empty:
        looks.append({
            "title": "Bullpen Workload Watch: No signal found",
            "meta": "No elevated bullpen risk signal on this slate.",
            "why": "",
            "link": "",
            "game": "",
        })
    else:
        bullpen_rows["_fatigue_max"] = bullpen_rows[
            ["Away Bullpen Fatigue", "Home Bullpen Fatigue"]
        ].max(axis=1)
        bullpen_row = bullpen_rows.sort_values(
            ["_fatigue_max", "Bullpen Edge Margin"],
            ascending=False,
            na_position="last",
        ).iloc[0]
        away_team, home_team = split_game_name(bullpen_row["Game"])
        looks.append({
            "title": f'Bullpen Workload Watch: {game_matchup_label(bullpen_row["Game"])}',
            "meta": f'Fatigue {bullpen_row["_fatigue_max"]} - Bullpen edge {get_row_value(bullpen_row, "Bullpen Edge Margin", "N/A")}',
            "why": f'{away_team} bullpen {bullpen_row["Away Bullpen Status"]} / {home_team} bullpen {bullpen_row["Home Bullpen Status"]}',
            "link": top_look_link(bullpen_row),
            "game": bullpen_row["Game"],
        })

    return looks


def top_look_games(games):
    return {
        look["game"]
        for look in build_top_looks(games)
        if look.get("game")
    }


def render_top_looks(games):
    items = []
    for index, look in enumerate(build_top_looks(games), start=1):
        why = f'<div class="top-look-why">Why: {escape(look["why"])}</div>' if look["why"] else ""
        link = look["link"]
        items.append(
            '<div class="top-look-item">'
            f'<div class="top-look-rank">{index}</div>'
            '<div>'
            f'<div class="top-look-title">{escape(look["title"])}</div>'
            f'<div class="top-look-meta">{escape(look["meta"])}</div>'
            f'{why}'
            f'{link}'
            '</div>'
            '</div>'
        )

    return (
        '<div class="model-favorite top-looks">'
        '<div class="model-label">TOP LOOKS</div>'
        '<div class="top-look-list">'
        f'{"".join(items)}'
        '</div>'
        '</div>'
    )


def performance_hit_rate(row):
    completed = (row.get("hits") or 0) + (row.get("misses") or 0) + (row.get("pushes") or 0)
    if completed == 0:
        return "N/A"

    return f"{((row.get('hits') or 0) / completed) * 100:.0f}%"


def parse_history_score_result(result):
    text = str(result or "")
    match = re.match(r"^(?:After 5|Final|In Progress):\s*(.+?)\s+(\d+),\s*(.+?)\s+(\d+)$", text)
    if not match:
        return None

    return {
        "away_team": match.group(1),
        "away_score": int(match.group(2)),
        "home_team": match.group(3),
        "home_score": int(match.group(4)),
    }


def grade_history_first_inning(pick, result):
    if str(pick).strip() == "Not Tracked":
        return "Not Tracked"
    if is_no_edge_pick(pick):
        return "No Edge"

    result_text = str(result or "").strip().upper()
    if result_text in ["", "PENDING", "IN PROGRESS"]:
        return "Pending"
    if result_text not in ["YRFI", "NRFI"]:
        return "Pending"

    return "Hit" if str(pick).strip().upper() == result_text else "Miss"


def grade_history_team_pick(pick, result, completed_prefix):
    if str(pick).strip() == "Not Tracked":
        return "Not Tracked"
    if is_no_edge_pick(pick):
        return "No Edge"

    result_text = str(result or "")
    if not result_text.startswith(completed_prefix):
        return "Pending"

    parsed = parse_history_score_result(result_text)
    if parsed is None:
        return "Pending"

    if parsed["away_score"] == parsed["home_score"]:
        return "Push"

    winner = parsed["away_team"] if parsed["away_score"] > parsed["home_score"] else parsed["home_team"]
    return "Hit" if str(pick).strip() == winner else "Miss"


def grade_history_outcome(row):
    market = str(row.get("base_market") or row.get("market") or "")
    if market == "1st Inning":
        return grade_history_first_inning(row.get("pick"), row.get("result"))
    if market == "First 5":
        return grade_history_team_pick(row.get("pick"), row.get("result"), "After 5:")
    if market == "Full Game":
        return grade_history_team_pick(row.get("pick"), row.get("result"), "Final:")

    return "No Edge" if is_no_edge_pick(row.get("pick")) else "Pending"


def summarize_history_rows(rows, tracking_segment="Official"):
    summary = {}
    market_order = {"1st Inning": 1, "First 5": 2, "Full Game": 3}

    for row in rows:
        row_segment = row.get("tracking_segment") or "Official"
        if tracking_segment != "All" and row_segment != tracking_segment:
            continue
        outcome = row.get("outcome") or grade_history_outcome(row)
        if outcome in ["No Edge", "Not Tracked"]:
            continue

        market = row.get("base_market") or row.get("market")
        if market not in summary:
            summary[market] = {
                "market": market,
                "tracking_segment": row_segment,
                "total": 0,
                "hits": 0,
                "misses": 0,
                "pushes": 0,
                "pending": 0,
            }

        summary[market]["total"] += 1
        if outcome == "Hit":
            summary[market]["hits"] += 1
        elif outcome == "Miss":
            summary[market]["misses"] += 1
        elif outcome == "Push":
            summary[market]["pushes"] += 1
        elif outcome == "Pending":
            summary[market]["pending"] += 1

    return sorted(summary.values(), key=lambda row: market_order.get(row["market"], 99))


def safe_load_model_versions():
    try:
        from model_history import load_model_versions

        return load_model_versions()
    except (ImportError, AttributeError):
        return []


def empty_history_diagnostics(storage_backend="Unavailable", module_path="N/A", error=None):
    return {
        "storage_backend": storage_backend,
        "db_path": "N/A",
        "module_path": module_path,
        "diagnostic_error": error,
        "using_fallback": False,
        "total_rows": 0,
        "completed_rows": 0,
        "pending_rows": 0,
        "no_edge_rows": 0,
        "not_tracked_rows": 0,
        "result_updated_rows": 0,
        "model_versions": [],
        "earliest_slate_date": None,
        "latest_slate_date": None,
        "earliest_snapshot": None,
        "latest_snapshot": None,
        "latest_update": None,
    }


def direct_load_history_diagnostics(previous_error=None):
    try:
        import model_history

        module_path = getattr(model_history, "__file__", "N/A")
        db_path = getattr(model_history, "DB_PATH", None)
        if db_path is None:
            return empty_history_diagnostics(
                module_path=module_path,
                error=f"{previous_error}; DB_PATH unavailable",
            )

        diagnostics = empty_history_diagnostics(
            storage_backend="SQLite fallback",
            module_path=module_path,
            error=previous_error,
        )
        diagnostics["using_fallback"] = True
        diagnostics["db_path"] = str(db_path)
        if not db_path.exists():
            return diagnostics

        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            model_history.init_db(connection)
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_rows,
                    SUM(CASE WHEN outcome IN ('Hit', 'Miss', 'Push') THEN 1 ELSE 0 END) AS completed_rows,
                    SUM(CASE WHEN outcome = 'Pending' THEN 1 ELSE 0 END) AS pending_rows,
                    SUM(CASE WHEN outcome = 'No Edge' THEN 1 ELSE 0 END) AS no_edge_rows,
                    SUM(CASE WHEN outcome = 'Not Tracked' THEN 1 ELSE 0 END) AS not_tracked_rows,
                    SUM(CASE WHEN updated_at != created_at THEN 1 ELSE 0 END) AS result_updated_rows,
                    MIN(slate_date) AS earliest_slate_date,
                    MAX(slate_date) AS latest_slate_date,
                    MIN(created_at) AS earliest_snapshot,
                    MAX(created_at) AS latest_snapshot,
                    MAX(updated_at) AS latest_update
                FROM model_history
                """
            ).fetchone()
            versions = connection.execute(
                """
                SELECT model_version
                FROM model_history
                GROUP BY model_version
                ORDER BY MAX(updated_at) DESC, model_version DESC
                """
            ).fetchall()

        if row:
            diagnostics.update(
                {
                    "total_rows": row["total_rows"] or 0,
                    "completed_rows": row["completed_rows"] or 0,
                    "pending_rows": row["pending_rows"] or 0,
                    "no_edge_rows": row["no_edge_rows"] or 0,
                    "not_tracked_rows": row["not_tracked_rows"] or 0,
                    "result_updated_rows": row["result_updated_rows"] or 0,
                    "earliest_slate_date": row["earliest_slate_date"],
                    "latest_slate_date": row["latest_slate_date"],
                    "earliest_snapshot": row["earliest_snapshot"],
                    "latest_snapshot": row["latest_snapshot"],
                    "latest_update": row["latest_update"],
                    "model_versions": [version["model_version"] for version in versions],
                }
            )

        return diagnostics
    except Exception as exc:
        combined_error = f"{previous_error}; direct fallback {type(exc).__name__}: {exc}"
        return empty_history_diagnostics(error=combined_error)


def safe_load_history_diagnostics():
    try:
        from model_history import load_history_diagnostics

        diagnostics = load_history_diagnostics()
        diagnostics["diagnostic_error"] = None
        diagnostics["using_fallback"] = False
        return diagnostics
    except Exception as exc:
        return direct_load_history_diagnostics(f"{type(exc).__name__}: {exc}")


def latest_history_slate_date(diagnostics=None):
    diagnostics = diagnostics or safe_load_history_diagnostics()
    latest_slate_date = diagnostics.get("latest_slate_date")
    if not latest_slate_date:
        return None

    try:
        return datetime.fromisoformat(str(latest_slate_date)).date()
    except ValueError:
        return None


def safe_load_performance_export_rows(model_version=None):
    try:
        from model_history import load_performance_export_rows

        rows = load_performance_export_rows(model_version)
        return recompute_export_outcomes(rows)
    except Exception:
        return direct_load_performance_export_rows(model_version)


def recompute_export_outcomes(rows):
    export_rows = []
    for row in rows:
        export_row = dict(row)
        if "stored_outcome" not in export_row and "outcome" in export_row:
            export_row["stored_outcome"] = export_row.get("outcome")
        export_row["outcome"] = grade_history_outcome(export_row)
        export_rows.append(export_row)

    return export_rows


def history_row_matches_filters(row, market=None, days=None, confidence=None, exact_date=None):
    if is_no_edge_pick(row.get("pick")):
        return False
    if market and market != "All" and (row.get("base_market") or row.get("market")) != market:
        return False
    if confidence and confidence != "All" and row.get("confidence") != confidence:
        return False
    if exact_date and str(row.get("slate_date")) != str(exact_date):
        return False
    if days:
        try:
            row_date = datetime.fromisoformat(str(row.get("slate_date"))).date()
            cutoff = datetime.utcnow().date() - timedelta(days=int(days))
            if row_date < cutoff:
                return False
        except (TypeError, ValueError):
            return False

    return True


def format_snapshot_time(value):
    if value in [None, "", "N/A"]:
        return "N/A"

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        eastern = parsed.astimezone(ZoneInfo("America/New_York"))
        hour = eastern.hour % 12 or 12
        suffix = "AM" if eastern.hour < 12 else "PM"
        return f"{eastern.month}/{eastern.day}/{eastern.year}, {hour}:{eastern.minute:02d} {suffix} ET"
    except Exception:
        return str(value)


def format_snapshot_caption(history_rows):
    timestamps = [
        row.get("updated_at") or row.get("created_at")
        for row in history_rows
        if row.get("updated_at") or row.get("created_at")
    ]
    if not timestamps:
        return "Snapshot as of: N/A"

    return f"Snapshot as of: {format_snapshot_time(max(timestamps))}"


def format_game_status_line(row):
    game_time = get_row_value(row, "Game Time", "N/A")
    status = get_row_value(row, "Status", "N/A")
    snapshot_status = str(get_row_value(row, "Snapshot Status", "")).strip()
    base_line = f"{game_time} - {status}"

    if snapshot_status == "Locked":
        return f"🔒 {base_line}"
    if snapshot_status == "Not Tracked":
        return f"⚠ Not Tracked - {base_line}"

    return base_line


def format_local_card_time(row):
    raw_value = row.get("Sort Date")
    if raw_value in [None, "", "N/A"] or pd.isna(raw_value):
        raw_value = row.get("Game Date")
    if raw_value in [None, "", "N/A"] or pd.isna(raw_value):
        return str(row.get("Game Time", "TBD"))

    try:
        parsed = pd.to_datetime(raw_value)
        if parsed.tzinfo is None:
            parsed = parsed.tz_localize(ZoneInfo(FALLBACK_TIMEZONE))
        local_time = parsed.tz_convert(ZoneInfo(display_timezone))
        hour = local_time.hour % 12 or 12
        suffix = "AM" if local_time.hour < 12 else "PM"
        timezone_name = local_time.tzname() or display_timezone
        return (
            f"{local_time.strftime('%a %b')} {local_time.day}, "
            f"{hour}:{local_time.minute:02d} {suffix} {timezone_name}"
        )
    except Exception:
        return str(row.get("Game Time", "TBD"))


def safe_load_performance_summary(
    model_version=None,
    market=None,
    days=None,
    confidence=None,
    exact_date=None,
    tracking_segment="Official",
):
    rows = safe_load_performance_export_rows(model_version)
    effective_confidence = confidence if tracking_segment == "Official" else "All"
    filtered_rows = [
        row
        for row in rows
        if history_row_matches_filters(
            row,
            market=market,
            days=days,
            confidence=effective_confidence,
            exact_date=exact_date,
        )
    ]
    return summarize_history_rows(filtered_rows, tracking_segment=tracking_segment)


def safe_load_slate_history_rows(model_version, slate_date):
    try:
        return load_slate_history_rows(model_version, slate_date)
    except Exception:
        return []


def safe_load_wnba_slate_history_rows(model_version, market_version, slate_date):
    try:
        rows = load_wnba_history(
            model_version=model_version,
            market_version=market_version,
        )
    except Exception:
        return []

    target_date = str(slate_date)
    return [
        row
        for row in rows
        if str(row.get("slate_date", "")) == target_date
    ]


def safe_load_nba_slate_history_rows(model_version, market_version, slate_date):
    try:
        rows = load_nba_history(
            model_version=model_version,
            market_version=market_version,
        )
    except Exception:
        return []

    target_date = str(slate_date)
    return [
        row
        for row in rows
        if str(row.get("slate_date", "")) == target_date
    ]


def safe_load_nhl_slate_history_rows(model_version, market_version, slate_date):
    try:
        rows = load_nhl_history(
            model_version=model_version,
            market_version=market_version,
        )
    except Exception:
        return []

    target_date = str(slate_date)
    return [
        row
        for row in rows
        if str(row.get("slate_date", "")) == target_date
    ]


def safe_load_cbb_slate_history_rows(model_version, market_version, slate_date):
    try:
        rows = load_cbb_history(
            model_version=model_version,
            market_version=market_version,
        )
    except Exception:
        return []

    target_date = str(slate_date)
    return [
        row
        for row in rows
        if str(row.get("slate_date", "")) == target_date
    ]


def safe_load_mls_slate_history_rows(model_version, market_version, slate_date):
    try:
        rows = load_mls_history(
            model_version=model_version,
            market_version=market_version,
        )
    except Exception:
        return []

    target_date = str(slate_date)
    return [
        row
        for row in rows
        if str(row.get("slate_date", "")) == target_date
    ]


def apply_tracked_snapshot_to_games(games, model_version, slate_date, history_rows=None):
    history_rows = (
        history_rows
        if history_rows is not None
        else safe_load_slate_history_rows(model_version, slate_date)
    )
    if not history_rows:
        return games

    snapshot = {
        (row.get("game"), row.get("market")): row
        for row in history_rows
    }
    market_columns = {
        "1st Inning": {
            "pick": "First Inning Pick",
            "confidence": "First Inning Confidence",
            "score": "First Inning Score",
            "signal_type": "First Inning Signal Type",
        },
        "First 5": {
            "pick": "F5 Pick",
            "confidence": "F5 Confidence",
            "score": "F5 Score",
        },
        "Full Game": {
            "pick": "Full Game Pick",
            "confidence": "Full Game Confidence",
            "score": "Full Game Score",
        },
    }

    tracked_games = games.copy()
    for column_name in ["Snapshot Status", "Locked At", "Snapshot Updated At", "Tracked Discovery Labels"]:
        if column_name not in tracked_games.columns:
            tracked_games[column_name] = ""

    for index, row in tracked_games.iterrows():
        game_name = row.get("Game")
        game_snapshot_rows = [
            snapshot_row
            for (snapshot_game, _), snapshot_row in snapshot.items()
            if snapshot_game == game_name
        ]
        if game_snapshot_rows:
            discovery_labels_for_game = [
                snapshot_row.get("discovery_label")
                for snapshot_row in game_snapshot_rows
                if (snapshot_row.get("tracking_segment") or "Official") in ["Watch", "Lean"]
                and snapshot_row.get("snapshot_status") != "Not Tracked"
                and snapshot_row.get("discovery_label")
            ]
            tracked_games.at[index, "Tracked Discovery Labels"] = " | ".join(discovery_labels_for_game)
            if any(
                snapshot_row.get("snapshot_status") == "Not Tracked"
                for snapshot_row in game_snapshot_rows
                if (snapshot_row.get("tracking_segment") or "Official") == "Official"
            ):
                tracked_games.at[index, "Snapshot Status"] = "Not Tracked"
            elif any(
                snapshot_row.get("snapshot_status") == "Locked"
                for snapshot_row in game_snapshot_rows
                if (snapshot_row.get("tracking_segment") or "Official") == "Official"
            ):
                tracked_games.at[index, "Snapshot Status"] = "Locked"
            else:
                tracked_games.at[index, "Snapshot Status"] = "Pregame"
            locked_values = [
                snapshot_row.get("locked_at")
                for snapshot_row in game_snapshot_rows
                if snapshot_row.get("locked_at")
            ]
            updated_values = [
                snapshot_row.get("updated_at")
                for snapshot_row in game_snapshot_rows
                if snapshot_row.get("updated_at")
            ]
            tracked_games.at[index, "Locked At"] = max(locked_values) if locked_values else ""
            tracked_games.at[index, "Snapshot Updated At"] = max(updated_values) if updated_values else ""

        for market, columns in market_columns.items():
            tracked_row = snapshot.get((game_name, market))
            if not tracked_row:
                continue
            for source_key, column_name in columns.items():
                value = tracked_row.get(source_key)
                if value is not None and column_name in tracked_games.columns:
                    tracked_games.at[index, column_name] = value

    return tracked_games


def direct_load_performance_export_rows(model_version=None):
    try:
        import model_history

        db_path = getattr(model_history, "DB_PATH", None)
        if db_path is None or not db_path.exists():
            return []

        where_clause = ""
        params = []
        if model_version:
            where_clause = "WHERE model_version = ?"
            params.append(model_version)

        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            model_history.init_db(connection)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(model_history)").fetchall()
            }
            signal_type_select = "signal_type" if "signal_type" in columns else "NULL AS signal_type"
            base_market_select = "base_market" if "base_market" in columns else "market AS base_market"
            tracking_segment_select = (
                "tracking_segment"
                if "tracking_segment" in columns
                else "'Official' AS tracking_segment"
            )
            discovery_label_select = (
                "discovery_label"
                if "discovery_label" in columns
                else "NULL AS discovery_label"
            )
            discovery_type_select = (
                "discovery_type"
                if "discovery_type" in columns
                else "NULL AS discovery_type"
            )
            discovery_side_select = (
                "discovery_side"
                if "discovery_side" in columns
                else "NULL AS discovery_side"
            )
            rows = connection.execute(
                f"""
                SELECT
                    model_version,
                    slate_date,
                    market,
                    {base_market_select},
                    {tracking_segment_select},
                    {discovery_label_select},
                    {discovery_type_select},
                    {discovery_side_select},
                    game,
                    pick,
                    confidence,
                    score,
                    {signal_type_select},
                    result,
                    outcome,
                    status,
                    created_at,
                    updated_at,
                    locked_at,
                    snapshot_status
                FROM model_history
                {where_clause}
                ORDER BY date(slate_date) DESC,
                    CASE COALESCE(base_market, market)
                        WHEN '1st Inning' THEN 1
                        WHEN 'First 5' THEN 2
                        WHEN 'Full Game' THEN 3
                        ELSE 4
                    END,
                    CASE COALESCE(tracking_segment, 'Official')
                        WHEN 'Official' THEN 1
                        WHEN 'Watch' THEN 2
                        WHEN 'Lean' THEN 3
                        ELSE 4
                    END,
                    game
                """,
                params,
            ).fetchall()

        export_rows = []
        for row in rows:
            export_row = dict(row)
            export_row["stored_outcome"] = export_row.pop("outcome", None)
            export_row["outcome"] = grade_history_outcome(export_row)
            export_rows.append(export_row)

        return export_rows
    except Exception:
        return []


def rows_to_csv(rows):
    if not rows:
        return ""

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def render_model_performance_legacy_unused():
    summary_cols = []
    for index, row in enumerate(summary_rows):
        completed = (row.get("hits") or 0) + (row.get("misses") or 0) + (row.get("pushes") or 0)
        pending = row.get("pending") or 0
        record = f"{row.get('hits') or 0}-{row.get('misses') or 0}"
        if row.get("pushes"):
            record = f"{record}-{row.get('pushes')}"
        with summary_cols[index]:
            st.metric(
                row["market"],
                performance_hit_rate(row),
                f"{record} - {pending} pending",
            )
            st.caption(f"{completed} completed")

    if not detail_rows:
        st.info("No detailed rows match the selected filters.")
        return

    detail_df = pd.DataFrame(detail_rows)
    detail_df = detail_df.rename(columns={
        "slate_date": "Slate",
        "market": "Market",
        "game": "Game",
        "pick": "Pick",
        "confidence": "Confidence",
        "score": "Score",
        "result": "Result",
        "outcome": "Outcome",
        "status": "Status",
        "created_at": "Snapshot",
        "updated_at": "Updated",
    })
    st.dataframe(
        detail_df[
            [
                "Slate",
                "Market",
                "Game",
                "Pick",
                "Confidence",
                "Score",
                "Result",
                "Outcome",
                "Status",
            ]
        ],
        hide_index=True,
        use_container_width=True,
    )


def render_model_performance(model_version, slate_date):
    st.markdown("### Model Performance")

    diagnostics = safe_load_history_diagnostics()
    history_today = latest_history_slate_date(diagnostics) or slate_date

    available_versions = safe_load_model_versions()
    version_options = [model_version]
    version_options.extend(
        version
        for version in available_versions
        if version != model_version
    )
    model_filter_options = [f"Current {model_version}", *version_options[1:], "All"]

    filter_cols = st.columns([1, 1, 1, 1])
    with filter_cols[0]:
        market_filter = st.selectbox(
            "Market",
            ["All", "1st Inning", "First 5", "Full Game"],
            key="performance_market_filter",
        )
    with filter_cols[1]:
        window_filter = st.selectbox(
            "Day(s)",
            ["Today", "Yesterday", "Last 7", "Last 30", "All"],
            key="performance_window_filter",
        )
    with filter_cols[2]:
        confidence_filter = st.selectbox(
            "Confidence",
            ["All", "A+", "A", "B", "C"],
            key="performance_confidence_filter",
        )
    with filter_cols[3]:
        selected_model_filter = st.selectbox(
            "Model",
            model_filter_options,
            key="performance_model_filter",
        )

    if selected_model_filter == "All":
        selected_model_version = None
        model_label = "All models"
    elif selected_model_filter.startswith("Current "):
        selected_model_version = model_version
        model_label = selected_model_filter
    else:
        selected_model_version = selected_model_filter
        model_label = f"Model {selected_model_filter}"

    day_filters = {
        "Today": {"exact_date": history_today, "label": f"Today ({history_today})"},
        "Yesterday": {
            "exact_date": history_today - timedelta(days=1),
            "label": f"Yesterday ({history_today - timedelta(days=1)})",
        },
        "Last 7": 7,
        "Last 30": 30,
        "All": {"days": None, "exact_date": None, "label": "All history"},
    }[window_filter]
    if isinstance(day_filters, dict):
        days = day_filters.get("days")
        exact_date = day_filters.get("exact_date")
        day_label = day_filters["label"]
    else:
        days = day_filters
        exact_date = None
        day_label = f"{window_filter} days"

    summary_rows = safe_load_performance_summary(
        selected_model_version,
        market=market_filter,
        days=days,
        confidence=confidence_filter,
        exact_date=exact_date,
        tracking_segment="Official",
    )
    watch_summary_rows = safe_load_performance_summary(
        selected_model_version,
        market=market_filter,
        days=days,
        confidence="All",
        exact_date=exact_date,
        tracking_segment="Watch",
    )
    lean_summary_rows = safe_load_performance_summary(
        selected_model_version,
        market=market_filter,
        days=days,
        confidence="All",
        exact_date=exact_date,
        tracking_segment="Lean",
    )

    export_rows = safe_load_performance_export_rows(selected_model_version)

    with st.expander("Performance History Diagnostics"):
        diag_cols = st.columns(4)
        with diag_cols[0]:
            st.metric("Rows", diagnostics["total_rows"])
        with diag_cols[1]:
            st.metric("Completed", diagnostics["completed_rows"])
        with diag_cols[2]:
            st.metric("Pending", diagnostics["pending_rows"])
        with diag_cols[3]:
            st.metric("No Edge", diagnostics["no_edge_rows"])

        st.caption(
            "Snapshot rule: pick, confidence, and score can update before lock; "
            "locked rows update only result, outcome, status, and updated timestamp."
        )
        st.caption(f"Storage: {diagnostics['storage_backend']}")
        st.code(diagnostics["db_path"], language="text")
        if diagnostics.get("using_fallback"):
            st.caption("Using direct DB fallback for diagnostics/export.")
        elif diagnostics.get("diagnostic_error"):
            st.caption(f"Diagnostic error: {diagnostics['diagnostic_error']}")
        st.caption(
            "Date range: "
            f"{diagnostics['earliest_slate_date'] or 'N/A'} to "
            f"{diagnostics['latest_slate_date'] or 'N/A'}"
        )
        st.caption(f"Rows with result updates: {diagnostics['result_updated_rows']}")
        st.caption(f"First snapshot: {diagnostics['earliest_snapshot'] or 'N/A'}")
        st.caption(f"Latest snapshot: {diagnostics['latest_snapshot'] or 'N/A'}")
        st.caption(f"Latest update: {diagnostics['latest_update'] or 'N/A'}")
        st.caption(
            "Model versions: "
            f"{', '.join(diagnostics['model_versions']) if diagnostics['model_versions'] else 'N/A'}"
        )

        if export_rows:
            export_label = (
                "all_models"
                if selected_model_version is None
                else str(selected_model_version).replace(".", "_")
            )
            st.download_button(
                f"Download Performance History CSV ({len(export_rows)} rows)",
                data=rows_to_csv(export_rows),
                file_name=f"model_history_{export_label}.csv",
                mime="text/csv",
                key="performance_history_download",
            )
        else:
            st.caption("No performance history rows are available to export.")

    if not summary_rows and not watch_summary_rows and not lean_summary_rows:
        st.info("No graded model history found for the selected filters.")
        return

    filter_text = f"{model_label} - {day_label}"
    if market_filter != "All":
        filter_text += f" - {market_filter}"
    if confidence_filter != "All":
        filter_text += f" - {confidence_filter} confidence"

    def performance_section_html(title, rows, meta):
        if not rows:
            return ""

        result_cards = []
        for row in rows:
            completed = (row.get("hits") or 0) + (row.get("misses") or 0) + (row.get("pushes") or 0)
            pending = row.get("pending") or 0
            record = f"{row.get('hits') or 0}-{row.get('misses') or 0}"
            if row.get("pushes"):
                record = f"{record}-{row.get('pushes')}"
            result_cards.append(
                '<div class="performance-card">'
                f'<div class="performance-market">{escape(row["market"])}</div>'
                f'<div class="performance-hit-rate">{performance_hit_rate(row)}</div>'
                f'<div class="performance-record">{escape(record)} record</div>'
                f'<div class="performance-meta">{completed} completed - {pending} pending</div>'
                '</div>'
            )

        return (
            '<div class="model-favorite top-looks">'
            f'<div class="model-label">{escape(title)}</div>'
            f'<div class="top-look-meta">{escape(meta)}</div>'
            '<div class="performance-results">'
            f'{"".join(result_cards)}'
            '</div>'
            '</div>'
        )

    sections = [
        performance_section_html("MODEL PERFORMANCE", summary_rows, filter_text),
        performance_section_html("WATCH PERFORMANCE", watch_summary_rows, f"{model_label} - {day_label}"),
        performance_section_html("LEAN PERFORMANCE", lean_summary_rows, f"{model_label} - {day_label}"),
    ]
    st.html("".join(section for section in sections if section))


def selected_sport():
    sport = str(get_query_param("sport") or "MLB").upper()
    if sport not in SPORT_CONFIG:
        return "MLB"
    if not SPORT_CONFIG[sport]["enabled"]:
        return "MLB"
    return sport


def selected_nfl_mode():
    mode = str(get_query_param("mode") or "current").lower()
    if mode not in ["current", "lab"]:
        return "current"
    return mode


def selected_nfl_filter(default_filter="all"):
    filter_value = str(get_query_param("filter") or default_filter).lower()
    valid_filters = {
        "all",
        "signals",
        "side",
        "scoring",
        "a",
        "pass",
        "correct",
        "missed",
    }
    if filter_value not in valid_filters:
        return default_filter
    return filter_value


def selected_nfl_week():
    week = str(get_query_param("week") or "all").lower()
    if week == "all":
        return "all"
    try:
        parsed = int(week)
    except Exception:
        return "all"
    if 1 <= parsed <= 18:
        return str(parsed)
    return "all"


def query_link(params):
    merged = {}
    for key, value in st.query_params.items():
        if isinstance(value, list):
            merged[key] = value[0] if value else ""
        else:
            merged[key] = value
    merged.update(params)
    query = "&".join(
        f"{escape(str(key))}={escape(str(value))}"
        for key, value in merged.items()
        if value is not None
    )
    return f"?{query}" if query else "?"


def selected_mlb_filter(default_filter="All Games"):
    filter_value = str(get_query_param("filter") or "all").lower()
    valid_filters = {
        "all": "All Games",
        "top": "Top Looks",
        "nrfi": "NRFI",
        "yrfi": "YRFI",
        "f5": "F5",
        "game": "Game",
        "perf": "Performance",
    }
    return valid_filters.get(filter_value, default_filter)


def render_mlb_filter_pills(active_filter):
    options = [
        ("All", "All Games", "all"),
        ("Top", "Top Looks", "top"),
        ("NRFI", "NRFI", "nrfi"),
        ("YRFI", "YRFI", "yrfi"),
        ("F5", "F5", "f5"),
        ("Game", "Game", "game"),
        ("Perf", "Performance", "perf"),
    ]
    pills = []
    for label, filter_key, value in options:
        classes = ["mlb-filter-card"]
        if filter_key == active_filter:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "MLB", "filter": value})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="mlb-filter-grid">{"".join(pills)}</div>')


def render_mlb_discovery_controls():
    columns = st.columns(2)
    with columns[0]:
        show_watches = st.checkbox("Show Watches", key="mlb_show_watches")
    with columns[1]:
        show_leans = st.checkbox("Show Leans", key="mlb_show_leans")
    return show_watches, show_leans


def render_discovery_labels(row):
    labels = discovery_labels(row)
    if not labels:
        return ""

    label_html = []
    for label in labels:
        classes = ["discovery-label"]
        if "Lean" in label:
            classes.append("lean")
        label_html.append(
            f'<span class="{" ".join(classes)}">{escape(str(label))}</span>'
        )

    return (
        '<div class="discovery-strip">'
        '<span>Discovery: </span>'
        f'{"".join(label_html)}'
        '</div>'
    )


def render_nfl_pills(options, active_value, extra_params=None):
    extra_params = extra_params or {}
    pills = []
    for label, value in options:
        classes = ["nfl-control-pill"]
        if value == active_value:
            classes.append("active")
        params = {"sport": "NFL", **extra_params, "filter": value}
        if "mode" not in params:
            params["mode"] = selected_nfl_mode()
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link(params)}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="nfl-control-row">{"".join(pills)}</div>')


def render_nfl_current_controls(slate, meta, selected_filter, filtered_count):
    slate_date = "TBD"
    if "Sort Date" in slate.columns and slate["Sort Date"].notna().any():
        try:
            slate_date = pd.to_datetime(slate["Sort Date"].dropna().min()).strftime(
                "%m/%d/%Y"
            )
        except Exception:
            slate_date = f"Season {meta['season']} - Week {meta['week']}"
    else:
        slate_date = f"Season {meta['season']} - Week {meta['week']}"

    options = [
        ("All", "all"),
        ("Signals", "signals"),
        ("Side", "side"),
        ("Scoring", "scoring"),
        ("A", "a"),
        ("Pass", "pass"),
    ]
    pills = []
    for label, value in options:
        classes = ["nfl-control-pill"]
        if value == selected_filter:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "NFL", "mode": "current", "week": "all", "filter": value})}">'
            f'{escape(label)}</a>'
        )

    st.html(
        '<div class="nfl-slate-label">Slate Date</div>'
        f'<div class="nfl-slate-box">{escape(str(slate_date))}</div>'
        f'<div class="nfl-filter-strip">{"".join(pills)}</div>'
        f'<div class="nfl-count-caption">{filtered_count} of {len(slate)}</div>'
    )


def render_nfl_mode_pills(active_mode):
    options = [("Current", "current"), ("Historical Lab", "lab")]
    pills = []
    for label, mode in options:
        classes = ["nfl-control-pill"]
        if mode == active_mode:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "NFL", "mode": mode, "filter": "all", "week": "all"})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="nfl-control-row">{"".join(pills)}</div>')


def render_wnba_mode_pills(active_mode):
    options = [("Current Slate", "current"), ("Historical Lab", "lab")]
    pills = []
    for label, mode in options:
        classes = ["nfl-control-pill"]
        if mode == active_mode:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "WNBA", "mode": mode, "filter": "all"})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="nfl-control-row">{"".join(pills)}</div>')


def render_wnba_filter_pills(active_filter, mode="lab"):
    options = [
        ("All", "all"),
        ("Signals", "signals"),
        ("Correct", "correct"),
        ("Missed", "missed"),
        ("Side", "side"),
        ("Scoring", "scoring"),
        ("A", "a"),
        ("Pass", "pass"),
    ]
    pills = []
    for label, value in options:
        classes = ["nfl-control-pill"]
        if value == active_filter:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "WNBA", "mode": mode, "filter": value})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="nfl-control-row">{"".join(pills)}</div>')


def selected_wnba_view(default_view="all"):
    view = str(get_query_param("view") or get_query_param("filter") or default_view).lower()
    valid_views = {"all", "top", "side", "scoring", "early", "perf"}
    if view not in valid_views:
        return default_view
    return view


def render_wnba_view_pills(active_view):
    options = [
        ("All", "all"),
        ("Top", "top"),
        ("Side", "side"),
        ("Scoring", "scoring"),
        ("Early", "early"),
        ("Perf", "perf"),
    ]
    pills = []
    for label, value in options:
        classes = ["wnba-filter-card"]
        if value == active_view:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "WNBA", "mode": "current", "view": value, "filter": None})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="wnba-filter-grid">{"".join(pills)}</div>')


def render_nba_mode_pills(active_mode):
    options = [("Current Slate", "current"), ("Historical Lab", "lab")]
    pills = []
    for label, mode in options:
        classes = ["nfl-control-pill"]
        if mode == active_mode:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "NBA", "mode": mode, "filter": "all"})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="nfl-control-row">{"".join(pills)}</div>')


def render_nba_filter_pills(active_filter, mode="lab"):
    options = [
        ("All", "all"),
        ("Signals", "signals"),
        ("Correct", "correct"),
        ("Missed", "missed"),
        ("Side", "side"),
        ("Scoring", "scoring"),
        ("A", "a"),
        ("Pass", "pass"),
    ]
    pills = []
    for label, value in options:
        classes = ["nfl-control-pill"]
        if value == active_filter:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "NBA", "mode": mode, "filter": value})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="nfl-control-row">{"".join(pills)}</div>')


def selected_nba_view(default_view="all"):
    view = str(get_query_param("view") or get_query_param("filter") or default_view).lower()
    valid_views = {"all", "top", "side", "scoring", "first_half", "perf"}
    if view not in valid_views:
        return default_view
    return view


def render_nba_view_pills(active_view):
    options = [
        ("All", "all"),
        ("Top", "top"),
        ("Side", "side"),
        ("Scoring", "scoring"),
        ("1H", "first_half"),
        ("Perf", "perf"),
    ]
    pills = []
    for label, value in options:
        classes = ["wnba-filter-card"]
        if value == active_view:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "NBA", "mode": "current", "view": value, "filter": None})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="wnba-filter-grid">{"".join(pills)}</div>')


def render_cbb_mode_pills(active_mode):
    options = [("Current Slate", "current"), ("Historical Lab", "lab")]
    pills = []
    for label, mode in options:
        classes = ["nfl-control-pill"]
        if mode == active_mode:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "CBB", "mode": mode, "filter": "all"})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="nfl-control-row">{"".join(pills)}</div>')


def render_cbb_filter_pills(active_filter, mode="lab"):
    options = [
        ("All", "all"),
        ("Signals", "signals"),
        ("Correct", "correct"),
        ("Missed", "missed"),
        ("Side", "side"),
        ("Scoring", "scoring"),
        ("A", "a"),
        ("Pass", "pass"),
    ]
    pills = []
    for label, value in options:
        classes = ["nfl-control-pill"]
        if value == active_filter:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "CBB", "mode": mode, "filter": value})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="nfl-control-row">{"".join(pills)}</div>')


def selected_cbb_view(default_view="all"):
    view = str(get_query_param("view") or get_query_param("filter") or default_view).lower()
    valid_views = {"all", "top", "side", "scoring", "first_half", "perf"}
    if view not in valid_views:
        return default_view
    return view


def render_cbb_view_pills(active_view):
    options = [
        ("All", "all"),
        ("Top", "top"),
        ("Side", "side"),
        ("Scoring", "scoring"),
        ("1H", "first_half"),
        ("Perf", "perf"),
    ]
    pills = []
    for label, value in options:
        classes = ["wnba-filter-card"]
        if value == active_view:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "CBB", "mode": "current", "view": value, "filter": None})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="wnba-filter-grid">{"".join(pills)}</div>')


def selected_mls_view(default_view="all"):
    view = str(get_query_param("view") or get_query_param("filter") or default_view).lower()
    valid_views = {
        "all",
        "top",
        "double_chance",
        "full_match",
        "goals",
        "btts",
        "first_half",
        "perf",
    }
    if view not in valid_views:
        return default_view
    return view


def render_mls_view_pills(active_view):
    options = [
        ("All", "all"),
        ("Top", "top"),
        ("DC", "double_chance"),
        ("Match", "full_match"),
        ("Goals", "goals"),
        ("BTTS", "btts"),
        ("1H", "first_half"),
        ("Perf", "perf"),
    ]
    pills = []
    for label, value in options:
        classes = ["wnba-filter-card"]
        if value == active_view:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "MLS", "mode": "current", "view": value, "filter": None})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="wnba-filter-grid">{"".join(pills)}</div>')


def render_nhl_mode_pills(active_mode):
    options = [("Current Slate", "current"), ("Historical Lab", "lab")]
    pills = []
    for label, mode in options:
        classes = ["nfl-control-pill"]
        if mode == active_mode:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "NHL", "mode": mode, "filter": "all"})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="nfl-control-row">{"".join(pills)}</div>')


def render_nhl_filter_pills(active_filter, mode="lab"):
    options = [
        ("All", "all"),
        ("Signals", "signals"),
        ("Correct", "correct"),
        ("Missed", "missed"),
        ("Moneyline", "moneyline"),
        ("A", "a"),
        ("Pass", "pass"),
    ]
    pills = []
    for label, value in options:
        classes = ["nfl-control-pill"]
        if value == active_filter:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "NHL", "mode": mode, "filter": value})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="nfl-control-row">{"".join(pills)}</div>')


def selected_nhl_view(default_view="all"):
    view = str(get_query_param("view") or get_query_param("filter") or default_view).lower()
    valid_views = {"all", "top", "moneyline", "first_period", "perf"}
    if view not in valid_views:
        return default_view
    return view


def render_nhl_view_pills(active_view):
    options = [
        ("All", "all"),
        ("Top", "top"),
        ("ML", "moneyline"),
        ("1P", "first_period"),
        ("Perf", "perf"),
    ]
    pills = []
    for label, value in options:
        classes = ["wnba-filter-card"]
        if value == active_view:
            classes.append("active")
        pills.append(
            f'<a class="{" ".join(classes)}" href="{query_link({"sport": "NHL", "mode": "current", "view": value, "filter": None})}">'
            f'{escape(label)}</a>'
        )
    st.html(f'<div class="wnba-filter-grid">{"".join(pills)}</div>')


def render_sport_picker(active_sport):
    pills = []
    for sport, config in SPORT_CONFIG.items():
        classes = ["sport-pill"]
        if sport == active_sport:
            classes.append("active")
        if not config["enabled"]:
            classes.append("disabled")
            pills.append(f'<span class="{" ".join(classes)}">{escape(sport)}</span>')
        else:
            pills.append(
                f'<a class="{" ".join(classes)}" href="?sport={escape(sport)}">'
                f'{escape(sport)}</a>'
            )

    st.html(f'<div class="sport-picker">{"".join(pills)}</div>')


def nfl_signal_class(row):
    if row["Model Signal"] == "Pass":
        return "badge-pass"
    if row["Scoring Edge"] not in [
        "Neutral Scoring Environment",
        "Neutral Goals Environment",
    ]:
        return "badge-f5"
    return "badge-nrfi"


def nfl_key_factor_list(row, limit=4):
    factors = row.get("Key Factors List", [])
    if not isinstance(factors, list):
        factors = [
            note.strip()
            for note in str(row.get("Agent Notes", "")).split(";")
            if note.strip()
        ]

    if not factors:
        summary = str(row.get("Key Factors Summary", "")).strip()
        factors = [summary] if summary else ["Neutral model profile"]

    return [str(factor) for factor in factors[:limit]]


def nfl_factor_groups(row):
    factors = nfl_key_factor_list(row, limit=12)
    side_keywords = (
        "side",
        "team-strength",
        "home-field",
        "rest",
        "margin",
        "threshold",
    )
    scoring_keywords = (
        "scoring",
        "score",
        "baseline",
        "total",
        "profile",
        "allowed",
    )
    side_factors = []
    scoring_factors = []

    for factor in factors:
        lower = factor.lower()
        if any(keyword in lower for keyword in side_keywords):
            side_factors.append(factor)
        if any(keyword in lower for keyword in scoring_keywords):
            scoring_factors.append(factor)

    if not side_factors:
        side_edge = str(row.get("Side Edge", "Pass"))
        if side_edge != "Pass":
            side_factors.append(f"{side_edge} clears the side-edge threshold")
        else:
            side_factors.append("Side edge stays below signal threshold")

    if not scoring_factors:
        scoring_edge = str(row.get("Scoring Edge", "Neutral Scoring Environment"))
        if scoring_edge != "Neutral Scoring Environment":
            scoring_factors.append(f"{scoring_edge} clears the scoring-environment threshold")
        else:
            scoring_factors.append("Scoring projection stays near the rolling league baseline")

    early_factors = [
        "Early Edge model pending",
        "First-half specific inputs are not yet modeled",
        "Use Side Edge and Scoring Environment for v1 review",
    ]

    return {
        "first": side_factors[:4],
        "f5": scoring_factors[:4],
        "full": early_factors,
    }


def render_nfl_key_factor_panel(row, view):
    headings = {
        "first": "Key Factors: Side Edge",
        "f5": "Key Factors: Scoring Environment",
        "full": "Key Factors: Early Edge",
    }
    factors = nfl_factor_groups(row).get(view, ["Neutral model profile"])
    items = []
    for factor in factors:
        items.append(
            '<div class="reason-item">'
            '<span class="reason-check">&#10003;</span>'
            f'<span>{escape(factor)}</span>'
            '</div>'
        )

    return (
        f'<div class="key-factors edge-factor-panel edge-factor-{escape(view)}">'
        f'<div class="market-heading">{escape(headings.get(view, "Key Factors"))}</div>'
        f'<div class="reason-stack">{"".join(items)}</div>'
        '</div>'
    )


def render_nfl_key_factor_panels(row):
    panels = "".join(
        render_nfl_key_factor_panel(row, view)
        for view in ["first", "f5", "full"]
    )
    return f'<div class="edge-factor-panels">{panels}</div>'


def nfl_scoring_environment_detail(row):
    projected_total = row.get("Projected Total", "N/A")
    baseline = row.get("League Total Baseline", "N/A")
    scoring_edge = row.get("Scoring Edge", "Neutral Scoring Environment")

    if scoring_edge == "Neutral Scoring Environment":
        return f"Projected total {projected_total} is near the rolling league baseline {baseline}."

    return f"{scoring_edge} with projected total {projected_total} vs rolling league baseline {baseline}."


def nfl_signal_agreement(row):
    agreements = []
    side_edge = str(row.get("Side Edge", "Pass"))
    scoring_edge = str(row.get("Scoring Edge", "Neutral Scoring Environment"))

    if side_edge != "Pass":
        agreements.append(f"Side Edge active: {side_edge}")
    else:
        agreements.append("Side Edge below signal threshold")

    if scoring_edge != "Neutral Scoring Environment":
        agreements.append(f"Scoring Environment active: {scoring_edge}")
    else:
        agreements.append("Scoring Environment near baseline")

    agreements.append(f"Confidence: {row.get('Confidence', 'Pass')}")
    return "; ".join(agreements)


def nfl_analysis_sections(row):
    side_edge = str(row.get("Side Edge", "Pass"))
    scoring_edge = str(row.get("Scoring Edge", "Neutral Scoring Environment"))
    confidence = str(row.get("Confidence", "Pass"))
    model_margin = row.get("Model Margin", "N/A")

    offense_signal = "Balanced / no clear separation"
    if side_edge != "Pass":
        offense_signal = f"{side_edge} supported by current scoring profile"
    elif scoring_edge != "Neutral Scoring Environment":
        offense_signal = f"{scoring_edge} supported by scoring profile"

    defense_signal = "No clear defensive separation in v1 model"
    if side_edge != "Pass":
        defense_signal = f"{side_edge} supported by team-strength margin {model_margin}"

    volatility_signal = "Moderate"
    if confidence == "A":
        volatility_signal = "Lower"
    elif confidence == "Pass":
        volatility_signal = "Elevated / no strong model separation"

    return [
        {
            "section": "Offense Edge",
            "signal": offense_signal,
            "detail": "Uses rolling scoring production and matchup-adjusted team rating from completed games.",
        },
        {
            "section": "Defense Edge",
            "signal": defense_signal,
            "detail": "Uses rolling points allowed and opponent scoring profile in the current v1 model.",
        },
        {
            "section": "Special Teams Edge",
            "signal": "Not yet modeled",
            "detail": "Field position, kicking, punting, and return edges are reserved for a future model pass.",
        },
        {
            "section": "Tempo / Game Script",
            "signal": scoring_edge,
            "detail": nfl_scoring_environment_detail(row),
        },
        {
            "section": "Volatility Check",
            "signal": volatility_signal,
            "detail": "Volatility is inferred from model separation and confidence until turnover-specific inputs are added.",
        },
        {
            "section": "Availability / Weather",
            "signal": "Pending",
            "detail": "Live injury, quarterback status, and weather inputs are not fully modeled in v1.0.",
        },
        {
            "section": "Signal Agreement",
            "signal": row.get("Model Signal", "Pass"),
            "detail": nfl_signal_agreement(row),
        },
    ]


def render_nfl_analysis_sections(row):
    st.markdown("### Edge Breakdown")
    for section in nfl_analysis_sections(row):
        st.markdown(f"#### {section['section']}")
        st.markdown(f"""
        | Metric | Value |
        |---|---|
        | Signal | {section["signal"]} |
        | Detail | {section["detail"]} |
        """)


def render_nfl_card(row, historical=False):
    away_team, home_team = split_game_name(row["Game"])
    card_anchor = f"nfl-{game_anchor(row['Game'])}"
    result_line = ""
    if historical:
        result_line = f"""
        <div class="muted">
            Final: <strong>{escape(str(row["Away Score"]))}-{escape(str(row["Home Score"]))}</strong>
            &nbsp; - &nbsp; Winner: <strong>{escape(str(row["Winner Result"]))}</strong>
            &nbsp; - &nbsp; Scoring: <strong>{escape(str(row["Scoring Result"]))}</strong>
            &nbsp; - &nbsp; Margin Error: <strong>{escape(str(row["Margin Error"]))}</strong>
            &nbsp; - &nbsp; Total Error: <strong>{escape(str(row["Total Error"]))}</strong>
        </div>
        """

    st.html(f"""
    <div id="{card_anchor}" class="game-card">
        <span class="badge {nfl_signal_class(row)}">{escape(str(row["Model Signal"]))}</span>
        <span class="badge badge-edge">Edge {escape(str(row["Edge Score"]))}</span>
        <span class="badge badge-edge">Confidence {escape(str(row["Confidence"]))}</span>

        <div class="game-title">{escape(str(row["Game"]))}</div>
        <div class="muted">{escape(str(row["Game Time"]))} - {escape(str(row["Status"]))}</div>

        <input class="edge-view-control edge-view-first" type="radio" name="{card_anchor}-edge-view" id="{card_anchor}-side" checked>
        <input class="edge-view-control edge-view-f5" type="radio" name="{card_anchor}-edge-view" id="{card_anchor}-scoring">
        <input class="edge-view-control edge-view-full" type="radio" name="{card_anchor}-edge-view" id="{card_anchor}-early">

        <div class="decision-stack">
            <label class="decision-line decision-first" for="{card_anchor}-side">Side Edge: {escape(str(row["Side Edge"]))}</label>
            <label class="decision-line decision-f5" for="{card_anchor}-scoring">Scoring Environment: {escape(str(row["Scoring Edge"]))}</label>
            <label class="decision-line decision-full" for="{card_anchor}-early">Early Edge: {escape(str(row["Early Edge"]))}</label>
        </div>

        {render_nfl_key_factor_panels(row)}

        {result_line}
    </div>
    """)

    with st.expander(f"🔍 Analysis: {row['Game']}"):
        if historical:
            st.markdown("### Result Review")
            st.markdown(f"""
            | Metric | Value |
            |---|---|
            | Final Score | {away_team} {row["Away Score"]} - {home_team} {row["Home Score"]} |
            | Winner | {row["Winner Result"]} |
            | Scoring | {row["Scoring Result"]} |
            | Margin Error | {row["Margin Error"]} |
            | Total Error | {row["Total Error"]} |
            """)

        render_nfl_analysis_sections(row)

        st.markdown("### Model Detail")
        st.markdown(f"""
        | Metric | Value |
        |---|---|
        | Side Edge | {row["Side Edge"]} |
        | Scoring Environment | {row["Scoring Edge"]} |
        | Early Edge | {row["Early Edge"]} |
        | Edge Score | {row["Edge Score"]} |
        | Confidence | {row["Confidence"]} |
        | Model Margin | {row["Model Margin"]} |
        | Projected Total | {row["Projected Total"]} |
        | League Total Baseline | {row["League Total Baseline"]} |
        """)


def wnba_key_factor_groups(row):
    factors = row.get("Key Factors List", [])
    if not isinstance(factors, list):
        factors = [
            note.strip()
            for note in str(row.get("Agent Notes", "")).split(";")
            if note.strip()
        ]

    primary = []
    support = []
    for factor in factors:
        text = str(factor)
        lower = text.lower()
        if (
            "team-strength" in lower
            or "threshold" in lower
            or "side edge" in lower
            or "home-court" in lower
        ):
            primary.append(text)
        else:
            support.append(text)

    if not primary and factors:
        primary = [str(factors[0])]
        support = [str(factor) for factor in factors[1:]]

    return primary[:2], support[:2]


def render_wnba_key_factors(row):
    primary, support = wnba_key_factor_groups(row)
    if not primary and not support:
        primary = ["Neutral model profile"]

    items = []
    if primary:
        items.append(
            '<div class="reason-item">'
            '<span class="reason-check">&#10003;</span>'
            f'<span>Primary drivers: {escape("; ".join(primary))}</span>'
            '</div>'
        )
    if support:
        items.append(
            '<div class="reason-item">'
            '<span class="reason-check">&#10003;</span>'
            f'<span>Support checks: {escape("; ".join(support))}</span>'
            '</div>'
        )

    return (
        '<div class="key-factors">'
        '<div class="market-heading">Key Factors: Full Game Edge</div>'
        f'<div class="reason-stack">{"".join(items)}</div>'
        '</div>'
    )


def wnba_result_icon(result):
    result = str(result or "Pending")
    if result == "Correct":
        return '<span class="result-outcome result-hit" aria-label="Correct">&#10003;</span>'
    if result == "Missed":
        return '<span class="result-outcome result-miss" aria-label="Missed">&times;</span>'
    return f'<span class="result-outcome result-push">{escape(result)}</span>'


def render_wnba_result_strip(row):
    sport = row.get("Sport")
    status = str(row.get("Status", "Scheduled"))
    side_result = row.get("Side Result") or row.get("Winner Result") or "Pending"
    scoring_result = row.get("Scoring Result") or "Pending"
    full_match_result = row.get("Winner Result") or "Pending"
    btts_result = row.get("BTTS Result") or "Pending"
    if sport == "NHL":
        side_label = "Moneyline"
        scoring_label = "Goal Env"
    elif sport == "MLS":
        side_label = "Double Chance"
        scoring_label = "Goals"
    else:
        side_label = "Side"
        scoring_label = "Scoring"

    if status != "Final":
        side_result = "Pending" if row.get("Side Edge") != "Pass" else "No Signal"
        if sport == "NHL":
            scoring_result = "No Signal"
        else:
            neutral_scoring = (
                "Neutral Goals Environment"
                if sport == "MLS"
                else "Neutral Scoring Environment"
            )
            scoring_result = (
                "Pending"
                if row.get("Scoring Edge") != neutral_scoring
                else "No Signal"
            )
        if sport == "MLS":
            full_match_result = (
                "Pending"
                if row.get("Full Match Edge") != "Pass"
                else "No Signal"
            )
            btts_result = (
                "Pending"
                if row.get("BTTS Edge") != "Pass"
                else "No Signal"
            )

    score_line = ""
    if status == "Final" and row.get("Away Score") is not None:
        score_line = (
            f'<div class="reason-item"><span class="reason-check">&#10003;</span>'
            f'<span>Final: {escape(str(row.get("Away")))} {escape(str(row.get("Away Score")))}'
            f' - {escape(str(row.get("Home")))} {escape(str(row.get("Home Score")))}</span></div>'
        )

    extra_results = ""
    if sport == "MLS":
        extra_results = (
            f'<div class="reason-item"><span>Full Match: {escape(str(full_match_result))}</span>{wnba_result_icon(full_match_result)}</div>'
            f'<div class="reason-item"><span>BTTS: {escape(str(btts_result))}</span>{wnba_result_icon(btts_result)}</div>'
        )

    return (
        '<div class="key-factors">'
        '<div class="market-heading">Model Results</div>'
        '<div class="reason-stack">'
        f'<div class="reason-item"><span>{escape(side_label)}: {escape(str(side_result))}</span>{wnba_result_icon(side_result)}</div>'
        f'<div class="reason-item"><span>{escape(scoring_label)}: {escape(str(scoring_result))}</span>{wnba_result_icon(scoring_result)}</div>'
        f'{extra_results}'
        f'{score_line}'
        '</div>'
        '</div>'
    )


def render_wnba_card(row, historical=False):
    sport = row.get("Sport")
    if sport == "NBA":
        half_label = "First Half"
    elif sport == "NHL":
        half_label = "First Period"
    elif sport == "MLS":
        half_label = "First Half"
    else:
        half_label = "Early Edge"
    if sport == "NHL":
        side_label = "Moneyline Edge"
        scoring_label = "Goal Environment"
    elif sport == "MLS":
        side_label = "Double Chance Edge"
        scoring_label = "Goals Environment"
    else:
        side_label = "Side Edge"
        scoring_label = "Scoring Environment"
    extra_decisions = ""
    if sport == "MLS":
        extra_decisions = (
            f'<div class="decision-line decision-first">Full Match: {escape(str(row.get("Full Match Edge", "Pass")))}</div>'
            f'<div class="decision-line decision-f5">BTTS: {escape(str(row.get("BTTS Edge", "Pass")))}</div>'
        )
    extra_model_rows = ""
    if sport == "MLS":
        extra_model_rows = f"""
        | Full Match | {row.get("Full Match Edge", "N/A")} |
        | Full Match Result | {row.get("Winner Result", "Pending")} |
        | BTTS | {row.get("BTTS Edge", "N/A")} |
        | BTTS Result | {row.get("BTTS Result", "Pending")} |
        """
    game_time_display = format_local_card_time(row)
    result_line = ""
    if historical:
        result_line = f"""
        <div class="muted">
            Final: <strong>{escape(str(row["Away Score"]))}-{escape(str(row["Home Score"]))}</strong>
            &nbsp; - &nbsp; Winner: <strong>{escape(str(row["Winner Result"]))}</strong>
            &nbsp; - &nbsp; {escape(scoring_label)}: <strong>{escape(str(row["Scoring Result"]))}</strong>
            &nbsp; - &nbsp; Margin Error: <strong>{escape(str(row["Margin Error"]))}</strong>
            &nbsp; - &nbsp; Total Error: <strong>{escape(str(row["Total Error"]))}</strong>
        </div>
        """

    st.html(f"""
    <div class="game-card">
        <span class="badge {nfl_signal_class(row)}">{escape(str(row["Model Signal"]))}</span>
        <span class="badge badge-edge">Edge {escape(str(row["Edge Score"]))}</span>
        <span class="badge badge-edge">Confidence {escape(str(row["Confidence"]))}</span>

        <div class="game-title">{escape(str(row["Game"]))}</div>
        <div class="muted">{escape(str(game_time_display))} - {escape(str(row["Status"]))}</div>

        <div class="decision-stack">
            <div class="decision-line decision-first">{escape(side_label)}: {escape(str(row["Side Edge"]))}</div>
            <div class="decision-line decision-f5">{escape(scoring_label)}: {escape(str(row["Scoring Edge"]))}</div>
            <div class="decision-line decision-full">{escape(half_label)}: {escape(str(row["Early Edge"]))}</div>
            {extra_decisions}
        </div>

        {render_wnba_result_strip(row)}

        {render_wnba_key_factors(row)}

        {result_line}
    </div>
    """)

    with st.expander(f"Analysis: {row['Game']}"):
        st.markdown("### Key Factors")
        for factor in row["Key Factors List"]:
            st.markdown(f"- {factor}")

        st.markdown("### Model Detail")
        st.markdown(f"""
        | Metric | Value |
        |---|---|
        | {side_label} | {row["Side Edge"]} |
        | {side_label} Result | {row.get("Side Result", row.get("Winner Result", "Pending"))} |
        | {scoring_label} | {row["Scoring Edge"]} |
        | {scoring_label} Result | {row.get("Scoring Result", "Pending")} |
        {extra_model_rows}
        | {half_label} | {row["Early Edge"]} |
        | Edge Score | {row["Edge Score"]} |
        | Confidence | {row["Confidence"]} |
        | Model Margin | {row["Model Margin"]} |
        | Projected Total | {row["Projected Total"]} |
        | League Total Baseline | {row["League Total Baseline"]} |
        """)


def filter_nfl_games(games, view, historical=False):
    filtered = games.copy()
    if view == "signals":
        filtered = filtered[filtered["Model Signal"] != "Pass"]
    elif view == "side":
        filtered = filtered[filtered["Side Edge"] != "Pass"]
    elif view == "scoring":
        filtered = filtered[filtered["Scoring Edge"] != "Neutral Scoring Environment"]
    elif view == "a":
        filtered = filtered[filtered["Confidence"] == "A"]
    elif view == "pass":
        filtered = filtered[filtered["Model Signal"] == "Pass"]
    elif historical and view == "correct":
        filtered = filtered[
            filtered["Winner Result"].eq("Correct")
            | filtered["Scoring Result"].eq("Correct")
        ]
    elif historical and view == "missed":
        filtered = filtered[
            filtered["Winner Result"].eq("Missed")
            | filtered["Scoring Result"].eq("Missed")
        ]
    return filtered


def filter_wnba_games(games, view):
    filtered = games.copy()
    if view == "side":
        filtered = filtered[filtered["Side Edge"] != "Pass"]
    elif view == "scoring":
        filtered = filtered[filtered["Scoring Edge"] != "Neutral Scoring Environment"]
    return filtered


def filter_mls_games(games, view):
    filtered = games.copy()
    if view == "top":
        filtered = filtered[
            (filtered["Model Signal"] != "Pass")
            & (filtered["Confidence"].isin(["A", "B"]))
        ]
    elif view == "double_chance":
        filtered = filtered[filtered["Side Edge"] != "Pass"]
    elif view == "full_match":
        filtered = filtered[filtered["Full Match Edge"] != "Pass"]
    elif view == "goals":
        filtered = filtered[filtered["Scoring Edge"] != "Neutral Goals Environment"]
    elif view == "btts":
        filtered = filtered[filtered["BTTS Edge"] != "Pass"]
    return filtered


def filter_nhl_games(games, view, historical=False):
    filtered = games.copy()
    if view in ["signals", "moneyline"]:
        filtered = filtered[filtered["Side Edge"] != "Pass"]
    elif view == "a":
        filtered = filtered[filtered["Confidence"] == "A"]
    elif view == "pass":
        filtered = filtered[filtered["Model Signal"] == "Pass"]
    elif historical and view == "correct":
        filtered = filtered[filtered["Side Result"].eq("Correct")]
    elif historical and view == "missed":
        filtered = filtered[filtered["Side Result"].eq("Missed")]
    return filtered


@st.cache_data(ttl=900)
def load_nfl_current():
    return build_current_slate()


@st.cache_data(ttl=900)
def load_nfl_historical():
    return build_historical_lab(2025)


def render_nfl_current():
    slate, meta = load_nfl_current()
    if slate.empty:
        st.info("No upcoming NFL games found.")
        st.markdown(
            f'[Open Historical Lab]({query_link({"sport": "NFL", "mode": "lab", "filter": "all", "week": "all"})})'
        )
        return

    selected_filter = selected_nfl_filter("all")
    filtered = filter_nfl_games(slate, selected_filter)
    render_nfl_current_controls(slate, meta, selected_filter, len(filtered))

    if filtered.empty:
        st.info("No NFL games match the selected filter.")
        return

    for _, row in filtered.iterrows():
        render_nfl_card(row)


def render_nfl_historical():
    results, summary = load_nfl_historical()

    selected_filter = selected_nfl_filter("all")
    st.html('<div class="nfl-control-label">Filter</div>')
    render_nfl_pills(
        [
            ("All", "all"),
            ("Signals", "signals"),
            ("Correct", "correct"),
            ("Missed", "missed"),
            ("Side", "side"),
            ("Scoring", "scoring"),
            ("A", "a"),
        ],
        selected_filter,
        {"mode": "lab", "week": selected_nfl_week()},
    )

    week_options = ["All Weeks"] + [f"Week {week}" for week in range(1, 19)]
    current_week = selected_nfl_week()
    week_index = 0 if current_week == "all" else int(current_week)
    selected_week = st.selectbox(
        "Week",
        week_options,
        index=week_index,
        key="nfl_historical_week_select",
    )
    desired_week_param = "all" if selected_week == "All Weeks" else selected_week.split()[-1]
    if desired_week_param != current_week:
        st.query_params["sport"] = "NFL"
        st.query_params["mode"] = "lab"
        st.query_params["filter"] = selected_filter
        st.query_params["week"] = desired_week_param
        st.rerun()

    filtered = results.copy()
    if selected_week != "All Weeks":
        filtered = filtered[filtered["Week"] == int(selected_week.split()[-1])]
    filtered = filter_nfl_games(filtered, selected_filter, historical=True)

    st.subheader("2025 Historical Lab")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Games", int(summary["games"]))
    c2.metric("Winner Acc", f"{summary['winner_accuracy']:.1%}")
    c3.metric("Side Signal Acc", f"{summary['side_signal_accuracy']:.1%}")
    c4.metric("Scoring Acc", f"{summary['scoring_signal_accuracy']:.1%}")
    c5.metric("Margin MAE", summary["margin_mae"])
    c6.metric("Total MAE", summary["total_mae"])

    confidence_table, scoring_table = historical_summary_tables(results)
    table_left, table_right = st.columns(2)
    with table_left:
        st.markdown("#### Confidence Tiers")
        st.dataframe(confidence_table, width="stretch", hide_index=True)
    with table_right:
        st.markdown("#### Scoring Environment")
        st.dataframe(scoring_table, width="stretch", hide_index=True)

    if filtered.empty:
        st.info("No historical NFL games match the selected filters.")
        return

    filtered = filtered.sort_values(["Week", "Game"])
    for _, row in filtered.iterrows():
        render_nfl_card(row, historical=True)


def render_nfl_page():
    st.title("NFL Edge Detector")
    st.caption("Outcome and scoring-environment model signals")

    mode = selected_nfl_mode()
    render_nfl_mode_pills(mode)

    if mode == "current":
        render_nfl_current()
    else:
        render_nfl_historical()

    with st.expander("NFL Data Sources / Model Info"):
        st.markdown("""
        **Game Data**: nflverse regular-season game data

        **Current Slate**: nearest upcoming regular-season week, when available

        **Historical Lab**: fixed 2025 regular-season model test

        **Model Scope**: matchup intelligence only. No odds, market comparison, staking guidance, or betting recommendations.
        """)


def wnba_data_contract_text():
    return """
    Required columns:

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
    """


def render_wnba_current():
    default_date = current_date_for_timezone(display_timezone)
    selected_date = st.date_input(
        "Slate Date",
        value=default_date,
        format="MM/DD/YYYY",
        key="wnba_slate_date",
    )
    selected_view = selected_wnba_view("all")
    slate = pd.DataFrame()
    meta = {}
    slate_error = None
    try:
        slate, meta = load_wnba_current(selected_date)
    except Exception as exc:
        slate_error = exc

    wnba_history_rows = safe_load_wnba_slate_history_rows(
        MODEL_BASELINES["WNBA"],
        MARKET_RELEASES["WNBA"],
        selected_date,
    )

    render_wnba_view_pills(selected_view)

    if selected_view == "perf":
        st.caption("Performance history")
        st.caption(format_snapshot_caption(wnba_history_rows))
        st.divider()
        render_wnba_performance_section()
        return

    if slate_error is not None:
        st.error(f"Could not load WNBA current slate: {slate_error}")
        return

    if slate.empty:
        st.info("No WNBA games found for the selected slate date.")
        return

    if selected_view in ["top", "early"]:
        filtered_count = 0
    else:
        filtered_count = len(filter_wnba_games(slate, selected_view))
    st.caption(f"{filtered_count} of {len(slate)}")
    st.caption(format_snapshot_caption(wnba_history_rows))
    st.divider()

    if selected_view == "top":
        st.info("WNBA Top signals are a placeholder until the v1.0 model has enough tracked performance to define a reliable top-pick cut.")
        return

    if selected_view == "early":
        st.info("WNBA Early edge is pending for v1.0. Current WNBA testing is focused on full-game side and scoring-environment signals.")
        return

    filtered = filter_wnba_games(slate, selected_view)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Games", len(slate))
    c2.metric("Model Signals", len(slate[slate["Model Signal"] != "Pass"]))
    c3.metric("Side Edges", len(slate[slate["Side Edge"] != "Pass"]))
    c4.metric(
        "Scoring Signals",
        len(slate[slate["Scoring Edge"] != "Neutral Scoring Environment"]),
    )

    if filtered.empty:
        st.info("No WNBA games match the selected view.")
        return

    for _, row in filtered.iterrows():
        render_wnba_card(row)


def render_wnba_summary_tables(tables):
    core = tables.get("core")
    if core is not None and not core.empty:
        st.markdown("#### Core")
        st.dataframe(core, width="stretch", hide_index=True)

    left, right = st.columns(2)
    with left:
        st.markdown("#### Confidence Tiers")
        confidence = tables.get("confidence")
        if confidence is not None and not confidence.empty:
            st.dataframe(confidence, width="stretch", hide_index=True)
        else:
            st.caption("No confidence-tier rows yet.")

        st.markdown("#### Side Location")
        side_location = tables.get("side_location")
        if side_location is not None and not side_location.empty:
            st.dataframe(side_location, width="stretch", hide_index=True)
        else:
            st.caption("No side signals yet.")

    with right:
        st.markdown("#### Scoring Environment")
        scoring = tables.get("scoring")
        if scoring is not None and not scoring.empty:
            st.dataframe(scoring, width="stretch", hide_index=True)
        else:
            st.caption("No high/low scoring signals yet.")

        st.markdown("#### Team History")
        history = tables.get("history")
        if history is not None and not history.empty:
            st.dataframe(history, width="stretch", hide_index=True)
        else:
            st.caption("No history split rows yet.")

    rest = tables.get("rest")
    if rest is not None and not rest.empty:
        st.markdown("#### Rest Context")
        st.dataframe(rest, width="stretch", hide_index=True)


def wnba_rows_to_csv(rows):
    if not rows:
        return ""
    return pd.DataFrame(rows).to_csv(index=False)


def parse_wnba_slate_date(row):
    try:
        return datetime.fromisoformat(str(row.get("slate_date"))).date()
    except Exception:
        return None


def latest_wnba_history_date(rows):
    dates = [parse_wnba_slate_date(row) for row in rows]
    dates = [date_value for date_value in dates if date_value is not None]
    return max(dates) if dates else None


def wnba_signal_result(row, market):
    if market == "Side":
        if row.get("side_edge") in [None, "", "Pass"]:
            return None
        return row.get("side_result")
    if market == "Scoring":
        if row.get("scoring_edge") in [None, "", "Neutral Scoring Environment"]:
            return None
        return row.get("scoring_result")

    return None


def wnba_history_row_matches_filters(
    row,
    market="All",
    days=None,
    confidence="All",
    exact_date=None,
    anchor_date=None,
):
    row_date = parse_wnba_slate_date(row)
    if exact_date is not None and row_date != exact_date:
        return False
    if days is not None and row_date is not None:
        latest_date = anchor_date or row_date
        if row_date < latest_date - timedelta(days=days - 1):
            return False
    if confidence != "All" and row.get("confidence") != confidence:
        return False
    if market != "All" and wnba_signal_result(row, market) is None:
        return False

    return True


def summarize_wnba_performance_rows(rows, market_filter="All"):
    markets = ["Side", "Scoring"] if market_filter == "All" else [market_filter]
    summary_rows = []
    for market in markets:
        market_rows = [
            row for row in rows if wnba_signal_result(row, market) is not None
        ]
        if not market_rows:
            continue

        hits = sum(
            1 for row in market_rows if wnba_signal_result(row, market) == "Correct"
        )
        misses = sum(
            1 for row in market_rows if wnba_signal_result(row, market) == "Missed"
        )
        pending = len(market_rows) - hits - misses
        summary_rows.append(
            {
                "market": market,
                "total": len(market_rows),
                "hits": hits,
                "misses": misses,
                "pushes": 0,
                "pending": pending,
            }
        )

    return summary_rows


def wnba_detail_rows(rows, market_filter="All"):
    detail_rows = []
    markets = ["Side", "Scoring"] if market_filter == "All" else [market_filter]
    for row in rows:
        for market in markets:
            result = wnba_signal_result(row, market)
            if result is None:
                continue

            detail = dict(row)
            detail["market"] = market
            detail["pick"] = (
                row.get("predicted_winner")
                if market == "Side"
                else row.get("scoring_edge")
            )
            detail["result"] = result or "Pending"
            detail["score"] = (
                row.get("edge_score")
                if market == "Side"
                else row.get("projected_total")
            )
            detail_rows.append(detail)

    return detail_rows


def render_wnba_performance_section():
    st.markdown("### WNBA Performance")
    model_version = MODEL_BASELINES["WNBA"]
    market_version = MARKET_RELEASES["WNBA"]
    current_summary = load_wnba_performance_summary(
        model_version=model_version,
        market_version=market_version,
    )
    storage_backend = current_summary.get("storage_backend", "Unavailable")
    storage_path = current_summary.get("db_path", "N/A")
    current_rows = load_wnba_history(
        model_version=model_version,
        market_version=market_version,
    )
    all_rows = load_wnba_history()

    if current_summary["snapshots"] == 0:
        st.info("No WNBA performance snapshots recorded yet. The scheduled WNBA snapshot workflow will create pregame snapshots when it runs.")
        return

    model_filter_options = [f"Current {model_version}", "All"]
    filter_cols = st.columns([1, 1, 1, 1])
    with filter_cols[0]:
        market_filter = st.selectbox(
            "Signal",
            ["All", "Side", "Scoring"],
            key="wnba_performance_market_filter",
        )
    with filter_cols[1]:
        window_filter = st.selectbox(
            "Day(s)",
            ["Today", "Yesterday", "Last 7", "Last 30", "All"],
            key="wnba_performance_window_filter",
        )
    with filter_cols[2]:
        confidence_filter = st.selectbox(
            "Confidence",
            ["All", "A", "B", "C", "Pass"],
            key="wnba_performance_confidence_filter",
        )
    with filter_cols[3]:
        selected_model_filter = st.selectbox(
            "Model",
            model_filter_options,
            key="wnba_performance_model_filter",
        )

    selected_rows = (
        all_rows if selected_model_filter == "All" else current_rows
    )
    model_label = (
        "All models"
        if selected_model_filter == "All"
        else f"Current {model_version}"
    )
    history_today = latest_wnba_history_date(selected_rows) or datetime.now().date()

    day_filters = {
        "Today": {"exact_date": history_today, "label": f"Today ({history_today})"},
        "Yesterday": {
            "exact_date": history_today - timedelta(days=1),
            "label": f"Yesterday ({history_today - timedelta(days=1)})",
        },
        "Last 7": 7,
        "Last 30": 30,
        "All": {"days": None, "exact_date": None, "label": "All history"},
    }[window_filter]
    if isinstance(day_filters, dict):
        days = day_filters.get("days")
        exact_date = day_filters.get("exact_date")
        day_label = day_filters["label"]
    else:
        days = day_filters
        exact_date = None
        day_label = f"{window_filter} days"

    if days is not None:
        filtered_rows = [
            row
            for row in selected_rows
            if wnba_history_row_matches_filters(
                row,
                market_filter,
                days=days,
                confidence=confidence_filter,
                exact_date=None,
                anchor_date=history_today,
            )
        ]
    else:
        filtered_rows = [
            row
            for row in selected_rows
            if wnba_history_row_matches_filters(
                row,
                market_filter,
                days=None,
                confidence=confidence_filter,
                exact_date=exact_date,
            )
        ]

    summary_rows = summarize_wnba_performance_rows(filtered_rows, market_filter)
    detail_rows = wnba_detail_rows(filtered_rows, market_filter)

    with st.expander("WNBA Performance History Diagnostics"):
        diag_cols = st.columns(4)
        with diag_cols[0]:
            st.metric("Snapshots", current_summary["snapshots"])
        with diag_cols[1]:
            st.metric("Completed", current_summary["completed"])
        with diag_cols[2]:
            st.metric("Side Signals", current_summary["side_signal_games"])
        with diag_cols[3]:
            st.metric("Scoring Signals", current_summary["scoring_signal_games"])

        st.caption(
            "Snapshot rule: WNBA predictions are stored only for pregame snapshots; "
            "final rows update result fields only when a matching snapshot exists."
        )
        st.caption(f"Storage: {storage_backend}")
        st.code(storage_path, language="text")
        st.caption(
            f"Current market version: {market_version} | Current model baseline: {model_version}"
        )

        export_label = (
            "all_models"
            if selected_model_filter == "All"
            else str(model_version).replace(".", "_")
        )
        st.download_button(
            f"Download WNBA Performance History CSV ({len(selected_rows)} rows)",
            data=wnba_rows_to_csv(selected_rows),
            file_name=f"wnba_model_history_{export_label}.csv",
            mime="text/csv",
            key="wnba_history_download",
        )

    if not summary_rows:
        st.info("No WNBA tracked results match the selected filters.")
        return

    result_cards = []
    for row in summary_rows:
        completed = (row.get("hits") or 0) + (row.get("misses") or 0)
        pending = row.get("pending") or 0
        record = f"{row.get('hits') or 0}-{row.get('misses') or 0}"
        result_cards.append(
            '<div class="performance-card">'
            f'<div class="performance-market">{escape(row["market"])}</div>'
            f'<div class="performance-hit-rate">{performance_hit_rate(row)}</div>'
            f'<div class="performance-record">{escape(record)} record</div>'
            f'<div class="performance-meta">{completed} completed - {pending} pending</div>'
            '</div>'
        )

    filter_text = f"{model_label} - {day_label}"
    if market_filter != "All":
        filter_text += f" - {market_filter}"
    if confidence_filter != "All":
        filter_text += f" - {confidence_filter} confidence"

    st.html(
        '<div class="model-favorite top-looks">'
        '<div class="model-label">WNBA MODEL PERFORMANCE</div>'
        f'<div class="top-look-meta">{escape(filter_text)}</div>'
        '<div class="performance-results">'
        f'{"".join(result_cards)}'
        '</div>'
        '</div>'
    )

    if not detail_rows:
        st.info("No detailed WNBA rows match the selected filters.")
        return

    detail_df = pd.DataFrame(detail_rows)
    detail_df = detail_df.rename(
        columns={
            "slate_date": "Slate",
            "market": "Signal",
            "game": "Game",
            "pick": "Pick",
            "confidence": "Confidence",
            "score": "Score",
            "result": "Result",
            "status": "Status",
            "model_version": "Model",
            "market_version": "Market Version",
        }
    )
    st.dataframe(
        detail_df[
            [
                "Slate",
                "Signal",
                "Game",
                "Pick",
                "Confidence",
                "Score",
                "Result",
                "Status",
                "Model",
                "Market Version",
            ]
        ],
        hide_index=True,
        use_container_width=True,
    )

    with st.expander("WNBA Performance Splits"):
        tables = load_wnba_performance_tables(
            model_version=model_version,
            market_version=market_version,
        )
        split_tabs = st.tabs(["Core", "Confidence", "Side", "Scoring", "History", "Rest"])
        split_keys = ["core", "confidence", "side_location", "scoring", "history", "rest"]
        for tab, split_key in zip(split_tabs, split_keys):
            with tab:
                split_df = pd.DataFrame(tables[split_key])
                if split_df.empty:
                    st.caption("No split rows yet.")
                else:
                    st.dataframe(split_df, width="stretch", hide_index=True)


def render_wnba_historical():
    uploaded = st.file_uploader(
        "WNBA historical/current-season CSV",
        type=["csv"],
        key="wnba_historical_csv",
    )

    with st.expander("CSV Data Contract", expanded=uploaded is None):
        st.markdown(wnba_data_contract_text())

    if uploaded is None:
        st.info("Upload a normalized WNBA games CSV to run the v1.0 model lab, or use Current Slate for the live ESPN-fed test surface.")
        try:
            current_results, current_summary = load_wnba_current_lab()
        except Exception:
            return

        if current_results.empty:
            return

        st.subheader("Current Season Completed Games")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Games", int(current_summary["games"]))
        c2.metric("Winner Acc", f"{current_summary['winner_accuracy']:.1%}")
        c3.metric("Side Signal Acc", f"{current_summary['side_signal_accuracy']:.1%}")
        c4.metric("Scoring Acc", f"{current_summary['scoring_signal_accuracy']:.1%}")
        c5.metric("Margin MAE", current_summary["margin_mae"])
        c6.metric("Total MAE", current_summary["total_mae"])
        render_wnba_summary_tables(wnba_historical_summary_tables(current_results))
        return

    try:
        games = pd.read_csv(uploaded)
    except Exception as exc:
        st.error(f"Could not read CSV: {exc}")
        return

    if "season" not in games.columns:
        st.error("CSV is missing required column: season")
        return

    seasons = sorted(
        int(season)
        for season in pd.to_numeric(games["season"], errors="coerce").dropna().unique()
    )
    season_options = ["All Seasons"] + [str(season) for season in seasons]
    default_index = len(season_options) - 1 if len(season_options) > 1 else 0
    selected_season = st.selectbox(
        "Season",
        season_options,
        index=default_index,
        key="wnba_lab_season",
    )
    season = None if selected_season == "All Seasons" else int(selected_season)
    compare_no_rest = st.checkbox(
        "Show no-rest ablation",
        value=True,
        key="wnba_compare_no_rest",
    )

    try:
        results, summary = build_wnba_historical_lab(games, season)
    except Exception as exc:
        st.error(f"Could not run WNBA model: {exc}")
        return

    if results.empty:
        st.info("No completed WNBA games found for the selected data.")
        return

    tables = wnba_historical_summary_tables(results)
    st.subheader("WNBA Historical Lab")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Games", int(summary["games"]))
    c2.metric("Winner Acc", f"{summary['winner_accuracy']:.1%}")
    c3.metric("Side Signal Acc", f"{summary['side_signal_accuracy']:.1%}")
    c4.metric("Scoring Acc", f"{summary['scoring_signal_accuracy']:.1%}")
    c5.metric("Margin MAE", summary["margin_mae"])
    c6.metric("Total MAE", summary["total_mae"])

    if compare_no_rest:
        try:
            _, no_rest_summary = backtest_no_rest_schedule(games, season)
            st.caption(
                "No-rest ablation: "
                f"side signal accuracy {no_rest_summary['side_signal_accuracy']:.1%}, "
                f"margin MAE {no_rest_summary['margin_mae']}"
            )
        except Exception as exc:
            st.warning(f"No-rest ablation could not run: {exc}")

    render_wnba_summary_tables(tables)

    selected_filter = selected_nfl_filter("all")
    st.html('<div class="nfl-control-label">Filter</div>')
    render_wnba_filter_pills(selected_filter, mode="lab")
    filtered = filter_nfl_games(results, selected_filter, historical=True)

    if filtered.empty:
        st.info("No WNBA games match the selected filter.")
        return

    filtered = filtered.sort_values(["Game Date", "Game"])
    for _, row in filtered.iterrows():
        render_wnba_card(row, historical=True)


def render_nba_current():
    default_date = current_date_for_timezone(FALLBACK_TIMEZONE)
    selected_date = st.date_input(
        "Slate Date",
        value=default_date,
        format="MM/DD/YYYY",
        key="nba_slate_date",
    )
    selected_view = selected_nba_view("all")
    slate = pd.DataFrame()
    slate_error = None
    try:
        slate, _ = load_nba_current(selected_date)
    except Exception as exc:
        slate_error = exc

    nba_history_rows = safe_load_nba_slate_history_rows(
        MODEL_BASELINES["NBA"],
        MARKET_RELEASES["NBA"],
        selected_date,
    )

    render_nba_view_pills(selected_view)

    if selected_view == "perf":
        st.caption("Performance history")
        st.caption(format_snapshot_caption(nba_history_rows))
        st.divider()
        render_nba_performance_section()
        return

    if slate_error is not None:
        st.error(f"Could not load NBA current slate: {slate_error}")
        return

    if slate.empty:
        st.info("No NBA games found for the selected slate date.")
        return

    if selected_view in ["top", "first_half"]:
        filtered_count = 0
    else:
        filtered_count = len(filter_wnba_games(slate, selected_view))
    st.caption(f"{filtered_count} of {len(slate)}")
    st.caption(format_snapshot_caption(nba_history_rows))
    st.divider()

    if selected_view == "top":
        st.info("NBA Top signals are a placeholder until the v0 model has enough tracked performance to define a reliable top-pick cut.")
        return

    if selected_view == "first_half":
        st.info("NBA First Half is pending until a reliable halftime-result data source is added. Full-game side and scoring signals are active in v0.")
        return

    filtered = filter_wnba_games(slate, selected_view)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Games", len(slate))
    c2.metric("Model Signals", len(slate[slate["Model Signal"] != "Pass"]))
    c3.metric("Side Edges", len(slate[slate["Side Edge"] != "Pass"]))
    c4.metric(
        "Scoring Signals",
        len(slate[slate["Scoring Edge"] != "Neutral Scoring Environment"]),
    )

    if filtered.empty:
        st.info("No NBA games match the selected view.")
        return

    for _, row in filtered.iterrows():
        render_wnba_card(row)


def render_nba_performance_section():
    st.markdown("### NBA Performance")
    model_version = MODEL_BASELINES["NBA"]
    market_version = MARKET_RELEASES["NBA"]
    current_summary = load_nba_performance_summary(
        model_version=model_version,
        market_version=market_version,
    )
    storage_backend = current_summary.get("storage_backend", "Unavailable")
    storage_path = current_summary.get("db_path", "N/A")
    current_rows = load_nba_history(
        model_version=model_version,
        market_version=market_version,
    )
    all_rows = load_nba_history()

    if current_summary["snapshots"] == 0:
        st.info("No NBA performance snapshots recorded yet. The scheduled NBA snapshot workflow will create pregame snapshots when it runs.")
        return

    model_filter_options = [f"Current {model_version}", "All"]
    filter_cols = st.columns([1, 1, 1, 1])
    with filter_cols[0]:
        market_filter = st.selectbox(
            "Signal",
            ["All", "Side", "Scoring"],
            key="nba_performance_market_filter",
        )
    with filter_cols[1]:
        window_filter = st.selectbox(
            "Day(s)",
            ["Today", "Yesterday", "Last 7", "Last 30", "All"],
            key="nba_performance_window_filter",
        )
    with filter_cols[2]:
        confidence_filter = st.selectbox(
            "Confidence",
            ["All", "A", "B", "C", "Pass"],
            key="nba_performance_confidence_filter",
        )
    with filter_cols[3]:
        selected_model_filter = st.selectbox(
            "Model",
            model_filter_options,
            key="nba_performance_model_filter",
        )

    selected_rows = all_rows if selected_model_filter == "All" else current_rows
    model_label = (
        "All models"
        if selected_model_filter == "All"
        else f"Current {model_version}"
    )
    history_today = latest_wnba_history_date(selected_rows) or datetime.now().date()

    day_filters = {
        "Today": {"exact_date": history_today, "label": f"Today ({history_today})"},
        "Yesterday": {
            "exact_date": history_today - timedelta(days=1),
            "label": f"Yesterday ({history_today - timedelta(days=1)})",
        },
        "Last 7": 7,
        "Last 30": 30,
        "All": {"days": None, "exact_date": None, "label": "All history"},
    }[window_filter]
    if isinstance(day_filters, dict):
        days = day_filters.get("days")
        exact_date = day_filters.get("exact_date")
        day_label = day_filters["label"]
    else:
        days = day_filters
        exact_date = None
        day_label = f"{window_filter} days"

    if days is not None:
        filtered_rows = [
            row
            for row in selected_rows
            if wnba_history_row_matches_filters(
                row,
                market_filter,
                days=days,
                confidence=confidence_filter,
                exact_date=None,
                anchor_date=history_today,
            )
        ]
    else:
        filtered_rows = [
            row
            for row in selected_rows
            if wnba_history_row_matches_filters(
                row,
                market_filter,
                days=None,
                confidence=confidence_filter,
                exact_date=exact_date,
            )
        ]

    summary_rows = summarize_wnba_performance_rows(filtered_rows, market_filter)
    detail_rows = wnba_detail_rows(filtered_rows, market_filter)

    with st.expander("NBA Performance History Diagnostics"):
        diag_cols = st.columns(4)
        with diag_cols[0]:
            st.metric("Snapshots", current_summary["snapshots"])
        with diag_cols[1]:
            st.metric("Completed", current_summary["completed"])
        with diag_cols[2]:
            st.metric("Side Signals", current_summary["side_signal_games"])
        with diag_cols[3]:
            st.metric("Scoring Signals", current_summary["scoring_signal_games"])

        st.caption(
            "Snapshot rule: NBA predictions are stored only for pregame snapshots; "
            "final rows update result fields only when a matching snapshot exists."
        )
        st.caption(f"Storage: {storage_backend}")
        st.code(storage_path, language="text")
        st.caption(
            f"Current market version: {market_version} | Current model baseline: {model_version}"
        )

        export_label = (
            "all_models"
            if selected_model_filter == "All"
            else str(model_version).replace(".", "_")
        )
        st.download_button(
            f"Download NBA Performance History CSV ({len(selected_rows)} rows)",
            data=wnba_rows_to_csv(selected_rows),
            file_name=f"nba_model_history_{export_label}.csv",
            mime="text/csv",
            key="nba_history_download",
        )

    if not summary_rows:
        st.info("No NBA tracked results match the selected filters.")
        return

    result_cards = []
    for row in summary_rows:
        completed = (row.get("hits") or 0) + (row.get("misses") or 0)
        pending = row.get("pending") or 0
        record = f"{row.get('hits') or 0}-{row.get('misses') or 0}"
        result_cards.append(
            '<div class="performance-card">'
            f'<div class="performance-market">{escape(row["market"])}</div>'
            f'<div class="performance-hit-rate">{performance_hit_rate(row)}</div>'
            f'<div class="performance-record">{escape(record)} record</div>'
            f'<div class="performance-meta">{completed} completed - {pending} pending</div>'
            '</div>'
        )

    filter_text = f"{model_label} - {day_label}"
    if market_filter != "All":
        filter_text += f" - {market_filter}"
    if confidence_filter != "All":
        filter_text += f" - {confidence_filter} confidence"

    st.html(
        '<div class="model-favorite top-looks">'
        '<div class="model-label">NBA MODEL PERFORMANCE</div>'
        f'<div class="top-look-meta">{escape(filter_text)}</div>'
        '<div class="performance-results">'
        f'{"".join(result_cards)}'
        '</div>'
        '</div>'
    )

    if not detail_rows:
        st.info("No detailed NBA rows match the selected filters.")
        return

    detail_df = pd.DataFrame(detail_rows)
    detail_df = detail_df.rename(
        columns={
            "slate_date": "Slate",
            "market": "Signal",
            "game": "Game",
            "pick": "Pick",
            "confidence": "Confidence",
            "score": "Score",
            "result": "Result",
            "status": "Status",
            "model_version": "Model",
            "market_version": "Market Version",
        }
    )
    st.dataframe(
        detail_df[
            [
                "Slate",
                "Signal",
                "Game",
                "Pick",
                "Confidence",
                "Score",
                "Result",
                "Status",
                "Model",
                "Market Version",
            ]
        ],
        hide_index=True,
        use_container_width=True,
    )

    with st.expander("NBA Performance Splits"):
        tables = load_nba_performance_tables(
            model_version=model_version,
            market_version=market_version,
        )
        split_tabs = st.tabs(["Core", "Confidence", "Side", "Scoring", "History", "Rest"])
        split_keys = ["core", "confidence", "side_location", "scoring", "history", "rest"]
        for tab, split_key in zip(split_tabs, split_keys):
            with tab:
                split_df = pd.DataFrame(tables[split_key])
                if split_df.empty:
                    st.caption("No split rows yet.")
                else:
                    st.dataframe(split_df, width="stretch", hide_index=True)


def render_nba_historical():
    uploaded = st.file_uploader(
        "NBA historical/current-season CSV",
        type=["csv"],
        key="nba_historical_csv",
    )
    if uploaded is None:
        st.info("Upload a normalized NBA games CSV to run the v0 model lab, or use Current Slate for the live ESPN-fed test surface.")
        return

    try:
        games = pd.read_csv(uploaded)
        results, summary = build_nba_historical_lab(games)
    except Exception as exc:
        st.error(f"Could not run NBA model: {exc}")
        return

    if results.empty:
        st.info("No completed NBA games found for the selected data.")
        return

    st.subheader("NBA Historical Lab")
    cols = st.columns(4)
    cols[0].metric("Games", int(summary["games"]))
    cols[1].metric("Winner Accuracy", f"{summary['winner_accuracy']:.1%}")
    cols[2].metric("Side Signals", int(summary["side_signal_games"]))
    cols[3].metric("Margin MAE", summary["margin_mae"])

    render_wnba_summary_tables(nba_historical_summary_tables(results))

    selected_filter = str(get_query_param("filter") or "all").lower()
    render_nba_filter_pills(selected_filter, mode="lab")
    filtered = filter_nfl_games(results, selected_filter, historical=True)
    if filtered.empty:
        st.info("No NBA games match the selected filter.")
        return

    for _, row in filtered.iterrows():
        render_wnba_card(row, historical=True)


def render_nba_model_info_sidebar():
    st.sidebar.title("NBA Controls")
    st.sidebar.caption(f"Market release: {MARKET_RELEASES['NBA']}")
    st.sidebar.caption(f"Model baseline: {MODEL_BASELINES['NBA']}")
    tracking_summary = load_nba_performance_summary(
        model_version=MODEL_BASELINES["NBA"],
        market_version=MARKET_RELEASES["NBA"],
    )
    storage_backend = tracking_summary.get("storage_backend", "Unavailable")
    storage_path = tracking_summary.get("db_path", "N/A")

    with st.sidebar.expander("NBA Model Info"):
        st.markdown(f"""
**Model Scope**: Full-game side and scoring environment

**First Half**: placeholder until a reliable halftime-result feed is added

**NBA Tracking**: separate NBA-only history table

**Snapshots**: {tracking_summary["snapshots"]}

**Completed**: {tracking_summary["completed"]}

**Tracking Writes**: scheduled snapshot workflow

**Storage Backend**: {escape(storage_backend)}

**Storage**: `{escape(storage_path)}`

**Current Status**: Current slate views are All, Top, Side, Scoring, 1H, and Perf.
""")


def render_nba_page():
    st.title("NBA Edge Detector")
    mode = selected_nfl_mode()

    render_nba_model_info_sidebar()
    render_nba_mode_pills(mode)

    if mode == "current":
        render_nba_current()
    else:
        render_nba_historical()


def render_cbb_current():
    default_date = current_date_for_timezone(FALLBACK_TIMEZONE)
    selected_date = st.date_input(
        "Slate Date",
        value=default_date,
        format="MM/DD/YYYY",
        key="cbb_slate_date",
    )
    selected_view = selected_cbb_view("all")
    slate = pd.DataFrame()
    slate_error = None
    try:
        slate, _ = load_cbb_current(selected_date)
    except Exception as exc:
        slate_error = exc

    cbb_history_rows = safe_load_cbb_slate_history_rows(
        MODEL_BASELINES["CBB"],
        MARKET_RELEASES["CBB"],
        selected_date,
    )

    render_cbb_view_pills(selected_view)

    if selected_view == "perf":
        st.caption("Performance history")
        st.caption(format_snapshot_caption(cbb_history_rows))
        st.divider()
        render_cbb_performance_section()
        return

    if slate_error is not None:
        st.error(f"Could not load CBB current slate: {slate_error}")
        return

    if slate.empty:
        st.caption("0 of 0")
        st.caption(format_snapshot_caption(cbb_history_rows))
        st.divider()
        st.info("No CBB games found for the selected slate date.")
        return

    if selected_view in ["top", "first_half"]:
        filtered_count = 0
    else:
        filtered_count = len(filter_wnba_games(slate, selected_view))
    st.caption(f"{filtered_count} of {len(slate)}")
    st.caption(format_snapshot_caption(cbb_history_rows))
    st.divider()

    if selected_view == "top":
        st.info("CBB Top signals are a placeholder until the v0 model has enough tracked performance to define a reliable top-pick cut.")
        return

    if selected_view == "first_half":
        st.info("CBB First Half is included in v0 planning, but official grading is pending until reliable halftime scores are verified.")
        return

    filtered = filter_wnba_games(slate, selected_view)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Games", len(slate))
    c2.metric("Model Signals", len(slate[slate["Model Signal"] != "Pass"]))
    c3.metric("Side Edges", len(slate[slate["Side Edge"] != "Pass"]))
    c4.metric(
        "Scoring Notes",
        len(slate[slate["Scoring Edge"] != "Neutral Scoring Environment"]),
    )

    if filtered.empty:
        st.info("No CBB games match the selected view.")
        return

    for _, row in filtered.iterrows():
        render_wnba_card(row)


def render_cbb_performance_section():
    st.markdown("### CBB Performance")
    model_version = MODEL_BASELINES["CBB"]
    market_version = MARKET_RELEASES["CBB"]
    current_summary = load_cbb_performance_summary(
        model_version=model_version,
        market_version=market_version,
    )
    storage_backend = current_summary.get("storage_backend", "Unavailable")
    storage_path = current_summary.get("db_path", "N/A")
    current_rows = load_cbb_history(
        model_version=model_version,
        market_version=market_version,
    )
    all_rows = load_cbb_history()

    if current_summary["snapshots"] == 0:
        st.info("No CBB performance snapshots recorded yet. Manual CBB snapshots can be run from GitHub Actions once season tracking is ready.")
        return

    model_filter_options = [f"Current {model_version}", "All"]
    filter_cols = st.columns([1, 1, 1, 1])
    with filter_cols[0]:
        market_filter = st.selectbox(
            "Signal",
            ["All", "Side", "Scoring"],
            key="cbb_performance_market_filter",
        )
    with filter_cols[1]:
        window_filter = st.selectbox(
            "Day(s)",
            ["Today", "Yesterday", "Last 7", "Last 30", "All"],
            key="cbb_performance_window_filter",
        )
    with filter_cols[2]:
        confidence_filter = st.selectbox(
            "Confidence",
            ["All", "A", "B", "C", "Pass"],
            key="cbb_performance_confidence_filter",
        )
    with filter_cols[3]:
        selected_model_filter = st.selectbox(
            "Model",
            model_filter_options,
            key="cbb_performance_model_filter",
        )

    selected_rows = all_rows if selected_model_filter == "All" else current_rows
    model_label = (
        "All models"
        if selected_model_filter == "All"
        else f"Current {model_version}"
    )
    history_today = latest_wnba_history_date(selected_rows) or datetime.now().date()

    day_filters = {
        "Today": {"exact_date": history_today, "label": f"Today ({history_today})"},
        "Yesterday": {
            "exact_date": history_today - timedelta(days=1),
            "label": f"Yesterday ({history_today - timedelta(days=1)})",
        },
        "Last 7": 7,
        "Last 30": 30,
        "All": {"days": None, "exact_date": None, "label": "All history"},
    }[window_filter]
    if isinstance(day_filters, dict):
        days = day_filters.get("days")
        exact_date = day_filters.get("exact_date")
        day_label = day_filters["label"]
    else:
        days = day_filters
        exact_date = None
        day_label = f"{window_filter} days"

    if days is not None:
        filtered_rows = [
            row
            for row in selected_rows
            if wnba_history_row_matches_filters(
                row,
                market_filter,
                days=days,
                confidence=confidence_filter,
                exact_date=None,
                anchor_date=history_today,
            )
        ]
    else:
        filtered_rows = [
            row
            for row in selected_rows
            if wnba_history_row_matches_filters(
                row,
                market_filter,
                days=None,
                confidence=confidence_filter,
                exact_date=exact_date,
            )
        ]

    summary_rows = summarize_wnba_performance_rows(filtered_rows, market_filter)
    detail_rows = wnba_detail_rows(filtered_rows, market_filter)

    with st.expander("CBB Performance History Diagnostics"):
        diag_cols = st.columns(4)
        with diag_cols[0]:
            st.metric("Snapshots", current_summary["snapshots"])
        with diag_cols[1]:
            st.metric("Completed", current_summary["completed"])
        with diag_cols[2]:
            st.metric("Side Signals", current_summary["side_signal_games"])
        with diag_cols[3]:
            st.metric("Scoring Notes", current_summary["scoring_signal_games"])

        st.caption(
            "Snapshot rule: CBB predictions are stored only for pregame snapshots; "
            "final rows update result fields only when a matching snapshot exists."
        )
        st.caption(f"Storage: {storage_backend}")
        st.code(storage_path, language="text")
        st.caption(
            f"Current market version: {market_version} | Current model baseline: {model_version}"
        )

        export_label = (
            "all_models"
            if selected_model_filter == "All"
            else str(model_version).replace(".", "_")
        )
        st.download_button(
            f"Download CBB Performance History CSV ({len(selected_rows)} rows)",
            data=wnba_rows_to_csv(selected_rows),
            file_name=f"cbb_model_history_{export_label}.csv",
            mime="text/csv",
            key="cbb_history_download",
        )

    if not summary_rows:
        st.info("No CBB tracked results match the selected filters.")
        return

    result_cards = []
    for row in summary_rows:
        completed = (row.get("hits") or 0) + (row.get("misses") or 0)
        pending = row.get("pending") or 0
        record = f"{row.get('hits') or 0}-{row.get('misses') or 0}"
        result_cards.append(
            '<div class="performance-card">'
            f'<div class="performance-market">{escape(row["market"])}</div>'
            f'<div class="performance-hit-rate">{performance_hit_rate(row)}</div>'
            f'<div class="performance-record">{escape(record)} record</div>'
            f'<div class="performance-meta">{completed} completed - {pending} pending</div>'
            '</div>'
        )

    filter_text = f"{model_label} - {day_label}"
    if market_filter != "All":
        filter_text += f" - {market_filter}"
    if confidence_filter != "All":
        filter_text += f" - {confidence_filter} confidence"

    st.html(
        '<div class="model-favorite top-looks">'
        '<div class="model-label">CBB MODEL PERFORMANCE</div>'
        f'<div class="top-look-meta">{escape(filter_text)}</div>'
        '<div class="performance-results">'
        f'{"".join(result_cards)}'
        '</div>'
        '</div>'
    )

    if not detail_rows:
        st.info("No detailed CBB rows match the selected filters.")
        return

    detail_df = pd.DataFrame(detail_rows)
    detail_df = detail_df.rename(
        columns={
            "slate_date": "Slate",
            "market": "Signal",
            "game": "Game",
            "pick": "Pick",
            "confidence": "Confidence",
            "score": "Score",
            "result": "Result",
            "status": "Status",
            "model_version": "Model",
            "market_version": "Market Version",
        }
    )
    st.dataframe(
        detail_df[
            [
                "Slate",
                "Signal",
                "Game",
                "Pick",
                "Confidence",
                "Score",
                "Result",
                "Status",
                "Model",
                "Market Version",
            ]
        ],
        hide_index=True,
        use_container_width=True,
    )

    with st.expander("CBB Performance Splits"):
        tables = load_cbb_performance_tables(
            model_version=model_version,
            market_version=market_version,
        )
        split_tabs = st.tabs(["Core", "Confidence", "Side", "Scoring", "History", "Rest"])
        split_keys = ["core", "confidence", "side_location", "scoring", "history", "rest"]
        for tab, split_key in zip(split_tabs, split_keys):
            with tab:
                split_df = pd.DataFrame(tables[split_key])
                if split_df.empty:
                    st.caption("No split rows yet.")
                else:
                    st.dataframe(split_df, width="stretch", hide_index=True)


def render_cbb_historical():
    uploaded = st.file_uploader(
        "CBB historical/current-season CSV",
        type=["csv"],
        key="cbb_historical_csv",
    )
    if uploaded is None:
        st.info("Upload a normalized CBB games CSV to run the v0 model lab, or use Current Slate for the live ESPN-fed test surface.")
        return

    try:
        games = pd.read_csv(uploaded)
        results, summary = build_cbb_historical_lab(games)
    except Exception as exc:
        st.error(f"Could not run CBB model: {exc}")
        return

    if results.empty:
        st.info("No completed CBB games found for the selected data.")
        return

    st.subheader("CBB Historical Lab")
    cols = st.columns(4)
    cols[0].metric("Games", int(summary["games"]))
    cols[1].metric("Winner Accuracy", f"{summary['winner_accuracy']:.1%}")
    cols[2].metric("Side Signals", int(summary["side_signal_games"]))
    cols[3].metric("Margin MAE", summary["margin_mae"])

    render_wnba_summary_tables(cbb_historical_summary_tables(results))

    selected_filter = str(get_query_param("filter") or "all").lower()
    render_cbb_filter_pills(selected_filter, mode="lab")
    filtered = filter_nfl_games(results, selected_filter, historical=True)
    if filtered.empty:
        st.info("No CBB games match the selected filter.")
        return

    for _, row in filtered.iterrows():
        render_wnba_card(row, historical=True)


def render_cbb_model_info_sidebar():
    st.sidebar.title("CBB Controls")
    st.sidebar.caption(f"Market release: {MARKET_RELEASES['CBB']}")
    st.sidebar.caption(f"Model baseline: {MODEL_BASELINES['CBB']}")
    tracking_summary = load_cbb_performance_summary(
        model_version=MODEL_BASELINES["CBB"],
        market_version=MARKET_RELEASES["CBB"],
    )
    storage_backend = tracking_summary.get("storage_backend", "Unavailable")
    storage_path = tracking_summary.get("db_path", "N/A")

    with st.sidebar.expander("CBB Model Info"):
        st.markdown(f"""
**Model Scope**: Men's college basketball full-game side and scoring environment

**First Half**: included in v0 planning; official grading waits for reliable halftime scores

**Data Gate**: official picks require enough prior team history and schedule context

**CBB Tracking**: separate CBB-only history table

**Snapshots**: {tracking_summary["snapshots"]}

**Completed**: {tracking_summary["completed"]}

**Tracking Writes**: manual snapshot workflow until season schedule is enabled

**Storage Backend**: {escape(storage_backend)}

**Storage**: `{escape(storage_path)}`

**Current Status**: Current slate views are All, Top, Side, Scoring, 1H, and Perf.
""")


def render_cbb_page():
    st.title("CBB Edge Detector")
    mode = selected_nfl_mode()

    render_cbb_model_info_sidebar()
    render_cbb_mode_pills(mode)

    if mode == "current":
        render_cbb_current()
    else:
        render_cbb_historical()


def render_mls_current():
    default_date = current_date_for_timezone(FALLBACK_TIMEZONE)
    selected_date = st.date_input(
        "Slate Date",
        value=default_date,
        format="MM/DD/YYYY",
        key="mls_slate_date",
    )
    selected_view = selected_mls_view("all")
    slate = pd.DataFrame()
    slate_error = None
    try:
        slate, _ = load_mls_current(selected_date)
    except Exception as exc:
        slate_error = exc

    mls_history_rows = safe_load_mls_slate_history_rows(
        MODEL_BASELINES["MLS"],
        MARKET_RELEASES["MLS"],
        selected_date,
    )

    render_mls_view_pills(selected_view)

    if selected_view == "perf":
        st.caption("Performance history")
        st.caption(format_snapshot_caption(mls_history_rows))
        st.divider()
        render_mls_performance_section()
        return

    if slate_error is not None:
        st.error(f"Could not load MLS current slate: {slate_error}")
        return

    if slate.empty:
        st.info("No MLS regular-season games found for the selected slate date.")
        return

    if selected_view == "first_half":
        filtered_count = 0
    else:
        filtered_count = len(filter_mls_games(slate, selected_view))
    st.caption(f"{filtered_count} of {len(slate)}")
    st.caption(format_snapshot_caption(mls_history_rows))
    st.divider()

    if selected_view == "first_half":
        st.info("MLS First Half is visible as Model Pending until a reliable halftime-result feed and grading rule are added.")
        return

    filtered = filter_mls_games(slate, selected_view)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Games", len(slate))
    c2.metric("Model Signals", len(slate[slate["Model Signal"] != "Pass"]))
    c3.metric("Double Chance", len(slate[slate["Side Edge"] != "Pass"]))
    c4.metric(
        "Goal Signals",
        len(slate[slate["Scoring Edge"] != "Neutral Goals Environment"]),
    )

    if filtered.empty:
        st.info("No MLS games match the selected view.")
        return

    for _, row in filtered.iterrows():
        render_wnba_card(row)


def render_mls_performance_section():
    st.markdown("### MLS Performance")
    model_version = MODEL_BASELINES["MLS"]
    market_version = MARKET_RELEASES["MLS"]
    summary = load_mls_performance_summary(
        model_version=model_version,
        market_version=market_version,
    )
    storage_backend = summary.get("storage_backend", "Unavailable")
    storage_path = summary.get("db_path", "N/A")

    if summary["snapshots"] == 0:
        st.info("No MLS performance snapshots recorded yet. Run the MLS snapshot script after approving a snapshot cadence.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Snapshots", summary["snapshots"])
    c2.metric("Completed", summary["completed"])
    c3.metric(
        "Double Chance",
        f"{summary['double_chance_signal_accuracy']:.1%}",
        help=f"{summary['double_chance_signal_games']} signals",
    )
    c4.metric(
        "Full Match",
        f"{summary['full_match_signal_accuracy']:.1%}",
        help=f"{summary['full_match_signal_games']} signals",
    )

    c5, c6, c7, c8 = st.columns(4)
    c5.metric(
        "Goals",
        f"{summary['goals_signal_accuracy']:.1%}",
        help=f"{summary['goals_signal_games']} signals",
    )
    c6.metric(
        "BTTS",
        f"{summary['btts_signal_accuracy']:.1%}",
        help=f"{summary['btts_signal_games']} discovery signals",
    )
    c7.metric("Margin MAE", summary["margin_mae"])
    c8.metric("Total MAE", summary["total_mae"])

    st.caption(f"Storage Backend: {storage_backend}")
    st.caption(f"Storage: {storage_path}")


def render_mls_model_info_sidebar():
    st.sidebar.title("MLS Controls")
    st.sidebar.caption(f"Market release: {MARKET_RELEASES['MLS']}")
    st.sidebar.caption(f"Model baseline: {MODEL_BASELINES['MLS']}")
    tracking_summary = load_mls_performance_summary(
        model_version=MODEL_BASELINES["MLS"],
        market_version=MARKET_RELEASES["MLS"],
    )
    storage_backend = tracking_summary.get("storage_backend", "Unavailable")
    storage_path = tracking_summary.get("db_path", "N/A")

    with st.sidebar.expander("MLS Model Info"):
        st.markdown(f"""
**Model Scope**: MLS regular season only

**Primary Market**: Double Chance

**Secondary Markets**: Full Match Result and Goals Environment

**Discovery**: BTTS

**First Half**: placeholder until a reliable halftime-result feed is added

**MLS Tracking**: separate MLS-only history table

**Snapshots**: {tracking_summary["snapshots"]}

**Completed**: {tracking_summary["completed"]}

**Tracking Writes**: manual snapshot workflow until a cadence is approved

**Storage Backend**: {escape(storage_backend)}

**Storage**: `{escape(storage_path)}`

**Current Status**: Current slate views are All, Top, DC, Match, Goals, BTTS, 1H, and Perf.
""")


def render_mls_page():
    st.title("MLS Edge Detector")
    mode = selected_nfl_mode()

    render_mls_model_info_sidebar()

    if mode == "current":
        render_mls_current()
    else:
        st.info("MLS Historical Lab is pending for v0. Current slate snapshots and performance tracking are active.")


def render_nhl_current():
    default_date = current_date_for_timezone(FALLBACK_TIMEZONE)
    selected_date = st.date_input(
        "Slate Date",
        value=default_date,
        format="MM/DD/YYYY",
        key="nhl_slate_date",
    )
    selected_view = selected_nhl_view("all")
    slate = pd.DataFrame()
    slate_error = None
    try:
        slate, _ = load_nhl_current(selected_date)
    except Exception as exc:
        slate_error = exc

    nhl_history_rows = safe_load_nhl_slate_history_rows(
        MODEL_BASELINES["NHL"],
        MARKET_RELEASES["NHL"],
        selected_date,
    )

    render_nhl_view_pills(selected_view)

    if selected_view == "perf":
        st.caption("Performance history")
        st.caption(format_snapshot_caption(nhl_history_rows))
        st.divider()
        render_nhl_performance_section()
        return

    if slate_error is not None:
        st.error(f"Could not load NHL current slate: {slate_error}")
        return

    if slate.empty:
        st.info("No NHL games found for the selected slate date.")
        return

    if selected_view in ["top", "first_period"]:
        filtered_count = 0
    else:
        filtered_count = len(filter_nhl_games(slate, selected_view))
    st.caption(f"{filtered_count} of {len(slate)}")
    st.caption(format_snapshot_caption(nhl_history_rows))
    st.divider()

    if selected_view == "top":
        st.info("NHL Top signals are a placeholder until the v0 moneyline model has enough tracked performance to define a reliable top-pick cut.")
        return

    if selected_view == "first_period":
        st.info("NHL First Period is pending until a reliable period-result data source and grading rule are added. Full-game moneyline is active in v0.")
        return

    filtered = filter_nhl_games(slate, selected_view)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Games", len(slate))
    c2.metric("Model Signals", len(slate[slate["Model Signal"] != "Pass"]))
    c3.metric("Moneyline Edges", len(slate[slate["Side Edge"] != "Pass"]))
    c4.metric(
        "Goal Env Notes",
        len(slate[slate["Scoring Edge"] != "Neutral Goal Environment"]),
    )

    if filtered.empty:
        st.info("No NHL games match the selected view.")
        return

    for _, row in filtered.iterrows():
        render_wnba_card(row)


def nhl_signal_result(row, market):
    if market not in ["All", "Moneyline"]:
        return None
    if row.get("side_edge") in [None, "", "Pass"]:
        return None
    return row.get("side_result")


def summarize_nhl_performance_rows(rows, market_filter="All"):
    market_rows = [row for row in rows if nhl_signal_result(row, "Moneyline") is not None]
    if not market_rows:
        return []
    hits = sum(1 for row in market_rows if nhl_signal_result(row, "Moneyline") == "Correct")
    misses = sum(1 for row in market_rows if nhl_signal_result(row, "Moneyline") == "Missed")
    pending = len(market_rows) - hits - misses
    return [
        {
            "market": "Moneyline",
            "total": len(market_rows),
            "hits": hits,
            "misses": misses,
            "pushes": 0,
            "pending": pending,
        }
    ]


def nhl_detail_rows(rows, market_filter="All"):
    detail_rows = []
    for row in rows:
        result = nhl_signal_result(row, "Moneyline")
        if result is None:
            continue
        detail = dict(row)
        detail["market"] = "Moneyline"
        detail["pick"] = row.get("predicted_winner")
        detail["result"] = result or "Pending"
        detail["score"] = row.get("edge_score")
        detail_rows.append(detail)
    return detail_rows


def render_nhl_performance_section():
    st.markdown("### NHL Performance")
    model_version = MODEL_BASELINES["NHL"]
    market_version = MARKET_RELEASES["NHL"]
    current_summary = load_nhl_performance_summary(
        model_version=model_version,
        market_version=market_version,
    )
    storage_backend = current_summary.get("storage_backend", "Unavailable")
    storage_path = current_summary.get("db_path", "N/A")
    current_rows = load_nhl_history(
        model_version=model_version,
        market_version=market_version,
    )
    all_rows = load_nhl_history()

    if current_summary["snapshots"] == 0:
        st.info("No NHL performance snapshots recorded yet. The scheduled NHL snapshot workflow will create pregame snapshots when it runs.")
        return

    model_filter_options = [f"Current {model_version}", "All"]
    filter_cols = st.columns([1, 1, 1])
    with filter_cols[0]:
        window_filter = st.selectbox(
            "Day(s)",
            ["Today", "Yesterday", "Last 7", "Last 30", "All"],
            key="nhl_performance_window_filter",
        )
    with filter_cols[1]:
        confidence_filter = st.selectbox(
            "Confidence",
            ["All", "A", "B", "C", "Pass"],
            key="nhl_performance_confidence_filter",
        )
    with filter_cols[2]:
        selected_model_filter = st.selectbox(
            "Model",
            model_filter_options,
            key="nhl_performance_model_filter",
        )

    selected_rows = all_rows if selected_model_filter == "All" else current_rows
    model_label = "All models" if selected_model_filter == "All" else f"Current {model_version}"
    history_today = latest_wnba_history_date(selected_rows) or datetime.now().date()

    day_filters = {
        "Today": {"exact_date": history_today, "label": f"Today ({history_today})"},
        "Yesterday": {
            "exact_date": history_today - timedelta(days=1),
            "label": f"Yesterday ({history_today - timedelta(days=1)})",
        },
        "Last 7": 7,
        "Last 30": 30,
        "All": {"days": None, "exact_date": None, "label": "All history"},
    }[window_filter]
    if isinstance(day_filters, dict):
        days = day_filters.get("days")
        exact_date = day_filters.get("exact_date")
        day_label = day_filters["label"]
    else:
        days = day_filters
        exact_date = None
        day_label = f"{window_filter} days"

    if days is not None:
        filtered_rows = [
            row
            for row in selected_rows
            if wnba_history_row_matches_filters(
                row,
                "Side",
                days=days,
                confidence=confidence_filter,
                exact_date=None,
                anchor_date=history_today,
            )
        ]
    else:
        filtered_rows = [
            row
            for row in selected_rows
            if wnba_history_row_matches_filters(
                row,
                "Side",
                days=None,
                confidence=confidence_filter,
                exact_date=exact_date,
            )
        ]

    summary_rows = summarize_nhl_performance_rows(filtered_rows)
    detail_rows = nhl_detail_rows(filtered_rows)

    with st.expander("NHL Performance History Diagnostics"):
        diag_cols = st.columns(4)
        with diag_cols[0]:
            st.metric("Snapshots", current_summary["snapshots"])
        with diag_cols[1]:
            st.metric("Completed", current_summary["completed"])
        with diag_cols[2]:
            st.metric("Moneyline Signals", current_summary["side_signal_games"])
        with diag_cols[3]:
            st.metric("Goal Env Signals", 0)

        st.caption(
            "Snapshot rule: NHL predictions are stored only for pregame snapshots; "
            "final rows update result fields only when a matching snapshot exists."
        )
        st.caption(f"Storage: {storage_backend}")
        st.code(storage_path, language="text")
        st.caption(
            f"Current market version: {market_version} | Current model baseline: {model_version}"
        )
        export_label = (
            "all_models"
            if selected_model_filter == "All"
            else str(model_version).replace(".", "_")
        )
        st.download_button(
            f"Download NHL Performance History CSV ({len(selected_rows)} rows)",
            data=wnba_rows_to_csv(selected_rows),
            file_name=f"nhl_model_history_{export_label}.csv",
            mime="text/csv",
            key="nhl_history_download",
        )

    if not summary_rows:
        st.info("No NHL tracked moneyline results match the selected filters.")
        return

    result_cards = []
    for row in summary_rows:
        completed = (row.get("hits") or 0) + (row.get("misses") or 0)
        pending = row.get("pending") or 0
        record = f"{row.get('hits') or 0}-{row.get('misses') or 0}"
        result_cards.append(
            '<div class="performance-card">'
            f'<div class="performance-market">{escape(row["market"])}</div>'
            f'<div class="performance-hit-rate">{performance_hit_rate(row)}</div>'
            f'<div class="performance-record">{escape(record)} record</div>'
            f'<div class="performance-meta">{completed} completed - {pending} pending</div>'
            '</div>'
        )

    filter_text = f"{model_label} - {day_label} - Moneyline"
    if confidence_filter != "All":
        filter_text += f" - {confidence_filter} confidence"

    st.html(
        '<div class="model-favorite top-looks">'
        '<div class="model-label">NHL MODEL PERFORMANCE</div>'
        f'<div class="top-look-meta">{escape(filter_text)}</div>'
        '<div class="performance-results">'
        f'{"".join(result_cards)}'
        '</div>'
        '</div>'
    )

    if not detail_rows:
        st.info("No detailed NHL rows match the selected filters.")
        return

    detail_df = pd.DataFrame(detail_rows)
    detail_df = detail_df.rename(
        columns={
            "slate_date": "Slate",
            "market": "Signal",
            "game": "Game",
            "pick": "Pick",
            "confidence": "Confidence",
            "score": "Score",
            "result": "Result",
            "status": "Status",
            "model_version": "Model",
            "market_version": "Market Version",
        }
    )
    st.dataframe(
        detail_df[
            [
                "Slate",
                "Signal",
                "Game",
                "Pick",
                "Confidence",
                "Score",
                "Result",
                "Status",
                "Model",
                "Market Version",
            ]
        ],
        hide_index=True,
        use_container_width=True,
    )

    with st.expander("NHL Performance Splits"):
        tables = load_nhl_performance_tables(
            model_version=model_version,
            market_version=market_version,
        )
        split_tabs = st.tabs(["Core", "Confidence", "Moneyline", "History", "Rest"])
        split_keys = ["core", "confidence", "side_location", "history", "rest"]
        for tab, split_key in zip(split_tabs, split_keys):
            with tab:
                split_df = pd.DataFrame(tables[split_key])
                if split_df.empty:
                    st.caption("No split rows yet.")
                else:
                    st.dataframe(split_df, width="stretch", hide_index=True)


def render_nhl_historical():
    uploaded = st.file_uploader(
        "NHL historical/current-season CSV",
        type=["csv"],
        key="nhl_historical_csv",
    )
    if uploaded is None:
        st.info("Upload a normalized NHL games CSV to run the v0 model lab, or use Current Slate for the live NHL schedule-fed test surface.")
        return

    try:
        games = pd.read_csv(uploaded)
        results, summary = build_nhl_historical_lab(games)
    except Exception as exc:
        st.error(f"Could not run NHL model: {exc}")
        return

    if results.empty:
        st.info("No completed NHL games found for the selected data.")
        return

    st.subheader("NHL Historical Lab")
    cols = st.columns(4)
    cols[0].metric("Games", int(summary["games"]))
    cols[1].metric("Moneyline Accuracy", f"{summary['moneyline_accuracy']:.1%}")
    cols[2].metric("Moneyline Signals", int(summary["moneyline_signal_games"]))
    cols[3].metric("Goal Env", "Discovery")

    render_wnba_summary_tables(nhl_historical_summary_tables(results))

    selected_filter = str(get_query_param("filter") or "all").lower()
    render_nhl_filter_pills(selected_filter, mode="lab")
    filtered = filter_nhl_games(results, selected_filter, historical=True)
    if filtered.empty:
        st.info("No NHL games match the selected filter.")
        return

    for _, row in filtered.iterrows():
        render_wnba_card(row, historical=True)


def render_nhl_model_info_sidebar():
    st.sidebar.title("NHL Controls")
    st.sidebar.caption(f"Market release: {MARKET_RELEASES['NHL']}")
    st.sidebar.caption(f"Model baseline: {MODEL_BASELINES['NHL']}")
    tracking_summary = load_nhl_performance_summary(
        model_version=MODEL_BASELINES["NHL"],
        market_version=MARKET_RELEASES["NHL"],
    )
    storage_backend = tracking_summary.get("storage_backend", "Unavailable")
    storage_path = tracking_summary.get("db_path", "N/A")

    with st.sidebar.expander("NHL Model Info"):
        st.markdown(f"""
**Model Scope**: Full-game moneyline only

**First Period**: placeholder until a reliable period-result feed is added

**Goal Environment**: discovery context, not official performance

**NHL Tracking**: separate NHL-only history table

**Snapshots**: {tracking_summary["snapshots"]}

**Completed**: {tracking_summary["completed"]}

**Tracking Writes**: scheduled snapshot workflow

**Storage Backend**: {escape(storage_backend)}

**Storage**: `{escape(storage_path)}`

**Current Status**: Current slate views are All, Top, ML, 1P, and Perf.
""")


def render_nhl_page():
    st.title("NHL Edge Detector")
    mode = selected_nfl_mode()

    render_nhl_model_info_sidebar()
    render_nhl_mode_pills(mode)

    if mode == "current":
        render_nhl_current()
    else:
        render_nhl_historical()


def render_wnba_model_info_sidebar():
    st.sidebar.title("WNBA Controls")
    st.sidebar.caption(f"Product release: {APP_VERSION}")
    st.sidebar.caption(f"Market release: {MARKET_RELEASES['WNBA']}")
    st.sidebar.caption(f"Model baseline: {MODEL_BASELINES['WNBA']}")
    st.sidebar.divider()
    st.sidebar.subheader("Data Sources")
    st.sidebar.markdown("""
**Current Slate**
ESPN scoreboard feed

**Performance Tracking**
WNBA-only history table

**Model Scope**
Matchup intelligence only. No odds, staking, or betting recommendations.
""")

    with st.sidebar.expander("WNBA Model Info"):
        tracking_summary = load_wnba_performance_summary(
            model_version=MODEL_BASELINES["WNBA"],
            market_version=MARKET_RELEASES["WNBA"],
        )
        storage_backend = tracking_summary.get("storage_backend", "Unavailable")
        storage_path = tracking_summary.get("db_path", "N/A")
        st.markdown(f"""
**WNBA Tracking**: separate WNBA-only history

**Snapshots**: {tracking_summary["snapshots"]}

**Completed**: {tracking_summary["completed"]}

**Tracking Writes**: scheduled snapshot workflow

**Storage Backend**: {escape(storage_backend)}

**Storage**: `{escape(storage_path)}`

**Current Status**: Current slate views are All, Top, Side, Scoring, Early, and Perf.

**Top / Early**: placeholders until enough WNBA-only tracked results exist to define those cuts.
""")


def render_wnba_page():
    st.title("WNBA Edge Detector")
    mode = selected_nfl_mode()

    render_wnba_model_info_sidebar()

    if mode == "current":
        render_wnba_current()
    else:
        render_wnba_historical()


@st.cache_data(ttl=900)
def load_wnba_current(selected_date):
    return build_wnba_current_slate(
        today=selected_date,
        days_ahead=0,
        slate_date=selected_date,
    )


@st.cache_data(ttl=900)
def load_nba_current(selected_date):
    return build_nba_current_slate(
        today=selected_date,
        days_ahead=0,
        slate_date=selected_date,
    )


@st.cache_data(ttl=900)
def load_nhl_current(selected_date):
    return build_nhl_current_slate(
        today=selected_date,
        days_ahead=0,
        slate_date=selected_date,
    )


@st.cache_data(ttl=900)
def load_cbb_current(selected_date):
    return build_cbb_current_slate(
        today=selected_date,
        days_ahead=0,
        slate_date=selected_date,
    )


@st.cache_data(ttl=900)
def load_mls_current(selected_date):
    return build_mls_current_slate(
        today=selected_date,
        days_ahead=0,
        slate_date=selected_date,
    )


@st.cache_data(ttl=900)
def load_wnba_current_lab():
    return build_wnba_current_season_lab()


@st.cache_data(ttl=900)
def load_nba_current_lab():
    return build_nba_current_season_lab()


@st.cache_data(ttl=900)
def load_nhl_current_lab():
    return build_nhl_current_season_lab()


@st.cache_data(ttl=900)
def load_cbb_current_lab():
    return build_cbb_current_season_lab()


@st.cache_data(ttl=900)
def load_games(selected_date, model_cache_version, display_timezone):
    return get_today_games(selected_date.isoformat(), display_timezone)


display_timezone, timezone_detected = detect_browser_timezone()
default_slate_date = current_date_for_timezone(display_timezone)
max_slate_date = default_slate_date + timedelta(days=1)

active_sport = selected_sport()
render_sport_picker(active_sport)

if active_sport == "NFL":
    render_nfl_page()
    st.stop()

if active_sport == "WNBA":
    render_wnba_page()
    st.stop()

if active_sport == "NBA":
    render_nba_page()
    st.stop()

if active_sport == "NHL":
    render_nhl_page()
    st.stop()

if active_sport == "CBB":
    render_cbb_page()
    st.stop()

if active_sport == "MLS":
    render_mls_page()
    st.stop()

if active_sport != "MLB":
    st.title(f"{active_sport} Edge Detector")
    st.info(f"{active_sport} module is coming soon.")
    st.stop()

st.title("⚾ MLB Edge Detector")

st.sidebar.title("Controls")
st.sidebar.caption(f"Model version: {APP_VERSION}")
if (
    "header_slate_date" in st.session_state
    and st.session_state["header_slate_date"] > max_slate_date
):
    st.session_state["header_slate_date"] = max_slate_date

selected_date = st.date_input(
    "Slate Date",
    value=default_slate_date,
    max_value=max_slate_date,
    format="MM/DD/YYYY",
    key="header_slate_date",
)
timezone_label = "local" if timezone_detected else "Eastern fallback"
st.sidebar.caption(f"Times shown in {display_timezone} ({timezone_label})")
st.sidebar.caption("Model 2.3 promoted; 2.2.7 retained as rollback reference.")
st.sidebar.divider()
st.sidebar.subheader("Data Sources")

st.sidebar.markdown("""
**Game Schedule / Probable Pitchers**  
MLB Stats API

**Team Records**  
MLB Standings API

**Pitcher Season Stats**  
MLB Stats API

**Bullpen Fatigue**  
MLB Game Boxscore API

**Team 1st Inning Offense**  
MLB Linescore API

**Pitcher 1st Inning Metrics**  
Baseball Savant / Statcast
""")

if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

games = load_games(selected_date, MODEL_CACHE_VERSION, display_timezone)

if games.empty:
    st.warning("No MLB games found for selected date.")
    st.stop()

games = games.copy()
slate_history_rows = safe_load_slate_history_rows(
    PERFORMANCE_TRACKING_VERSION,
    selected_date,
)
games = apply_tracked_snapshot_to_games(
    games,
    PERFORMANCE_TRACKING_VERSION,
    selected_date,
    history_rows=slate_history_rows,
)

top_look_game_names = top_look_games(games)
first_inning_pick_text = games["First Inning Pick"].fillna("").astype(str)
nrfi_mask = first_inning_pick_text.str.contains("NRFI", case=False, na=False)
yrfi_mask = first_inning_pick_text.str.contains("YRFI", case=False, na=False)
game_mask = ~games["Full Game Pick"].apply(is_no_edge_pick)
f5_mask = ~games["F5 Pick"].apply(is_no_edge_pick)
selected_filter = selected_mlb_filter()
render_mlb_filter_pills(selected_filter)
show_watches, show_leans = render_mlb_discovery_controls()

filtered = games.copy()
base_mask = pd.Series(True, index=games.index)

if selected_filter == "Top Looks":
    base_mask = games["Game"].isin(top_look_game_names)
elif selected_filter == "NRFI":
    base_mask = nrfi_mask
elif selected_filter == "YRFI":
    base_mask = yrfi_mask
elif selected_filter == "F5":
    base_mask = f5_mask
elif selected_filter == "Game":
    base_mask = game_mask

if selected_filter == "Performance":
    filtered = games.copy()
else:
    discovery_mask = pd.Series(False, index=games.index)
    if show_watches:
        discovery_mask = discovery_mask | games.apply(
            lambda row: has_discovery_label(row, selected_filter, "Watch"),
            axis=1,
        )
    if show_leans:
        discovery_mask = discovery_mask | games.apply(
            lambda row: has_discovery_label(row, selected_filter, "Lean"),
            axis=1,
        )

    if show_watches or show_leans:
        if selected_filter == "All Games":
            filtered = games[discovery_mask]
        else:
            filtered = games[base_mask | discovery_mask]
    else:
        filtered = games[base_mask]

filtered = filtered.sort_values(
    ["Status Sort", "Game Sort Time"],
    ascending=[True, True],
    na_position="last",
)

if selected_filter == "Performance":
    performance_history_date = latest_history_slate_date() or selected_date
    performance_total = sum(
        row.get("total") or 0
        for row in safe_load_performance_summary(
            PERFORMANCE_TRACKING_VERSION,
            exact_date=performance_history_date,
        )
    )
    st.caption(f"{performance_total} results")
else:
    st.caption(f"{len(filtered)} of {len(games)}")
st.caption(format_snapshot_caption(slate_history_rows))

st.divider()

if selected_filter == "Performance":
    render_model_performance(PERFORMANCE_TRACKING_VERSION, selected_date)
    st.stop()

if selected_filter in ["All Games", "Top Looks"]:
    st.html(render_top_looks(games))

# Legacy V1 model-favorite UI is intentionally quarantined because it can
# conflict with the V2 model-specific outputs displayed in Top Looks.

st.subheader("Game Cards")

if filtered.empty:
    st.info("No games match the selected filters.")
else:
    for _, row in filtered.iterrows():
        away_team, home_team = split_game_name(row["Game"])
        away_short = team_abbreviation(away_team)
        home_short = team_abbreviation(home_team)
        logo_matchup = render_logo_matchup(away_team, home_team)
        market_watch = render_market_watch(row)
        data_quality_notice = render_data_quality_notice(row)
        card_anchor = game_anchor(row["Game"])
        key_factors = render_key_factor_panels(row, away_team, home_team)
        discovery_label_html = render_discovery_labels(row)
        first_inning_pick = get_row_value(row, "First Inning Pick")
        first_inning_confidence = get_row_value(row, "First Inning Confidence")
        f5_pick = get_row_value(row, "F5 Pick")
        f5_confidence = get_row_value(row, "F5 Confidence")
        full_game_pick = get_row_value(row, "Full Game Pick")
        full_game_confidence = get_row_value(row, "Full Game Confidence")
        first_inning_result = ""
        f5_result = ""
        full_game_result = ""
        if should_show_game_result(get_row_value(row, "Status", "")):
            first_inning_result_value = get_row_value(row, "First Inning Result", "")
            f5_result_value = get_row_value(row, "F5 Result", "")
            full_game_result_value = get_row_value(row, "Full Game Result", "")
            first_inning_compact_result = get_row_value(row, "First Inning Result Compact", "")
            if first_inning_compact_result not in [None, "", "N/A", "Pending"]:
                first_inning_compact_result = f"Result: {first_inning_compact_result}"
            first_inning_result = render_decision_result(
                first_inning_result_value,
                first_inning_compact_result,
                grade_history_first_inning(first_inning_pick, first_inning_result_value),
            )
            f5_result = render_decision_result(
                f5_result_value,
                get_row_value(row, "F5 Result Compact", ""),
                grade_history_team_pick(f5_pick, f5_result_value, "After 5:"),
            )
            full_game_result = render_decision_result(
                full_game_result_value,
                get_row_value(row, "Full Game Result Compact", ""),
                grade_history_team_pick(full_game_pick, full_game_result_value, "Final:"),
            )
        first_inning_display = format_decision_pick(
            first_inning_pick,
            first_inning_confidence,
            away_team,
            home_team,
            market="first",
        )
        f5_display = format_decision_pick(
            f5_pick,
            f5_confidence,
            away_team,
            home_team,
            market="f5",
        )
        full_game_display = format_decision_pick(
            full_game_pick,
            full_game_confidence,
            away_team,
            home_team,
            market="full_game",
        )
        away_pitcher_yrfi_display = format_yrfi_vs_league(row, "Away Pitcher YRFI %")
        home_pitcher_yrfi_display = format_yrfi_vs_league(row, "Home Pitcher YRFI %")
        away_offense_yrfi_display = format_yrfi_vs_league(row, "Away Offense YRFI %")
        home_offense_yrfi_display = format_yrfi_vs_league(row, "Home Offense YRFI %")
        first_signal_direction = first_inning_signal_direction(row)
        first_signal_active = first_signal_direction is not None
        league_yrfi = get_numeric_value(row, "League YRFI %")
        away_pitcher_yrfi_cell, home_pitcher_yrfi_cell = signal_cells_by_direction(
            row,
            "Away Pitcher YRFI %",
            "Home Pitcher YRFI %",
            first_signal_direction,
            away_pitcher_yrfi_display,
            home_pitcher_yrfi_display,
            league_yrfi,
        )
        away_first_era_cell, home_first_era_cell = signal_cells_by_direction(
            row,
            "Away 1st ERA",
            "Home 1st ERA",
            first_signal_direction,
            neutral=3.75,
        )
        away_first_whip_cell, home_first_whip_cell = signal_cells_by_direction(
            row,
            "Away 1st WHIP",
            "Home 1st WHIP",
            first_signal_direction,
            neutral=1.15,
        )
        away_offense_yrfi_cell, home_offense_yrfi_cell = signal_cells_by_direction(
            row,
            "Away Offense YRFI %",
            "Home Offense YRFI %",
            first_signal_direction,
            away_offense_yrfi_display,
            home_offense_yrfi_display,
            league_yrfi,
        )
        away_first_run_cell, home_first_run_cell = signal_cells_by_direction(
            row,
            "Away 1st Run Avg",
            "Home 1st Run Avg",
            first_signal_direction,
            neutral=0.45,
        )
        starter_edge_winner = replace_home_away(
            get_row_value(row, "Starter Edge Winner", "Pass"),
            away_team,
            home_team,
        )
        offensive_edge_winner = replace_home_away(
            get_row_value(row, "Offensive Edge Winner", "Pass"),
            away_team,
            home_team,
        )
        bullpen_signal_active = (
            not is_no_edge_pick(get_row_value(row, "Bullpen Edge Winner", "No Edge"))
            and (get_numeric_value(row, "Bullpen Edge Margin") or 0) >= 6
        )
        away_fatigue_cell, home_fatigue_cell = signal_cells_by_winner(
            row,
            "Away Bullpen Fatigue",
            "Home Bullpen Fatigue",
            "Bullpen Edge Winner",
            bullpen_signal_active,
        )
        away_yesterday_pitch_cell, home_yesterday_pitch_cell = signal_cells_by_winner(
            row,
            "Away Yesterday Pitches",
            "Home Yesterday Pitches",
            "Bullpen Edge Winner",
            bullpen_signal_active,
        )
        away_three_day_pitch_cell, home_three_day_pitch_cell = signal_cells_by_winner(
            row,
            "Away 3 Day Bullpen Pitches",
            "Home 3 Day Bullpen Pitches",
            "Bullpen Edge Winner",
            bullpen_signal_active,
        )
        away_back_to_back_cell, home_back_to_back_cell = signal_cells_by_winner(
            row,
            "Away Back-to-Back Arms",
            "Home Back-to-Back Arms",
            "Bullpen Edge Winner",
            bullpen_signal_active,
        )
        bullpen_edge_winner = replace_home_away(
            get_row_value(row, "Bullpen Edge Winner", "Pass"),
            away_team,
            home_team,
        )

        st.html(f"""
        <div id="{card_anchor}" class="game-card">
            {logo_matchup}

            <div class="game-title">{row["Game"]}</div>
            <div class="muted">{escape(format_game_status_line(row))}</div>

            {data_quality_notice}
            <input class="edge-view-control edge-view-first" type="radio" name="{card_anchor}-edge-view" id="{card_anchor}-first" checked>
            <input class="edge-view-control edge-view-f5" type="radio" name="{card_anchor}-edge-view" id="{card_anchor}-f5">
            <input class="edge-view-control edge-view-full" type="radio" name="{card_anchor}-edge-view" id="{card_anchor}-full">

            <div class="decision-stack">
                <label class="decision-line decision-first" for="{card_anchor}-first">🎯 1st Inning: {first_inning_display}{first_inning_result}</label>
                <label class="decision-line decision-f5" for="{card_anchor}-f5">⚾ First 5: {f5_display}{f5_result}</label>
                <label class="decision-line decision-full" for="{card_anchor}-full">🏆 Full Game: {full_game_display}{full_game_result}</label>
            </div>

            {key_factors}

            {market_watch}
        </div>
        """)

        with st.expander(f"🔍 Analysis: {row['Game']}"):
            if discovery_label_html:
                st.html(discovery_label_html)
            st.markdown("### Edge Breakdown")

            st.markdown("#### Starter Edge")
            st.markdown(f"""
            | Metric | Value |
            |---|---|
            | {away_team} Starter Edge | {get_row_value(row, "Away Starter Edge", "TBD")} |
            | {home_team} Starter Edge | {get_row_value(row, "Home Starter Edge", "TBD")} |
            | Starter Edge Winner | {starter_edge_winner} |
            | Starter Edge Margin | {get_row_value(row, "Starter Edge Margin", "TBD")} |
            """)

            st.markdown("#### Offensive Edge")
            st.markdown(f"""
            | Metric | Value |
            |---|---|
            | {away_team} Offensive Edge | {get_row_value(row, "Away Offensive Edge", "TBD")} |
            | {home_team} Offensive Edge | {get_row_value(row, "Home Offensive Edge", "TBD")} |
            | Offensive Edge Winner | {offensive_edge_winner} |
            | Offensive Edge Margin | {get_row_value(row, "Offensive Edge Margin", "TBD")} |
            """)

            st.markdown("#### Bullpen Edge")
            st.markdown(f"""
            | Metric | Value |
            |---|---|
            | {away_team} Bullpen Edge | {get_row_value(row, "Away Bullpen Edge", "TBD")} |
            | {home_team} Bullpen Edge | {get_row_value(row, "Home Bullpen Edge", "TBD")} |
            | Bullpen Edge Winner | {bullpen_edge_winner} |
            | Bullpen Edge Margin | {get_row_value(row, "Bullpen Edge Margin", "TBD")} |
            """)

            st.markdown("---")
            st.markdown("### Pitching Matchup")
            st.markdown(f"""
            | Metric | {away_team} Starter | {home_team} Starter |
            |---|---|---|
            | Pitcher | {row["Away Pitcher"]} | {row["Home Pitcher"]} |
            | Throws | {get_row_value(row, "Away Pitcher Throws", "N/A")} | {get_row_value(row, "Home Pitcher Throws", "N/A")} |
            | Record | {row["Away Pitcher Record"]} | {row["Home Pitcher Record"]} |
            | IP/Start | {get_row_value(row, "Away IP/Start", "N/A")} | {get_row_value(row, "Home IP/Start", "N/A")} |
            | IP | {row["Away IP"]} | {row["Home IP"]} |
            | K | {row["Away K"]} | {row["Home K"]} |
            | ERA | {row["Away ERA"]} | {row["Home ERA"]} |
            | WHIP | {row["Away WHIP"]} | {row["Home WHIP"]} |
            | {signal_label("Pitcher YRFI% vs Lg Avg", first_signal_active)} | {away_pitcher_yrfi_cell} | {home_pitcher_yrfi_cell} |
            | {signal_label("1st Inning ERA", first_signal_active)} | {away_first_era_cell} | {home_first_era_cell} |
            | {signal_label("1st Inning WHIP", first_signal_active)} | {away_first_whip_cell} | {home_first_whip_cell} |
            | 1st Inning Source | {get_row_value(row, "Away 1st Split Source", "N/A")} | {get_row_value(row, "Home 1st Split Source", "N/A")} |
            | 1st Inning Sample | {get_row_value(row, "Away 1st Games", "N/A")} G / {get_row_value(row, "Away 1st IP", "N/A")} IP | {get_row_value(row, "Home 1st Games", "N/A")} G / {get_row_value(row, "Home 1st IP", "N/A")} IP |
            | Confidence Guardrail | {get_row_value(row, "First Inning Sample Cap", "N/A")} | {get_row_value(row, "First Inning Sample Note", "N/A")} |
            | 1st Inning R / ER | {get_row_value(row, "Away 1st R", "N/A")} / {get_row_value(row, "Away 1st ER", "N/A")} | {get_row_value(row, "Home 1st R", "N/A")} / {get_row_value(row, "Home 1st ER", "N/A")} |
            | 1st Inning H / BB / HR | {get_row_value(row, "Away 1st H", "N/A")} / {get_row_value(row, "Away 1st BB", "N/A")} / {get_row_value(row, "Away 1st HR", "N/A")} | {get_row_value(row, "Home 1st H", "N/A")} / {get_row_value(row, "Home 1st BB", "N/A")} / {get_row_value(row, "Home 1st HR", "N/A")} |
            """)
            if first_signal_active:
                st.caption("\\* - Edge Signal")

            st.markdown("---")
            st.markdown("### Offensive Matchup")
            st.markdown(f"""
            | Metric | {away_team} | {home_team} |
            |---|---|---|
            | Record | {row["Away Record"]} | {row["Home Record"]} |
            | Runs Per Game | {get_row_value(row, "Away Runs Per Game", "N/A")} | {get_row_value(row, "Home Runs Per Game", "N/A")} |
            | {signal_label("Offense YRFI% vs Lg Avg", first_signal_active)} | {away_offense_yrfi_cell} | {home_offense_yrfi_cell} |
            | {signal_label("First-Inning Run Avg", first_signal_active)} | {away_first_run_cell} | {home_first_run_cell} |
            """)
            if first_signal_active:
                st.caption("\\* - Edge Signal")

            pressure_rows, pressure_summary, pressure_model_read = first_inning_pressure_summary(row)

            st.markdown("### 1st Inning Pressure")
            st.table(pd.DataFrame(pressure_rows))
            st.caption(pressure_summary)
            st.caption(pressure_model_read)

            st.markdown("### 1st Inning Matchup Pressure")
            st.markdown(f"""
            | Matchup | Offense YRFI% | Opp Starter YRFI% | Read |
            |---|---|---|---|
            | {away_short} offense vs {home_short} starter | {away_offense_yrfi_display} | {home_pitcher_yrfi_display} | {get_row_value(row, "Away 1st Inning Matchup Pressure", "Neutral")} |
            | {home_short} offense vs {away_short} starter | {home_offense_yrfi_display} | {away_pitcher_yrfi_display} | {get_row_value(row, "Home 1st Inning Matchup Pressure", "Neutral")} |
            """)
            st.caption(
                f'Matchup summary: {get_row_value(row, "1st Inning Matchup Summary", "No clear matchup pressure")} '
                f'| Review modifier: {get_row_value(row, "1st Inning Matchup Modifier", 0)}'
            )

            st.markdown("---")
            st.markdown("### Bullpen Usage")
            st.markdown(f"""
            | Metric | {away_team} Bullpen | {home_team} Bullpen |
            |---|---|---|
            | Rating | {row["Away Bullpen Status"]} | {row["Home Bullpen Status"]} |
            | {signal_label("Fatigue Score", bullpen_signal_active)} | {away_fatigue_cell} | {home_fatigue_cell} |
            | {signal_label("Yesterday Pitches", bullpen_signal_active)} | {away_yesterday_pitch_cell} | {home_yesterday_pitch_cell} |
            | 3-Day Bullpen IP | {row["Away 3 Day Bullpen IP"]} | {row["Home 3 Day Bullpen IP"]} |
            | {signal_label("3-Day Bullpen Pitches", bullpen_signal_active)} | {away_three_day_pitch_cell} | {home_three_day_pitch_cell} |
            | 3-Day Relievers Used | {row["Away 3 Day Relievers"]} | {row["Home 3 Day Relievers"]} |
            | {signal_label("Back-to-Back Arms", bullpen_signal_active)} | {away_back_to_back_cell} | {home_back_to_back_cell} |
            """)
            if bullpen_signal_active:
                st.caption("\\* - Edge Signal")

            st.markdown("---")
            st.markdown("### Last 5 Game Results")
            st.html(render_last_five_results(row))

st.divider()

csv = filtered.to_csv(index=False).encode("utf-8")

st.download_button(
    label="Download MLB Report",
    data=csv,
    file_name=f"first_five_edge_report_{selected_date}.csv",
    mime="text/csv"
)
