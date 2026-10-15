import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from movie_agent.agent import run_agent
from movie_agent.tools import search_movies


def response(text="", calls=()):
    return SimpleNamespace(output=list(calls), output_text=text)


def call(name="search_movies", arguments=None):
    return SimpleNamespace(type="function_call", name=name, call_id="call_1",
                           arguments=arguments or '{"genres":["comedy"],"exclude_genres":["horror"],"max_runtime":119}')


DISCOVER = {"results": [{"id": 1, "title": "Game Night", "release_date": "2018-02-23", "overview": "Friends."}]}


class AgentTests(unittest.TestCase):
    def test_v0_does_not_offer_tools(self):
        client = Mock()
        client.responses.create.return_value = response("Unverified suggestions")
        answer = run_agent([], use_tools=False, client=client)
        self.assertEqual(answer, "Unverified suggestions")
        self.assertEqual(client.responses.create.call_args.kwargs["tools"], [])
        self.assertEqual(client.responses.create.call_count, 1)

    def test_loop_returns_matching_call_output_and_preserves_model_items(self):
        client = Mock()
        first_call = call()
        reasoning = SimpleNamespace(type="reasoning")
        snapshots = []
        def create(**kwargs):
            snapshots.append(list(kwargs["input"]))
            return [response(calls=[reasoning, first_call]), response("Done")][len(snapshots) - 1]
        client.responses.create.side_effect = create
        events = []
        with patch("movie_agent.tools._get", return_value=DISCOVER):
            self.assertEqual(run_agent([], client=client, on_call=lambda *event: events.append(event)), "Done")
        self.assertIs(snapshots[1][0], reasoning)
        self.assertEqual(snapshots[1][2]["call_id"], "call_1")
        self.assertIn("Game Night", snapshots[1][2]["output"])
        self.assertEqual(len(events), 1)

    def test_tool_error_goes_back_to_the_model_until_the_step_limit(self):
        client = Mock()
        client.responses.create.return_value = response(calls=[call(name="unknown")])
        events = []
        answer = run_agent([], client=client, max_rounds=2, on_call=lambda *event: events.append(event))
        self.assertIn("Stopped", answer)
        self.assertEqual(client.responses.create.call_count, 2)
        self.assertIn("error", events[0][2])

    def test_tmdb_failure_is_returned_to_the_model(self):
        client = Mock()
        client.responses.create.side_effect = [response(calls=[call()]), response("Unavailable")]
        events = []
        with patch("movie_agent.tools._get", side_effect=RuntimeError("TMDB down")):
            answer = run_agent([], client=client, on_call=lambda *event: events.append(event))
        self.assertEqual(answer, "Unavailable")
        self.assertEqual(events[0][2], {"error": "TMDB down"})


class ToolTests(unittest.TestCase):
    def test_discover_uses_correct_query(self):
        with patch("movie_agent.tools._get", return_value={"results": []}) as get:
            search_movies(["comedy", "mystery"], ["horror"], 119)
        params = get.call_args.args[1]
        self.assertEqual(params["with_genres"], "35|9648")
        self.assertEqual(params["without_genres"], "27")
        self.assertEqual(params["with_runtime.lte"], 119)


class InterfaceTests(unittest.TestCase):
    def test_missing_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "movie_agent" / "page.py")).run()
            self.assertFalse(app.exception)
            app.chat_input[0].set_value("Find a movie").run()
            self.assertTrue(any("OPENAI_API_KEY" in item.value for item in app.error))


if __name__ == "__main__":
    unittest.main()
