import streamlit as st
from mlb_agent import get_today_games

st.set_page_config(
    page_title="First Five Edge",
    layout="wide"
)

st.title("⚾ First Five Edge")
st.subheader("Daily MLB YRFI / NRFI + F5 Dashboard")


if st.button("Refresh MLB Data"):
    st.cache_data.clear()
    st.rerun()


@st.cache_data(ttl=900)
def load_games():
    return get_today_games()


games = load_games()

if games.empty:
    st.warning("No MLB games found for today.")
else:
    games_sorted = games.sort_values(
        "NRFI Score",
        ascending=False,
        na_position="last"
    )

    top_nrfi = games_sorted[
        games_sorted["Lean"].isin(["NRFI", "Strong NRFI"])
    ].head(1)

    top_yrfi = games_sorted[
        games_sorted["Lean"].isin(["YRFI", "Strong YRFI"])
    ].sort_values(
        "NRFI Score",
        ascending=True,
        na_position="last"
    ).head(1)

    top_f5 = games_sorted[
        games_sorted["F5 Edge"] != "F5 Pass"
    ].head(1)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Top NRFI",
            top_nrfi.iloc[0]["Game"] if not top_nrfi.empty else "None",
            top_nrfi.iloc[0]["Lean"] if not top_nrfi.empty else ""
        )

    with col2:
        st.metric(
            "Top YRFI",
            top_yrfi.iloc[0]["Game"] if not top_yrfi.empty else "None",
            top_yrfi.iloc[0]["Lean"] if not top_yrfi.empty else ""
        )

    with col3:
        st.metric(
            "Top F5 Edge",
            top_f5.iloc[0]["Game"] if not top_f5.empty else "None",
            top_f5.iloc[0]["F5 Edge"] if not top_f5.empty else ""
        )

    st.divider()

    st.subheader("Best Board")

    best_board = games[
        games["Recommendation"] != "Pass"
    ].copy()

    best_board = best_board.sort_values(
        "NRFI Score",
        ascending=False,
        na_position="last"
    )

    if best_board.empty:
        st.info("No strong recommendations today.")
    else:
        for _, row in best_board.head(5).iterrows():
            st.markdown(
                f"""
                **{row["Game Time"]} | {row["Game"]}**  
                Recommendation: **{row["Recommendation"]}**  
                NRFI Score: **{row["NRFI Score"]}**  
                Notes: {row["Agent Notes"]}
                """
            )
            st.divider()

    filter_choice = st.radio(
        "View",
        [
            "All Games",
            "NRFI Only",
            "YRFI Looks",
            "F5 Edges",
            "High Bullpen Fatigue",
        ],
        horizontal=True
    )

    filtered_games = games.copy()

    if filter_choice == "NRFI Only":
        filtered_games = filtered_games[
            filtered_games["Lean"].isin(["NRFI", "Strong NRFI"])
        ]

    elif filter_choice == "YRFI Looks":
        filtered_games = filtered_games[
            filtered_games["Lean"].isin(["YRFI", "Strong YRFI"])
        ]

    elif filter_choice == "F5 Edges":
        filtered_games = filtered_games[
            filtered_games["F5 Edge"] != "F5 Pass"
        ]

    elif filter_choice == "High Bullpen Fatigue":
        filtered_games = filtered_games[
            (filtered_games["Away Bullpen Fatigue"] >= 7) |
            (filtered_games["Home Bullpen Fatigue"] >= 7)
        ]

    display_columns = [
        "Game Time",
        "Game",
        "Recommendation",
        "NRFI Score",
        "Lean",
        "F5 Edge",
        "Away Pitcher",
        "Home Pitcher",
        "Away ERA",
        "Home ERA",
        "Away WHIP",
        "Home WHIP",
        "Away Offense",
        "Home Offense",
        "Away Bullpen Fatigue",
        "Home Bullpen Fatigue",
        "Agent Notes",
        "Status",
    ]

    filtered_games = filtered_games[display_columns]

    filtered_games = filtered_games.sort_values(
        "NRFI Score",
        ascending=False,
        na_position="last"
    )

    csv = filtered_games.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download Today's MLB Report",
        data=csv,
        file_name="first_five_edge_report.csv",
        mime="text/csv"
    )

    st.dataframe(
        filtered_games,
        use_container_width=True,
        hide_index=True
    )