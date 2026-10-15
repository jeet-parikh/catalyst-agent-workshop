import io
import json
import sys
import tarfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "investigator"))

from agents import PLANNER, ROUTER, WORKER, WRITER, Investigation  # noqa: E402
from repo import Repo, check_citation, parse_repo  # noqa: E402

FILES = {
    "tools.py": "import os\n\ndef search_movies(genres, exclude_genres, max_runtime):\n    return {}\n",
    "tests/test_tools.py": "def test_search():\n    search_movies([], [], 90)\n",
    "README.md": "# Movies\nAdd a watched-movie argument.\n",
}


def repo():
    return Repo("owner", "movies", "abc1234", dict(FILES))


def response(text="", calls=()):
    return SimpleNamespace(output=list(calls), output_text=text,
                           usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def call(name, args, call_id="c1"):
    return SimpleNamespace(type="function_call", name=name, arguments=json.dumps(args), call_id=call_id)


def finding(path, line, quote, claim="claim"):
    return {"claim": claim, "path": path, "line": line, "quote": quote}


class RepoTests(unittest.TestCase):
    def test_parse_repo(self):
        self.assertEqual(parse_repo("owner/repo"), ("owner", "repo", ""))
        self.assertEqual(parse_repo("https://github.com/owner/repo.git"), ("owner", "repo", ""))
        self.assertEqual(parse_repo("github.com/owner/repo/tree/dev"), ("owner", "repo", "dev"))
        with self.assertRaises(ValueError):
            parse_repo("not a repo")

    def test_tarball_keeps_text_files_and_reads_sha(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as archive:
            folder = tarfile.TarInfo("owner-movies-abc1234")
            folder.type = tarfile.DIRTYPE
            archive.addfile(folder)
            for path, body in [("app.py", b"print(1)\n"), ("node_modules/x.js", b"x"), ("logo.png", b"\xff\xd8\xff")]:
                info = tarfile.TarInfo(f"owner-movies-abc1234/{path}")
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
        loaded = Repo.from_tarball("owner", "movies", data.getvalue())
        self.assertEqual(loaded.sha, "abc1234")
        self.assertEqual(list(loaded.files), ["app.py"])

    def test_tools_return_numbered_lines_and_matches(self):
        r = repo()
        self.assertIn("3: def search_movies", r.read_file("tools.py", 3, 3)["text"])
        self.assertIn("error", r.read_file("missing.py"))
        self.assertEqual(r.search_code("SEARCH_MOVIES")["total"], 2)

    def test_citation_check(self):
        r = repo()
        self.assertTrue(check_citation(r, finding("tools.py", 3, "def search_movies(genres, exclude_genres, max_runtime):"))[0])
        self.assertTrue(check_citation(r, finding("tools.py", 3, "`search_movies(genres,  exclude_genres`"))[0])
        self.assertFalse(check_citation(r, finding("tools.py", 99, "def"))[0])
        self.assertFalse(check_citation(r, finding("app.py", 1, "x"))[0])
        ok, reason = check_citation(r, finding("README.md", 1, "watched list is stored in session state"))
        self.assertFalse(ok)
        self.assertIn("says", reason)


class FakeModel:
    """Answers by role. Worker A cites one wrong line, then fixes it when the check sends it back."""

    def __init__(self, route="investigate"):
        self.route, self.kwargs = route, []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.kwargs.append(kwargs)
        instructions, items = kwargs["instructions"], kwargs["input"]
        if instructions == ROUTER:
            return response(json.dumps({"route": self.route, "reason": "test"}))
        if instructions == PLANNER:
            return response(json.dumps({"assignments": [
                {"name": "Code", "objective": "find the function", "scope": ["tools.py"], "budget": 3},
                {"name": "Tests", "objective": "find the tests", "scope": ["tests"], "budget": 3}]}))
        if instructions == WRITER:
            return response("Add the argument [F1].")
        assert instructions == WORKER
        text = json.dumps([getattr(item, "arguments", item) for item in items], default=str)
        tests = "find the tests" in items[0]["content"]
        if not any(isinstance(i, dict) and i.get("type") == "function_call_output" for i in items):
            return response(calls=[call("read_file", {"path": "tools.py", "start_line": 1, "end_line": 0})])
        if "failed the citation check" in text:
            return response(calls=[call("submit_findings", {"findings": [
                finding("tools.py", 3, "def search_movies(genres, exclude_genres, max_runtime):")], "unresolved": ""})])
        if tests:
            return response(calls=[call("submit_findings", {"findings": [
                finding("tests/test_tools.py", 2, "search_movies([], [], 90)")], "unresolved": ""})])
        return response(calls=[call("submit_findings", {"findings": [
            finding("tools.py", 1, "import os"), finding("tools.py", 1, "def watched()")], "unresolved": ""})])


class InvestigationTests(unittest.TestCase):
    def run_investigation(self, model, mode="multi"):
        events = []
        Investigation(repo(), "How do I skip watched movies?", emit=events.append, client=model).run(mode)
        return events

    def test_multi_agent_run_checks_evidence_and_repairs_once(self):
        events = self.run_investigation(FakeModel())
        kinds = [e["type"] for e in events]
        self.assertEqual(kinds[:2], ["route", "plan"])
        self.assertEqual(kinds[-2:], ["answer", "stats"])
        retry = [e for e in events if e["type"] == "check" and e["retry"]]
        self.assertEqual(len(retry), 1)
        self.assertTrue(retry[0]["results"][0]["ok"])
        answer, stats = events[-2], events[-1]
        self.assertTrue(all(s["link"].startswith("https://github.com/owner/movies/blob/abc1234/") for s in answer["sources"]))
        self.assertEqual(len(answer["sources"]), 3)
        self.assertEqual((stats["verified"], stats["rejected"]), (3, 1))

    def test_writer_sees_only_verified_findings(self):
        model = FakeModel()
        self.run_investigation(model)
        writer = next(k for k in model.kwargs if k["instructions"] == WRITER)
        self.assertNotIn("def watched()", writer["input"])
        self.assertIn("tools.py:3", writer["input"])

    def test_worker_cannot_read_outside_its_scope(self):
        investigation = Investigation(repo(), "q", client=Mock())
        result = investigation.run_tool("A", ["tests"], "read_file", {"path": "tools.py", "start_line": 1, "end_line": 0})
        self.assertIn("outside your assignment scope", result["error"])
        listed = investigation.run_tool("A", ["tests"], "list_files", {"prefix": ""})
        self.assertEqual(listed["files"], ["tests/test_tools.py"])

    def test_budget_forces_submission(self):
        model = Mock()
        model.responses.create.side_effect = [
            response(calls=[call("list_files", {"prefix": ""})]),
            response(calls=[call("list_files", {"prefix": ""})]),
            response(calls=[call("submit_findings", {"findings": [], "unresolved": "ran out"})]),
        ]
        investigation = Investigation(repo(), "q", client=model)
        findings, unresolved = investigation.loop("A", [""], [{"role": "user", "content": "go"}], 2)
        self.assertEqual((findings, unresolved), ([], "ran out"))
        last = model.responses.create.call_args.kwargs["tool_choice"]
        self.assertEqual(last, {"type": "function", "name": "submit_findings"})
        self.assertEqual(investigation.stats["tool_calls"], 2)

    def test_baseline_uses_one_worker_on_the_whole_repo(self):
        events = self.run_investigation(FakeModel(), mode="single")
        plan = next(e for e in events if e["type"] == "plan")
        self.assertTrue(plan["baseline"])
        self.assertEqual(plan["assignments"][0]["scope"], [""])

    def test_out_of_scope_requests_stop_after_routing(self):
        model = FakeModel(route="out_of_scope")
        events = self.run_investigation(model)
        self.assertEqual([e["type"] for e in events], ["route", "answer", "stats"])
        self.assertEqual(len(model.kwargs), 1)


class DemoTests(unittest.TestCase):
    def test_missing_key(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "investigator" / "demo.py")).run()
            self.assertFalse(app.exception)
            next(b for b in app.button if b.label == "Investigate").click().run()
            self.assertTrue(any("OPENAI_API_KEY" in item.value for item in app.error))


if __name__ == "__main__":
    unittest.main()
