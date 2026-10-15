# Repo Investigator

A read-only multi-agent system for Workshop 2. Give it a public GitHub repository and a question. It routes the request, splits it into parallel investigations, checks every citation in plain code and answers from verified findings only. It never writes, runs code or opens pull requests.

```sh
streamlit run investigator/demo.py
```

Uses the same `.env` as the movie agent. `OPENAI_API_KEY` is required. `GITHUB_TOKEN` is optional and only raises GitHub's rate limit. `INVESTIGATOR_MODEL` overrides the default model.

## What happens in one run

```text
request → route → coordinator → worker A ┐
                              → worker B ├→ citation check → answer
                              → worker C ┘        │
                                   ↑   retry once ┘
```

| Stage | Pattern | Where |
| --- | --- | --- |
| Route: investigate, review or out of scope | Routing | `Investigation.route` |
| Coordinator writes 2–4 assignments from the file list | Orchestrator–workers | `Investigation.plan` |
| Workers run at the same time, each in its own context | Parallelization | `Investigation.investigate` |
| A worker cannot read outside its scope | Application controls | `Investigation.run_tool` |
| Budget reached → submission is forced | Bounded run | `Investigation.loop` |
| File, line and quote are checked by code, not a model | Evaluator–optimizer | `repo.check_citation` |
| The answer sees only verified findings | Evidence state | `Investigation.write_answer` |

Switch to **Single agent (baseline)** in the sidebar to send the same request to one agent with the same tools. Run both modes once and a comparison table appears.

## Limits worth saying out loud

- The check proves a cited line exists and says what the worker quoted. It does not prove the claim about that line is right.
- Workers can miss things. A missed file is a coverage gap, not a failed check.
- One run per mode is an anecdote. Compare several requests before claiming one architecture is better.

## Offline backup

Every live run is saved in `investigator/runs/`. **Replay recording** plays a saved run back with no network, so Wi-Fi trouble does not end the demo. The recording is a real run, not mock data.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests fake the model and GitHub, so they make no API calls.
