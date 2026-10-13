# Movie Night Planner

A movie agent you can read and run. **V0** is one model call with no tools. **V1** is the same model with two tools: search movies, then look one up.

Python, Streamlit, and the OpenAI Responses API. No agent framework.

## Setup

Python 3.10 or newer.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add your keys to `.env`. Do not commit that file.

- `OPENAI_API_KEY` — from your OpenAI account. Calls are billed there.
- `TMDB_READ_TOKEN` — the long **API Read Access Token** from [TMDB API settings](https://www.themoviedb.org/settings/api), not the shorter API key.

```sh
streamlit run app.py
```

Open the local URL Streamlit prints. Pick V0 or V1 in the sidebar. Switching versions clears the chat.

## The code

| File | What it does |
| --- | --- |
| `app.py` | Chat and the tool-call trace |
| `agent.py` | Instructions, the V0 request, and the V1 loop |
| `tools.py` | `search_movies` and `get_movie_details` |

V1 looks like this:

```text
You → model → tool call → Python → tool result → model → answer
                ↑                              |
                └──────── another call ────────┘
```

The model chooses the arguments and whether to call a tool. Python runs only those two functions and sends each result back with its `call_id`, including a failed call. A turn stops after eight model requests. The trace shows calls and data, not the model's private reasoning.

`search_movies` keeps movies that match any requested genre, drops excluded genres, and applies a runtime cap. It returns at most eight movies from the first page of results. `get_movie_details` loads one id. Later messages are only the chat you can see. Nothing else is remembered.

## Try

- “We want something funny or mysterious, under two hours, with no horror.”
- “Actually, we already watched Game Night. Something under 105 minutes?”
- “Find a comedy under 20 minutes.”

Run the same prompt in V0. Those picks are not looked up.

A constraint is an instruction to the model, not a guarantee. A genre does not prove a movie is safe for kids or not scary. There is no tool for where a movie is streaming.

If you want to change the code, add a watched-movie argument to `search_movies` and ask the agent to skip a title.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests fake the model and TMDB, so they do not spend API credits.

[OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling) · [TMDB discover](https://developer.themoviedb.org/reference/discover-movie) · [TMDB movie details](https://developer.themoviedb.org/reference/movie-details)

This product uses the TMDB API but is not endorsed or certified by TMDB.
