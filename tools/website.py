#!/usr/bin/env python3
"""Build and publish a book's public website (GitHub Pages).

    python tools/website.py plan                 what would be published, with warnings
    python tools/website.py export [--preview]   write approved content into site/ (preview: include games in review)
    python tools/website.py build [--preview] [--no-downloads]
                                                 export, build the static site into site/dist, validate it
    python tools/website.py validate             check site/dist for missing pages, broken links and private files
    python tools/website.py setup                create/configure the public publishing repository (once)
    python tools/website.py publish [--yes]      build, validate, commit and push to the publishing repo, verify deploy
    python tools/website.py status               latest deployment status and URL

Only approved chapters and approved games are exported. The public repository receives only the
generated site (site/dist), never Markdown sources, research, reviews or drafts. Settings live in
website.yml (created by `setup`).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import games as G  # noqa: E402
import jobs as J  # noqa: E402

ROOT = Path(os.environ.get("BOOK_PROJECT") or Path(__file__).resolve().parent.parent).resolve()  # the book project
SITE = ROOT / "site"
GEN = SITE / "src" / "generated"
PUBLIC_GEN = [SITE / "public" / "games", SITE / "public" / "downloads", SITE / "public" / "brand",
              SITE / "public" / "book-media", SITE / "public" / "brand-fonts"]
DIST = SITE / "dist"
CACHE = SITE / ".cache"
CONFIG = ROOT / "website.yml"
PUBLISH_DIR = ROOT / ".publish"
BIB = ROOT / "references.bib"
CSL = ROOT / "assets/csl/apa.csl"
FILTER = ROOT / "assets/filters/callouts.lua"
FONTS = ["PlayfairDisplay.ttf", "PlayfairDisplay-Italic.ttf", "SourceSans3.ttf", "SourceSans3-Italic.ttf",
         "SourceSerif4.ttf", "SourceSerif4-Italic.ttf", "AtkinsonHyperlegibleNext.ttf", "AtkinsonHyperlegibleNext-Italic.ttf"]
DOWNLOAD_FORMATS = ("pdf", "epub", "docx")
PLACEHOLDER = "This chapter will be written through the agent pipeline"

# Never allowed in the published site (checked in `validate`).
FORBIDDEN_NAMES = re.compile(r"\.(md|bib|yml|yaml|py|lua|typ|csl|zip|env|key|pem)$|(^|/)\.(git|env)|registry\.json$", re.I)
FORBIDDEN_TEXT = [PLACEHOLDER, "sources-private", "drafts/", "reviews/", "Claude-written box", "ready to approve"]


# ------------------------------------------------------------------ config

def load_config() -> dict:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    return cfg or {}


def site_paths(cfg: dict) -> tuple[str, str]:
    """(origin, base path) for Astro, from website.yml url. Defaults suit a local preview."""
    url = cfg.get("url") or "http://localhost/"
    u = urlparse(url)
    base = u.path if u.path.endswith("/") else u.path + "/"
    return f"{u.scheme}://{u.netloc}", base


# ------------------------------------------------------------------ book data

def slugify(stem: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", stem.lower()).strip("-")


def load_book() -> dict:
    manifest = yaml.safe_load((ROOT / "book.yml").read_text(encoding="utf-8"))
    entries = []
    for pi, part in enumerate(manifest["parts"]):
        kind = "front" if "00-front" in part["chapters"][0] else "back" if "99-back" in part["chapters"][0] else "chapter"
        for rel in part["chapters"]:
            p = ROOT / rel
            text = p.read_text(encoding="utf-8") if p.exists() else ""
            fm = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.S)
            meta = (yaml.safe_load(fm.group(1)) or {}) if fm else {}
            body = text[fm.end():] if fm else text
            m = re.match(r"^(\d+)-(.*)$", p.stem)
            n = int(m.group(1)) if (m and kind == "chapter") else None
            slug = p.stem if n else slugify(m.group(2) if m else p.stem)
            status = meta.get("status", "planned")
            entries.append({
                "n": n, "slug": slug, "title": meta.get("title", p.stem), "part": part["title"], "partIndex": pi,
                "kind": kind, "status": status, "source": rel, "body": body,
                "published": status == "approved" and PLACEHOLDER not in body,
            })
    return {"metadata": manifest["metadata"], "entries": entries}


MEDIA_WARNINGS: list[str] = []


def pandoc_chapter(entry: dict) -> str:
    """Render one chapter to an HTML fragment (cached by content hash)."""
    src = ROOT / entry["source"]
    reg = ROOT / "images" / "registry.json"           # image approvals change what's published
    key = hashlib.sha256(b"v4" + src.read_bytes() + BIB.read_bytes() + CSL.read_bytes() + FILTER.read_bytes()
                         + (reg.read_bytes() if reg.exists() else b"")).hexdigest()[:24]
    cached = CACHE / f"{entry['slug']}-{key}.html"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    import media  # noqa: PLC0415
    text = src.read_text(encoding="utf-8")
    body, _imgs, warns = media.resolve(text, src, ROOT, published=True)   # only approved images go public
    MEDIA_WARNINGS.extend(warns)
    r = subprocess.run(["pandoc", "-", "--from", "markdown", "--to", "html5", "--wrap=none",
                        "--lua-filter", str(FILTER), "--citeproc", "--bibliography", str(BIB), "--csl", str(CSL),
                        "--metadata", "link-citations=true", "--metadata", "reference-section-title="],
                       input=body, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"pandoc failed for {entry['source']}:\n{r.stderr}")
    CACHE.mkdir(parents=True, exist_ok=True)
    for old in CACHE.glob(f"{entry['slug']}-*.html"):
        old.unlink()
    cached.write_text(r.stdout, encoding="utf-8")
    return r.stdout


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def postprocess(fragment: str) -> tuple[str, list[dict], list[dict], list[str]]:
    """Drop the chapter's own h1, collect the section list, mark references and callouts."""
    out = re.sub(r"\A\s*<h1[^>]*>.*?</h1>\s*", "", fragment, count=1, flags=re.S)
    toc = [{"id": m.group(1), "text": strip_tags(m.group(2))}
           for m in re.finditer(r'<h2 id="([^"]+)"[^>]*>(.*?)</h2>', out, re.S)]
    refs = []
    if 'id="refs"' in out:
        out = out.replace('<div id="refs"', '<h2 id="references">References</h2>\n<div id="refs"', 1)
        toc.append({"id": "references", "text": "References"})
        for m in re.finditer(r'<div id="(ref-[^"]+)" class="csl-entry"[^>]*>(.*?)</div>', out, re.S):
            refs.append({"id": m.group(1), "html": m.group(2).strip()})
    callouts = sorted(set(re.findall(r'class="callout (perspective|neurotype|partner) \1-([a-z-]+)"', out)))
    tags = [f"{k}:{t}" for k, t in callouts]
    # Tables scroll sideways on small screens instead of widening the page.
    out = re.sub(r"(<table.*?</table>)", r'<div class="table-wrap" tabindex="0" role="region" aria-label="Table">\1</div>',
                 out, flags=re.S)
    return out, toc, refs, tags


def export(preview: bool = False, downloads: bool = True, log=print, base_override: str | None = None,
           origin_override: str | None = None) -> dict:
    """Write site/src/generated and site/public generated assets. Returns a summary."""
    cfg = load_config()
    origin, base = site_paths(cfg)
    if base_override:
        origin, base = origin_override or "http://127.0.0.1:8765", base_override
    book = load_book()
    entries = book["entries"]
    chapters_by_n = {e["n"]: {"status": e["status"] if e["published"] else "planned", "title": e["title"],
                              "path": e["source"], "part": e["part"]} for e in entries if e["n"]}

    # Games: approved (or, in preview, also those in review) whose chapter is published.
    if preview:
        reg = G.load_registry()["games"].values()
        game_list = [g for g in reg if g["status"] in ("approved", "review")
                     and chapters_by_n.get(g["chapter"], {}).get("status") == "approved"]
    else:
        game_list = G.published_games(chapters_by_n)

    shutil.rmtree(GEN, ignore_errors=True)
    (GEN / "chapters").mkdir(parents=True)
    for d in PUBLIC_GEN:
        shutil.rmtree(d, ignore_errors=True)

    published = [e for e in entries if e["published"]]
    log(f"Rendering {len(published)} approved chapters…")
    J.report(0.0, f"Rendering {len(published)} approved chapters…")
    rendered = {}
    with cf.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        futures = {ex.submit(pandoc_chapter, e): e["slug"] for e in published}
        for i, f in enumerate(cf.as_completed(futures), 1):
            rendered[futures[f]] = f.result()
            J.report(0.45 * i / max(1, len(published)), f"Rendered {i} of {len(published)} chapters")

    games_out = []
    for g in game_list:
        files = G.installed_files(g["id"])
        res = G.validate_package(files, chapters_by_n)
        if not res["ok"]:
            log(f"  skipped game {g['id']}: no longer valid ({res['errors'][0]})")
            continue
        dest = SITE / "public" / "games" / g["id"]
        allowed = {"game.json", "activity.json"} | {a["path"] for a in res["manifest"]["assets"]}
        for name, content in files.items():
            if name in allowed:
                (dest / name).parent.mkdir(parents=True, exist_ok=True)
                (dest / name).write_bytes(content)
        games_out.append({"manifest": res["manifest"], "activity": res["activity"], "status": g["status"]})
    games_by_chapter: dict[int, list[str]] = {}
    for g in games_out:
        games_by_chapter.setdefault(g["manifest"]["chapter"], []).append(g["manifest"]["id"])

    all_refs: dict[str, dict] = {}
    out_entries = []
    for e in entries:
        item = {k: e[k] for k in ("n", "slug", "title", "part", "partIndex", "kind", "published")}
        item["status"] = "published" if e["published"] else "coming-soon"
        item["games"] = games_by_chapter.get(e["n"], []) if e["published"] else []
        if e["published"]:
            body, toc, refs, tags = postprocess(rendered[e["slug"]])
            words = len(re.sub(r"<[^>]+>", " ", body).split())
            item.update(toc=toc, words=words, minutes=max(1, round(words / 230)), callouts=tags)
            main_html, _, refs_html = body.partition('<h2 id="references">References</h2>')
            import media  # noqa: PLC0415
            main_html, _copied = media.publish(main_html, ROOT, SITE / "public", base)   # approved images only (see pandoc_chapter)
            (GEN / "chapters" / f"{e['slug']}.html").write_text(main_html, encoding="utf-8")
            (GEN / "chapters" / f"{e['slug']}.refs.html").write_text(refs_html, encoding="utf-8")
            if refs_html:
                item["toc"] = [t for t in toc if t["id"] != "references"]
                item["hasRefs"] = True
            for r in refs:
                all_refs.setdefault(r["id"], {**r, "chapters": []})["chapters"].append(e["slug"])
        out_entries.append(item)
    # Skip the back-matter references stub: the site has its own references page.
    out_entries = [e for e in out_entries if not (e["kind"] == "back" and e["slug"] == "references")]

    # Downloads: built from approved chapters only (tools/build.py --published).
    dl = []
    if downloads:
        dl_dir = SITE / "public" / "downloads"
        dl_dir.mkdir(parents=True, exist_ok=True)
        J.report(0.5, "Building the PDF, EPUB and Word downloads…")
        with J.span(0.5, 0.98):
            ok, out = J.run_cmd([sys.executable, str(Path(__file__).resolve().parent / "build.py"), "build", *DOWNLOAD_FORMATS, "--published",
                                 "--outdir", str(dl_dir)], cwd=ROOT, timeout=900)
        if not ok:
            log(f"  downloads not built: {out[-400:]}")
        for fmt in DOWNLOAD_FORMATS:
            f = dl_dir / f"book.{fmt}"
            if f.exists():
                dl.append({"format": fmt, "file": f"downloads/{f.name}", "bytes": f.stat().st_size})

    fonts = GEN / "fonts"  # bundled by Vite from src/styles/global.css
    fonts.mkdir(parents=True, exist_ok=True)
    for f in FONTS:
        shutil.copy2(ROOT / "assets" / "fonts" / f, fonts / f)
    brand = SITE / "public" / "brand"
    brand.mkdir(parents=True, exist_ok=True)
    for f in ("cover.jpg", "logo-black-800.png", "logo-white-800.png"):
        if (ROOT / "assets/branding" / f).exists():
            shutil.copy2(ROOT / "assets/branding" / f, brand / f)

    meta = book["metadata"]
    data = {
        "title": meta.get("title"), "subtitle": meta.get("subtitle"), "author": meta.get("author"),
        "editor": meta.get("editor") or "", "publisher": meta.get("publisher") or "",
        "creditLine": meta.get("credit-line") or "", "aboutAuthors": meta.get("about-authors") or "",
        "aiContributors": list(meta.get("ai-contributors") or []),
        "rights": meta.get("rights"), "origin": origin, "base": base, "preview": preview,
        "repository": cfg.get("repo"), "generatedAt": time.strftime("%Y-%m-%d"),
        "entries": out_entries, "downloads": dl,
    }
    (GEN / "book.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    try:                                   # the book's brand, if it was applied to the website (tools/brand.py)
        import brand as BR  # noqa: PLC0415
        (GEN / "brand.css").write_text(BR.website_css(SITE / "public"), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        (GEN / "brand.css").write_text(f"/* brand not applied: {e} */\n", encoding="utf-8")
    (GEN / "games.json").write_text(json.dumps(games_out, indent=1, ensure_ascii=False), encoding="utf-8")
    refs_sorted = sorted(all_refs.values(), key=lambda r: strip_tags(r["html"]).lower())
    (GEN / "references.json").write_text(json.dumps(refs_sorted, indent=1, ensure_ascii=False), encoding="utf-8")
    guides = build_guides(book["entries"], out_entries)
    (GEN / "guides.json").write_text(json.dumps(guides, indent=1, ensure_ascii=False), encoding="utf-8")
    summary = {"chapters": len(published), "comingSoon": len(out_entries) - len(published),
               "games": [g["manifest"]["id"] for g in games_out], "references": len(refs_sorted),
               "downloads": [d["format"] for d in dl]}
    log(f"Exported {summary['chapters']} chapters, {len(games_out)} games, {summary['references']} references, "
        f"downloads: {', '.join(summary['downloads']) or 'none'}.")
    return summary


# ------------------------------------------------------------------ quick-orientation guides

# Optional, additive navigation for each numbered chapter. Built only from existing approved text:
# glossary entries that point to the chapter (verbatim, as rendered), and the
# chapter's own section headings with their real anchors. Nothing here is newly written prose. (A
# one-line "useful when" sentence per chapter would be new prose, so it's left to the ChatGPT pipeline.)
ACTION_HEADING = re.compile(r"^(how|what to|what you can|if |when |try|getting|asking|saying|steps|practical|"
                            r"where|finding|making|planning|questions|scripts?|a simple|putting|before|after|"
                            r"help|safety|what helps)", re.I)


def glossary_entries() -> list[dict]:
    path = ROOT / "book/99-back/glossary.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    fm = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not fm or (yaml.safe_load(fm.group(1)) or {}).get("status") != "approved":
        return []
    out = []
    for m in re.finditer(r"^([^\n:#][^\n]*)\n:\s+(.+?)(?=\n\n|\Z)", text[fm.end():], re.M | re.S):
        definition = " ".join(m.group(2).split())
        see = re.search(r"See chapters? ([\d, and]+)\.\s*$", definition)
        chapters = [int(x) for x in re.findall(r"\d+", see.group(1))] if see else []
        out.append({"term": m.group(1).strip(), "definition": definition, "chapters": chapters})
    # Render with Pandoc (as the glossary page is), so quotes and dashes match the glossary exactly.
    sep = "\n\nGLOSSARYSPLIT\n\n"
    r = subprocess.run(["pandoc", "-f", "markdown", "-t", "plain", "--wrap=none"],
                       input=sep.join(e["term"] + "\n\n" + e["definition"] for e in out),
                       capture_output=True, text=True, check=True)
    for e, rendered in zip(out, r.stdout.split("GLOSSARYSPLIT")):
        term, _, definition = rendered.strip().partition("\n\n")
        e["term"], e["definition"] = term.strip(), " ".join(definition.split())
    return out


def build_guides(entries: list[dict], out_entries: list[dict]) -> list[dict]:
    gloss = glossary_entries()
    published = {e["n"]: e for e in out_entries if e.get("n") and e["published"]}
    guides = []
    for n, e in sorted(published.items()):
        toc = [h for h in (e.get("toc") or []) if h["id"] != "references"]
        picks = [h for h in toc if ACTION_HEADING.search(h["text"])][:6]
        for h in toc:  # top up with the chapter's own order, never more than six
            if len(picks) >= 3 or h in picks:
                continue
            picks.append(h)
        picks = sorted(picks[:6], key=toc.index)
        terms = [g for g in gloss if n in g["chapters"]]
        # Prefer terms that point only to this chapter (most specific), keep glossary order.
        terms = sorted(terms, key=lambda g: (len(g["chapters"]), gloss.index(g)))[:3]
        related = []
        for g in terms:
            for m in g["chapters"]:
                if m != n and m in published and m not in related:
                    related.append(m)
        guides.append({
            "n": n, "slug": e["slug"], "title": e["title"],
            "terms": [{"term": g["term"], "definition": g["definition"]} for g in sorted(terms, key=gloss.index)],
            "sections": picks,
            "related": [{"n": m, "slug": published[m]["slug"], "title": published[m]["title"]} for m in related[:3]],
            "sensitive": n in SENSITIVE_CHAPTERS,
        })
    return guides


# Chapters where guides must stay navigational only (headings and glossary terms).
SENSITIVE_CHAPTERS = {32, 33, 34, 35, 36, 47, 48, 54, 55, 57, 58, 59, 60}


# ------------------------------------------------------------------ plan, build, validate

def plan() -> dict:
    book = load_book()
    chapters_by_n = {e["n"]: {"status": e["status"] if e["published"] else "planned", "title": e["title"],
                              "path": e["source"], "part": e["part"]} for e in book["entries"] if e["n"]}
    reg = G.load_registry()["games"]
    publish_games = G.published_games(chapters_by_n)
    warnings = []
    for e in book["entries"]:
        if e["status"] == "approved" and not e["published"]:
            warnings.append(f"{e['source']} is marked approved but still has placeholder text; it stays Coming Soon.")
    for g in reg.values():
        if g["id"] in {x["id"] for x in publish_games}:
            continue
        reason = ("not approved yet" if g["status"] != "approved" else
                  "its chapter isn't published" if chapters_by_n.get(g["chapter"], {}).get("status") != "approved" else
                  "files changed since approval (re-import)")
        warnings.append(f"Game {g['id']} won't be published: {reason}.")
    cfg = load_config()
    if not cfg.get("repo"):
        warnings.append("No publishing repository configured yet: run Setup (tools/website.py setup).")
    if "TODO" in str(book["metadata"].get("author", "")):
        warnings.append("book.yml author is still a TODO.")
    return {
        "chapters": [{"n": e["n"], "title": e["title"], "slug": e["slug"]} for e in book["entries"] if e["published"]],
        "comingSoon": [{"n": e["n"], "title": e["title"], "status": e["status"]} for e in book["entries"] if not e["published"]
                       and not (e["kind"] == "back" and e["status"] == "generated")],
        "games": [{"id": g["id"], "title": g["title"], "chapter": g["chapter"], "version": g["version"]} for g in publish_games],
        "warnings": warnings, "repo": cfg.get("repo"), "url": cfg.get("url"),
    }


def npm(*args: str, env: dict | None = None, log=print) -> None:
    if not (SITE / "node_modules").exists():
        log("Installing website dependencies (npm ci)…")
        subprocess.run(["npm", "ci"], cwd=SITE, check=True, capture_output=True)
    r = subprocess.run(["npm", *args], cwd=SITE, capture_output=True, text=True, env={**os.environ, **(env or {})})
    if r.returncode != 0:
        raise RuntimeError(f"npm {' '.join(args)} failed:\n{(r.stdout + r.stderr)[-3000:]}")


def build(preview: bool = False, downloads: bool = True, log=print, base_override: str | None = None,
          origin_override: str | None = None) -> dict:
    with J.span(0.0, 0.6 if downloads else 0.35):
        summary = export(preview=preview, downloads=downloads, log=log, base_override=base_override,
                         origin_override=origin_override)
    origin, base = site_paths(load_config())
    if base_override:
        origin, base = origin_override or "http://127.0.0.1:8765", base_override
    log("Building the static site (Astro + Pagefind)…")
    with J.creep(0.6 if downloads else 0.35, 0.95, 45, "Building the static site (Astro + Pagefind)…"):
        npm("run", "build", env={"SITE_ORIGIN": origin, "SITE_BASE": base}, log=log)
    J.report(0.95, "Checking the website output…")
    problems = validate(log=log)
    if problems:
        raise RuntimeError("Website validation failed:\n- " + "\n- ".join(problems[:30]))
    return summary


def validate(log=print) -> list[str]:
    """Check site/dist: expected pages exist, internal links resolve, nothing private is included."""
    problems: list[str] = []
    if not (DIST / "index.html").exists():
        return ["site/dist/index.html is missing: build first."]
    data = json.loads((GEN / "book.json").read_text(encoding="utf-8"))
    games = json.loads((GEN / "games.json").read_text(encoding="utf-8"))
    base = data["base"]
    for e in data["entries"]:
        page = DIST / "read" / e["slug"] / "index.html"
        if not page.exists():
            problems.append(f"Missing chapter page /read/{e['slug']}/")
            continue
        text = page.read_text(encoding="utf-8")
        if e["published"] and "data-pagefind-body" not in text:
            problems.append(f"/read/{e['slug']}/ isn't marked for search.")
        if not e["published"] and ("data-pagefind-body" in text or 'class="chapter-body' in text):
            problems.append(f"Unpublished chapter /read/{e['slug']}/ exposes content.")
    for g in games:
        gid = g["manifest"]["id"]
        if not (DIST / "activities" / gid / "index.html").exists():
            problems.append(f"Missing activity page /activities/{gid}/")
        if not (DIST / "games" / gid / "activity.json").exists():
            problems.append(f"Missing game data for {gid}")
    guides_path = GEN / "guides.json"
    if guides_path.exists():
        glossary_page = DIST / "read" / "glossary" / "index.html"
        glossary_text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", glossary_page.read_text(encoding="utf-8"))).split()) \
            if glossary_page.exists() else ""
        for g in json.loads(guides_path.read_text(encoding="utf-8")):
            page = DIST / "guides" / g["slug"] / "index.html"
            chapter = DIST / "read" / g["slug"] / "index.html"
            if not page.exists():
                problems.append(f"Missing guide page /guides/{g['slug']}/")
                continue
            ids = set(re.findall(r'id="([^"]+)"', chapter.read_text(encoding="utf-8"))) if chapter.exists() else set()
            for s in g["sections"]:
                if s["id"] not in ids:
                    problems.append(f"Guide {g['slug']}: heading anchor #{s['id']} not found in the chapter page")
            for term in g["terms"]:
                plain = " ".join(re.sub(r"[*_`]", "", term["definition"]).split())
                if plain not in glossary_text:
                    problems.append(f"Guide {g['slug']}: definition of {term['term']!r} doesn't match the glossary")
    # Activities is in the main navigation exactly when at least one activity is published.
    nav_re = re.compile(r'<nav aria-label="Main".*?</nav>', re.S)
    for p in DIST.rglob("*.html"):
        navs = nav_re.findall(p.read_text(encoding="utf-8", errors="ignore"))
        has = any(f'href="{base}activities/"' in n for n in navs)
        if navs and has != bool(games):
            problems.append(f"{p.relative_to(DIST)}: Activities is {'in' if has else 'missing from'} the main "
                            f"navigation with {len(games)} published activities")
    if not (DIST / "pagefind" / "pagefind.js").exists():
        problems.append("Search index (pagefind) is missing.")
    published_ids = {g["manifest"]["id"] for g in games}
    if (DIST / "games").exists():
        for d in (DIST / "games").iterdir():
            if d.name not in published_ids:
                problems.append(f"Unexpected game folder in output: games/{d.name}")

    files = [p for p in DIST.rglob("*") if p.is_file()]
    for p in files:
        rel = p.relative_to(DIST).as_posix()
        if FORBIDDEN_NAMES.search(rel):
            problems.append(f"Private or source file in output: {rel}")
        if p.suffix in (".html", ".json", ".js") and p.stat().st_size < 5_000_000:
            text = p.read_text(encoding="utf-8", errors="ignore")
            for bad in FORBIDDEN_TEXT:
                if bad in text and not rel.startswith("pagefind/"):
                    problems.append(f"{rel} contains {bad!r}")
    # Internal links and assets must resolve under the base path (GitHub Pages project sites).
    link_re = re.compile(r'(?:href|src)="([^"#?]+)[^"]*"')
    for p in DIST.rglob("*.html"):
        for url in set(link_re.findall(p.read_text(encoding="utf-8", errors="ignore"))):
            if url.startswith(("http:", "https:", "mailto:", "tel:", "data:", "//")):
                continue
            if not url.startswith(base):
                if url.startswith("/"):
                    problems.append(f"{p.relative_to(DIST)}: link {url} ignores the base path {base}")
                continue
            target = DIST / unquote(url[len(base):])
            if not (target.exists() or (target / "index.html").exists()):
                problems.append(f"{p.relative_to(DIST)}: broken link {url}")
    log("Website output is valid." if not problems else f"{len(problems)} problem(s) in the website output.")
    return sorted(set(problems))


# ------------------------------------------------------------------ git publishing

def gh(*args: str, check: bool = True) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}… failed: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def git(*args: str, cwd: Path = PUBLISH_DIR, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


WORKFLOW = """# Deploys the generated book website to GitHub Pages.
# This repository only holds generated files; they are published by the local book builder.
name: Deploy to GitHub Pages
on:
  push:
    branches: [BRANCH]
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: false
jobs:
  # Two jobs (GitHub's standard layout): deploy starts only after the upload is fully registered,
  # which avoids "No artifacts named github-pages were found" races.
  upload:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check the site is complete
        run: test -f site/index.html && test -f site/pagefind/pagefind.js
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
  deploy:
    needs: upload
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
"""

PUBLIC_README = """# {title}

The published website for *{title}: {subtitle}*.

**Read it at {url}**

This repository holds only the generated website. It is built and published by the book's local
builder; please don't edit these files by hand. Licensed {license}.
"""


def setup(name: str | None = None, log=print) -> dict:
    """Create (if needed) the public publishing repo, enable Pages via Actions, write website.yml."""
    cfg = load_config()
    owner = gh("api", "user", "--jq", ".login")
    repo = cfg.get("repo") or f"{owner}/{name or 'book-site'}"
    exists = subprocess.run(["gh", "repo", "view", repo, "--json", "visibility", "--jq", ".visibility"],
                            capture_output=True, text=True)
    if exists.returncode != 0:
        log(f"Creating public repository {repo}…")
        gh("repo", "create", repo, "--public", "--description",
           f"{load_book()['metadata'].get('title', 'Book')} (published website)")
    elif exists.stdout.strip() != "PUBLIC":
        raise RuntimeError(f"{repo} exists but is {exists.stdout.strip().lower()}. Pages on a free plan needs a public repo.")
    pages = subprocess.run(["gh", "api", f"repos/{repo}/pages"], capture_output=True, text=True)
    if pages.returncode != 0:
        log("Enabling GitHub Pages (deploy from GitHub Actions)…")
        gh("api", "-X", "POST", f"repos/{repo}/pages", "-f", "build_type=workflow")
    else:
        info = json.loads(pages.stdout)
        if info.get("build_type") != "workflow":
            gh("api", "-X", "PUT", f"repos/{repo}/pages", "-f", "build_type=workflow")
    info = json.loads(gh("api", f"repos/{repo}/pages"))
    url = info.get("html_url") or f"https://{owner}.github.io/{repo.split('/')[1]}/"
    cfg.update(repo=repo, branch=cfg.get("branch", "main"), url=url)
    CONFIG.write_text("# Public website publishing (tools/website.py). The source repo stays private;\n"
                      "# only the generated site is pushed to `repo`, which GitHub Pages serves at `url`.\n"
                      + yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    log(f"Publishing to {repo}; site URL {url}")
    return cfg


def prepare_checkout(cfg: dict, log=print) -> None:
    repo, branch = cfg["repo"], cfg.get("branch", "main")
    remote = f"https://github.com/{repo}.git"
    if not (PUBLISH_DIR / ".git").exists():
        shutil.rmtree(PUBLISH_DIR, ignore_errors=True)
        log(f"Cloning {repo}…")
        r = subprocess.run(["gh", "repo", "clone", repo, str(PUBLISH_DIR)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Couldn't clone {repo}: {r.stderr.strip()}")
    if git("remote", "get-url", "origin") .rstrip("/").removesuffix(".git") != remote.removesuffix(".git"):
        git("remote", "set-url", "origin", remote)
    # Recover from any earlier failed publish: discard local changes and match the remote.
    git("fetch", "origin", check=False)
    has_remote_branch = git("ls-remote", "--heads", "origin", branch) != ""
    if has_remote_branch:
        git("checkout", "-B", branch, f"origin/{branch}")
        git("reset", "--hard", f"origin/{branch}")
    else:
        git("checkout", "--orphan", branch, check=False)
        git("reset", "--hard", check=False)
    git("clean", "-fdx")


def publish(yes: bool = False, log=print, wait: bool = True) -> dict:
    cfg = load_config()
    if not cfg.get("repo"):
        cfg = setup(log=log)
    p = plan()
    log(f"Will publish {len(p['chapters'])} chapters and {len(p['games'])} games to {cfg['repo']}.")
    for w in p["warnings"]:
        log(f"  warning: {w}")
    if not yes:
        raise RuntimeError("Not confirmed. Re-run with --yes (the Book Manager asks you first).")
    J.report(0.02, "Building the website…")
    with J.span(0.03, 0.6):
        summary = build(preview=False, log=log)
    J.report(0.62, "Preparing the publishing copy…")
    prepare_checkout(cfg, log=log)
    target = PUBLISH_DIR / "site"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(DIST, target)
    (target / ".nojekyll").write_text("")
    import hosting as HO  # noqa: PLC0415
    if (domain := HO.cname_for_publish()):            # custom domain for GitHub Pages
        (target / "CNAME").write_text(domain + "\n")
    wf = PUBLISH_DIR / ".github" / "workflows" / "deploy.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(WORKFLOW.replace("BRANCH", cfg.get("branch", "main")), encoding="utf-8")
    meta = load_book()["metadata"]
    (PUBLISH_DIR / "README.md").write_text(PUBLIC_README.format(
        title=meta["title"], subtitle=meta["subtitle"].lower(), url=cfg["url"], license="CC BY-NC-ND 4.0"),
        encoding="utf-8")
    # Final guard: nothing but the generated site, the workflow and the README.
    for item in PUBLISH_DIR.iterdir():
        if item.name not in {".git", ".github", "site", "README.md"}:
            raise RuntimeError(f"Unexpected file in publishing checkout: {item.name}")
    git("add", "-A")
    if not git("status", "--porcelain"):
        log("Nothing changed since the last publish.")
        commit = git("rev-parse", "--short", "HEAD", check=False)
    else:
        msg = f"Publish website: {summary['chapters']} chapters, {len(summary['games'])} games"
        git("-c", "user.name=Book Builder", "-c", "user.email=builder@users.noreply.github.com",
            "commit", "-q", "-m", msg)
        commit = git("rev-parse", "--short", "HEAD")
        log(f"Committed {commit}: {msg}")
        J.report(0.66, "Pushing to GitHub…")
        branch = cfg.get("branch", "main")
        r = subprocess.run(["git", "push", "origin", f"HEAD:{branch}"], cwd=PUBLISH_DIR, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Push failed (nothing was published; run Publish again to retry):\n{r.stderr.strip()}")
        log("Pushed. GitHub Actions is deploying…")
        J.report(0.7, "Pushed. GitHub is deploying the site…")
    result = {"commit": commit, "url": cfg["url"], "repo": cfg["repo"], **summary}
    if wait:
        with J.span(0.7, 1.0):
            result["deploy"] = wait_for_deploy(cfg, commit, log=log)
    return result


def deploy_status(cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    if not cfg.get("repo"):
        return {"configured": False}
    runs = json.loads(gh("run", "list", "--repo", cfg["repo"], "--workflow", "deploy.yml", "--limit", "1",
                         "--json", "status,conclusion,headSha,url,createdAt", check=False) or "[]")
    run = runs[0] if runs else {}
    return {"configured": True, "repo": cfg["repo"], "url": cfg.get("url"), "run": run}


def wait_for_deploy(cfg: dict, commit: str, log=print, timeout: int = 420) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        st = deploy_status(cfg)
        run = st.get("run") or {}
        if run.get("headSha", "").startswith(commit) and run.get("status") == "completed":
            ok = run.get("conclusion") == "success"
            log(f"Deployment {'succeeded' if ok else 'FAILED'}: {run.get('url')}")
            if ok:
                live = check_live(cfg["url"])
                log(f"Live site check: {'OK' if live else 'not reachable yet (GitHub can take a minute)'}")
                return {"ok": True, "live": live, "run": run}
            return {"ok": False, "run": run}
        # GitHub usually takes 1–3 minutes; move the bar on a curve that slows down instead of guessing.
        waited = time.time() - start
        J.report(waited / (waited + 90), f"GitHub is deploying… ({int(waited)} s)")
        time.sleep(10)
    log("Still deploying; check again with Status in a minute.")
    return {"ok": None, "pending": True}


def check_live(url: str) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.status == 200 and b"<html" in r.read().lower()
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------ cli

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    s = sub.add_parser("export"); s.add_argument("--preview", action="store_true"); s.add_argument("--no-downloads", action="store_true")
    s = sub.add_parser("build"); s.add_argument("--preview", action="store_true"); s.add_argument("--no-downloads", action="store_true")
    s.add_argument("--base", help="base path for a local preview build, e.g. /site-preview/")
    sub.add_parser("validate")
    s = sub.add_parser("zip", help="portable website ZIP with a hosting guide")
    s.add_argument("--base", default=None, help="path the site will live at, e.g. / or /books/my-book/")
    s.add_argument("--downloads", action="store_true", help="also build the PDF/EPUB downloads (slower)")
    s = sub.add_parser("setup"); s.add_argument("--name")
    s = sub.add_parser("publish"); s.add_argument("--yes", action="store_true"); s.add_argument("--no-wait", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args()
    try:
        if a.cmd == "plan":
            print(json.dumps(plan(), indent=2))
        elif a.cmd == "export":
            export(preview=a.preview, downloads=not a.no_downloads)
        elif a.cmd == "build":
            build(preview=a.preview, downloads=not a.no_downloads, base_override=a.base)
        elif a.cmd == "zip":
            import hosting as HO  # noqa: PLC0415
            print(json.dumps(HO.make_zip(a.base or HO.settings()["zip_base"], a.downloads), indent=2))
        elif a.cmd == "validate":
            problems = validate()
            for p in problems:
                print(f"  {p}")
            sys.exit(1 if problems else 0)
        elif a.cmd == "setup":
            setup(a.name)
        elif a.cmd == "publish":
            print(json.dumps(publish(yes=a.yes, wait=not a.no_wait), indent=2))
        elif a.cmd == "status":
            print(json.dumps(deploy_status(), indent=2))
    except (RuntimeError, G.PackageError, subprocess.CalledProcessError) as e:
        sys.exit(f"✗ {e}")


if __name__ == "__main__":
    main()
