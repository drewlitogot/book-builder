#!/usr/bin/env python3
"""Chapter workflow for the ChatGPT-first pipeline.

    python tools/chapter.py scaffold            create placeholder files for every outline chapter, rewrite book.yml
    python tools/chapter.py list                show chapters, status and what research exists
    python tools/chapter.py research N          build a ChatGPT research prompt (web search) -> prompts/
    python tools/chapter.py save-research N FILE  store ChatGPT's research reply -> research/chatgpt/
    python tools/chapter.py import-research N ZIP  import ChatGPT's chNN-research.zip (findings + source cards)
    python tools/chapter.py library             build the ChatGPT Project memory files -> dist/chatgpt-project-files/
    python tools/chapter.py write N             build a paste-ready ChatGPT writing prompt -> prompts/
    python tools/chapter.py save N FILE         store ChatGPT's reply as the next draft version -> drafts/
    python tools/chapter.py revise N            build a revision prompt from the latest draft + reviews -> prompts/
    python tools/chapter.py approve N           copy the latest draft into book/ with status: approved

See research/06-agent-workflow.md ("ChatGPT-first pipeline").
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("BOOK_PROJECT") or Path(__file__).resolve().parent.parent).resolve()  # the book project
OUTLINE = ROOT / "research/03-content-outline.md"
INDEX = ROOT / "research/pass-1/index.yml"
GUIDE = ROOT / "agents/chatgpt-writer.md"
CONTINUITY = ROOT / "research/continuity.md"
MARKER = "=== EDITOR NOTES ==="
SOURCES_MARKER = "=== SOURCES ==="
RESEARCH_DIR = ROOT / "research/chatgpt"
CARDS_DIR = RESEARCH_DIR / "sources"          # one "source card" per source, shared across chapters
PROJECT_OUT = ROOT / "dist/chatgpt-project-files"  # memory files to upload to the ChatGPT Project
PROJECT_REFS = ["research/02-editorial-charter.md", "research/03-content-outline.md", "research/continuity.md"]


# ------------------------------------------------------------------ outline

# Front matter and the glossary go through the same pipeline as chapters (prompt, draft, check,
# revise, approve), with prompts written for their purpose. They get internal numbers outside 1-60 so
# every tool can keep addressing items by number; `num` is what people see.
# Front matter and back matter sections (with their own prompts) can be added per book here.
SPECIAL: list[dict] = []
FRONT_PART = {"n": 0, "name": "Before you start", "folder": "00-front"}
BACK_PART = {"n": 10, "name": "Back matter", "folder": "99-back"}


def is_special(ch: dict) -> bool:
    return "kind" in ch


def label(ch: dict) -> str:
    """How people see the item: "Ch 05", "Front 1", "Glossary"."""
    if not is_special(ch):
        return f"Ch {ch['n']:02d}"
    return "Glossary" if ch["key"] == "glossary" else f"Front {ch['num'][1:]}"


def what(ch: dict) -> str:
    """Phrase for prompts and messages: "chapter 5", "the front-matter section “How to use this book”"."""
    if not is_special(ch):
        return f"chapter {ch['n']}"
    return "the glossary" if ch["key"] == "glossary" else f"the front-matter section “{ch['title']}”"

def slugify(title: str, words: int = 6) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return "-".join(s.split("-")[:words])


def parse_outline() -> tuple[list[dict], dict, list[dict]]:
    text = OUTLINE.read_text(encoding="utf-8")
    parts, chapters, front = {}, [], []
    through = {}
    for m in re.finditer(r'^\| (\d)\. ([^|]+)\| "(.+?)" \| (.+?) \|$', text, re.M):
        through[int(m.group(1))] = {"question": m.group(3), "handoff": m.group(4).strip()}
    part = None
    for line in text.splitlines():
        if m := re.match(r"^## Part (\d+): (.+?) \(`([^`]+)`\)", line):
            n = int(m.group(1))
            part = {"n": n, "name": m.group(2), "folder": m.group(3), **through.get(n, {})}
            parts[n] = part
        elif line.startswith("## Front matter"):
            part = "front"
        elif line.startswith("## "):
            part = None
        elif part == "front" and (m := re.match(r"^- \*\*(.+?)\*\*:?\s*(.*)$", line)):
            front.append({"title": m.group(1), "desc": m.group(2)})
        elif isinstance(part, dict) and (m := re.match(r"^(\d+)\. \*\*(.+?)\*\*(.*)$", line)):
            rest = m.group(3)
            markers = re.findall(r"\[([PND])\]", rest)
            desc = re.sub(r"^\s*(\[[PND]\]\s*)*:?\s*", "", rest).strip()
            desc = re.sub(r"^\(and aren't\)\s*", "", desc)
            chapters.append({"n": int(m.group(1)), "title": m.group(2), "desc": desc,
                             "markers": markers, "part": part})
    specials = []
    for sp in SPECIAL:
        item = {**sp, "markers": [], "part": FRONT_PART if sp["kind"] == "front" else BACK_PART}
        if sp["kind"] == "front":
            i = int(sp["num"][1:]) - 1
            if i >= len(front):   # other book projects may list fewer (or no) front-matter sections
                continue
            item.setdefault("title", front[i]["title"])
            item.setdefault("desc", front[i]["desc"])
        elif not (ROOT / "book" / sp["file"]).exists() and "## Back matter" not in text:
            continue              # the glossary only exists in books that have one
        specials.append(item)
    chapters = [s for s in specials if s["kind"] == "front"] + chapters + [s for s in specials if s["kind"] == "back"]
    return chapters, parts, front


def chapter_path(ch: dict) -> Path:
    if "file" in ch:
        return ROOT / "book" / ch["file"]
    folder = ROOT / "book" / ch["part"]["folder"]
    found = sorted(folder.glob(f"{ch['n']:02d}-*.md"))
    return found[0] if found else folder / f"{ch['n']:02d}-{slugify(ch['title'])}.md"


def chapter_id(ch: dict) -> str:
    p = chapter_path(ch)
    return f"{p.parent.name}/{p.stem}"


def get(n: int) -> tuple[dict, list[dict], dict]:
    chapters, parts, _ = parse_outline()
    for ch in chapters:
        if ch["n"] == n:
            return ch, chapters, parts
    sys.exit(f"No chapter or section {n} in the outline.")


def front_matter(path: Path) -> tuple[dict, str]:
    if not path.exists():
        return {}, ""
    t = path.read_text(encoding="utf-8")
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n", t, re.S)
    return ((yaml.safe_load(m.group(1)) or {}), t[m.end():]) if m else ({}, t)


# ------------------------------------------------------------------ scaffold / list

def scaffold() -> None:
    chapters, parts, front = parse_outline()
    created = 0
    for ch in chapters:
        if is_special(ch):
            continue
        p = chapter_path(ch)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f'---\ntitle: "{ch["title"]}"\nstatus: planned\nsources: []\n---\n\n'
                         f'# {ch["title"]}\n\n*Planned.* {ch["desc"]}\n', encoding="utf-8")
            created += 1
    front_dir = ROOT / "book/00-front"
    for i, f in enumerate(front, 1):
        if not sorted(front_dir.glob(f"{i:02d}-*.md")):
            (front_dir / f"{i:02d}-{slugify(f['title'])}.md").write_text(
                f'---\ntitle: "{f["title"]}"\nstatus: planned\nsources: []\n---\n\n'
                f'# {f["title"]} {{.unnumbered}}\n\n*Planned.* {f["desc"]}\n', encoding="utf-8")
            created += 1
    manifest = yaml.safe_load((ROOT / "book.yml").read_text(encoding="utf-8"))
    rel = lambda p: p.relative_to(ROOT).as_posix()
    new_parts = [{"title": "Before you start", "chapters": [rel(p) for p in sorted(front_dir.glob("*.md"))]}]
    for n, part in sorted(parts.items()):
        new_parts.append({"title": f"Part {n}: {part['name']}",
                          "chapters": [rel(chapter_path(c)) for c in chapters if c["part"] is part]})
    new_parts.append({"title": "Back matter",
                      "chapters": ["book/99-back/glossary.md", "book/99-back/references.md"]})
    manifest["parts"] = new_parts
    header = ("# Book manifest: metadata and chapter order. Regenerated by `tools/chapter.py scaffold`\n"
              "# from research/03-content-outline.md; edit the outline, then rerun scaffold.\n\n")
    (ROOT / "book.yml").write_text(header + yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
                                   encoding="utf-8")
    print(f"created {created} placeholder files; book.yml lists {sum(len(p['chapters']) for p in new_parts)} files")


def list_chapters() -> None:
    chapters, _, _ = parse_outline()
    index = yaml.safe_load(INDEX.read_text()) if INDEX.exists() else {}
    for ch in chapters:
        meta, _ = front_matter(chapter_path(ch))
        drafts = len(list((ROOT / "drafts" / chapter_path(ch).stem).glob("v*.md")))
        print(f"{label(ch):<9} {meta.get('status', '?'):<10} research:{'yes' if ch['n'] in index else 'NO ':<3}"
              f"  drafts:{drafts}  {ch['title']}")


# ------------------------------------------------------------------ prompt pieces

def research_sections(n: int) -> str:
    index = (yaml.safe_load(INDEX.read_text()) or {}) if INDEX.exists() else {}   # new books have no pass-1 index
    entry = index.get(n)
    if not entry:
        return ""
    out = []
    for fname, heading in zip(entry[::2], entry[1::2]):
        text = (ROOT / "research/pass-1" / fname).read_text(encoding="utf-8")
        m = re.search(r"^## [^\n]*" + re.escape(heading) + r"[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        if m:
            out.append(m.group(1).strip())
    return "\n\n".join(out)


def source_notes(text: str, extra_keys: list[str]) -> list[tuple[str, str]]:
    found = []
    for d in sorted((ROOT / "sources").iterdir()):
        if d.is_dir() and (d.name in extra_keys or re.search(rf"\b{re.escape(d.name)}\b", text)):
            meta = yaml.safe_load((d / "meta.yml").read_text()) if (d / "meta.yml").exists() else {}
            notes = (d / "notes.md").read_text(encoding="utf-8") if (d / "notes.md").exists() else ""
            found.append((d.name, f"Read status: {meta.get('status', '?')}\n\n{notes.strip()}"))
    return found


def neighbors(ch: dict, chapters: list[dict], before: int = 4, after: int = 3) -> str:
    i = chapters.index(ch)
    fmt = lambda c: f"- Ch. {c['n']}, **{c['title']}**: {c['desc']}"
    earlier = "\n".join(fmt(c) for c in chapters[max(0, i - before):i]) or "- (This is the first chapter.)"
    later = "\n".join(fmt(c) for c in chapters[i + 1:i + 1 + after]) or "- (This is the last chapter.)"
    return f"**Comes just before (build on these, don't re-teach them):**\n{earlier}\n\n" \
           f"**Comes just after (leave these topics for later):**\n{later}"


def save_prompt(name: str, body: str) -> Path:
    out = ROOT / "prompts" / name
    out.parent.mkdir(exist_ok=True)
    out.write_text(body, encoding="utf-8")
    words = len(body.split())
    print(f"{out.relative_to(ROOT)}  ({words:,} words; copy the whole file into ChatGPT)")
    return out


# ------------------------------------------------------------------ write / save / revise / approve

def special_by_n(n: int) -> dict | None:
    return next((s for s in SPECIAL if s["n"] == n), None)


def chat_name(n: int, title: str, kind: str = "") -> str:
    """The chat's standard name, e.g. "Ch 05 · Masking and burnout" or "Front 1 · How to use this book"."""
    sp = special_by_n(n)
    if sp:
        return "Glossary" if sp["key"] == "glossary" else f"Front {sp['num'][1:]} · {title}"
    return f"Ch {n:02d} · {title}"


def chat_header(n: int, title: str, kind: str) -> str:
    """Top of every prompt. ChatGPT titles new chats from the first message, so lead with the name."""
    name = chat_name(n, title)
    sp = special_by_n(n)
    target = what({**sp, "title": title}) if sp else f"chapter {n}"
    return (f"# {name}\n\n"
            f"CHAT NAME: {name}\n"
            f"Title this conversation exactly \"{name}\". "
            f"This message is the {kind} for {target}. Don't repeat these lines in your reply.\n\n")


def research_path(ch: dict) -> Path:
    return RESEARCH_DIR / f"{chapter_path(ch).stem}.md"


def research(n: int) -> None:
    """Prompt asking ChatGPT (with web search) to research one chapter. Its reply goes back into the write prompt."""
    ch, chapters, _ = get(n)
    if is_special(ch):
        import special
        return save_prompt(f"{chapter_path(ch).stem}-research.md", special.research_prompt(ch, chapters))
    part = ch["part"]
    path = chapter_path(ch)
    brief_path = ROOT / "briefs" / part["folder"] / path.name
    brief = brief_path.read_text(encoding="utf-8") if brief_path.exists() else ""
    existing = research_sections(n)
    keys = [k for k, _ in source_notes(existing + brief, [])]
    keys += sorted(p.stem for p in CARDS_DIR.glob("*.md")) if CARDS_DIR.exists() else []
    nn = f"{n:02d}"
    s = [chat_header(n, ch["title"], "research step (the chapter draft comes later in this same chat)")]
    s.append(f"""You are researching one chapter of a nonfiction book. You can't see the project's repository. Everything you need is in this prompt. You may also have the project's **research memory** (`research-part-*.md`, research from earlier chapters; `sources-library.md`, a card for every source found so far), either as files in this ChatGPT Project or in an attached prompt pack ZIP; if you don't, carry on without them. Don't write the chapter yet.

# Chapter {n}: {ch['title']}

**Part {part['n']}: {part['name']}.** This part answers: *"{part.get('question', '')}"*

**What the chapter covers:** {ch['desc']}

{neighbors(ch, chapters)}

# Your task

First, if you have the research memory files, check them for sources and findings that already cover this chapter; reuse them (same key) instead of searching again, and say which ones you reused. Either way, reuse an existing key (listed below) when you find the same work. Then use web search to find the best available evidence for what's still missing. Aim for 6–15 strong sources in total.

1. List the 4–8 questions this chapter must answer well for a beginner.
2. For each question, give the findings: what the evidence says, how strong it is (one study, several studies, review or meta-analysis, official statistics, expert guidance), and its limits (sample, country, self-report, age, who was left out). Say where studies disagree.
3. Note anything that applies differently to different groups of readers, but only where a source supports it.
4. For legal or safety topics, prefer official sources for the book's country and note when rules vary by region.
5. Gaps: what readers need that research doesn't answer. The chapter will give practical advice there without pretending it's research.

# Rules for sources

- **Only sources you actually found and opened in this chat.** Give a working link (DOI preferred). If you can't browse, say so at the top and list only sources you're certain exist, marked "not opened".
- Never invent a source, author, year, statistic, quote or page number. If unsure, leave it out.
- Say how you read each source: **full text**, **abstract only**, or **summary page**. Keep claims as modest as what you read.
- Prefer peer-reviewed research, systematic reviews, government data and professional bodies. Avoid pop science and blogs (you may mention a myth only to say the evidence doesn't support it).
- Give each source a key: first author's surname plus year, lowercase, e.g. `smith2020` (add a, b if needed). If a source is already in the memory, reuse its key. Don't reuse these existing keys for different works: {', '.join(keys) if keys else '(none yet)'}.
""")
    if existing:
        s.append("\n# Research we already have (don't repeat it; check, update, and fill the gaps)\n\n" + existing + "\n")
    s.append(f"""
# What to send back: a zip file

This research becomes the project's long-term memory, so deliver it as a file. Use your file or code tool to create \
**`ch{nn}-research.zip`** for download, containing:

1. **`ch{nn}-research.md`**: starts with the line `# Research: {chat_name(n, ch['title'])}`, then your findings in \
Markdown, citing sources by key like [@smith2020], then a line containing only `{SOURCES_MARKER}`, then one block per \
source (new and reused) exactly like this:

```
- key: smith2020
  apa: "Smith, J., & Lee, K. (2020). Title of the article. *Journal Name, 12*(3), 45–67. https://doi.org/..."
  link: https://doi.org/...
  read: full text | abstract only | summary page | not opened
  type: peer-reviewed study | review | meta-analysis | government | professional body | book | other
  supports: "one line on what this source supports in the chapter"
  caveats: "one line on its limits"
```

2. **`sources/<key>.md`**, one per NEW source (skip sources reused from memory): a source card that future chats can \
rely on without re-reading the source. Include: the key as a heading; APA reference; link; how you read it; type; \
who and what was studied (sample, country, year, method); the main findings, with page or section numbers where you \
have them; at most two short quotes (under 25 words each) only if the exact wording matters; limits; and which \
topics or chapters of this book it could help besides this one.

Then reply in the chat with a summary of under 150 words and the download link. Keep the full findings in this chat's \
context: the writing prompt comes next, in this same chat.

**If you can't create files**, reply instead with the full text of `ch{nn}-research.md` (from the `# Research:` line to \
the last source block) and nothing else; it will be pasted in.
""")
    save_prompt(f"{path.stem}-research.md", "".join(s))


def save_research(n: int, src: str) -> None:
    ch, _, _ = get(n)
    text = Path(src).read_text(encoding="utf-8")
    out = store_research(ch, text)
    print(f"saved {out.relative_to(ROOT)}  ({len(text.split()):,} words). Next: copy the writing prompt "
          "into the SAME ChatGPT chat.")
    build_library(quiet=True)


def store_research(ch: dict, text: str) -> Path:
    """Write the chapter's main research file (keeping the previous one)."""
    n = ch["n"]
    text = clean(text).strip()
    if not text:
        sys.exit("Not saved: the research is empty.")
    head = text.splitlines()[0]
    if head.startswith("# Research") and slugify(ch["title"], 2) not in slugify(head, 20):
        print(f"WARNING: the research starts \"{head}\" but chapter {n} is \"{ch['title']}\". Check you used the right chat.")
    if SOURCES_MARKER not in text:
        print("WARNING: no === SOURCES === line; the source list may be missing.")
    out = research_path(ch)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        shutil.copy(out, out.with_suffix(".previous.md"))
    out.write_text(f"<!-- ChatGPT research for chapter {n}. Sources not yet verified by Claude. -->\n\n{text}\n",
                   encoding="utf-8")
    return out


def import_research_zip(n: int, zip_path: str) -> None:
    """Import ChatGPT's chNN-research.zip: main findings + source cards. Only text files are read."""
    import zipfile
    ch, _, _ = get(n)
    main, cards = None, {}
    with zipfile.ZipFile(zip_path) as z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if sum(i.file_size for i in infos) > 20_000_000:
            sys.exit("Not imported: the zip is larger than 20 MB of files, which isn't a research zip.")
        for i in infos:
            parts = Path(i.filename).parts
            name = parts[-1]
            if "__MACOSX" in parts or name.startswith(".") or not name.lower().endswith((".md", ".txt", ".yml", ".yaml")):
                continue
            text = z.read(i).decode("utf-8", "replace")
            if any(p.lower() in ("sources", "source-cards", "cards") for p in parts[:-1]):
                key = re.sub(r"[^a-z0-9]+", "", Path(name).stem.lower())
                if key:
                    cards[key] = text
            elif main is None or "research" in name.lower():
                main = text
    if main is None:
        sys.exit("Not imported: no research .md file found in the zip.")
    out = store_research(ch, main)
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    new = updated = 0
    for key, text in cards.items():
        dest = CARDS_DIR / f"{key}.md"
        if not dest.exists():
            dest.write_text(text.strip() + "\n", encoding="utf-8")
            new += 1
        elif text.strip() not in dest.read_text(encoding="utf-8"):
            with dest.open("a", encoding="utf-8") as f:
                f.write(f"\n\n## Update from chapter {n} research\n\n{text.strip()}\n")
            updated += 1
    print(f"imported {out.relative_to(ROOT)} ({len(main.split()):,} words) and {len(cards)} source cards "
          f"({new} new, {updated} updated).")
    build_library(quiet=True)
    print("Project memory files updated: upload them to the ChatGPT Project (Help tab, Show the files to upload).")


def library_stale() -> bool:
    """True when research or reference files changed after the author last uploaded the memory files to ChatGPT."""
    marker = PROJECT_OUT / ".uploaded"
    if not marker.exists():
        return True
    t = marker.stat().st_mtime
    files = [ROOT / f for f in PROJECT_REFS] + (list(RESEARCH_DIR.rglob("*.md")) if RESEARCH_DIR.exists() else [])
    return any(f.exists() and f.stat().st_mtime > t for f in files)


def build_library(quiet: bool = False) -> None:
    """Merge research into a few files for the ChatGPT Project (Projects hold only about 20 files)."""
    chapters, parts, _ = parse_outline()
    PROJECT_OUT.mkdir(parents=True, exist_ok=True)
    for old in PROJECT_OUT.glob("research-part-*.md"):
        old.unlink()
    made = []
    for pn, part in sorted(parts.items()):
        chunks = []
        for c in chapters:
            if c["part"] is not part:
                continue
            f = research_path(c)
            if f.exists() and "skipped" not in f.read_text(encoding="utf-8")[:80]:
                body = re.sub(r"\A<!--.*?-->\s*", "", f.read_text(encoding="utf-8"), flags=re.S).strip()
                chunks.append(f"\n\n---\n\n<!-- Chapter {c['n']}: {c['title']} -->\n\n{body}")
        if chunks:
            out = PROJECT_OUT / f"research-part-{pn}.md"
            out.write_text(f"# Research memory, Part {pn}: {part['name']}\n\nChatGPT research saved for each chapter "
                           "in this part. Sources are verified by Claude when chapters are checked.\n" + "".join(chunks) + "\n",
                           encoding="utf-8")
            made.append(out.name)
    cards = sorted(CARDS_DIR.glob("*.md")) if CARDS_DIR.exists() else []
    lib = ["# Sources library\n\nOne card per source found so far, by key. Reuse these keys; don't create a second "
           "key for the same work.\n"]
    lib += [f"\n\n---\n\n{c.read_text(encoding='utf-8').strip()}" for c in cards]
    (PROJECT_OUT / "sources-library.md").write_text("".join(lib) + "\n", encoding="utf-8")
    made.append("sources-library.md")
    for f in PROJECT_REFS:
        src = ROOT / f
        if src.exists():
            shutil.copy(src, PROJECT_OUT / src.name)
            made.append(src.name)
    (PROJECT_OUT / ".built").write_text("built\n")
    if not quiet:
        print(f"{PROJECT_OUT.relative_to(ROOT)}: {len(made)} files ({', '.join(made)}). "
              f"{len(cards)} source cards. Upload all of them to the ChatGPT Project, replacing older copies.")


def skip_research(n: int) -> None:
    ch, _, _ = get(n)
    out = research_path(ch)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"<!-- Research step skipped for chapter {n}. -->\n", encoding="utf-8")
    print(f"Research skipped for chapter {n}.")


def write(n: int) -> None:
    ch, chapters, parts = get(n)
    if is_special(ch):
        import special
        save_prompt(f"{chapter_path(ch).stem}-write.md", special.write_prompt(ch, chapters))
        return
    part = ch["part"]
    path = chapter_path(ch)
    meta, body = front_matter(path)
    brief_path = ROOT / "briefs" / part["folder"] / path.name
    brief = brief_path.read_text(encoding="utf-8") if brief_path.exists() else ""
    research = research_sections(n)
    notes = source_notes(research + brief + body, meta.get("sources") or [])
    boxes = {"P": "perspective boxes (different readers' viewpoints)", "N": "experience-titled reader-group boxes",
             "D": "partner boxes (for the people around the reader)"}
    box_hint = ", ".join(boxes[m] for m in ch["markers"]) or "probably none; add a box only if an experience clearly differs"

    last_in_part = n == max(c["n"] for c in chapters if c["part"] is part)
    if last_in_part and part.get("handoff"):
        handoff = (f"This is the **last chapter of the part**, so end it by handing the reader on with: "
                   f"{part['handoff']}")
    else:
        handoff = ("This is not the last chapter of the part: don't use the part's closing hand-off line. "
                   "End by leading naturally into the next chapter.")
    s = [chat_header(n, ch["title"], "draft"), GUIDE.read_text(encoding="utf-8").strip(), "\n\n---\n\n# Your assignment\n"]
    s.append(f"**Chapter {n}: {ch['title']}**\n\n**Part {part['n']}: {part['name']}**. "
             f"This part answers: *\"{part.get('question', '')}\"* {handoff}"
             f"\n\n**What this chapter covers (from the outline):** {ch['desc']}\n\n"
             f"**Boxes likely needed:** {box_hint}.\n\n"
             "**Length:** let the content decide. As a guide, 2,000–4,000 words; shorter if the topic is simple, "
             "longer only if every section earns its place.\n\n"
             "**Reader goal:** by the end, the reader should understand the idea well enough to explain it to a "
             "friend, and know at least one concrete thing to try or say. Move them from recognition (\"that's me\") "
             "to understanding (\"that's why\") to action (\"here's what I can do\"), without shaming.\n")
    s.append("\n## Where this sits in the book\n\n" + neighbors(ch, chapters))
    if CONTINUITY.exists():
        s.append("\n\n## Continuity reference (terms and decisions already fixed)\n\n" + CONTINUITY.read_text(encoding="utf-8").strip())
    if brief:
        s.append("\n\n## Chapter brief (prepared earlier; follow it unless it conflicts with the rules above)\n\n" + brief.strip())
    if meta.get("status") not in (None, "planned") and body.strip():
        s.append("\n\n## Existing draft (keep what works; improve the rest)\n\n" + body.strip())
    chat_research = research_path(ch).read_text(encoding="utf-8") if research_path(ch).exists() else ""
    if "skipped" in chat_research[:80]:
        chat_research = ""
    s.append("\n\n---\n\n# Research for this chapter\n\nThese notes come from the project's research pass"
             + (" and from your own research step earlier in this chat (repeated below)" if chat_research else "") + ". "
             "Source tables list how each source was read (full text vs abstract). **Only cite these sources**, "
             "using their keys. Where notes flag weak, conflicting or missing evidence, keep that uncertainty in the prose.\n")
    if research:
        s.append("\n## Research notes\n\n" + research)
    else:
        s.append("\n**No research notes exist for this chapter yet.** Write practical guidance only, make no research "
                 "claims, and mark anything factual with `[NEEDS SOURCE]`.\n")
    for key, text in notes:
        s.append(f"\n\n## Source notes: `{key}` (cite as `[@{key}]`)\n\n{text}")
    if chat_research:
        s.append("\n\n## Your research step (sources you found; you may cite them by key, like the others. "
                 "Claude verifies each one, so cite them only for what you actually read)\n\n"
                 + re.sub(r"\A<!--.*?-->\s*", "", chat_research, flags=re.S).strip())
    s.append("\n\n---\n\nNow write the complete chapter, then the editor notes, in the format described under "
             "\"What to send back\".\n")
    save_prompt(f"{path.stem}-write.md", "".join(s))


def drafts_dir(ch: dict) -> Path:
    return ROOT / "drafts" / chapter_path(ch).stem


def latest_draft(ch: dict) -> Path | None:
    vs = sorted(drafts_dir(ch).glob("v*-chapter.md"), key=lambda p: int(re.match(r"v(\d+)", p.name).group(1)))
    return vs[-1] if vs else None


def clean(text: str) -> str:
    """Undo escaping that sneaks in when copying from ChatGPT's rendered view."""
    text = text.replace("&#x20;", " ").replace("&nbsp;", " ")
    text = re.sub(r"^\\(-{3})\\?\s*$", r"\1", text, flags=re.M)
    text = re.sub(r"[ \t]*\\[ \t]*$", "", text, flags=re.M)  # trailing backslash = escaped line break
    return re.sub(r"\\([*#\-._\[\]>`=])", r"\1", text)


def save(n: int, src: str) -> None:
    ch, _, _ = get(n)
    text = clean(Path(src).read_text(encoding="utf-8"))
    for d in (ROOT / "drafts").glob("*/v*-chapter.md"):
        if d.read_text(encoding="utf-8").strip() == text.partition(MARKER)[0].strip():
            sys.exit(f"Not saved: this exact text is already saved as {d.relative_to(ROOT)}. "
                     "Did you copy the right ChatGPT reply?")
    title = re.search(r'^title:\s*"?(.+?)"?\s*$', text, re.M)
    if title and slugify(ch["title"], 2) not in slugify(title.group(1), 12):
        print(f"WARNING: the reply's title is \"{title.group(1)}\" but chapter {n} is \"{ch['title']}\". "
              "Check you copied the right chat.")
    chapter, _, notes = text.partition(MARKER)
    d = drafts_dir(ch)
    d.mkdir(parents=True, exist_ok=True)
    last = latest_draft(ch)
    v = int(re.match(r"v(\d+)", last.name).group(1)) + 1 if last else 1
    (d / f"v{v}-chapter.md").write_text(chapter.strip() + "\n", encoding="utf-8")
    if notes.strip():
        (d / f"v{v}-editor-notes.md").write_text(notes.strip() + "\n", encoding="utf-8")
    print(f"saved {d.relative_to(ROOT)}/v{v}-chapter.md" + (" + editor notes" if notes.strip() else
          "  (no editor notes found; was the marker line missing?)"))
    print("Next: ask Claude to check it, e.g. \"Check chapter %d draft v%d\"." % (n, v))


def revise(n: int) -> None:
    ch, _, _ = get(n)
    draft = latest_draft(ch)
    if not draft:
        sys.exit("No draft saved yet. Use: tools/chapter.py save N FILE")
    review_dir = ROOT / "reviews" / ch["part"]["folder"] / chapter_path(ch).stem
    reviews = sorted(p for p in review_dir.glob("*.md") if p.is_file()) if review_dir.exists() else []
    v = re.match(r"v(\d+)", draft.name).group(1)
    checks = [p for p in reviews if p.name.startswith(f"v{v}-")] or reviews
    if not checks:
        sys.exit(f"No review findings in {review_dir.relative_to(ROOT)} yet. Ask Claude to check the draft first.")
    s = [chat_header(n, ch["title"], f"revision {int(v) + 1}"), GUIDE.read_text(encoding="utf-8").strip(),
         f"\n\n---\n\n# Your assignment: revise {what(ch)}, {ch['title']}\n\n"
         + ("This is not a regular chapter: keep following the purpose-specific instructions from the first "
            "message in this chat.\n\n" if is_special(ch) else "") +
         "Below are your previous draft and the review findings. Revise the chapter:\n\n"
         "- Address every finding: apply it, apply it differently, or explain in the editor notes why not.\n"
         "- Keep your voice and everything that already works. Don't rewrite sections nobody flagged.\n"
         "- Fix overstated claims by weakening them to what the source supports.\n"
         "- Return the full revised chapter and editor notes in the same format. In the editor notes, list each "
         "finding and what you did.\n",
         "\n## Your previous draft\n\n" + draft.read_text(encoding="utf-8").strip()]
    for p in checks:
        s.append(f"\n\n## Review findings: {p.stem}\n\n" + p.read_text(encoding="utf-8").strip())
    save_prompt(f"{chapter_path(ch).stem}-revise-v{v}.md", "".join(s) + "\n")


def approve(n: int) -> None:
    ch, _, _ = get(n)
    draft = latest_draft(ch)
    if not draft:
        sys.exit("No draft to approve.")
    text = draft.read_text(encoding="utf-8")
    text = re.sub(r"^status: .*$", "status: approved", text, count=1, flags=re.M)
    text = re.sub(r'^title: .*$', f'title: "{ch["title"]}"', text, count=1, flags=re.M)
    heading = f"# {ch['title']}" + (" {.unnumbered}" if is_special(ch) else "")
    text = re.sub(r"^# .*$", heading, text, count=1, flags=re.M)
    dest = chapter_path(ch)
    if dest.exists():
        shutil.copy(dest, drafts_dir(ch) / "previous-book-version.md")
    dest.write_text(text, encoding="utf-8")
    print(f"approved {draft.relative_to(ROOT)} -> {dest.relative_to(ROOT)}. Update research/continuity.md next.")


def main() -> None:
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
    elif a[0] == "scaffold":
        scaffold()
    elif a[0] == "list":
        list_chapters()
    elif a[0] == "research" and len(a) == 2:
        research(int(a[1]))
    elif a[0] == "save-research" and len(a) == 3:
        save_research(int(a[1]), a[2])
    elif a[0] == "import-research" and len(a) == 3:
        import_research_zip(int(a[1]), a[2])
    elif a[0] == "library":
        build_library()
    elif a[0] == "skip-research" and len(a) == 2:
        skip_research(int(a[1]))
    elif a[0] == "write" and len(a) == 2:
        write(int(a[1]))
    elif a[0] == "save" and len(a) == 3:
        save(int(a[1]), a[2])
    elif a[0] == "revise" and len(a) == 2:
        revise(int(a[1]))
    elif a[0] == "approve" and len(a) == 2:
        approve(int(a[1]))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
