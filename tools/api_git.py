"""Save Work routes: git status, commit, push and fetch (logic in gitstatus.py).

Owned by the Publication / Save Work module (see MODULES.json). Registered through routes.py.
"""
from __future__ import annotations

import chapter as C
import jobs as J
import routes

ROOT = C.ROOT


@routes.get("/api/git")
def git_info(qs: dict | None = None) -> dict:
    import gitstatus as GS  # noqa: PLC0415
    return GS.status(ROOT)


def git_commit(message: str, push: bool) -> dict:
    """Commit the book's folders (unchanged staging policy), then optionally push. Reports each step."""
    import gitstatus as GS  # noqa: PLC0415
    J.report(0.2, "Committing…")
    c = GS.commit(ROOT, message)
    result = {"ok": c["ok"], "commit": c, "push": None, "output": c.get("output", "")}
    if c["ok"] and push:
        with J.creep(0.4, 0.98, 8, "Pushing to GitHub…"):
            pu = GS.push(ROOT)
        result.update(ok=pu["ok"], push=pu, output="\n".join(x for x in (c.get("output"), pu.get("output")) if x))
    return result


@routes.post("/api/git/push")
def git_push(data: dict | None = None) -> dict:
    import gitstatus as GS  # noqa: PLC0415
    with J.creep(0.1, 0.98, 8, "Pushing to GitHub…"):
        pu = GS.push(ROOT)
    return {"ok": pu["ok"], "commit": None, "push": pu, "output": pu.get("output", "")}


@routes.post("/api/git/fetch")
def git_fetch(data: dict | None = None) -> dict:
    import gitstatus as GS  # noqa: PLC0415
    with J.creep(0.1, 0.98, 5, "Checking GitHub…"):
        return GS.fetch(ROOT)



@routes.post("/api/git/commit")
def git_commit_route(data: dict) -> dict:
    return git_commit(data.get("message", ""), bool(data.get("push")))
