import streamlit as st
from datetime import datetime, timedelta
from html import escape
import re
from zoneinfo import ZoneInfo
from mlb_agent import get_today_games
from model_history import (
    load_performance_summary,
    record_model_history,
)

APP_VERSION = "2.2.7"
MODEL_CACHE_VERSION = "edge-v2-local-time-v1"
FALLBACK_TIMEZONE = "America/New_York"

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

div[data-testid="stRadio"] [role="radiogroup"] {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 12px;
}

div[data-testid="stRadio"] [role="radiogroup"] label {
    display: flex;
    align-items: center;
    min-height: 78px;
    padding: 14px 16px;
    border-radius: 14px;
    background: #1e293b;
    border: 1px solid #334155;
    color: #f8fafc;
    box-shadow: inset 0 0 24px rgba(14, 165, 233, 0.12);
}

div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(1) {
    grid-column: 1 / -1;
    border-color: #22c55e;
}

div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(2) {
    border-color: #38bdf8;
}

div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(3) {
    border-color: #f97316;
}

div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(4) {
    border-color: #a855f7;
}

div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(5) {
    border-color: #ef4444;
}

div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(6) {
    border-color: #f59e0b;
}

div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(7) {
    border-color: #14b8a6;
}

div[data-testid="stRadio"] [role="radiogroup"] label p {
    color: #f8fafc;
    font-weight: 900;
    line-height: 1.25;
    white-space: pre-line;
    word-break: keep-all;
}

div[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {
    background: linear-gradient(135deg, #1d4ed8, #0f766e);
    box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.28), inset 0 0 26px rgba(255, 255, 255, 0.08);
}

@media (max-width: 640px) {
    div[data-testid="stRadio"] [role="radiogroup"] {
        grid-template-columns: repeat(6, minmax(44px, 1fr));
        gap: 6px;
    }

    .performance-results {
        grid-template-columns: 1fr;
    }

    div[data-testid="stRadio"] [role="radiogroup"] label {
        width: 100% !important;
        box-sizing: border-box;
        min-height: 44px;
        padding: 8px 4px !important;
        border-radius: 12px;
        justify-content: center;
        text-align: center;
    }

    div[data-testid="stRadio"] [role="radiogroup"] label > div:first-child {
        display: none;
    }

    div[data-testid="stRadio"] [role="radiogroup"] label p {
        display: none;
    }

    div[data-testid="stRadio"] [role="radiogroup"] label::after {
        color: #f8fafc;
        font-size: 12px;
        font-weight: 900;
        line-height: 1;
        white-space: nowrap;
    }

    div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(1)::after {
        content: "All";
    }

    div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(2)::after {
        content: "Top";
    }

    div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(3)::after {
        content: "NRFI";
    }

    div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(4)::after {
        content: "YRFI";
    }

    div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(5)::after {
        content: "F5";
    }

    div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(6)::after {
        content: "Game";
    }

    div[data-testid="stRadio"] [role="radiogroup"] label:nth-child(7)::after {
        content: "Perf";
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
    return str(pick).strip() in ["Pass", "No Edge", "F5 Pass"]


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


def render_decision_result(result, compact_result=None):
    if result in [None, "", "N/A", "Pending"]:
        return ""

    compact_result = compact_result or result
    return (
        f'<span class="decision-result decision-result-full">Result: {escape(str(result))}</span>'
        f'<span class="decision-result decision-result-mobile">{escape(str(compact_result))}</span>'
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
        if value is not None
    ]
    if not numbers:
        return None

    return sum(numbers) / len(numbers)


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
        f'{counts["Confirms"]} confirm • {counts["Warning"]} warning • '
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
        return "Scoring Environment Watch", [
            "Both bullpens fatigued",
            "Elevated late-game scoring risk",
        ]

    if both_bullpens_fresh and strong_starting_pitching:
        return "Run Prevention Watch", [
            "Fresh bullpens",
            "Strong starting pitching",
        ]

    if starter_margin >= 8 and bullpen_margin < 6:
        return "In-Game Edge Watch", [
            "Early starter edge detected",
            "Bullpen edge remains uncertain",
            "Recheck as pitch counts rise",
        ]

    return "No Clear Edge", [
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
        <div class="market-heading">📈 Edge Watch</div>
        <div class="market-pick">{escape(market_pick)}</div>
        <div class="market-why">Why?</div>
        <div class="reason-stack">{reason_items}</div>
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
        factors.append("Primary drivers: pitcher and offense YRFI rates")
        factors.append("Support checks: 1st ERA, 1st WHIP, 1st run avg")

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

    return f"{label} {score:.1f} • Confidence {confidence}"


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
            "title": "Bullpen Watch: No edges found",
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
            "title": f'Bullpen Watch: {game_matchup_label(bullpen_row["Game"])}',
            "meta": f'Fatigue {bullpen_row["_fatigue_max"]} • Bullpen edge {get_row_value(bullpen_row, "Bullpen Edge Margin", "N/A")}',
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
                f"{record} • {pending} pending",
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

    filter_cols = st.columns([1, 1, 1])
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

    day_filters = {
        "Today": {"exact_date": slate_date, "label": "Today"},
        "Yesterday": {
            "exact_date": slate_date - timedelta(days=1),
            "label": "Yesterday",
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

    summary_rows = load_performance_summary(
        model_version,
        market=market_filter,
        days=days,
        confidence=confidence_filter,
        exact_date=exact_date,
    )

    if not summary_rows:
        st.info("No graded model history found yet.")
        return

    result_cards = []
    for row in summary_rows:
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
            f'<div class="performance-meta">{completed} completed &bull; {pending} pending</div>'
            '</div>'
        )

    filter_text = day_label
    if market_filter != "All":
        filter_text += f" • {market_filter}"
    if confidence_filter != "All":
        filter_text += f" • {confidence_filter} confidence"

    st.html(
        '<div class="model-favorite top-looks">'
        '<div class="model-label">MODEL PERFORMANCE</div>'
        f'<div class="top-look-meta">{escape(filter_text)}</div>'
        '<div class="performance-results">'
        f'{"".join(result_cards)}'
        '</div>'
        '</div>'
    )


@st.cache_data(ttl=900)
def load_games(selected_date, model_cache_version, display_timezone):
    return get_today_games(selected_date.isoformat(), display_timezone)


def apply_model_view(games, model_view):
    if model_view != "Baseline 2.2.7":
        return games

    games = games.copy()
    baseline_column_map = {
        "First Inning Pick": "Baseline First Inning Pick",
        "First Inning Confidence": "Baseline First Inning Confidence",
        "First Inning Score": "Baseline First Inning Score",
        "F5 Pick": "Baseline F5 Pick",
        "F5 Confidence": "Baseline F5 Confidence",
        "F5 Score": "Baseline F5 Score",
        "Full Game Pick": "Baseline Full Game Pick",
        "Full Game Confidence": "Baseline Full Game Confidence",
        "Full Game Score": "Baseline Full Game Score",
        "Full Game Agreement": "Baseline Full Game Agreement",
        "Full Game Edge": "Baseline Full Game Edge",
        "Away Starter Edge": "Baseline Away Starter Edge",
        "Home Starter Edge": "Baseline Home Starter Edge",
        "Starter Edge Winner": "Baseline Starter Edge Winner",
        "Starter Edge Margin": "Baseline Starter Edge Margin",
        "Away Pitcher YRFI %": "Baseline Away Pitcher YRFI %",
        "Home Pitcher YRFI %": "Baseline Home Pitcher YRFI %",
        "Away 1st ERA": "Baseline Away 1st ERA",
        "Home 1st ERA": "Baseline Home 1st ERA",
        "Away 1st WHIP": "Baseline Away 1st WHIP",
        "Home 1st WHIP": "Baseline Home 1st WHIP",
    }

    for active_column, baseline_column in baseline_column_map.items():
        if baseline_column in games.columns:
            games[active_column] = games[baseline_column]

    games["Model View"] = model_view
    return games


st.title("⚾ First Five Edge")

display_timezone, timezone_detected = detect_browser_timezone()
default_slate_date = current_date_for_timezone(display_timezone)
max_slate_date = default_slate_date + timedelta(days=1)

st.sidebar.title("Controls")
st.sidebar.caption(f"Version {APP_VERSION}")
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
model_view = st.selectbox(
    "Model View",
    ["Proposed Model", "Baseline 2.2.7"],
    index=0,
    key="model_view_selector_v3",
)
timezone_label = "local" if timezone_detected else "Eastern fallback"
st.sidebar.caption(f"Times shown in {display_timezone} ({timezone_label})")
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
if model_view == "Proposed Model":
    record_model_history(games, selected_date, APP_VERSION)
games = apply_model_view(games, model_view)
st.caption(f"Model view: {model_view}")

top_look_game_names = top_look_games(games)
first_inning_pick_text = games["First Inning Pick"].fillna("").astype(str)
nrfi_mask = first_inning_pick_text.str.contains("NRFI", case=False, na=False)
yrfi_mask = first_inning_pick_text.str.contains("YRFI", case=False, na=False)
game_mask = ~games["Full Game Pick"].apply(is_no_edge_pick)
f5_mask = ~games["F5 Pick"].apply(is_no_edge_pick)
nrfi_count = int(nrfi_mask.sum())
yrfi_count = int(yrfi_mask.sum())
f5_count = int(f5_mask.sum())
game_count = int(game_mask.sum())
filter_labels = {
    "All Games": f"All\n{len(games)}",
    "Top Looks": f"Top\n{len(top_look_game_names)}",
    "NRFI": f"NRFI\n{nrfi_count}",
    "YRFI": f"YRFI\n{yrfi_count}",
    "F5": f"F5\n{f5_count}",
    "Game": f"Game\n{game_count}",
    "Performance": "Perf",
}

selected_filter_label = st.radio(
    "Game card filter",
    list(filter_labels.values()),
    horizontal=True,
    label_visibility="collapsed",
    key="game_card_filter",
)
selected_filter = {
    label: key
    for key, label in filter_labels.items()
}[selected_filter_label]

filtered = games.copy()

if selected_filter == "Top Looks":
    filtered = filtered[filtered["Game"].isin(top_look_game_names)]
elif selected_filter == "NRFI":
    filtered = filtered[nrfi_mask]
elif selected_filter == "YRFI":
    filtered = filtered[yrfi_mask]
elif selected_filter == "F5":
    filtered = filtered[f5_mask]
elif selected_filter == "Game":
    filtered = filtered[game_mask]

filtered = filtered.sort_values(
    ["Status Sort", "Game Sort Time"],
    ascending=[True, True],
    na_position="last",
)

if selected_filter == "Performance":
    performance_total = sum(
        row.get("total") or 0
        for row in load_performance_summary(APP_VERSION, exact_date=selected_date)
    )
    st.caption(f"{performance_total} results")
else:
    st.caption(f"{len(filtered)} of {len(games)}")

st.divider()

if selected_filter == "Performance":
    render_model_performance(APP_VERSION, selected_date)
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
        logo_matchup = render_logo_matchup(away_team, home_team)
        market_watch = render_market_watch(row)
        card_anchor = game_anchor(row["Game"])
        key_factors = render_key_factor_panels(row, away_team, home_team)
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
            first_inning_compact_result = get_row_value(row, "First Inning Result Compact", "")
            if first_inning_compact_result not in [None, "", "N/A", "Pending"]:
                first_inning_compact_result = f"Result: {first_inning_compact_result}"
            first_inning_result = render_decision_result(
                get_row_value(row, "First Inning Result", ""),
                first_inning_compact_result,
            )
            f5_result = render_decision_result(
                get_row_value(row, "F5 Result", ""),
                get_row_value(row, "F5 Result Compact", ""),
            )
            full_game_result = render_decision_result(
                get_row_value(row, "Full Game Result", ""),
                get_row_value(row, "Full Game Result Compact", ""),
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
            <div class="muted">{row["Game Time"]} • {row["Status"]}</div>

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
            render_signal_review(row, away_team, home_team)

            st.markdown("---")
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
            | 1st Inning R / ER | {get_row_value(row, "Away 1st R", "N/A")} / {get_row_value(row, "Away 1st ER", "N/A")} | {get_row_value(row, "Home 1st R", "N/A")} / {get_row_value(row, "Home 1st ER", "N/A")} |
            | 1st Inning H / BB / HR | {get_row_value(row, "Away 1st H", "N/A")} / {get_row_value(row, "Away 1st BB", "N/A")} / {get_row_value(row, "Away 1st HR", "N/A")} | {get_row_value(row, "Home 1st H", "N/A")} / {get_row_value(row, "Home 1st BB", "N/A")} / {get_row_value(row, "Home 1st HR", "N/A")} |
            """)
            if first_signal_active:
                st.caption("\\* - Edge Signal")

            st.markdown("#### Recent Pitching Form")
            st.markdown(f"""
            | Metric | {away_team} Starter | {home_team} Starter |
            |---|---|---|
            | Last 7 ERA / WHIP | {get_row_value(row, "Away Last 7 ERA", "N/A")} / {get_row_value(row, "Away Last 7 WHIP", "N/A")} | {get_row_value(row, "Home Last 7 ERA", "N/A")} / {get_row_value(row, "Home Last 7 WHIP", "N/A")} |
            | Last 7 K/BB / P-IP | {get_row_value(row, "Away Last 7 K/BB", "N/A")} / {get_row_value(row, "Away Last 7 P/IP", "N/A")} | {get_row_value(row, "Home Last 7 K/BB", "N/A")} / {get_row_value(row, "Home Last 7 P/IP", "N/A")} |
            | Last 15 ERA / WHIP | {get_row_value(row, "Away Last 15 ERA", "N/A")} / {get_row_value(row, "Away Last 15 WHIP", "N/A")} | {get_row_value(row, "Home Last 15 ERA", "N/A")} / {get_row_value(row, "Home Last 15 WHIP", "N/A")} |
            | Last 15 K/BB / P-IP | {get_row_value(row, "Away Last 15 K/BB", "N/A")} / {get_row_value(row, "Away Last 15 P/IP", "N/A")} | {get_row_value(row, "Home Last 15 K/BB", "N/A")} / {get_row_value(row, "Home Last 15 P/IP", "N/A")} |
            | Last 30 OPS Allowed | {get_row_value(row, "Away Last 30 OPS", "N/A")} | {get_row_value(row, "Home Last 30 OPS", "N/A")} |
            """)

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
