"""ChatGPT workspace setup: everything a new ChatGPT Project needs, generated from one form.

A ChatGPT Project has three parts, and the manager generates all three:

  1. **Instructions** (the Project's instruction box, about 8,000 characters at most): who the
     assistant is, the rules that apply to every chat, and how replies come back.
  2. **Files** (the Project's files, up to about 20): the long reference material every prompt can lean
     on: charter, outline, continuity, writing guide, glossary, the book so far, research memory, the
     sources library, the Game API and the image style. Each prompt still works without them.
  3. **The initial prompt**: the first message in the Project, which gets the assistant oriented and
     starts the first task.

The author's choices live in `workspace.yml`, edited through the form in the Workspace view. FIELDS below
is the form: each field says what it's for and where it's used, so the standalone app can reuse it.
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chapter as C  # noqa: E402
import jobs as J  # noqa: E402

ROOT = C.ROOT
SETTINGS = ROOT / "workspace.yml"
OUT = C.PROJECT_OUT                      # dist/chatgpt-project-files: what you upload to the Project
INSTRUCTIONS_LIMIT = 8000                # ChatGPT Project instruction box limit (characters)
FILES_LIMIT = 20                         # ChatGPT Project file limit (per project, on most plans)

DEFAULT_RULES = """\
- Nothing usable for harm; describe harmful tactics only enough to recognize them.
- No stereotyping of any group. Report average differences only when the research supports them, with limits.
- Reality checks without shame. Never talk down to readers.
- Not medical or legal advice. Inform and point to professionals."""

DEFAULT_EVIDENCE = """\
- Cite only sources given in the prompt or found and opened in the same chat, as [@key], [@key, p. 12] or [@key1; @key2].
- Keep claims as modest as the source and keep its caveats. "One study found" is not "research shows."
- A factual claim with no source gets [NEEDS SOURCE]. Never invent a source, statistic, quote, page number or study.
- Advice and example scripts need no citation but must not be presented as research findings."""

DEFAULT_STYLE = """\
- Write like an excellent nonfiction handbook, not an AI textbook: warm, plain, specific, sometimes funny, never cute.
- Define a term once, then use only that term. Explain idioms or avoid them (many readers read literally).
- Realistic example people, short dialogues and small exercises where they genuinely help.
- Short paragraphs, clear headings; lists and tables only when they help scanning.
- Avoid "In this chapter we will…", formulaic conclusions, therapy-speak ("hold space", "your journey"), stacked hedges, cheerleading."""

# The form. type: text | textarea | select | check | chapter. where: instructions | initial | files | all.
FIELDS: list[dict] = [
    # The book
    {"key": "title", "group": "The book", "label": "Title", "type": "text", "where": "all", "need": "required"},
    {"key": "subtitle", "group": "The book", "label": "Subtitle", "type": "text", "where": "all"},
    {"key": "byline", "group": "The book", "label": "Byline (author names)", "type": "text", "where": "all",
     "help": "Pen names as they appear on the cover."},
    {"key": "audience", "group": "The book", "label": "Who it's for", "type": "textarea", "where": "all", "need": "required",
     "help": "Readers in a few lines: who they are and what they need. The assistant writes for them."},
    {"key": "purpose", "group": "The book", "label": "What the book should do for them", "type": "textarea", "where": "all"},
    {"key": "locale", "group": "The book", "label": "Country focus and spelling", "type": "select", "where": "all",
     "options": ["United States (US English)", "United Kingdom (UK English)", "Canada", "Australia", "International (US English)"]},
    {"key": "reading_level", "group": "The book", "label": "Reading level", "type": "select", "where": "all",
     "options": ["Plain language (grade 6–8)", "General adult (grade 9–10)", "Professional"]},
    {"key": "voice", "group": "The book", "label": "Voice", "type": "textarea", "where": "all",
     "help": "Point of view and tone, e.g. 'address the reader as you; no I or we stories'."},
    {"key": "license", "group": "The book", "label": "License", "type": "text", "where": "instructions"},
    {"key": "citations", "group": "The book", "label": "Citation style", "type": "select", "where": "instructions",
     "options": ["APA 7 (keys like [@smith2020])", "Chicago author-date", "No citations"]},
    # The assistant
    {"key": "assistant_name", "group": "The assistant", "label": "ChatGPT's pen name", "type": "text", "where": "instructions",
     "help": "Leave empty until ChatGPT has chosen one (Prompts: Pen name)."},
    {"key": "role", "group": "The assistant", "label": "ChatGPT's role", "type": "select", "where": "instructions",
     "options": ["Researcher and author", "Author only (research comes from you)", "Researcher only"]},
    {"key": "checker", "group": "The assistant", "label": "Who checks the drafts", "type": "text", "where": "instructions",
     "help": "Named in the instructions so ChatGPT knows who prepares the prompts and reviews its drafts."},
    {"key": "web_search", "group": "The assistant", "label": "Use web search for research", "type": "check", "where": "instructions"},
    {"key": "images", "group": "The assistant", "label": "Make images (games and illustrations)", "type": "check", "where": "instructions"},
    {"key": "files_out", "group": "The assistant", "label": "Deliver research as downloadable ZIP files", "type": "check", "where": "instructions",
     "help": "Off: everything comes back as text in the chat."},
    {"key": "chat_names", "group": "The assistant", "label": "Chat naming", "type": "text", "where": "instructions",
     "help": "How each chat is titled, so they sort. Prompts start with this name."},
    # Rules
    {"key": "rules", "group": "Rules", "label": "Non-negotiable rules", "type": "textarea", "rows": 9, "where": "instructions", "need": "required"},
    {"key": "evidence", "group": "Rules", "label": "Evidence rules", "type": "textarea", "rows": 5, "where": "instructions"},
    {"key": "style", "group": "Rules", "label": "Style", "type": "textarea", "rows": 6, "where": "instructions"},
    {"key": "extra_rules", "group": "Rules", "label": "Anything else, every chat", "type": "textarea", "where": "instructions",
     "help": "House preferences that aren't covered above (words to avoid, formatting quirks…)."},
    # Project files
    {"key": "file_book", "group": "Project files", "label": "Include the book so far (approved chapters)", "type": "check", "where": "files"},
    {"key": "file_research", "group": "Project files", "label": "Include the research memory and sources library", "type": "check", "where": "files"},
    {"key": "file_games", "group": "Project files", "label": "Include the Game API and image style", "type": "check", "where": "files"},
    # The first chat
    {"key": "kickoff", "group": "The first chat", "label": "What the first chat should do", "type": "select", "where": "initial",
     "options": ["Get oriented: read the files and summarize the project back", "Start research for the next chapter",
                 "Choose a pen name", "Plan games for the approved chapters", "Something else (below)"]},
    {"key": "next_chapter", "group": "The first chat", "label": "Chapter to start with", "type": "chapter", "where": "initial"},
    {"key": "status_note", "group": "The first chat", "label": "Where the book stands", "type": "textarea", "where": "initial",
     "help": "Filled in from the manager each time; add anything the assistant should know."},
    {"key": "ask_first", "group": "The first chat", "label": "Ask me up to 5 questions before starting", "type": "check", "where": "initial"},
    {"key": "custom_kickoff", "group": "The first chat", "label": "Your own words for the first chat", "type": "textarea", "where": "initial",
     "help": "Added to the initial prompt (used alone if you chose 'Something else')."},
]


def defaults() -> dict:
    meta = (yaml.safe_load((ROOT / "book.yml").read_text(encoding="utf-8")) or {}).get("metadata", {})
    return {
        "title": meta.get("title", ""), "subtitle": meta.get("subtitle", ""), "byline": meta.get("author", ""),
        "audience": "Describe the readers this book is for.",
        "purpose": "Describe what the book should do for its readers.",
        "locale": "United States (US English)", "reading_level": "Plain language (grade 6–8)",
        "voice": "Neutral handbook voice. Address the reader as \"you\"; no \"I\" or \"we\" stories.",
        "license": "CC BY-NC-ND 4.0", "citations": "APA 7 (keys like [@smith2020])",
        "assistant_name": "", "role": "Researcher and author", "checker": "Claude",
        "web_search": True, "images": True, "files_out": True, "chat_names": "Ch NN · <chapter title>",
        "rules": DEFAULT_RULES, "evidence": DEFAULT_EVIDENCE, "style": DEFAULT_STYLE, "extra_rules": "",
        "file_book": True, "file_research": True, "file_games": True,
        "kickoff": next(f for f in FIELDS if f["key"] == "kickoff")["options"][0], "next_chapter": None, "status_note": "", "ask_first": True,
        "custom_kickoff": "",
    }


def load() -> dict:
    saved = yaml.safe_load(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.exists() else {}
    return {**defaults(), **(saved or {})}


def save(values: dict) -> dict:
    known = {f["key"] for f in FIELDS}
    base = defaults()
    clean = {k: v for k, v in values.items() if k in known and v != base.get(k)}  # store only changes
    header = "# ChatGPT workspace settings. Edit in the Book Manager (Workspace view).\n"
    SETTINGS.write_text(header + yaml.safe_dump(clean, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    return load()


def status() -> str:
    """Where the book stands, from the chapters' status."""
    chapters, _, _ = C.parse_outline()
    approved = drafted = 0
    for ch in chapters:
        meta, _ = C.front_matter(C.chapter_path(ch))
        approved += meta.get("status") == "approved"
        drafted += meta.get("status") not in (None, "planned", "approved")
    return f"{approved} of {len(chapters)} chapters are approved; {drafted} more have drafts."


# ------------------------------------------------------------------ instructions

def instructions(s: dict | None = None) -> str:
    s = s or load()
    name = s["assistant_name"].strip() or "ChatGPT"
    role = s["role"]
    title = s["title"] + (f": {s['subtitle']}" if s.get("subtitle") else "")
    steps = []
    if role.startswith("Researcher"):
        search = " with web search" if s["web_search"] else ""
        deliver = ("as the downloadable ZIP the prompt describes (or as text if you can't make files)"
                   if s["files_out"] else "as text in the chat, exactly as the prompt describes")
        steps.append(f"RESEARCH prompt: check the research memory files first, then find real, current evidence{search}. "
                     f"Deliver {deliver}. Don't write the chapter yet.")
    if role != "Researcher only":
        steps.append("WRITING prompt, in the same chat: write the chapter from the prompt's research notes plus your own research step.")
        steps.append("REVISION prompts come later in the same chat, with the review findings.")
    images = ("IMAGES: when a prompt asks for images, follow image-style.md exactly (one house look for the whole book)."
              if s["images"] else "IMAGES: don't make images.")
    out = f"""You are {name}, {role.lower()} of a published nonfiction book: "{title}"{f", by {s['byline']}" if s.get('byline') else ""}. {s['checker']} prepares every prompt and checks every draft; the author decides.

READERS
{s['audience'].strip()}
{s.get('purpose', '').strip()}
Focus: {s['locale']}. Reading level: {s['reading_level']}. {s['voice'].strip()}

WHAT YOU CAN SEE: each prompt, these instructions, earlier messages in the same chat, and the files in this Project (start with 00-start-here.md). Every prompt is complete on its own; the files add background. Never guess what a file you can't see says; if something you need is missing, say so.

HOW CHATS WORK
- One chat per chapter or task, titled exactly as the prompt's first line says ({s['chat_names']}). Revisions go in the same chat.
""" + "\n".join(f"- {x}" for x in steps) + f"""
- Follow each prompt's "what to send back" section exactly; the author pastes your reply into the Book Manager, which reads it.

NON-NEGOTIABLE RULES
{s['rules'].strip()}
"""
    if s["citations"] != "No citations" and s.get("evidence", "").strip():
        out += f"\nEVIDENCE ({s['citations'].split(' (')[0]})\n{s['evidence'].strip()}\n"
    if s.get("style", "").strip():
        out += f"\nSTYLE\n{s['style'].strip()}\n"
    if s.get("extra_rules", "").strip():
        out += f"\nALSO\n{s['extra_rules'].strip()}\n"
    out += f"\n{images}\nLICENSE: the book is published under {s['license']}.\n"
    return out


# ------------------------------------------------------------------ initial prompt

def initial_prompt(s: dict | None = None) -> str:
    s = s or load()
    chapters, _, _ = C.parse_outline()
    n = s.get("next_chapter")
    ch = next((c for c in chapters if c["n"] == n), None) if n else None
    if ch is None:  # the first chapter that isn't approved yet
        for c in chapters:
            if (C.front_matter(C.chapter_path(c))[0].get("status")) != "approved":
                ch = c
                break
    where = s.get("status_note", "").strip()
    task = s["kickoff"]
    lines = ["# Getting started", "", "CHAT NAME: Start here", "",
             f"This is the first chat in the Project for \"{s['title']}\". Read the Project instructions and "
             "00-start-here.md, then look through the other files.", "",
             "## Where the book stands", "", status() + (f" {where}" if where else ""), ""]
    if ch:
        lines += [f"Next up: {C.chat_name(ch['n'], ch['title'])}: {ch['desc']}", ""]
    lines += ["## What I'd like from this chat", ""]
    if task.startswith("Get oriented"):
        lines += ["1. Summarize the project back to me in under 200 words: readers, purpose, the rules you'll "
                  "follow, and how each chat works.",
                  "2. List anything in the files that's unclear, contradictory or missing.",
                  "3. Tell me what you'll need from me for the next chapter. Don't start writing yet; the next "
                  "prompt will come from the Book Manager."]
    elif task.startswith("Start research") and ch:
        lines += [f"Get ready to research {C.chat_name(ch['n'], ch['title'])}: list the 4–8 questions it must "
                  "answer for a beginner and which files in this Project already help. The full research prompt "
                  "comes next, in a new chat with that name."]
    elif task.startswith("Choose a pen name"):
        lines += [(ROOT / "agents" / "chatgpt-pen-name-prompt.md").read_text(encoding="utf-8").strip()]
    elif task.startswith("Plan games"):
        lines += ["Using the Game API and image style files, suggest one interactive activity for each of the "
                  "first five approved chapters: activity type, what the reader practices, and the 8 scenes you'd "
                  "draw. Don't build them yet; each game gets its own prompt."]
    if s.get("custom_kickoff", "").strip():
        lines += ["", s["custom_kickoff"].strip()]
    if s.get("ask_first"):
        lines += ["", "Before you start, ask me up to five questions if anything would change your answer. If "
                  "nothing would, say so and go ahead."]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ project files

START_HERE = """# Start here

These files are the long-term memory for "{title}". Every prompt from the Book Manager is complete on its
own; these files add background, so check them before searching or guessing.

| File | What it's for |
|---|---|
{rows}

Rules of thumb: the prompt in front of you comes first, then the Project instructions, then these files.
Reuse source keys from sources-library.md; never invent a new key for a source that already has one.
Generated {status}
"""

DESCRIPTIONS = {
    "02-editorial-charter.md": "the book's rules in full: readers, safety, language, evidence, style",
    "03-content-outline.md": "every part and chapter and what each covers",
    "continuity.md": "terms, names and decisions already fixed; example names already used",
    "writing-guide.md": "how to write and format a chapter, the boxes, and what to send back",
    "glossary.md": "the book's defined terms, word for word",
    "book-so-far.md": "the full text of every approved chapter, in order",
    "sources-library.md": "a card for every source found so far, by key",
    "game-api.md": "the Game Package API: how to build an interactive activity",
    "image-style.md": "the one house look for every image",
}


def _book_so_far() -> str:
    chapters, _, _ = C.parse_outline()
    parts = []
    for c in chapters:
        meta, body = C.front_matter(C.chapter_path(c))
        if meta.get("status") == "approved":
            parts.append(f"\n\n---\n\n<!-- {C.chat_name(c['n'], c['title'])} -->\n\n{body.strip()}")
    return "# The book so far (approved chapters)\n" + "".join(parts) + "\n"


def project_files(s: dict | None = None) -> dict[str, bytes | str | Path]:
    """Every file for the ChatGPT Project, at most FILES_LIMIT."""
    import games as G
    s = s or load()
    J.report(0.1, "Rebuilding the research memory…")
    C.build_library(quiet=True)
    files: dict[str, bytes | str | Path] = {}
    for name in ("02-editorial-charter.md", "03-content-outline.md", "continuity.md"):
        if (OUT / name).exists():
            files[name] = (OUT / name).read_bytes()
    files["writing-guide.md"] = C.GUIDE.read_text(encoding="utf-8")
    glossary = ROOT / "book" / "99-back" / "glossary.md"
    if glossary.exists():
        files["glossary.md"] = glossary.read_text(encoding="utf-8")
    J.report(0.4, "Collecting the book so far…")
    if s.get("file_book"):
        files["book-so-far.md"] = _book_so_far()
    if s.get("file_research"):
        for f in sorted(OUT.glob("research-part-*.md")):
            files[f.name] = f.read_bytes()
        if (OUT / "sources-library.md").exists():
            files["sources-library.md"] = (OUT / "sources-library.md").read_bytes()
    if s.get("file_games"):
        files["game-api.md"] = G.docs_markdown()
        files["image-style.md"] = (G.DOCS / "image-style.md").read_text(encoding="utf-8")
    rows = "\n".join(f"| {n} | {DESCRIPTIONS.get(n) or ('research saved for part ' + n.split('-')[-1][:-3] + ' of the book')} |"
                     for n in sorted(files))
    files = {"00-start-here.md": START_HERE.format(title=s["title"], rows=rows, status=status()), **files}
    if len(files) > FILES_LIMIT:
        raise RuntimeError(f"{len(files)} files is more than a ChatGPT Project holds ({FILES_LIMIT}). "
                           "Turn off one of the Project file options.")
    return files


def write_files(s: dict | None = None) -> dict:
    """Write the Project files to OUT (replacing the old set) and a ZIP beside it."""
    files = project_files(s)
    J.report(0.7, "Writing the files…")
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.md"):
        old.unlink()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            raw = data.read_bytes() if isinstance(data, Path) else data.encode("utf-8") if isinstance(data, str) else data
            (OUT / name).write_bytes(raw)
            zf.writestr(name, raw)
    zpath = OUT.parent / "chatgpt-project-files.zip"
    zpath.write_bytes(buf.getvalue())
    (OUT / "instructions.txt").write_text(instructions(s), encoding="utf-8")
    (OUT / "initial-prompt.md").write_text(initial_prompt(s), encoding="utf-8")
    J.report(1.0, "Done")
    sizes = {n: (OUT / n).stat().st_size for n in files}
    return {"folder": OUT.relative_to(ROOT).as_posix(), "zip": zpath.relative_to(ROOT).as_posix(),
            "files": [{"name": n, "bytes": b, "about": DESCRIPTIONS.get(n, "")} for n, b in sizes.items()]}


def summary() -> dict:
    s = load()
    text = instructions(s)
    return {"fields": FIELDS, "values": s, "defaults": defaults(),
            "instructions": {"chars": len(text), "limit": INSTRUCTIONS_LIMIT},
            "filesLimit": FILES_LIMIT, "stale": C.library_stale(),
            "chapters": [{"n": c["n"], "name": C.chat_name(c["n"], c["title"])} for c in C.parse_outline()[0]]}

