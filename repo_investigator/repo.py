"""A public GitHub repository, loaded once into memory, plus three read-only tools."""

import io
import os
import re
import tarfile

import requests

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv", "vendor", "__pycache__"}
MAX_FILE_BYTES = 150_000
MAX_FILES = 3_000
MAX_READ_LINES = 150
MAX_MATCHES = 30


def parse_repo(text):
    """Accept owner/repo or a github.com URL, optionally with /tree/<ref>."""
    text = text.strip().removesuffix(".git").rstrip("/")
    match = re.fullmatch(r"(?:https?://)?(?:www\.)?(?:github\.com/)?([\w.-]+)/([\w.-]+)(?:/tree/(.+))?", text)
    if not match:
        raise ValueError("Use owner/repo or https://github.com/owner/repo")
    return match.group(1), match.group(2), match.group(3) or ""


class Repo:
    def __init__(self, owner, name, sha, files):
        self.owner, self.name, self.sha, self.files = owner, name, sha, files

    @classmethod
    def from_github(cls, text):
        owner, name, ref = parse_repo(text)
        headers = {"Accept": "application/vnd.github+json"}
        if os.getenv("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {os.getenv('GITHUB_TOKEN')}"
        url = f"https://api.github.com/repos/{owner}/{name}/tarball/{ref}".rstrip("/")
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 404:
            raise ValueError(f"{owner}/{name} not found, or it is private.")
        response.raise_for_status()
        return cls.from_tarball(owner, name, response.content)

    @classmethod
    def from_tarball(cls, owner, name, data):
        files, sha = {}, ""
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive:
                # GitHub names the top folder owner-repo-<short sha>. Nothing is written to disk.
                top, _, path = member.name.partition("/")
                if not path:
                    sha = top.rsplit("-", 1)[-1]
                if not member.isfile() or member.size > MAX_FILE_BYTES:
                    continue
                if SKIP_DIRS & set(path.split("/")[:-1]):
                    continue
                try:
                    files[path] = archive.extractfile(member).read().decode("utf-8")
                except UnicodeDecodeError:
                    continue
                if len(files) >= MAX_FILES:
                    break
        return cls(owner, name, sha, files)

    def link(self, path, line=None):
        url = f"https://github.com/{self.owner}/{self.name}/blob/{self.sha}/{path}"
        return f"{url}#L{line}" if line else url

    def lines(self, path):
        return self.files[path].splitlines()

    # The tools. Every result is a small dict the model can read.

    # `allowed` is set by the application, not the model, to keep a worker inside its scope.

    def list_files(self, prefix="", allowed=lambda path: True):
        paths = [p for p in sorted(self.files) if p.startswith(prefix) and allowed(p)]
        return {"files": paths[:300], "total": len(paths)}

    def read_file(self, path, start_line=1, end_line=0):
        if path not in self.files:
            return {"error": f"No file {path}. Use list_files to see paths."}
        lines = self.lines(path)
        start = max(start_line, 1)
        end = min(end_line or len(lines), start + MAX_READ_LINES - 1, len(lines))
        numbered = "\n".join(f"{n}: {lines[n - 1]}" for n in range(start, end + 1))
        return {"path": path, "start_line": start, "end_line": end, "total_lines": len(lines), "text": numbered}

    def search_code(self, text, prefix="", allowed=lambda path: True):
        needle = text.lower()
        matches = []
        for path in sorted(self.files):
            if not path.startswith(prefix) or not allowed(path):
                continue
            for number, line in enumerate(self.lines(path), 1):
                if needle in line.lower():
                    matches.append(f"{path}:{number}: {line.strip()[:160]}")
        return {"matches": matches[:MAX_MATCHES], "total": len(matches)}


def normalize(text):
    return " ".join(text.split()).strip("`'\" ")


def check_citation(repo, finding):
    """Plain code, no model: does the file exist, and is the quote on (or next to) the cited line?"""
    path, line, quote = finding["path"], finding["line"], normalize(finding["quote"])
    if path not in repo.files:
        return False, f"{path} does not exist"
    lines = repo.lines(path)
    if not 1 <= line <= len(lines):
        return False, f"{path} has {len(lines)} lines, not {line}"
    if not quote:
        return False, "no quote given"
    nearby = normalize(" ".join(lines[max(line - 3, 0):line + 2]))
    if quote not in nearby:
        return False, f"line {line} says: {lines[line - 1].strip()[:120]}"
    return True, "quote matches the cited line"
