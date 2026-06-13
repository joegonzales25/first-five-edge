import streamlit as st
from datetime import date
from html import escape
import re
from mlb_agent import get_today_games

APP_VERSION = "2.2.5"
MODEL_CACHE_VERSION = "edge-confidence-v2"

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
    min-height: 72px;
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

div[data-testid="stRadio"] [role="radiogroup"] {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
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
        grid-template-columns: repeat(5, minmax(48px, 1fr));
        gap: 6px;
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


def get_badge_class(row):
    if row["Lean"] in ["Strong NRFI", "NRFI"]:
        return "badge-nrfi"
    if row["Lean"] in ["Strong YRFI", "YRFI"]:
        return "badge-yrfi"
    if row["F5 Edge"] != "F5 Pass":
        return "badge-f5"
    return "badge-pass"


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


def build_reason_stack(row):
    reasons = [
        note.strip()
        for note in str(row["Agent Notes"]).split(";")
        if note.strip()
    ]

    if not reasons:
        reasons = ["Neutral model profile"]

    lean = row["Lean"]
    if lean == "Pass":
        reasons.append("Model lean remains in pass range")
    elif lean != "Pending":
        reasons.append(f"{lean} threshold cleared")

    if row["F5 Edge"] != "F5 Pass":
        reasons.append(row["F5 Edge"])

    bullpen_status = f'{row["Away Bullpen Status"]} / {row["Home Bullpen Status"]}'
    if bullpen_status != "Normal / Normal":
        reasons.append(f"Bullpen watch: {bullpen_status}")

    reasons.append(f'Confidence {row["Confidence"]}')

    return reasons[:5]


def render_reason_stack(row):
    items = "".join(
        f"""
        <div class="reason-item">
            <span class="reason-check">&#10003;</span>
            <span>{escape(reason)}</span>
        </div>
        """
        for reason in build_reason_stack(row)
    )

    return f'<div class="reason-stack">{items}</div>'


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


def get_numeric_value(row, column_name):
    value = get_row_value(row, column_name, "")
    try:
        return float(str(value).replace("%", "").strip())
    except ValueError:
        return None


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


def build_key_factors(row, view="first", away_team=None, home_team=None):
    factors = []

    if view == "first":
        pick = get_row_value(row, "First Inning Pick", "Pass")
        confidence = get_row_value(row, "First Inning Confidence", "Pass")
        if is_no_edge_pick(pick):
            factors.append("No clear first-inning edge")

        notes = [
            note.strip()
            for note in str(get_row_value(row, "Agent Notes", "")).split(";")
            if note.strip()
        ]
        factors.extend(notes[:2])

    elif view == "f5":
        pick = get_row_value(row, "F5 Pick", "Pass")
        confidence = get_row_value(row, "F5 Confidence", "Pass")
        if is_no_edge_pick(pick):
            factors.append("No qualified First 5 edge")

        factors.append(format_edge_factor(
            row,
            "Starter Edge Winner",
            "Starter Edge Margin",
            "Starter edge",
            away_team,
            home_team,
        ))
        factors.append(format_edge_factor(
            row,
            "Offensive Edge Winner",
            "Offensive Edge Margin",
            "Offensive edge",
            away_team,
            home_team,
        ))

    elif view == "full":
        pick = get_row_value(row, "Full Game Pick", "Pass")
        confidence = get_row_value(row, "Full Game Confidence", "Pass")
        if is_no_edge_pick(pick):
            factors.append("No qualified full-game edge")

        factors.append(format_edge_factor(
            row,
            "Starter Edge Winner",
            "Starter Edge Margin",
            "Starter edge",
            away_team,
            home_team,
        ))
        factors.append(format_edge_factor(
            row,
            "Offensive Edge Winner",
            "Offensive Edge Margin",
            "Offensive edge",
            away_team,
            home_team,
        ))
        factors.append(format_edge_factor(
            row,
            "Bullpen Edge Winner",
            "Bullpen Edge Margin",
            "Bullpen edge",
            away_team,
            home_team,
        ))

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


def best_row(rows, confidence_column):
    if rows.empty:
        return None

    ranked = rows.copy()
    ranked["_confidence_rank"] = ranked[confidence_column].map(confidence_sort_value)
    ranked = ranked.sort_values(
        ["_confidence_rank", "Edge Score"],
        ascending=False,
        na_position="last",
    )
    return ranked.iloc[0]


def build_top_looks(games):
    looks = []

    first_rows = games[
        ~games["First Inning Pick"].apply(is_no_edge_pick)
    ].copy()
    first_row = best_row(first_rows, "First Inning Confidence")
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
            "meta": f'Edge {first_row["Edge Score"]} • Confidence {first_row["First Inning Confidence"]}',
            "why": str(first_row["Agent Notes"]).split(";")[0],
            "link": top_look_link(first_row),
            "game": first_row["Game"],
        })

    f5_rows = games[
        ~games["F5 Pick"].apply(is_no_edge_pick)
    ].copy()
    f5_row = best_row(f5_rows, "F5 Confidence")
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
        f5_pick = replace_home_away(f5_row["F5 Pick"], away_team, home_team)
        looks.append({
            "title": f'First 5 {f5_pick}: {game_matchup_label(f5_row["Game"])} ({f5_row["F5 Confidence"]})',
            "meta": f'Edge {f5_row["Edge Score"]} • Confidence {f5_row["F5 Confidence"]}',
            "why": str(f5_row["Agent Notes"]).split(";")[0],
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
            ["_fatigue_max", "Edge Score"],
            ascending=False,
            na_position="last",
        ).iloc[0]
        away_team, home_team = split_game_name(bullpen_row["Game"])
        looks.append({
            "title": f'Bullpen Watch: {game_matchup_label(bullpen_row["Game"])}',
            "meta": f'Edge {bullpen_row["Edge Score"]} • Confidence {bullpen_row["Confidence"]}',
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


@st.cache_data(ttl=900)
def load_games(selected_date, model_cache_version):
    return get_today_games(selected_date.isoformat())


st.title("⚾ First Five Edge")

st.sidebar.title("Controls")
st.sidebar.caption(f"Version {APP_VERSION}")
selected_date = st.date_input(
    "Slate Date",
    value=date.today(),
    format="MM/DD/YYYY",
    key="header_slate_date",
)
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

games = load_games(selected_date, MODEL_CACHE_VERSION)

if games.empty:
    st.warning("No MLB games found for selected date.")
    st.stop()

games = games.copy()
games["Edge Score"] = games["Edge Score"].fillna(0)

top_look_game_names = top_look_games(games)
nrfi_count = len(games[games["Lean"].isin(["NRFI", "Strong NRFI"])])
yrfi_count = len(games[games["Lean"].isin(["YRFI", "Strong YRFI"])])
f5_count = len(games[games["F5 Edge"] != "F5 Pass"])
filter_labels = {
    "All Games": f"All\n{len(games)}",
    "Top Looks": f"Top\n{len(top_look_game_names)}",
    "NRFI": f"NRFI\n{nrfi_count}",
    "YRFI": f"YRFI\n{yrfi_count}",
    "F5": f"F5\n{f5_count}",
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
    filtered = filtered[filtered["Lean"].isin(["NRFI", "Strong NRFI"])]
elif selected_filter == "YRFI":
    filtered = filtered[filtered["Lean"].isin(["YRFI", "Strong YRFI"])]
elif selected_filter == "F5":
    filtered = filtered[filtered["F5 Edge"] != "F5 Pass"]

filtered = filtered.sort_values(
    ["Status Sort", "Game Sort Time"],
    ascending=[True, True],
    na_position="last",
)

st.divider()

if selected_filter in ["All Games", "Top Looks"]:
    st.html(render_top_looks(games))

model_favorites = games[games["Recommendation"] != "Pass"].sort_values(
    "Edge Score",
    ascending=False,
    na_position="last"
)

if False and not model_favorites.empty:
    top = model_favorites.iloc[0]

    st.html(f"""
    <div class="model-favorite">
        <div class="model-label">MODEL FAVORITE</div>
        <div class="model-pick">{top["Recommendation"]}</div>
        <h2>{top["Game"]}</h2>
        <p>{top["Game Time"]} • {top["Status"]}</p>
        <span class="badge badge-edge">Edge {top["Edge Score"]}</span>
        <span class="badge badge-edge">Confidence {top["Confidence"]}</span>
        <span class="badge badge-edge">{top["Lean"]}</span>
        <p style="margin-top: 14px;">{top["Agent Notes"]}</p>
    </div>
    """)

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
        away_pitcher_yrfi_display = format_rank_metric(
            row,
            "Away Pitcher YRFI %",
            [
                "Away Pitcher YRFI Rank",
                "Away Pitcher YRFI % Rank",
                "Away Pitcher YRFI SP Rank",
                "Away Pitcher YRFI % SP Rank",
            ],
            "SP",
        )
        home_pitcher_yrfi_display = format_rank_metric(
            row,
            "Home Pitcher YRFI %",
            [
                "Home Pitcher YRFI Rank",
                "Home Pitcher YRFI % Rank",
                "Home Pitcher YRFI SP Rank",
                "Home Pitcher YRFI % SP Rank",
            ],
            "SP",
        )
        away_offense_yrfi_display = format_rank_metric(
            row,
            "Away Offense YRFI %",
            [
                "Away Offense YRFI Rank",
                "Away Offense YRFI % Rank",
                "Away Offense YRFI MLB Rank",
                "Away Offense YRFI % MLB Rank",
            ],
            "MLB",
        )
        home_offense_yrfi_display = format_rank_metric(
            row,
            "Home Offense YRFI %",
            [
                "Home Offense YRFI Rank",
                "Home Offense YRFI % Rank",
                "Home Offense YRFI MLB Rank",
                "Home Offense YRFI % MLB Rank",
            ],
            "MLB",
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
                <label class="decision-line decision-first" for="{card_anchor}-first">🎯 1st Inning: {first_inning_display}</label>
                <label class="decision-line decision-f5" for="{card_anchor}-f5">⚾ First 5: {f5_display}</label>
                <label class="decision-line decision-full" for="{card_anchor}-full">🏆 Full Game: {full_game_display}</label>
            </div>

            {key_factors}

            {market_watch}
        </div>
        """)

        with st.expander(f"🔍 Analysis: {row['Game']}"):
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
            | IP | {row["Away IP"]} | {row["Home IP"]} |
            | K | {row["Away K"]} | {row["Home K"]} |
            | ERA | {row["Away ERA"]} | {row["Home ERA"]} |
            | WHIP | {row["Away WHIP"]} | {row["Home WHIP"]} |
            | Pitcher YRFI % | {away_pitcher_yrfi_display} | {home_pitcher_yrfi_display} |
            """)

            st.markdown("---")
            st.markdown("### Offensive Matchup")
            st.markdown(f"""
            | Metric | {away_team} | {home_team} |
            |---|---|---|
            | Record | {row["Away Record"]} | {row["Home Record"]} |
            | Runs Per Game | {get_row_value(row, "Away Runs Per Game", "N/A")} | {get_row_value(row, "Home Runs Per Game", "N/A")} |
            | Offense YRFI % | {away_offense_yrfi_display} | {home_offense_yrfi_display} |
            | First-Inning Run Avg | {get_row_value(row, "Away 1st Run Avg", "N/A")} | {get_row_value(row, "Home 1st Run Avg", "N/A")} |
            """)

            st.markdown("---")
            st.markdown("### Bullpen Usage")
            st.markdown(f"""
            | Metric | {away_team} Bullpen | {home_team} Bullpen |
            |---|---|---|
            | Rating | {row["Away Bullpen Status"]} | {row["Home Bullpen Status"]} |
            | Fatigue Score | {row["Away Bullpen Fatigue"]} | {row["Home Bullpen Fatigue"]} |
            | 3-Day Bullpen IP | {row["Away 3 Day Bullpen IP"]} | {row["Home 3 Day Bullpen IP"]} |
            | 3-Day Bullpen Pitches | {row["Away 3 Day Bullpen Pitches"]} | {row["Home 3 Day Bullpen Pitches"]} |
            | 3-Day Relievers Used | {row["Away 3 Day Relievers"]} | {row["Home 3 Day Relievers"]} |
            | Back-to-Back Arms | {row["Away Back-to-Back Arms"]} | {row["Home Back-to-Back Arms"]} |
            """)

st.divider()

csv = filtered.to_csv(index=False).encode("utf-8")

st.download_button(
    label="Download MLB Report",
    data=csv,
    file_name=f"first_five_edge_report_{selected_date}.csv",
    mime="text/csv"
)
