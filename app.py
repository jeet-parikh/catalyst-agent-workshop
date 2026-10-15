"""Run with: streamlit run app.py"""

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
st.set_page_config(page_title="Catalyst Agent Workshop", page_icon="🤖", layout="wide")

st.navigation({
    "Workshop 1": [st.Page("movie_agent/page.py", title="Movie Night Planner", icon="🎬")],
    "Workshop 2": [st.Page("repo_investigator/page.py", title="Repo Investigator", icon="🔎", url_path="investigator")],
}).run()
