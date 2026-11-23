"""Git status, commit and push for Book Builder's Save Work page, as structured data.

Save Work only ever commits the book's own folders (SAVE_PATHS); other changes are reported as
"not included" and never staged. Ignored files are not listed. Errors from GitHub are classified
(network, authentication, rejected, no remote) so the page can explain them in plain words.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

# The staging policy: what "Commit" saves. Unchanged from the original Book Manager.
SAVE_PATHS = ["book", "drafts", "prompts", "reviews", "research", "briefs", "sources", "images", "references.bib", "book.yml"]
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "LC_ALL": "C"}  # never hang on a password prompt


def git(root: Path, *args: str, timeout: int = 30, raw: bool = False) -> tuple[int, str]:
    """raw=True keeps leading spaces, which are part of `git status --porcelain` codes."""
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=timeout, env=GIT_ENV)
        return r.returncode, r.stdout if raw else (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "Timed out waiting for git (the network may be unavailable)."
    except OSError as e:
        return 127, f"git couldn't run: {e}"


def eligible(path: str) -> bool:
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in SAVE_PATHS)


def classify_error(text: str) -> str:
    t = text.lower()
    if re.search(r"could not resolve host|unable to access|failed to connect|network is unreachable|timed out|"
                 r"connection (refused|reset|timed out)|could not read from remote repository\.\s*$", t) and \
            not re.search(r"authentication|permission denied|403|could not read username", t):
        return "network"
    if re.search(r"authentication failed|permission denied|could not read username|403|invalid username|"
                 r"terminal prompts disabled|denied to", t):
        return "auth"
    if re.search(r"\[rejected\]|non-fast-forward|fetch first|updates were rejected", t):
        return "rejected"
    if re.search(r"no configured push destination|no upstream|does not appear to be a git repository|"
                 r"has no upstream branch", t):
        return "noremote"
    return "other"


ERROR_TEXT = {
    "network": "Couldn't reach GitHub. Check your internet connection and try again; your commit is safe on this computer.",
    "auth": "GitHub didn't accept your sign-in. Sign in again (for example run `gh auth login` in Terminal), then push.",
    "rejected": "GitHub has changes this computer doesn't have yet. Pull them first (git pull), then push.",
    "noremote": "This book isn't connected to a GitHub repository (no upstream branch), so there's nothing to push to.",
    "other": "Git reported a problem. See Technical details.",
}


def parse_porcelain(raw: str) -> list[dict]:
    """`git status --porcelain=v1 -z` → [{path, x, y, kind}]."""
    out, parts, i = [], raw.split("\0"), 0
    while i < len(parts):
        e = parts[i]
        i += 1
        if len(e) < 4:
            continue
        x, y, path = e[0], e[1], e[3:]
        if x in "RC":                       # renames carry the old path as the next field
            i += 1
        if x == "?" and y == "?":
            kind = "untracked"
        elif "U" in (x, y) or (x, y) in (("A", "A"), ("D", "D")):
            kind = "conflict"
        elif "D" in (x, y):
            kind = "deleted"
        elif x in "AC" and x != " ":
            kind = "added"
        elif x == "R":
            kind = "renamed"
        else:
            kind = "modified"
        out.append({"path": path, "x": x, "y": y, "kind": kind, "eligible": eligible(path)})
    return out


def status(root: Path) -> dict:
    code, inside = git(root, "rev-parse", "--is-inside-work-tree")
    if code != 0 or inside != "true":
        return {"repo": False, "state": "norepo", "message": "This book's folder isn't a git repository, so there's nothing to save to GitHub."}
    _, branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    c_up, upstream = git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    upstream = upstream if c_up == 0 else None
    ahead = behind = 0
    if upstream:
        c, counts = git(root, "rev-list", "--left-right", "--count", "@{u}...HEAD")
        if c == 0 and re.fullmatch(r"\d+\s+\d+", counts):
            behind, ahead = (int(v) for v in counts.split())
    _, raw = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=normal", raw=True)
    files = parse_porcelain(raw)
    _, ignored_raw = git(root, "status", "--porcelain=v1", "--ignored=traditional", "--untracked-files=normal", raw=True)
    ignored = sum(1 for line in ignored_raw.splitlines() if line.startswith("!!"))
    _, human = git(root, "status")
    merging = (root / ".git" / "MERGE_HEAD").exists() or (root / ".git" / "rebase-merge").exists()

    def last(ref: str) -> dict | None:
        c, line = git(root, "log", "-1", "--format=%h%x1f%ct%x1f%s", ref)
        if c != 0 or not line:
            return None
        h, t, s = line.split("\x1f", 2)
        return {"hash": h, "time": float(t), "subject": s}

    _, log = git(root, "log", "-10", "--format=%h%x1f%ct%x1f%s")
    fetch_head = root / ".git" / "FETCH_HEAD"
    counts = {k: sum(1 for f in files if f["kind"] == k) for k in ("modified", "added", "deleted", "renamed", "untracked", "conflict")}
    save = [f for f in files if f["eligible"] and f["kind"] != "conflict"]
    other = [f for f in files if not f["eligible"]]
    conflicts = [f for f in files if f["kind"] == "conflict"]
    if conflicts or merging:
        state = "conflict"
    elif save:
        state = "changes"
    elif ahead and upstream:
        state = "ahead"
    elif behind and upstream:
        state = "behind"
    elif not upstream:
        state = "noupstream"
    elif other:
        state = "other"
    else:
        state = "clean"
    return {"repo": True, "state": state, "branch": branch, "upstream": upstream, "ahead": ahead, "behind": behind,
            "files": files, "counts": counts, "saveCount": len(save), "otherCount": len(other), "ignored": ignored,
            "conflicts": [f["path"] for f in conflicts], "merging": merging,
            "lastCommit": last("HEAD"), "lastPush": last("@{u}") if upstream else None,
            "lastFetch": fetch_head.stat().st_mtime if fetch_head.exists() else None,
            "log": [dict(zip(("hash", "time", "subject"), (h, float(t), s))) for h, t, s in
                    (line.split("\x1f", 2) for line in log.splitlines() if line.count("\x1f") == 2)],
            "savePaths": SAVE_PATHS, "raw": human}


def commit(root: Path, message: str) -> dict:
    """Commit only SAVE_PATHS. Never stages anything else; returns the new commit's hash and subject."""
    message = " ".join((message or "").split()) or "Update chapters"
    st = status(root)
    if not st["repo"]:
        return {"ok": False, "stage": "commit", "message": st["message"], "output": ""}
    if st["state"] == "conflict":
        return {"ok": False, "stage": "commit", "message": "Resolve the merge conflicts first.", "output": st["raw"]}
    if not st["saveCount"]:
        return {"ok": False, "stage": "commit", "message": "There are no changes in the book's folders to commit.", "output": ""}
    paths = [p for p in SAVE_PATHS if (root / p).exists()]
    out = []
    code, o = git(root, "add", "-A", "--", *paths)
    out.append(o)
    if code != 0:
        return {"ok": False, "stage": "commit", "message": "Couldn't stage the book's changes.", "output": "\n".join(out)}
    code, o = git(root, "commit", "-m", message, "--", *paths)   # --only these paths, even if other files are staged
    out.append(o)
    if code != 0:
        return {"ok": False, "stage": "commit", "message": "The commit didn't go through.", "output": "\n".join(x for x in out if x)}
    _, h = git(root, "rev-parse", "--short", "HEAD")
    return {"ok": True, "stage": "commit", "hash": h, "subject": message,
            "message": f"Committed {h} on this computer.", "output": "\n".join(x for x in out if x)}


def push(root: Path, timeout: int = 90) -> dict:
    st = status(root)
    if not st["repo"]:
        return {"ok": False, "stage": "push", "kind": "noremote", "message": st["message"], "output": ""}
    if not st["upstream"]:
        return {"ok": False, "stage": "push", "kind": "noremote", "message": ERROR_TEXT["noremote"], "output": ""}
    if not st["ahead"]:
        return {"ok": True, "stage": "push", "message": "Nothing to push: GitHub already has every commit.", "output": ""}
    code, o = git(root, "push", timeout=timeout)
    if code == 0:
        return {"ok": True, "stage": "push", "message": f"Pushed {st['ahead']} commit(s) to {st['upstream']}.", "output": o}
    kind = "network" if code == 124 else classify_error(o)
    return {"ok": False, "stage": "push", "kind": kind, "message": ERROR_TEXT[kind], "output": o}


def fetch(root: Path, timeout: int = 45) -> dict:
    code, o = git(root, "fetch", "--quiet", timeout=timeout)
    if code == 0:
        return {"ok": True, "message": "Checked GitHub.", "output": o, "time": time.time()}
    kind = "network" if code == 124 else classify_error(o)
    return {"ok": False, "kind": kind, "message": ERROR_TEXT[kind], "output": o}
