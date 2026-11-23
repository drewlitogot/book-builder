"""Read-only facts about the open book project for Book Builder's dashboards.

Everything here is derived from files that already exist (book.yml, chapters, references.bib,
assets, build outputs, git history). Nothing is written, and a check that hasn't been run is
reported as "unchecked", never as passed.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import yaml

import chapter as C
import registry as R

ROOT = C.ROOT
WORDS_PER_MINUTE = 238          # average adult silent reading speed for nonfiction
CHECK_FILE = ROOT / "dist" / ".book-builder-check.json"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
FORMATS = {".pdf": "PDF", ".epub": "EPUB", ".docx": "DOCX", ".html": "HTML"}


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def manifest_files() -> list[Path]:
    man = R.manifest(ROOT)
    return [ROOT / f for part in man.get("parts") or [] for f in part.get("chapters") or []]


def chapter_texts() -> dict[str, str]:
    out = {}
    for p in manifest_files():
        if p.exists():
            out[rel(p)] = p.read_text(encoding="utf-8")
    return out


# ------------------------------------------------------------------ build outputs

def pdf_pages(path: Path) -> int | None:
    if not shutil.which("pdfinfo"):
        return None
    try:
        r = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=20)
        m = re.search(r"^Pages:\s+(\d+)", r.stdout, re.M)
        return int(m.group(1)) if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def outputs(stem: str) -> list[dict]:
    dist = ROOT / "dist"
    if not dist.exists():
        return []
    files, changed = [], latest_source_change()
    try:
        built = json.loads((dist / "build-manifest.json").read_text(encoding="utf-8")).get("artifacts", {})
    except (OSError, ValueError):
        built = {}
    for p in dist.glob("*.*"):
        if p.suffix not in FORMATS:
            continue
        st = p.stat()
        files.append({"path": rel(p), "name": p.name, "format": FORMATS[p.suffix], "bytes": st.st_size,
                      "mtime": st.st_mtime, "current": p.name.startswith(stem),
                      "stale": st.st_mtime < changed,
                      "sha256": (built.get(p.name) or {}).get("sha256"), "preflight": (built.get(p.name) or {}).get("preflight")})
    return sorted(files, key=lambda f: -f["mtime"])


def latest_source_change() -> float:
    return max((p.stat().st_mtime for p in manifest_files() if p.exists()), default=0.0)


# ------------------------------------------------------------------ research and evidence

BIB_ENTRY = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)\n\}", re.S)
BIB_FIELD = re.compile(r"(\w+)\s*=\s*[{\"](.*?)[}\"]\s*,?\s*$", re.M)


def bibliography() -> dict:
    path = ROOT / "references.bib"
    if not path.exists():
        return {"exists": False, "entries": [], "duplicates": [], "incomplete": []}
    text = path.read_text(encoding="utf-8")
    entries, seen, dups = [], set(), []
    for m in BIB_ENTRY.finditer(text):
        kind, key, body = m.group(1).lower(), m.group(2), m.group(3)
        if kind in ("comment", "string", "preamble"):
            continue
        fields = {k.lower(): re.sub(r"[{}]", "", v).strip() for k, v in BIB_FIELD.findall(body)}
        if key in seen:
            dups.append(key)
        seen.add(key)
        entries.append({"key": key, "type": kind, "title": fields.get("title", ""),
                        "author": fields.get("author", "") or fields.get("editor", ""),
                        "year": fields.get("year", "") or fields.get("date", "")[:4],
                        "doi": fields.get("doi", ""), "url": fields.get("url", ""), "file": fields.get("file", "")})
    incomplete = [e["key"] for e in entries if not e["title"] or not e["year"]]
    return {"exists": True, "entries": entries, "duplicates": dups, "incomplete": incomplete}


CITE = re.compile(r"(?<![\w.])@([A-Za-z][\w:-]*\w)")


def citations(texts: dict[str, str], where: str = "text") -> dict[str, set[str]]:
    """Citation keys per chapter: [@key] citations in the text, or the front-matter `sources:` list."""
    out = {}
    for path, t in texts.items():
        keys, meta_keys = set(), set()
        m = re.match(r"\A---\s*\n(.*?)\n---", t, re.S)
        if m:
            try:
                meta = yaml.safe_load(m.group(1)) or {}
                meta_keys = {str(k) for k in meta.get("sources") or []}
            except yaml.YAMLError:
                pass
        body = t[m.end():] if m else t
        for block in re.findall(r"\[[^\]]*@[^\]]*\]", body):
            keys |= set(CITE.findall(block))
        out[path] = keys if where == "text" else meta_keys
    return out


def gaps(texts: dict[str, str]) -> list[dict]:
    found = []
    for path, t in texts.items():
        for i, line in enumerate(t.splitlines(), 1):
            if "[NEEDS SOURCE" in line.upper():
                found.append({"path": path, "line": i, "text": line.strip()[:200]})
    return found


def folder_listing(name: str, limit: int = 200) -> dict:
    d = ROOT / name
    if not d.exists():
        return {"exists": False, "count": 0, "files": []}
    files = sorted((p for p in d.rglob("*") if p.is_file() and not p.name.startswith(".")), key=lambda p: -p.stat().st_mtime)
    return {"exists": True, "count": len(files),
            "files": [{"path": rel(p), "bytes": p.stat().st_size, "mtime": p.stat().st_mtime} for p in files[:limit]]}


def research() -> dict:
    texts = chapter_texts()
    bib = bibliography()
    cites = citations(texts)
    keys = {e["key"] for e in bib["entries"]}
    used = set().union(*cites.values()) if cites else set()
    missing = sorted(k for k in used if k not in keys) if bib["exists"] else []
    missing_by = {p: sorted(k for k in ks if k not in keys) for p, ks in cites.items() if bib["exists"] and ks - keys}
    meta = citations(texts, "meta")
    meta_missing = {p: sorted(k for k in ks if k not in keys) for p, ks in meta.items() if bib["exists"] and ks - keys}
    file_missing = [e["key"] for e in bib["entries"] if e["file"] and not (ROOT / e["file"]).exists()]
    needed = ROOT / "research/08-sources-needed.md"
    open_items = 0
    if needed.exists():
        open_items = len(re.findall(r"^\s*- \[ \]", needed.read_text(encoding="utf-8"), re.M))
    return {"bib": bib, "used": len(used), "unused": sorted(keys - used) if bib["exists"] else [],
            "missingKeys": missing, "missingBy": missing_by, "metaMissing": meta_missing, "fileMissing": file_missing,
            "gaps": gaps(texts), "sources": folder_listing("sources"), "inbox": folder_listing("sources-inbox"),
            "private": {"exists": (ROOT / "sources-private").exists(),
                        "count": sum(1 for p in (ROOT / "sources-private").rglob("*") if p.is_file())
                        if (ROOT / "sources-private").exists() else 0},
            "neededDoc": rel(needed) if needed.exists() else None, "neededOpen": open_items}


# ------------------------------------------------------------------ graphics and design

IMG = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)(\{[^}]*\})?")


def images(texts: dict[str, str]) -> list[dict]:
    out = []
    for path, t in texts.items():
        for m in IMG.finditer(t):
            src = m.group(2)
            if re.match(r"^[a-z]+://", src):
                exists = None
            else:
                cand = [(ROOT / path).parent / src, ROOT / src, ROOT / "book" / src]
                exists = any(c.exists() for c in cand)
            alt = m.group(1).strip()
            attrs = m.group(3) or ""
            if not alt and (a := re.search(r'alt="([^"]*)"', attrs)):
                alt = a.group(1).strip()
            out.append({"chapter": path, "src": src, "alt": alt, "exists": exists})
    return out


def assets() -> dict:
    texts = chapter_texts()
    used = images(texts)
    groups = {"cover": [], "back": [], "spine": [], "logo": [], "illustrations": [], "other": []}
    adir = ROOT / "assets"
    for p in sorted(adir.rglob("*")) if adir.exists() else []:
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXT or "/fonts/" in p.as_posix():
            continue
        n = p.name.lower()
        key = ("back" if "back" in n else "spine" if "spine" in n else "cover" if "cover" in n
               else "logo" if ("logo" in n or "wordmark" in n) else "illustrations" if "illustr" in p.as_posix() else "other")
        groups[key].append({"path": rel(p), "bytes": p.stat().st_size})
    credits = next((ROOT / c for c in ("assets/credits.yml", "assets/CREDITS.md", "assets/branding/credits.yml")
                    if (ROOT / c).exists()), None)
    return {"groups": groups, "used": used, "brokenRefs": [u for u in used if u["exists"] is False],
            "noAlt": [u for u in used if not u["alt"]], "credits": rel(credits) if credits else None,
            "cover": R.cover_of(ROOT)}


def typst_brand() -> dict:
    p = ROOT / "assets/typst/callouts.typ"
    if not p.exists():
        return {"exists": False, "fonts": {}, "colors": {}}
    t = p.read_text(encoding="utf-8")
    fonts = dict(re.findall(r'^#let ([a-z]+)-font = "([^"]+)"', t, re.M))
    colors = dict(re.findall(r'^#let ([a-z-]+) = rgb\("(#[0-9A-Fa-f]{6})"\)', t, re.M))
    return {"exists": True, "path": rel(p), "fonts": fonts, "colors": colors}


def set_typst_brand(fonts: dict | None = None, colors: dict | None = None) -> dict:
    """Change font names or colors in the PDF template, one `#let` line at a time."""
    p = ROOT / "assets/typst/callouts.typ"
    if not p.exists():
        return {"ok": False, "message": "This project has no PDF template (assets/typst/callouts.typ)."}
    t = p.read_text(encoding="utf-8")
    changed = []
    for role, name in (fonts or {}).items():
        if not re.fullmatch(r"[A-Za-z0-9 ]{2,60}", name or ""):
            return {"ok": False, "message": f"“{name}” isn't a valid font name."}
        t, k = re.subn(rf'^(#let {re.escape(role)}-font = )"[^"]+"', rf'\1"{name}"', t, count=1, flags=re.M)
        changed += [f"{role} font"] * k
    for name, hexv in (colors or {}).items():
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", hexv or ""):
            return {"ok": False, "message": f"“{hexv}” isn't a color like #1A2B3C."}
        t, k = re.subn(rf'^(#let {re.escape(name)} = rgb\(")#[0-9A-Fa-f]{{6}}("\))', rf"\g<1>{hexv.upper()}\g<2>", t,
                       count=1, flags=re.M)
        changed += [name] * k
    if not changed:
        return {"ok": True, "message": "Nothing changed.", "brand": typst_brand()}
    p.write_text(t, encoding="utf-8")
    return {"ok": True, "message": f"Updated {', '.join(changed)} in {rel(p)}. Rebuild to see it.", "brand": typst_brand()}


def installed_fonts() -> list[str]:
    d = ROOT / "assets/fonts"
    names = set()
    for p in d.glob("*.[ot]tf") if d.exists() else []:
        base = re.sub(r"(\[.*\]|-(Regular|Italic|Bold.*|Variable.*|VariableFont.*))$", "", p.stem)
        names.add(re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", base).replace("  ", " ").strip())
    return sorted(names)


# ------------------------------------------------------------------ activity (real events only)

def git(*args: str, timeout: int = 10) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def activity(limit: int = 40) -> dict:
    commits = []
    raw = git("log", f"-n{limit}", "--format=%x1e%h%x1f%ct%x1f%s", "--name-only")
    for block in raw.split("\x1e")[1:]:
        head, *files = block.strip().split("\n")
        h, t, s = head.split("\x1f")
        files = [f for f in files if f]
        kinds = sorted({("chapters" if f.startswith("book/") else "drafts" if f.startswith(("drafts/", "reviews/"))
                         else "games" if f.startswith("games/") else "assets" if f.startswith("assets/")
                         else "website" if f.startswith(("site/", "website.yml")) else "tools" if f.startswith("tools/")
                         else "other") for f in files})
        commits.append({"hash": h, "time": float(t), "subject": s, "files": len(files), "kinds": kinds})
    approvals = []
    raw = git("log", "-n15", "-G^status: approved", "--format=%x1e%h%x1f%ct%x1f%s", "--name-only", "--", "book")
    for block in raw.split("\x1e")[1:]:
        head, *files = block.strip().split("\n")
        h, t, s = head.split("\x1f")
        approvals.append({"hash": h, "time": float(t), "subject": s, "files": [f for f in files if f][:80]})
    publishes = []
    pub = ROOT / ".publish"
    if (pub / ".git").exists():
        try:
            r = subprocess.run(["git", "log", "-n8", "--format=%h%x1f%ct%x1f%s"], cwd=pub, capture_output=True,
                               text=True, timeout=10)
            for line in r.stdout.splitlines():
                h, t, s = line.split("\x1f")
                publishes.append({"hash": h, "time": float(t), "subject": s})
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return {"git": bool(commits) or (ROOT / ".git").exists(), "commits": commits, "approvals": approvals,
            "publishes": publishes}


# ------------------------------------------------------------------ format check (existing validator)

def run_check() -> dict:
    """Run the existing `build.py check` validator and remember its result."""
    import sys  # noqa: PLC0415
    r = subprocess.run([sys.executable, str(R.APP / "tools/build.py"), "check"], cwd=ROOT, capture_output=True,
                       text=True, timeout=600)
    out = (r.stdout + r.stderr).strip()
    errors = len(re.findall(r"^\s*(ERROR|error)", out, re.M))
    m = re.search(r"(\d+) error", out)
    if m:
        errors = int(m.group(1))
    warn = re.search(r"(\d+) warning", out)
    result = {"time": time.time(), "ok": r.returncode == 0 and errors == 0, "errors": errors,
              "warnings": int(warn.group(1)) if warn else 0, "output": out[-6000:]}
    CHECK_FILE.parent.mkdir(exist_ok=True)
    CHECK_FILE.write_text(json.dumps(result), encoding="utf-8")
    return result


def last_check() -> dict | None:
    try:
        return json.loads(CHECK_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ health

def item(label: str, status: str, detail: str = "", link: str = "") -> dict:
    return {"label": label, "status": status, "detail": detail, "link": link}


def health(chapters: list[dict], stem: str, site: dict) -> dict:
    """Four categories. Status is one of pass | warn | fail | unchecked | na."""
    total = len(chapters)
    approved = sum(1 for c in chapters if c["code"] == "advance")
    serious = [c for c in chapters if c["serious"]]
    claude = [c for c in chapters if c["code"] in ("claude", "revise")]
    planned = [c for c in chapters if c["status"] in ("planned", "?") and c["words"] == 0]
    res = research()
    texts = chapter_texts()
    imgs = images(texts)
    outs = outputs(stem)
    changed = latest_source_change()
    chk = last_check()

    content = [
        item("Approved chapters", "pass" if total and approved == total else "warn",
             f"{approved} of {total} approved", "chapters/approvals"),
        item("Chapter problems", "pass" if not serious else "fail",
             f"{len(serious)} chapter(s) with problems to fix" if serious else "None found", "overview/dashboard"),
        item("Outstanding reviews", "pass" if not claude else "warn",
             f"{len(claude)} waiting on a check or revision" if claude else "None waiting", "ai/review"),
        item("Missing chapter content", "pass" if not planned else "fail",
             f"{len(planned)} still a placeholder" if planned else "Every chapter has text", "chapters/list"),
    ]
    bib = res["bib"]
    evidence = [
        item("Citation keys", "na" if not bib["exists"] else "pass" if not res["missingKeys"] else "fail",
             "No bibliography in this project" if not bib["exists"] else
             f"{len(res['missingKeys'])} cited but not in references.bib" if res["missingKeys"] else
             f"All {res['used']} cited keys are in references.bib", "research/audit"),
        item("Front-matter source lists", "na" if not bib["exists"] else "warn" if res["metaMissing"] else "pass",
             f"{sum(map(len, res['metaMissing'].values()))} key(s) in {len(res['metaMissing'])} chapter(s) don't match references.bib"
             if res["metaMissing"] else "Every listed key is in references.bib", "research/audit"),
        item("Bibliography consistency", "na" if not bib["exists"] else
             "fail" if bib["duplicates"] else "warn" if bib["incomplete"] else "pass",
             "" if not bib["exists"] else
             f"{len(bib['duplicates'])} duplicate key(s), {len(bib['incomplete'])} missing title or year"
             if bib["duplicates"] or bib["incomplete"] else f"{len(bib['entries'])} entries, no duplicates", "research/bibliography"),
        item("[NEEDS SOURCE] markers", "pass" if not res["gaps"] else "fail",
             f"{len(res['gaps'])} unresolved" if res["gaps"] else "None in the manuscript", "research/gaps"),
        item("Referenced source files", "na" if not any(e["file"] for e in bib["entries"]) else
             "pass" if not res["fileMissing"] else "fail",
             "No bibliography entries point to files" if not any(e["file"] for e in bib["entries"]) else
             f"{len(res['fileMissing'])} missing", "research/sources"),
        item("Sources to verify", "na" if not res["neededDoc"] else "pass" if not res["neededOpen"] else "warn",
             f"{res['neededOpen']} open item(s) in {res['neededDoc']}" if res["neededDoc"] else "No sources-needed list",
             "research/gaps"),
    ]
    design = [
        item("Cover", "pass" if R.cover_of(ROOT) else "fail", R.cover_of(ROOT) or "No cover image found", "design/graphics"),
        item("Broken image references", "na" if not imgs else "pass" if not [i for i in imgs if i["exists"] is False] else "fail",
             "The manuscript has no images" if not imgs else
             f"{len([i for i in imgs if i['exists'] is False])} of {len(imgs)} missing", "design/graphics"),
        item("Alternative text", "na" if not imgs else "pass" if all(i["alt"] for i in imgs) else "warn",
             "The manuscript has no images" if not imgs else
             f"{len([i for i in imgs if not i['alt']])} image(s) without alt text", "design/graphics"),
        item("Formatting check (build.py check)",
             "unchecked" if not chk else "pass" if chk["ok"] else "fail",
             "Not run yet" if not chk else
             f"{chk['errors']} error(s), {chk['warnings']} warning(s) · {time.strftime('%b %d %H:%M', time.localtime(chk['time']))}"
             + (" · chapters changed since" if chk and chk["time"] < changed else ""), "overview/health"),
    ]
    pdf = next((o for o in outs if o["format"] == "PDF" and o["current"]), None)
    epub = next((o for o in outs if o["format"] == "EPUB" and o["current"]), None)
    distribution = [
        item("PDF build", "fail" if not pdf else "pass" if pdf["mtime"] >= changed else "warn",
             "Not built yet" if not pdf else "Up to date" if pdf["mtime"] >= changed else "Chapters changed since the last build",
             "build/pdf"),
        item("EPUB build", "fail" if not epub else "pass" if epub["mtime"] >= changed else "warn",
             "Not built yet" if not epub else "Up to date" if epub["mtime"] >= changed else "Chapters changed since the last build",
             "build/epub"),
        item("EPUB validation", "unchecked",
             "epubcheck isn't installed, so EPUB files aren't validated" if not shutil.which("epubcheck")
             else "Not run yet", "build/epub"),
        item("Website", "na" if not site.get("configured") else "pass" if site.get("built") else "unchecked",
             "No website set up for this project" if not site.get("configured") else
             "Built locally" if site.get("built") else "Not built in this session", "website/publish"),
        item("Build warnings", "unchecked" if not pdf or pdf.get("preflight") is None else "warn" if pdf["preflight"] else "pass",
             "No build record yet" if not pdf or pdf.get("preflight") is None else
             f"{len(pdf['preflight'])} image or content warning(s) in the last PDF build" if pdf["preflight"] else "None in the last PDF build",
             "build/history"),
        item("Exports available", "pass" if outs else "fail",
             ", ".join(sorted({o["format"] for o in outs})) or "No files in dist/", "build/export"),
    ]
    cats = {"Content": content, "Evidence": evidence, "Design": design, "Distribution": distribution}
    return {"categories": cats, "check": chk}


# ------------------------------------------------------------------ dashboard

def dashboard(chapters: list[dict], stem: str, site: dict) -> dict:
    words = sum(c["words"] for c in chapters)
    parts = {}
    for c in chapters:
        p = parts.setdefault(c["part"], {"n": c["part"], "name": c["partName"], "chapters": 0, "words": 0, "approved": 0})
        p["chapters"] += 1
        p["words"] += c["words"]
        p["approved"] += c["code"] == "advance"
    outs = outputs(stem)
    pdf = next((o for o in outs if o["format"] == "PDF" and o["current"]), None)
    h = health(chapters, stem, site)
    return {"words": words, "sections": len(parts), "chapters": len(chapters),
            "approved": sum(1 for c in chapters if c["code"] == "advance"),
            "readingMinutes": round(words / WORDS_PER_MINUTE),
            "pages": pdf_pages(ROOT / pdf["path"]) if pdf else None, "pdf": pdf,
            "composition": sorted(parts.values(), key=lambda p: p["n"]), "outputs": outs,
            "health": h, "cover": R.cover_of(ROOT), "modified": R.last_modified(ROOT)}
