"""This book's prompt kinds for the prompt-pack system (tools/promptpack.py).

Each builder returns a Pack: the self-contained prompt (what the clipboard gets) plus the reference
files that go in the optional ZIP. The prompt texts themselves come from chapter.py, special.py and
games.py, unchanged, so the CLI and the manager produce the same prompts.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chapter as C  # noqa: E402
import games as G  # noqa: E402
import jobs as J  # noqa: E402
from promptpack import Pack, kind  # noqa: E402

ROOT = C.ROOT
REFS = {
    "02-editorial-charter.md": "the book's rules: readers, safety, language, evidence, style",
    "03-content-outline.md": "every part and chapter, with what each covers",
    "continuity.md": "terms, names and decisions already fixed in earlier chapters",
    "sources-library.md": "a card for every source found so far, by key",
}


def _memory(part_n: int | None, include_library: bool = True) -> tuple[dict, dict]:
    """Reference files from the ChatGPT memory folder (rebuilt first, so it's never stale)."""
    J.report(0.2, "Gathering the reference files…")
    C.build_library(quiet=True)
    files, notes = {}, {}
    names = ["02-editorial-charter.md", "03-content-outline.md", "continuity.md"]
    if include_library:
        names.append("sources-library.md")
    for name in names:
        f = C.PROJECT_OUT / name
        if f.exists():
            files[name], notes[name] = f, REFS[name]
    part_file = C.PROJECT_OUT / f"research-part-{part_n}.md"
    if part_n is not None and part_file.exists():
        files[part_file.name] = part_file
        notes[part_file.name] = "research saved for the other chapters in this part"
    return files, notes


def _saved(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"The prompt wasn't created ({path.relative_to(ROOT)}).")
    return path.read_text(encoding="utf-8")


def _chapter(n: int) -> dict:
    ch, _, _ = C.get(int(n))
    return ch


@kind("research", "Research prompt", "research", "chapter",
      "Asks ChatGPT (with web search) to research one chapter and send back findings and source cards.")
def research(n: int) -> Pack:
    ch = _chapter(n)
    J.report(0.05, "Writing the research prompt…")
    C.research(ch["n"])
    prompt = _saved(ROOT / "prompts" / f"{C.chapter_path(ch).stem}-research.md")
    files, notes = _memory(ch["part"]["n"])
    return Pack("research", C.chat_name(ch["n"], ch["title"]), prompt, files, notes,
                reply="A research ZIP (or the findings as text): import it on the Save reply tab.")


@kind("write", "Writing prompt", "write", "chapter",
      "The full brief for writing one chapter or section: rules, outline position, continuity and research.")
def write(n: int) -> Pack:
    ch = _chapter(n)
    J.report(0.05, "Writing the writing prompt…")
    C.write(ch["n"])
    prompt = _saved(ROOT / "prompts" / f"{C.chapter_path(ch).stem}-write.md")
    files, notes = _memory(ch["part"]["n"], include_library=False)
    own = C.research_path(ch)
    if own.exists() and "skipped" not in own.read_text(encoding="utf-8")[:80]:
        files[own.name], notes[own.name] = own, "the research saved for this chapter"
    prompt += _brand_voice()
    return Pack("write", C.chat_name(ch["n"], ch["title"]), prompt, files, notes,
                reply="The chapter and editor notes as text: copy ChatGPT's reply and save it here.")


def _brand_voice() -> str:
    """The book's brand voice (Design › Brand Kit), if one was saved."""
    try:
        import brand as BR  # noqa: PLC0415
        if not BR.FILE.exists():
            return ""
        v = BR.load()["voice"]
        lines = [f"- {k}: {v[key]}" for k, key in (("Tone", "tone"), ("Point of view", "person"),
                                                   ("Reading level", "readingLevel"), ("Avoid", "avoid")) if v.get(key)]
        return ("\n\n## Book voice (from the author's brand)\n" + "\n".join(lines) + "\n") if lines else ""
    except Exception:  # noqa: BLE001
        return ""


@kind("revise", "Revision prompt", "revise", "chapter-with-review",
      "The previous draft plus Claude's review findings, asking for a revised draft.")
def revise(n: int) -> Pack:
    ch = _chapter(n)
    J.report(0.05, "Writing the revision prompt…")
    C.revise(ch["n"])
    stem = C.chapter_path(ch).stem
    found = sorted((ROOT / "prompts").glob(f"{stem}-revise-*.md"), key=lambda p: p.stat().st_mtime)
    if not found:
        raise RuntimeError("No revision prompt was created.")
    files, notes = _memory(None, include_library=False)
    return Pack("revise", C.chat_name(ch["n"], ch["title"]), found[-1].read_text(encoding="utf-8"), files, notes,
                reply="The revised chapter and editor notes as text: copy the reply and save it here.")


@kind("game", "Game creation prompt", "extras", "chapter",
      "Asks ChatGPT to make an interactive activity (Game API package) for an approved chapter.")
def game(n: int | None = None) -> Pack:
    J.report(0.1, "Writing the game creation prompt…")
    n = int(n) if n else None
    prompt = G.creation_prompt(n)
    name = f"Game · ch{n:02d}" if n else "Game"
    files = {f"game-api-{G.API_VERSION}.md": G.docs_markdown()}
    notes = {f"game-api-{G.API_VERSION}.md": "the complete Game Package API documentation, schemas and templates"}
    for f in sorted((G.DOCS / "templates").rglob("*.json")):
        rel = f"templates/{f.relative_to(G.DOCS / 'templates').as_posix()}"
        files[rel] = f
        notes[rel] = "part of a complete, valid example package"
    return Pack("game", name, prompt, files, notes,
                reply="game.json, activity.json and README.md in code blocks (plus any images): "
                      "copy the reply and use Import from ChatGPT reply.")


def _agent_prompt(kind_id: str, file: str, name: str, reply: str) -> Pack:
    path = ROOT / "agents" / file
    return Pack(kind_id, name, _saved(path), {}, {}, reply=reply)


@kind("pen-name", "Pen name for ChatGPT", "plan", "none",
      "Asks ChatGPT to choose its own pen name for the byline.")
def pen_name() -> Pack:
    return _agent_prompt("pen-name", "chatgpt-pen-name-prompt.md", "Pen name",
                         "A pen name: put it in book.yml (author).")


@kind("branding", "Branding brief", "plan", "none", "Asks ChatGPT for name, logo and cover ideas.")
def branding() -> Pack:
    return _agent_prompt("branding", "chatgpt-branding-prompt.md", "Branding", "Ideas to choose from.")


@kind("game-update", "Update a game to the new API", "extras", "game",
      "Asks ChatGPT to bring an installed game up to the current Game API and the unified image style.")
def game_update(game: str) -> Pack:
    J.report(0.1, "Writing the update prompt…")
    entry = G.get(game)
    prompt = G.update_prompt(game)
    J.report(0.5, "Packing the current game…")
    files = {f"{game}-{entry['version']}.zip": G.export(game, Path(C.ROOT / "dist" / "game-exports")).read_bytes(),
             f"game-api-{G.API_VERSION}.md": G.docs_markdown()}
    notes = {f"{game}-{entry['version']}.zip": "the installed game package, including its current images",
             f"game-api-{G.API_VERSION}.md": "the complete Game Package API documentation"}
    return Pack("game-update", f"Game update · {game}", prompt, files, notes,
                reply="game.json, activity.json, README.md and three images: use Import from ChatGPT reply, "
                      "with Replace/Update ticked.")


@kind("image-style", "Game image style", "extras", "none",
      "The unified look for all game images: paste it into any image chat to make or remake game art.")
def image_style() -> Pack:
    return Pack("image-style", "Game image style", G.image_style(), {}, {},
                reply="Images: import them with the game (Sheet 1, Sheet 2, Icon).")


@kind("kickoff", "Initial prompt for a new ChatGPT Project", "plan", "none",
      "The first message in the Project: gets ChatGPT oriented and starts the first task (set it up in Workspace).")
def kickoff() -> Pack:
    import workspace as W
    return Pack("kickoff", "Start here", W.initial_prompt(), {}, {},
                reply="A summary and questions: answer them in the same chat.")


@kind("ui-review", "Book Manager UI review", "plan", "none",
      "Explains the Book Manager to ChatGPT and asks for a design review to make it cleaner and easier.")
def ui_review() -> Pack:
    return _agent_prompt("ui-review", "chatgpt-ui-review-prompt.md", "Book Manager UI review",
                         "A design review: top changes, navigation, chapter screen, Copy/ZIP pattern, first run, quick wins.")


# ------------------------------------------------------------------ planning: from point one
# These turn the Workspace form (workspace.yml) into the first prompts for a new book. Each asks for one
# Markdown file in a labeled code block, so the reply can be saved where the book keeps it.

def _plan(kind_id: str, name: str, target: str, task: str, needs_before: str = "") -> Pack:
    import workspace as W
    s = W.load()
    about = (f"**Working title:** {s['title']}" + (f": {s['subtitle']}" if s.get("subtitle") else "") +
             f"\n**Readers:** {s['audience']}\n**Purpose:** {s.get('purpose', '')}\n"
             f"**Focus:** {s['locale']}. **Reading level:** {s['reading_level']}. **Voice:** {s['voice']}")
    before = ""
    if needs_before:
        f = ROOT / needs_before
        before = (f"\n\n## What's decided so far (`{needs_before}`)\n\n{f.read_text(encoding='utf-8').strip()}"
                  if f.exists() else f"\n\n(No `{needs_before}` yet; work from the description above.)")
    prompt = (f"# {name}\n\nCHAT NAME: Plan · {name}\n\nYou're helping plan a nonfiction book from the ground up. "
              f"Everything you need is in this message.\n\n## The book\n\n{about}{before}\n\n## Your task\n\n{task}\n\n"
              f"## What to send back\n\nFirst ask me up to five questions if the answers would change the result, and "
              f"wait for my answers. Then send the whole file in one code block, with its name on the line just above:\n\n"
              f"    **{target}**\n    ```markdown\n    ...\n    ```\n\nI'll save it as `{target}`.")
    return Pack(kind_id, name, prompt, {}, {}, reply=f"{target} in a code block: save it in the project.")


@kind("idea", "Shape the book idea", "plan", "none",
      "Turns the Workspace description into a sharp one-page idea: promise, readers, scope, what it isn't.")
def idea() -> Pack:
    return _plan("idea", "Book idea", "research/00-book-idea.md",
                 "Write a one-page book idea: the promise to the reader in one sentence; who it's for and who it isn't "
                 "for; the 3–5 problems it solves; what makes it different from existing books; what's out of scope; "
                 "and the risks (accuracy, safety, sensitivity) to plan for.")


@kind("brief", "Project brief", "plan", "none",
      "A project brief: goals, readers, format, sources, rules and how the AI-assisted workflow runs.")
def brief() -> Pack:
    return _plan("brief", "Project brief", "PROJECT-BRIEF.md",
                 "Write the project brief: goals and success measures; readers and their situations; format and "
                 "length; evidence standards and kinds of sources; safety and sensitivity rules; voice; and how the "
                 "work is split (you research and write, Claude prepares prompts and checks, the editor approves).",
                 "research/00-book-idea.md")


@kind("charter", "Editorial charter", "plan", "none",
      "The rules every chapter follows: readers, non-negotiables, language, evidence, style, boxes.")
def charter() -> Pack:
    return _plan("charter", "Editorial charter", "research/02-editorial-charter.md",
                 "Write the editorial charter every chapter will follow: readers; non-negotiable rules; language "
                 "(terms to use and avoid); evidence and citation rules; style; structure guidance; and how side "
                 "boxes or examples are used. Be specific enough that a reviewer could check a draft against it.",
                 "PROJECT-BRIEF.md")


@kind("outline", "Content outline", "plan", "none",
      "Parts and chapters, each with what it covers, in the format the Book Manager reads.")
def outline() -> Pack:
    return _plan("outline", "Content outline", "research/03-content-outline.md",
                 "Write the content outline: parts (each with the question it answers) and numbered chapters (each "
                 "with a one-paragraph description of what it covers), in reading order, building from basics. Use exactly "
                 "this format, so the Book Manager can read it: a part is a line `## Part N: Title (`NN-short-slug`)`, "
                 "followed by its chapters, each on one line `N. **Chapter title**: what it covers`, numbered "
                 "continuously across parts.",
                 "research/02-editorial-charter.md")
