import streamlit as st
from nba_api.live.nba.endpoints import scoreboard, playbyplay
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import re
import time
from nba_api.stats.endpoints import scoreboardv2, winprobabilitypbp, boxscoretraditionalv2
import plotly.graph_objects as go
import datetime
import logging
import os
import base64

# Set up logging
logging.basicConfig(level=logging.INFO)

# Path to logos
LOGO_PATH = r"YOUR PATH TO LOGOS"

TEAM_LOGOS = {
    "Atlanta Hawks": "atlantahawks.png",
    "Boston Celtics": "bostonceltics.png",
    "Brooklyn Nets": "brooklynnets.png",
    "Charlotte Hornets": "charlottehornets.png",
    "Chicago Bulls": "chicagobulls.png",
    "Cleveland Cavaliers": "clevelandcavaliers.png",
    "Dallas Mavericks": "dallasmavericks.png",
    "Denver Nuggets": "denvernuggets.png",
    "Detroit Pistons": "detroitpistons.png",
    "Golden State Warriors": "goldenstatewarriors.png",
    "Houston Rockets": "houstonrockets.png",
    "Indiana Pacers": "indianapacers.png",
    "Los Angeles Clippers": "losangelesclippers.png",
    "Los Angeles Lakers": "losangeleslakers.png",
    "Memphis Grizzlies": "memphisgrizzlies.png",
    "Miami Heat": "miamiheat.png",
    "Milwaukee Bucks": "milwaukeebucks.png",
    "New Orleans Pelicans": "neworleanspelicans.png",
    "New York Knicks": "newyorkknicks.png",
    "Oklahoma City Thunder": "oklahomacitythunder.png",
    "Orlando Magic": "orlandomagic.png",
    "Philadelphia 76ers": "philadelphia76ers.png",
    "Phoenix Suns": "phoenixsuns.png",
    "Portland Trail Blazers": "portlandtrailblazers.png",
    "Sacramento Kings": "sacramentokings.png",
    "San Antonio Spurs": "sanantoniospurs.png",
    "Toronto Raptors": "torontoraptors.png",
    "Washington Wizards": "washingtonwizards.png",
    "Utah Jazz": "utahjazz.png",
    "Minnesota Timberwolves": "minnesotatimberwolves.png",
}

def base64_encode_image(image_path):
    """Encodes the image at the given path into a Base64 string."""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except FileNotFoundError:
        logging.error(f"Logo file not found: {image_path}")
        return ""  # Return an empty string if the file doesn't exist


def get_full_team_name(team_name):
    """
    Normalizes the team name to match the keys in TEAM_LOGOS.
    Falls back to the original team name if no match is found.
    """
    for full_name in TEAM_LOGOS.keys():
        if team_name in full_name:  # Match partial names like "Nuggets" to "Denver Nuggets"
            return full_name
    logging.warning(f"Team name '{team_name}' not found in TEAM_LOGOS. Using fallback.")
    return team_name  # Fallback to the original name


@st.cache_data(ttl=60)
def fetch_win_probability(game_id):
    try:
        win_prob_data = winprobabilitypbp.WinProbabilityPBP(game_id=game_id, run_type='each second')
        return pd.DataFrame(win_prob_data.win_prob_p_bp.get_dict()['data'], columns=[
            'GAME_ID', 'EVENT_NUM', 'HOME_PCT', 'VISITOR_PCT', 'HOME_PTS', 'VISITOR_PTS',
            'HOME_SCORE_MARGIN', 'PERIOD', 'SECONDS_REMAINING', 'HOME_POSS_IND',
            'HOME_G', 'DESCRIPTION', 'LOCATION', 'PCTIMESTRING', 'ISVISIBLE'
        ])
    except Exception as e:
        logging.error(f"Error fetching win probability data: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60)
def get_player_stats(game_id):
    try:
        box_score = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        return box_score.player_stats.get_data_frame()
    except Exception as e:
        logging.error(f"Error fetching player statistics: {e}")
        return pd.DataFrame()


def calculate_total_seconds(row):
    return (row['PERIOD'] - 1) * 720 + (720 - row['SECONDS_REMAINING'])


def format_time(clock):
    if clock.startswith("PT"):
        try:
            match = re.match(r"PT(\d+)M([\d.]+)S", clock)
            if match:
                minutes, seconds = match.groups()
                return f"{int(minutes)}:{float(seconds):04.1f}"
        except ValueError:
            return clock
    return clock


def app():
    st.title("NBA Live Play-by-Play")

    try:
        scoreboard_data = scoreboard.ScoreBoard().get_dict()
    except Exception as e:
        logging.error(f"Error fetching scoreboard data: {e}")
        return

    if 'scoreboard' not in scoreboard_data or 'games' not in scoreboard_data['scoreboard']:
        logging.error("No games data available.")
        return

    games = scoreboard_data['scoreboard']['games']

    if not games:
        logging.info("No games scheduled for today.")
        return

    # Generate game options
    game_options = [f"{game['awayTeam']['teamName']} vs {game['homeTeam']['teamName']}" for game in games]

    if 'selected_game1' not in st.session_state:
        st.session_state.selected_game1 = game_options[0]
    if 'selected_game2' not in st.session_state:
        st.session_state.selected_game2 = game_options[1] if len(game_options) > 1 else game_options[0]

    col1, col2 = st.columns(2)

    with col1:
        selected_game1 = st.selectbox(
            "Game 1:",
            game_options,
            index=game_options.index(st.session_state.selected_game1),
            key="game1_selector",
        )
        st.session_state.selected_game1 = selected_game1
    with col2:
        selected_game2 = st.selectbox(
            "Game 2:",
            game_options,
            index=game_options.index(st.session_state.selected_game2),
            key="game2_selector",
        )
        st.session_state.selected_game2 = selected_game2

    try:
        game_index1 = game_options.index(st.session_state.selected_game1)
        game_id1 = games[game_index1]['gameId']

        game_index2 = game_options.index(st.session_state.selected_game2)
        game_id2 = games[game_index2]['gameId']
    except ValueError:
        logging.error("Selected game not found. Please refresh the page.")
        st.stop()

    def display_game_info(game_id, game, col):
        with col:
            # Normalize team names
            away_team_full_name = get_full_team_name(game['awayTeam']['teamName'])
            home_team_full_name = get_full_team_name(game['homeTeam']['teamName'])

            # Get logos or fallback
            away_logo = os.path.join(LOGO_PATH, TEAM_LOGOS.get(away_team_full_name, "default_logo.png"))
            home_logo = os.path.join(LOGO_PATH, TEAM_LOGOS.get(home_team_full_name, "default_logo.png"))

            st.markdown(
                f"""
                <div style="display: flex; align-items: center; gap: 10px;">
                    <img src="data:image/png;base64,{base64_encode_image(away_logo)}" style="width:80px;"> 
                    <strong>{game['awayTeam']['teamName']} {game['awayTeam']['score']}</strong>
                    <span>vs</span>
                    <strong>{game['homeTeam']['score']} {game['homeTeam']['teamName']}</strong>
                    <img src="data:image/png;base64,{base64_encode_image(home_logo)}" style="width:80px;">
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Other game info
            st.write(f"**Status:** {game['gameStatusText']}")
            st.write(f"**Timeouts Remaining:** Home - {game['homeTeam'].get('timeoutsRemaining', 'N/A')}, Away - {game['awayTeam'].get('timeoutsRemaining', 'N/A')}")
            st.write(f"**Team Fouls:** Home - {game['homeTeam'].get('teamFouls', 'N/A')}, Away - {game['awayTeam'].get('teamFouls', 'N/A')}")

            if game['gameStatus'] < 2:
                st.info("Play-by-play data will be available once the game starts.")
                return

            try:
                pbp = playbyplay.PlayByPlay(game_id).get_dict()
            except Exception as e:
                logging.error(f"Error fetching play-by-play data: {e}")
                return

            if 'game' in pbp and 'actions' in pbp['game']:
                actions = pbp['game']['actions'][-20:][::-1]

                data = [
                    {
                        "Period": action.get('period', 'N/A'),
                        "Time Remaining": format_time(action.get('clock', 'N/A')),
                        "Team": action.get('teamTricode', 'N/A'),
                        "Action": action.get('description', 'No description'),
                    }
                    for action in actions
                ]
                df = pd.DataFrame(data)

                st.subheader("Play-by-Play Data")
                st.dataframe(df)

    display_game_info(game_id1, games[game_index1], col1)
    display_game_info(game_id2, games[game_index2], col2)

    st.subheader("Win Probability")
    for idx, (game_id, game) in enumerate([(game_id1, games[game_index1]), (game_id2, games[game_index2])], start=1):
        st.write(f"**Game {idx}:** {game['awayTeam']['teamName']} vs {game['homeTeam']['teamName']}")
        win_prob_pbp = fetch_win_probability(game_id)

        if not win_prob_pbp.empty:
            win_prob_pbp['TOTAL_SECONDS'] = win_prob_pbp.apply(calculate_total_seconds, axis=1)

            fig = go.Figure()

            fig.add_trace(go.Scatter(
                x=win_prob_pbp['TOTAL_SECONDS'], y=win_prob_pbp['HOME_PCT'],
                mode='lines', name=f"{game['homeTeam']['teamName']} Win Probability",
                line=dict(color='green', width=3)
            ))

            fig.add_trace(go.Scatter(
                x=win_prob_pbp['TOTAL_SECONDS'], y=win_prob_pbp['VISITOR_PCT'],
                mode='lines', name=f"{game['awayTeam']['teamName']} Win Probability",
                line=dict(color='red', width=3)
            ))

            fig.update_layout(
                title=f"Win Probability: {game['homeTeam']['teamName']} vs {game['awayTeam']['teamName']}",
                xaxis_title="Game Time (Seconds)",
                yaxis_title="Win Probability (%)",
            )

            st.plotly_chart(fig)
        else:
            st.warning("Win Probability data not available for this game.")

    st.caption(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    REFRESH_INTERVAL = 10
    st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="autorefresh")


if __name__ == "__main__":
    app()
