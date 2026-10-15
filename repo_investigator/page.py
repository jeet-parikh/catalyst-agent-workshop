"""Workshop 2 page. Open it from app.py."""

import json
import os
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from repo_investigator.agents import MODEL, Investigation
from repo_investigator.repo import Repo

RUNS = Path(__file__).parent / "runs"
DIAGRAM = Path(__file__).parent / "architecture.png"
MODES = {"Multi-agent": "multi", "Single agent (baseline)": "single"}

st.title("🔎 Repo Investigator")
st.caption("y/cs · Read-only agents: route, delegate, check the evidence, answer")


@st.dialog("How the Repo Investigator works", width="large")
def show_diagram():
    st.image(str(DIAGRAM))


if st.button("Show agent diagram", icon=":material/account_tree:"):
    show_diagram()


@st.cache_resource(show_spinner=False, ttl=3600)
def load_repo(text):
    return Repo.from_github(text)


def describe(event):
    args = event["args"]
    if event["name"] == "read_file":
        end = args["end_line"] or "end"
        return f"`read_file` {args['path']} {args['start_line']}–{end}"
    if event["name"] == "search_code":
        return f"`search_code` \"{args['text']}\" in /{args['prefix']}"
    return f"`list_files` /{args.get('prefix', '')}"


def show_results(check):
    if check["retry"]:
        st.markdown("↻ *Resubmitted after the check*")
    for r in check["results"]:
        if r["ok"]:
            st.markdown(f"✅ [{r['path']}:{r['line']}]({r['link']}) {r['claim']}")
        else:
            st.markdown(f"❌ `{r['path']}:{r['line']}` {r['claim']}  \n:red[{r['reason']}]")


def render(events):
    of = lambda kind: [e for e in events if e["type"] == kind]
    for e in of("error"):
        if e.get("worker") is None:
            st.error(e["message"])
    if of("route"):
        route = of("route")[0]
        st.markdown("##### 1 · Route")
        st.info(f"**{route['route']}** · {route['reason']}")
    if of("plan"):
        plan = of("plan")[0]
        baseline = plan.get("baseline")
        st.markdown("##### 2 · " + ("One agent, whole repository" if baseline else "Coordinator assigns workers, run in parallel"))
        assignments = plan["assignments"]
        for column, a in zip(st.columns(len(assignments)), assignments):
            with column, st.container(border=True):
                st.markdown(f"**{a['id']} · {a['name']}**")
                scope = ", ".join(f"/{s}" for s in a["scope"]) or "/"
                st.caption(f"{a['objective']}  \nScope: {scope} · Budget: {a['budget']} tool calls")
                for e in events:
                    if e.get("worker") != a["id"]:
                        continue
                    if e["type"] == "tool":
                        st.markdown(describe(e) + (f"  \n:orange[⛔ {e['error']}]" if e["error"] else ""))
                    elif e["type"] == "check":
                        show_results(e)
                    elif e["type"] == "error":
                        st.error(e["message"])
    if of("answer"):
        answer = of("answer")[0]
        st.markdown("##### 3 · Answer from verified findings only")
        with st.container(border=True):
            st.markdown(answer["text"])
            if answer["sources"]:
                st.caption("  \n".join(f"[{s['id']}] [{s['path']}:{s['line']}]({s['link']}) {s['claim']}"
                                       for s in answer["sources"]))
    if of("stats"):
        s = of("stats")[0]
        columns = st.columns(5)
        columns[0].metric("Elapsed", f"{s['seconds']} s")
        columns[1].metric("Model calls", s["model_calls"])
        columns[2].metric("Tool calls", s["tool_calls"])
        columns[3].metric("Tokens", f"{s['input_tokens'] + s['output_tokens']:,}")
        columns[4].metric("Verified citations", s["verified"], f"{s['rejected']} rejected", delta_color="off")


def run_live(repo, question, mode):
    events, inbox = [], queue.Queue()

    def work():
        try:
            Investigation(repo, question, emit=inbox.put).run(mode)
        except Exception as error:
            inbox.put({"type": "error", "worker": None, "message": str(error)})

    # Workers run on background threads; only this thread draws the page.
    thread = threading.Thread(target=work)
    thread.start()
    area = st.empty()
    while thread.is_alive() or not inbox.empty():
        fresh = False
        while not inbox.empty():
            events.append(inbox.get())
            fresh = True
        if fresh:
            with area.container():
                render(events)
        time.sleep(0.25)
    return events


def save(record):
    RUNS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = RUNS / f"{stamp}-{record['repo'].replace('/', '_')}-{record['mode']}.json"
    path.write_text(json.dumps(record, indent=1))


def remember(record):
    st.session_state.last = record
    stats = next((e for e in record["events"] if e["type"] == "stats"), None)
    if stats:
        key = (record["repo"], record["question"])
        st.session_state.setdefault("compare", {}).setdefault(key, {})[record["mode"]] = stats


with st.sidebar:
    mode_label = st.radio("Architecture", list(MODES))
    st.caption(f"Model: {MODEL}. Tools: list_files, read_file, search_code. Nothing can write.")
    st.divider()
    saved = sorted(RUNS.glob("*.json"), reverse=True) if RUNS.exists() else []
    st.markdown("**Recorded runs**")
    chosen = st.selectbox("Recording", saved, format_func=lambda p: p.stem, label_visibility="collapsed")
    replay = st.button("Replay recording", disabled=not saved, use_container_width=True)
    st.caption("Every live run is saved here, so you can replay a real run without network access.")

repo_text = st.text_input("Public GitHub repository", "jeet-parikh/catalyst-agent-workshop")
question = st.text_area("Question or request", height=80, value=(
    "How do I add a watched-movie argument to search_movies so the agent skips titles we've already seen?"))
start = st.button("Investigate", type="primary")

if start:
    if not os.getenv("OPENAI_API_KEY"):
        st.error("Add OPENAI_API_KEY to .env.")
        st.stop()
    try:
        with st.spinner(f"Loading {repo_text} from GitHub…"):
            repo = load_repo(repo_text)
    except Exception as error:
        st.error(f"Could not load the repository: {error}")
        st.stop()
    st.caption(f"Loaded {len(repo.files)} text files at [{repo.sha}](https://github.com/{repo.owner}/{repo.name}/tree/{repo.sha})")
    mode = MODES[mode_label]
    events = run_live(repo, question, mode)
    record = {"repo": f"{repo.owner}/{repo.name}", "sha": repo.sha, "question": question, "mode": mode, "events": events}
    save(record)
    remember(record)
elif replay and chosen:
    record = json.loads(chosen.read_text())
    st.caption(f"Replaying a recorded {record['mode']} run on {record['repo']} @ {record['sha']}: {record['question']}")
    area = st.empty()
    for n in range(1, len(record["events"]) + 1):
        with area.container():
            render(record["events"][:n])
        time.sleep(0.15 if record["events"][n - 1]["type"] == "tool" else 0.6)
    remember(record)
elif "last" in st.session_state:
    render(st.session_state.last["events"])

last = st.session_state.get("last")
runs = st.session_state.get("compare", {}).get((last["repo"], last["question"]), {}) if last else {}
if len(runs) == 2:
    st.markdown("##### Same request, both architectures")
    rows = {"Elapsed (s)": "seconds", "Model calls": "model_calls", "Tool calls": "tool_calls",
            "Input tokens": "input_tokens", "Output tokens": "output_tokens",
            "Verified citations": "verified", "Rejected citations": "rejected"}
    st.table({"Metric": list(rows), "Multi-agent": [f"{runs['multi'][k]:,}" for k in rows.values()],
              "Single agent": [f"{runs['single'][k]:,}" for k in rows.values()]})
    st.caption("One run each. Repeat on several requests before drawing conclusions.")
