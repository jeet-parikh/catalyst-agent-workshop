"""Run with: streamlit run app.py"""

import os

import streamlit as st
from dotenv import load_dotenv

from agent import run_agent

load_dotenv()
st.set_page_config(page_title="Movie Night Planner", page_icon="🎬", layout="wide")
st.title("🎬 Movie Night Planner")
st.caption("y/cs · One model, two tools, a small agent loop")

with st.sidebar:
    version = st.radio("Version", ["V1 · Agent with tools", "V0 · LLM only"])
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.messages = []
    st.caption("This product uses the TMDB API but is not endorsed or certified by TMDB.")

if st.session_state.get("version") != version:
    st.session_state.messages = []
    st.session_state.version = version

if version.startswith("V0"):
    st.info("V0 has no tools: movie suggestions are unverified.")

answer_panel, trace_panel = st.columns([3, 2])
with trace_panel:
    st.subheader("Tool calls")
    st.caption("Observable calls and results, not private model reasoning.")
    trace = st.container()


def show_call(name, args, result):
    with trace.expander(name, expanded=True):
        st.json({"arguments": args, "result": result})


with answer_panel:
    st.subheader("Movie night")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    prompt = st.chat_input("e.g. Funny or mysterious, under two hours, no horror")
    if prompt:
        with st.chat_message("user"):
            st.markdown(prompt)
        if not os.getenv("OPENAI_API_KEY"):
            st.error("Add OPENAI_API_KEY to .env.")
        else:
            messages = st.session_state.messages + [{"role": "user", "content": prompt}]
            with st.spinner("Finding a movie…"):
                answer = run_agent(messages, version.startswith("V1"), show_call)
            st.session_state.messages = messages + [{"role": "assistant", "content": answer}]
            with st.chat_message("assistant"):
                st.markdown(answer)
