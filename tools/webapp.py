#!/usr/bin/env python3
"""Book manager in your browser. Started by run/Book Manager.command.

    python tools/webapp.py            start on http://127.0.0.1:8765 and open the browser
    python tools/webapp.py --no-open  start without opening a browser
    python tools/webapp.py --port 8766  use another port (e.g. to test while another copy runs)

Only listens on this computer (127.0.0.1). Uses the same logic as tools/chapter.py and tools/menu.py.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chapter as C  # noqa: E402
import games as G  # noqa: E402
import jobs as J  # noqa: E402
import packs  # noqa: E402,F401  (registers this book's prompt kinds)
import promptpack as P  # noqa: E402
import workspace as W  # noqa: E402
import platformio  # noqa: E402
import routes  # noqa: E402
from bookmeta import BOOK_FIELDS, book_meta, save_book_meta  # noqa: E402,F401  (re-exported for callers)
import menu as M  # noqa: E402

ROOT = C.ROOT
APP = Path(__file__).resolve().parent.parent  # Book Builder itself (tools, fonts, web UI)
PORT = 8765
PAGE = Path(__file__).resolve().parent / "web" / "index.html"
PY = sys.executable
READABLE = ("book", "drafts", "reviews", "prompts", "briefs", "research", "agents", "sources", "dist",
            "run", "README.md", "PROJECT-BRIEF.md", "book.yml", "references.bib")
STAGES = ["research", "prompt", "draft", "check", "revise", "approved"]


# ------------------------------------------------------------------ helpers

def run(*args: str, timeout: int = 600) -> tuple[bool, str]:
    """Run one of the project's Python tools; its progress reports move the current job's bar."""
    args = tuple(str(APP / a) if str(a).startswith("tools/") else a for a in args)  # engine scripts live with the app
    return J.run_cmd([PY, *args], cwd=ROOT, timeout=timeout)


def sh(*args: str) -> tuple[bool, str]:
    r = subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def pbcopy(text: str) -> None:
    platformio.copy(text)


def pbpaste() -> str:
    return platformio.paste()


def rel(p: Path | None) -> str | None:
    return p.relative_to(ROOT).as_posix() if p else None


def find(n: int) -> dict:
    for ch in M.chapters():
        if ch["n"] == n:
            return ch
    raise ValueError(f"No chapter {n}")


def stage_of(code: str, ch: dict) -> str:
    return {"research": "research", "saveresearch": "research", "write": "prompt", "save": "draft" if not C.latest_draft(ch) else "revise", "fix": "draft",
            "claude": "check", "revise": "revise", "approve": "check", "advance": "approved"}[code]


def chapter_summary(ch: dict, hashes: dict) -> dict:
    code, label = M.next_step(ch, hashes)
    issues = M.problems(ch, hashes)
    draft = C.latest_draft(ch)
    meta, _ = C.front_matter(C.chapter_path(ch))
    v = M.draft_version(draft) if draft else 0
    words = 0
    if draft:
        body = re.sub(r"\A---.*?\n---\s*\n", "", draft.read_text(encoding="utf-8"), flags=re.S)
        words = len(body.split())
    return {
        "n": ch["n"], "title": ch["title"], "part": ch["part"]["n"], "partName": ch["part"]["name"],
        "status": meta.get("status", "?"), "code": code, "label": label, "stage": stage_of(code, ch),
        "version": v, "words": words, "problems": issues,
        "serious": len(M.serious(issues)), "chat": M.name(ch),
        "kind": ch.get("kind", "chapter"), "num": ch["num"] if C.is_special(ch) else f"{ch['n']:02d}",
        "ref": C.what(ch), "zip": f"{ch['key']}-research.zip" if C.is_special(ch) else f"ch{ch['n']:02d}-research.zip",
        "needsResearch": not C.is_special(ch) or bool(ch.get("research")),
    }


def chapter_detail(ch: dict) -> dict:
    hashes = M.body_hashes()
    out = chapter_summary(ch, hashes)
    st = M.stem(ch)
    ddir = C.drafts_dir(ch)
    versions = []
    for d in sorted(ddir.glob("v*-chapter.md"), key=M.draft_version) if ddir.exists() else []:
        v = M.draft_version(d)
        notes = ddir / f"v{v}-editor-notes.md"
        check = M.review_dir(ch) / f"v{v}-check.md"
        versions.append({"v": v, "chapter": rel(d), "notes": rel(notes) if notes.exists() else None,
                         "check": rel(check) if check.exists() else None,
                         "verdict": ("ready" if check.exists() and "ready to approve" in
                                     check.read_text(encoding="utf-8").lower() else
                                     "revise" if check.exists() else None)})
    prompts = sorted(rel(p) for p in (ROOT / "prompts").glob(f"{st}-*.md"))
    reviews = sorted(rel(p) for p in M.review_dir(ch).rglob("*.md")) if M.review_dir(ch).exists() else []
    brief = ROOT / "briefs" / ch["part"]["folder"] / C.chapter_path(ch).name
    out.update({
        "desc": ch["desc"], "markers": ch["markers"], "book": rel(C.chapter_path(ch)),
        "brief": rel(brief) if brief.exists() else None, "versions": versions,
        "prompts": prompts, "reviews": reviews,
        "partQuestion": ch["part"].get("question", ""), "partHandoff": ch["part"].get("handoff", ""),
        "draftName": C.chat_name(ch["n"], ch["title"], "draft"),
        "research": rel(C.research_path(ch)) if C.research_path(ch).exists() else None,
    })
    return out


def state() -> dict:
    hashes = M.body_hashes()
    chs = [chapter_summary(c, hashes) for c in M.chapters()]
    _, parts, _ = C.parse_outline()
    missing = [f for f in ("agents/chatgpt-writer.md", "agents/chatgpt-project-instructions.md",
                           "research/continuity.md", "research/pass-1/index.yml", "book.yml", "references.bib")
               if not (ROOT / f).exists()]
    dist = sorted(rel(p) for p in (ROOT / "dist").glob("*.*") if p.suffix in (".pdf", ".epub", ".html", ".docx"))
    info = [{"path": d, "bytes": (ROOT / d).stat().st_size, "mtime": (ROOT / d).stat().st_mtime,
             "current": Path(d).name.startswith(build_stem())} for d in dist]
    return {"current": M.load_current(), "chapters": chs, "missing": missing, "outputs": dist, "outputInfo": info,
            "memoryStale": C.library_stale(), "book": book_meta(),
            "parts": {n: {"name": p["name"], "question": p.get("question", "")} for n, p in parts.items()}}


def build_stem() -> str:
    """File name the current build writes (older names are kept but shown as older files)."""
    import build as B  # noqa: PLC0415
    return B.OUTPUT_STEM


def guess_chapter(title: str) -> int | None:
    best, score = None, 0
    want = set(C.slugify(title, 20).split("-"))
    for ch in M.chapters():
        if C.slugify(ch["title"], 2) in C.slugify(title, 12):
            return ch["n"]
        words = set(C.slugify(ch["title"], 20).split("-"))
        s = len(want & words) / max(len(words), 1)
        if s > score:
            best, score = ch["n"], s
    return best if score >= 0.6 else None


def preview(ch: dict, raw: str) -> dict:
    text = C.clean(raw)
    chapter_text, _, notes = text.partition(C.MARKER)
    m = re.search(r'^title:\s*"?(.+?)"?\s*$', chapter_text, re.M)
    title = m.group(1) if m else None
    issues = M.text_problems(ch, chapter_text.strip())
    dup = None
    for d in (ROOT / "drafts").glob("*/v*-chapter.md"):
        if d.read_text(encoding="utf-8").strip() == chapter_text.strip():
            dup = rel(d)
    if not notes.strip():
        issues.append("(Minor) No editor notes: the === EDITOR NOTES === line is missing.")
    guess = guess_chapter(title) if title else None
    body = re.sub(r"\A---.*?\n---\s*\n", "", chapter_text, flags=re.S)
    return {"title": title, "words": len(body.split()), "problems": issues, "duplicate": dup,
            "guess": guess if guess != ch["n"] else None, "hasNotes": bool(notes.strip()),
            "start": text.strip()[:400], "empty": not text.strip()}


def research_preview(ch: dict, raw: str) -> dict:
    text = C.clean(raw).strip()
    lines = text.splitlines()
    head = lines[0] if lines else ""
    issues = []
    guess = None
    m = re.match(r"#\s*Research:\s*(?:Ch\s*(\d+)\s*·\s*)?(.+)", head)
    if m:
        if m.group(1) and int(m.group(1)) != ch["n"]:
            guess = int(m.group(1))
        elif C.slugify(ch["title"], 2) not in C.slugify(m.group(2), 20):
            guess = guess_chapter(m.group(2))
    else:
        issues.append("Doesn't start with “# Research: Ch NN · Title”. Is this the research reply?")
    if C.MARKER in text or re.search(r"^status:\s*draft", text, re.M):
        issues.append("This looks like a chapter draft, not research. Save it as a draft instead.")
    sources = len(re.findall(r"^\s*-\s*key:", text, re.M))
    if C.SOURCES_MARKER not in text:
        issues.append("No === SOURCES === line; the source list is missing or was cut off.")
    elif sources == 0:
        issues.append("The source list is empty.")
    if len(text.split()) < 300:
        issues.append(f"Only {len(text.split())} words; probably cut off. Type “continue” in ChatGPT.")
    if re.search(r"can(no|')t browse|unable to browse|don't have (web|internet)|not opened", text, re.I):
        issues.append("(Minor) ChatGPT says it couldn't browse or didn't open some sources; Claude will check those closely.")
    return {"title": head[:120], "words": len(text.split()), "sources": sources, "problems": issues,
            "guess": guess if guess != ch["n"] else None, "start": text[:400], "empty": not text,
            "duplicate": None, "hasNotes": sources > 0}


def save_research(ch: dict, raw: str) -> dict:
    tmp = ROOT / "dist" / "web-research.md"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text(raw, encoding="utf-8")
    ok, out = run("tools/chapter.py", "save-research", str(ch["n"]), str(tmp))
    tmp.unlink(missing_ok=True)
    if ok:
        archive_research(ch, raw, "clipboard")
    return {"ok": ok, "output": out, "problems": []}


def archive_research(ch: dict, text: str, via: str, original: Path | None = None) -> None:
    """Keep every imported research reply in the Research Library (never blocks the import itself)."""
    try:
        import research_library as RL  # noqa: PLC0415
        rec = RL.add_text(text, "ai-research", [ch["n"]], f"Research: {ch['title']}",
                          {"assistant": "ChatGPT", "via": via, "chapter": ch["n"]})
        if original is not None and original.exists():
            sha, rel = RL._store_original(original.read_bytes(), ".zip")
            rec.setdefault("origin", {})["zip"] = rel
            RL._save(rec)
    except Exception as e:  # noqa: BLE001
        print(f"Research Library: couldn't archive the research for {ch['n']}: {e}", file=sys.stderr)


def save_reply(ch: dict, raw: str) -> dict:
    tmp = ROOT / "dist" / "web-reply.md"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text(raw, encoding="utf-8")
    before = C.latest_draft(ch)
    ok, out = run("tools/chapter.py", "save", str(ch["n"]), str(tmp))
    tmp.unlink(missing_ok=True)
    saved = C.latest_draft(ch) != before
    issues = M.serious(M.problems(ch, M.body_hashes())) if saved else []
    return {"ok": ok and saved, "output": out, "problems": issues}


def render(path: Path) -> str:
    args = ["pandoc", "-f", "markdown", "-t", "html", "--lua-filter", "assets/filters/callouts.lua"]
    r = subprocess.run(args, input=path.read_text(encoding="utf-8"), cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        r = subprocess.run(args[:5], input=path.read_text(encoding="utf-8"), cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else f"<pre>{r.stderr}</pre>"


def safe_path(p: str) -> Path:
    full = (ROOT / p).resolve()
    if ROOT not in full.parents or not any(full.relative_to(ROOT).as_posix().startswith(a) for a in READABLE):
        raise ValueError("That file is outside the project folders the manager may open.")
    if not full.exists():
        raise ValueError(f"Missing file: {p}")
    return full


# ------------------------------------------------------------------ actions

def step(ch: dict, code: str) -> dict:
    n, st = ch["n"], M.stem(ch)
    if code == "research":
        pack = P.make("research", n=n)
        pbcopy(pack.text())
        return {"ok": True, "copied": True, "pack": pack.summary(), "message": f"Copied the research prompt for {M.name(ch)}.",
                "help": ["In ChatGPT, start a NEW chat (inside your Project if you use one). Turn on web search if it's offered.",
                         "Paste (⌘V) and send.", f"If the chat isn't named “{M.name(ch)}”, rename it.",
                         "When it's done, click the copy button under the reply and save it here as research."]}
    if code == "skipresearch":
        ok, out = run("tools/chapter.py", "skip-research", str(n))
        return {"ok": ok, "message": out}
    if code in ("write", "recopy"):
        pack = P.make("write", n=n)
        pbcopy(pack.text())
        return {"ok": True, "copied": True, "pack": pack.summary(), "message": f"Copied the writing prompt for {M.name(ch)}.",
                "help": [f"In ChatGPT, open the chat “{M.name(ch)}” (the one with the research), or start a NEW chat "
                         "in your project if you skipped research.", "Paste (⌘V) and send.",
                         "When it's done, click the copy button under the reply and come back here."]}
    if code == "claude":
        v = C.latest_draft(ch).name.split("-")[0]
        msg = M.check_message(ch, v)
        pbcopy(msg)
        return {"ok": True, "copied": True, "message": f"Copied “{msg}”",
                "help": ["Paste it into Claude Code.", "When Claude says the check is done, press Refresh."]}
    if code == "revise":
        pack = P.make("revise", n=n)
        pbcopy(pack.text())
        return {"ok": True, "copied": True, "pack": pack.summary(), "message": f"Copied the revision prompt for {M.name(ch)}.",
                "help": [f"Paste it into the chat named “{M.name(ch)}”.",
                         "When it's done, copy the reply and save it here."]}
    if code == "approve":
        ok, out = run("tools/chapter.py", "approve", str(n))
        if ok:
            pbcopy(f"{C.what(ch)[0].upper() + C.what(ch)[1:]} approved. Update continuity and build.")
        return {"ok": ok, "copied": ok, "message": out,
                "help": ["Copied a message for Claude: paste it into Claude Code so it updates the continuity notes."]}
    if code == "advance":
        nxt = M.next_in_order(n)
        M.save_current(nxt)
        nch = find(nxt)
        return {"ok": True, "current": nxt, "message": f"Moved to {C.label(nch)} · {nch['title']}."}
    if code == "claude-text":
        return {"ok": True}
    return {"ok": False, "message": f"Unknown step {code}"}


def project_files() -> dict:
    """Rebuild the ChatGPT Project memory files and show the folder in Finder."""
    ok, out = run("tools/chapter.py", "library")
    sh("open", str(C.PROJECT_OUT))
    files = sorted(p.name for p in C.PROJECT_OUT.glob("*.md"))
    return {"ok": ok, "output": out, "folder": rel(C.PROJECT_OUT), "files": files}


def mark_uploaded() -> dict:
    C.PROJECT_OUT.mkdir(parents=True, exist_ok=True)
    (C.PROJECT_OUT / ".uploaded").write_text("uploaded\n")
    return {"ok": True}


def newest_zip(n: int) -> Path | None:
    """Newest chNN…zip (or front4…zip) in ~/Downloads (ChatGPT may add “ (1)” to repeat downloads)."""
    dl = Path.home() / "Downloads"
    sp = C.special_by_n(n)
    pat = (re.compile(rf"^{sp['key']}[ _-].*\.zip$", re.I) if sp
           else re.compile(rf"^ch[ _-]?0*{n}(?!\d).*\.zip$", re.I))
    found = [p for p in dl.glob("*.zip") if pat.match(p.name)] if dl.exists() else []
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def import_zip(ch: dict, data: dict) -> dict:
    if data.get("downloads"):
        z = newest_zip(ch["n"])
        if not z:
            return {"ok": False, "notFound": True,
                    "output": f"No zip named like {chapter_summary(ch, {})['zip']} in your Downloads folder."}
        src, label = z, f"~/Downloads/{z.name}"
    else:
        import base64
        src = ROOT / "dist" / "web-import.zip"
        src.parent.mkdir(exist_ok=True)
        src.write_bytes(base64.b64decode(data["data"]))
        label = data.get("name", "uploaded zip")
    ok, out = run("tools/chapter.py", "import-research", str(ch["n"]), str(src))
    if ok and C.research_path(ch).exists():
        archive_research(ch, C.research_path(ch).read_text(encoding="utf-8"), "zip", src)
    if src.name == "web-import.zip":
        src.unlink(missing_ok=True)
    return {"ok": ok, "output": out, "file": label}


def build(formats: list[str], audience: str | None, toc: str = "simple", bookmarks: bool = True,
          links: bool = True) -> dict:
    args = ["tools/build.py", "build", *formats, "--toc", "detailed" if toc == "detailed" else "simple"]
    if not bookmarks:
        args.append("--no-bookmarks")
    if not links:
        args.append("--no-toc-links")
    if audience:
        kind, value = audience.split(":", 1)
        args += [f"--only-{kind}", value]
    ok, out = run(*args)
    return {"ok": ok, "output": out}


# ------------------------------------------------------------------ games and website

RUNTIME = Path(__file__).resolve().parent / "web" / "runtime"
PREVIEW_BASE = "/site-preview/"
MIME = {".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
        ".vtt": "text/vtt", ".txt": "text/plain", ".md": "text/plain", ".js": "text/javascript", ".css": "text/css",
        ".html": "text/html", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".ttf": "font/ttf",
        ".pdf": "application/pdf", ".epub": "application/epub+zip", ".docx": "application/octet-stream"}


PACK_DIR = ROOT / "dist" / "prompt-packs"


def prompt_action(p: str, data: dict) -> dict:
    """Prompt packs: copy the self-contained prompt, or also make the optional ZIP of reference files."""
    if p == "kinds":
        return {"kinds": P.kinds()}
    needs = P.KINDS[data["kind"]].needs if data.get("kind") in P.KINDS else "chapter"
    if needs == "none":
        args = {}
    elif needs == "game":
        args = {"game": data["game"]}
    else:
        args = {"n": int(data["n"])} if data.get("n") not in (None, "") else {}
    try:
        pack = P.make(data["kind"], **args)
    except (RuntimeError, SystemExit, G.PackageError) as e:
        return {"ok": False, "message": str(e)}
    pbcopy(pack.text())
    out = {"ok": True, "copied": True, "pack": pack.summary()}
    if p == "zip":
        J.report(0.8, "Packing the ZIP…")
        PACK_DIR.mkdir(parents=True, exist_ok=True)
        for old in PACK_DIR.glob(f"*-{pack.kind}-pack.zip"):
            old.unlink()
        (PACK_DIR / pack.filename).write_bytes(pack.to_zip())
        out["download"] = f"/api/prompts/download/{pack.filename}"
    return out


def workspace_action(p: str, data: dict) -> dict:
    """The ChatGPT Project: settings form, instructions, initial prompt and files."""
    if p == "save":
        W.save(data.get("values") or {})
        return {"ok": True, **W.summary()}
    if p == "reset":
        W.SETTINGS.unlink(missing_ok=True)
        return {"ok": True, **W.summary()}
    if p == "preview":  # live preview of unsaved form values
        values = {**W.load(), **(data.get("values") or {})}
        text = W.instructions(values)
        return {"instructions": text, "initial": W.initial_prompt(values), "chars": len(text), "limit": W.INSTRUCTIONS_LIMIT}
    if p == "instructions":
        text = W.instructions()
        pbcopy(text)
        return {"ok": True, "chars": len(text), "limit": W.INSTRUCTIONS_LIMIT}
    if p == "initial":
        text = W.initial_prompt()
        pbcopy(text)
        return {"ok": True, "words": len(text.split())}
    if p == "files":
        res = W.write_files()
        if data.get("reveal"):
            sh("open", str(W.OUT))
        return {"ok": True, **res}
    if p == "uploaded":
        return mark_uploaded()
    return {"ok": False, "message": f"Unknown workspace action {p}"}


def games_state() -> dict:
    chapters = G.book_chapters()
    reg = G.load_registry()["games"]
    published = {g["id"] for g in G.published_games(chapters)}
    games = []
    for g in sorted(reg.values(), key=lambda g: (g["chapter"], g["id"])):
        games.append({**g, "chapterTitle": chapters.get(g["chapter"], {}).get("title", "?"),
                      "chapterStatus": chapters.get(g["chapter"], {}).get("status", "missing"),
                      "willPublish": g["id"] in published})
    return {"games": games, "apiVersion": G.API_VERSION,
            "chapters": [{"n": n, "title": c["title"], "status": c["status"]} for n, c in sorted(chapters.items())],
            "runtimeReady": (RUNTIME / "game-runtime.js").exists()}


def game_action(p: str, data: dict) -> dict:
    import base64
    try:
        if p == "validate":
            res = G.validate_package(G.read_archive(base64.b64decode(data["data"])))
            m = res.get("manifest") or {}
            return {"ok": res["ok"], "errors": res["errors"], "warnings": res["warnings"],
                    "id": m.get("id"), "title": m.get("title"), "version": m.get("version"), "chapter": m.get("chapter")}
        if p in ("validate-reply", "import-reply"):
            text = pbpaste() if data.get("clipboard") else data.get("text", "")
            if not text.strip():
                return {"ok": False, "message": "Your clipboard is empty. In ChatGPT, click the copy button under its reply first."}
            files = G.parse_reply(text)
            uploads = {path: base64.b64decode(b) for path, b in (data.get("assets") or {}).items()}
            files = G.attach_assets(files, uploads)
            need = G.missing_assets(files)
            slots = G.image_slots(files)
            res = G.validate_package(files)
            m = res.get("manifest") or {}
            missing_paths = {a["path"] for a in need}
            # Errors about images still to be chosen are expected at this point; show the rest.
            errors = [e for e in res["errors"] if not any(path in e for path in missing_paths)]
            info = {"text": text, "needAssets": need, "slots": slots, "errors": errors, "warnings": res["warnings"],
                    "id": m.get("id"), "title": m.get("title"), "version": m.get("version"), "chapter": m.get("chapter")}
            if p == "validate-reply" or need or errors:
                return {"ok": not errors and not need, **info}
            res = G.install(G.zip_files(files), replace=bool(data.get("replace")), source="pasted ChatGPT reply")
            return {"ok": True, "entry": res["entry"], "warnings": res["warnings"], "replaced": res["replaced"]}
        if p == "import":
            res = G.install(base64.b64decode(data["data"]), replace=bool(data.get("replace")), source=data.get("name", ""))
            return {"ok": True, "entry": res["entry"], "warnings": res["warnings"], "replaced": res["replaced"]}
        if p == "status":
            return {"ok": True, "entry": G.set_status(data["id"], data["status"])}
        if p == "assign":
            return {"ok": True, "entry": G.assign(data["id"], int(data["chapter"]))}
        if p == "remove":
            G.remove(data["id"])
            return {"ok": True}
        if p == "export":
            out = G.export(data["id"])
            return {"ok": True, "path": rel(out), "download": f"/api/games/export/{out.name}", "name": out.name}
        if p == "prompt":
            text = G.creation_prompt(int(data["chapter"]) if data.get("chapter") else None)
            pbcopy(text)
            return {"ok": True, "chars": len(text)}
        if p == "docs-zip":
            out = G.docs_zip()
            sh("open", "-R", str(out))
            return {"ok": True, "path": rel(out)}
    except G.PackageError as e:
        return {"ok": False, "message": str(e)}
    return {"ok": False, "message": f"Unknown games action {p}"}


def website_action(p: str, data: dict) -> dict:
    if p == "plan":
        ok, out = run("tools/website.py", "plan")
        return json.loads(out) if ok else {"error": out}
    if p == "preview":
        ok, out = run("tools/website.py", "build", "--preview", "--no-downloads", "--base", PREVIEW_BASE, timeout=900)
        return {"ok": ok, "output": out, "url": PREVIEW_BASE}
    if p == "setup":
        ok, out = run("tools/website.py", "setup", timeout=300)
        return {"ok": ok, "output": out}
    if p == "zip":
        args = ["tools/website.py", "zip", "--base", str(data.get("base") or "/")] + (["--downloads"] if data.get("downloads") else [])
        ok, out = run(*args, timeout=1800)
        try:
            res = json.loads(out[out.index("{"):out.rindex("}") + 1])
        except ValueError:
            return {"ok": False, "output": out}
        return {**res, "ok": ok, "download": f"/api/website-zip?f={res.get('name', '')}"}
    if p in ("setup", "publish"):
        import registry as REG  # noqa: PLC0415
        allowed, why = REG.publishing_enabled(ROOT)
        if not allowed:
            return {"ok": False, "output": why}
    if p == "publish":
        if data.get("confirm") is not True:
            return {"ok": False, "output": "Publishing needs confirmation."}
        ok, out = run("tools/website.py", "publish", "--yes", timeout=1500)
        return {"ok": ok, "output": out}
    if p == "status":
        ok, out = run("tools/website.py", "status", timeout=60)
        return json.loads(out) if ok else {"error": out}
    return {"ok": False, "output": f"Unknown website action {p}"}


def preview_page(gid: str) -> str:
    g = G.get(gid)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Preview: {html_escape(g['title'])}</title><link rel="stylesheet" href="/runtime/game.css">
<style>body{{font-family:system-ui,sans-serif;max-width:50rem;margin:1.5rem auto;padding:0 1rem;background:#F7F6F2;color:#171717}}
.note{{background:#FBF3DE;border-left:4px solid #E3AC19;padding:.6rem 1rem;border-radius:4px}} #log{{font:12px ui-monospace,monospace;max-height:16rem;overflow:auto;background:#fff;border:1px solid #ddd;padding:.5rem 1.8rem}}</style></head>
<body><p class="note"><b>Local preview</b> of <code>{html_escape(gid)}</code> {html_escape(g['version'])}, chapter {g['chapter']}, status <b>{html_escape(g['status'])}</b>. Not published. Approve it in the Book Manager's Games view.</p>
<div id="game"></div><h2 style="font-size:1rem">Lifecycle events</h2><ol id="log"></ol>
<script src="/runtime/game-runtime.js"></script>
<script>BookBuilderGame.mount(document.getElementById("game"), {{ base: "/games/preview/{gid}/", onEvent: e => {{
  const li = document.createElement("li"); li.textContent = e.type + (e.screenId ? " · " + e.screenId : "") + " " + JSON.stringify(e.detail);
  document.getElementById("log").append(li); }} }}).catch(err => {{ document.getElementById("game").textContent = "Couldn't load: " + err.message; }});</script>
</body></html>"""


def html_escape(s: str) -> str:
    import html as _h
    return _h.escape(str(s))


def serve_file(handler, base: Path, relpath: str) -> None:
    target = (base / unquote(relpath)).resolve()
    if not target.is_relative_to(base.resolve()):
        return handler.send({"error": "forbidden"}, 403)
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        return handler.send({"error": "not found"}, 404)
    handler.send(target.read_bytes(), ctype=MIME.get(target.suffix.lower(), "application/octet-stream"))


# ------------------------------------------------------------------ server

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:  # quiet
        pass

    def allowed(self) -> bool:
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        ok_hosts = (f"127.0.0.1:{PORT}", f"localhost:{PORT}")
        return host in ok_hosts and (origin is None or origin.split("//")[-1] in ok_hosts)

    def send(self, data, status: int = 200, ctype: str = "application/json", download: str | None = None) -> None:
        body = data if isinstance(data, bytes) else (json.dumps(data) if ctype == "application/json" else data).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self.allowed():
            return self.send({"error": "forbidden"}, 403)
        u = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self.send(PAGE.read_bytes(), ctype="text/html")
            if u.path.startswith("/api/jobs/"):
                job = J.get(u.path.rsplit("/", 1)[1])
                return self.send(job.to_dict() if job else {"error": "That job has finished and was cleared."}, 200 if job else 404)
            if u.path.startswith("/api/") and (res := routes.handle_get(u.path, qs)) is not None:
                if isinstance(res, dict) and "__download__" in res:       # a route asking to send a file
                    f = Path(res["__download__"])
                    if not f.is_file() or not f.resolve().is_relative_to(ROOT.resolve()):
                        return self.send({"error": "not found"}, 404)
                    return self.send(f.read_bytes(), ctype=MIME.get(f.suffix.lower(), "application/octet-stream"),
                                     download=res.get("name", f.name).replace('"', ""))
                return self.send(res)
            if u.path == "/builder.js":
                return serve_file(self, PAGE.parent, "builder.js")
            if u.path.startswith("/pfile/"):     # images from the open project (covers, assets)
                rp = unquote(u.path[len("/pfile/"):])
                if Path(rp).suffix.lower() not in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
                    return self.send({"error": "forbidden"}, 403)
                return serve_file(self, ROOT, rp)
            if u.path == "/api/ping":
                return self.send({"app": "book-manager"})
            if u.path == "/api/state":
                return self.send(state())
            if u.path == "/api/chapter":
                return self.send(chapter_detail(find(int(qs["n"]))))
            if u.path == "/api/file":
                return self.send({"path": qs["path"], "text": safe_path(qs["path"]).read_text(encoding="utf-8")})
            if u.path == "/api/render":
                return self.send({"path": qs["path"], "html": render(safe_path(qs["path"]))})
            if u.path == "/api/games":
                return self.send(games_state())
            if u.path == "/api/games/docs.md":
                return self.send(G.docs_markdown().encode("utf-8"), ctype="text/markdown",
                                 download=f"book-builder-game-api-{G.API_VERSION}.md")
            if u.path.startswith("/api/prompts/download/"):
                name = unquote(u.path.rsplit("/", 1)[1])
                f = PACK_DIR / name
                if "/" in name or not f.is_file():
                    return self.send({"error": "That ZIP is gone; make it again."}, 404)
                return self.send(f.read_bytes(), ctype="application/zip", download=name)
            if u.path.startswith("/api/games/export/"):
                name = unquote(u.path.rsplit("/", 1)[1])
                f = ROOT / "dist" / "game-exports" / name
                if "/" in name or not f.is_file():
                    return self.send({"error": "Export the game again."}, 404)
                return self.send(f.read_bytes(), ctype="application/zip", download=name)
            if u.path == "/api/workspace":
                return self.send(W.summary())
            if u.path == "/api/workspace/files.zip":
                f = W.OUT.parent / "chatgpt-project-files.zip"
                if not f.is_file():
                    return self.send({"error": "Build the Project files first."}, 404)
                return self.send(f.read_bytes(), ctype="application/zip", download=f.name)
            if u.path == "/api/prompts/kinds":
                return self.send({"kinds": P.kinds()})
            if u.path.startswith("/api/website/"):
                return self.send(website_action(u.path.rsplit("/", 1)[1], {}))
            m = re.match(r"^/games/preview/([a-z0-9-]+)/(.*)$", u.path)
            if m:
                if not m.group(2):
                    return self.send(preview_page(m.group(1)), ctype="text/html")
                return serve_file(self, G.PACKAGES / m.group(1), m.group(2))
            if u.path.startswith("/fonts/") and u.path.endswith(".ttf"):
                return serve_file(self, APP / "assets" / "fonts", u.path[len("/fonts/"):])
            if u.path in ("/icons.svg", "/ICONS-LICENSE.txt"):
                return serve_file(self, PAGE.parent, u.path[1:])
            if u.path.startswith("/brand/"):
                return serve_file(self, ROOT / "assets" / "branding", u.path[len("/brand/"):])
            if u.path.startswith("/runtime/"):
                return serve_file(self, RUNTIME, u.path[len("/runtime/"):])
            if u.path.startswith(PREVIEW_BASE):
                return serve_file(self, ROOT / "site" / "dist", u.path[len(PREVIEW_BASE):])
            if u.path == "/api/clipboard":
                return self.send({"text": pbpaste()})
            if u.path.startswith("/dist/"):
                p = safe_path(u.path[1:])
                types = {".pdf": "application/pdf", ".html": "text/html", ".epub": "application/epub+zip",
                         ".docx": "application/octet-stream"}
                return self.send(p.read_bytes(), ctype=types.get(p.suffix, "application/octet-stream"))
            self.send({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            self.send({"error": str(e)}, 400)

    def do_POST(self) -> None:
        if not self.allowed() or "application/json" not in self.headers.get("Content-Type", ""):
            return self.send({"error": "forbidden"}, 403)
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        p = urlparse(self.path).path
        if p == "/api/open-browser":         # the desktop app's "Open in browser"
            webbrowser.open(f"http://127.0.0.1:{PORT}/")
            return self.send({"ok": True})
        if p == "/api/quit":
            self.send({"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if data.pop("background", False):
            # Run as a job so the page can show a progress bar. Quick actions still answer at once.
            job = J.start(data.pop("jobTitle", None) or p.rsplit("/", 1)[1], lambda: dispatch(p, data))
            if J.wait(job, 0.25):
                return self.send({"error": job.error} if job.error else job.result, 400 if job.error else 200)
            return self.send({"job": job.id})
        try:
            self.send(dispatch(p, data))
        except Exception as e:  # noqa: BLE001
            self.send({"error": str(e)}, 400)


class NotFound(Exception):
    pass


def dispatch(p: str, data: dict) -> dict:
    """Every POST action. Runs in a request thread or as a background job."""
    if (res := routes.handle_post(p, data)) is not None:
        return res
    if p == "/api/book/save":
        return save_book_meta(data)
    if p == "/api/current":
        M.save_current(int(data["n"]))
        return {"ok": True}
    if p == "/api/step":
        return step(find(int(data["n"])), data["code"])
    if p == "/api/preview":
        raw = pbpaste() if data.get("clipboard") else data.get("text", "")
        fn = research_preview if data.get("kind") == "research" else preview
        return {**fn(find(int(data["n"])), raw), "raw": raw}
    if p == "/api/save":
        fn = save_research if data.get("kind") == "research" else save_reply
        return fn(find(int(data["n"])), data["text"])
    if p == "/api/projectfiles":
        return project_files()
    if p == "/api/uploaded":
        return mark_uploaded()
    if p == "/api/import-zip":
        return import_zip(find(int(data["n"])), data)
    if p == "/api/copy":
        text = data.get("text")
        if data.get("path"):
            text = safe_path(data["path"]).read_text(encoding="utf-8")
        pbcopy(text or "")
        return {"ok": True}
    if p == "/api/build":
        return build(data.get("formats", ["pdf"]), data.get("audience"), data.get("toc", "simple"),
                     data.get("bookmarks", True) is not False, data.get("links", True) is not False)
    if p == "/api/open":
        target = safe_path(data["path"])
        platformio.open_path(target, reveal=bool(data.get("reveal")))
        return {"ok": True}
    if p.startswith("/api/workspace/"):
        return workspace_action(p.rsplit("/", 1)[1], data)
    if p.startswith("/api/prompts/"):
        return prompt_action(p.rsplit("/", 1)[1], data)
    if p.startswith("/api/games/"):
        return game_action(p.rsplit("/", 1)[1], data)
    if p.startswith("/api/website/"):
        return website_action(p.rsplit("/", 1)[1], data)
    raise NotFound(p)


# Feature modules (routes.FEATURES) get the webapp helpers they need through routes.ctx, then register.
routes.ctx.port = lambda: PORT
routes.ctx.chapter_summary = chapter_summary
routes.ctx.build_stem = build_stem
routes.ctx.rel = rel
routes.load()


def is_book_manager(port: int) -> bool:
    """True when the server on this port is a Book Manager (not some other local app)."""
    import urllib.request  # noqa: PLC0415
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2) as r:  # noqa: S310
            return json.loads(r.read()).get("app") == "book-manager"
    except (OSError, ValueError):
        return False


def main() -> None:
    global PORT
    if "--port" in sys.argv:
        PORT = int(sys.argv[sys.argv.index("--port") + 1])
    server = None
    for port in range(PORT, PORT + (1 if "--exact-port" in sys.argv else 20)):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            if "--exact-port" in sys.argv:          # restarting on another project: wait for the port
                import time as _t  # noqa: PLC0415
                for _ in range(40):
                    _t.sleep(0.25)
                    try:
                        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
                        break
                    except OSError:
                        continue
                if server:
                    break
            if is_book_manager(port):           # our own copy is already running there: just open it
                url = f"http://127.0.0.1:{port}/"
                print(f"Already running: opening {url}")
                webbrowser.open(url)
                return
            print(f"Port {port} is used by another app; trying {port + 1}.")
    if server is None:
        sys.exit(f"No free port between {PORT} and {PORT + 19}.")
    PORT = server.server_address[1]
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Book Builder running at {url} (project: {ROOT})\nClose this window or press Quit in the page to stop it.")
    if "--no-open" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
