"""Two ordinary Python functions, exposed to the model as tools."""

import os

import requests

GENRES = {
    "action": 28, "adventure": 12, "animation": 16, "comedy": 35,
    "crime": 80, "documentary": 99, "drama": 18, "family": 10751,
    "fantasy": 14, "history": 36, "horror": 27, "music": 10402,
    "mystery": 9648, "romance": 10749, "science fiction": 878,
    "thriller": 53, "war": 10752, "western": 37,
}


def _get(path, params=None):
    response = requests.get(
        f"https://api.themoviedb.org/3/{path}",
        headers={"Authorization": f"Bearer {os.getenv('TMDB_READ_TOKEN')}"},
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def search_movies(genres, exclude_genres, max_runtime):
    """Discover candidates matching ANY requested genre, excluding others."""
    include = [g.lower().strip() for g in genres]
    exclude = [g.lower().strip() for g in exclude_genres]
    data = _get("discover/movie", {
        "with_genres": "|".join(str(GENRES[g]) for g in include),
        "without_genres": ",".join(str(GENRES[g]) for g in exclude),
        "with_runtime.gte": 1,
        "with_runtime.lte": max_runtime,
        "include_adult": "false",
        "sort_by": "popularity.desc",
    })
    movies = [{"id": m["id"], "title": m["title"],
               "year": (m.get("release_date") or "")[:4],
               "overview": m.get("overview", "")} for m in data["results"]]
    return {"movies": movies[:8]}


def get_movie_details(movie_id):
    movie = _get(f"movie/{movie_id}")
    return {
        "id": movie["id"],
        "title": movie["title"],
        "year": (movie.get("release_date") or "")[:4],
        "runtime": movie.get("runtime"),
        "genres": [g["name"] for g in movie.get("genres", [])],
        "overview": movie.get("overview", ""),
    }


TOOLS = [
    {
        "type": "function", "name": "search_movies", "strict": True,
        "description": "Discover up to 8 movies. Genres are OR-matched. Valid genres: "
                       + ", ".join(GENRES) + ". Use empty lists for no genre filter.",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "genres": {"type": "array", "items": {"type": "string"}},
                "exclude_genres": {"type": "array", "items": {"type": "string"}},
                "max_runtime": {"type": "integer", "description": "Minutes, 1–400. Use 400 if unspecified."},
            },
            "required": ["genres", "exclude_genres", "max_runtime"],
        },
    },
    {
        "type": "function", "name": "get_movie_details", "strict": True,
        "description": "Look up runtime, genres, and overview for a movie ID from search results.",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {"movie_id": {"type": "integer"}},
            "required": ["movie_id"],
        },
    },
]
